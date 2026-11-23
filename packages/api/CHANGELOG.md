# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-23

### Added

- Default options for new downloads can be saved and are used unless a download sets its own; logins and passwords are never saved.
- Each download has a log of what the engine reported (the last 200 lines, kept between restarts), and says whether it has one (`has_log`).
- A failed download reports an `error_code` (such as `output_exists`), and retry can replace an existing file for that run with `overwrite`.
- The download folder and theme are saved between restarts, and the folder can be changed from the window.
- The download list is now saved between restarts, and a new call clears finished downloads. Downloads cut short by a restart show as failed. Where they are kept can be set with `RAYOHX_API_DB_PATH`.
- `/api/v1` routes to inspect a playlist, run, pause, resume, cancel and follow downloads (with server-sent events), read and change defaults, and clean leftover working folders.
- The `rayohx-api` web service, with health and readiness checks and API-key authentication (or none, for local development).
- Settings through `RAYOHX_API_` environment variables or a `.env` file, JSON logs and consistent error responses.
- Every engine option can be set when starting a download, grouped as network, selection, storage, output and engine settings.
- Several addresses can be started at once, and a playlist you already have as text can be inspected or downloaded.
- The settings endpoint reports the fewest and most parallel segments the engine accepts, so clients need not hard-code them.
- Settings that point at files on the server are refused unless `RAYOHX_API_ALLOW_LOCAL_PATHS` is on.
- Requires Python 3.15 or newer.
- Security headers on every response and a limit on request size.

### Changed

- Quality, concurrency and replace-existing are no longer separate settings; they are now part of the saved default options.
