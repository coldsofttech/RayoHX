# Logging

The library writes only to loggers under the name `rayohx` and adds no handlers of its own, so it
stays silent until your application asks for logs. It never configures the root logger.

[Back to the Python guide](../python.md)

## configure_logging

```python
rayohx.configure_logging(
    level: int | str = logging.INFO,
    *,
    console: bool = True,
    log_file: Path | str | None = None,
) -> logging.Logger
```

Sends `rayohx` log records to stderr and, optionally, to a file. It returns the `rayohx` logger.

| Parameter | Meaning |
|---|---|
| `level` | A level number (`logging.DEBUG`) or name (`"DEBUG"`). Default `INFO` |
| `console` | Write to **stderr**. Never stdout, so logs cannot mix with output you pipe. Default `True` |
| `log_file` | Also (or only) write to this file, UTF-8. Missing folders are created |

Calling it again replaces the handlers it added before, so it is safe to repeat, for example when a
`--verbose` option changes the level.

```python
import rayohx

rayohx.configure_logging("DEBUG")  # to stderr
rayohx.configure_logging("INFO", log_file="rayohx.log")  # stderr and a file
rayohx.configure_logging("INFO", console=False, log_file="rayohx.log")  # file only
```

Every line has the same shape:

```text
2026-11-16 09:30:12,345 INFO     [d1a2b3c4d5e6] rayohx.http: Attempt 1 of 4 failed (...). Retrying ...
```

The bracketed part is the download id, so lines from several downloads can be told apart. It is
`-` outside a download.

## What is redacted

Every record that goes through a handler added by `configure_logging` passes a filter that removes
secrets from the message, its arguments and any traceback: tokens and signatures in query strings,
`Authorization` and `Cookie` values, and passwords in addresses. Addresses the library logs are
already redacted at the source.

The filter is attached to the handlers `configure_logging` creates. If you attach your own handler
instead, the library still logs redacted addresses and never logs header or cookie values, but the
safety-net filter is not on your handler.

## Using your own handlers

If you prefer to manage logging yourself, use the standard library:

```python
import logging

logging.getLogger("rayohx").addHandler(logging.StreamHandler())
logging.getLogger("rayohx").setLevel(logging.INFO)
```

Because the library installs a `NullHandler` on the `rayohx` logger, importing it never prints
"no handlers" warnings and never writes anything until you add a handler.

Log levels in use:

| Level | What gets logged |
|---|---|
| `WARNING` | A retry after a failed attempt, TLS verification turned off, resume state that was unreadable or unexpected and was ignored |
| `INFO` | A resume that was not possible and why, for example a partial output that could not be reused or state that does not match this download |

## Examples

Verbose on request, quiet by default:

```python
import logging
import rayohx


def setup_logging(verbose: bool) -> None:
    rayohx.configure_logging(logging.DEBUG if verbose else logging.WARNING)
```

Keep a log file per run:

```python
from datetime import datetime

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
rayohx.configure_logging("INFO", console=False, log_file=f"logs/rayohx-{stamp}.log")
```

Silence the library inside your own application:

```python
logging.getLogger("rayohx").setLevel(logging.CRITICAL)
```

Send only the HTTP layer's messages somewhere else:

```python
http_log = logging.getLogger("rayohx.http")
http_log.addHandler(logging.FileHandler("http.log", encoding="utf-8"))
```
