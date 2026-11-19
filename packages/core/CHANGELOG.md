# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Platform (unstable)

The platform is the new `rayohx.platform` package: persistent services around the engine. It is not part of the engine's stable API until its first release. See `docs/platform.md`.

- `Rayo`, the platform's entry point (`from rayohx import Rayo`), with a local SQLite database (migrations, backup before upgrade, recovery from a damaged file), shared folders (including portable mode and `RAYOHX_HOME`), a saved event log, and a small settings store.
- Platform events remove secrets from every payload before saving or delivering them.
- A persistent download queue (`rayo.queue`): priorities, an explicit order, several jobs at once, pause and resume that give up the slot and keep the work, cancel, retry, bulk actions, export and import. Jobs survive restarts and crashes, and a failure never affects other jobs.
- Failed jobs are retried after a growing delay when the error may pass; every run is recorded.
- Job secrets (cookies, secret headers, proxy credentials) are kept in a secret store (system credential store with the optional `keyring` package, else memory) and never in the database.
- Storage management (`rayo.storage`): free-space thresholds with hysteresis, admission with reservations, automatic pause and resume, `STORAGE_LOW` stop, low-storage mode, workspace ownership, a safe cleanup planner and a storage snapshot.
- Diagnostics (`rayo.diagnostics`): failure explanations for every stable code, network and stream checks, retry history, and sanitized reports. `rayo.metrics()` and Prometheus text.
- The engine emits a `workspace_opened` event with the folder it works in; `rayohx.storage` gains `disk_usage`.
- Download profiles (`rayo.profiles`): five built in (Best Quality, 1080p, Mobile, Archive, Custom) and your own, with validation, a default profile, file name templates, import and export. `rayo.queue.add(url, profile=..., overrides=...)` copies the settings into the job.
- `DownloadConfig` can be saved as plain data and rebuilt (`rayohx.platform.jobs.config_to_options`, `config_from_options`).

### Fixed

- Audio-only output made by FFmpeg now really is the container its extension says (an `.m4a` was a Matroska file).

### Added

- Verification: `VerifyConfig` (`none`, `basic`, `strong`, an optional checksum or expected checksum) checks the finished file. A download goes through `VERIFYING`, returns an `IntegrityReport` (every check, and what could not be done), and a file that fails is renamed `.invalid` and fails the download with `VERIFICATION_FAILED`. Segments cut off mid-packet or mid-box are refused in `strong`. Nothing is hashed unless asked.
- `rayohx.media`: `inspect_media` (codecs, profile and level, frame rate, tracks, size as exact, estimated or unavailable, and metadata), `check_compatibility`, and `probe_file` (ffprobe).
- Metadata: `MetadataConfig` (`none`, `minimal`, `preserve`, `custom`) writes the title, description, language, chapters and cover picture into Matroska, audio and FFmpeg-made MP4 files, and says when a file cannot hold them. The playlist parser reads `EXT-X-SESSION-DATA` and `EXT-X-DATERANGE`.
- `OutputConfig.name_template` names a file from the stream (`{title}`, `{language}`, `{name}`, `{date}`, `{time}`, `{host}`).
- Output formats `original` (the stream's own container, untouched), `mkv` (Matroska) and `audio` (only the sound, as `.m4a`, `.mp3`, `.ac3`, `.eac3` or `.mka` to suit the codec). `mkv` and `audio` need FFmpeg, which only copies the streams, and are refused before any download when it is missing. Audio-only from a separate audio track never fetches the video.
- `OutputInfo.processing` (`copied`, `remuxed`, `muxed`, `extracted`) and `rayohx.capabilities` to find out what this machine can do.
- `audio_languages=("*",)` and `subtitle_languages=("*",)` select every audio or subtitle track.
- `rayohx.naming` with the file name helpers.
- Every error has a stable `code` and an `ErrorCategory` (`error.code`, `error.category`); HTTP errors include the status (`HTTP_503`, `AUTH_403`).
- A `VERIFYING` download state between finalizing and completed. Nothing enters it yet.
- The public modules `rayohx.storage` (find, measure and clean working folders) and `rayohx.redaction`, so front ends no longer import private modules.
- SOCKS5 proxies (`socks5://`, `socks5h://`), proxies from the environment with `NetworkConfig(proxy_from_env=True)`, and client certificates (`client_cert`, `client_key`, `client_key_password`) for servers that require mutual TLS.
- Playlist variables (`EXT-X-DEFINE` with `NAME`/`VALUE`, `QUERYPARAM` and `IMPORT`) are read instead of refused.
- Prefer a `codec`, a `video_range` (`sdr`, `pq`, `hlg`, `hdr`) and a `max_frame_rate` when choosing a stream.
- AES-128 keys from `data:` addresses, from `file:` addresses with `allow_file_keys`, or from your own `key_fetcher`.
- `download_many` downloads several streams in one call, and `OutputConfig(directory=...)` sets the folder for unnamed outputs.
- `Downloader.pause()` and `resume()`, with `DOWNLOAD_PAUSED` and `DOWNLOAD_RESUMED` events.
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
