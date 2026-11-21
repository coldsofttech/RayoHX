# Security Policy

## Supported versions

Only the latest release of each package (core, command line, API, UI and the Docker image) receives security fixes.

## What is covered

Anything this project ships: the `rayohx` library, the command line, the HTTP API (run on its own), the local server behind the Windows window, the Docker image, and the installers and packages published with each release. Please report problems in the packaged software here, not in the dependencies of it; those go to their own projects.

How each part protects requests, secrets and the machine it runs on is described in [docs/security.md](docs/security.md), which links to the notes of each package:

- [Core](packages/core/docs/security.md)
- [Command line](packages/cli/docs/security.md)
- [API](packages/api/docs/security.md)
- [UI](packages/ui/docs/security.md)
- [Docker](packages/docker/docs/security.md)

## Reporting a vulnerability

Please do **not** report vulnerabilities in public issues.

Use GitHub's private reporting: go to the **Security** tab of this repository and choose **Report a vulnerability**.

Include what you found, how to reproduce it, and the potential impact. You can expect an acknowledgement within a few days and updates as the fix progresses. Once a fix is released, we will credit you if you wish.
