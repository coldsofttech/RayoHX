"""Helpers for the muxer tests that need the engine's own muxer and demuxer.

The real fixtures, the synthetic MPEG-TS builders and the FFmpeg oracle live in ``rayohx_pytest``.
"""

from rayohx_pytest.site import media

from rayohx._mux._model import Sample, TrackConfig
from rayohx._mux._mp4read import iter_boxes
from rayohx._mux._muxer import Mp4Muxer
from rayohx._mux._source import TsSource
from rayohx._mux._ts import TsDemuxer


def mux_ts(data: bytes, chunk: int = 50_000) -> tuple[bytes, Mp4Muxer]:
    """Remux transport stream data into a fragmented MP4, fed in pieces of ``chunk`` bytes."""
    output = bytearray()
    muxer = Mp4Muxer(output.extend)
    source = TsSource(muxer)
    for start in range(0, len(data), chunk):
        source.feed(data[start : start + chunk])
    source.finish()
    muxer.close()
    return bytes(output), muxer


def top_level(data: bytes) -> list[bytes]:
    """The types of the top-level boxes of an MP4."""
    return [kind for kind, _, _, _ in iter_boxes(data)]


def config(kind: str = "video") -> TrackConfig:
    """A minimal track description for tests that do not look inside it."""
    return TrackConfig(kind, 1000, b"\x00\x00\x00\x08test", "test", width=16, height=16)


# --- reading MP4 files back --------------------------------------------------------------------


def read_fragments(data: bytes) -> list[dict[str, int | list[int]]]:
    """Each ``moof`` of an MP4 as a dictionary: track, sequence, decode time and sample facts."""
    import struct

    from rayohx._mux._mp4read import find_box

    found: list[dict[str, int | list[int]]] = []
    for kind, offset, size, _ in iter_boxes(data):
        if kind != b"moof":
            continue
        mfhd = find_box(data, (b"mfhd",), offset + 8, offset + size)
        traf = find_box(data, (b"traf",), offset + 8, offset + size)
        assert mfhd is not None
        assert traf is not None
        inner = (traf[0] + 8, traf[0] + traf[1])
        tfhd = find_box(data, (b"tfhd",), *inner)
        tfdt = find_box(data, (b"tfdt",), *inner)
        trun = find_box(data, (b"trun",), *inner)
        assert tfhd is not None
        assert tfdt is not None
        assert trun is not None
        version = data[tfdt[0] + 8]
        base = struct.unpack_from(">Q" if version else ">I", data, tfdt[0] + 12)[0]
        count = struct.unpack_from(">I", data, trun[0] + 12)[0]
        entries = trun[0] + 20
        durations = [
            struct.unpack_from(">I", data, entries + index * 16)[0] for index in range(count)
        ]
        found.append(
            {
                "track": struct.unpack_from(">I", data, tfhd[0] + 12)[0],
                "sequence": struct.unpack_from(">I", data, mfhd[0] + 12)[0],
                "start": base,
                "count": count,
                "durations": durations,
                "moof_offset": offset,
                "data_offset": struct.unpack_from(">i", data, trun[0] + 16)[0],
            }
        )
    return found


# --- builders shared by the per-module tests ---------------------------------------------------


def stream_payloads(name: str, stream_type: int) -> list[bytes]:
    """The PES payloads of one stream type in a fixture, in order."""
    payloads: list[bytes] = []
    demuxer = TsDemuxer(
        lambda p, s: payloads.append(p.payload) if s.stream_type == stream_type else None
    )
    demuxer.feed(media(name))
    demuxer.flush()
    return payloads


def samples(count: int = 3, *, start: int = 1000) -> list[Sample]:
    """``count`` samples of 40 ticks each, the first one a keyframe."""
    return [
        Sample(
            data=bytes([index]) * (10 + index),
            dts=start + index * 40,
            duration=40,
            cts_offset=index * 3 - 3,
            sync=index == 0,
        )
        for index in range(count)
    ]
