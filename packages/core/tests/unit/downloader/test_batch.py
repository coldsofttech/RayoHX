"""Downloading several streams in one call."""

import functools
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from rayohx import CancellationToken
from rayohx.config import DownloadConfig, NetworkConfig, OutputConfig
from rayohx.downloader import BatchItem, Downloader, batch_outputs, controller, download_many
from rayohx.errors import ConfigurationError
from rayohx.events import DownloadEvent
from tests.helpers.media import BASE, Origin

CONFIG = DownloadConfig(network=NetworkConfig(retries=0, backoff_factor=0.001))


@pytest.fixture
def origin(monkeypatch: pytest.MonkeyPatch) -> Origin:
    site = Origin(4, content="ts")
    absolute = site.playlist_text().replace("\nseg", f"\n{BASE}seg").encode()
    site.files = {"a/clip.m3u8": absolute, "b/clip.m3u8": absolute}
    monkeypatch.setattr(
        controller, "Downloader", functools.partial(Downloader, transport=httpx.MockTransport(site))
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
    seen: list[DownloadEvent] = []
    download_many([BASE + "index.m3u8"], tmp_path, config=CONFIG, on_event=seen.append)
    assert seen


def test_names_come_from_the_addresses_and_repeats_are_numbered(tmp_path: Path) -> None:
    urls = [BASE + "a/clip.m3u8", BASE + "b/clip.m3u8", BASE + "c/clip.m3u8"]
    assert batch_outputs(urls, tmp_path) == [
        tmp_path / "clip",
        tmp_path / "clip-2",
        tmp_path / "clip-3",
    ]


def test_without_a_folder_names_are_relative_to_the_current_folder() -> None:
    assert batch_outputs([BASE + "a/clip.m3u8"]) == [Path("clip")]


def test_an_item_knows_whether_it_was_skipped_or_succeeded() -> None:
    waiting = BatchItem(url="u", output=Path("x"))
    assert waiting.skipped
    assert not waiting.success
    failed = BatchItem(url="u", output=Path("x"), exception=RuntimeError("no"))
    assert not failed.skipped
    assert not failed.success


def test_the_folder_can_come_from_the_settings(origin: Origin, tmp_path: Path) -> None:
    config = DownloadConfig(
        network=NetworkConfig(retries=0, backoff_factor=0.001),
        output=OutputConfig(directory=tmp_path),
    )
    (item,) = download_many([BASE + "a/clip.m3u8"], config=config)
    assert item.success
    assert item.result
    assert item.result.output
    assert item.result.output.path.parent == tmp_path


def test_batch_names_load_without_the_downloader() -> None:
    code = (
        "import sys\n"
        "from rayohx import batch_outputs\n"
        "assert 'rayohx.downloader.controller' not in sys.modules\n"
        "batch_outputs(['https://x.test/a.m3u8'])\n"
        "assert 'rayohx.downloader.controller' not in sys.modules\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_a_playlist_you_already_have_can_be_downloaded(tmp_path: Path) -> None:
    site = Origin(3, content="ts")
    text = site.playlist_text().replace("\nseg", f"\n{BASE}seg")
    downloader = Downloader(
        BASE + "local.m3u8",
        output=tmp_path / "out.ts",
        config=CONFIG,
        transport=httpx.MockTransport(site),
        playlist_text=text,
    )
    assert downloader.run().success
    assert (tmp_path / "out.ts").read_bytes() == site.expected()
    assert "local.m3u8" not in site.log  # the playlist itself was never requested
