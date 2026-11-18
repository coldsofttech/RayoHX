"""The queue: storing, ordering, controlling and running jobs (with a scripted downloader)."""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from rayohx.config import DownloadConfig, NetworkConfig, OutputConfig
from rayohx.errors import (
    AuthenticationError,
    ConfigurationError,
    HTTPError,
    NetworkConnectionError,
)
from rayohx.platform import Rayo
from rayohx.platform.errors import QueueError, RunnerLockedError
from rayohx.platform.events import Severity
from rayohx.platform.jobs import JobState, QueuePriority, RetryPolicy
from rayohx.platform.secrets import MemorySecretStore
from tests.unit.platform import fakes
from tests.unit.platform.conftest import state_of, wait_for, wait_state

URL = "https://media.test/{}/master.m3u8"
FAST = RetryPolicy(max_attempts=3, initial_delay=0.05, factor=1, max_delay=0.05)


def u(name: str) -> str:
    return URL.format(name)


def order(rayo: Rayo) -> list[str]:
    return [j.url.split("/")[3] for j in rayo.queue.list()]


# --- adding and listing ------------------------------------------------------------------


def test_a_job_is_stored_queued_with_a_safe_address(rayo: Rayo) -> None:
    job = rayo.queue.add("https://media.test/a.m3u8?token=SECRET&x=1")
    assert job.state is JobState.QUEUED
    assert job.priority is QueuePriority.NORMAL
    assert "SECRET" not in job.url
    assert "SECRET" not in str(job.to_dict())
    assert job.spec.url.endswith("token=SECRET&x=1")  # the real address is kept to run the job
    assert rayo.queue.get(job.id) == job
    assert rayo.queue.get("nope") is None


def test_invalid_input_is_refused_at_enqueue(rayo: Rayo) -> None:
    with pytest.raises(ConfigurationError):
        rayo.queue.add("ftp://nope")
    with pytest.raises(ConfigurationError):
        rayo.queue.add(u("a"), output_name="../evil.mp4")
    with pytest.raises(ConfigurationError):
        rayo.queue.add(u("a"), options={"concurrency": 0})
    with pytest.raises(ConfigurationError, match="not both"):
        rayo.queue.add(u("a"), config=DownloadConfig(), options={})
    with pytest.raises(ConfigurationError):
        rayo.queue.add_many([u("a"), "not a url"])
    assert rayo.queue.list() == []


def test_add_many_queues_each_address(rayo: Rayo) -> None:
    jobs = rayo.queue.add_many([u("a"), u("b"), u("c")], priority="high")
    assert len(jobs) == 3
    assert {j.priority for j in jobs} == {QueuePriority.HIGH}
    assert order(rayo) == ["a", "b", "c"]


def test_priority_decides_the_order_then_arrival(rayo: Rayo) -> None:
    rayo.queue.add(u("n1"))
    rayo.queue.add(u("low"), priority="low")
    rayo.queue.add(u("high"), priority="HIGH")
    rayo.queue.add(u("n2"), priority=QueuePriority.NORMAL)
    assert order(rayo) == ["high", "n1", "n2", "low"]
    with pytest.raises(ValueError, match="unknown priority"):
        rayo.queue.add(u("x"), priority="urgent")


def test_priority_can_change_later(rayo: Rayo) -> None:
    a, b = rayo.queue.add(u("a")), rayo.queue.add(u("b"))
    assert rayo.queue.set_priority(b.id, "high").ok
    assert order(rayo) == ["b", "a"]
    rayo.queue.cancel(a.id)
    assert not rayo.queue.set_priority(a.id, "high").ok  # finished jobs keep their priority


def test_move_to_top_bottom_and_before(rayo: Rayo) -> None:
    ids = {n: rayo.queue.add(u(n)).id for n in "abcde"}
    rayo.queue.move_to_top([ids["d"], ids["e"]])
    assert order(rayo) == ["d", "e", "a", "b", "c"]
    rayo.queue.move_to_bottom(ids["d"])
    assert order(rayo) == ["e", "a", "b", "c", "d"]
    rayo.queue.move_before(ids["c"], ids["a"])
    assert order(rayo) == ["e", "c", "a", "b", "d"]
    rayo.queue.move_before(ids["b"], ids["e"])
    assert order(rayo) == ["b", "e", "c", "a", "d"]
    with pytest.raises(QueueError):
        rayo.queue.move_before(ids["a"], "nope")


