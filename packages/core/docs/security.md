# Core security

How the `rayohx` library protects secrets, requests and the machine it runs on. To report a vulnerability, see [SECURITY.md](../../../SECURITY.md). How the command line handles secrets, output and its installers is in the [CLI security notes](../../cli/docs/security.md), and the API's protections are in the [API security notes](../../api/docs/security.md).

## Secrets you give it

- **Settings hide them.** `repr` and `as_dict()` of the settings leave out header values, cookie values and proxy passwords. Resume state must be built from `as_dict()`, never from the raw objects.
- **Credentials stay with their host.** Secret headers and configured cookies go only to the starting host and the hosts listed in `credential_hosts`, including across redirects.
- **Keys stay in memory.** Decryption keys are never written to disk, and never appear in resume state.

## What it shows and logs

- **Redaction.** URLs (user info and the values of keys such as `token`, `sig` and `key`), `Authorization`, `Cookie` and proxy credentials are hidden in log records and error messages by `rayohx._redaction`. Every exception message and every handler added by `configure_logging` goes through it, including formatted tracebacks.
- **Errors carry a message and a hint,** not the request that failed.

## Input checks

- Download addresses must be absolute `http` or `https` URLs without control characters.
- Header names must be valid tokens, and header and cookie values cannot hold line breaks, which stops header injection.
- Proxies must be `http` or `https`, and redirect targets must be `http` or `https`.
- **Address guard.** Every request address, including redirect targets, can be vetted by a `url_guard` function, which keeps protection against server-side request forgery possible when the library is used in a server.

## Connections

- **Certificates are checked.** TLS verification is on by default, and a warning is logged whenever it is turned off.
- **Proxies are explicit.** Proxy settings and environment variables such as `HTTPS_PROXY` are not read implicitly.
- **Responses are limited.** A playlist may be at most 32 MiB, and a single media request 512 MiB by default.
- **Every request goes through `HttpClient`,** so these protections cannot be skipped by a new code path.

## Files and folders

- **Working folder.** Its name is a hash of the address and output name, never user input, so it cannot point elsewhere. It is created readable by the current user only, where the system allows, and locked while in use. Resume state holds a fingerprint, counters and a redacted address, never headers, cookies or keys.
- **File names.** Names made from an address contain only letters, digits, dots, dashes and underscores, never start with a dot, never contain a path separator and are never Windows device names, so a hostile address cannot write outside the chosen folder. A name you give is used as given, but its extension must match the content.
- **Existing files are safe.** An existing output file is never replaced unless `overwrite` is on. Output is written to a `.part` file and renamed only when complete.
- **Temporary files.** Separate audio tracks and FFmpeg inputs are saved as hidden files beside the output (never in a shared temporary folder) and removed on success, failure and cancellation.

## Untrusted media

- **Parsers check what they read.** The demuxer and codec parsers read untrusted data, so every length and count is checked against the data actually present, and malformed headers raise a clear error instead of reading past the end. Buffered data waiting for another track is capped at 64 MiB.
- **Fuzzed.** The playlist parser, the transport stream and MP4 readers, the codec parsers and the subtitle merger are fuzzed with repeatable damage (flipped, cut, removed and inserted bytes, and random data) in `tests/unit/test_hardening.py`. Damaged input ends in one of the engine's own errors, never an unhandled exception or an endless loop, and implausible timestamps are ignored instead of breaking the output file. Run it longer with `RAYOHX_FUZZ_SEEDS=1500`.
- **No DRM claim.** Only plain AES-128 is decrypted. SAMPLE-AES and DRM key formats are refused before downloading.

## FFmpeg

FFmpeg is optional and never bundled. When it is used, it is started without a shell, with a fixed argument list built from paths RayoHX chose itself, no standard input, and only on files already downloaded. It is only asked to copy streams, never to transcode. Its output is shown with secrets removed, and it is stopped at once if the download is cancelled. It is found only on the `PATH` or at a path the user configures.

## Checked end to end

`tests/integration/test_security_end_to_end.py` shows over real sockets that:

- credentials are not sent to another host after a redirect
- redirects to `file:` and other schemes are refused, and redirect loops end
- segment addresses with `../` cannot write outside the output folder
- an existing file survives a failed download
- the output and log never contain a token, header or cookie

## Not included

The library does not sandbox the media it downloads: it checks it, but it runs with the permissions of the program using it. Download only from sources you trust, and keep FFmpeg, if you use it, up to date. A program that lets other people choose the address should set a `url_guard`, restrict `credential_hosts`, and run the download with limited permissions.

## Supply chain

The library depends only on `httpx` and `cryptography`. Dependabot covers its dependencies, `audit-core.yml` audits the locked dependencies weekly, `security-core.yml` runs Semgrep, and dependency review blocks vulnerable additions on pull requests. The lock file is committed. The release is published with trusted publishing, with no stored token (see [packaging](packaging.md#releasing-to-pypi)).

## Rules to keep

- Keep every protection on unless the maintainer says otherwise, and document a new one here.
- Never log or show a URL, header, key or token without `_redaction` first.
- Explain any `# noqa` or `# nosemgrep` with a reason in the comment.
