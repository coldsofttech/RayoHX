# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `inspect(url)` shows a stream's variants and tracks without downloading it, with retries, redirects, proxy and TLS settings.
- A network setting lists extra hosts that may receive login credentials; other hosts never get them.
- Download a stream's segments in parallel into one file, with AES-128 decryption, a choice of storage strategies and disk-space checks.
- Interrupted or cancelled downloads can continue where they stopped.
- Reading HLS playlists, including audio and subtitle tracks, encryption, byte ranges and fMP4.
- Choosing a stream by quality, resolution or bitrate limit, with audio and subtitle selection by language or name.
- Inspecting a stream's playlist, tracks and encryption without downloading any media.
- Typed settings, results, progress events and clear errors for the downloader library.
- Secrets such as tokens, cookies and proxy passwords are hidden from logs and error messages.

### Changed

- The library is now imported as `rayohx`.
- The command line tool is now run as `rayohx` (it was `rayohx-cli`), and its options read `RAYOHX_VERBOSE`, `RAYOHX_QUIET` and `RAYOHX_NO_COLOR`.
- A license check in CI blocks GPL and AGPL dependencies.
