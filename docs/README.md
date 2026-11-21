# Documentation

Technical documentation for this project lives in this folder. The top-level [README](../README.md) is for users.

- [Development](development.md): repository layout, tooling and CI.
- [Architecture](architecture.md): how the packages and the checks fit together.
- [Engine design](../packages/core/docs/engine.md): the HLS engine's parts, the FFmpeg-free output approach and licensing rules.
- [Python guide](guides/python.md): using RayoHX as a library: inspecting and downloading streams, settings, events, errors and logging.
- [API](../packages/api/docs/api.md): running the API on its own, settings, endpoints and the OpenAPI contract.
- [UI](../packages/ui/docs/architecture.md): the Windows window, the React frontend and how it talks to Python.
- [Security](security.md): overview of how each package is protected, with links to the package notes.
- Installers: [installer packaging](../installer/docs/packaging.md), the one Windows setup and the Linux packages.
- Packaging: see each package's `docs/packaging.md` ([CLI](../packages/cli/docs/packaging.md), [UI](../packages/ui/docs/packaging.md), [core](../packages/core/docs/packaging.md), [Docker](../packages/docker/docs/packaging.md)).
- [Releasing](releasing.md): publishing, signing, and the Homebrew, Scoop and winget channels.
- [Command line guide](guides/cli.md): using `rayohx` from the terminal: commands, options, settings and exit codes.
- [Benchmarks](../packages/core/docs/benchmarks.md): measuring download speed and memory between changes.
