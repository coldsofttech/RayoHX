"""Exit codes by kind of failure, the legacy escape hatch, and --non-interactive."""

import json
from pathlib import Path
from typing import Any

import pytest
from rayohx import Rayo
from rayohx.enums import DownloadState, ErrorCategory
from rayohx.errors import (
    AuthenticationError,
    HTTPError,
    InsufficientStorageError,
    VerificationError,
)
from rayohx.models import DownloadProgress, DownloadResult
from rayohx.platform.secrets import MemorySecretStore
from typer.testing import CliRunner

from rayohx_cli.cli import app
from rayohx_cli.cli.common import (
    EXIT_AUTH,
    EXIT_AUTOMATION,
    EXIT_PARTIAL,
    EXIT_STORAGE,
    EXIT_VERIFICATION,
    exit_for_batch,
    exit_for_category,
    exit_for_code,
    exit_for_error,
)
from tests.unit.cli.test_queue import InstantDownloader


@pytest.fixture(autouse=True)
def platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "platform"
    real = Rayo

    def make(home: Path | None = None, **kwargs: Any) -> Rayo:
        return real(
            home=tmp_path / "platform",
            download_dir=tmp_path / "dl",
            secrets=MemorySecretStore(),
            downloader_factory=InstantDownloader,
            **kwargs,
        )

    monkeypatch.setattr("rayohx_cli.cli.queue.Rayo", make)
    monkeypatch.delenv("RAYOHX_EXIT_CODES", raising=False)
    return home


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_each_kind_of_failure_has_its_code() -> None:
    assert exit_for_category(ErrorCategory.VERIFICATION) == EXIT_VERIFICATION == 3
    assert exit_for_category(ErrorCategory.AUTHENTICATION) == EXIT_AUTH == 4
    assert exit_for_category(ErrorCategory.STORAGE) == EXIT_STORAGE == 5
    assert exit_for_category(ErrorCategory.AUTOMATION) == EXIT_AUTOMATION == 6
    assert exit_for_category(ErrorCategory.NETWORK) == 1
    assert exit_for_category(None) == 1


def test_errors_and_codes_map_by_category_never_by_message() -> None:
    assert exit_for_error(AuthenticationError("https://x/y", 403)) == 4
    assert exit_for_error(InsufficientStorageError(10, 1, location="/x")) == 5
    assert exit_for_error(VerificationError("bad")) == 3
    assert exit_for_error(HTTPError("https://x/y", 404)) == 1
    assert exit_for_error(ValueError("whatever")) == 1
    assert exit_for_code("VERIFICATION_FAILED") == 3
    assert exit_for_code("STORAGE_LOW") == 5
    assert exit_for_code("AUTH_403") == 4
    assert exit_for_code("HTTP_503") == 1
    assert exit_for_code(None) == 1


def test_a_batch_has_one_code() -> None:
    assert exit_for_batch([], 3) == 0
    assert exit_for_batch([1], 2) == EXIT_PARTIAL == 7
    assert exit_for_batch([4, 4], 0) == 4
    assert exit_for_batch([4, 1], 0) == 1


def test_legacy_mode_makes_every_failure_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAYOHX_EXIT_CODES", "legacy")
    assert exit_for_category(ErrorCategory.AUTHENTICATION) == 1
    assert exit_for_code("STORAGE_LOW") == 1
    assert exit_for_batch([1], 2) == 1


def failing(error: Exception) -> Any:
    def broken(self: InstantDownloader) -> DownloadResult:
        self.exception = error
        return DownloadResult(
            download_id=self.download_id,
            url=self.url,
            state=DownloadState.FAILED,
            elapsed_seconds=0,
            progress=DownloadProgress(state=DownloadState.FAILED),
            error=str(error),
        )

    return broken


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (AuthenticationError("https://m.test/a", 403), 4),
        (InsufficientStorageError(10, 1, location="/x"), 5),
        (VerificationError("bad"), 3),
        (HTTPError("https://m.test/a", 404), 1),
    ],
)
def test_queue_run_exits_with_the_failed_jobs_code(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, error: Exception, code: int
) -> None:
    monkeypatch.setattr(InstantDownloader, "run", failing(error))
    runner.invoke(app, ["queue", "add", "https://media.example.com/a.m3u8", "--max-attempts", "1"])
    assert runner.invoke(app, ["queue", "run", "--until-empty"]).exit_code == code


def test_non_interactive_refuses_to_ask(runner: CliRunner) -> None:
    runner.invoke(app, ["profile", "create", "Mine"])
    result = runner.invoke(app, ["--non-interactive", "profile", "delete", "mine"])
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert (
        runner.invoke(app, ["--non-interactive", "profile", "delete", "mine", "--yes"]).exit_code
        == 0
    )


def test_the_environment_turns_non_interactive_on(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(app, ["profile", "create", "Mine"])
    monkeypatch.setenv("RAYOHX_NON_INTERACTIVE", "1")
    assert runner.invoke(app, ["profile", "delete", "mine"]).exit_code == 2


def test_clean_can_print_json(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["clean", str(tmp_path), "--json", "--yes"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"removed": [], "bytes": 0}
