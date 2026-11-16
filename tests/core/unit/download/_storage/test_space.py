import errno
from pathlib import Path

import pytest

from rayohx import StorageStrategy
from rayohx.config import StorageConfig
from rayohx.download._storage import (
    DEFAULT_SPILL_BYTES,
    ESTIMATE_MARGIN,
    SizeEstimator,
    SpaceNeed,
    check_disk_space,
    free_bytes,
    nearest_existing,
    same_volume,
    space_needed,
    translate_os_error,
)
from rayohx.errors import InsufficientStorageError, OutputError
from tests.helpers.storage import GIB, S


def test_the_estimate_starts_from_the_bitrate() -> None:
    estimator = SizeEstimator([4.0] * 10, 8_000_000)
    assert estimator.total_bytes() == 40_000_000
    assert estimator.bytes_per_second() == 1_000_000
    assert estimator.average_segment_bytes() == 4_000_000
    assert estimator.samples == 0


def test_the_estimate_learns_from_real_segments() -> None:
    estimator = SizeEstimator([4.0] * 10, 8_000_000)
    estimator.observe(4.0, 2_000_000)
    estimator.observe(4.0, 2_000_000)
    assert estimator.samples == 2
    assert estimator.total_bytes() == 20_000_000
    assert estimator.average_segment_bytes() == 2_000_000


def test_without_a_bitrate_nothing_is_known_until_a_segment_arrives() -> None:
    estimator = SizeEstimator([4.0] * 5, None)
    assert estimator.total_bytes() is None
    assert estimator.average_segment_bytes() == 0
    estimator.observe(4.0, 1000)
    assert estimator.total_bytes() == 5000


def test_the_estimator_uses_the_average_bitrate_when_given() -> None:
    from rayohx import MediaPlaylist, Segment, Variant

    playlist = MediaPlaylist(
        uri="u",
        target_duration=4,
        segments=tuple(
            Segment(index=i, uri=f"{i}.ts", duration=4.0, sequence_number=i) for i in range(5)
        ),
    )
    plain = SizeEstimator.for_playlist(playlist, Variant(uri="v", bandwidth=8_000_000))
    averaged = SizeEstimator.for_playlist(
        playlist, Variant(uri="v", bandwidth=8_000_000, average_bandwidth=4_000_000)
    )
    unknown = SizeEstimator.for_playlist(playlist, None)
    assert plain.total_bytes() == 20_000_000
    assert averaged.total_bytes() == 10_000_000
    assert unknown.total_bytes() is None


def need(
    strategy: StorageStrategy, config: StorageConfig | None = None, **options: bool
) -> SpaceNeed:
    return space_needed(strategy, 10 * GIB, config or StorageConfig(), **options)


def test_a_direct_download_needs_the_output_and_no_working_space() -> None:
    result = need(S.DIRECT)
    assert result.output_bytes == int(10 * GIB * ESTIMATE_MARGIN)
    assert result.workspace_bytes == 0
    # The old tool needed twice the output; this one must not.
    assert result.output_bytes + result.workspace_bytes < 2 * 10 * GIB


def test_streaming_to_a_pipe_needs_no_disk() -> None:
    assert need(S.STREAMING, writes_file=False) == SpaceNeed(0, 0)
    assert need(S.BUFFERED, writes_file=False) == SpaceNeed(0, 0)


def test_temporary_storage_is_bounded_when_a_limit_is_set() -> None:
    unlimited = need(S.TEMPORARY)
    limited = need(S.TEMPORARY, StorageConfig(max_temp_bytes=GIB))
    assert unlimited.workspace_bytes == int(10 * GIB * ESTIMATE_MARGIN)
    assert limited.workspace_bytes == GIB
    assert limited.output_bytes == unlimited.output_bytes


def test_hybrid_working_space_is_small_by_default() -> None:
    assert need(S.HYBRID).workspace_bytes == DEFAULT_SPILL_BYTES
    assert need(S.HYBRID, StorageConfig(max_temp_bytes=GIB // 4)).workspace_bytes == GIB // 4
    tiny = space_needed(S.HYBRID, 1000, StorageConfig())
    assert tiny.workspace_bytes == int(1000 * ESTIMATE_MARGIN)


def test_the_paths_and_volumes(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    assert nearest_existing(deep) == tmp_path
    assert free_bytes(deep) > 0
    assert same_volume(deep, tmp_path / "other")


def test_enough_space_passes_and_too_little_fails_accurately(tmp_path: Path) -> None:
    need_ = SpaceNeed(output_bytes=700, workspace_bytes=200)
    check_disk_space(
        need_, output_dir=tmp_path, workspace_dir=tmp_path, reserve_bytes=100, free=lambda _p: 1000
    )
    with pytest.raises(InsufficientStorageError) as info:
        check_disk_space(
            need_,
            output_dir=tmp_path,
            workspace_dir=tmp_path,
            reserve_bytes=101,
            free=lambda _p: 1000,
        )
    assert info.value.required_bytes == 1001
    assert info.value.available_bytes == 1000
    assert str(tmp_path) in str(info.value)


def test_separate_disks_are_checked_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rayohx.download._storage._space.same_volume", lambda _a, _b: False)
    output, work = tmp_path / "out", tmp_path / "work"
    space = {output: 1000, work: 300}
    need_ = SpaceNeed(output_bytes=900, workspace_bytes=250)

    def free(path: Path) -> int:
        return space[path]

    check_disk_space(need_, output_dir=output, workspace_dir=work, reserve_bytes=50, free=free)
    space[work] = 299
    with pytest.raises(InsufficientStorageError) as info:
        check_disk_space(need_, output_dir=output, workspace_dir=work, reserve_bytes=50, free=free)
    assert str(work) in str(info.value)
    space[work] = 300
    space[output] = 949
    with pytest.raises(InsufficientStorageError):
        check_disk_space(need_, output_dir=output, workspace_dir=work, reserve_bytes=50, free=free)


def test_a_disk_with_no_need_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("rayohx.download._storage._space.same_volume", lambda _a, _b: False)
    check_disk_space(
        SpaceNeed(0, 0),
        output_dir=tmp_path,
        workspace_dir=tmp_path,
        reserve_bytes=10,
        free=lambda _p: pytest.fail("nothing should be checked"),
    )


def test_a_full_disk_is_recognised_when_writing() -> None:
    full = translate_os_error(OSError(errno.ENOSPC, "No space left on device"), "out.mp4")
    assert isinstance(full, InsufficientStorageError)
    other = translate_os_error(OSError(errno.EACCES, "Permission denied"), "out.mp4")
    assert isinstance(other, OutputError)
    assert "Permission denied" in str(other)
