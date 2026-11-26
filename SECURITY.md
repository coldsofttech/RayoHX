# Security Policy

## Supported versions

Only the latest release of the `rayohx` library receives security fixes. The command line, Docker image, desktop window and installers are released from their own repositories, which have their own security policies.

## What is covered

Anything this repository ships: the `rayohx` library. Please report problems in the packaged software here, not in the dependencies of it; those go to their own projects. The `rayohx-pytest` test plugin is for development only and is not published.

How the library protects requests, secrets and the machine it runs on is described in [docs/security.md](docs/security.md).

## Reporting a vulnerability

Please do **not** report vulnerabilities in public issues.

Use GitHub's private reporting: go to the **Security** tab of this repository and choose **Report a vulnerability**.

Include what you found, how to reproduce it, and the potential impact. You can expect an acknowledgement within a few days and updates as the fix progresses. Once a fix is released, we will credit you if you wish.
