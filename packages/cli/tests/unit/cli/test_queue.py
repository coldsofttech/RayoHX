"""The ``queue`` commands."""

import json
from pathlib import Path
from typing import Any

import pytest
from rayohx import Rayo
from rayohx.enums import ContainerFormat, DownloadState, EventType
from rayohx.events import DownloadEvent, EventBus
from rayohx.models import DownloadProgress, DownloadResult, OutputInfo
from rayohx.platform.secrets import MemorySecretStore
from typer.testing import CliRunner

from rayohx_cli.cli import app

URL = "https://media.example.com/{}.m3u8"


class InstantDownloader:
    """Finishes at once, writing a small file."""

    def __init__(self, url: str, *, config: Any, download_id: str, **_: Any) -> None:
        self.url, self.config, self.download_id = url, config, download_id
        self.events = EventBus()
        self.exception = None

    def run(self) -> DownloadResult:
        self.events.emit(
            DownloadEvent(
                type=EventType.DOWNLOAD_STARTED,
                download_id=self.download_id,
                state=DownloadState.DOWNLOADING,
                progress=DownloadProgress(state=DownloadState.DOWNLOADING),
            )
        )
        path = Path(self.config.output.directory) / "out.ts"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"1234")
        return DownloadResult(
            download_id=self.download_id,
            url=self.url,
            state=DownloadState.COMPLETED,
            elapsed_seconds=0,
            progress=DownloadProgress(state=DownloadState.COMPLETED),
            output=OutputInfo(path=path, container=ContainerFormat.MPEG_TS, size_bytes=4),
        )


