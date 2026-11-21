from types import SimpleNamespace
from typing import ClassVar

import pytest

from rayohx import DownloadState
from rayohx.config import DownloadConfig, OutputConfig, SelectionConfig
from rayohx.downloader.shortcut import download, languages, replace
from rayohx.enums import OutputFormat
from rayohx.errors import DownloadError
from rayohx.models import DownloadProgress, DownloadResult

URL = "https://example.com/show/index.m3u8"


class FakeDownloader:
    """Stands in for ``Downloader``: remembers how it was built and ends as it is told to."""

    created: ClassVar[list["FakeDownloader"]] = []
    state = DownloadState.COMPLETED
    failure: Exception | None = None

    def __init__(
        self, url: str, *, output: object = None, config: object = None, cancel: object = None
    ) -> None:
        self.url = url
        self.output = output
        self.config: DownloadConfig = config  # type: ignore[assignment]
        self.cancel = cancel
        self.listeners: list[object] = []
        self.events = SimpleNamespace(subscribe=self.listeners.append)
        self.exception = type(self).failure
        FakeDownloader.created.append(self)

    def run(self) -> DownloadResult:
        state = type(self).state
        return DownloadResult(
            download_id="abc",
            url=self.url,
            state=state,
            elapsed_seconds=0.0,
            progress=DownloadProgress(state=state),
        )


@pytest.fixture(autouse=True)
def fake_downloader(monkeypatch: pytest.MonkeyPatch) -> type[FakeDownloader]:
    FakeDownloader.created = []
    FakeDownloader.state = DownloadState.COMPLETED
    FakeDownloader.failure = None
    monkeypatch.setattr("rayohx.downloader.controller.Downloader", FakeDownloader)
    return FakeDownloader


def test_a_list_of_languages_becomes_a_tuple() -> None:
    assert languages(None) is None
    assert languages("en") == ("en",)
    assert languages(["en", "fr"]) == ("en", "fr")
    assert languages(()) == ()


def test_replace_changes_only_the_options_that_were_given() -> None:
    base = SelectionConfig(quality="worst", video_only=True)
    changed = replace(base, quality="720p", max_bitrate=None)
    assert (changed.quality, changed.video_only, changed.max_bitrate) == ("720p", True, None)
    assert base.quality == "worst"


def test_replace_returns_the_same_object_when_nothing_was_given() -> None:
    base = SelectionConfig()
    assert replace(base, quality=None, video_only=None) is base


def test_the_options_override_the_config_the_download_runs_with() -> None:
    download(
        URL,
        "out.ts",
        quality="720p",
        max_resolution="1080p",
        max_bitrate=2_000_000,
        audio="en",
        subtitles=["en", "fr"],
        video_only=True,
        format=OutputFormat.TS,
        overwrite=True,
        concurrency=2,
        resume=False,
    )
    (downloader,) = FakeDownloader.created
    config = downloader.config
    assert downloader.url == URL
    assert downloader.output == "out.ts"
    assert (config.selection.quality, config.selection.max_resolution) == ("720p", "1080p")
    assert config.selection.max_bitrate == 2_000_000
    assert config.selection.audio_languages == ("en",)
    assert config.selection.subtitle_languages == ("en", "fr")
    assert config.selection.video_only is True
    assert (config.output.format, config.output.overwrite) == (OutputFormat.TS, True)
    assert (config.concurrency, config.resume) == (2, False)


def test_a_format_can_be_given_as_text() -> None:
    download(URL, format="mp4")
    assert FakeDownloader.created[0].config.output.format is OutputFormat.MP4


def test_settings_that_were_not_overridden_come_from_the_config() -> None:
    base = DownloadConfig(
        concurrency=8,
        selection=SelectionConfig(quality="worst"),
        output=OutputConfig(overwrite=True),
    )
    download(URL, config=base)
    config = FakeDownloader.created[0].config
    assert config.concurrency == 8
    assert config.selection.quality == "worst"
    assert config.output.overwrite is True


def test_the_event_listener_and_the_cancellation_token_are_passed_on() -> None:
    from rayohx import CancellationToken

    token = CancellationToken()

    def listener(_event: object) -> None:
        return None

    download(URL, on_event=listener, cancel=token)
    (downloader,) = FakeDownloader.created
    assert downloader.listeners == [listener]
    assert downloader.cancel is token


def test_no_listener_is_added_when_none_is_given() -> None:
    download(URL)
    assert FakeDownloader.created[0].listeners == []


def test_a_completed_download_returns_its_result() -> None:
    result = download(URL)
    assert result.state is DownloadState.COMPLETED


def test_a_failed_download_raises_the_original_error() -> None:
    FakeDownloader.state = DownloadState.FAILED
    FakeDownloader.failure = DownloadError("the segment was bad")
    with pytest.raises(DownloadError, match="the segment was bad"):
        download(URL)


def test_a_cancelled_download_returns_a_result_instead_of_raising() -> None:
    FakeDownloader.state = DownloadState.CANCELLED
    result = download(URL)
    assert result.cancelled
