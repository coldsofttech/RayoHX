import struct
from collections.abc import Callable

import pytest

from rayohx._mux._boxes import box, descriptor, full_box, u16, u32, u64


def test_a_box_is_its_size_its_type_and_its_parts() -> None:
    assert box(b"abcd", b"12", b"345") == struct.pack(">I", 13) + b"abcd" + b"12345"


def test_a_box_without_parts_is_just_a_header() -> None:
    assert box(b"free") == b"\x00\x00\x00\x08free"


def test_boxes_nest() -> None:
    inner = box(b"in  ", b"x")
    assert box(b"out ", inner) == struct.pack(">I4s", 8 + len(inner), b"out ") + inner


def test_a_full_box_starts_with_its_version_and_flags() -> None:
    data = full_box(b"full", 1, 0x000203, b"zz")
    assert struct.unpack_from(">I", data)[0] == len(data)
    assert data[4:8] == b"full"
    assert data[8:12] == bytes([1, 0, 2, 3])
    assert data[12:] == b"zz"


@pytest.mark.parametrize(
    ("make", "value", "expected"),
    [
        (u16, 0, b"\x00\x00"),
        (u16, 0x0102, b"\x01\x02"),
        (u16, 0xFFFF, b"\xff\xff"),
        (u32, 0x01020304, b"\x01\x02\x03\x04"),
        (u32, 0xFFFFFFFF, b"\xff\xff\xff\xff"),
        (u64, 2**40 + 5, b"\x00\x00\x01\x00\x00\x00\x00\x05"),
    ],
)
def test_numbers_are_written_big_endian(
    make: Callable[[int], bytes], value: int, expected: bytes
) -> None:
    assert make(value) == expected


@pytest.mark.parametrize(
    ("make", "value"), [(u16, 65536), (u16, -1), (u32, 2**32), (u32, -1), (u64, 2**64)]
)
def test_numbers_that_do_not_fit_are_refused(make: Callable[[int], bytes], value: int) -> None:
    with pytest.raises(struct.error):
        make(value)


def test_a_descriptor_is_a_tag_a_four_byte_size_and_a_body() -> None:
    assert descriptor(0x05, b"abc") == bytes([0x05, 0x80, 0x80, 0x80, 0x03]) + b"abc"


def test_a_descriptor_joins_its_parts() -> None:
    assert descriptor(0x03, b"a", b"bc") == descriptor(0x03, b"abc")


def test_descriptor_sizes_use_seven_bits_per_byte() -> None:
    body = bytes(300)  # 300 = 2 * 128 + 44
    data = descriptor(0x04, body)
    assert data[:5] == bytes([0x04, 0x80, 0x80, 0x82, 0x2C])
    assert data[5:] == body
