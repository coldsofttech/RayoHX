from pathlib import Path

from rayohx import ContainerFormat, StorageStrategy
from rayohx._download import DownloadSummary
from rayohx.downloader._result import join_message, output_info
from rayohx.models import DownloadProgress, StorageMetrics


def summary(output: Path | None = None) -> DownloadSummary:
    return DownloadSummary(
        strategy=StorageStrategy.DIRECT,
        total_segments=1,
        resumed_segments=0,
        metrics=StorageMetrics(),
        progress=DownloadProgress(),
        elapsed_seconds=0.1,
        output=output,
    )


def test_a_message_is_followed_by_its_hint() -> None:
    assert join_message("It failed.", "Try again.") == "It failed. Try again."


def test_a_message_without_a_hint_is_left_as_it_is() -> None:
    assert join_message("It failed.", None) == "It failed."
    assert join_message("It failed.", "") == "It failed."


def test_the_result_describes_the_written_file(tmp_path: Path) -> None:
    path = tmp_path / "out.ts"
    path.write_bytes(b"x" * 123)
    info = output_info(path, summary(), ContainerFormat.MPEG_TS)
    assert (info.path, info.container, info.size_bytes) == (path, ContainerFormat.MPEG_TS, 123)


def test_a_folder_of_segments_is_measured_by_the_files_in_it(tmp_path: Path) -> None:
    folder = tmp_path / "segments"
    folder.mkdir()
    (folder / "a.ts").write_bytes(b"123")
    (folder / "b.ts").write_bytes(b"45678")
    (folder / "nested").mkdir()
    (folder / "nested" / "c.ts").write_bytes(b"not counted")
    info = output_info(folder, summary(), ContainerFormat.MPEG_TS)
    assert info.size_bytes == 8


def test_the_path_the_download_reports_wins_over_the_planned_one(tmp_path: Path) -> None:
    planned = tmp_path / "planned.mp4"
    written = tmp_path / "written.mp4"
    written.write_bytes(b"x" * 7)
    info = output_info(planned, summary(written), ContainerFormat.FMP4)
    assert (info.path, info.size_bytes) == (written, 7)
