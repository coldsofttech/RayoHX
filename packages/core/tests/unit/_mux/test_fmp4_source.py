import struct
from pathlib import Path

import pytest

from rayohx._mux._boxes import box
from rayohx._mux._fmp4 import build_init_ordered
from rayohx._mux._fmp4_source import (
    Fmp4Source,
    _fragment_times,
    _rescale_edit_list,
    _set_tfdt,
    _trex_defaults,
)
from rayohx._mux._mp4read import find_box, iter_boxes
from rayohx._mux._muxer import Mp4Muxer
from rayohx.errors import FinalizationError, UnsupportedCodecError
from tests.helpers.mux import MEDIA, config, read_fragments, top_level

HLS = MEDIA / "hls_fmp4"


def piece(name: str) -> bytes:
    return (HLS / name).read_bytes()


VIDEO = (piece("init_0.mp4"), [piece("v0_0.m4s"), piece("v0_1.m4s")])
AUDIO = (piece("init_1.mp4"), [piece("v1_0.m4s"), piece("v1_1.m4s"), piece("v1_2.m4s")])


def join(
    *sources: tuple[bytes, list[bytes]], chunk: int | None = None, language: str | None = None
) -> bytes:
    out = bytearray()
    muxer = Mp4Muxer(out.extend)
    feeders = [Fmp4Source(muxer, language=language if i else None) for i, _ in enumerate(sources)]

    def push(feeder: Fmp4Source, data: bytes) -> None:
        if chunk is None:
            feeder.feed(data)
            return
        for start in range(0, len(data), chunk):
            feeder.feed(data[start : start + chunk])

    for feeder, (init, _) in zip(feeders, sources, strict=True):
        push(feeder, init)  # every stream names its tracks before any media is written
    for feeder, (_, segments) in zip(feeders, sources, strict=True):
        for segment in segments:
            push(feeder, segment)
    for feeder in feeders:
        feeder.finish()
    muxer.close()
    return bytes(out)


def moofs(data: bytes) -> int:
    return top_level(data).count(b"moof")


def test_one_track_is_passed_through_fragment_for_fragment() -> None:
    data = join(VIDEO)
    assert top_level(data)[:2] == [b"ftyp", b"moov"]
    assert moofs(data) == sum(top_level(seg).count(b"moof") for seg in VIDEO[1])
    fragments = read_fragments(data)
    assert [f["sequence"] for f in fragments] == list(range(1, len(fragments) + 1))
    assert {f["track"] for f in fragments} == {1}
    assert fragments[0]["start"] == 0  # the output starts at zero


def test_the_compressed_data_is_not_touched() -> None:
    data = join(VIDEO)
    source_mdats = [
        bytes(seg[o : o + s]) for seg in VIDEO[1] for k, o, s, _ in iter_boxes(seg) if k == b"mdat"
    ]
    output_mdats = [bytes(data[o : o + s]) for k, o, s, _ in iter_boxes(data) if k == b"mdat"]
    assert output_mdats == source_mdats


def test_the_result_does_not_depend_on_how_the_data_is_cut() -> None:
    assert join(VIDEO, chunk=100) == join(VIDEO)
    assert join(VIDEO, AUDIO, chunk=777) == join(VIDEO, AUDIO)


def test_two_renditions_become_two_tracks_in_time_order() -> None:
    data = join(VIDEO, AUDIO, language="fr")
    fragments = read_fragments(data)
    assert {f["track"] for f in fragments} == {1, 2}
    # Fragments come out in time order, each track's own order unchanged.
    seconds = [int(str(f["start"])) / (90000 if f["track"] == 1 else 44100) for f in fragments]
    assert seconds == sorted(seconds)
    moov = find_box(data, (b"moov",))
    assert moov is not None
    kinds = []
    for kind, offset, size, _ in iter_boxes(data, moov[0] + 8, moov[0] + moov[1]):
        if kind == b"trak":
            hdlr = find_box(data[offset : offset + size], (b"mdia", b"hdlr"), 8)
            assert hdlr is not None
            kinds.append(data[offset + hdlr[0] + 16 : offset + hdlr[0] + 20])
    assert kinds == [b"vide", b"soun"]  # video first, though audio was added first below


def test_video_is_listed_first_even_when_the_audio_was_added_first() -> None:
    out = bytearray()
    muxer = Mp4Muxer(out.extend)
    audio, video = Fmp4Source(muxer, language="en"), Fmp4Source(muxer)
    audio.feed(AUDIO[0])
    video.feed(VIDEO[0])
    for segment in VIDEO[1]:
        video.feed(segment)
    for segment in AUDIO[1]:
        audio.feed(segment)
    audio.finish()
    video.finish()
    muxer.close()
    first_track = find_box(bytes(out), (b"moov", b"trak", b"mdia", b"hdlr"), 0)
    assert first_track is not None
    assert bytes(out[first_track[0] + 16 : first_track[0] + 20]) == b"vide"


