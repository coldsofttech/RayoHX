"""Downloading several streams in one call."""

import functools
from pathlib import Path

import httpx
import pytest

from rayohx import CancellationToken
from rayohx.config import DownloadConfig, NetworkConfig
from rayohx.downloader import Downloader, batch, download_many
from rayohx.errors import ConfigurationError
from tests.helpers.media import BASE, Origin

CONFIG = DownloadConfig(network=NetworkConfig(retries=0, backoff_factor=0.001))


@pytest.fixture
def origin(monkeypatch: pytest.MonkeyPatch) -> Origin:
    site = Origin(4, content="ts")
    absolute = site.playlist_text().replace("\nseg", f"\n{BASE}seg").encode()
    site.files = {"a/clip.m3u8": absolute, "b/clip.m3u8": absolute}
    monkeypatch.setattr(
        batch, "Downloader", functools.partial(Downloader, transport=httpx.MockTransport(site))
    )
    return site


def test_each_address_gets_its_own_file(origin: Origin, tmp_path: Path) -> None:
    urls = [BASE + "a/clip.m3u8", BASE + "b/clip.m3u8", BASE + "index.m3u8"]
    items = download_many(urls, tmp_path, config=CONFIG)
    assert all(item.success for item in items)
    names = sorted(
        item.result.output.path.name for item in items if item.result and item.result.output
    )
    assert names == ["clip-2.ts", "clip.ts", "v.ts"]


def test_a_failure_does_not_stop_the_rest_by_default(origin: Origin, tmp_path: Path) -> None:
    bad = BASE + "missing/index.m3u8"
    items = download_many([bad, BASE + "index.m3u8"], tmp_path, config=CONFIG)
    assert not items[0].success
    assert items[0].exception is not None
    assert items[1].success


def test_stop_on_error_skips_the_rest(origin: Origin, tmp_path: Path) -> None:
    bad = BASE + "missing/index.m3u8"
    items = download_many([bad, BASE + "index.m3u8"], tmp_path, config=CONFIG, stop_on_error=True)
    assert not items[0].success
    assert items[1].skipped
    assert not list(tmp_path.glob("*.ts"))


def test_cancelling_skips_what_was_not_started(origin: Origin, tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()
    items = download_many([BASE + "index.m3u8"], tmp_path, config=CONFIG, cancel=token)
    assert items[0].skipped


def test_nothing_to_do_and_bad_addresses_are_refused_up_front(
    origin: Origin, tmp_path: Path
) -> None:
    with pytest.raises(ConfigurationError):
        download_many([], tmp_path)
    with pytest.raises(ConfigurationError):
        download_many([BASE + "index.m3u8", "not a url"], tmp_path, config=CONFIG)
    assert not list(tmp_path.iterdir())


def test_events_from_every_download_reach_the_listener(origin: Origin, tmp_path: Path) -> None:
    seen = []
    download_many([BASE + "index.m3u8"], tmp_path, config=CONFIG, on_event=seen.append)
    assert seen
