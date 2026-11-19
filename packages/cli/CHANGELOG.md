# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Exit codes:** failures that used to exit `1` can now exit `3`, `4` or `5` by kind, and a batch where some downloads failed exits `7`. Set `RAYOHX_EXIT_CODES=legacy` to get `1` for every failure for one more release.
- `rayohx clean` and the output code use the public `rayohx.storage` and `rayohx.redaction` modules.

### Added

- `rayohx daemon` runs the queue as a service (JSON logs, `/health`, `/ready`, optional `/metrics`, clean stop on SIGTERM) and `rayohx migrate` shows the result of an upgrade from version 1.
- `--non-interactive` (or `RAYOHX_NON_INTERACTIVE`): commands never wait for an answer, and `clean --json`.
- New exit codes `3` verification, `4` authentication, `5` storage, `6` automation and `7` partly failed batch.
- `rayohx storage` (`status`, `workspaces`, `policy`, `cleanup`) and `rayohx diagnostics` (`explain`, `network`, `stream`, `report`, `reports`).
- `--verify`, `--checksum`, `--metadata`, `--title` and `--name-template` on `download` and `queue add`; `queue verification`; and `info --media` for the details of a stream and whether it can be saved in a format.
- `rayohx profile` (list, show, create, edit, duplicate, rename, delete, default, validate, export, import) and `--profile` on `download` and `queue add`. Options you give win over the profile.
- `--format original`, `mkv` and `audio`.
- `rayohx queue`: a download queue that survives restarts (`add`, `list`, `show`, `stats`, `pause`, `resume`, `cancel`, `retry`, `remove`, `clear`, `priority`, `move`, `export`, `import`, `run`).
- `rayohx clean` removes leftover working folders, and `rayohx config` shows the settings in effect.
- Read a playlist from a local file (`rayohx info master.m3u8 --base-url URL`), also for `download`.
- `--events` writes download events as JSON lines on stderr.
- `kill -USR1` pauses and continues a running download (Linux and macOS).
- `--cookie-file` reads a browser-style `cookies.txt`; `--proxy-username` and `--proxy-password` give the proxy login separately.
- `--backoff`, `--max-redirects`, `--reserve-space`, `--keep-state` and `--directory` expose the remaining engine settings.
- Download several streams with one command: `rayohx download URL URL -o folder/` or `--input-file`, with `--stop-on-error`.
- `--codec`, `--video-range` and `--max-frame-rate` to prefer a kind of stream.
- SOCKS5 proxies, `--env-proxy` to use `HTTP_PROXY` and friends, `--client-cert`, `--client-key` and `--client-key-password` for mutual TLS, and `--allow-file-keys`.
- The `rayohx` command: `rayohx info URL` shows a stream's qualities and tracks and what a download would pick, and `rayohx download URL` saves it as one file.
- Choose what to download: a quality (`--quality`, `--max-resolution`, `--max-bitrate`), a stream exactly (`--variant N` from `rayohx info`, counting from 1, `--resolution 1280x720`, `--bandwidth`, `--variant-name`), and audio and subtitle tracks (`--audio`, `--subtitles`, `--video-only`).
- Choose how to save: `--format` (`auto`, `ts`, `mp4` or one file per segment), `--overwrite` and `--validate`. FFmpeg is optional (`--ffmpeg`, `--remux-backend`).
- Network options for protected streams: headers, cookies, user agent, referer, origin, a proxy, TLS settings (`--insecure`, `--ca-bundle`), timeouts, retries and a rate limit. Secret values can be read from a file with `@file`, and credentials go only to the stream's own host and the hosts you list.
- Interrupted downloads continue where they stopped when you run the same command again, and Ctrl-C stops one cleanly.
- A progress bar (or plain lines), `--json` output for other programs, `--quiet`, `--verbose` and `--no-color`, and `--log-file` with secrets removed.
- Defaults from a `rayohx.toml` settings file (or `--config`) and `RAYOHX_` environment variables, with exit codes 0, 1, 2 and 130.
- `--no-space-check` turns off the disk-space check, for drives that report free space wrongly.
- A Windows setup (with an optional `PATH` entry) and a portable zip, and Linux `.deb` and `.rpm` packages for x86_64 and ARM64 with an icon.
- The command is also available as the `rayohx-cli` package.
