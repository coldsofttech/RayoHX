"""A small benchmark harness: how fast the engine moves data from a local server.

It serves generated segments from this machine (no internet involved), downloads them with the real
engine, and prints the throughput and the peak memory of each scenario. The numbers are for
comparing one change with another on the same machine, not for publishing.

    uv run python packages/core/scripts/benchmark.py              # all scenarios, default size
    uv run python packages/core/scripts/benchmark.py --segments 200 --segment-kb 512
    uv run python packages/core/scripts/benchmark.py --json > before.json

See packages/core/docs/benchmarks.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from rayohx_pytest.servers import Route

    from rayohx.config import DownloadConfig

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# shared test helpers (rayohx-pytest)
from rayohx_pytest.fixtures import FIXTURES  # noqa: E402

MEDIA = FIXTURES / "media" / "h264_aac.ts"


def _playlist(count: int) -> bytes:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:4", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for index in range(count):
        lines += ["#EXTINF:4.0,", f"s{index}.ts"]
    return ("\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n").encode()


def _routes(count: int, body: bytes) -> dict[str, Route]:
    from rayohx_pytest.servers import Reply

    routes: dict[str, Route] = {"/index.m3u8": lambda _s: Reply(body=_playlist(count))}
    for index in range(count):
        routes[f"/s{index}.ts"] = lambda _s: Reply(body=body)
    return routes


def _peak_memory_mb() -> float:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        process = kernel32.GetCurrentProcess()
        psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
        return counters.PeakWorkingSetSize / (1024 * 1024)

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def run_scenario(
    name: str, count: int, body: bytes, config: DownloadConfig, output: str
) -> dict[str, object]:
    """Download ``count`` segments of ``body`` and measure the time and the data written."""
    import tempfile
    import time

    from rayohx_pytest.servers import LocalServer

    from rayohx import Downloader

    with tempfile.TemporaryDirectory() as folder, LocalServer(_routes(count, body)) as server:
        target = Path(folder) / output
        started = time.perf_counter()
        result = Downloader(f"{server.url}/index.m3u8", output=target, config=config).run()
        seconds = time.perf_counter() - started
        size = result.output.size_bytes if result.output else 0
    if not result.success:
        raise SystemExit(f"{name}: the download failed: {result.error}")
    return {
        "scenario": name,
        "segments": count,
        "input_mb": round(count * len(body) / 1e6, 1),
        "output_mb": round(size / 1e6, 1),
        "seconds": round(seconds, 2),
        "mb_per_second": round(count * len(body) / 1e6 / seconds, 1),
        "peak_rss_mb": round(_peak_memory_mb(), 1),
    }


def scenarios(args: argparse.Namespace) -> list[Callable[[], dict[str, object]]]:
    """The scenarios to run, each a function returning one result row."""
    from rayohx_pytest.media import ts_payload

    from rayohx import OutputFormat
    from rayohx.config import DownloadConfig, OutputConfig

    plain = DownloadConfig(
        concurrency=args.concurrency, output=OutputConfig(format=OutputFormat.TS)
    )
    mp4 = DownloadConfig(concurrency=args.concurrency, output=OutputConfig(format=OutputFormat.MP4))
    filler = ts_payload(0, packets=max(1, args.segment_kb * 1024 // 188))
    clip = MEDIA.read_bytes()
    return [
        lambda: run_scenario("join segments (ts)", args.segments, filler, plain, "out.ts"),
        lambda: run_scenario(
            "rewrap to mp4 (native)", max(1, args.segments // 10), clip, mp4, "out.mp4"
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    import json

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--segments", type=int, default=100, help="segments to download")
    parser.add_argument("--segment-kb", type=int, default=256, help="size of each segment")
    parser.add_argument("--concurrency", type=int, default=8, help="parallel downloads")
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    args = parser.parse_args(argv)
    rows = [scenario() for scenario in scenarios(args)]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print("  ".join(f"{key}={value}" for key, value in row.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
