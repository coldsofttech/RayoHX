"""Helpers for reading the HLS fixture files."""

from pathlib import Path

from rayohx import MasterPlaylist, MediaPlaylist, Resolution, Variant
from rayohx.playlist.parser import parse_playlist

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "hls"
BASE = "https://media.example.com/vod/title/master.m3u8"
#: The folder ``BASE`` lives in, which relative addresses in the fixtures resolve against.
DIR = "https://media.example.com/vod/title/"


def fixture_text(name: str) -> str:
    """Return the text of ``tests/fixtures/hls/<name>``."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def media(name: str) -> MediaPlaylist:
    """Parse the media playlist fixture ``name``."""
    playlist = parse_playlist(fixture_text(name), BASE)
    assert isinstance(playlist, MediaPlaylist)
    return playlist


def master(name: str) -> MasterPlaylist:
    """Parse the master playlist fixture ``name``."""
    playlist = parse_playlist(fixture_text(name), BASE)
    assert isinstance(playlist, MasterPlaylist)
    return playlist


def variant(
    bandwidth: int,
    size: tuple[int, int] | None = None,
    *codecs: str,
    uri: str = "v.m3u8",
    **extra: object,
) -> Variant:
    """A variant with the given bandwidth, picture size and codecs."""
    return Variant(
        uri=uri,
        bandwidth=bandwidth,
        resolution=Resolution(*size) if size else None,
        codecs=codecs,
        **extra,  # type: ignore[arg-type]
    )
