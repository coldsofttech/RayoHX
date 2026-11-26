# Contributing

Thanks for taking the time to contribute! By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and requesting features

Open an issue using one of the provided forms. Search existing issues first. For security problems, do **not** open an issue; follow [SECURITY.md](SECURITY.md).

## Repository layout

One uv workspace holds two packages under `packages/`, each with its own `src/`:

| Package | What it is |
| --- | --- |
| `core` | The `rayohx` library, with its `tests/` and `scripts/` |
| `pytest` | The `rayohx-pytest` plugin: test servers, certificates and sample streams shared by the RayoHX repositories |

Docs are in `docs/`, and the changelog is the root `CHANGELOG.md`. The command line, Docker image, desktop window and installers live in their own repositories (listed in the [README](README.md#other-ways-to-use-rayohx)).

## Submitting changes

1. Fork the repository and create a branch from `main`.
2. Make your change, keeping it focused on one thing.
3. Set up with [uv](https://docs.astral.sh/uv/): `uv sync`, then `uv run pre-commit install --hook-type pre-commit --hook-type post-commit`.
4. Run the checks for what you changed (below) before you push.
5. Add an entry under `[Unreleased]` in `CHANGELOG.md` (one or two lines, written from a reader's point of view).
6. Open a pull request and fill in the template.

## Checks by area

Run these from the repository root. Scope them to the package you changed rather than running everything.

| You changed | Run |
| --- | --- |
| The library (`packages/core`) | `uv run ruff check packages/core`, `uv run ruff format --check packages/core`, `uv run mypy packages/core/src` and `uv run pytest packages/core/tests`; see [development](docs/development.md) |
| The test plugin (`packages/pytest`) | `uv run ruff check packages/pytest`, `uv run ruff format --check packages/pytest` and `uv run mypy packages/pytest/src`; it has no tests of its own, so also run the core tests |
| Docs or the repository files | `uv run pre-commit run --files <files>` |

See [development](docs/development.md) and [testing](docs/testing.md) for the details.

## Pull request rules

- `main` is protected: changes land through pull requests that are squash-merged.
- Required checks must pass and the branch must be up to date.
- A code owner must review, and all conversations must be resolved.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/), for example `fix: handle empty input`.
