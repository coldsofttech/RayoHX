# Testing

How the tests are organized, and what lives in the repository-wide `tests/` folder.

## Where tests live

Each package keeps its own tests in `packages/<name>/tests/`:

```text
tests/unit/          fast tests, run by default; one test file per source module
tests/integration/   slower end-to-end tests over real sockets or real processes
tests/helpers/       helpers used only by this package
tests/fixtures/      data files used only by this package
```

Anything in an `integration` folder is marked `integration` automatically and is skipped by a normal `pytest` run. Run it with `-m integration`, for example `uv run pytest -m integration tests/integration`.

## Shared tests folder

Anything more than one package needs lives in the repository's own `tests/` folder, so it is written once:

```text
tests/
  fixtures/   data files that several packages read
  helpers/    code that several packages import
```

### Fixtures

`packages/pytest/src/rayohx_pytest/data/` holds files, not code. A fixture is shared only when two or more packages use it. Data that only one package uses stays in that package's `tests/fixtures/`; for example the core engine keeps its malformed playlists and real TS and fMP4 samples.

| File | What it is |
|---|---|
| `hls/master_two_variants.m3u8` | A master playlist with a 640x360 and a 1280x720 variant. Used by the API's route tests and by the live API tests. |
| `hls/ladder.m3u8` | A master playlist with four variants (640x360 up to 1920x1080), used by the command line tests. |
| `hls/single_segment.m3u8` | A media playlist with one segment, used by the command line tests. |
| `media/` | Small real MPEG-TS and fragmented MP4 files and two HLS sets, made by FFmpeg with `packages/core/scripts/make_media_fixtures.py`. Used by the core muxer tests and the command line tests. |

Read a fixture with `rayohx_pytest.fixtures` (below), not with a path built from `__file__`, so a test keeps working if it moves.

### Helpers

`packages/pytest` (the `rayohx-pytest` distribution, import name `rayohx_pytest`) holds the shared test code. It is a pytest plugin installed with the workspace, so its fixtures need no import: `local_server` (a factory that starts a real HTTP server and stops it after the test), `tls_certificate` and `ts_payload`. The classes behind them are importable for types and routes:

```python
from rayohx_pytest.plugin import ServerFactory
from rayohx_pytest.servers import Reply, Seen
from rayohx_pytest.hls import vod_routes, expected
```

It is not published to PyPI. Other repositories take it from git as a development dependency; see its [README](../packages/pytest/README.md).

| Module | What it gives you |
|---|---|
| `servers` | `LocalServer`: a real threaded HTTP/1.1 server (optionally TLS) with routes by path, per-reply delays and a log of every request. Also `Reply`, `Seen`, `Route` and `make_certificate`. |
| `media` | `ts_payload`: MPEG-TS packets that pass the engine's sync-byte check. |
| `hls` | A small VOD stream on top of `LocalServer`: `vod_routes(count, delay=, gate=)` serves `/index.m3u8` and `/seg<N>.ts`; `expected(count)` is what a finished download contains; `segment_index` tells which segment a request asked for. A `gate` holds segments until a test sets it, to stop a download at a known point. |
| `fixtures` | `fixture_path`, `fixture_text` and `fixture_bytes` for the files in `rayohx_pytest/data/`. |

Package-specific helpers stay in the package. For example `packages/api/tests/helpers/live.py` starts the real API as a subprocess (`ApiProcess`) and extends `LocalServer` with a master playlist (`HlsServer`).

## Writing a shared helper

- Put it in `packages/pytest/src/rayohx_pytest/` only when a second package needs it; start in the package otherwise.
- Keep it free of package imports (`rayohx`, `rayohx_cli`, `rayohx_api`), so any package can use it.
- Import heavy or rarely needed modules inside the function that uses them, as in the source code. Imports used only in annotations go under `TYPE_CHECKING`.
- Do not add dependencies for it. `make_certificate` imports `cryptography` inside the function so packages that do not have it can still use `LocalServer`.

## Running

Run only what your change touches, from the package folder:

```text
cd packages/api
uv run pytest tests/unit/routers                                  # one folder of unit tests
uv run pytest -m integration tests/integration/test_downloads_live.py
```

The integration tests start local servers on free ports and, for the API, a real `rayohx_api` process. They need no network access and write only to pytest's temporary folders.

## Manual testing

For trying RayoHX against real streams by hand, see [Manual test streams](manual-test-streams.md).
