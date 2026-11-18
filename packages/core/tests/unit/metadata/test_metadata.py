"""Metadata: reading it from playlists, choosing what to write, and writing it with FFmpeg."""

import json
import struct
import subprocess
import zlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from rayohx import DownloadState, OutputFormat
from rayohx._mux.ffmpeg import FfmpegInput, build_command
from rayohx.config import DownloadConfig, MetadataConfig, NetworkConfig, OutputConfig
from rayohx.downloader import Downloader
from rayohx.enums import MetadataPolicy
from rayohx.errors import ConfigurationError
from rayohx.metadata import Chapter, MetadataInfo, effective_metadata, extract_metadata
from rayohx.metadata import ffmpeg as meta_ffmpeg
from rayohx.playlist.parser import parse_playlist
from tests.unit._mux.helpers import MEDIA, Site, needs_ffmpeg

BASE = "https://media.example.com/"
START = "2026-01-01T10:00:00Z"


def png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


MASTER = f"""#EXTM3U
#EXT-X-SESSION-DATA:DATA-ID="com.apple.hls.title",VALUE="My Film: Part 1"
#EXT-X-SESSION-DATA:DATA-ID="description",VALUE="A film about things."
#EXT-X-SESSION-DATA:DATA-ID="com.apple.hls.language",VALUE="de"
#EXT-X-SESSION-DATA:DATA-ID="artwork",URI="{BASE}show/cover.png"
#EXT-X-SESSION-DATA:DATA-ID="broken"
#EXT-X-SESSION-DATA:oops
#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=320x240
index.m3u8
"""


def media_playlist(parts: int = 3, ranges: bool = True) -> str:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:2", "#EXT-X-PLAYLIST-TYPE:VOD"]
    if ranges:
        lines += [
            '#EXT-X-DATERANGE:ID="c1",START-DATE="2026-01-01T10:00:00Z",X-TITLE="Opening"',
            '#EXT-X-DATERANGE:ID="c2",START-DATE="2026-01-01T10:00:02Z",DURATION=1.5,'
            'X-TITLE="Middle; part = two"',
            '#EXT-X-DATERANGE:ID="ad",START-DATE="2026-01-01T10:00:01Z",CLASS="ad"',
            '#EXT-X-DATERANGE:ID="late",START-DATE="2026-01-02T10:00:00Z",X-TITLE="Out of range"',
            "#EXT-X-DATERANGE:garbage",
        ]
    lines.append(f"#EXT-X-PROGRAM-DATE-TIME:{START}")
    for index in range(parts):
        lines += ["#EXTINF:1.3,", f"seg{index}.ts"]
    return "\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n"


