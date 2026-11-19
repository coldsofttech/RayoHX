"""``rayo.diagnostics``: explaining failures and collecting a report that is safe to share."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rayohx import __version__
from rayohx.capabilities import detect
from rayohx.config import NetworkConfig
from rayohx.errors import ConfigurationError, RayoHXError
from rayohx.platform.diagnostics.explain import Explanation, explain
from rayohx.platform.diagnostics.network import NetworkReport, probe_network
from rayohx.platform.diagnostics.sanitize import Sanitizer, secret_values, url_secrets
from rayohx.platform.diagnostics.storage_findings import storage_findings
from rayohx.platform.diagnostics.stream import Finding, StreamReport, diagnose_stream
from rayohx.platform.events import Severity
from rayohx.platform.jobs.options import config_from_options

if TYPE_CHECKING:
    from collections.abc import Callable

    from rayohx.platform.diagnostics.registry import ReportRegistry
    from rayohx.platform.events import EventStore
    from rayohx.platform.jobs.model import JobRecord
    from rayohx.platform.paths import PlatformPaths
    from rayohx.platform.queue.queue import Queue
    from rayohx.platform.queue.repository import JobRepository
    from rayohx.platform.secrets import SecretStore
    from rayohx.platform.storage.service import StorageService

REPORT_VERSION = 1
EVENT_LIMIT = 60


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """A report, already cleaned, and where it was saved."""

    data: dict[str, Any]
    path: Path | None = None

    @property
    def text(self) -> str:
        return json.dumps(self.data, indent=2, sort_keys=True, ensure_ascii=False)


class DiagnosticsService:
    """Failure explanations, network and stream checks, and sanitized reports."""

    def __init__(
        self,
        repository: JobRepository,
        events: EventStore,
        queue: Queue,
        storage: StorageService,
        secrets: SecretStore,
        paths: PlatformPaths,
        registry: ReportRegistry,
        *,
        download_dir: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._jobs = repository
        self._events = events
        self._queue = queue
        self._storage = storage
        self._secrets = secrets
        self._paths = paths
        self._registry = registry
        self._download_dir = download_dir
        self._clock = clock

    # --- explaining ------------------------------------------------------------------------

    def explain(self, code: str | None) -> Explanation:
        """What an error code means and what to do about it."""
        return explain(code)

    def explain_job(self, job_id: str) -> dict[str, Any] | None:
        """Why a job failed (or how it went), with what was tried. ``None`` if no such job."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        attempts = self._queue.attempts(job_id)
        clean = Sanitizer(
            secret_values(self._job_secrets(job)) | url_secrets(job.spec.url), home=Path.home()
        )
        result: dict[str, Any] = {
            "job": self._job_summary(job),
            "attempts": attempts,
            "explanation": None,
        }
        if job.error_code:
            result["explanation"] = explain(job.error_code, attempts=attempts).to_dict()
            result["error"] = job.error_message
        return dict(clean.clean(result))

    # --- checking --------------------------------------------------------------------------

    def network(
        self,
        url: str,
        *,
        job_id: str | None = None,
        config: NetworkConfig | None = None,
        timeout: float = 10.0,
    ) -> NetworkReport:
        """Try to reach ``url`` and say where it fails. A job's headers and proxy are used."""
        settings = config or (self._job_config(job_id).network if job_id else NetworkConfig())
        return probe_network(url, settings, timeout=timeout)

    def stream(
        self, url: str, *, job_id: str | None = None, config: NetworkConfig | None = None
    ) -> StreamReport:
        """Describe a stream and list what is unusual about it."""
        if job_id:
            built = self._job_config(job_id)
            return diagnose_stream(url, network=built.network, selection=built.selection)
        return diagnose_stream(url, network=config)

    # --- the report ------------------------------------------------------------------------

    def report(
        self,
        job_id: str | None = None,
        *,
        url: str | None = None,
        include_network: bool = False,
        include_stream: bool = False,
        save: bool = True,
        network_timeout: float = 10.0,
    ) -> DiagnosticReport:
        """Collect a report with no secrets in it.

        With ``job_id`` it is about that job. With ``url`` (or the job's address, when
        ``include_network`` or ``include_stream`` is set) the server is checked too.
        """
        job = self._jobs.get(job_id) if job_id else None
        if job_id and job is None:
            raise ConfigurationError(f"There is no job {job_id}.")
        known: set[str] = set()
        if job is not None:
            known = secret_values(self._job_secrets(job)) | url_secrets(job.spec.url)
        if url:
            known |= url_secrets(url)
        clean = Sanitizer(known, home=Path.home())

        report: dict[str, Any] = {
            "report": {
                "version": REPORT_VERSION,
                "generated_at": self._clock(),
                "sanitized": True,
                "job": job_id,
            },
            "environment": self._environment(),
            "queue": self._queue.stats(),
            "storage": self._storage_section(),
            "recent_problems": self._recent(job_id),
        }
        findings: list[Finding] = []
        if job is not None:
            report["job"] = self._job_section(job)
            if job.error_code:
                report["explanation"] = explain(
                    job.error_code, attempts=self._queue.attempts(job.id)
                ).to_dict()
        target = url or (job.spec.url if job is not None else None)
        if target and (include_network or include_stream):
            try:
                if include_network:
                    probe = self.network(target, job_id=job_id, timeout=network_timeout)
                    report["network"] = probe.to_dict()
                    if probe.code:
                        report.setdefault("explanation", explain(probe.code).to_dict())
                if include_stream:
                    shown = self.stream(target, job_id=job_id)
                    report["stream"] = shown.to_dict()
                    findings += list(shown.findings)
            except RayoHXError as exc:
                report["network_error"] = exc.describe()
        findings += self._storage_findings()
        report["findings"] = [f.to_dict() for f in findings]
        cleaned = dict(clean.clean(report))

        path = self._save(cleaned, job_id) if save else None
        return DiagnosticReport(cleaned, path)

    def reports(self, limit: int = 50) -> list[dict[str, object]]:
        """The reports that were saved, newest first."""
        return self._registry.listing(limit)

    # --- sections --------------------------------------------------------------------------

    def _environment(self) -> dict[str, Any]:
        caps = detect()
        return {
            "rayohx": __version__,
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "portable": self._paths.portable,
            "schema_version": self._queue._repo._db.schema_version,
            "ffmpeg": _program(caps.ffmpeg),
            "ffprobe": _program(caps.ffprobe),
        }

    def _storage_section(self) -> dict[str, Any]:
        snapshot = self._storage.snapshot()
        data = snapshot.to_dict()
        data["workspaces"] = [w.to_dict() for w in self._storage.workspaces()]
        return data

    def _storage_findings(self) -> list[Finding]:
        return storage_findings(self._storage.snapshot(), self._storage.workspaces())

    def _recent(self, job_id: str | None) -> list[dict[str, Any]]:
        events = self._events.query(
            job_id=job_id, min_severity=Severity.WARNING, limit=EVENT_LIMIT, newest_first=True
        )
        return [e.to_dict() for e in reversed(events)]

    def _job_summary(self, job: JobRecord) -> dict[str, Any]:
        data = job.to_dict()
        data["output_path"] = Path(job.output_path).name if job.output_path else None
        return data

    def _job_section(self, job: JobRecord) -> dict[str, Any]:
        events = self._events.query(job_id=job.id, limit=500)
        failed = [
            {"segment": e.payload.get("segment"), "message": e.payload.get("message")}
            for e in events
            if e.type == "download.segment_failed"
        ]
        result = job.result or {}
        return {
            **self._job_summary(job),
            "settings": dict(job.spec.options),
            "protected_settings": self._secret_names(job),
            "retry_policy": job.spec.retry.to_dict(),
            "attempt_history": self._queue.attempts(job.id),
            "failed_segments": failed,
            "storage": self._storage.job_usage(job.id),
            "verification": result.get("integrity"),
            "finalization": {
                "processing": result.get("processing"),
                "metadata_written": result.get("metadata"),
                "notes": result.get("notes", []),
            },
        }

    # --- secrets and files -----------------------------------------------------------------

    def _job_secrets(self, job: JobRecord) -> dict[str, Any]:
        ref = self._jobs.secret_ref(job.id)
        found = self._secrets.get(ref) if ref else None
        return found or {}

    def _secret_names(self, job: JobRecord) -> list[str]:
        """What secrets the job has, by name only."""
        found = self._job_secrets(job)
        names: list[str] = []
        for key, value in sorted(found.items()):
            if isinstance(value, dict):
                names.append(f"{key}: {', '.join(sorted(value))}")
            else:
                names.append(key)
        return names

    def _job_config(self, job_id: str | None) -> Any:
        job = self._jobs.get(job_id) if job_id else None
        if job is None:
            raise ConfigurationError(f"There is no job {job_id}.")
        return config_from_options(
            job.spec.options, self._job_secrets(job), default_directory=self._download_dir
        )

    def _save(self, data: dict[str, Any], job_id: str | None) -> Path:
        folder = self._paths.reports_dir
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self._clock()))
        name = f"rayohx-report-{stamp}{'-' + job_id if job_id else ''}.json"
        target = folder / name
        counter = 1
        while target.exists():
            counter += 1
            target = folder / f"{target.stem.rsplit('-#', 1)[0]}-#{counter}.json"
        text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        target.write_text(text + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            target.chmod(0o600)
        problem = (data.get("explanation") or {}).get("title") or "no problem found"
        self._registry.add(target, job_id=job_id, summary=str(problem))
        return target


def _program(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"found": False}
    version = None
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        done = subprocess.run(  # noqa: S603 - a program found by name, with a fixed argument
            [str(path), "-version"], capture_output=True, text=True, timeout=5, check=False
        )
        version = (done.stdout or "").splitlines()[0] if done.stdout else None
    return {"found": True, "version": version}