def test_moving_before_a_job_adopts_its_priority(rayo: Rayo) -> None:
    low = rayo.queue.add(u("low"), priority="low")
    high = rayo.queue.add(u("high"), priority="high")
    moved = rayo.queue.move_before(low.id, high.id)
    assert moved.priority is QueuePriority.HIGH
    assert order(rayo) == ["low", "high"]


def test_repeated_moves_never_run_out_of_room(rayo: Rayo) -> None:
    a, b = rayo.queue.add(u("a")), rayo.queue.add(u("b"))
    for _ in range(60):  # ranks would collapse after ~50 halvings without renumbering
        rayo.queue.move_before(b.id, a.id)
        rayo.queue.move_before(a.id, b.id)
    assert order(rayo) == ["a", "b"]


def test_listing_filters_and_stats(rayo: Rayo) -> None:
    a, b = rayo.queue.add(u("a")), rayo.queue.add(u("b"))
    rayo.queue.pause(b.id)
    assert [j.id for j in rayo.queue.list(states=["paused"])] == [b.id]
    assert [j.id for j in rayo.queue.list(states=[JobState.QUEUED])] == [a.id]
    assert [j.id for j in rayo.queue.list(newest_first=True)] == [b.id, a.id]
    assert len(rayo.queue.list(limit=1)) == 1
    stats = rayo.queue.stats()
    assert stats["counts"]["queued"] == 1
    assert stats["counts"]["paused"] == 1
    assert stats["total"] == 2
    assert stats["runner"] == "none"


# --- controlling waiting jobs ------------------------------------------------------------


def test_pause_resume_cancel_retry_remove_on_waiting_jobs(rayo: Rayo) -> None:
    q = rayo.queue
    job = q.add(u("a"))
    assert q.pause(job.id).ok
    assert state_of(rayo, job.id) is JobState.PAUSED
    assert q.pause(job.id).ok  # pausing twice is fine
    assert q.resume(job.id).ok
    assert state_of(rayo, job.id) is JobState.QUEUED
    assert q.resume(job.id).ok  # resuming a queued job is fine
    assert q.cancel(job.id).ok
    assert state_of(rayo, job.id) is JobState.CANCELLED
    assert "already cancelled" in q.cancel(job.id).failed[job.id]
    assert "already cancelled" in q.pause(job.id).failed[job.id]
    assert "cancelled" in q.resume(job.id).failed[job.id]
    assert q.retry(job.id).ok
    assert state_of(rayo, job.id) is JobState.QUEUED
    assert "Only a failed or cancelled" in q.retry(job.id).failed[job.id]
    assert q.remove(job.id).ok
    assert q.get(job.id) is None
    assert q.remove(job.id).failed[job.id] == "No such job."


def test_bulk_actions_report_each_job(rayo: Rayo) -> None:
    a, b = rayo.queue.add(u("a")), rayo.queue.add(u("b"))
    rayo.queue.cancel(b.id)
    result = rayo.queue.pause([a.id, b.id, "ghost", a.id])
    assert result.done == [a.id]
    assert set(result.failed) == {b.id, "ghost"}
    assert not result.ok
    assert result.to_dict()["done"] == [a.id]


def test_export_and_import_keep_the_settings_but_not_the_secrets(rayo: Rayo) -> None:
    config = DownloadConfig(
        network=NetworkConfig(headers={"Authorization": "Bearer S", "Accept": "x"}),
        output=OutputConfig(directory=rayo.download_dir / "shows"),
    )
    rayo.queue.add(u("a"), config=config, priority="high", output_name="a.ts")
    rayo.queue.add(u("b"), priority="low")
    exported = rayo.queue.export()
    assert "Bearer S" not in str(exported)
    assert [e["priority"] for e in exported] == ["high", "low"]
    other = rayo.queue.import_jobs(exported)
    assert [j.priority.name for j in other] == ["HIGH", "LOW"]
    assert other[0].spec.output_name == "a.ts"
    assert len(rayo.queue.export([other[0].id])) == 1
    with pytest.raises(ConfigurationError):
        rayo.queue.import_jobs([{"url": u("c"), "options": {"concurrency": 0}}])
    assert len(rayo.queue.list()) == 4  # nothing was added by the failed import


