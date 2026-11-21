from pathlib import Path

import pytest

from rayohx import CancellationToken
from rayohx._download._output import OutputPlan
from rayohx.config import DownloadConfig, OutputConfig
from rayohx.downloader._delivery import Delivery, check_free, subtitle_path
from rayohx.enums import ContainerFormat, OutputFormat
from rayohx.errors import OutputExistsError
from rayohx.events import EventBus
from rayohx.models import SubtitleTrack
from tests.helpers.media import Origin, client_for

TS = ContainerFormat.MPEG_TS


def make(origin: Origin, *, overwrite: bool = False) -> tuple[Delivery, list[int]]:
    finalizing: list[int] = []
    delivery = Delivery(
        client_for(origin),
        DownloadConfig(output=OutputConfig(overwrite=overwrite)),
        EventBus(),
        "abc123",
        CancellationToken(),
        lambda: finalizing.append(1),
    )
    return delivery, finalizing


def track(name: str = "English", language: str | None = "en") -> SubtitleTrack:
    return SubtitleTrack(
        group_id="sub",
        name=name,
        language=language,
        uri="https://example.com/sub.m3u8",
        default=False,
        autoselect=True,
        forced=False,
        characteristics=(),
    )


# --- plain -------------------------------------------------------------------------------------


def test_plain_delivery_joins_the_segments_into_the_planned_file(tmp_path: Path) -> None:
    origin = Origin(6, content="ts")
    delivery, finalizing = make(origin)
    plan = OutputPlan(tmp_path / "out.ts", OutputFormat.TS, TS)
    summary = delivery.plain(origin.playlist(), TS, plan, None)
    assert plan.path.read_bytes() == origin.expected()
    assert summary.output == plan.path
    assert summary.total_segments == 6
    assert finalizing == [1]  # told once, just before the output is put in place
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out.ts"]


def test_plain_delivery_can_save_every_segment_as_its_own_file(tmp_path: Path) -> None:
    origin = Origin(3, content="ts")
    delivery, _ = make(origin)
    plan = OutputPlan(tmp_path / "segments", OutputFormat.SEGMENTS, TS)
    delivery.plain(origin.playlist(), TS, plan, None)
    names = sorted(path.name for path in plan.path.iterdir())
    assert names == ["segment-00001.ts", "segment-00002.ts", "segment-00003.ts"]


def test_an_existing_file_is_not_replaced_by_plain_delivery(tmp_path: Path) -> None:
    origin = Origin(2, content="ts")
    delivery, _ = make(origin)
    plan = OutputPlan(tmp_path / "out.ts", OutputFormat.TS, TS)
    plan.path.write_bytes(b"old")
    with pytest.raises(OutputExistsError):
        delivery.plain(origin.playlist(), TS, plan, None)
    assert plan.path.read_bytes() == b"old"


def test_overwriting_replaces_the_existing_file(tmp_path: Path) -> None:
    origin = Origin(2, content="ts")
    delivery, _ = make(origin, overwrite=True)
    plan = OutputPlan(tmp_path / "out.ts", OutputFormat.TS, TS)
    plan.path.write_bytes(b"old")
    delivery.plain(origin.playlist(), TS, plan, None)
    assert plan.path.read_bytes() == origin.expected()


# --- helpers of the other deliveries -----------------------------------------------------------


@pytest.mark.parametrize(
    ("container", "suffix"),
    [(TS, ".ts"), (ContainerFormat.FMP4, ".mp4"), (ContainerFormat.UNKNOWN, ".bin")],
)
def test_temporary_pieces_are_hidden_files_beside_the_output(
    container: ContainerFormat, suffix: str
) -> None:
    path = Delivery._temporary(Path("out") / "video.mp4", "audio0", container)
    assert path == Path("out") / f".video.mp4.audio0{suffix}"


def test_a_part_file_is_moved_into_place(tmp_path: Path) -> None:
    delivery, _ = make(Origin(1))
    part = tmp_path / "out.mp4.part"
    part.write_bytes(b"new")
    delivery._place(part, tmp_path / "out.mp4")
    assert (tmp_path / "out.mp4").read_bytes() == b"new"
    assert not part.exists()


def test_a_part_file_does_not_replace_a_file_that_appeared_meanwhile(tmp_path: Path) -> None:
    delivery, _ = make(Origin(1))
    part = tmp_path / "out.mp4.part"
    part.write_bytes(b"new")
    (tmp_path / "out.mp4").write_bytes(b"old")
    with pytest.raises(OutputExistsError):
        delivery._place(part, tmp_path / "out.mp4")
    assert (tmp_path / "out.mp4").read_bytes() == b"old"


def test_overwriting_lets_a_part_file_replace_the_existing_one(tmp_path: Path) -> None:
    delivery, _ = make(Origin(1), overwrite=True)
    part = tmp_path / "out.mp4.part"
    part.write_bytes(b"new")
    (tmp_path / "out.mp4").write_bytes(b"old")
    delivery._place(part, tmp_path / "out.mp4")
    assert (tmp_path / "out.mp4").read_bytes() == b"new"


# --- subtitle names and early checks -----------------------------------------------------------


def test_a_subtitle_file_is_named_after_the_output_and_the_language() -> None:
    used: set[Path] = set()
    path = subtitle_path(Path("out") / "movie.mp4", track(), used)
    assert path == Path("out") / "movie.en.vtt"
    assert used == {path}


def test_two_tracks_with_one_language_get_different_names() -> None:
    used: set[Path] = set()
    output = Path("out") / "movie.mp4"
    first = subtitle_path(output, track(), used)
    second = subtitle_path(output, track(), used)
    third = subtitle_path(output, track(), used)
    assert [first.name, second.name, third.name] == [
        "movie.en.vtt",
        "movie.en2.vtt",
        "movie.en3.vtt",
    ]


def test_a_track_without_a_language_is_named_after_its_title() -> None:
    path = subtitle_path(Path("movie.mp4"), track(name="Director's cut", language=None), set())
    assert path == Path("movie.Director_s_cut.vtt")


def test_a_track_with_nothing_to_name_it_by_is_called_subtitles() -> None:
    path = subtitle_path(Path("movie.mp4"), track(name="???", language=None), set())
    assert path == Path("movie.subtitles.vtt")


def test_existing_files_are_refused_before_anything_is_downloaded(tmp_path: Path) -> None:
    free = tmp_path / "free.ts"
    taken = tmp_path / "taken.ts"
    taken.write_bytes(b"x")
    check_free([free], overwrite=False)
    with pytest.raises(OutputExistsError, match=r"taken.ts") as info:
        check_free([free, taken], overwrite=False)
    assert info.value.hint


def test_nothing_is_refused_when_overwriting_is_allowed(tmp_path: Path) -> None:
    taken = tmp_path / "taken.ts"
    taken.write_bytes(b"x")
    check_free([taken], overwrite=True)
