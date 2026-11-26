# Benchmarks

`packages/core/scripts/benchmark.py` measures how fast the engine moves data, and how much memory it uses doing so. It is a tool for developers of the library: run it before and after a change to see whether the change made downloading faster, slower or hungrier. For how the engine is built, see [architecture](architecture.md); for working on it, see [development](development.md).

## Why it exists

Unit tests say whether the engine is correct, not whether it is fast. Speed problems are easy to introduce without noticing: an extra copy of every segment, a check that reads the data twice, a lock held too long. The benchmark gives a number to compare, so a slowdown shows up in a pull request instead of in a user's download.

It helps with three things:

- **Catching regressions.** Run it on the base branch and on your branch and compare. A drop in throughput or a rise in memory is a reason to look closer.
- **Checking an optimisation.** A change meant to make things faster has to show it. Without a number, "faster" is a guess.
- **Watching memory.** The engine promises bounded memory (see [the segment pipeline](architecture.md#the-segment-pipeline)). Peak memory is the figure that would grow if segments started piling up.

## What it does

1. It generates fake segments in memory, so there is nothing to download first and no internet is involved.
2. It starts a small HTTP server on `127.0.0.1` (the test helper `LocalServer`) that serves a playlist and those segments.
3. It downloads the playlist with the real engine, through `Downloader`, exactly as a user's program would: the same HTTP client, pipeline, storage strategy, checks and output code.
4. It times the download, and prints one row of figures for each scenario.

Because the server is on the same machine, the network is out of the picture. What is measured is the engine itself: how quickly it can fetch, check, order and write data.

## Running it

It needs a checkout of the repository, because it uses the test helpers and the sample media in `packages/core/tests`.

```bash
uv run python packages/core/scripts/benchmark.py                                   # default sizes
uv run python packages/core/scripts/benchmark.py --segments 200 --segment-kb 512 --concurrency 16
uv run python packages/core/scripts/benchmark.py --json > before.json              # keep the figures
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--segments` | 100 | How many segments the first scenario downloads. |
| `--segment-kb` | 256 | The size of each of those segments. |
| `--concurrency` | 8 | How many segments are fetched in parallel (the engine's `concurrency` setting). |
| `--json` | off | Print the results as JSON instead of one line per scenario. |

The script reads the process's memory use through the `resource` module, so it runs on Linux and macOS, not on Windows. On Windows, run it in WSL or a Linux container.

## The scenarios

| Scenario | What it downloads | What it measures |
| --- | --- | --- |
| `join segments (ts)` | `--segments` segments of `--segment-kb` each, as MPEG-TS, written to one `.ts` file | The core path: downloading, checking and writing segments in order into one file. This is the one to watch for general speed. |
| `rewrap to mp4 (native)` | One tenth of `--segments` copies (at least one) of a small real clip (about 91 KB, H.264 video and AAC audio), written as `.mp4` | The same, plus the built-in remuxer turning MPEG-TS into fragmented MP4. It always uses the built-in remuxer, because the clip's codecs are ones it supports, so FFmpeg is never involved. |

The second scenario uses fewer, real segments because remuxing needs real video: it has to parse the codecs and cut the stream into fragments. The first uses filler segments with valid MPEG-TS packet structure, so the engine's format checks accept them but nothing needs decoding.

## Reading the results

Each scenario prints one line (or one JSON object):

```text
scenario=join segments (ts)  segments=100  input_mb=25.6  output_mb=25.6  seconds=0.25  mb_per_second=102.4  peak_rss_mb=70.1
```

| Figure | Meaning |
| --- | --- |
| `segments` | How many segments were downloaded. |
| `input_mb` | The data the server sent, in megabytes. |
| `output_mb` | The size of the finished file. For `join segments` it equals the input; for the remux scenario it differs, since the output is a re-wrapped MP4. |
| `seconds` | The time from starting the download to the finished file. It includes reading the playlist and finishing the output, not only the segments. |
| `mb_per_second` | `input_mb` divided by `seconds`: the throughput. Higher is better. |
| `peak_rss_mb` | The most memory the whole process has used so far. Lower is better. |

Things to keep in mind when reading them:

- **Peak memory is for the whole process, and it never goes down.** It includes Python itself, the test server running in the same process, and everything used by earlier scenarios. So the second row can only be equal to or higher than the first. Compare the same row between two runs, not one row with another.
- **The numbers depend on the machine.** CPU, disk, other programs running and the Python version all change them. They are for comparing one change with another on the same machine, not for publishing or for comparing machines.
- **One run is noisy.** Run each side two or three times, and treat a difference of a few percent as noise. A large, repeatable difference is real.
- **A failed download stops the script.** If a scenario fails, it exits with the engine's error message instead of printing figures.

On a development machine the engine joined segments at roughly 100 MB/s, and the remuxer ran at about 130 to 150 MB/s with around 70 MB of memory. These figures are a rough guide to what to expect, not a promise.

## Comparing a change

```bash
git switch main
uv run python packages/core/scripts/benchmark.py --json > before.json
git switch my-change
uv run python packages/core/scripts/benchmark.py --json > after.json
```

Compare `mb_per_second` and `peak_rss_mb` for each scenario in the two files. Use the same options and the same machine for both, and close busy programs first. Mention a meaningful difference in the pull request.

Use bigger sizes (`--segments 500 --segment-kb 1024`) when a change should only matter for large downloads, and a higher `--concurrency` to see how well the engine uses parallel fetching.

## What it does not measure

- **Real network behaviour.** There is no latency, packet loss, slow server, retry or back-off, since the server is local and instant.
- **Decryption.** The segments are not encrypted, so AES-128 cost is not included.
- **Many small segments.** The segments are as large as `--segment-kb` says; a playlist of thousands of tiny segments stresses the engine differently.
- **Other storage strategies and output modes.** It runs with the default strategy, and does not cover separate audio tracks, subtitles or FFmpeg.
- **Start-up time.** Importing the library and the first request are not separated out.

## Keeping it working

A test, `packages/core/tests/unit/scripts/test_benchmark.py`, runs the script with tiny sizes and checks it reports both scenarios, so it does not rot as the engine changes. It is skipped on Windows. The script is a starting point: add scenarios (encrypted segments, many small segments, a slow server) as they become useful, by adding a function to `scenarios()` that calls `run_scenario` with the new case and returns one row.
