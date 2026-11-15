"""Recognising an HLS playlist by its content."""

HEADER = "#EXTM3U"


def is_hls_playlist(text: str) -> bool:
    """Whether ``text`` starts like an HLS playlist, whatever it was called or fetched from."""
    return text.lstrip("﻿").lstrip().startswith(HEADER)
