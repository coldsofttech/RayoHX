# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Streams that use playlist variables (`EXT-X-DEFINE`) are now read and downloaded instead of refused.
- Prefer a video codec (`codec`) or dynamic range (`video_range`), and cap the frame rate (`max_frame_rate`), in `SelectionConfig`.
- SOCKS5 proxies (`socks5://`, `socks5h://`), proxies read from the environment with `NetworkConfig(proxy_from_env=True)`, and client certificates for mutual TLS (`client_cert`, `client_key`, `client_key_password`).
- Choose a stream exactly with `variant` (its number in the listing, from 1), `resolution` (such as `1280x720`), `bandwidth` and `variant_name` in `SelectionConfig`. A choice that matches nothing lists the available streams.
- `StorageConfig(check_space=False)` turns off the disk-space check, for drives that report free space wrongly.
- A guide for moving from `pym3u8downloader`.
- Damaged or hostile streams are refused with a clear error instead of crashing: playlists, MPEG-TS, MP4 and subtitles are tested against thousands of corrupted variations.
- A benchmark script (`scripts/benchmark.py`) to compare download speed and memory between changes.
- Read HLS playlists, including audio and subtitle tracks, encryption, byte ranges and fMP4.
- Look at a stream's variants, tracks and encryption from a web address without downloading any media.
- Choose a stream by quality, resolution or bitrate limit, with audio and subtitle selection by language or name.
- Download a stream to a file in one call, with parallel segments, progress events, and a cancelled download returning a result instead of an error.
- Encrypted (AES-128) streams are decrypted; protected (DRM) and live streams are refused with an explanation.
- MPEG-TS streams are saved as `.ts` and fragmented MP4 streams as `.mp4`; a name that does not match is refused instead of mislabelling the file, and an existing file is never replaced unless you allow it.
- Streams with a separate audio track are joined into one MP4 in the chosen language, and MPEG-TS streams can be saved as MP4. The re-wrapping is built in and nothing is re-encoded.
- Subtitles are saved next to the video as `.vtt` files that line up with it.
- An installed FFmpeg is used as an optional fallback for codecs the built-in remuxer cannot copy; it is never required or shipped.
- Segments can be saved as separate files in a folder, and a video-only option downloads just the video of a stream with a separate audio track.
- Interrupted or cancelled downloads continue where they stopped, and need disk space for the video only, not twice that.
- Every segment and the finished file are checked, so an error page, a cut-off file or a wrong key is caught instead of producing a corrupt file.
- Requests retry with back-off, follow redirects, and support proxies, TLS settings, headers, cookies and a speed limit.
- Typed settings, results, progress events and clear errors with hints, and logging that stays silent until you turn it on.
- A cancellation token lets one thread stop work started by others.
- A Python guide describes using RayoHX as a library.

### Security

- Login credentials go only to the starting host and to hosts you list; redirects never carry them elsewhere.
- Secrets such as tokens, cookies and proxy passwords are hidden from logs and error messages.
- Segment names from a stream cannot write outside the download folder, and an existing file is never replaced unless you allow it.
- Unsupported web address schemes and endless redirect loops are refused.
- Damaged or hostile streams are refused with a clear error instead of crashing.
