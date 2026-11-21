import struct

from rayohx._mux._boxes import box
from rayohx._mux._mp4read import find_box, iter_boxes


def test_boxes_with_large_and_open_ended_sizes() -> None:
    large = struct.pack(">I4sQ", 1, b"big ", 16 + 5) + b"hello"
    open_ended = struct.pack(">I4s", 0, b"last") + b"tail"
    data = box(b"aaaa", b"xx") + large + open_ended
    found = [(kind, size, header) for kind, _, size, header in iter_boxes(data)]
    assert found == [(b"aaaa", 10, 8), (b"big ", 21, 16), (b"last", 12, 8)]


def test_a_box_that_does_not_fit_stops_the_walk() -> None:
    data = box(b"good", b"x") + struct.pack(">I4s", 100, b"bad ") + b"short"
    assert [kind for kind, *_ in iter_boxes(data)] == [b"good"]
    assert list(iter_boxes(b"\x00\x00\x00")) == []
    truncated_large = struct.pack(">I4s", 1, b"big ") + b"\x00\x00"
    assert list(iter_boxes(truncated_large)) == []
    assert list(iter_boxes(struct.pack(">I4s", 4, b"tiny"))) == []  # smaller than its own header


def test_finding_nested_boxes() -> None:
    data = box(b"outr", box(b"mid ", box(b"leaf", b"!")))
    found = find_box(data, (b"outr", b"mid ", b"leaf"))
    assert found is not None
    assert data[found[0] + found[2] : found[0] + found[1]] == b"!"
    assert find_box(data, (b"outr", b"nope")) is None
    assert find_box(data, (b"nope",)) is None
