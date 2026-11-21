# CLI security

How the `rayohx` command protects secrets and the machine it runs on. To report a vulnerability, see [SECURITY.md](../../../SECURITY.md). The protections of the download engine itself (redaction, input checks, credentials per host, working folder, file names, FFmpeg, untrusted media) are in the [core security notes](../../core/docs/security.md); the API's are in the [API security notes](../../api/docs/security.md).

## Secrets you give it

- **Read them from a file.** `--header` and `--cookie` accept `@file`, which reads the entries from that file, one per line. The secret then never appears in your shell history or in the process list. Use this for tokens, cookies and `Authorization` headers.
- **Environment variables work too.** Most options can be set with a `RAYOHX_<NAME>` variable, such as `RAYOHX_PROXY`. Treat the variables of a shared shell or CI job like any other secret.
- **The settings file can hold them.** Its keys are option names, so it may contain headers, cookies or a proxy with credentials. Keep it private (permissions to your own account), and prefer `@file` for the secret values.
- **Credentials stay with their host.** Secret headers and cookies go only to the stream's own host and to hosts you list with `--credential-host`, including across redirects.

## What it shows and logs

- **Redaction.** Addresses (user info and the values of keys such as `token`, `sig` and `key`), `Authorization`, `Cookie` and proxy credentials are hidden in messages, errors and log lines, whether they go to the screen or to `--log-file`. The log file records everything down to debug detail, with secrets removed.
- **Errors are short.** A failure prints a message and, where useful, a hint. An unexpected error prints its type and message only.
- **Tracebacks only on request.** `--verbose` adds a traceback, and local variables are never shown, since they can hold secrets.
- **Result and messages are separate.** The saved path goes to stdout and messages go to stderr, so a pipe or a captured result never carries a secret that a message could have contained.
- **A typo in the settings file is an error.** A key that is not an option is refused with a "did you mean" hint, so a setting meant to protect you is never silently ignored.

## Connections

- **Certificates are checked.** `--insecure` turns TLS verification off and the library logs a warning each time it does. Prefer `--ca-bundle` with the right certificate authority.
- **Proxies are explicit.** A proxy is used only when you give `--proxy` (or `RAYOHX_PROXY`). `HTTPS_PROXY` and similar variables are read only with `--env-proxy`.
- **Client certificates.** `--client-cert` is for servers that require mutual TLS. Give the key password through `RAYOHX_CLIENT_KEY_PASSWORD` or a file, not on the command line.
- **Existing files are safe.** An output file is replaced only with `--overwrite`, and a download is written to a `.part` file and renamed when it is complete.

## The installers

- **Per user by default.** The Windows setup installs for the current user and offers all users, which asks for administrator rights. The Linux packages are system-wide and need root.
- **PATH changes go through a script.** The setup adds its folder to `PATH` with a PowerShell script (`path.ps1`) and removes it again on uninstall.
- **Uninstalling is narrow.** It removes only what setup installed, so a folder chosen by hand keeps anything else in it, and your settings and data stay. Removing a Linux package never touches your home folder.
- **Check what you download.** Each release carries `SHA256SUMS.txt`. Installers are unsigned unless the maintainer has set up signing, so Windows may show SmartScreen warnings. Linux packages are not signed. See [packaging and releasing](packaging.md#signing).
- **The Linux packages ship the command and its icons only.** They hold the command, its libraries, the license and the icons, with no compilers, no pip and no FFmpeg.

## Not included

The command runs with your permissions and does not sandbox the media it downloads, so only download from sources you trust and keep FFmpeg, if you use it, up to date. Dependencies are checked by the weekly audit and by dependency review on pull requests (see the [project security notes](../../../docs/security.md#supply-chain)).
