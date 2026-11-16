# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Choose a stream exactly: `--variant N` (its number in `rayohx info`, from 1), `--resolution 1280x720`, `--bandwidth` and `--variant-name`.
- `--no-space-check` turns off the disk-space check, for drives that report free space wrongly.
- Linux packages (`.deb` and `.rpm`) are also built for ARM64.
- The `rayohx` command: `rayohx info URL` shows a stream's qualities and tracks, and `rayohx download URL` saves it, with progress, `--json` output and settings from a file or `RAYOHX_` environment variables.
