from pathlib import Path

import pytest

from rayohx.config import OutputConfig
from rayohx.errors import ConfigurationError


def test_output_validation() -> None:
    with pytest.raises(ConfigurationError):
        OutputConfig(path=Path("."))
    with pytest.raises(ConfigurationError):
        OutputConfig(path=Path("bad\0name"))
    config = OutputConfig(path=Path("video.mp4"), ffmpeg_path=Path("/usr/bin/ffmpeg"))
    assert config.as_dict()["path"] == "video.mp4"
    assert config.as_dict()["ffmpeg_path"] == str(Path("/usr/bin/ffmpeg"))
