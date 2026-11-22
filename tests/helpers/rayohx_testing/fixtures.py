"""Files shared by every package's tests, kept in the repository's ``tests/fixtures`` folder."""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def fixture_path(name: str) -> Path:
    """The path of a shared fixture, for example ``hls/master_two_variants.m3u8``."""
    return FIXTURES / name


def fixture_text(name: str) -> str:
    return fixture_path(name).read_text(encoding="utf-8")


def fixture_bytes(name: str) -> bytes:
    return fixture_path(name).read_bytes()
