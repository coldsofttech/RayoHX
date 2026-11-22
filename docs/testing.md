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

`tests/fixtures/` holds files, not code. A fixture is shared only when two or more packages use it. Data that only one package uses stays in that package's `tests/fixtures/`; for example the core engine keeps its malformed playlists and real TS and fMP4 samples.

| File | What it is |
|---|---|
| `hls/master_two_variants.m3u8` | A master playlist with a 640x360 and a 1280x720 variant. Used by the API's route tests and by the live API tests. |

Read a fixture with `rayohx_testing.fixtures` (below), not with a path built from `__file__`, so a test keeps working if it moves.

### Helpers

`tests/helpers/` holds the shared test code. Its one package, `rayohx_testing`, is on the import path of every package through the `pythonpath` setting in each `pyproject.toml` (and in the root one), so a test imports it directly:

```python
from rayohx_testing.servers import LocalServer, Reply
from rayohx_testing.hls import vod_routes, expected
```

It is named `rayohx_testing` because every package already has a `tests` package of its own, and a second one with the same name would clash.

| Module | What it gives you |
|---|---|
| `servers` | `LocalServer`: a real threaded HTTP/1.1 server (optionally TLS) with routes by path, per-reply delays and a log of every request. Also `Reply`, `Seen`, `Route` and `make_certificate`. |
| `media` | `ts_payload`: MPEG-TS packets that pass the engine's sync-byte check. |
| `hls` | A small VOD stream on top of `LocalServer`: `vod_routes(count, delay=, gate=)` serves `/index.m3u8` and `/seg<N>.ts`; `expected(count)` is what a finished download contains; `segment_index` tells which segment a request asked for. A `gate` holds segments until a test sets it, to stop a download at a known point. |
| `fixtures` | `fixture_path`, `fixture_text` and `fixture_bytes` for the files in `tests/fixtures/`. |

Package-specific helpers stay in the package. For example `packages/api/tests/helpers/live.py` starts the real API as a subprocess (`ApiProcess`) and extends `LocalServer` with a master playlist (`HlsServer`).

## Writing a shared helper

- Put it in `tests/helpers/rayohx_testing/` only when a second package needs it; start in the package otherwise.
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
