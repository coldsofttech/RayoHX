# CLI development

How to work on `packages/cli`. For how it is built, see [architecture](architecture.md); for using the command, see the [command line guide](guides/cli.md). General set-up for the whole repository is in the [project development notes](../../../docs/development.md).

## Set up and run

```bash
uv sync --locked                                  # all packages and the dev tools
uv run rayohx --help                              # the command, from your checkout
uv run rayohx info https://example.com/master.m3u8
uv run python -m rayohx_cli download --help       # the same thing, as a module
```

The module form works here because development runs the plain Python sources. The compiled wheel a release ships has no `python -m rayohx_cli`; use the `rayohx` command there.

## Checks

Run only what your change touches:

```bash
uv run pytest packages/cli/tests/unit --no-cov            # unit tests
uv run pytest -m integration packages/cli/tests --no-cov  # real process and local servers
uv run ruff check packages/cli
uv run ruff format --check packages/cli
uv run mypy packages/cli/src
```

The package's own pytest settings require 80% coverage of `rayohx_cli`, so a run of a few tests fails on coverage unless you pass `--no-cov`. CI runs the same commands per package (`ci-cli.yml`), plus pre-commit on the package's files.

## Tests

```text
packages/cli/tests/
  conftest.py      fixtures shared by all tests: a clean environment, restored logging,
                   a CliRunner, a fake download, and the marker for integration tests
  unit/            commands through typer.testing.CliRunner, and the pure modules
  integration/     the installed command as a real process against a real local server,
                   and the built (frozen) executable
  helpers/         small real HTTP servers, a fake web site and test media
  frozen.py        finds the executables PyInstaller built
```

- **Unit tests** call the app with the `runner` fixture and check the exit code, stdout and stderr. Test the pure modules (`values`, `format`, `settings`) directly.
- **Everything under `integration/`** is marked `integration` automatically, so the default run leaves it out.
- **The frozen tests** need a PyInstaller build first (`uv run python installer/scripts/build.py`). Without one they are skipped. Set `RAYOHX_INSTALLER_DIR` to test a build somewhere other than `build/installer`.
- **The conftest** removes `RAYOHX_*` variables and settings files from the machine, so a test never depends on the developer's own set-up.

### Smoke test the compiled build

`scripts/smoke/` builds the compiled wheel (a single `.pyd` plus type stubs) and tries it in a
fresh virtual environment. It is a manual check, separate from the pytest suites, and it needs
network access and a C compiler. The scripts are PowerShell, so the check runs on Windows, and
`setup_venv.ps1` expects Python 3.11 (`py -3.11`). It installs the compiled core wheel, so run
core's smoke `setup_venv.ps1` first.

```powershell
./scripts/smoke/setup_venv.ps1   # builds the wheel and installs it into scripts/smoke/.venv
./scripts/smoke/test_cli.ps1     # runs `rayohx info` from the installed build
```

`test_cli.ps1` runs `rayohx info` on the **first line** of `scripts/smoke/test_links.txt` and fails
if the command exits with an error. To try another stream, put its URL on the first line of that
file; any further lines are ignored. `test_links.txt` is kept in the repository, so use a stream
you are allowed to share.

The virtual environment, `wheels/`, `data/` and logs under `scripts/smoke/` are git-ignored.

## Adding an option

1. Define it once in the right file in `params/` (selection, network, engine, output or display) and put it in that file's help panel.
2. Add it to the signature of each command that takes it, and pass it to `make_config(...)` in that command.
3. Handle it in `values.build_config`, and raise `ConfigurationError` for a bad value so it becomes a usage error.
4. The environment variable `RAYOHX_<NAME>` and the settings-file key work automatically, because both use the option's name.
5. Add unit tests for the value handling and for the command.
6. Update the guide in `docs/guides/cli/` and the `[Unreleased]` section of `packages/cli/CHANGELOG.md`.

## Adding a command

1. Add a module in `cli/` with a function decorated by `@app.command()`, and import it in `cli/__init__.py` so it registers.
2. Reuse the options in `params/`, build settings with `make_config`, and call the library for the work. Keep the command to parsing and showing.
3. Print through `output` only: the result with `output.data` or `output.print_json`, everything else with `output.message` and `output.error_from`.
4. End with one of the exit codes in `cli/common.py`.
5. Document it in `docs/guides/cli/` and the changelog.

## Rules to keep

- No `print`: the linter rejects it, and `output` keeps data on stdout and messages on stderr.
- Keep Typer's Rich help: `rich_markup_mode="rich"` on every Typer app, and escape literal square brackets in help text with a backslash.
- Never show local variables in an error, and never put headers, cookies, keys or tokens in output or logs.
- The library does the work and never imports the command line. If you need logic in the command, it probably belongs in `rayohx`.
- Explain any `# noqa` or `# nosemgrep` with a reason in the comment.

## Building the installers

```bash
uv sync --group installer
uv run python installer/scripts/build.py --smoke                   # everything this OS can build
uv run python installer/scripts/build.py --format deb,rpm --smoke  # on Linux
```

The installer files are in the root `installer/` folder; see [installer packaging](../../../installer/docs/packaging.md) and [packaging](packaging.md) for the tools you need and what each file does.
