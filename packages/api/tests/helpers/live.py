"""A local HLS site and the real API in a subprocess, for tests that download over real sockets."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Self

import httpx
from rayohx_testing.fixtures import fixture_bytes
from rayohx_testing.hls import segment_index, vod_routes
from rayohx_testing.servers import LocalServer, Reply

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class HlsServer(LocalServer):
    """A ``LocalServer`` that serves ``/master.m3u8``, ``/index.m3u8`` and ``/seg<N>.ts``.

    ``delay`` slows every segment. Segments from ``gate_from`` on wait until ``release()`` is
    called, so a test can hold a download open at a known point.
    """

    def __init__(self, *, count: int = 6, delay: float = 0.0, gate_from: int | None = None) -> None:
        self.gate = threading.Event()
        routes = vod_routes(
            count,
            delay=delay,
            gate=self.gate if gate_from is not None else None,
            gate_from=gate_from or 0,
        )
        master = fixture_bytes("hls/master_two_variants.m3u8")
        routes["/master.m3u8"] = lambda _s: Reply(body=master)
        super().__init__(routes)

    @property
    def playlist_url(self) -> str:
        return f"{self.url}/index.m3u8"

    @property
    def master_url(self) -> str:
        return f"{self.url}/master.m3u8"

    @property
    def segment_requests(self) -> list[int]:
        """The segment numbers asked for so far, in order (repeats included)."""
        found = (segment_index(seen) for seen in list(self.requests))
        return [index for index in found if index is not None]

    @property
    def headers_seen(self) -> list[dict[str, str]]:
        return [seen.headers for seen in list(self.requests)]

    def release(self) -> None:
        self.gate.set()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
        super().__exit__(exc_type, exc, traceback)


class ApiProcess:
    """The real API, started the way users start it on its own."""

    def __init__(self, download_dir: Path, **settings: str) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        env = {
            **os.environ,
            "RAYOHX_API_PORT": str(self.port),
            "RAYOHX_API_HOST": "127.0.0.1",
            "RAYOHX_API_AUTH_MODE": "none",
            "RAYOHX_API_DOWNLOAD_DIR": str(download_dir),
        }
        env.update({f"RAYOHX_API_{name.upper()}": value for name, value in settings.items()})
        self._process = subprocess.Popen([sys.executable, "-m", "rayohx_api"], env=env)
        self.client = httpx.Client(base_url=self.url, timeout=10)
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError("the API exited during startup")
            try:
                if self.client.get("/health", timeout=1).status_code == 200:
                    return
            except httpx.TransportError:
                time.sleep(0.2)
        raise RuntimeError("the API did not become ready")

    def start_download(self, url: str, **body: Any) -> dict[str, Any]:
        response = self.client.post("/api/v1/downloads", json={"url": url, **body})
        assert response.status_code == 202, response.text
        return dict(response.json())

    def job(self, job_id: str) -> dict[str, Any]:
        return dict(self.client.get(f"/api/v1/downloads/{job_id}").json())

    def wait_for(
        self, job_id: str, *states: str, timeout: float = 30, until: Any = None
    ) -> dict[str, Any]:
        """Poll until the job is in one of ``states`` (and ``until(job)`` holds, if given)."""
        deadline = time.monotonic() + timeout
        job = self.job(job_id)
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["state"] in states and (until is None or until(job)):
                return job
            time.sleep(0.05)
        raise AssertionError(f"job stuck in {job['state']!r}, wanted {states}")

    def stop(self, *, kill: bool = False) -> None:
        self.client.close()
        if kill:
            self._process.kill()
        else:
            self._process.terminate()
        self._process.wait(timeout=10)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._process.poll() is None:
            self.stop(kill=True)
