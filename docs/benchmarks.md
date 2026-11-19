# Benchmarks

`scripts/benchmark.py` measures how fast the engine moves data. It serves generated segments from a local server (no internet), downloads them with the real engine, and prints the throughput and the peak memory of each scenario.

```bash
uv run python scripts/benchmark.py                                   # default sizes
uv run python scripts/benchmark.py --segments 200 --segment-kb 512 --concurrency 16
uv run python scripts/benchmark.py --json > before.json              # compare before and after a change
```

| Scenario | What it measures |
| --- | --- |
| `join segments (ts)` | Downloading, checking and writing segments in order into one file. |
| `rewrap to mp4 (native)` | The same plus the built-in remuxer turning MPEG-TS into fragmented MP4. |

The figures depend on the machine and are meant for comparing one change with another on the same machine, not for publishing. On a development machine the engine joins segments at roughly 100 MB/s and the remuxer runs at about 130 to 150 MB/s with around 70 MB of memory.

## Queue and database

`--platform` measures the platform instead of the engine: adding, listing and running jobs (with a downloader that finishes at once, so only the queue's cost shows), writing and reading event records, and collecting metrics.

```bash
uv run python scripts/benchmark.py --platform                       # 500 jobs, 5000 events
uv run python scripts/benchmark.py --platform --jobs 2000 --events 20000 --json
```

On a development machine: about 1 ms to add a job, 20 ms to list 500, about 4 ms of queue overhead per job, roughly 12,000 events written per second and a thousand read in 10 ms.

Tests (`packages/core/tests/unit/test_benchmark_script.py`) run the script with tiny sizes, so it keeps working. It is a starting point: add scenarios (encrypted segments, many small segments, a slow server with `--rate-limit`) as they become useful.
