import struct
from pathlib import Path

import pytest
from rayohx_pytest.media import box, fmp4_fragment, fmp4_init, ts_payload

from rayohx import ContainerFormat
from rayohx._download._containers import (
    validate_fmp4_file,
    validate_output,
    validate_ts_file,
)
from rayohx.errors import FinalizationError

TS = ContainerFormat.MPEG_TS


MP4 = ContainerFormat.FMP4


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_a_good_ts_file_passes(tmp_path: Path) -> None:
    validate_ts_file(write(tmp_path / "a.ts", b"".join(ts_payload(i, 5) for i in range(40))))


def test_a_huge_ts_file_is_only_spot_checked(tmp_path: Path) -> None:
    path = tmp_path / "big.ts"
    with path.open("wb") as handle:
        for index in range(20_000):
            handle.write(ts_payload(index, 1))
    validate_ts_file(path)


@pytest.mark.parametrize("data", [b"", b"\x47" * 100])
def test_a_tiny_ts_file_is_rejected(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(FinalizationError, match="too small"):
        validate_ts_file(write(tmp_path / "a.ts", data))


def test_a_ts_file_of_something_else_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FinalizationError, match="not a valid MPEG-TS") as info:
        validate_ts_file(write(tmp_path / "a.ts", b"<html>" + bytes(2000)))
    assert info.value.hint


def test_misaligned_packets_are_rejected(tmp_path: Path) -> None:
    good = ts_payload(0, 20)
    shifted = good[:188] + b"\x00" + good[188:]
    with pytest.raises(FinalizationError, match="misaligned"):
        validate_ts_file(write(tmp_path / "a.ts", shifted))


def test_a_trailing_partial_packet_only_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        validate_ts_file(write(tmp_path / "a.ts", ts_payload(0, 10) + b"\x00" * 7))
    assert "partial packet" in caplog.text


def fmp4_file(*fragments: int) -> bytes:
    return fmp4_init() + b"".join(fmp4_fragment(i) for i in fragments)


def test_a_good_fmp4_file_passes(tmp_path: Path) -> None:
    validate_fmp4_file(write(tmp_path / "a.mp4", fmp4_file(0, 1, 2, 3)))


def test_large_and_open_ended_boxes_are_understood(tmp_path: Path) -> None:
    body = bytes(50)
    large = struct.pack(">I4sQ", 1, b"mdat", 16 + len(body)) + body
    open_ended = struct.pack(">I4s", 0, b"free") + bytes(30)
    data = fmp4_init() + box(b"moof", box(b"mfhd", bytes(8))) + large + open_ended
    validate_fmp4_file(write(tmp_path / "a.mp4", data))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (fmp4_file(0, 1)[:-20], "runs past the end"),
        (fmp4_file(0)[:-95] + b"\x00\x00\x00", "past the end|ends in the middle"),
        (b"\x00\x00\x00", "middle of an MP4 box header"),
        (struct.pack(">I4s", 1, b"mdat") + b"\x00" * 4, "middle of an MP4 box header"),
        (struct.pack(">I4s", 4, b"free"), "runs past the end"),
        (b"<html>denied</html>", "runs past the end|does not start"),
        (fmp4_init(), "no fragment"),
        (box(b"moof") + box(b"mdat"), "does not start like"),
        (box(b"ftyp", bytes(8)) + fmp4_fragment(0), "no initialization"),
        (box(b"ftyp", bytes(8)) + box(b"moov") + box(b"moof"), "no media data"),
    ],
)
def test_damaged_or_incomplete_fmp4_files_are_rejected(
    tmp_path: Path, data: bytes, message: str
) -> None:
    with pytest.raises(FinalizationError, match=message):
        validate_fmp4_file(write(tmp_path / "a.mp4", data))


def test_validate_output_picks_the_right_check(tmp_path: Path) -> None:
    validate_output(TS, write(tmp_path / "a.ts", ts_payload(0, 5)))
    validate_output(MP4, write(tmp_path / "a.mp4", fmp4_file(0)))
    with pytest.raises(FinalizationError):
        validate_output(TS, write(tmp_path / "b.ts", b"x" * 400))
    with pytest.raises(FinalizationError):
        validate_output(MP4, write(tmp_path / "b.mp4", b"x" * 400))
    validate_output(ContainerFormat.UNKNOWN, write(tmp_path / "c.bin", b"whatever"))
