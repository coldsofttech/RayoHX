# Settings

Settings are frozen dataclasses in `rayohx.config` with keyword-only fields. Each one checks itself
when it is created and raises `ConfigurationError` (with a message and a hint), so a bad value fails
early and a settings object that exists is always valid.

[Back to the Python guide](../python.md)

| Class | Purpose |
|---|---|
| [`DownloadConfig`](#downloadconfig) | The top-level object; groups the others |
| [`NetworkConfig`](#networkconfig) | How requests are made |
| [`ProxyConfig`](#proxyconfig) | An HTTP or HTTPS proxy |
| [`SelectionConfig`](#selectionconfig) | Which tracks to take |
| [`OutputConfig`](#outputconfig) | The finished file |
| [`StorageConfig`](#storageconfig) | Where working data lives and how much may pile up |
| [`validate_url`](#validate_url) | Check and clean an http(s) address |

```python
from rayohx.config import (
    DownloadConfig,
    NetworkConfig,
    OutputConfig,
    ProxyConfig,
    SelectionConfig,
    StorageConfig,
    validate_url,
)
```

## Common behavior

- **Frozen.** A settings object cannot change. Use `dataclasses.replace` to make a changed copy:

  ```python
  import dataclasses

  network = NetworkConfig(retries=1)
  patient = dataclasses.replace(network, retries=5)
  ```

- **Validated.** Constructing an invalid object raises `ConfigurationError`:

  ```python
  from rayohx.errors import ConfigurationError

  try:
      SelectionConfig(quality="ultra")
  except ConfigurationError as exc:
      print(exc.describe())
      # quality 'ultra' is not valid. Use best, worst, auto, or a height such as 1080p.
  ```

- **Normalised.** Collections become tuples and read-only mappings; text such as `quality` is
  lower-cased; host names are lower-cased.
- **Serializable without secrets.** Every class has `as_dict()` returning plain Python values,
  with secrets replaced by `***`. See [Secrets](#secrets-stay-out-of-logs).

## DownloadConfig

Everything that shapes a download, grouped by area.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `concurrency` | `int` | `4` | Segments fetched at the same time, from 1 to 64 |
| `resume` | `bool` | `True` | Continue an interrupted download |
| `network` | `NetworkConfig` | `NetworkConfig()` | Requests: headers, timeouts, retries, TLS, proxy |
| `storage` | `StorageConfig` | `StorageConfig()` | Where and how data is kept while downloading |
| `output` | `OutputConfig` | `OutputConfig()` | The finished file |
| `selection` | `SelectionConfig` | `SelectionConfig()` | Which tracks to take |

Method: `as_dict() -> dict[str, Any]`, a serializable view without secrets, safe for logs and resume
state.

Pass it to [`download(config=...)`](downloading.md#download) or `Downloader(config=...)`. The keyword
options of `download()` (such as `quality` or `overwrite`) override the matching fields.

```python
config = DownloadConfig(
    concurrency=8,
    network=NetworkConfig(retries=5, rate_limit=2_000_000),
    selection=SelectionConfig(quality="1080p", audio_languages=("en",)),
)
print(config.network.retries, config.selection.quality)  # 5 1080p
```

`concurrency` outside 1 to 64 raises `ConfigurationError`.

## NetworkConfig

How requests are made.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `headers` | `Mapping[str, str]` | `{}` | Extra request headers. Yours win over the default `User-Agent` |
| `cookies` | `Mapping[str, str]` | `{}` | Cookies sent to trusted hosts only |
| `user_agent` | `str` | `"RayoHX"` | The `User-Agent` header |
| `connect_timeout` | `float` | `10.0` | Seconds to open a connection |
| `read_timeout` | `float` | `30.0` | Seconds to wait for data |
| `total_timeout` | `float \| None` | `None` | Cap on one call, retries included; `None` means no cap |
| `retries` | `int` | `3` | Extra attempts after a retryable failure |
| `backoff_factor` | `float` | `0.5` | The wait between retries grows as `backoff_factor * 2^n` with a little random spread |
| `max_redirects` | `int` | `10` | Redirects followed per request |
| `verify_tls` | `bool \| Path` | `True` | `True` verifies with the default trust store, `False` turns verification off, a `Path` verifies against that CA bundle |
| `proxy` | `ProxyConfig \| None` | `None` | Send requests through this proxy |
| `rate_limit` | `int \| None` | `None` | Download speed cap in bytes per second, shared by all workers |
| `credential_hosts` | `tuple[str, ...]` | `()` | Extra hosts, besides the one the download starts from, allowed to receive secret headers and cookies |

Methods:

| Method | Returns |
|---|---|
| `request_headers()` | The headers to send: the user agent, then your own, which win on a clash |
| `as_dict()` | A serializable view; headers and cookies have their secrets replaced with `***` |

Validation: header names must be valid HTTP tokens and values must not contain line breaks; cookie
names must be non-empty and free of `;`; the user agent must be one non-empty line; timeouts and
`rate_limit` must be greater than zero; `retries`, `backoff_factor` and `max_redirects` must not be
negative; each `credential_hosts` entry must be a bare host name such as `cdn.example.com`, without
scheme or path.

### Retries

Retries cover connection failures, timeouts, HTTP 408, 425, 429 and 5xx, a web page served as
media, an empty body and a body cut short. `Retry-After` is obeyed up to 60 seconds. Other 4xx
answers, a refused certificate, a server that ignores a byte range, a response over the size limit
and an expired overall limit are not retried.

### Credentials stay with their host

Secret headers (`Authorization`, `Cookie`, API keys, anything with token or secret in its name) and
the configured cookies go to the host the download started from and to `credential_hosts`. A
redirect or a segment on another host gets `Referer`, `Origin`, `User-Agent` and other plain
headers, but none of the secrets.

```python
network = NetworkConfig(
    headers={"Authorization": "Bearer ...", "Referer": "https://site.example/"},
    credential_hosts=("keys.example.com",),  # may also receive the Authorization header
)
```

Environment variables such as `HTTPS_PROXY` are not read. Settings come only from the
configuration, so behavior never depends on hidden state.

```python
network = NetworkConfig(user_agent="Agent/1", headers={"user-agent": "Mine", "Origin": "o"})
print(network.request_headers())  # {'user-agent': 'Mine', 'Origin': 'o'}
```

## ProxyConfig

An HTTP or HTTPS proxy. Credentials go in `username` and `password`, or in the URL.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `url` | `str` | required | The proxy address, `http://host:port` or `https://host:port` |
| `username` | `str \| None` | `None` | Sent as proxy authentication |
| `password` | `str \| None` | `None` | Sent as proxy authentication |

| Member | Returns |
|---|---|
| `redacted_url` (property) | The proxy address with any credentials hidden |
| `as_dict()` | A serializable view; username and password are replaced with `***` |

Set both `username` and `password`, or neither. SOCKS proxies are not supported yet. `repr` shows
only `redacted_url`.

```python
proxy = ProxyConfig(url="http://proxy.example:3128", username="me", password="s3cret")
print(proxy)  # ProxyConfig(url='http://proxy.example:3128')
network = NetworkConfig(proxy=proxy)
```

## SelectionConfig

Which tracks to download. The rules are explained in [Selecting tracks](selecting.md).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `quality` | `str` | `"best"` | `best`, `worst`, `auto`, or a height such as `720p` |
| `max_resolution` | `str \| None` | `None` | Largest picture to consider, a height such as `1080p` |
| `max_bitrate` | `int \| None` | `None` | Largest bandwidth in bits per second; must be greater than zero |
| `audio_languages` | `tuple[str, ...]` | `()` | Language codes, in order of preference |
| `audio_names` | `tuple[str, ...]` | `()` | Track names, in order of preference |
| `subtitle_languages` | `tuple[str, ...]` | `()` | Subtitle language codes |
| `subtitle_names` | `tuple[str, ...]` | `()` | Subtitle track names |
| `video_only` | `bool` | `False` | Download only the video stream, leaving out separate audio and subtitle tracks |
| `variant` | `int \| None` | `None` | Stream to download by its number in the listing (the first is 1); cannot be combined with `resolution`, `bandwidth`, `variant_name`, `max_resolution` or `max_bitrate` |
| `resolution` | `str \| None` | `None` | Only streams with exactly this size, such as `1280x720` |
| `bandwidth` | `int \| None` | `None` | Only streams with exactly this bandwidth or average bandwidth, in bits per second |
| `variant_name` | `str \| None` | `None` | Only streams with exactly this name, ignoring case |

Method: `as_dict()` (it includes `video_only` and the exact-choice fields). Language codes must look like `en`, `en-US` or `fil`; names must not be empty.

## OutputConfig

What file is produced and how it is checked.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `path` | `Path \| None` | `None` | Path of the output file; it must not be empty or contain a null character |
| `format` | `OutputFormat` | `OutputFormat.AUTO` | `AUTO`, `TS`, `MP4` or `SEGMENTS` |
| `overwrite` | `bool` | `False` | Replace an existing file. Off by default so a download never destroys data silently |
| `validate` | `bool` | `True` | Check the finished file |
| `remux_backend` | `RemuxBackend` | `RemuxBackend.AUTO` | `AUTO`, `NATIVE` or `FFMPEG` |
| `ffmpeg_path` | `Path \| None` | `None` | Path of an FFmpeg program to use when the backend is `FFMPEG`, or when `AUTO` needs it |

Method: `as_dict()`.

RayoHX does its own container handling and never bundles FFmpeg. It remuxes and never transcodes.
An FFmpeg already installed on the machine is used only for streams the native muxer cannot
handle. See the [engine design](../../engine.md#output-without-ffmpeg).

```python
from pathlib import Path
from rayohx.enums import OutputFormat

output = OutputConfig(path=Path("video.mp4"), format=OutputFormat.MP4, overwrite=False)
```

## StorageConfig

Where working data lives and how much of it may pile up.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `strategy` | `StorageStrategy` | `StorageStrategy.AUTO` | `AUTO`, `DIRECT`, `STREAMING`, `BUFFERED`, `TEMPORARY` or `HYBRID` |
| `workspace_dir` | `Path \| None` | `None` | Folder for working files; `None` lets the engine pick a folder beside the output |
| `buffer_bytes` | `int` | `67108864` | Memory the bounded buffer may hold (64 MiB); must be greater than zero |
| `max_temp_bytes` | `int \| None` | `None` | Most temporary data allowed on disk at once; `None` means no explicit limit |
| `reserve_bytes` | `int` | `268435456` | Free space that must remain after the download (256 MiB); must not be negative |
| `keep_state_on_failure` | `bool` | `True` | Keep resume state after a failure or cancellation |
| `check_space` | `bool` | `True` | Check that the disk has room before and during the download; turn off only when the free-space figure is wrong, for example on some network drives |

Method: `as_dict()`.

The strategies decide where segments that finish early wait for their turn:

| Strategy | Where waiting segments live |
|---|---|
| `DIRECT`, `STREAMING` | Memory, limited to a few segments past the one being written |
| `BUFFERED` | Memory, limited by `buffer_bytes` |
| `TEMPORARY` | Files in the working folder, so every finished segment survives a crash |
| `HYBRID` | Memory first, then files once the memory limit is reached |

`AUTO` writes straight to a file when the output supports resuming, and streams otherwise. In every
case a segment leaves the store the moment it is written, so working storage stays small instead
of growing to the size of the stream.

## validate_url

```python
rayohx.config.validate_url(url: str, *, name: str = "url") -> str
```

Returns `url` stripped, or raises `ConfigurationError` if it is not an absolute `http` or `https`
address (or contains control characters). `name` is the word used in the error message.

```python
validate_url("  https://example.com/master.m3u8  ")  # 'https://example.com/master.m3u8'
validate_url("ftp://x")
# ConfigurationError: url must be an absolute http or https address. Example: https://example.com/master.m3u8
```

## Constants

| Name | Where | Value | Meaning |
|---|---|---|---|
| `rayohx.__version__` | `rayohx` | `"0.1.0"` | The package version |
| `DEFAULT_CONCURRENCY` | `rayohx.config.download` | `4` | Default for `DownloadConfig.concurrency` |
| `MAX_CONCURRENCY` | `rayohx.config.download` | `64` | Upper limit for `DownloadConfig.concurrency` |
| `DEFAULT_USER_AGENT` | `rayohx.config.network` | `"RayoHX"` | Default for `NetworkConfig.user_agent` |

## Secrets stay out of logs

Headers, cookies and proxy passwords are left out of `repr`, and `as_dict()` hides them, so a
settings object is safe to log or store. `DownloadRequest` and `ProxyConfig` show addresses with
their credentials and query tokens removed.

```python
network = NetworkConfig(
    headers={"Authorization": "Bearer abc", "Referer": "https://s"},
    cookies={"sid": "123"},
)
print(network.as_dict()["headers"])  # {'Authorization': '***', 'Referer': 'https://s'}
print(network.as_dict()["cookies"])  # {'sid': '***'}

from rayohx.models import DownloadRequest

request = DownloadRequest(url="https://cdn.example.com/master.m3u8?token=abc", config=config)
print(request.url)  # the address as given
print(request.redacted_url)  # https://cdn.example.com/master.m3u8?token=***
```

Log a whole configuration safely:

```python
import json
import logging

logging.getLogger("myapp").info("settings: %s", json.dumps(config.as_dict()))
```
