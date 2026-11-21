import dataclasses
from pathlib import Path

import pytest

from rayohx import ContainerFormat
from rayohx.models import OutputInfo


def test_the_output_names_its_file_its_format_and_its_size() -> None:
    info = OutputInfo(path=Path("out.mp4"), container=ContainerFormat.FMP4, size_bytes=1234)
    assert info.path == Path("out.mp4")
    assert info.container is ContainerFormat.FMP4
    assert info.size_bytes == 1234


def test_every_field_is_required() -> None:
    with pytest.raises(TypeError):
        OutputInfo(path=Path("out.mp4"), container=ContainerFormat.FMP4)  # type: ignore[call-arg]


def test_output_info_cannot_be_changed() -> None:
    info = OutputInfo(path=Path("out.ts"), container=ContainerFormat.MPEG_TS, size_bytes=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.size_bytes = 2  # type: ignore[misc]


def test_arguments_must_be_named() -> None:
    with pytest.raises(TypeError):
        OutputInfo(Path("out.ts"), ContainerFormat.MPEG_TS, 1)  # type: ignore[call-arg]
