import re
import sys

import pytest
from typer.testing import CliRunner

import rayohx
from rayohx_cli import output
from rayohx_cli.cli import app, run

runner = CliRunner()

ANSI = re.compile(chr(27) + re.escape("[") + "[0-9;]*m")


def plain(text: str) -> str:
    """Remove color codes. Typer's help always colors output on GitHub Actions."""
    return ANSI.sub("", text)


def test_help_lists_options() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for text in ("--version", "--verbose", "--quiet", "--no-color"):
        assert text in plain(result.output)


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert rayohx.__version__ in result.output


def test_verbose_and_quiet_conflict() -> None:
    result = runner.invoke(app, ["--verbose", "--quiet"])

    assert result.exit_code == 2


def _boom() -> None:
    raise RuntimeError("boom")


def test_unexpected_error_is_short_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["rayohx"])
    monkeypatch.setattr(output.settings, "verbose", False)
    monkeypatch.setattr("rayohx_cli.cli.app", _boom)

    with pytest.raises(SystemExit) as exit_info:
        run()

    stderr = capsys.readouterr().err
    assert exit_info.value.code == 1
    assert "RuntimeError: boom" in stderr
    assert "--verbose" in stderr
    assert "Traceback" not in stderr


def test_unexpected_error_shows_traceback_with_verbose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["rayohx", "--verbose"])
    monkeypatch.setattr(output.settings, "verbose", True)
    monkeypatch.setattr("rayohx_cli.cli.app", _boom)

    with pytest.raises(SystemExit):
        run()

    assert "Traceback" in capsys.readouterr().err
