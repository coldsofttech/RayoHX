from pathlib import Path

import pytest

from rayohx import ContainerFormat, OutputFormat
from rayohx._download._output import (
    plan_output,
)
from rayohx.errors import OutputFormatError

TS = ContainerFormat.MPEG_TS


MP4 = ContainerFormat.FMP4


URL = "https://cdn.example.com/shows/my-show/index.m3u8?token=abc"


def plan(
    path: str | None,
    container: ContainerFormat,
    requested: OutputFormat = OutputFormat.AUTO,
    directory: Path | None = None,
) -> tuple[str, OutputFormat]:
    result = plan_output(
        path=Path(path) if path else None,
        requested=requested,
        container=container,
        url=URL,
        directory=directory,
    )
    return result.path.as_posix(), result.format


@pytest.mark.parametrize(
    ("path", "container", "expected"),
    [
        ("video.ts", TS, ("video.ts", OutputFormat.TS)),
        ("video.TS", TS, ("video.TS", OutputFormat.TS)),
        ("video.m2ts", TS, ("video.m2ts", OutputFormat.TS)),
        ("video.mp4", MP4, ("video.mp4", OutputFormat.MP4)),
        ("video.m4v", MP4, ("video.m4v", OutputFormat.MP4)),
        ("video", TS, ("video.ts", OutputFormat.TS)),
        ("video", MP4, ("video.mp4", OutputFormat.MP4)),
        ("dir/video", MP4, ("dir/video.mp4", OutputFormat.MP4)),
    ],
)
def test_names_must_match_what_is_inside(
    path: str, container: ContainerFormat, expected: tuple[str, OutputFormat]
) -> None:
    assert plan(path, container) == expected


def test_a_name_is_made_from_the_address(tmp_path: Path) -> None:
    assert plan(None, TS, directory=tmp_path) == (
        (tmp_path / "my-show.ts").as_posix(),
        OutputFormat.TS,
    )
    assert plan(None, MP4, directory=tmp_path) == (
        (tmp_path / "my-show.mp4").as_posix(),
        OutputFormat.MP4,
    )
    unnamed = plan_output(
        path=None, requested=OutputFormat.AUTO, container=TS, url="https://h/index.m3u8"
    )
    assert unnamed.path == Path.cwd() / "video.ts"


def test_ts_is_never_saved_under_an_mp4_name() -> None:
    with pytest.raises(OutputFormatError, match="cannot be saved as MP4") as info:
        plan("video.mp4", TS)
    assert ".ts" in (info.value.hint or "")
    with pytest.raises(OutputFormatError, match="cannot be saved as MP4"):
        plan(None, TS, OutputFormat.MP4)


def test_fmp4_is_never_saved_under_a_ts_name() -> None:
    with pytest.raises(OutputFormatError, match="cannot be saved as TS") as info:
        plan("video.ts", MP4)
    assert ".mp4" in (info.value.hint or "")


def test_an_explicit_format_must_agree_with_the_file_name() -> None:
    with pytest.raises(OutputFormatError, match="was asked for"):
        plan("video.mp4", TS, OutputFormat.TS)
    assert plan("video.ts", TS, OutputFormat.TS) == ("video.ts", OutputFormat.TS)
    assert plan("video", MP4, OutputFormat.MP4) == ("video.mp4", OutputFormat.MP4)


@pytest.mark.parametrize("name", ["video.avi", "video.mov", "video.webm", "video.txt"])
def test_unsupported_file_types_are_refused(name: str) -> None:
    with pytest.raises(OutputFormatError, match="not supported") as info:
        plan(name, TS)
    assert ".ts" in (info.value.hint or "")


def test_segments_go_in_a_folder_whatever_the_format() -> None:
    assert plan("parts", TS, OutputFormat.SEGMENTS) == ("parts", OutputFormat.SEGMENTS)
    assert plan("parts", MP4, OutputFormat.SEGMENTS) == ("parts", OutputFormat.SEGMENTS)
    folder = plan_output(
        path=None, requested=OutputFormat.SEGMENTS, container=TS, url=URL, directory=Path("/out")
    )
    assert folder.path == Path("/out/my-show")
    assert folder.is_directory


@pytest.mark.parametrize("container", [ContainerFormat.UNKNOWN, ContainerFormat.WEBVTT])
def test_unusable_formats_are_explained(container: ContainerFormat) -> None:
    with pytest.raises(OutputFormatError) as info:
        plan("video.ts", container)
    assert info.value.hint