@pytest.fixture(autouse=True)
def platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Every command works on a private platform folder and downloads instantly."""
    home = tmp_path / "platform"
    monkeypatch.setenv("RAYOHX_HOME", str(home))

    real = Rayo

    def make(home: Path | None = None, **kwargs: Any) -> Rayo:
        return real(
            home=home,
            download_dir=tmp_path / "dl",
            secrets=MemorySecretStore(),
            downloader_factory=InstantDownloader,
            **kwargs,
        )

    monkeypatch.setattr("rayohx_cli.cli.queue.Rayo", make)
    return home


def invoke(runner: CliRunner, *args: str) -> Any:
    return runner.invoke(app, ["queue", *args], catch_exceptions=False)


def add(runner: CliRunner, name: str, *extra: str) -> str:
    result = invoke(runner, "add", URL.format(name), *extra)
    assert result.exit_code == 0, result.stderr
    return str(result.stdout.strip())


def listing(runner: CliRunner, *extra: str) -> list[dict[str, Any]]:
    result = invoke(runner, "list", "--json", *extra)
    assert result.exit_code == 0, result.stderr
    return list(json.loads(result.stdout)["items"])


def test_add_prints_the_job_id_and_list_shows_it(runner: CliRunner) -> None:
    job = add(runner, "a", "--priority", "high")
    (item,) = listing(runner)
    assert item["id"] == job
    assert item["state"] == "queued"
    assert item["priority"] == "high"
    assert item["max_attempts"] == 3
    table = invoke(runner, "list")
    assert job in table.stdout
    assert "queued" in table.stdout


def test_the_empty_queue_says_so(runner: CliRunner) -> None:
    assert "empty" in invoke(runner, "list").stderr


def test_add_refuses_bad_input_and_adds_nothing(runner: CliRunner) -> None:
    result = invoke(runner, "add", URL.format("ok"), "ftp://nope")
    assert result.exit_code == 2
    assert listing(runner) == []
    assert invoke(runner, "add", URL.format("a"), URL.format("b"), "--name", "x.ts").exit_code == 2
    assert invoke(runner, "add", URL.format("a"), "--priority", "urgent").exit_code == 2
    assert invoke(runner, "add").exit_code == 2


def test_add_reads_an_input_file_and_keeps_secrets_out_of_output(
    runner: CliRunner, tmp_path: Path
) -> None:
    listfile = tmp_path / "urls.txt"
    listfile.write_text(f"# comment\n{URL.format('a')}\n{URL.format('b')}\n", encoding="utf-8")
    result = invoke(
        runner,
        "add",
        "--input-file",
        str(listfile),
        "--header",
        "Authorization: Bearer HUSH",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    assert len(json.loads(result.stdout)) == 2
    assert "HUSH" not in result.output
    assert "HUSH" not in invoke(runner, "list", "--json").stdout
    assert "HUSH" not in invoke(runner, "export").stdout


def test_pause_resume_cancel_retry_remove(runner: CliRunner) -> None:
    job = add(runner, "a")
    assert invoke(runner, "pause", job).exit_code == 0
    assert listing(runner)[0]["state"] == "paused"
    assert invoke(runner, "resume", job).exit_code == 0
    assert invoke(runner, "cancel", job).exit_code == 0
    assert listing(runner)[0]["state"] == "cancelled"
    assert invoke(runner, "retry", job).exit_code == 0
    assert listing(runner)[0]["state"] == "queued"
    assert invoke(runner, "remove", job).exit_code == 0
    assert listing(runner) == []


def test_actions_on_missing_jobs_fail_with_a_message(runner: CliRunner) -> None:
    result = invoke(runner, "pause", "ghost")
    assert result.exit_code == 1
    assert "No such job" in result.stderr
    assert invoke(runner, "show", "ghost").exit_code == 1


def test_priority_and_move(runner: CliRunner) -> None:
    a, b, c = (add(runner, n) for n in "abc")
    assert invoke(runner, "priority", "high", c).exit_code == 0
    assert [j["id"] for j in listing(runner)] == [c, a, b]
    assert invoke(runner, "move", b, "--top").exit_code == 0
    assert invoke(runner, "move", a, "--bottom").exit_code == 0
    assert invoke(runner, "move", a, "--before", b).exit_code == 0
    assert [j["id"] for j in listing(runner)] == [c, a, b]
    assert invoke(runner, "move", a).exit_code == 2
    assert invoke(runner, "move", a, "--top", "--bottom").exit_code == 2
    assert invoke(runner, "move", a, "--before", "ghost").exit_code == 1


def test_show_and_stats(runner: CliRunner) -> None:
    job = add(runner, "a")
    shown = invoke(runner, "show", job, "--json")
    assert json.loads(shown.stdout)["id"] == job
    assert json.loads(shown.stdout)["attempt_history"] == []
    assert job in invoke(runner, "show", job).stdout
    stats = json.loads(invoke(runner, "stats", "--json").stdout)
    assert stats["counts"]["queued"] == 1
    assert "queued" in invoke(runner, "stats").stdout


def test_export_then_import_moves_jobs(runner: CliRunner, tmp_path: Path) -> None:
    add(runner, "a", "--priority", "low")
    exported = invoke(runner, "export").stdout
    file = tmp_path / "queue.json"
    file.write_text(exported, encoding="utf-8")
    assert invoke(runner, "import", str(file)).exit_code == 0
    assert [j["priority"] for j in listing(runner)] == ["low", "low"]
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    assert invoke(runner, "import", str(bad)).exit_code == 2
    bad.write_text('[{"nourl": 1}]', encoding="utf-8")
    assert invoke(runner, "import", str(bad)).exit_code == 2


def test_clear_removes_finished_jobs_only(runner: CliRunner) -> None:
    done, waiting = add(runner, "a"), add(runner, "b")
    invoke(runner, "cancel", done)
    assert invoke(runner, "clear", "--state", "cancelled").exit_code == 0
    assert [j["id"] for j in listing(runner)] == [waiting]
    assert invoke(runner, "clear", "--state", "queued").exit_code == 2
    assert "Nothing to clear" in invoke(runner, "clear").stderr


def test_run_until_empty_downloads_everything(runner: CliRunner) -> None:
    add(runner, "a")
    add(runner, "b", "--priority", "high")
    result = invoke(runner, "run", "--until-empty", "--events")
    assert result.exit_code == 0, result.stderr
    states = {j["state"] for j in listing(runner)}
    assert states == {"completed"}
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert "queue.completed" in {line["type"] for line in lines}
    assert "The queue is empty" in result.stderr


def test_run_on_an_empty_queue_returns_at_once(runner: CliRunner) -> None:
    assert invoke(runner, "run", "--until-empty").exit_code == 0


def test_run_exits_1_when_a_job_failed(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(self: InstantDownloader) -> DownloadResult:
        return DownloadResult(
            download_id=self.download_id,
            url=self.url,
            state=DownloadState.FAILED,
            elapsed_seconds=0,
            progress=DownloadProgress(state=DownloadState.FAILED),
            error="nope",
        )

    monkeypatch.setattr(InstantDownloader, "run", broken)
    add(runner, "a", "--max-attempts", "1")
    result = invoke(runner, "run", "--until-empty")
    assert result.exit_code == 1
    assert listing(runner)[0]["state"] == "failed"
    assert listing(runner)[0]["error"] == "nope"


def test_only_one_run_at_a_time(runner: CliRunner, platform: Path) -> None:
    from rayohx.storage import FileLock

    add(runner, "a")
    lock = FileLock(platform / "data" / "runner.lock")
    assert lock.acquire()
    try:
        result = invoke(runner, "run", "--until-empty")
        assert result.exit_code == 1
        assert "already running the queue" in result.stderr
    finally:
        lock.release()
