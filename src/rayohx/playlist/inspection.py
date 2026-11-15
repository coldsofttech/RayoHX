"""Looking at a stream before downloading it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rayohx.models import Playlist


class PlaylistFetcher(Protocol):
    """Anything that can fetch a playlist's text. The HTTP layer provides the real one."""

    def fetch_text(self, url: str) -> tuple[str, str]:
        """Return the text at ``url`` and the address it finally came from (after redirects)."""
        ...


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
