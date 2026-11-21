"""Running the command with ``python -m rayohx_cli``."""

import runpy

import pytest


def test_running_the_package_starts_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    monkeypatch.setattr("rayohx_cli.cli.run", lambda: started.append("run"))
    runpy.run_module("rayohx_cli", run_name="__main__")
    assert started == ["run"]


def test_importing_the_module_does_not_start_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    monkeypatch.setattr("rayohx_cli.cli.run", lambda: started.append("run"))
    runpy.run_module("rayohx_cli.__main__", run_name="rayohx_cli.__main__")
    assert started == []
