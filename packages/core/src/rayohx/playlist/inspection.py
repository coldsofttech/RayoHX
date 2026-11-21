"""Looking at a stream before downloading it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rayohx.config import NetworkConfig
    from rayohx.models import Playlist


class PlaylistFetcher(Protocol):
    """Anything that can fetch a playlist's text. The HTTP layer provides the real one."""

    def fetch_text(self, url: str) -> tuple[str, str]:
        """Return the text at ``url`` and the address it finally came from (after redirects)."""
        ...


def inspect_text(text: str, base_url: str) -> Playlist:
    """Parse playlist ``text`` you already have (for example from a file).

    Relative addresses in it are resolved against ``base_url``.

    Raises:
        ConfigurationError: If ``base_url`` is not an http(s) address.
        InvalidPlaylistError: If the text is not an HLS playlist.
    """
    from rayohx.config import validate_url
    from rayohx.errors import InvalidPlaylistError
    from rayohx.playlist.detect import is_hls_playlist
    from rayohx.playlist.parser import parse_playlist

    if not is_hls_playlist(text):
        raise InvalidPlaylistError(
            "This is not an HLS playlist: it does not start with #EXTM3U.",
            hint="Check that the file is an .m3u8 playlist.",
        )
    return parse_playlist(text, validate_url(base_url))


def inspect_playlist(url: str, fetcher: PlaylistFetcher) -> Playlist:
    """Fetch and parse the playlist at ``url`` without downloading any media.

    Raises:
        ConfigurationError: If ``url`` is not an http(s) address.
        InvalidPlaylistError: If what comes back is not an HLS playlist.
    """
    from rayohx.config import validate_url
    from rayohx.errors import InvalidPlaylistError
    from rayohx.playlist.detect import is_hls_playlist
    from rayohx.playlist.parser import parse_playlist

    text, final_url = fetcher.fetch_text(validate_url(url))
    if not is_hls_playlist(text):
        raise InvalidPlaylistError(
            "The address did not return an HLS playlist.",
            hint="It may be a web page or need sign-in. Check the address, headers and cookies.",
        )
    return parse_playlist(text, final_url)


def inspect(url: str, network: NetworkConfig | None = None) -> Playlist:
    """Look at the stream at ``url`` without downloading it: its variants, tracks or segments.

    ``network`` sets headers, cookies, proxy, timeouts and TLS for the request.

    Raises:
        ConfigurationError: If ``url`` is not an http(s) address.
        PlaylistNotFoundError: If the playlist does not exist.
        InvalidPlaylistError: If what comes back is not an HLS playlist.
        NetworkError: If the request fails.
    """
    from rayohx._http import HttpClient
    from rayohx.config import NetworkConfig, validate_url

    address = validate_url(url)
    with HttpClient(network or NetworkConfig(), origin_url=address) as client:
        return inspect_playlist(address, client)
