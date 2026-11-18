import random

import pytest

from rayohx.enums import ErrorCategory
from rayohx.errors import (
    AuthenticationError,
    ConfigurationError,
    HTTPError,
    InsufficientStorageError,
    NetworkConnectionError,
    SegmentDownloadError,
    TLSError,
)
from rayohx.platform.jobs import RetryPolicy
from rayohx.platform.queue import Candidate, pick_next

HIGH, NORMAL, LOW = 2, 1, 0


def c(id_: str, priority: int = NORMAL, rank: float = 0, created: float = 0, nb=None) -> Candidate:
    return Candidate(id_, priority, rank, created, nb)


def test_priority_beats_rank_and_age() -> None:
    jobs = [c("low", LOW, rank=1), c("normal", NORMAL, rank=2), c("high", HIGH, rank=3)]
    assert pick_next(jobs, free_slots=3, now=0) == ["high", "normal", "low"]


def test_rank_orders_within_a_priority_then_age_then_id() -> None:
    jobs = [
        c("d", rank=2, created=1),
        c("c", rank=1, created=5),
        c("b", rank=1, created=5),
        c("a", rank=1, created=9),
    ]
    assert pick_next(jobs, free_slots=4, now=0) == ["b", "c", "a", "d"]


def test_only_the_free_slots_start() -> None:
    jobs = [c(str(i), rank=i) for i in range(5)]
    assert pick_next(jobs, free_slots=2, now=0) == ["0", "1"]
    assert pick_next(jobs, free_slots=0, now=0) == []
    assert pick_next(jobs, free_slots=-3, now=0) == []
    assert pick_next([], free_slots=2, now=0) == []


def test_delayed_jobs_wait_for_their_time() -> None:
    jobs = [c("later", HIGH, nb=100.0), c("now", LOW), c("due", NORMAL, nb=50.0)]
    assert pick_next(jobs, free_slots=3, now=60.0) == ["due", "now"]
    assert pick_next(jobs, free_slots=3, now=100.0) == ["later", "due", "now"]


def test_a_refused_job_does_not_use_a_slot_or_reorder_the_rest() -> None:
    jobs = [c("big", HIGH), c("a", NORMAL, rank=1), c("b", NORMAL, rank=2)]
    chosen = pick_next(jobs, free_slots=2, now=0, admit=lambda cand: cand.id != "big")
    assert chosen == ["a", "b"]


def test_the_answer_does_not_depend_on_input_order() -> None:
    rng = random.Random(7)  # noqa: S311
    jobs = [
        c(f"j{i}", rng.choice([LOW, NORMAL, HIGH]), rng.randint(0, 5), float(rng.randint(0, 5)))
        for i in range(60)
    ]
    expected = pick_next(jobs, free_slots=60, now=0)
    for _ in range(20):
        rng.shuffle(jobs)
        assert pick_next(jobs, free_slots=60, now=0) == expected
    assert len(set(expected)) == 60
    priorities = {j.id: j.priority for j in jobs}
    seen = [priorities[i] for i in expected]
    assert seen == sorted(seen, reverse=True)


# --- retry policy -------------------------------------------------------------------------


def test_delays_grow_and_are_capped() -> None:
    policy = RetryPolicy(max_attempts=9, initial_delay=10, factor=2, max_delay=50)
    assert [policy.delay_for(n) for n in (1, 2, 3, 4, 5)] == [10, 20, 40, 50, 50]


@pytest.mark.parametrize(
    ("error", "retry"),
    [
        (NetworkConnectionError("reset"), True),
        (HTTPError("https://x.test/a", 503), True),
        (HTTPError("https://x.test/a", 429), True),
        (HTTPError("https://x.test/a", 404), False),
        (AuthenticationError("https://x.test/a", 403), False),
        (TLSError("bad certificate"), False),
        (SegmentDownloadError(3, "https://x.test/s", "timeout"), True),
        (ConfigurationError("bad"), False),
        (InsufficientStorageError(10, 1, location="here"), False),
        (RuntimeError("bug"), False),
        (None, False),
    ],
)
def test_which_errors_are_retried(error: BaseException | None, retry: bool) -> None:
    assert RetryPolicy().should_retry(error, 1) is retry


def test_attempts_run_out() -> None:
    policy = RetryPolicy(max_attempts=3)
    error = NetworkConnectionError("reset")
    assert [policy.should_retry(error, n) for n in (1, 2, 3, 4)] == [True, True, False, False]
    assert not RetryPolicy(max_attempts=1).should_retry(error, 1)


def test_categories_can_be_narrowed() -> None:
    policy = RetryPolicy(categories=frozenset({ErrorCategory.HTTP}))
    assert not policy.should_retry(NetworkConnectionError("reset"), 1)
    assert policy.should_retry(HTTPError("https://x.test/a", 500), 1)


def test_policy_round_trips_and_validates() -> None:
    policy = RetryPolicy(
        max_attempts=5, initial_delay=1, categories=frozenset({ErrorCategory.NETWORK})
    )
    assert RetryPolicy.from_dict(policy.to_dict()) == policy
    assert RetryPolicy.from_dict({}) == RetryPolicy()
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="delays"):
        RetryPolicy(factor=0.5)
