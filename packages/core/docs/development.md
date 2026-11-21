# Core development

How to work on `packages/core`. For how it is built, see [architecture](architecture.md); for using the library, see the [Python guide](guides/python.md). General set-up for the whole repository is in the [project development notes](../../../docs/development.md).

## Set up and run

```bash
uv sync --locked                                  # all packages and the dev tools
uv run python                                     # then: import rayohx
uv run python -c "import rayohx; print(rayohx.inspect('https://example.com/master.m3u8'))"
```

## Checks

Run only what your change touches:

```bash
uv run pytest packages/core/tests/unit --no-cov            # unit tests
uv run pytest -m integration packages/core/tests --no-cov  # real local servers and the installed package
uv run ruff check packages/core
uv run ruff format --check packages/core
uv run mypy packages/core
```

The package's own pytest settings require 80% coverage of `rayohx`, so a run of a few tests fails on coverage unless you pass `--no-cov`. mypy runs in strict mode over `src` and `tests`. CI runs the same commands for this package (`ci-core.yml`), plus pre-commit on its files and a licence check on the dependencies.

## Tests

```text
packages/core/tests/
  conftest.py      marks every test under an integration folder as an integration test
  unit/            one folder per package (config, downloader, playlist, stream, _http, _mux ...),
                   plus tests for single modules such as errors, redaction and serialization
  integration/     the engine against real local servers, and the installed package
  helpers/         small real HTTP servers and builders for playlists, encryption, media and storage
  fixtures/        sample playlists (hls) and small real media files (media)
```

- **Unit tests** follow the source layout: a change in `rayohx/playlist` is tested in `tests/unit/playlist`. Test the pure modules directly.
- **Everything under `integration/`** is marked `integration` automatically, so the default run leaves it out.
- **Use the helpers** instead of mocking the network: they run real HTTP servers on the local machine, so retries, redirects, timeouts and damaged responses are exercised for real.
- **Damaged media.** `unit/test_hardening.py` feeds corrupted input to the parsers and the muxer. For a longer run, set the number of seeds: `RAYOHX_FUZZ_SEEDS=1500 uv run pytest packages/core/tests/unit/test_hardening.py --no-cov`.

## Media test files

The muxer tests use small real MPEG-TS and fragmented MP4 files in `tests/fixtures/media` (about 860 KB), including two complete HLS sets with separate audio. They were made by FFmpeg so that RayoHX's output can be compared with something it did not write. To regenerate them, run `uv run python packages/core/scripts/make_media_fixtures.py` (needs `ffmpeg` with libx264 and libx265).

`ffmpeg` and `ffprobe` are used by some tests only as a reference to compare against, and those tests are skipped when they are not installed. They are never needed to use or build RayoHX.

## Speed

```bash
uv run python packages/core/scripts/benchmark.py              # all scenarios, default size
uv run python packages/core/scripts/benchmark.py --json > before.json
```

The benchmark downloads generated segments from a server on your own machine, so no internet is involved. Use it to compare one change with another on the same machine; see [benchmarks](benchmarks.md).

## Platforms in CI

Tests and integration tests run on Linux (Python 3.11 to 3.15), and on Windows, macOS (Apple silicon and Intel) and Linux ARM64 (Python 3.11). Code must work on all of them, so use `pathlib` and avoid assuming POSIX paths or signals.

## Changing the library

1. Put the logic in the module that owns it (see the module map in [architecture](architecture.md)). Names without a leading underscore are public; add a new public name to the package's `__all__`, and to `rayohx/__init__.py` only if users should reach it from the top.
2. Validate settings in `config/` and raise `ConfigurationError` with a message and a hint, before any request is made.
3. Add unit tests next to the matching folder, and an integration test when the change touches the network or the output files.
4. If you change public behaviour, update the guide in `docs/guides/python/` and the `[Unreleased]` section of `packages/core/CHANGELOG.md`.

## Rules to keep

- The library never prints, exits the process or reads global state. Report through return values, exceptions, events and `logging`. The linter rejects `print` (scripts are the exception).
- Every network request goes through `HttpClient`, and nothing logs or shows a URL, header, key or token without `_redaction` first.
- Keep it typed: public models are frozen, and everything passes strict mypy.
- Import heavy modules inside the function or under `TYPE_CHECKING`, as the existing modules do, so `import rayohx` stays cheap. A public package exposing submodules does so through a lazy `__getattr__`.
- The library never imports a front end (`rayohx_cli`, `rayohx_api`, `rayohx_ui`). The only runtime dependencies are `httpx` and `cryptography`; adding another needs a strong reason.
- Runtime dependencies must be permissively licensed (MIT, BSD, Apache-2.0 and similar); CI runs `pip-licenses` and fails on any GPL-family license. Do not copy code from GPL, LGPL or AGPL projects such as FFmpeg, Bento4 or GPAC; implement from the specifications instead.
- Explain any `# noqa` or `# nosemgrep` with a reason in the comment.

## Building and releasing

```bash
uv build --package rayohx          # the sdist and wheel
```

The version is `__version__` in `src/rayohx/__init__.py`. Bump it and update `packages/core/CHANGELOG.md` in the same pull request; the release workflow (`release-core.yml`) fails if the tag and the version differ. The steps to publish are in [releasing](../../../docs/releasing.md).
