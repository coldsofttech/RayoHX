"""Checks that an installed rayohx wheel loads and works. The release build runs it on every wheel.

It does not repeat the unit tests, which pull requests already run on the source. It proves what
they cannot: the compiled binary for this platform and Python version imports, reports the version
it was built as, and parses and selects from a playlist.

Usage: ``python scripts/wheel_smoke.py [--compiled]``. With ``--compiled`` it fails when the
loaded package is plain Python instead of the compiled binary.
"""

from __future__ import annotations

import importlib.metadata
import sys

PLAYLIST = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720
high.m3u8
"""
BASE = "https://example.com/vod/master.m3u8"


def main() -> int:
    import rayohx
    from rayohx.config import SelectionConfig

    # Nuitka modules report __file__ as rayohx/__init__.py, so check the loader instead.
    loader = type(rayohx.__spec__.loader).__name__
    compiled = "nuitka" in loader.lower() or "Extension" in loader
    print(f"rayohx {rayohx.__version__} from {rayohx.__file__} (loader: {loader})")
    if "--compiled" in sys.argv and not compiled:
        print("FAIL: the loaded package is not the compiled build", file=sys.stderr)
        return 1

    installed = importlib.metadata.version("rayohx")
    if installed != rayohx.__version__:
        print(f"FAIL: metadata says {installed}, the package says {rayohx.__version__}")
        return 1

    playlist = rayohx.inspect_text(PLAYLIST, BASE)
    if not isinstance(playlist, rayohx.MasterPlaylist) or len(playlist.variants) != 2:
        print(f"FAIL: expected a master playlist with 2 variants, got {playlist!r}")
        return 1

    chosen = rayohx.select_stream(playlist, SelectionConfig(quality="720p")).variant
    if chosen is None or chosen.bandwidth != 2000000:
        print(f"FAIL: expected the 720p variant, got {chosen}")
        return 1

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