def test_the_language_is_written_into_the_copied_track() -> None:
    data = join(VIDEO, AUDIO, language="fr")
    mdhd_boxes = []
    moov = find_box(data, (b"moov",))
    assert moov is not None
    for kind, offset, size, _ in iter_boxes(data, moov[0] + 8, moov[0] + moov[1]):
        if kind == b"trak":
            mdhd = find_box(data[offset : offset + size], (b"mdia", b"mdhd"), 8)
            assert mdhd is not None
            mdhd_boxes.append(struct.unpack_from(">H", data, offset + mdhd[0] + 28)[0])
    packed = mdhd_boxes[1]
    assert "".join(chr(((packed >> shift) & 0x1F) + 0x60) for shift in (10, 5, 0)) == "fra"


def test_a_repeated_initialization_section_is_ignored() -> None:
    out = bytearray()
    muxer = Mp4Muxer(out.extend)
    source = Fmp4Source(muxer)
    source.feed(VIDEO[0])
    source.feed(VIDEO[0] + VIDEO[1][0])
    source.feed(VIDEO[0] + VIDEO[1][1])
    source.finish()
    muxer.close()
    assert out.count(b"moov") == 1


def test_a_different_initialization_section_part_way_through_is_refused() -> None:
    muxer = Mp4Muxer(lambda data: None)
    source = Fmp4Source(muxer)
    source.feed(VIDEO[0])
    with pytest.raises(FinalizationError, match="changed its tracks"):
        source.feed(AUDIO[0])


def test_several_tracks_in_one_stream_are_not_supported() -> None:
    init = build_init_ordered(
        [type("T", (), {"track_id": 1, "config": config("video"), "raw": None})(),
         type("T", (), {"track_id": 2, "config": config("audio"), "raw": None})()]
    )  # fmt: skip
    source = Fmp4Source(Mp4Muxer(lambda data: None))
    with pytest.raises(UnsupportedCodecError, match="several tracks"):
        source.feed(init)


def test_fragments_before_the_initialization_section_are_dropped() -> None:
    out = bytearray()
    muxer = Mp4Muxer(out.extend)
    source = Fmp4Source(muxer)
    source.feed(VIDEO[1][0])
    source.feed(VIDEO[0])
    source.feed(VIDEO[1][1])
    source.finish()
    muxer.close()
    assert moofs(bytes(out)) == top_level(VIDEO[1][1]).count(b"moof")


def set_decode_time(segment: bytes, value: int) -> bytes:
    data = bytearray(segment)
    tfdt = find_box(data, (b"moof", b"traf", b"tfdt"), 0)
    assert tfdt is not None
    assert data[tfdt[0] + 8] == 1
    struct.pack_into(">Q", data, tfdt[0] + 12, value)
    return bytes(data)


def test_a_jump_in_decode_time_is_closed_up() -> None:
    expected = read_fragments(join(VIDEO))[1]["start"]
    jumped = (VIDEO[0], [VIDEO[1][0], set_decode_time(VIDEO[1][1], 500 * 90000)])
    fragments = read_fragments(join(jumped))
    assert fragments[1]["start"] == expected  # continues where the first fragment ended


def test_boxes_that_are_not_media_are_skipped() -> None:
    from tests.helpers.media import box

    padded = box(b"emsg", b"x" * 12) + VIDEO[1][0] + box(b"free", b"y" * 5) + box(b"prft", bytes(8))
    out = join((VIDEO[0], [padded]))
    assert moofs(out) == top_level(VIDEO[1][0]).count(b"moof")


def test_files_can_be_used_without_a_directory_listing(tmp_path: Path) -> None:
    (tmp_path / "x.mp4").write_bytes(VIDEO[0])
    assert (tmp_path / "x.mp4").stat().st_size == len(VIDEO[0])


# --- fragments from other packagers -----------------------------------------------------------


def trun(count: int, *, flags: int, per_sample: bytes = b"", extra: bytes = b"") -> bytes:
    body = struct.pack(">I", (0 << 24) | flags) + struct.pack(">I", count) + extra + per_sample
    return box(b"trun", body)


def fragment_with(*traf_children: bytes) -> bytes:
    return box(b"moof", box(b"mfhd", bytes(8)), box(b"traf", *traf_children)) + box(
        b"mdat", b"data"
    )


