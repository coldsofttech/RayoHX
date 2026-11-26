# Testing

How the tests are organized, and the shared `rayohx-pytest` plugin that the tests (and the other RayoHX repositories) use.

## Where tests live

The core tests are in `packages/core/tests/`:

```text
tests/unit/          fast tests, run by default; one test file per source module
tests/integration/   slower end-to-end tests over real sockets or real processes
tests/helpers/       helpers that need the engine's own code
tests/fixtures/      data files only the core tests use (for example its malformed playlists)
```

Anything in an `integration` folder is marked `integration` automatically and is skipped by a normal `pytest` run. Run it with `-m integration`, for example `uv run pytest -m integration packages/core/tests/integration`.

The pytest plugin has no tests of its own; the core tests exercise it.

## The shared plugin

`packages/pytest` (the `rayohx-pytest` distribution, import name `rayohx_pytest`) holds the test code and data that more than one repository needs, so it is written once. It is a pytest plugin installed with the workspace, so its fixtures need no import: `local_server` (a factory that starts a real HTTP server and stops it after the test), `tls_certificate` and `ts_payload`. The classes and helpers behind them are importable:

```python
from rayohx_pytest.plugin import ServerFactory
from rayohx_pytest.servers import Reply, Seen
from rayohx_pytest.hls import vod_routes, expected
```

It is not published to PyPI. Other repositories take it from git at a `pytest-v<version>` tag as a development dependency; see its [README](../packages/pytest/README.md).

| Module | What it gives you |
|---|---|
| `servers` | `LocalServer`: a real threaded HTTP/1.1 server (optionally TLS) with routes by path, per-reply delays and a log of every request. Also `Reply`, `Seen`, `Route`, `make_certificate` and `free_port()` (a free local TCP port). |
| `hls` | A small VOD stream on top of `LocalServer`: `vod_routes(count, delay=, gate=)` serves `/index.m3u8` and `/seg<N>.ts`; `expected(count)` is what a finished download contains; `segment_index` tells which segment a request asked for. `HlsServer(count=, delay=, gate_from=)` is a `LocalServer` that serves that stream plus `/master.m3u8` (the shared two-variant playlist), with `playlist_url`, `master_url`, `segment_requests` and `release()` helpers. A `gate` holds segments until a test sets it, to stop a download at a known point. |
| `site` | `Site`, an `httpx` mock handler that serves bytes by path and logs requests, plus `hls_site` and `single_file_site`, which build streams from the shared media files, and `media(name)`. |
| `media` | Stream bytes: `ts_payload` (MPEG-TS packets that pass the engine's sync-byte check), `payload`, `encrypt` (AES-128-CBC as HLS does), MP4 builders (`box`, `fmp4_init`, `fmp4_fragment`) and MPEG-TS builders (`pes`, `ts_packets`, `pat`, `pmt`, `stream`, with `BitWriter`, `escape_nal` and `annexb` for hand-made video headers). |
| `mocks` | `httpx` test doubles: `FakeTime` (a clock that only moves when something sleeps), `Body` (a response body that can fail part-way), `Recorder`, and the `ok` and `sequence` handlers. |
| `ffmpeg` | FFmpeg as a test oracle: `needs_ffmpeg` (skips a test when `ffmpeg` and `ffprobe` are missing), `probe`, `decodes_cleanly` and `decoded`. |
| `fixtures` | `fixture_path`, `fixture_text` and `fixture_bytes` for the files in `rayohx_pytest/data/`. |

Read a fixture with `rayohx_pytest.fixtures`, not with a path built from `__file__`, so a test keeps working if it moves.

### Fixtures

`packages/pytest/src/rayohx_pytest/data/` holds files, not code. A fixture belongs there only when more than one repository uses it. Data that only the core tests use stays in `packages/core/tests/fixtures/`.

| File | What it is |
|---|---|
| `hls/master_two_variants.m3u8` | A master playlist with a 640x360 and a 1280x720 variant, used by `HlsServer` and by the other RayoHX repositories' tests. |
| `hls/ladder.m3u8` | A master playlist with four variants (640x360 up to 1920x1080). |
| `hls/single_segment.m3u8` | A media playlist with one segment. |
| `media/` | Small real MPEG-TS and fragmented MP4 files and two HLS sets, made by FFmpeg with `packages/core/scripts/make_media_fixtures.py`. Used by the core muxer tests. |

## Helpers that stay in core

`packages/core/tests/helpers/` holds the helpers that need the engine's own code, so they cannot move to the plugin: `Origin`, an in-memory HLS origin, and `client_for`, which wires an `HttpClient` to it (`media.py`); `make`, which builds an `HttpClient` on a mock transport (`http.py`); and the muxer helpers `mux_ts`, `read_fragments` and `samples` (`mux.py`).

## Writing a shared helper

- Put it in `packages/pytest/src/rayohx_pytest/` only when another repository needs it; start in `packages/core/tests/helpers/` otherwise.
- Keep it free of `rayohx` imports, so any RayoHX repository can use it.
- Import heavy or rarely needed modules inside the function that uses them, as in the source code. Imports used only in annotations go under `TYPE_CHECKING`.
- Do not add dependencies for it. `make_certificate` imports `cryptography` inside the function so a repository that does not have it can still use `LocalServer`.

## Running

Run only what your change touches, from the repository root:

```text
uv run pytest packages/core/tests/unit/playlist --no-cov                         # one folder of unit tests
uv run pytest -m integration packages/core/tests/integration/test_http_network.py --no-cov
```

The integration tests start local servers on free ports. They need no network access and write only to pytest's temporary folders. Core requires 80% coverage, so a run of a few tests fails on coverage unless you pass `--no-cov`.

## Manual testing

For trying RayoHX against real streams by hand, see [Manual test streams](manual-test-streams.md).
