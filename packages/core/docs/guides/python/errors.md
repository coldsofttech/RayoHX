# Errors

Every error the library raises on purpose derives from `RayoHXError`, so one `except` catches them
all. Errors say what happened and, where possible, what to do about it.

[Back to the Python guide](../python.md)

```python
from rayohx.errors import RayoHXError
```

## The hierarchy

```text
RayoHXError
├── ConfigurationError           an invalid setting or address
├── PlaylistError
│   ├── InvalidPlaylistError     not an HLS playlist, or a broken one (has line)
│   ├── UnsupportedPlaylistError a feature RayoHX refuses (I-frame only, live, DRM)
│   └── PlaylistNotFoundError    HTTP 404 or 410 for a playlist
├── NetworkError                 (has retryable)
│   ├── NetworkConnectionError
│   │   ├── NetworkTimeoutError  a connect, read or overall timeout expired
│   │   └── TLSError             the certificate check failed
│   ├── InvalidResponseError     web page instead of media, empty, cut short, wrong range
│   └── HTTPError                an HTTP error status (has url, status_code, retry_after)
│       └── AuthenticationError  HTTP 401 or 403
├── DownloadError
│   ├── SegmentDownloadError     one segment failed (has index, url)
│   ├── DecryptionError          a segment could not be decrypted, usually a wrong key
│   ├── WorkspaceLockedError     another download is using the same working folder
│   └── InvalidStateTransitionError  an invalid state move
├── OutputError
│   ├── InsufficientStorageError not enough disk space (has required_bytes, available_bytes)
│   ├── OutputExistsError        the output exists and overwriting was not requested
│   ├── OutputFormatError        no way to produce the requested format
│   │   └── UnsupportedCodecError    a codec that cannot be re-wrapped (has codec)
│   └── FinalizationError        joining or validating the data failed
└── CancellationError            the download was cancelled
```

All of them are in `rayohx.errors`.

## What every error has

| Member | Type | Meaning |
|---|---|---|
| `message` | `str` | What went wrong, with addresses and secrets removed |
| `hint` | `str \| None` | What to try next, when there is advice |
| `describe()` | `str` | The message followed by the hint |

Construct one with `Error(message, *, hint=None)`. The exception text (`str(error)`) is the
message.

```python
from rayohx.errors import ConfigurationError

error = ConfigurationError("retries must not be negative.", hint="Use 0 or more.")
print(error.message)  # retries must not be negative.
print(error.hint)  # Use 0 or more.
print(error.describe())  # retries must not be negative. Use 0 or more.
```

Messages never contain credentials: addresses are redacted, so it is safe to log or show
`error.message`.

## Errors with extra members

| Error | Extra members | Constructor |
|---|---|---|
| `InvalidPlaylistError` | `line: int \| None`, the line of the problem | `(message, *, line=None, hint=None)` |
| `NetworkError` and subclasses | `retryable: bool` (property) | `(message, *, hint=None, retryable=None)` |
| `HTTPError` | `url` (redacted), `status_code`, `retry_after` (seconds, or `None`) | `(url, status_code, *, hint=None, retry_after=None)` |
| `SegmentDownloadError` | `index`, `url` (redacted) | `(index, url, reason, *, hint=None)` |
| `InsufficientStorageError` | `required_bytes`, `available_bytes` | `(required_bytes, available_bytes, *, location)` |

### retryable

`NetworkError` and its subclasses say whether trying the same request again could succeed:

| Error | `retryable` by default |
|---|---|
| `NetworkConnectionError`, `NetworkTimeoutError` | `True` |
| `TLSError` | `False` |
| `InvalidResponseError`, plain `NetworkError` | `False`, unless the error says otherwise (a web page served as media, an empty body and a cut-off body are retryable) |
| `HTTPError` | `True` for 408, 425, 429 and 5xx; `False` otherwise |

The HTTP layer already retries what is retryable, up to `NetworkConfig.retries`. By the time you
see the error, retries have been used.

## Where each error comes from

| Raised by | Errors |
|---|---|
| Creating a settings object | `ConfigurationError` |
| `inspect`, `inspect_playlist` | `ConfigurationError`, `PlaylistNotFoundError`, `AuthenticationError`, `InvalidPlaylistError`, `UnsupportedPlaylistError`, `NetworkError` family |
| `parse_playlist` | `InvalidPlaylistError`, `UnsupportedPlaylistError` |
| `CancellationToken.raise_if_cancelled` | `CancellationError` |
| `DownloadStateMachine.move_to` | `InvalidStateTransitionError` |
| `download()` | Raises what went wrong: `ConfigurationError` before it starts; then `UnsupportedPlaylistError` (live, DRM or SAMPLE-AES streams), `OutputFormatError` (a name that does not match the content, or audio and subtitles that cannot be saved as segments), `UnsupportedCodecError`, `OutputExistsError`, `InsufficientStorageError`, `WorkspaceLockedError`, `SegmentDownloadError`, `DecryptionError`, `FinalizationError`, and the `NetworkError` family. A cancelled download returns a result and does not raise |
| `Downloader.run()` | Returns a `FAILED` result instead of raising, and keeps the error in `Downloader.exception`. Raises `DownloadError` if it runs a second time |

## Examples

Handle the common cases and catch the rest:

```python
import rayohx
from rayohx.errors import (
    AuthenticationError,
    InvalidPlaylistError,
    PlaylistNotFoundError,
    RayoHXError,
)

try:
    playlist = rayohx.inspect("https://cdn.example.com/vod/master.m3u8")
except PlaylistNotFoundError as exc:
    print(
        exc.describe()
    )  # The playlist was not found: ... Check the address; the link may have expired.
except AuthenticationError as exc:
    print("Refused with HTTP", exc.status_code)
except InvalidPlaylistError as exc:
    print("Not a playlist:", exc.message)
except RayoHXError as exc:  # anything else the library raises
    print(exc.describe())
```

Retry yourself, with your own policy, only when it makes sense:

```python
from rayohx.errors import NetworkError

try:
    playlist = rayohx.inspect(url)
except NetworkError as exc:
    if exc.retryable:
        schedule_retry(url)
    else:
        raise
```

Show how long a server asked you to wait:

```python
from rayohx.errors import HTTPError

try:
    playlist = rayohx.inspect(url)
except HTTPError as exc:
    if exc.retry_after is not None:
        print(f"Try again in {exc.retry_after:.0f} s")
```

Tell a user to free disk space:

```python
from rayohx.errors import InsufficientStorageError

try:
    run_download()
except InsufficientStorageError as exc:
    short = exc.required_bytes - exc.available_bytes
    print(f"Free {short / 1e9:.1f} GB and try again.")
```

Treat a cancellation as normal, not as a failure:

```python
from rayohx.errors import CancellationError

try:
    run_download()
except CancellationError:
    print("Stopped.")
```

Build your own error with a hint, in the same style:

```python
from rayohx.errors import RayoHXError


class QuotaExceededError(RayoHXError):
    """Your own condition, handled with the rest."""


raise QuotaExceededError("Daily limit reached.", hint="Try again tomorrow.")
```

Read the real HTTP error from a failed segment:

```python
from rayohx.errors import SegmentDownloadError

try:
    run_download()
except SegmentDownloadError as exc:
    print(f"segment {exc.index} failed at {exc.url}")  # the address is redacted
    print(exc.hint)
```
