import pytest

from rayohx.config import SelectionConfig
from rayohx.errors import ConfigurationError


@pytest.mark.parametrize("quality", ["best", "WORST", "auto", "1080p", "720P"])
def test_valid_qualities(quality: str) -> None:
    assert SelectionConfig(quality=quality).quality == quality.lower()


@pytest.mark.parametrize("quality", ["", "hd", "1080", "p1080", "12p"])
def test_invalid_qualities(quality: str) -> None:
    with pytest.raises(ConfigurationError, match="quality"):
        SelectionConfig(quality=quality)


def test_selection_limits_and_languages() -> None:
    selection = SelectionConfig(
        max_resolution="1080P", max_bitrate=5_000_000, audio_languages=("en", "pt-BR")
    )
    assert selection.max_resolution == "1080p"
    assert selection.as_dict()["audio_languages"] == ["en", "pt-BR"]
    with pytest.raises(ConfigurationError):
        SelectionConfig(max_resolution="full")
    with pytest.raises(ConfigurationError):
        SelectionConfig(max_bitrate=0)
    with pytest.raises(ConfigurationError):
        SelectionConfig(subtitle_languages=("english!",))
