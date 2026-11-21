import struct

import pytest

from rayohx._mux import _aac as aac
from rayohx._mux._mp4read import find_box
from rayohx.errors import OutputFormatError
from tests.helpers.mux import stream_payloads


def adts(
    payload: bytes, *, rate_index: int = 4, channels: int = 2, profile: int = 2, crc: bool = False
) -> bytes:
    header_size = 9 if crc else 7
    length = header_size + len(payload)
    header = bytes(
        [
            0xFF,
            0xF0 | (0 if crc else 1),
            ((profile - 1) << 6) | (rate_index << 2) | (channels >> 2),
            ((channels & 3) << 6) | (length >> 11),
            (length >> 3) & 0xFF,
            ((length & 7) << 5) | 0x1F,
            0xFC,
        ]
    )
    return header + (b"\x00\x00" if crc else b"") + payload


def test_adts_frames_are_split_and_the_config_is_built() -> None:
    parser = aac.AacParser()
    frames = parser.frames(adts(b"A" * 10) + adts(b"B" * 20))
    assert frames == [b"A" * 10, b"B" * 20]
    config = parser.config
    assert config is not None
    assert (config.timescale, config.channels, config.sample_rate) == (44100, 2, 44100)
    assert config.codec == "mp4a.40.2"
    esds = find_box(config.sample_entry, (b"esds",), 36)
    assert esds is not None
    body = config.sample_entry[esds[0] : esds[0] + esds[1]]
    assert struct.pack(">H", (2 << 11) | (4 << 7) | (2 << 3)) in body  # the AudioSpecificConfig
    assert bytes([0x40, 0x15]) in body  # MPEG-4 audio


def test_frames_cut_across_payloads_are_put_back_together() -> None:
    stream = adts(b"A" * 100) + adts(b"B" * 100) + adts(b"C" * 100)
    parser = aac.AacParser()
    found = []
    for start in range(0, len(stream), 37):
        found += parser.frames(stream[start : start + 37])
    assert found == [b"A" * 100, b"B" * 100, b"C" * 100]


def test_frames_with_a_crc_and_junk_between_them() -> None:
    parser = aac.AacParser()
    frames = parser.frames(b"\x00\x01" + adts(b"A" * 8, crc=True) + b"junk" + adts(b"B" * 8))
    assert frames == [b"A" * 8, b"B" * 8]


@pytest.mark.parametrize(
    ("rate_index", "rate"), [(0, 96000), (3, 48000), (4, 44100), (8, 16000), (11, 8000)]
)
def test_all_common_sampling_rates(rate_index: int, rate: int) -> None:
    parser = aac.AacParser()
    parser.frames(adts(b"x" * 5, rate_index=rate_index))
    assert parser.config is not None
    assert parser.config.sample_rate == rate


def test_unusual_aac_is_refused() -> None:
    with pytest.raises(OutputFormatError, match="sampling rate"):
        aac.AacParser().frames(adts(b"x" * 5, rate_index=14))
    with pytest.raises(OutputFormatError, match="channel layout"):
        aac.AacParser().frames(adts(b"x" * 5, channels=0))


def test_aac_samples_follow_each_other() -> None:
    samples = aac.audio_samples([b"a", b"b", b"c"], 1000, 1024)
    assert [(s.dts, s.duration) for s in samples] == [(1000, 1024), (2024, 1024), (3048, 1024)]


def test_the_real_aac_stream_parses_completely() -> None:
    parser = aac.AacParser()
    frames = [
        frame
        for payload in stream_payloads("aac_only.ts", 0x0F)
        for frame in parser.frames(payload)
    ]
    assert len(frames) == 174
    assert parser.flush() == []
