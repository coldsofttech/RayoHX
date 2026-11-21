"""Facts about the MPEG-TS and fragmented MP4 formats that the checks share."""

TS_PACKET = 188
TS_SYNC = 0x47
#: Top-level boxes a media segment of fragmented MP4 may start with.
FMP4_SEGMENT_START = frozenset({b"styp", b"moof", b"sidx", b"emsg", b"prft", b"free", b"skip"})
FMP4_INIT_START = frozenset({b"ftyp", b"moov", b"styp"})


def looks_like_ts(data: bytes) -> bool:
    if not data or data[0] != TS_SYNC:
        return False
    # One packet is too little to be sure; with more data the next sync bytes must line up.
    return all(
        data[offset] == TS_SYNC
        for offset in range(TS_PACKET, min(len(data), 3 * TS_PACKET), TS_PACKET)
    )
