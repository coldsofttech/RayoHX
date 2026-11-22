# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `/api/v1` routes to inspect a playlist, run, pause, resume, cancel and follow downloads (with server-sent events), read and change defaults, and clean leftover working folders.
- The `rayohx-api` web service, with health and readiness checks and API-key authentication (or none, for local development).
- Settings through `RAYOHX_API_` environment variables or a `.env` file, JSON logs and consistent error responses.
- Requires Python 3.15 or newer.
- Security headers on every response and a limit on request size.
