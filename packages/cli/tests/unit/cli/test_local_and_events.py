"""Playlists from local files, and the ``--events`` stream."""

import json
from pathlib import Path

from typer.testing import CliRunner

from rayohx_cli.cli import app
from tests.helpers.cli import BASE, Serve
from tests.helpers.site import hls_site


def local_playlist(tmp_path: Path) -> tuple[Path, str]:
    site = hls_site("ts", "one")
    path = tmp_path / "master.m3u8"
    path.write_bytes(site.files["one/master.m3u8"])
    return path, BASE + "one/"


def test_info_reads_a_local_playlist(runner: CliRunner, serve: Serve, tmp_path: Path) -> None:
    serve(hls_site("ts", "one"))
    path, base = local_playlist(tmp_path)
    result = runner.invoke(app, ["info", str(path), "--base-url", base, "--json"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["type"] == "master"
    assert data["variants"][0]["url"].startswith(base)


def test_download_reads_a_local_playlist(runner: CliRunner, serve: Serve, tmp_path: Path) -> None:
    site = serve(hls_site("ts", "one"))
    path, base = local_playlist(tmp_path)
    out = tmp_path / "local.mp4"
    result = runner.invoke(app, ["download", str(path), "--base-url", base, "-o", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.exists()
    assert "one/master.m3u8" not in site.log  # the playlist was read from disk


def test_a_file_that_is_not_a_playlist_is_explained(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "notes.m3u8"
    path.write_text("hello", encoding="utf-8")
    result = runner.invoke(app, ["info", str(path)])
    assert result.exit_code == 1
    assert "EXTM3U" in result.stderr


def test_events_are_json_lines_on_stderr(runner: CliRunner, serve: Serve, tmp_path: Path) -> None:
    serve(hls_site("ts", "one"))
    out = tmp_path / "e.mp4"
    result = runner.invoke(app, ["download", BASE + "one/master.m3u8", "-o", str(out), "--events"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == str(out)
    events = [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]
    kinds = [event["type"] for event in events]
    assert kinds[0] == "download_started"
    assert "download_completed" in kinds
    assert all("download_id" in event and "state" in event for event in events)
