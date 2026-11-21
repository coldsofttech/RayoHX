from rayohx._mux import _mp3 as mp3
from rayohx._mux._mp4read import find_box
from tests.helpers.mux import stream_payloads


def mpeg_frame(header: int, size: int) -> bytes:
    return header.to_bytes(4, "big") + bytes(size - 4)


def test_mp3_frames_are_found_by_their_headers() -> None:
    header = 0xFFFB9004  # MPEG-1 layer 3, 128 kbit/s, 44.1 kHz, stereo
    parser = mp3.Mp3Parser()
    frames = parser.frames(mpeg_frame(header, 417) + mpeg_frame(header | 0x200, 418) + b"\x00\x00")
    assert [len(frame) for frame in frames] == [417, 418]
    assert parser.config is not None
    assert (parser.config.sample_rate, parser.config.channels) == (44100, 2)
    assert parser.samples_per_frame == 1152
    esds = find_box(parser.config.sample_entry, (b"esds",), 36)
    assert esds is not None
    assert bytes([0x6B, 0x15]) in parser.config.sample_entry


def test_mpeg2_layer3_has_shorter_frames() -> None:
    header = 0xFFF39004 & ~0xF000 | 0x8000  # MPEG-2 layer 3, 64 kbit/s at 22.05 kHz
    parser = mp3.Mp3Parser()
    expected = 72 * 64000 // 22050
    frames = parser.frames(mpeg_frame(header, expected) + mpeg_frame(header, expected))
    assert len(frames) == 2
    assert parser.samples_per_frame == 576
    assert parser.config is not None
    assert bytes([0x69, 0x15]) in parser.config.sample_entry


def test_a_real_mp3_stream_parses_completely() -> None:
    parser = mp3.Mp3Parser()
    frames = [
        frame
        for payload in stream_payloads("h264_mp3.ts", 0x03)
        for frame in parser.frames(payload)
    ]
    assert len(frames) == 155
    assert parser.flush() == []


def test_garbage_is_skipped_over() -> None:
    parser = mp3.Mp3Parser()
    header = 0xFFFB9004
    assert len(parser.frames(b"\x12\x34\x56" + mpeg_frame(header, 417))) == 1


def test_mpeg_audio_layers_one_and_two() -> None:
    layer2 = 0xFFFD9000  # MPEG-1 layer 2, bitrate index 9, 44.1 kHz
    parser = mp3.Mp3Parser()
    size = 144 * 160000 // 44100
    assert len(parser.frames(layer2.to_bytes(4, "big") + bytes(size - 4))) == 1
    assert parser.samples_per_frame == 1152
    layer1 = 0xFFFF9000
    first = mp3.Mp3Parser()
    expected = (12 * 288000 // 44100) * 4
    assert len(first.frames(layer1.to_bytes(4, "big") + bytes(expected - 4))) == 1
    assert first.samples_per_frame == 384


def test_invalid_mpeg_audio_headers_are_not_frames() -> None:
    for header in (0xFFE00000, 0xFFFB0000, 0xFFFBF000, 0xFFFB9C00, 0xFFEB9000):
        assert mp3._parse_header(header) is None
