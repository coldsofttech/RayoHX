# Security

A high-level view of how RayoHX is protected. Each package documents its own protections; start there for detail. To report a vulnerability, see [SECURITY.md](../SECURITY.md).

## Packages

| Package | Protects | Notes |
| --- | --- | --- |
| core (`rayohx`) | secrets, requests, files, untrusted media, FFmpeg | [Core security](../packages/core/docs/security.md) |
| CLI (`rayohx`) | secrets you pass, output and logs, the installers | [CLI security](../packages/cli/docs/security.md) |
| API (`rayohx_api`) | requests when run on its own: API key, response headers, request size limit | [API security](../packages/api/docs/security.md) |
| UI (`rayohxu`) | the local window server: host and origin checks, start-up token, content security policy | [UI security](../packages/ui/docs/security.md) |
| Docker | the image: unprivileged user, minimal runtime, no baked-in secrets | [Docker security](../packages/docker/docs/security.md) |

The CLI, API, UI and Docker image all build on the core library, so its protections (redaction, input checks, credentials per host, safe file names) apply to each of them.

## Supply chain

Dependabot covers Python, npm and Actions. Each package has its own audit and security workflows (`audit-<package>.yml`, `security-<package>.yml`) that check locked dependencies weekly and run static analysis. Dependency review blocks vulnerable additions on pull requests, and the lock files are committed. Releases are published with trusted publishing, with no stored token (see [releasing](releasing.md)).

## Rules to keep

- Keep every protection on unless the maintainer says otherwise.
- Document a new protection in the package's `docs/security.md`.
- Explain any `# noqa` or `# nosemgrep` with a reason in the comment.
