# Documentation

Technical documentation for this project lives in this folder. The top-level [README](../README.md) is for users.

- [Development](development.md): repository layout, tooling and CI.
- [Architecture](architecture.md): how the library and the checks fit together.
- [Testing](testing.md): how tests are organized, and the shared `rayohx-pytest` plugin.
- [Manual test streams](manual-test-streams.md): public HLS streams for trying RayoHX by hand, with what each one covers.
- [Engine design](engine.md): the HLS engine's parts, the FFmpeg-free output approach and licensing rules.
- [Python guide](guides/python.md): using RayoHX as a library: inspecting and downloading streams, settings, events, errors and logging.
- [Migration guide](guides/migration.md): moving from `pym3u8downloader`.
- [Security](security.md): how the library is protected.
- [Packaging and releasing](packaging.md): building the compiled wheels and publishing a release to PyPI.
- [Benchmarks](benchmarks.md): measuring download speed and memory between changes.
