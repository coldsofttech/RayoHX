"""Small media builders for the command line tests."""


def ts_payload(index: int, packets: int = 3) -> bytes:
    """MPEG-TS packets (188 bytes each, starting with the 0x47 sync byte)."""
    return b"".join(
        b"\x47" + bytes([(index + number) % 256]) + bytes(186) for number in range(packets)
    )