def test_output_path_in_a_config_becomes_a_name_and_folder(rayo: Rayo, tmp_path: Path) -> None:
    config = DownloadConfig(output=OutputConfig(path=tmp_path / "films" / "x.mp4"))
    job = rayo.queue.add(u("a"), config=config)
    assert job.spec.output_name == "x.mp4"
    assert job.spec.options["output"]["directory"] == str(tmp_path / "films")


def test_the_limit_on_active_jobs_is_remembered(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    assert rayo.queue.max_active == 2
    rayo.queue.max_active = 5
    with pytest.raises(ConfigurationError):
        rayo.queue.max_active = 0
    rayo.close()
    assert make_rayo().queue.max_active == 5


# --- running -----------------------------------------------------------------------------


def test_jobs_run_and_complete_in_priority_order(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo(max_active=1)
    rayo.queue.add(u("n"))
    rayo.queue.add(u("low"), priority="low")
    rayo.queue.add(u("high"), priority="high")
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    assert [x.split("/")[3] for x in fakes.FakeDownloader.started] == ["high", "n", "low"]
    jobs = rayo.queue.list()
    assert {j.state for j in jobs} == {JobState.COMPLETED}
    done = jobs[0]
    assert done.output_path is not None
    assert done.output_size == 4
    assert done.attempts == 1
    assert done.started_at is not None
    assert done.finished_at is not None
    types = [e.type for e in rayo.event_store.query(job_id=done.id)]
    assert "queue.job_added" in types
    assert "queue.job_completed" in types
    assert "download.started" in types


def test_only_max_active_jobs_run_at_once(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo(max_active=2)
    gate = threading.Event()
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped(gate)
    ids = [rayo.queue.add(u(f"j{i}")).id for i in range(5)]
    rayo.queue.start()
    wait_for(lambda: rayo.queue.stats()["active"] == 2)
    assert len(fakes.FakeDownloader.started) == 2
    assert [state_of(rayo, i) for i in ids].count(JobState.QUEUED) == 3
    rayo.queue.max_active = 3  # raised while running
    wait_for(lambda: rayo.queue.stats()["active"] == 3)
    gate.set()
    assert rayo.queue.wait_idle(5)
    assert {state_of(rayo, i) for i in ids} == {JobState.COMPLETED}


def test_one_failure_does_not_touch_the_others(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo(max_active=2)
    fakes.FakeDownloader.scripts[u("bad")] = fakes.fail_with(
        AuthenticationError("https://media.test/x", 403)
    )
    bad = rayo.queue.add(u("bad"))
    good = [rayo.queue.add(u(n)).id for n in ("ok1", "ok2")]
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    failed = rayo.queue.get(bad.id)
    assert failed is not None
    assert failed.state is JobState.FAILED
    assert failed.error_code == "AUTH_403"
    assert failed.attempts == 1  # authentication problems are not retried
    assert {state_of(rayo, i) for i in good} == {JobState.COMPLETED}
    events = [e for e in rayo.event_store.query(job_id=bad.id) if e.type == "queue.job_failed"]
    assert events[0].severity is Severity.ERROR
    assert events[0].payload["code"] == "AUTH_403"


def test_transient_failures_are_retried_with_a_delay(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts[u("flaky")] = fakes.flaky(2)
    job = rayo.queue.add(u("flaky"), retry=FAST)
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    done = rayo.queue.get(job.id)
    assert done is not None
    assert done.state is JobState.COMPLETED
    assert done.attempts == 3
    history = rayo.queue.attempts(job.id)
    assert [a["outcome"] for a in history] == ["failed", "failed", "completed"]
    assert history[0]["error_code"] == "NETWORK_CONNECTION"
    scheduled = [
        e for e in rayo.event_store.query(job_id=job.id) if e.type == "queue.job_retry_scheduled"
    ]
    assert len(scheduled) == 2
    assert scheduled[0].payload["attempt"] == 1


def test_retries_stop_at_the_limit(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts["*"] = fakes.fail_with(HTTPError("https://media.test/s", 503))
    job = rayo.queue.add(u("a"), retry=FAST)
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    failed = rayo.queue.get(job.id)
    assert failed is not None
    assert (failed.state, failed.attempts, failed.error_code) == (JobState.FAILED, 3, "HTTP_503")
    assert rayo.queue.retry(job.id).ok  # a manual retry starts again from zero
    again = rayo.queue.get(job.id)
    assert again is not None
    assert (again.state, again.attempts, again.error_code) == (JobState.QUEUED, 0, None)


def test_a_delayed_retry_does_not_block_other_jobs(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo(max_active=1)
    fakes.FakeDownloader.scripts[u("flaky")] = fakes.flaky(1)
    slow = RetryPolicy(max_attempts=2, initial_delay=0.3, factor=1)
    flaky = rayo.queue.add(u("flaky"), retry=slow)
    other = rayo.queue.add(u("other"), priority="low")
    rayo.queue.start()
    wait_state(rayo, other.id, JobState.COMPLETED)
    assert state_of(rayo, flaky.id) in {JobState.QUEUED, JobState.PREPARING, JobState.COMPLETED}
    assert rayo.queue.wait_idle(5)
    assert state_of(rayo, flaky.id) is JobState.COMPLETED


def test_unexpected_errors_fail_the_job_not_the_runner(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()

    def explode(_d: fakes.FakeDownloader) -> object:
        raise RuntimeError("boom with token=abc123")

    fakes.FakeDownloader.scripts[u("bug")] = explode  # type: ignore[assignment]
    bug = rayo.queue.add(u("bug"))
    fine = rayo.queue.add(u("fine"))
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    failed = rayo.queue.get(bug.id)
    assert failed is not None
    assert failed.state is JobState.FAILED
    assert failed.error_code == "INTERNAL"
    assert state_of(rayo, fine.id) is JobState.COMPLETED


def test_a_bad_saved_config_fails_without_retrying(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    job = rayo.queue.add(u("a"), retry=FAST)
    # Corrupt the saved options directly, as a hand-edited database could.
    import json

    spec = json.loads(job.spec.to_json())
    spec["options"] = {"concurrency": 0}
    rayo.database.execute("UPDATE jobs SET spec_json = ?", (json.dumps(spec),))
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    failed = rayo.queue.get(job.id)
    assert failed is not None
    assert (failed.state, failed.attempts) == (JobState.FAILED, 1)
    assert failed.error_code == "CONFIGURATION_INVALID"


def test_queue_completed_is_announced_once_per_burst(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    rayo.queue.add_many([u("a"), u("b")])
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    wait_for(lambda: any(e.type == "queue.completed" for e in rayo.event_store.query()))
    rayo.queue.add(u("c"))
    wait_for(lambda: sum(e.type == "queue.completed" for e in rayo.event_store.query()) == 2)


# --- pause, resume, cancel of running jobs -----------------------------------------------


def test_pausing_a_running_job_frees_its_slot(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo(max_active=1)
    fakes.FakeDownloader.scripts[u("long")] = fakes.block_until_stopped()
    long = rayo.queue.add(u("long"))
    short = rayo.queue.add(u("short"))
    rayo.queue.start()
    wait_state(rayo, long.id, JobState.DOWNLOADING)
    assert rayo.queue.pause(long.id).ok
    wait_state(rayo, long.id, JobState.PAUSED)
    wait_state(rayo, short.id, JobState.COMPLETED)  # the slot went to the next job
    assert rayo.queue.stats()["active"] == 0
    fakes.FakeDownloader.scripts[u("long")] = fakes.ok
    assert rayo.queue.resume(long.id).ok
    wait_state(rayo, long.id, JobState.COMPLETED)
    got = rayo.queue.get(long.id)
    assert got is not None
    assert got.attempts == 2
    assert [a["outcome"] for a in rayo.queue.attempts(long.id)] == ["pause", "completed"]


def test_cancelling_a_running_job(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(u("a"))
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.DOWNLOADING)
    assert rayo.queue.remove(job.id).failed[job.id] == "Cancel the job before removing it."
    assert rayo.queue.cancel(job.id).ok
    wait_state(rayo, job.id, JobState.CANCELLED)
    assert rayo.queue.remove(job.id).ok


def test_pause_then_cancel_wins(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(u("a"))
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.DOWNLOADING)
    rayo.queue.cancel(job.id)
    rayo.queue.pause(job.id)
    wait_state(rayo, job.id, JobState.CANCELLED)


def test_live_progress_is_shown_while_running(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(u("a"))
    rayo.queue.start()
    wait_for(lambda: (rayo.queue.get(job.id) or job).progress is not None)
    live = rayo.queue.get(job.id)
    assert live is not None
    assert live.progress is not None
    assert live.progress["state"] == "downloading"


# --- stopping, crashing and recovering ---------------------------------------------------


def test_stopping_the_runner_puts_running_jobs_back(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(u("a"))
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.DOWNLOADING)
    rayo.queue.stop()
    got = rayo.queue.get(job.id)
    assert got is not None
    assert got.state is JobState.QUEUED
    assert got.attempts == 0  # an interrupted run does not count
    assert not got.recovered
    assert not rayo.queue.running


def test_a_crashed_runner_is_recovered_at_the_next_start(
    make_rayo: Callable[..., Rayo], tmp_path: Path
) -> None:
    first = make_rayo()
    jobs = [first.queue.add(u(n)) for n in "abcd"]
    # Leave jobs in every active state, as a killed process would.
    for job, state in zip(
        jobs, ["preparing", "downloading", "finalizing", "verifying"], strict=True
    ):
        first.jobs.update(job.id, state=state)
    first.close()

    second = make_rayo()
    recovered = second.queue.start()
    assert sorted(recovered) == sorted(j.id for j in jobs)
    assert second.queue.wait_idle(5)
    for job in jobs:
        got = second.queue.get(job.id)
        assert got is not None
        assert got.state is JobState.COMPLETED
        assert got.recovered
    assert {e.type for e in second.event_store.query()} >= {"queue.job_recovered"}


def test_paused_and_waiting_jobs_survive_a_restart_untouched(
    make_rayo: Callable[..., Rayo],
) -> None:
    first = make_rayo()
    paused, waiting = first.queue.add(u("p")), first.queue.add(u("w"), priority="high")
    first.queue.pause(paused.id)
    first.close()
    second = make_rayo()
    assert second.queue.start() == []
    wait_state(second, waiting.id, JobState.COMPLETED)
    assert state_of(second, paused.id) is JobState.PAUSED
    assert fakes.FakeDownloader.started == [waiting.spec.url]


def test_only_one_runner_per_folder(make_rayo: Callable[..., Rayo]) -> None:
    first = make_rayo()
    first.queue.start()
    second = make_rayo()
    with pytest.raises(RunnerLockedError):
        second.queue.start()
    first.queue.stop()
    second.queue.start()  # the lock is free again


def test_another_process_controls_jobs_through_the_database(
    make_rayo: Callable[..., Rayo],
) -> None:
    runner = make_rayo(max_active=1)
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = runner.queue.add(u("a"))
    waiting = runner.queue.add(u("b"))
    runner.queue.start()
    wait_state(runner, job.id, JobState.DOWNLOADING)

    cli = make_rayo()  # a second platform on the same data, like the command line
    assert cli.queue.stats()["runner"] == "another process"
    assert cli.queue.cancel(waiting.id).ok  # still waiting: changed directly
    assert state_of(cli, waiting.id) is JobState.CANCELLED
    assert cli.queue.pause(job.id).ok  # running: handed to the runner through the database
    wait_state(cli, job.id, JobState.PAUSED)


def test_control_of_an_orphaned_active_job_is_applied_directly(
    make_rayo: Callable[..., Rayo],
) -> None:
    rayo = make_rayo()
    job = rayo.queue.add(u("a"))
    rayo.jobs.update(job.id, state="downloading")  # left by a crash; no runner anywhere
    assert rayo.queue.pause(job.id).ok
    assert state_of(rayo, job.id) is JobState.PAUSED
    rayo.jobs.update(job.id, state="downloading")
    assert rayo.queue.cancel(job.id).ok
    assert state_of(rayo, job.id) is JobState.CANCELLED


# --- secrets -----------------------------------------------------------------------------


def secret_config() -> DownloadConfig:
    return DownloadConfig(network=NetworkConfig(headers={"Authorization": "Bearer S3CRET"}))


def test_secrets_never_reach_the_database(make_rayo: Callable[..., Rayo], tmp_path: Path) -> None:
    rayo = make_rayo()
    job = rayo.queue.add(u("a"), config=secret_config())
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    rayo.close()
    raw = b"".join(p.read_bytes() for p in (tmp_path / "home" / "data").glob("rayohx.db*"))
    assert b"S3CRET" not in raw
    assert job.spec.options["network"]["headers"] == {}


def test_the_job_gets_its_secrets_when_it_runs(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    seen: list[object] = []

    def capture(d: fakes.FakeDownloader) -> object:
        seen.append(dict(d.config.network.headers))
        return fakes.ok(d)

    fakes.FakeDownloader.scripts["*"] = capture  # type: ignore[assignment]
    rayo.queue.add(u("a"), config=secret_config())
    rayo.queue.start()
    assert rayo.queue.wait_idle(5)
    assert seen == [{"Authorization": "Bearer S3CRET"}]


def test_lost_secrets_park_the_job_until_they_are_supplied(
    make_rayo: Callable[..., Rayo],
) -> None:
    first = make_rayo(secrets=MemorySecretStore())
    job = first.queue.add(u("a"), config=secret_config())
    first.close()

    second = make_rayo(secrets=MemorySecretStore())  # a restart without a keyring
    second.queue.start()
    wait_for(lambda: (second.queue.get(job.id) or job).needs_credentials)
    parked = second.queue.get(job.id)
    assert parked is not None
    assert (parked.state, parked.attempts) == (JobState.QUEUED, 0)
    assert second.queue.wait_idle(0.3)  # parked jobs do not keep the queue busy
    assert fakes.FakeDownloader.started == []

    second.queue.provide_credentials(job.id, {"headers": {"Authorization": "Bearer NEW"}})
    wait_state(second, job.id, JobState.COMPLETED)
    with pytest.raises(QueueError):
        second.queue.provide_credentials("ghost", {})


def test_removing_a_job_forgets_its_secrets(make_rayo: Callable[..., Rayo]) -> None:
    store = MemorySecretStore()
    rayo = make_rayo(secrets=store)
    job = rayo.queue.add(u("a"), config=secret_config())
    ref = rayo.jobs.secret_ref(job.id)
    assert ref is not None
    assert store.get(ref) is not None
    rayo.queue.remove(job.id)
    assert store.get(ref) is None


def test_a_failed_insert_does_not_leave_secrets_behind(
    make_rayo: Callable[..., Rayo], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemorySecretStore()
    rayo = make_rayo(secrets=store)

    def broken(**_: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(rayo.jobs, "insert", broken)
    with pytest.raises(RuntimeError):
        rayo.queue.add(u("a"), config=secret_config())
    assert store._data == {}


def test_a_network_error_class_is_used_for_retry_tests() -> None:
    assert NetworkConnectionError("x").retryable


def test_hundreds_of_jobs_are_cheap_to_queue_list_and_run(make_rayo: Callable[..., Rayo]) -> None:
    import time

    rayo = make_rayo(max_active=8)
    started = time.monotonic()
    jobs = [
        rayo.queue.add(u(f"j{i}"), priority=["low", "normal", "high"][i % 3]) for i in range(300)
    ]
    added = time.monotonic() - started
    started = time.monotonic()
    listed = rayo.queue.list()
    listing = time.monotonic() - started
    assert len(listed) == 300
    assert [j.priority.name for j in listed[:100]] == ["HIGH"] * 100  # priority first
    assert added < 15
    assert listing < 1.0
    rayo.queue.start()
    assert rayo.queue.wait_idle(60)
    assert {j.state for j in rayo.queue.list()} == {JobState.COMPLETED}
    assert len({j.id for j in jobs}) == 300
