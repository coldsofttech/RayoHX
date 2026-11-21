import dataclasses

import pytest

from rayohx.models import StorageMetrics


def test_a_new_snapshot_has_moved_and_kept_nothing() -> None:
    metrics = StorageMetrics()
    assert dataclasses.asdict(metrics) == {
        "output_bytes": 0,
        "temporary_bytes": 0,
        "working_bytes": 0,
        "peak_temporary_bytes": 0,
        "downloaded_bytes": 0,
        "written_bytes": 0,
    }


def test_each_figure_is_set_on_its_own() -> None:
    metrics = StorageMetrics(downloaded_bytes=500, written_bytes=300, peak_temporary_bytes=40)
    assert (metrics.downloaded_bytes, metrics.written_bytes) == (500, 300)
    assert metrics.peak_temporary_bytes == 40
    assert (metrics.output_bytes, metrics.temporary_bytes, metrics.working_bytes) == (0, 0, 0)


def test_a_snapshot_cannot_be_changed() -> None:
    metrics = StorageMetrics()
    with pytest.raises(dataclasses.FrozenInstanceError):
        metrics.written_bytes = 1  # type: ignore[misc]


def test_figures_must_be_named() -> None:
    with pytest.raises(TypeError):
        StorageMetrics(1)  # type: ignore[call-arg]


def test_snapshots_with_the_same_figures_are_equal() -> None:
    assert StorageMetrics(written_bytes=5) == StorageMetrics(written_bytes=5)
    assert StorageMetrics(written_bytes=5) != StorageMetrics(written_bytes=6)
