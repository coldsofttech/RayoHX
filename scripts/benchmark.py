"""A small benchmark harness: how fast the engine moves data from a local server.

It serves generated segments from this machine (no internet involved), downloads them with the real
engine, and prints the throughput and the peak memory of each scenario. The numbers are for
comparing one change with another on the same machine, not for publishing.

    uv run python scripts/benchmark.py                  # all scenarios, default size
    uv run python scripts/benchmark.py --segments 200 --segment-kb 512 --concurrency 16
    uv run python scripts/benchmark.py --json > before.json

See docs/benchmarks.md.
"""

import argparse
import json
import resource
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "packages" / "core"
sys.path.insert(0, str(CORE))

from tests.helpers.media import ts_payload  # noqa: E402
from tests.helpers.servers import LocalServer, Reply, Route  # noqa: E402

from rayohx import Downloader, OutputFormat  # noqa: E402
from rayohx.config import DownloadConfig, OutputConfig  # noqa: E402

MEDIA = CORE / "tests" / "fixtures" / "media" / "h264_aac.ts"


def _playlist(count: int) -> bytes:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:4", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for index in range(count):
        lines += ["#EXTINF:4.0,", f"s{index}.ts"]
    return ("\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n").encode()


def _routes(count: int, body: bytes) -> dict[str, Route]:
    routes: dict[str, Route] = {"/index.m3u8": lambda _s: Reply(body=_playlist(count))}
    for index in range(count):
        routes[f"/s{index}.ts"] = lambda _s: Reply(body=body)
    return routes


def _peak_memory_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def run_scenario(
    name: str, count: int, body: bytes, config: DownloadConfig, output: str
) -> dict[str, object]:
    """Download ``count`` segments of ``body`` and measure the time and the data written."""
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


class _InstantDownloader:
    """Finishes at once, so the numbers show the queue's own cost."""

    def __init__(self, url: str, *, config: object, download_id: str, **_: object) -> None:
        from rayohx.events import EventBus

        self.url, self.config, self.download_id = url, config, download_id
        self.events = EventBus()
        self.exception = None

    def run(self) -> object:
        from rayohx.enums import ContainerFormat, DownloadState
        from rayohx.models import DownloadProgress, DownloadResult, OutputInfo

        path = Path(self.config.output.directory) / f"{self.download_id}.ts"  # type: ignore[attr-defined]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return DownloadResult(
            download_id=self.download_id,
            url=self.url,
            state=DownloadState.COMPLETED,
            elapsed_seconds=0,
            progress=DownloadProgress(state=DownloadState.COMPLETED),
            output=OutputInfo(path=path, container=ContainerFormat.MPEG_TS, size_bytes=1),
        )


def platform_rows(jobs: int, events: int) -> list[dict[str, object]]:
    """Queue and database costs: adding, listing, running and event records."""
    from rayohx.platform import Rayo, Severity
    from rayohx.platform.jobs import JobState
    from rayohx.platform.secrets import MemorySecretStore

    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as folder:
        rayo = Rayo(
            home=Path(folder) / "home",
            download_dir=Path(folder) / "dl",
            secrets=MemorySecretStore(),
            downloader_factory=_InstantDownloader,  # type: ignore[arg-type]
            max_active=4,
        )
        try:
            started = time.perf_counter()
            for index in range(jobs):
                rayo.queue.add(f"https://media.test/{index}/master.m3u8")
            added = time.perf_counter() - started
            rows.append(
                {"scenario": f"add {jobs} jobs", "seconds": round(added, 3),
                 "ms_per_job": round(added * 1000 / jobs, 2)}
            )  # fmt: skip
            started = time.perf_counter()
            listed = len(rayo.queue.list())
            rows.append(
                {
                    "scenario": f"list {listed} jobs",
                    "seconds": round(time.perf_counter() - started, 3),
                }
            )
            started = time.perf_counter()
            rayo.queue.start()
            rayo.queue.wait_idle(600)
            ran = time.perf_counter() - started
            done = len(rayo.queue.list(states=[JobState.COMPLETED]))
            rayo.queue.stop()
            rows.append(
                {"scenario": f"run {jobs} instant jobs", "completed": done,
                 "seconds": round(ran, 2), "ms_per_job": round(ran * 1000 / jobs, 2)}
            )  # fmt: skip
            started = time.perf_counter()
            for index in range(events):
                rayo.events.emit("benchmark.event", severity=Severity.INFO, index=index)
            written = time.perf_counter() - started
            rows.append(
                {"scenario": f"write {events} events", "seconds": round(written, 3),
                 "events_per_second": round(events / written)}
            )  # fmt: skip
            started = time.perf_counter()
            found = rayo.event_store.query(limit=1000, newest_first=True)
            rows.append(
                {
                    "scenario": f"read {len(found)} events",
                    "seconds": round(time.perf_counter() - started, 4),
                }
            )
            started = time.perf_counter()
            rayo.metrics()
            rows.append(
                {"scenario": "collect metrics", "seconds": round(time.perf_counter() - started, 4)}
            )
            rows[-1]["peak_rss_mb"] = round(_peak_memory_mb(), 1)
        finally:
            rayo.close()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--segments", type=int, default=100, help="segments to download")
    parser.add_argument("--segment-kb", type=int, default=256, help="size of each segment")
    parser.add_argument("--concurrency", type=int, default=8, help="parallel downloads")
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument("--platform", action="store_true", help="measure the queue and database")
    parser.add_argument("--jobs", type=int, default=500, help="jobs for --platform")
    parser.add_argument("--events", type=int, default=5000, help="event records for --platform")
    args = parser.parse_args(argv)
    if args.platform:
        rows = platform_rows(args.jobs, args.events)
    else:
        rows = [scenario() for scenario in scenarios(args)]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print("  ".join(f"{key}={value}" for key, value in row.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
