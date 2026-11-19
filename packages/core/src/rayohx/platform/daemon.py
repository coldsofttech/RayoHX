"""The daemon: runs the queue until told to stop, and answers health checks.

``Daemon`` is what ``rayohx daemon`` runs, and what a service manager (systemd, Windows Task
Scheduler, Docker) keeps alive. It does no download work itself: it starts the queue runner,
reports on it over a small HTTP endpoint, writes structured log lines, and stops cleanly when
asked, which puts running jobs back in the queue so the next start continues them.

Endpoints (JSON, no authentication, loopback by default; they show state, never settings):

* ``/health``: 200 while the process is working; the body says what the runner is doing.
* ``/ready``: 200 once the runner has started, else 503 (use it for readiness probes).
* ``/metrics``: Prometheus text, only when ``metrics=True``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

from rayohx import __version__
from rayohx.platform.events import Severity
from rayohx.platform.metrics import to_prometheus

if TYPE_CHECKING:
    from rayohx.platform.events import PlatformEvent
    from rayohx.platform.facade import Rayo

logger = logging.getLogger("rayohx.daemon")
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_LEVELS = {
    Severity.DEBUG: logging.DEBUG,
    Severity.INFO: logging.INFO,
    Severity.WARNING: logging.WARNING,
    Severity.ERROR: logging.ERROR,
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy for log collectors, and nothing a person must parse."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            entry.update(extra)
        if record.exc_info:
            entry["error"] = type(record.exc_info[1]).__name__  # never the traceback's locals
        return json.dumps(entry, sort_keys=True, default=str)


def configure_logging(stream: Any = None, *, level: int = logging.INFO) -> logging.Handler:
    """Send ``rayohx.*`` log lines to ``stream`` (stderr) as JSON. Returns the handler."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("rayohx")
    root.addHandler(handler)
    root.setLevel(level)
    return handler


class Daemon:
    """Runs a ``Rayo`` queue and serves ``/health``."""

    def __init__(
        self,
        rayo: Rayo,
        *,
        host: str = "127.0.0.1",
        port: int | None = 8765,
        metrics: bool = False,
        max_active: int | None = None,
    ) -> None:
        self.rayo = rayo
        self.host = host
        self.port = port
        self.metrics = metrics
        self.max_active = max_active
        self.started_at: float | None = None
        self.recovered: list[str] = []
        self._stop = threading.Event()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # --- state -----------------------------------------------------------------------------

    @property
    def health_port(self) -> int | None:
        """The port the health endpoint listens on (useful when ``port=0`` chose one)."""
        return self._server.server_address[1] if self._server else None

    def health(self) -> dict[str, Any]:
        stats = self.rayo.queue.stats()
        level = self.rayo.storage.snapshot().level.name.lower()
        return {
            "status": "ok",
            "version": __version__,
            "uptime_seconds": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "runner": stats["runner"],
            "queued": stats["counts"]["queued"],
            "active": stats["active"],
            "storage": level,
            "schema_version": self.rayo.schema_version,
        }

    @property
    def ready(self) -> bool:
        return self.rayo.queue.running

    def request_stop(self) -> None:
        """Ask ``run`` to return. Safe from a signal handler or another thread."""
        self._stop.set()

    # --- running ---------------------------------------------------------------------------

    def start(self) -> None:
        """Start the queue and the health endpoint. Raises if another process runs the queue."""
        queue = self.rayo.queue
        if self.max_active is not None:
            queue.max_active = self.max_active
        self.rayo.events.subscribe(self._log_event)
        self.recovered = list(queue.start())
        self.started_at = time.time()
        if self.port is not None:
            self._serve(self.port)
        logger.info(
            "daemon started",
            extra={"fields": {"recovered": len(self.recovered), "health_port": self.health_port}},
        )

    def run(self) -> None:
        """Start, wait until ``request_stop``, then stop cleanly."""
        self.start()
        try:
            self._stop.wait()
        finally:
            self.stop()

    def stop(self) -> None:
        logger.info("daemon stopping")
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.rayo.queue.stop()
        logger.info("daemon stopped")

    # --- internals -------------------------------------------------------------------------

    def _log_event(self, event: PlatformEvent) -> None:
        if event.severity < Severity.INFO:
            return
        fields = {"event": event.type, "job": event.job_id, **dict(event.payload)}
        logger.log(_LEVELS.get(event.severity, logging.INFO), event.type, extra={"fields": fields})

    def _serve(self, port: int) -> None:
        if self.host not in LOOPBACK:
            logger.warning(
                "the health endpoint is not on loopback",
                extra={"fields": {"host": self.host}},
            )
        daemon = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/health":
                    self._send(200, json.dumps(daemon.health()), "application/json")
                elif path == "/ready":
                    ok = daemon.ready
                    body = json.dumps({"ready": ok})
                    self._send(200 if ok else 503, body, "application/json")
                elif path == "/metrics" and daemon.metrics:
                    text = to_prometheus(daemon.rayo.metrics())
                    self._send(200, text, "text/plain; version=0.0.4")
                else:
                    self._send(404, json.dumps({"error": "not found"}), "application/json")

            def _send(self, status: int, body: str, kind: str) -> None:
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_: object) -> None:  # the access log would be noise
                return

        self._server = ThreadingHTTPServer((self.host, port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="rayohx-health", daemon=True
        )
        self._thread.start()
