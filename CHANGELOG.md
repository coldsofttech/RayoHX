# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

This file covers the repository as a whole. Each package keeps its own changelog: [core](packages/core/CHANGELOG.md), [cli](packages/cli/CHANGELOG.md), [api](packages/api/CHANGELOG.md), [ui](packages/ui/CHANGELOG.md), [installer](installer/CHANGELOG.md) and [docker](packages/docker/CHANGELOG.md).

## [Unreleased]

### Added

- Shared test helpers and sample streams that the library, command line and API tests all use, so each package no longer keeps its own copy.
- Downloads through the HTTP API accept every engine option, several addresses at once and playlist text, and the window can use files on this computer for them.

### Changed

- The Docker image checks in continuous integration are now an automated test suite instead of a shell script.

## [0.1.0] - 2026-11-21

### Added

- The repository is now a set of five packages (library, command line, API, desktop window and Docker image) that are built, tested, versioned and released separately.
- Continuous integration for each package: linting, type checks, tests on Linux, Windows and macOS, and builds of the installers and the Docker image.
- Release workflows that publish each package and attach its installers. After each full release, the `core-latest`, `cli-latest`, `installer-latest` and `docker-latest` tags and pre-releases move to the new version, so every package has its own latest, and the repository's Latest badge stays on the newest core release.
- Documentation for the whole project and for each package, with guides, architecture notes and a development guide.
- Issue forms, a pull request template, contributing, support and code of conduct pages, and automatic dependency updates.
- Logo and icon artwork in light and dark variants.
- The project is released under the Apache-2.0 licence.

### Changed

- The Linux packages (deb and rpm) are now built and attached with the installer release instead of the command line release.
- The step that decides which parts of the project a pull request changes uses a newer version of its action.

### Security

- Dependencies are audited for known vulnerabilities and checked for disallowed licences on every change.
- Code is scanned for security problems, and commits are scanned for leaked secrets.
- Pull requests are checked for risky new dependencies.
- A security policy explains how to report a vulnerability privately, and each package documents how it protects secrets, requests and the machine it runs on.
