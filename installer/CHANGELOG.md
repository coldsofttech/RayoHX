# Changelog

All notable changes to the Windows installer are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

The setup has its own version, separate from the command line and the desktop app it contains. Each release lists the versions inside it.

## [Unreleased]

### Changed

- The installers ship the command line and the desktop app as compiled code, with no Python source files.

### Added

- One Windows installer, `rayohx-<version>-full-setup.exe`, installs the command line, the desktop app or both.
- Choose to add the command line to PATH or create a desktop shortcut during setup.
- Uninstall either the command line or the desktop app on its own, or both.
