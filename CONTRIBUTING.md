# Contributing

Thanks for taking the time to contribute! By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and requesting features

Open an issue using one of the provided forms. Search existing issues first. For security problems, do **not** open an issue; follow [SECURITY.md](SECURITY.md).

## Repository layout

One uv workspace holds five packages under `packages/`, each with its own `src/`, `tests/`, `docs/` and `CHANGELOG.md`:

| Package | What it is |
| --- | --- |
| `core` | The `rayohx` library |
| `cli` | The command line (`rayohx-cli`), built on core |
| `api` | The HTTP API (`rayohx-api`), built on core |
| `ui` | The desktop window (`rayohx-ui`), with the command line and the API |
| `docker` | The container image and its docs |

Shared docs are in `docs/`, and each package's own are in `packages/<package>/docs/`.

## Submitting changes

1. Fork the repository and create a branch from `main`.
2. Make your change, keeping it focused on one thing.
3. Set up with [uv](https://docs.astral.sh/uv/): `uv sync`, then `uv run pre-commit install --hook-type pre-commit --hook-type post-commit`.
4. Run the checks for what you changed (below) before you push.
5. Add an entry under `[Unreleased]` in the `CHANGELOG.md` of the package you changed (one or two lines, written from a reader's point of view).
6. Open a pull request and fill in the template.

## Checks by area

Run these from the repository root. Scope them to the package you changed rather than running everything.

| You changed | Run |
| --- | --- |
| Any Python | `uv run ruff check packages/<package>`, `uv run ruff format --check packages/<package>`, `uv run mypy packages/<package>` and `uv run pytest packages/<package>/tests` |
| The library (`packages/core`) | The Python checks above for `core`; see `packages/core/docs/development.md` |
| The command line (`packages/cli`) | The Python checks above for `cli`; if commands, options or exit codes changed, update the [command line guide](packages/cli/docs/guides/cli.md) |
| The API (`packages/api`) | The Python checks above for `api`, then `uv run python packages/api/scripts/export_openapi.py` and commit `packages/api/docs/openapi.json` |
| The frontend (`packages/ui/src/rayohx_ui/ui`) | `npm ci`, `npm run lint`, `npm test` and `npm run build` in that folder |
| The installers (`packages/cli` or `packages/ui`) | `uv run python packages/<cli or ui>/scripts/build_installer.py --sync --smoke` |
| The Docker image (`packages/docker`) | See `packages/docker/docs/development.md` |

You need Node for frontend work and Windows only to open the real window. The UI's Python tests use a stand-in for the window and run anywhere. See `docs/development.md` and each package's `docs/development.md` for the details.

## Pull request rules

- `main` is protected: changes land through pull requests that are squash-merged.
- Required checks must pass and the branch must be up to date.
- A code owner must review, and all conversations must be resolved.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/), for example `fix: handle empty input`.
