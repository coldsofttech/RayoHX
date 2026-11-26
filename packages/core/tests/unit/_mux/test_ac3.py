import pytest
from rayohx_pytest.media import BitWriter
from rayohx_pytest.site import media

from rayohx._mux import _ac3 as ac3
from rayohx._mux._mp4read import find_box
from rayohx.errors import OutputFormatError
from tests.helpers.mux import stream_payloads


@pytest.mark.parametrize(
    ("name", "kind", "enhanced"), [("h264_ac3.ts", 0x81, False), ("h264_eac3.ts", 0x87, True)]
)
def test_real_dolby_streams_parse_frame_after_frame(name: str, kind: int, enhanced: bool) -> None:
    parser = ac3.Ac3Parser()
    units = []
    for payload in stream_payloads(name, kind):
        units += parser.frames(payload)
    units += parser.flush()
    assert len(units) == 115
    assert all(unit[:2] == ac3.SYNC for unit in units)
    assert parser.config is not None
    assert parser.enhanced is enhanced
    assert parser.sample_rate == 44100
    assert parser.samples_per_frame == 1536
    assert find_box(parser.config.sample_entry, (b"dec3" if enhanced else b"dac3",), 36) is not None


def test_dac3_describes_the_stream() -> None:
    parser = ac3.Ac3Parser()
    for payload in stream_payloads("h264_ac3.ts", 0x81):
        parser.frames(payload)
    assert parser.config is not None
    found = find_box(parser.config.sample_entry, (b"dac3",), 36)
    assert found is not None
    bits = int.from_bytes(parser.config.sample_entry[found[0] + 8 : found[0] + 11], "big")
    assert bits >> 22 == 1  # 44.1 kHz
    assert (bits >> 5) & 0x1F == 6  # the code for 96 kbit/s


def test_dolby_frames_cut_across_payloads() -> None:
    data = b"".join(stream_payloads("h264_ac3.ts", 0x81))
    parser = ac3.Ac3Parser()
    units = []
    for start in range(0, len(data), 53):
        units += parser.frames(data[start : start + 53])
    units += parser.flush()
    assert len(units) == 115


def test_a_dolby_frame_with_an_unknown_version_is_refused() -> None:
    data = ac3.SYNC + bytes(2) + b"\x00" + bytes([0x1F << 3]) + bytes(20)
    with pytest.raises(OutputFormatError, match="bit stream version"):
        ac3.parse_frame(data, 0)


def test_incomplete_dolby_frames_wait_for_more_data() -> None:
    data = b"".join(stream_payloads("h264_ac3.ts", 0x81))
    assert ac3.parse_frame(data[:10], 0) is None
    first = ac3.parse_frame(data, 0)
    assert first is not None
    assert ac3.parse_frame(data[: len(first.data) - 1], 0) is None


def eac3_frame(
    *, fscod: int = 1, blocks_code: int = 3, strmtyp: int = 0, size_words: int = 100
) -> bytes:
    writer = BitWriter().bits(strmtyp, 2).bits(0, 3).bits(size_words - 1, 11).bits(fscod, 2)
    if fscod == 3:
        writer.bits(1, 2)
    else:
        writer.bits(blocks_code, 2)
    writer.bits(7, 3).flag(True).bits(16, 5)
    body = writer.to_bytes(trailing=False)
    return ac3.SYNC + body + bytes(size_words * 2 - 2 - len(body))


def test_dolby_digital_plus_frames_are_measured_by_their_header() -> None:
    frame = ac3.parse_frame(eac3_frame(blocks_code=3), 0)
    assert frame is not None
    assert frame.enhanced
    assert (frame.sample_rate, frame.samples, frame.channels) == (44100, 1536, 6)
    assert len(frame.data) == 200
    short = ac3.parse_frame(eac3_frame(blocks_code=0), 0)
    assert short is not None
    assert short.samples == 256


def test_reduced_sample_rates_are_read_for_dolby_digital_plus() -> None:
    frame = ac3.parse_frame(eac3_frame(fscod=3), 0)
    assert frame is not None
    assert frame.sample_rate == 22050


def test_dependent_substreams_are_attached_to_their_access_unit() -> None:
    main, dependent = eac3_frame(), eac3_frame(strmtyp=1, size_words=40)
    parser = ac3.Ac3Parser()
    units = parser.frames(main + dependent + main + dependent + main)
    tail = parser.flush()
    assert [len(unit) for unit in units + tail] == [280, 280, 200]
    assert parser.config is not None
    assert parser.enhanced
    dec3 = find_box(parser.config.sample_entry, (b"dec3",), 36)
    assert dec3 is not None
    body = parser.config.sample_entry[dec3[0] + 8 : dec3[0] + dec3[1]]
    assert len(body) == 6  # a dependent substream adds the channel location field
    assert (body[4] >> 1) & 0xF == 1  # one dependent substream


def test_a_plain_dec3_has_no_dependent_substreams() -> None:
    parser = ac3.Ac3Parser()
    parser.frames(eac3_frame() + eac3_frame())
    assert parser.config is not None
    dec3 = find_box(parser.config.sample_entry, (b"dec3",), 36)
    assert dec3 is not None
    assert dec3[1] - 8 == 5  # no channel location field without a dependent substream


def test_dolby_frames_with_bad_headers_are_refused() -> None:
    data = ac3.SYNC + bytes(2) + bytes([0x3F, 0x40]) + bytes(40)  # frame size code 63
    with pytest.raises(OutputFormatError, match="invalid header"):
        ac3.parse_frame(data, 0)
    reserved_rate = ac3.SYNC + bytes(2) + bytes([0xC0, 0x40]) + bytes(40)  # fscod 3
    with pytest.raises(OutputFormatError, match="invalid header"):
        ac3.parse_frame(reserved_rate, 0)


def test_data_before_the_first_dolby_frame_is_skipped() -> None:
    parser = ac3.Ac3Parser()
    frames = [media("h264_ac3.ts")[0:0]]
    assert frames == [b""]
    assert parser.frames(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09") == []
