"""The ``storage`` and ``diagnostics`` commands."""

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from rayohx import Rayo
from rayohx.platform.secrets import MemorySecretStore
from typer.testing import CliRunner

from rayohx_cli.cli import app


@pytest.fixture(autouse=True)
def platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    real = Rayo

    def make(home: Path | None = None, **kwargs: Any) -> Rayo:
        return real(
            home=tmp_path / "platform",
            download_dir=tmp_path / "dl",
            secrets=MemorySecretStore(),
            **kwargs,
        )

    monkeypatch.setattr("rayohx_cli.cli.queue.Rayo", make)
    return tmp_path / "platform"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def invoke(runner: CliRunner, *args: str, code: int = 0) -> Any:
    result = runner.invoke(app, list(args), catch_exceptions=False)
    assert result.exit_code == code, result.stdout + result.stderr
    return result


def test_status_shows_disk_use(runner: CliRunner) -> None:
    data = json.loads(invoke(runner, "storage", "status", "--json").stdout)
    assert data["level"] == "ok"
    assert data["policy"]["warn_below"] is None
    assert "free" in invoke(runner, "storage", "status").stdout


def test_the_policy_is_set_shown_and_cleared(runner: CliRunner) -> None:
    invoke(runner, "storage", "policy", "--warn", "10GB", "--pause", "5GB", "--stop", "1GB")
    shown = json.loads(invoke(runner, "storage", "policy", "--json").stdout)
    assert (shown["warn_below"], shown["pause_below"], shown["stop_below"]) == (
        10 * 1024**3,
        5 * 1024**3,
        1024**3,
    )
    invoke(runner, "storage", "policy", "--low-storage")
    assert json.loads(invoke(runner, "storage", "policy", "--json").stdout)["low_storage_mode"]
    invoke(runner, "storage", "policy", "--clear")
    assert json.loads(invoke(runner, "storage", "policy", "--json").stdout)["warn_below"] is None


def test_a_policy_out_of_order_is_a_usage_error(runner: CliRunner) -> None:
    result = invoke(runner, "storage", "policy", "--warn", "1GB", "--pause", "5GB", code=2)
    assert "order" in result.stderr


def test_cleanup_previews_then_removes_only_with_yes(runner: CliRunner, tmp_path: Path) -> None:
    downloads = tmp_path / "dl"
    stale = downloads / ".rayohx-old"
    stale.mkdir(parents=True)
    (stale / "state.json").write_text("{}")
    (stale / "x.part").write_bytes(b"x" * 100)
    old = time.time() - 30 * 86400
    for item in (stale / "state.json", stale / "x.part", stale):
        os.utime(item, (old, old))
    (downloads / "keep.mp4").write_bytes(b"movie")

    preview = invoke(runner, "storage", "cleanup")
    assert "Would free" in preview.stdout
    assert stale.exists()
    invoke(runner, "storage", "cleanup", "--yes")
    assert not stale.exists()
    assert (downloads / "keep.mp4").read_bytes() == b"movie"
    assert json.loads(invoke(runner, "storage", "workspaces", "--json").stdout) == []


def test_explain_an_error_code(runner: CliRunner) -> None:
    out = invoke(runner, "diagnostics", "explain", "HTTP_403").stdout
    assert "HTTP_403" in out
    data = json.loads(invoke(runner, "diagnostics", "explain", "DNS_FAILED", "--json").stdout)
    assert data["explanation"]["code"] == "DNS_FAILED"
    assert data["job"] is None


def test_report_is_saved_and_listed(runner: CliRunner) -> None:
    invoke(runner, "queue", "add", "https://media.test/a.m3u8?token=SuperSecretToken123")
    out = invoke(runner, "diagnostics", "report", "--json").stdout
    assert "SuperSecretToken123" not in out
    assert json.loads(out)["report"]["sanitized"] is True
    listing = json.loads(invoke(runner, "diagnostics", "reports", "--json").stdout)
    assert len(listing) == 1
    assert listing[0]["name"].startswith("rayohx-report-")
