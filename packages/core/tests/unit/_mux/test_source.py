import pytest
from rayohx_pytest.media import pat, pmt, stream
from rayohx_pytest.site import media

from rayohx._mux import _h264 as h264
from rayohx._mux import _ts as ts
from rayohx._mux._muxer import Mp4Muxer
from rayohx._mux._source import TsSource, classify, probe_codecs
from rayohx._mux._ts import TsDemuxer, TsStream
from rayohx.errors import UnsupportedCodecError
from tests.helpers.mux import stream_payloads


def streams_in(data: bytes) -> list[TsStream]:
    found: list[TsStream] = []
    demuxer = TsDemuxer(lambda packet, listed: None, found.extend)
    demuxer.feed(data)
    demuxer.flush()
    return found


def test_private_streams_carrying_dolby_audio_are_recognised() -> None:
    streams = streams_in(
        pat()
        + pmt(
            [
                stream(ts.STREAM_PRIVATE, 0x101, bytes([ts.DESCRIPTOR_AC3, 1, 0])),
                stream(ts.STREAM_PRIVATE, 0x102, bytes([ts.DESCRIPTOR_EAC3, 1, 0])),
                stream(ts.STREAM_PRIVATE, 0x103, bytes([0x59, 0])),
                stream(0x15, 0x104),
            ]
        )
    )
    assert [classify(s) for s in streams] == ["ac3", "eac3", "ignore", "ignore"]
    assert streams[0].has_descriptor(ts.DESCRIPTOR_AC3)
    assert not streams[0].has_descriptor(ts.DESCRIPTOR_EAC3)


@pytest.mark.parametrize(
    ("kind", "name"),
    [(0x02, "MPEG-2 video"), (0x82, "DTS audio"), (0xEA, "VC-1 video"), (0x99, "stream type 0x99")],
)
def test_codecs_that_cannot_be_copied_are_named(kind: int, name: str) -> None:
    data = pat() + pmt([stream(kind, 0x101)])
    with pytest.raises(UnsupportedCodecError, match=name) as info:
        probe_codecs(data)
    assert info.value.codec == name
    assert info.value.hint


def test_probing_lists_the_codecs() -> None:
    assert probe_codecs(media("h264_aac.ts")) == ["h264", "aac"]
    assert probe_codecs(media("hevc_aac.ts")) == ["hevc", "aac"]
    assert probe_codecs(media("h264_eac3.ts")) == ["h264", "eac3"]
    assert probe_codecs(media("aac_only.ts")) == ["aac"]


def test_leading_frames_that_cannot_be_decoded_are_dropped() -> None:
    packets = stream_payloads("h264_only.ts", 0x1B)
    start = next(
        i for i, p in enumerate(packets) if h264.H264Parser().access_units(p)[0] is not None
    )
    assert start == 0
    out = bytearray()
    muxer = Mp4Muxer(out.extend)
    source = TsSource(muxer)
    source.feed(media("h264_only.ts"))
    source.finish()
    muxer.close()
    assert out[4:8] == b"ftyp"
