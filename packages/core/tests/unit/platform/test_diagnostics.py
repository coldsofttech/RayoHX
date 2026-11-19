"""Diagnostics: explanations, network and stream checks, and reports that carry no secrets."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from rayohx.config import DownloadConfig, NetworkConfig
from rayohx.errors import ConfigurationError, HTTPError, NetworkConnectionError
from rayohx.platform import Rayo
from rayohx.platform.diagnostics import (
    Sanitizer,
    contains_secret,
    diagnose_stream,
    explain,
    probe_network,
)
from rayohx.platform.jobs import JobState, RetryPolicy
from rayohx.platform.metrics import to_prometheus
from tests.unit.platform import fakes
from tests.unit.platform.conftest import wait_state

TOKEN = "tok-Zq81xKd93LmPw"
COOKIE = "sess-9f8e7d6c5b4a"
BEARER = "Bearer s3cr3t-Auth-Value-77"
PASSWORD = "hunter2-hunter2"
URL = f"https://media.test/show/master.m3u8?token={TOKEN}&sig=abc123def456"
MEDIA = "#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nseg0.ts\n#EXT-X-ENDLIST\n"
SEEDS = [TOKEN, COOKIE, BEARER, PASSWORD, "s3cr3t-Auth-Value-77", "abc123def456"]


# --- explanations ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "word"),
    [
        ("DNS_FAILED", "name"),
        ("HTTP_403", "refus"),
        ("HTTP_404", "exist"),
        ("HTTP_503", "server"),
        ("STORAGE_LOW", "space"),
        ("TLS_FAILED", "certificate"),
    ],
)
def test_known_codes_have_plain_explanations(code: str, word: str) -> None:
    found = explain(code)
    assert found.code == code
    assert found.next_steps
    assert word in (found.title + found.what + found.why).lower()


def test_unknown_codes_get_their_category_not_a_crash() -> None:
    found = explain("SOMETHING_NEW")
    assert found.title
    assert explain(None).title


def test_attempts_are_described() -> None:
    found = explain("HTTP_503", attempts=[{"attempt": 1, "outcome": "failed"}] * 3)
    assert "3" in found.tried


# --- sanitizer ---------------------------------------------------------------------------


def test_the_sanitizer_removes_literals_in_every_form() -> None:
    clean = Sanitizer([TOKEN, "a b c d e f g"], home=Path("/home/alice"))
    data = {
        "msg": f"failed {TOKEN} and %s" % "a%20b%20c%20d%20e%20f%20g",
        "nested": [{"path": "/home/alice/Downloads/x.mp4"}],
        "authorization": "anything",
    }
    out = json.dumps(clean.clean(data))
    assert TOKEN not in out
    assert "alice" not in out
    assert "anything" not in out
    assert contains_secret(out, [TOKEN]) == []
    assert contains_secret(f"x{TOKEN}", [TOKEN]) == [TOKEN]


# --- network and stream checks -----------------------------------------------------------


def test_a_missing_name_is_reported_without_the_query() -> None:
    def no_dns(*_: object, **__: object) -> list[object]:
        raise OSError("Name or service not known")

    report = probe_network(URL, NetworkConfig(), resolver=no_dns)
    assert report.code == "DNS_FAILED"
    assert not report.ok
    text = json.dumps(report.to_dict())
    assert TOKEN not in text
    assert "abc123def456" not in text
    assert report.steps[0].name == "dns"


def test_only_http_addresses_are_checked() -> None:
    with pytest.raises(ConfigurationError):
        probe_network("file:///etc/passwd")


def test_a_stream_is_described_from_text() -> None:
    report = diagnose_stream("https://media.test/a.m3u8", playlist_text=MEDIA, probe=False)
    assert report.media is not None
    assert report.code is None


def test_a_broken_stream_is_a_finding(tmp_path: Path) -> None:
    report = diagnose_stream("https://media.test/a.m3u8", playlist_text="not a playlist")
    assert report.media is None
    assert report.code
    assert report.findings[0].level == "error"


# --- the job report ----------------------------------------------------------------------


def seeded_job(rayo: Rayo, exc: Exception) -> str:
    fakes.FakeDownloader.scripts["*"] = fakes.fail_with(exc)
    config = DownloadConfig(
        network=NetworkConfig(
            headers={"Authorization": BEARER}, cookies={"session": COOKIE}, proxy=None
        )
    )
    job = rayo.queue.add(
        URL, config=config, secrets={"password": PASSWORD}, retry=RetryPolicy(max_attempts=1)
    )
    return job.id


def test_explaining_a_failed_job(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    job_id = seeded_job(rayo, HTTPError("https://media.test/seg0.ts?token=" + TOKEN, 503))
    rayo.queue.start()
    wait_state(rayo, job_id, JobState.FAILED, timeout=15)
    found = rayo.diagnostics.explain_job(job_id)
    assert found is not None
    assert found["explanation"]["code"] == "HTTP_503"
    assert TOKEN not in json.dumps(found)
    assert rayo.diagnostics.explain_job("nope") is None


def test_the_report_contains_no_seeded_secret(
    make_rayo: Callable[..., Rayo], tmp_path: Path
) -> None:
    rayo = make_rayo()
    job_id = seeded_job(rayo, NetworkConnectionError(f"reset while fetching {URL} with {BEARER}"))
    rayo.queue.start()
    wait_state(rayo, job_id, JobState.FAILED, timeout=15)

    report = rayo.diagnostics.report(job_id)
    assert report.path is not None
    for text in (report.text, report.path.read_text(encoding="utf-8")):
        assert contains_secret(text, SEEDS) == [], "a secret leaked into the report"
        assert str(Path.home()) not in text or str(Path.home()) in ("/", "")
    data = report.data
    assert data["report"]["sanitized"] is True
    assert data["job"]["id"] == job_id
    assert data["explanation"]["code"]
    assert data["environment"]["rayohx"]
    # The names of the secrets are shown, never their values.
    assert "headers: Authorization" in data["job"]["protected_settings"]
    assert "cookies: session" in data["job"]["protected_settings"]
    assert report.path.stat().st_mode & 0o077 == 0
    assert [r["name"] for r in rayo.diagnostics.reports()] == [report.path.name]


def test_a_report_without_a_job_is_about_the_machine(rayo: Rayo) -> None:
    report = rayo.diagnostics.report(save=False)
    assert report.path is None
    assert "storage" in report.data
    assert "queue" in report.data


def test_a_report_for_a_missing_job_is_refused(rayo: Rayo) -> None:
    with pytest.raises(ConfigurationError):
        rayo.diagnostics.report("ghost")


def test_a_report_can_include_the_stream_check(rayo: Rayo, monkeypatch: pytest.MonkeyPatch) -> None:
    from rayohx.platform.diagnostics import service

    def fake(url: str, **_: object) -> object:
        return diagnose_stream(url, playlist_text=MEDIA, probe=False)

    monkeypatch.setattr(service, "diagnose_stream", fake)
    report = rayo.diagnostics.report(url=URL, include_stream=True, save=False)
    assert report.data["stream"]["media"] is not None
    assert contains_secret(report.text, SEEDS) == []


# --- metrics -----------------------------------------------------------------------------


def test_metrics_count_jobs_and_render_as_prometheus(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts["*"] = fakes.ok
    job = rayo.queue.add("https://media.test/a/master.m3u8")
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.COMPLETED)
    metrics = rayo.metrics()
    assert metrics["queue"]["completed"] == 1
    assert metrics["queue"]["queued"] == 0
    assert metrics["downloads"]["bytes_written_total"] >= 0
    assert metrics["storage"]["level"] == "ok"
    text = to_prometheus(metrics)
    assert "rayohx_queue_completed 1" in text
    for line in text.strip().splitlines():
        name, _, value = line.rpartition(" ")
        assert name.startswith("rayohx_")
        assert value