def test_sample_durations_come_from_the_trun_when_it_lists_them() -> None:
    entries = b"".join(struct.pack(">II", duration, 10) for duration in (40, 40, 50))
    tfdt = box(b"tfdt", struct.pack(">II", 0, 1234))
    fragment = fragment_with(tfdt, trun(3, flags=0x300, per_sample=entries))
    assert _fragment_times(fragment, 99) == (1234, 130)


def test_sample_durations_fall_back_to_the_track_defaults() -> None:
    tfdt = box(b"tfdt", struct.pack(">II", 0, 0))
    plain = fragment_with(tfdt, trun(4, flags=0x200, per_sample=b"\x00" * 16))
    assert _fragment_times(plain, 25) == (0, 100)
    # tfhd with its own default duration (flag 0x8) wins over the track default.
    tfhd = box(b"tfhd", struct.pack(">II", 0x8, 1) + struct.pack(">I", 40))
    own = fragment_with(tfhd, tfdt, trun(2, flags=0x200, per_sample=bytes(8)))
    assert _fragment_times(own, 25) == (0, 80)
    # tfhd flags that insert other fields before the duration are skipped over correctly.
    skewed = box(
        b"tfhd",
        struct.pack(">II", 0x1 | 0x2 | 0x8, 1) + struct.pack(">QII", 0, 1, 60),
    )
    other = fragment_with(skewed, tfdt, trun(2, flags=0x200, per_sample=bytes(8)))
    assert _fragment_times(other, 25) == (0, 120)


def test_a_data_offset_and_first_sample_flags_do_not_confuse_the_duration() -> None:
    extra = struct.pack(">iI", 100, 0)
    entries = struct.pack(">II", 33, 10) + struct.pack(">II", 34, 10)
    fragment = fragment_with(trun(2, flags=0x305, per_sample=entries, extra=extra))
    assert _fragment_times(fragment, 0) == (None, 67)


def test_a_fragment_without_a_decode_time_or_traf_is_tolerated() -> None:
    assert _fragment_times(box(b"moof", box(b"mfhd", bytes(8))) + box(b"mdat", b""), 0) == (None, 0)
    assert _fragment_times(b"not a fragment", 0) == (None, 0)
    assert _set_tfdt(b"not a fragment", 5) == b"not a fragment"
    no_tfdt = fragment_with(trun(1, flags=0x200, per_sample=bytes(4)))
    assert _set_tfdt(no_tfdt, 5) == no_tfdt


def test_a_version_zero_decode_time_is_rewritten() -> None:
    fragment = fragment_with(box(b"tfdt", struct.pack(">II", 0, 1000)))
    patched = _set_tfdt(fragment, 70)
    tfdt = find_box(patched, (b"moof", b"traf", b"tfdt"))
    assert tfdt is not None
    assert struct.unpack_from(">I", patched, tfdt[0] + 12)[0] == 70


def test_track_defaults_are_read_from_the_trex_box() -> None:
    trex = box(b"trex", struct.pack(">IIIIII", 0, 7, 1, 1024, 0, 0x10000))
    moov = box(b"moov", box(b"mvex", trex))
    assert _trex_defaults(moov, 7) == (1, 1024, 0, 0x10000)
    assert _trex_defaults(moov, 8) == (1, 0, 0, 0)
    assert _trex_defaults(box(b"moov"), 1) == (1, 0, 0, 0)


@pytest.mark.parametrize("version", [0, 1])
def test_edit_lists_are_rescaled_to_the_output_movie_clock(version: int) -> None:
    if version == 1:
        entry = struct.pack(">QqHH", 90000, 0, 1, 0)
    else:
        entry = struct.pack(">IiHH", 90000, 0, 1, 0)
    elst = box(b"elst", struct.pack(">I", version << 24) + struct.pack(">I", 1) + entry)
    trak = bytearray(box(b"trak", box(b"edts", elst)))
    _rescale_edit_list(trak, 90000)
    found = find_box(trak, (b"edts", b"elst"), 8)
    assert found is not None
    fmt = ">Q" if version else ">I"
    assert struct.unpack_from(fmt, trak, found[0] + 16)[0] == 1000
    unchanged = bytearray(box(b"trak", box(b"edts", elst)))
    _rescale_edit_list(unchanged, 1000)
    assert unchanged == bytearray(box(b"trak", box(b"edts", elst)))
    _rescale_edit_list(bytearray(box(b"trak")), 90000)  # no edit list: nothing happens


def test_a_stream_without_track_data_cannot_be_copied() -> None:
    with pytest.raises(FinalizationError, match="incomplete"):
        Fmp4Source(Mp4Muxer(lambda data: None)).feed(
            box(b"moov", box(b"mvhd", bytes(100)), box(b"trak", box(b"free")))
        )
