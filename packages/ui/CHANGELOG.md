# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-24

### Added

- Save default options for every download from Settings, and read a per-download log of what happened.
- An Open folder button on Downloads shows the download folder in Explorer.
- When a download fails because the file already exists, an Overwrite button replaces it and starts the download again.
- After inspecting a stream, choose how to pick it with Quick (a quality) or Advanced (a stream, size, bitrate, codec, range and tracks from what the stream offers), with one Download button. Audio and subtitle choices show only when the stream has them.
- Choose the folder downloads are saved in from Settings. It, the theme and your other defaults are remembered between restarts.
- A Fluent UI interface in the RayoHX brand colours (slate with orange, red and yellow), with light and dark themes: add and inspect a stream, follow downloads live, and settings and clean-up.
- The RayoHX desktop window for Windows, started with `rayohxu`, with the HTTP API built in.
- The parallel segments slider now spans the range the engine accepts, instead of a fixed 1 to 16.
- Files on this computer, such as cookie files and certificates, can be used for downloads in the window.
- Your download list is kept between restarts, and a download cut short by closing the app shows as failed.
- A clear history button removes finished downloads, and a retry button restarts one that failed.
- Each download shows the quality it was started with.
- Every download option is available in the window, and you can download several streams at once or paste playlist text.
- Requires Python 3.15 or newer.
