"""Splitting a playlist into numbered lines and reading tags."""

import re

Line = tuple[int, str]

_LINE_BREAK = re.compile(r"\r\n|\n|\r")


def numbered_lines(text: str) -> list[Line]:
    """Numbered, non-blank lines. Only real line breaks split text, never other Unicode ones."""
    numbered = []
    for number, raw in enumerate(_LINE_BREAK.split(text.lstrip("﻿")), start=1):
        content = raw.strip()
        if content:
            numbered.append((number, content))
    return numbered


def tag_name(content: str) -> str:
    return content[1:].partition(":")[0]


def tag_value(content: str) -> str:
    return content.partition(":")[2]


def is_comment(content: str) -> bool:
    return content.startswith("#") and not content.startswith("#EXT")
