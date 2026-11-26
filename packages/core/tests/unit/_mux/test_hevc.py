import struct

import pytest
from rayohx_pytest.media import BitWriter, annexb, escape_nal

from rayohx._mux import _hevc as hevc
from rayohx._mux._mp4read import find_box
from rayohx.errors import OutputFormatError
from tests.helpers.mux import stream_payloads


def hevc_sps(*, sub_layers: int = 0, crop: bool = False, chroma: int = 1) -> bytes:
    writer = BitWriter().bits(0, 4).bits(sub_layers, 3).flag(True)
    writer.bits(0, 2).bits(0, 1).bits(1, 5).bits(0x60000000, 32).bits(0, 48).bits(93, 8)
    present = [(index % 2 == 0, index % 2 == 1) for index in range(sub_layers)]
    for profile, level in present:
        writer.flag(profile).flag(level)
    if sub_layers:
        writer.bits(0, 2 * (8 - sub_layers))
    for profile, level in present:
        if profile:
            writer.bits(0, 88)
        if level:
            writer.bits(0, 8)
    writer.ue(0).ue(chroma)
    if chroma == 3:
        writer.flag(False)
    writer.ue(1920).ue(1088).flag(crop)
    if crop:
        writer.ue(0).ue(0).ue(0).ue(4)
    writer.ue(2).ue(2)
    return bytes([0x42, 0x01]) + escape_nal(writer.to_bytes())


@pytest.mark.parametrize(
    ("kwargs", "size", "layers"),
    [
        ({}, (1920, 1088), 1),
        ({"crop": True}, (1920, 1080), 1),
        ({"sub_layers": 2}, (1920, 1088), 3),
        ({"sub_layers": 3, "crop": True, "chroma": 3}, (1920, 1084), 4),
    ],
)
def test_hevc_sequence_parameters_with_sub_layers_and_cropping(
    kwargs: dict[str, object], size: tuple[int, int], layers: int
) -> None:
    info = hevc.parse_sps(hevc_sps(**kwargs))  # type: ignore[arg-type]
    assert (info.width, info.height) == size
    assert info.temporal_layers == layers
    assert (info.bit_depth_luma, info.bit_depth_chroma) == (10, 10)
    assert info.profile == 1
    assert info.level == 93


def test_hevc_headers_that_leave_no_picture_are_refused() -> None:
    writer = BitWriter().bits(0, 4).bits(0, 3).flag(True).bits(0, 2).bits(0, 1).bits(1, 5)
    writer.bits(0, 32).bits(0, 48).bits(93, 8).ue(0).ue(1).ue(0).ue(0).flag(False).ue(0).ue(0)
    with pytest.raises(OutputFormatError, match="size could not be read"):
        hevc.parse_sps(bytes([0x42, 0x01]) + writer.to_bytes())


def test_the_real_hevc_headers_are_read() -> None:
    packets = stream_payloads("hevc_aac.ts", 0x24)
    units = hevc.HevcParser().access_units(packets[0])
    assert units[0] is not None
    parser = hevc.HevcParser()
    parser.access_units(packets[0])
    assert parser.config is not None
    assert (parser.config.width, parser.config.height) == (320, 240)
    assert parser.config.codec.startswith("hvc1.")
    box = find_box(parser.config.sample_entry, (b"hvcC",), 86)
    assert box is not None
    record = parser.config.sample_entry[box[0] + 8 : box[0] + box[1]]
    assert record[0] == 1
    assert record[21] & 3 == 3  # four-byte NAL lengths
    arrays = record[22]
    assert arrays == 3  # video, sequence and picture parameter sets


def test_hevc_keyframes_are_detected_and_parameter_sets_removed() -> None:
    packets = stream_payloads("hevc_aac.ts", 0x24)
    parser = hevc.HevcParser()
    flags = []
    for payload in packets[:12]:
        flags += [unit[1] for unit in parser.access_units(payload) if unit is not None]
    assert flags[0] is True
    assert flags.count(True) == 1
    sample = hevc.HevcParser().access_units(packets[0])[0]
    assert sample is not None
    data = sample[0]
    position = 0
    kinds = []
    while position < len(data):
        (length,) = struct.unpack_from(">I", data, position)
        kinds.append((data[position + 4] >> 1) & 0x3F)
        position += 4 + length
    assert not set(kinds) & {32, 33, 34, 35}


def test_a_stream_without_parameter_sets_never_gets_a_config() -> None:
    parser = hevc.HevcParser()
    assert parser.access_units(annexb(bytes([0x02, 0x01, 0xAA, 0xBB]))) == [None]
    assert parser.config is None
