# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Read HLS playlists, including audio and subtitle tracks, encryption, byte ranges and fMP4.
- Look at a stream's variants, tracks and encryption from a web address without downloading any media.
- Choose a stream by quality, resolution or bitrate limit, with audio and subtitle selection by language or name.
- Download a stream to a file in one call, with parallel segments, progress events, and a cancelled download returning a result instead of an error.
- Encrypted (AES-128) streams are decrypted; protected (DRM) and live streams are refused with an explanation.
- MPEG-TS streams are saved as `.ts` and fragmented MP4 streams as `.mp4`; a name that does not match is refused instead of mislabelling the file, and an existing file is never replaced unless you allow it.
- Segments can be saved as separate files in a folder, and a video-only option downloads just the video of a stream with a separate audio track.
- Interrupted or cancelled downloads continue where they stopped, and need disk space for the video only, not twice that.
- Every segment and the finished file are checked, so an error page, a cut-off file or a wrong key is caught instead of producing a corrupt file.
- Requests retry with back-off, follow redirects, and support proxies, TLS settings, headers, cookies and a speed limit.
- Typed settings, results, progress events and clear errors with hints, and logging that stays silent until you turn it on.
- A cancellation token lets one thread stop work started by others.
- A Python guide describes using RayoHX as a library.
- A license check in CI blocks GPL and AGPL dependencies.

### Security

- Login credentials go only to the starting host and to hosts you list; redirects never carry them elsewhere.
- Secrets such as tokens, cookies and proxy passwords are hidden from logs and error messages.

