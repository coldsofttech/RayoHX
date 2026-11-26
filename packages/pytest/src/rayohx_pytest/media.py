"""Stream bytes for tests: segments, MP4 boxes, MPEG-TS packets and bit-packed headers."""

import struct

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def ts_payload(index: int, packets: int = 3) -> bytes:
    """MPEG-TS packets (188 bytes each, starting with the 0x47 sync byte)."""
    return b"".join(
        b"\x47" + bytes([(index + number) % 256]) + bytes(186) for number in range(packets)
    )


def payload(index: int, size: int = 500) -> bytes:
    """Deterministic, recognisable bytes for segment ``index``."""
    return bytes((index * 31 + offset * 7) % 251 for offset in range(size))


def encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC with PKCS#7 padding, as HLS does."""
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    # HLS defines AES-128 segments as plain CBC, so a test stream must be built that way: GCM is not
    # an option. This only makes test data and protects nothing.
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()  # nosemgrep
    return encryptor.update(padded) + encryptor.finalize()


# --- fragmented MP4 ----------------------------------------------------------------------------


def box(kind: bytes, body: bytes = b"") -> bytes:
    """An MP4 box: a 4-byte size, a 4-byte type, then the body."""
    return struct.pack(">I4s", 8 + len(body), kind) + body


def fmp4_init() -> bytes:
    """A minimal fragmented-MP4 initialization section."""
    return box(b"ftyp", b"iso5\x00\x00\x00\x01iso5") + box(b"moov", box(b"mvhd", bytes(20)))


def fmp4_fragment(index: int, size: int = 100) -> bytes:
    """A movie fragment: a ``moof`` box followed by its ``mdat`` box."""
    return box(b"moof", box(b"mfhd", struct.pack(">II", 0, index + 1))) + box(
        b"mdat", bytes([index % 251]) * size
    )


# --- a bit writer for hand-made headers --------------------------------------------------------


class BitWriter:
    """Builds bit-packed data, for crafting video headers."""

    def __init__(self) -> None:
        self._bits = ""

    def bits(self, value: int, count: int) -> "BitWriter":
        self._bits += format(value, f"0{count}b") if count else ""
        return self

    def flag(self, value: bool) -> "BitWriter":
        return self.bits(int(value), 1)

    def ue(self, value: int) -> "BitWriter":
        number = value + 1
        length = number.bit_length()
        self._bits += "0" * (length - 1) + format(number, "b")
        return self

    def se(self, value: int) -> "BitWriter":
        return self.ue(2 * value - 1 if value > 0 else -2 * value)

    def to_bytes(self, *, trailing: bool = True) -> bytes:
        bits = self._bits + ("1" if trailing else "")
        bits += "0" * (-len(bits) % 8)
        return int(bits, 2).to_bytes(len(bits) // 8, "big") if bits else b""


def escape_nal(data: bytes) -> bytes:
    """Insert emulation-prevention bytes, as an encoder does."""
    out = bytearray()
    zeros = 0
    for byte in data:
        if zeros >= 2 and byte <= 3:
            out.append(3)
            zeros = 0
        out.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(out)


def annexb(*units: bytes, long: bool = False) -> bytes:
    """NAL units joined with Annex B start codes."""
    start = b"\x00\x00\x00\x01" if long else b"\x00\x00\x01"
    return b"".join(start + unit for unit in units)


# --- a synthetic MPEG-TS builder ---------------------------------------------------------------


def _timestamp(marker: int, value: int) -> bytes:
    return bytes(
        [
            (marker << 4) | (((value >> 30) & 7) << 1) | 1,
            (value >> 22) & 0xFF,
            (((value >> 15) & 0x7F) << 1) | 1,
            (value >> 7) & 0xFF,
            ((value & 0x7F) << 1) | 1,
        ]
    )


def pes(stream_id: int, payload: bytes, pts: int | None, dts: int | None = None) -> bytes:
    """A PES packet with optional timestamps (in 90 kHz ticks)."""
    flags = 0
    header = b""
    if pts is not None:
        flags = 0x80
        header = _timestamp(3 if dts is not None else 2, pts)
        if dts is not None:
            flags = 0xC0
            header += _timestamp(1, dts)
    return (
        b"\x00\x00\x01"
        + bytes([stream_id])
        + b"\x00\x00"
        + bytes([0x80, flags, len(header)])
        + header
        + payload
    )


def ts_packets(pid: int, payload: bytes, *, start: bool = True, counter: int = 0) -> bytes:
    """Cut ``payload`` into 188-byte transport packets, padding the last with stuffing."""
    packets = bytearray()
    position = 0
    first = start
    while position < len(payload) or first:
        room = 184
        chunk = payload[position : position + room]
        position += len(chunk)
        header = bytes([0x47, (0x40 if first else 0) | (pid >> 8), pid & 0xFF])
        if len(chunk) < room:
            stuffing = room - len(chunk)
            adaptation = (
                bytes([0x30 | (counter & 0xF)])
                + bytes([stuffing - 1])
                + (b"\x00" + b"\xff" * (stuffing - 2) if stuffing >= 2 else b"")
            )
            packets += header + adaptation + chunk
        else:
            packets += header + bytes([0x10 | (counter & 0xF)]) + chunk
        counter += 1
        first = False
    return bytes(packets)


def pat(program: int = 1, pmt_pid: int = 0x100) -> bytes:
    """A program association table packet."""
    body = (
        bytes([0x00, 0x01, 0xC1, 0x00, 0x00])
        + program.to_bytes(2, "big")
        + bytes([0xE0 | (pmt_pid >> 8), pmt_pid & 0xFF])
    )
    section = bytes([0x00, 0xB0, len(body) + 4]) + body + b"\x00\x00\x00\x00"
    return ts_packets(0, b"\x00" + section)


def pmt(streams: list[tuple[int, int, bytes]], pmt_pid: int = 0x100, program: int = 1) -> bytes:
    """A program map table packet. Each stream is ``(stream_type, pid, descriptors)``."""
    loop = b"".join(
        bytes([kind, 0xE0 | (pid >> 8), pid & 0xFF, 0xF0 | (len(desc) >> 8), len(desc) & 0xFF])
        + desc
        for kind, pid, desc in streams
    )
    body = program.to_bytes(2, "big") + bytes([0xC1, 0x00, 0x00, 0xE1, 0x00, 0xF0, 0x00]) + loop
    section = bytes([0x02, 0xB0 | ((len(body) + 4) >> 8), (len(body) + 4) & 0xFF]) + body
    return ts_packets(pmt_pid, b"\x00" + section + b"\x00\x00\x00\x00")


def stream(kind: int, pid: int, descriptors: bytes = b"") -> tuple[int, int, bytes]:
    """One stream entry for ``pmt``: ``(stream_type, pid, descriptors)``."""
    return (kind, pid, descriptors)
