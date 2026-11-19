"""``rayohx daemon`` as a real process, and ``rayohx migrate``."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from rayohx_cli.cli import app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(os.name == "nt", reason="needs POSIX signals")
def test_the_daemon_serves_health_and_stops_on_sigterm(tmp_path: Path) -> None:
    port = free_port()
    env = {
        **os.environ,
        "RAYOHX_HOME": str(tmp_path / "home"),
        "RAYOHX_DOWNLOAD_DIR": str(tmp_path),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from rayohx_cli.cli import run; run()",
            "daemon",
            "--port",
            str(port),
        ],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        body: dict[str, Any] = {}
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    body = json.loads(r.read())
                break
            except OSError:
                time.sleep(0.1)
        assert body["status"] == "ok"
        assert body["runner"] == "this process"
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
    assert process.stderr is not None
    lines = [
        json.loads(line) for line in process.stderr.read().splitlines() if line.startswith("{")
    ]
    messages = [line["message"] for line in lines]
    assert "daemon started" in messages
    assert "daemon stopped" in messages


def test_migrate_reports_the_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAYOHX_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(app, ["migrate", "--json"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["up_to_date"] is True
    assert data["defaults"] == "nothing_to_import"
    assert "up to date" in CliRunner().invoke(app, ["migrate"]).stdout
