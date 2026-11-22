# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A Fluent UI interface in the RayoHX brand colours (slate with orange, red and yellow), with light and dark themes: add and inspect a stream, follow downloads live, and settings and clean-up.
- The RayoHX desktop window for Windows, started with `rayohxu`, with the HTTP API built in.
- The parallel segments slider now spans the range the engine accepts, instead of a fixed 1 to 16.
- Files on this computer, such as cookie files and certificates, can be used for downloads in the window.
- Your download list and concurrency setting are kept between restarts, and a download cut short by closing the app shows as failed.
- A clear history button removes finished downloads, and a retry button restarts one that failed.
- Each download shows the quality it was started with.
- Requires Python 3.15 or newer.
