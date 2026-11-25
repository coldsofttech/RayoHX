"""An in-memory site for tests: an httpx mock handler serving bytes, and the shared HLS sets."""

import httpx

from rayohx_pytest.fixtures import FIXTURES, fixture_bytes

MEDIA = FIXTURES / "media"


class Site:
    """An ``httpx`` mock transport handler that serves bytes by path and logs the requests."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = dict(files or {})
        self.log: list[str] = []
        self.requests: list[httpx.Request] = []
        self.fail: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.lstrip("/")
        self.log.append(path)
        self.requests.append(request)
        if path in self.fail:
            return httpx.Response(500)
        if path in self.files:
            return httpx.Response(200, content=self.files[path])
        return httpx.Response(404)


def fixture(name: str) -> bytes:
    """The bytes of a shared HLS playlist from the ``rayohx-pytest`` fixtures."""
    return fixture_bytes(f"hls/{name}")


def media(name: str) -> bytes:
    """The bytes of a fixture in the ``rayohx-pytest`` media fixtures."""
    return (MEDIA / name).read_bytes()


def hls_site(kind: str, prefix: str) -> Site:
    """A site serving one of the generated HLS sets under ``prefix/``."""
    folder = MEDIA / f"hls_{kind}"
    return Site({f"{prefix}/{item.name}": item.read_bytes() for item in folder.iterdir()})


def single_file_site(name: str, prefix: str = "show", parts: int = 3) -> Site:
    """A playlist of one real transport stream cut into ``parts`` segments at packet boundaries."""
    data = media(name)
    packets = len(data) // 188
    bounds = [(packets * i // parts) * 188 for i in range(parts)] + [packets * 188]
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:2", "#EXT-X-PLAYLIST-TYPE:VOD"]
    files = {}
    for index in range(parts):
        lines += ["#EXTINF:1.3,", f"seg{index}.ts"]
        files[f"{prefix}/seg{index}.ts"] = data[bounds[index] : bounds[index + 1]]
    lines.append("#EXT-X-ENDLIST")
    files[f"{prefix}/index.m3u8"] = ("\n".join(lines) + "\n").encode()
    return Site(files)
