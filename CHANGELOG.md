# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Read HLS playlists, including audio and subtitle tracks, encryption, byte ranges and fMP4.
- Look at a stream's variants, tracks and encryption from a web address without downloading any media.
- Choose a stream by quality, resolution or bitrate limit, with audio and subtitle selection by language or name.
- Requests retry with back-off, follow redirects, and support proxies, TLS settings, headers, cookies and a speed limit.
- Typed settings, results, progress events and clear errors with hints, and logging that stays silent until you turn it on.
- A cancellation token lets one thread stop work started by others.
- A Python guide describes using RayoHX as a library.
- A license check in CI blocks GPL and AGPL dependencies.
- The groundwork for downloading is built but not yet available as a public call: parallel segments, AES-128 decryption, storage strategies with disk-space checks, and resuming.

### Security

- Login credentials go only to the starting host and to hosts you list; redirects never carry them elsewhere.
- Secrets such as tokens, cookies and proxy passwords are hidden from logs and error messages.

