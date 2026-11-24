# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security

- The image now includes the patched zlib library, fixing a high-severity heap buffer overflow (CVE-2026-85091).

## [0.1.0] - 2026-11-21

### Added

- A Docker image that runs the `rayohx` command for `linux/amd64` and `linux/arm64`. It is small, runs as a normal user, and keeps the output and the resume state in two folders you can mount.
- Every option can be set with a `RAYOHX_` environment variable, and secrets can be read from mounted files, so they stay off the command line.
- Releases are published to GitHub Container Registry as a version tag, plus `latest` for full releases, after a reviewer approves them.
- Documentation for the image: how it is built, developed, packaged and secured.

### Security

- The image runs as an unprivileged user, and holds no compilers, pip or FFmpeg, which keeps what can be attacked small.
- The Dockerfile is checked on every change, and the built image is scanned for known vulnerabilities every week.
- Published images carry build provenance.
