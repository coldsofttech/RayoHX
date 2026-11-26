"""The fixture script builds the right FFmpeg commands, without needing FFmpeg itself."""

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rayohx_pytest.fixtures import FIXTURES

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "make_media_fixtures.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("make_media_fixtures_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_output_folder_is_the_package_media_fixtures() -> None:
    module = _load()

    assert FIXTURES / "media" == module.OUT


def test_run_calls_ffmpeg_quietly_and_checks_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load()
    calls: list[tuple[list[str], bool]] = []

    def fake_run(command: list[str], check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr(subprocess, "run", fake_run)

    module.run("-i", "in", "out.ts")

    assert calls == [
        (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "in", "out.ts"], True)
    ]


def test_main_stops_when_ffmpeg_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    monkeypatch.setattr("shutil.which", lambda _name: None)

    assert module.main() == 1
    assert "ffmpeg is needed" in capsys.readouterr().out


def test_main_writes_every_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load()
    module.OUT = tmp_path
    commands: list[list[str]] = []
    monkeypatch.setattr("shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr(module, "run", lambda *args: commands.append(list(args)))

    assert module.main() == 0

    targets = {Path(command[-1]).name for command in commands}
    assert {"h264_aac.ts", "hevc_aac.ts", "h264_only_frag.mp4", "v%v.m3u8"} <= targets
    assert (tmp_path / "hls_ts").is_dir()
    assert (tmp_path / "hls_fmp4").is_dir()
