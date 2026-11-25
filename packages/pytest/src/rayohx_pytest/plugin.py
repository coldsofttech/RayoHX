"""The pytest fixtures: local servers, a test certificate and stream bytes."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest

from rayohx_pytest.media import ts_payload as _ts_payload
from rayohx_pytest.servers import LocalServer, Route, make_certificate

ServerFactory = Callable[..., LocalServer]


@pytest.fixture
def local_server() -> Iterator[ServerFactory]:
    """Start real HTTP servers on 127.0.0.1; every one started is stopped after the test."""
    started: list[LocalServer] = []

    def start(
        routes: Mapping[str, Route] | None = None, *, tls: tuple[Path, Path] | None = None
    ) -> LocalServer:
        server = LocalServer(routes, tls=tls)
        server.__enter__()
        started.append(server)
        return server

    yield start
    for server in reversed(started):
        server.__exit__(None, None, None)


@pytest.fixture
def tls_certificate(tmp_path: Path) -> tuple[Path, Path]:
    """A self-signed certificate and key, valid for 127.0.0.1 and localhost."""
    return make_certificate(tmp_path)


@pytest.fixture
def ts_payload() -> Callable[..., bytes]:
    """Build MPEG-TS packets (188 bytes each, starting with the 0x47 sync byte)."""
    return _ts_payload
