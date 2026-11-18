# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Downloads are now jobs in the platform's persistent queue: they survive a restart of the API, and a job that was running when it stopped continues. `/api/v1/downloads` keeps its behavior on top of the queue. Pausing a download now frees its place in the queue.
- The clean route uses the public `rayohx.storage` module instead of private engine code.

### Added

- `/api/v2`: the queue with priorities, retries, ordering and bulk actions, the job run history, and the saved event log with a server-sent stream that can be resumed with `Last-Event-ID`.
- `RAYOHX_API_HOME` for the queue database folder.
- Every download option of the command line on `/api/v1/downloads`, batches of addresses, playlist text with a base address, saved default options and a per-job engine log.
- `/api/v1` routes to inspect a playlist, run, pause, resume, cancel and follow downloads (with server-sent events), read and change defaults, and clean leftover working folders.
- The `rayohx-api` web service, with health and readiness checks and API-key authentication (or none, for local development).
- Settings through `RAYOHX_API_` environment variables or a `.env` file, JSON logs and consistent error responses.
- Security headers on every response and a limit on request size.