def site(master: str = MASTER, *, ranges: bool = True, art: bytes | None = None) -> Site:
    data = (MEDIA / "h264_aac.ts").read_bytes()
    packets = len(data) // 188
    bounds = [(packets * i // 3) * 188 for i in range(3)] + [packets * 188]
    files = {f"show/seg{i}.ts": data[bounds[i] : bounds[i + 1]] for i in range(3)}
    files["show/master.m3u8"] = master.encode()
    files["show/index.m3u8"] = media_playlist(ranges=ranges).encode()
    files["show/cover.png"] = png() if art is None else art
    return Site(files)


# --- reading the playlists ---------------------------------------------------------------------


def parsed() -> Any:
    return parse_playlist(MASTER, BASE + "show/master.m3u8")


def test_session_data_is_read_and_junk_is_skipped() -> None:
    master = parsed()
    ids = {item.data_id: item for item in master.session_data}
    assert set(ids) == {
        "com.apple.hls.title", "description", "com.apple.hls.language", "artwork", "broken",
    }  # fmt: skip
    assert ids["broken"].value is None
    assert ids["artwork"].uri == BASE + "show/cover.png"
    assert ids["description"].value == "A film about things."


def test_date_ranges_are_read_and_junk_is_skipped() -> None:
    media = parse_playlist(media_playlist(), BASE + "show/index.m3u8")
    assert [r.id for r in media.date_ranges] == ["c1", "c2", "ad", "late"]
    second = media.date_ranges[1]
    assert (second.duration, second.attributes["X-TITLE"]) == (1.5, "Middle; part = two")
    assert media.date_ranges[2].kind == "ad"


def test_what_the_stream_says_is_collected() -> None:
    master = parsed()
    media = parse_playlist(media_playlist(), BASE + "show/index.m3u8")
    info = extract_metadata(master, media, url=BASE + "show/master.m3u8?token=SECRET")
    assert (info.title, info.description, info.language) == (
        "My Film: Part 1",
        "A film about things.",
        "de",
    )
    assert info.artwork_url == BASE + "show/cover.png"
    assert info.duration == pytest.approx(3.9)
    assert info.start_time == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    assert "SECRET" not in (info.source or "")
    assert [(c.start, c.title) for c in info.chapters] == [
        (0.0, "Opening"),
        (2.0, "Middle; part = two"),
    ]
    assert info.chapters[1].end == 3.5
    assert not info.empty


def test_chapters_need_a_start_time_and_a_title() -> None:
    media = parse_playlist(
        media_playlist().replace("#EXT-X-PROGRAM-DATE-TIME:" + START, ""), BASE + "s/i.m3u8"
    )
    assert extract_metadata(None, media).chapters == ()
    assert extract_metadata(None, None) == MetadataInfo()


def test_artwork_must_be_a_web_address_and_language_can_come_from_the_audio_track() -> None:
    master = parse_playlist(
        '#EXTM3U\n#EXT-X-SESSION-DATA:DATA-ID="artwork",VALUE="file:///etc/passwd"\n'
        "#EXT-X-STREAM-INF:BANDWIDTH=1\nv.m3u8\n",
        BASE + "m.m3u8",
    )
    track = SimpleNamespace(language="fr")
    info = extract_metadata(master, None, audio=(track,))  # type: ignore[arg-type]
    assert info.artwork_url is None
    assert info.language == "fr"


# --- the policy --------------------------------------------------------------------------------

FULL = MetadataInfo(
    title="T", description="D", language="en", artwork_url=BASE + "c.png",
    chapters=(Chapter(0, "A"),), source="https://x/",
)  # fmt: skip


@pytest.mark.parametrize(
    ("policy", "kept"),
    [
        ("none", set()),
        ("minimal", {"title", "language"}),
        ("preserve", {"title", "description", "language", "artwork_url", "chapters"}),
        ("custom", set()),
    ],
)
def test_each_policy_keeps_what_it_promises(policy: str, kept: set[str]) -> None:
    chosen = effective_metadata(FULL, MetadataConfig(policy=policy))
    present = {
        name
        for name in ("title", "description", "language", "artwork_url", "chapters")
        if getattr(chosen, name)
    }
    assert present == kept


def test_switching_off_chapters_or_artwork_and_overriding_values() -> None:
    chosen = effective_metadata(
        FULL, MetadataConfig(policy="preserve", artwork=False, chapters=False)
    )
    assert chosen.artwork_url is None
    assert chosen.chapters == ()
    over = effective_metadata(
        FULL, MetadataConfig(policy="minimal", title="Mine", description="Own")
    )
    assert (over.title, over.description, over.language) == ("Mine", "Own", "en")
    custom = effective_metadata(FULL, MetadataConfig(policy="custom", title="Only"))
    assert (custom.title, custom.description, custom.language) == ("Only", None, None)
    assert (
        effective_metadata(FULL, MetadataConfig(title="ignored")) == MetadataInfo()
    )  # policy none


def test_metadata_settings_are_checked() -> None:
    assert MetadataConfig().policy is MetadataPolicy.NONE
    with pytest.raises(ConfigurationError, match="not a metadata policy"):
        MetadataConfig(policy="everything")
    with pytest.raises(ConfigurationError):
        MetadataConfig(title="x" * 3000)


# --- the FFmpeg helpers ------------------------------------------------------------------------


def test_chapter_files_escape_and_fill_in_the_ends() -> None:
    info = MetadataInfo(chapters=(Chapter(0, "A=1;#"), Chapter(2, "B", end=3.5), Chapter(5, "C")))
    text = meta_ffmpeg.chapters_text(info, total=9.0)
    assert text.startswith(";FFMETADATA1\n")
    assert "title=A\\=1\\;\\#" in text
    assert text.count("[CHAPTER]") == 3
    assert "START=0\nEND=2000" in text  # the next chapter's start
    assert "START=2000\nEND=3500" in text
    assert "START=5000\nEND=9000" in text  # the total length
    assert "END=6000" in meta_ffmpeg.chapters_text(info, total=None)


def test_which_files_can_hold_what() -> None:
    assert meta_ffmpeg.support_for(Path("a.mkv")).chapters
    assert meta_ffmpeg.support_for(Path("a.mp3")).artwork
    assert not meta_ffmpeg.support_for(Path("a.mp3")).chapters
    assert meta_ffmpeg.support_for(Path("a.ts")) == meta_ffmpeg.Support()
    assert meta_ffmpeg.support_for(Path("a.aac")) == meta_ffmpeg.Support()


def test_nothing_is_prepared_for_a_file_that_cannot_hold_metadata(tmp_path: Path) -> None:
    prepared = meta_ffmpeg.prepare(FULL, tmp_path / "a.ts", client=None, total_duration=1.0)
    assert prepared.tags == {}
    assert "cannot hold metadata" in prepared.notes[0]
    assert (
        meta_ffmpeg.prepare(
            MetadataInfo(), tmp_path / "a.mkv", client=None, total_duration=1
        ).written
        == []
    )


class FakeClient:
    def __init__(self, content: bytes | Exception) -> None:
        self.content = content

    def fetch_bytes(self, url: str, **_: object) -> SimpleNamespace:
        if isinstance(self.content, Exception):
            raise self.content
        return SimpleNamespace(content=self.content)


def test_artwork_must_really_be_an_image(tmp_path: Path) -> None:
    out = tmp_path / "a.mkv"
    info = MetadataInfo(title="T", artwork_url=BASE + "c.png")
    good = meta_ffmpeg.prepare(info, out, client=FakeClient(png()), total_duration=1)  # type: ignore[arg-type]
    assert good.artwork is not None
    assert good.artwork.suffix == ".png"
    assert "artwork" in good.written
    good.cleanup()
    assert not good.artwork.exists()
    for content in (b"<html>not a picture</html>", RuntimeError("down")):
        bad = meta_ffmpeg.prepare(info, out, client=FakeClient(content), total_duration=1)  # type: ignore[arg-type]
        assert bad.artwork is None
        assert "could not be used" in bad.notes[0]
        assert bad.tags == {"title": "T"}


def test_the_command_carries_the_metadata_without_a_shell(tmp_path: Path) -> None:
    cover = tmp_path / ".x.cover.png"
    chapters = tmp_path / ".x.chapters.txt"
    meta = meta_ffmpeg.FfmpegMetadata(
        tags={"title": 'He said "hi"; rm -rf /'},
        chapters_file=chapters,
        artwork=cover,
        language="de",
    )
    inputs = [FfmpegInput(Path("v.ts"), ("aac",))]
    mkv = build_command(Path("ffmpeg"), inputs, Path("o.mkv"), kind="mkv", metadata=meta)
    assert mkv[mkv.index("-metadata") + 1] == 'title=He said "hi"; rm -rf /'  # one argument
    assert "-attach" in mkv
    assert "mimetype=image/png" in mkv
    assert mkv[mkv.index("-map_chapters") + 1] == "1"
    assert "language=ger" in " ".join(mkv) or "language=deu" in " ".join(mkv)
    mp4 = build_command(Path("ffmpeg"), inputs, Path("o.mp4"), metadata=meta)
    assert "-attach" not in mp4
    assert mp4.count("-i") == 3
    assert "attached_pic" in mp4
    assert mp4[mp4.index("-disposition:v:1") - 0] == "-disposition:v:1"
    m4a = build_command(Path("ffmpeg"), inputs, Path("o.m4a"), audio_only=True, metadata=meta)
    assert "-disposition:v:0" in m4a
    assert "-vn" not in m4a  # the picture is the one video stream


# --- whole downloads ---------------------------------------------------------------------------


def run(
    web: Site,
    output: Path | None,
    fmt: OutputFormat,
    metadata: MetadataConfig,
    **kw: Any,
) -> tuple[Downloader, Any]:
    config = DownloadConfig(
        network=NetworkConfig(retries=0, backoff_factor=0.001),
        output=OutputConfig(
            format=fmt,
            directory=kw.pop("directory", None),
            name_template=kw.pop("template", None),
            **kw,
        ),
        metadata=metadata,
    )
    downloader = Downloader(
        BASE + "show/master.m3u8", output=output, config=config, transport=httpx.MockTransport(web)
    )
    return downloader, downloader.run()


def everything(path: Path) -> dict[str, Any]:
    done = subprocess.run(
        [  # noqa: S607
            "ffprobe", "-v", "error", "-show_format", "-show_streams", "-show_chapters",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return dict(json.loads(done.stdout))


@needs_ffmpeg
def test_matroska_gets_the_title_chapters_and_cover(tmp_path: Path) -> None:
    _, result = run(site(), tmp_path / "film", OutputFormat.MKV, MetadataConfig(policy="preserve"))
    assert result.success, result.error
    assert result.output is not None
    assert set(result.output.metadata) >= {
        "title",
        "description",
        "chapters",
        "artwork",
        "language",
    }
    found = everything(result.output.path)
    tags = {k.lower(): v for k, v in found["format"].get("tags", {}).items()}
    assert tags["title"] == "My Film: Part 1"
    assert [c["tags"]["title"] for c in found["chapters"]] == ["Opening", "Middle; part = two"]
    covers = [s for s in found["streams"] if s["disposition"]["attached_pic"] == 1]
    assert len(covers) == 1  # a Matroska attachment that is a picture shows up as a cover stream
    audio = next(s for s in found["streams"] if s["codec_type"] == "audio")
    assert audio["tags"]["language"] in {"ger", "deu"}
    assert list(tmp_path.glob(".*")) == []  # the helper files are gone


@needs_ffmpeg
def test_an_audio_file_gets_its_cover_and_title(tmp_path: Path) -> None:
    _, result = run(
        site(), tmp_path / "talk", OutputFormat.AUDIO, MetadataConfig(policy="preserve")
    )
    assert result.success, result.error
    assert result.output is not None
    assert result.output.path.suffix == ".m4a"
    found = everything(result.output.path)
    assert {k.lower(): v for k, v in found["format"]["tags"].items()}["title"] == "My Film: Part 1"
    picture = [s for s in found["streams"] if s["codec_type"] == "video"]
    assert len(picture) == 1
    assert picture[0]["disposition"]["attached_pic"] == 1
    assert len(found["chapters"]) == 2


@needs_ffmpeg
def test_minimal_writes_only_the_title_and_language(tmp_path: Path) -> None:
    _, result = run(site(), tmp_path / "m", OutputFormat.MKV, MetadataConfig(policy="minimal"))
    assert result.output is not None
    assert set(result.output.metadata) == {"title", "language"}
    found = everything(result.output.path)
    assert found["chapters"] == []
    assert not [s for s in found["streams"] if s["disposition"]["attached_pic"] == 1]


@needs_ffmpeg
def test_custom_values_replace_what_the_stream_says(tmp_path: Path) -> None:
    _, result = run(
        site(),
        tmp_path / "c",
        OutputFormat.MKV,
        MetadataConfig(policy="custom", title="Mine", description="Own"),
    )
    found = everything(result.output.path)  # type: ignore[union-attr]
    tags = {k.lower(): v for k, v in found["format"]["tags"].items()}
    assert tags["title"] == "Mine"
    assert found["chapters"] == []


@needs_ffmpeg
def test_policy_none_writes_nothing(tmp_path: Path) -> None:
    _, result = run(site(), tmp_path / "n", OutputFormat.MKV, MetadataConfig())
    assert result.output is not None
    assert result.output.metadata == ()
    assert result.notes == ()
    tags = everything(result.output.path)["format"].get("tags", {})
    assert "title" not in {k.lower() for k in tags}


@needs_ffmpeg
def test_a_bad_cover_never_fails_the_download(tmp_path: Path) -> None:
    _, result = run(
        site(art=b"<html>nope</html>"),
        tmp_path / "b",
        OutputFormat.MKV,
        MetadataConfig(policy="preserve"),
    )
    assert result.success, result.error
    assert result.output is not None
    assert "artwork" not in result.output.metadata
    assert any("cover picture" in n for n in result.notes)


def test_the_built_in_mp4_remuxer_says_it_cannot_write_metadata(tmp_path: Path) -> None:
    _, result = run(site(), tmp_path / "v.mp4", OutputFormat.MP4, MetadataConfig(policy="preserve"))
    assert result.success, result.error
    assert result.output is not None
    assert result.output.metadata == ()
    assert any("Metadata was not written" in n for n in result.notes)


def test_a_transport_stream_says_so_too(tmp_path: Path) -> None:
    _, result = run(site(), tmp_path / "v.ts", OutputFormat.TS, MetadataConfig(policy="preserve"))
    assert result.success, result.error
    assert any("Metadata was not written" in n for n in result.notes)
    _, quiet = run(site(), tmp_path / "w.ts", OutputFormat.TS, MetadataConfig())
    assert quiet.notes == ()


def test_the_title_can_name_the_file(tmp_path: Path) -> None:
    _, result = run(
        site(), None, OutputFormat.TS, MetadataConfig(policy="none"),
        directory=tmp_path, template="{title} [{language}]",
    )  # fmt: skip
    assert result.success, result.error
    assert result.output is not None
    # The title only names the file here. Characters unsafe in a name are replaced.
    assert result.output.path == tmp_path / "My Film_ Part 1 [de].ts"


def test_a_name_template_falls_back_to_the_address(tmp_path: Path) -> None:
    plain = site(master="#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=300000\nindex.m3u8\n")
    _, result = run(
        plain, None, OutputFormat.TS, MetadataConfig(), directory=tmp_path, template="{title}"
    )
    assert result.output is not None
    assert result.output.path == tmp_path / "show.ts"


def test_an_explicit_output_path_beats_the_template(tmp_path: Path) -> None:
    _, result = run(
        site(), tmp_path / "chosen", OutputFormat.TS, MetadataConfig(), template="{title}"
    )
    assert result.output is not None
    assert result.output.path == tmp_path / "chosen.ts"


def test_a_bad_template_is_refused_when_the_settings_are_made() -> None:
    with pytest.raises(ConfigurationError):
        OutputConfig(name_template="{nope}")
    with pytest.raises(ConfigurationError):
        OutputConfig(name_template="a/{title}")


def test_the_state_machine_is_not_disturbed_by_metadata(tmp_path: Path) -> None:
    downloader, result = run(
        site(), tmp_path / "s.ts", OutputFormat.TS, MetadataConfig(policy="preserve")
    )
    assert result.state is DownloadState.COMPLETED
    assert downloader.state is DownloadState.COMPLETED
