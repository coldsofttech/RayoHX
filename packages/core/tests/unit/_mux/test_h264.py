import struct

import pytest

from rayohx._mux import _h264 as h264
from rayohx._mux._mp4read import find_box
from rayohx.errors import OutputFormatError
from tests.helpers.mux import BitWriter, annexb, escape_nal, stream_payloads

HIGH = 100


def sps_nal(
    profile: int = 66,
    width_mbs: int = 20,
    height_units: int = 15,
    *,
    frame_mbs_only: bool = True,
    crop: tuple[int, int, int, int] = (0, 0, 0, 0),
    chroma: int = 1,
    scaling: bool = False,
) -> bytes:
    writer = BitWriter().bits(profile, 8).bits(0, 8).bits(30, 8).ue(0)
    if profile == HIGH:
        writer.ue(chroma)
        if chroma == 3:
            writer.flag(False)
        writer.ue(0).ue(0).flag(False).flag(scaling)
        if scaling:
            for index in range(8 if chroma != 3 else 12):
                writer.flag(index == 0)
                if index == 0:
                    writer.se(-8)  # "use the default list": ends the list at once
    writer.ue(0).ue(0).ue(0).ue(1).flag(False)
    writer.ue(width_mbs - 1).ue(height_units - 1).flag(frame_mbs_only)
    if not frame_mbs_only:
        writer.flag(False)
    writer.flag(True).flag(any(crop))
    if any(crop):
        for value in crop:
            writer.ue(value)
    writer.flag(False)
    return bytes([0x67]) + escape_nal(writer.to_bytes())


PPS = bytes([0x68, 0xCE, 0x38, 0x80])
IDR = bytes([0x65, 0x88, 0x84, 0x00, 0x10])
SLICE = bytes([0x41, 0x9A, 0x24, 0x6C])
AUD = bytes([0x09, 0xF0])
SEI = bytes([0x06, 0x05, 0x01, 0x80])


def test_nal_units_are_split_on_either_start_code() -> None:
    data = b"\x00\x00\x00\x01" + SLICE + b"\x00\x00\x01" + IDR + b"\x00\x00\x00\x00\x01" + AUD
    assert h264.split_nal_units(data) == [SLICE, IDR, AUD]
    assert h264.split_nal_units(b"no start codes") == []
    assert h264.split_nal_units(b"") == []


@pytest.mark.parametrize(
    ("kwargs", "size"),
    [
        ({}, (320, 240)),
        ({"width_mbs": 120, "height_units": 68, "crop": (0, 0, 0, 4)}, (1920, 1080)),
        ({"width_mbs": 80, "height_units": 45, "profile": HIGH}, (1280, 720)),
        (
            {"width_mbs": 80, "height_units": 23, "frame_mbs_only": False, "crop": (0, 0, 0, 4)},
            (1280, 720),
        ),
        ({"width_mbs": 45, "height_units": 80, "crop": (2, 2, 0, 0)}, (712, 1280)),
        ({"profile": HIGH, "scaling": True, "width_mbs": 40, "height_units": 30}, (640, 480)),
        ({"profile": HIGH, "chroma": 3, "scaling": True, "crop": (2, 0, 0, 0)}, (318, 240)),
        ({"profile": HIGH, "chroma": 0}, (320, 240)),
    ],
)
def test_the_picture_size_comes_from_the_sequence_parameters(
    kwargs: dict[str, object], size: tuple[int, int]
) -> None:
    info = h264.parse_sps(sps_nal(**kwargs))  # type: ignore[arg-type]
    assert (info.width, info.height) == size


def test_the_real_files_sequence_parameters_are_read() -> None:
    packets = stream_payloads("h264_aac.ts", 0x1B)
    unit = next(u for u in h264.split_nal_units(packets[0]) if u[0] & 0x1F == 7)
    info = h264.parse_sps(unit)
    assert (info.width, info.height, info.profile) == (320, 240, 100)
    assert (info.chroma_format, info.bit_depth_luma) == (1, 8)


def test_a_cut_off_parameter_set_is_an_error() -> None:
    with pytest.raises(OutputFormatError):
        h264.parse_sps(sps_nal()[:4])


def test_parameter_sets_move_to_the_sample_entry_and_out_of_the_samples() -> None:
    parser = h264.H264Parser()
    sps = sps_nal()
    units = parser.access_units(annexb(AUD, sps, PPS, SEI, IDR))
    assert len(units) == 1
    data, keyframe = units[0]  # type: ignore[misc]
    assert keyframe
    assert data == struct.pack(">I", len(SEI)) + SEI + struct.pack(">I", len(IDR)) + IDR
    assert parser.config is not None
    assert (parser.config.width, parser.config.height) == (320, 240)
    assert parser.config.codec == "avc1.42001e"
    avc_c = find_box(parser.config.sample_entry, (b"avcC",), 86)
    assert avc_c is not None
    record = parser.config.sample_entry[avc_c[0] + 8 : avc_c[0] + avc_c[1]]
    assert record[:5] == bytes([1, 66, 0, 30, 0xFF])
    assert record[5] == 0xE1
    assert record[6:8] == struct.pack(">H", len(sps))
    assert sps in record
    assert PPS in record


def test_samples_before_the_first_parameter_sets_are_skipped() -> None:
    parser = h264.H264Parser()
    assert parser.access_units(annexb(AUD, SLICE)) == [None]
    assert parser.config is None
    units = parser.access_units(annexb(AUD, sps_nal(), PPS, IDR))
    assert units[0] is not None
    follow = parser.access_units(annexb(AUD, SLICE))
    assert follow == [(struct.pack(">I", len(SLICE)) + SLICE, False)]


def test_several_access_units_in_one_payload_are_separated() -> None:
    parser = h264.H264Parser()
    units = parser.access_units(annexb(AUD, sps_nal(), PPS, IDR, AUD, SLICE, AUD, SLICE))
    assert [u[1] for u in units if u is not None] == [True, False, False]


def test_repeated_parameter_sets_are_stored_once() -> None:
    parser = h264.H264Parser()
    sps = sps_nal()
    parser.access_units(annexb(AUD, sps, PPS, IDR))
    parser.access_units(annexb(AUD, sps, PPS, SLICE))
    assert parser.config is not None
    assert parser.config.sample_entry.count(sps) == 1


def test_high_profiles_get_the_extra_avcc_fields() -> None:
    parser = h264.H264Parser()
    parser.access_units(annexb(AUD, sps_nal(profile=HIGH), PPS, IDR))
    assert parser.config is not None
    avc_c = find_box(parser.config.sample_entry, (b"avcC",), 86)
    assert avc_c is not None
    record = parser.config.sample_entry[avc_c[0] + 8 : avc_c[0] + avc_c[1]]
    assert record[-4:] == bytes([0xFD, 0xF8, 0xF8, 0])


def test_filler_and_delimiters_are_dropped() -> None:
    parser = h264.H264Parser()
    filler = bytes([0x0C, 0xFF, 0xFF])
    end_of_sequence = bytes([0x0A])
    units = parser.access_units(annexb(AUD, sps_nal(), PPS, IDR, filler, end_of_sequence))
    assert units[0] == (struct.pack(">I", len(IDR)) + IDR, True)
