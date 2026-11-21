from rayohx import SegmentData, StorageStrategy

GIB = 1024**3


S = StorageStrategy


def seg(index: int, size: int = 100, init: bytes = b"") -> SegmentData:
    return SegmentData(index=index, media=bytes([index % 256]) * size, init=init)
