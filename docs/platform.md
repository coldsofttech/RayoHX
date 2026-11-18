# Platform

RayoHX has two layers inside the `rayohx` package:

- **The engine** (everything outside `rayohx.platform`) decides *how* a stream is downloaded.
- **The platform** (`rayohx.platform`) decides *what* should happen: which downloads run, when, with which settings, and what is remembered between runs.

The command line, the API, the window and (later) the browser host are front ends. They call the platform and the public engine, and hold no download logic.

> The platform is **unstable** until its first release. Names and storage formats may change between versions. The engine's public API is not affected.

## Rules

Checked in CI by `packages/core/tests/unit/test_architecture.py`:

1. The engine never imports `rayohx.platform`. Importing `rayohx` does not load it.
2. The platform imports only public engine modules, never `rayohx._*`.
3. The API, command line and window import only public names from `rayohx`.

When a front end needs something that lives in a private module, promote it to a public module (as `rayohx.storage` and `rayohx.redaction` were) instead of importing the private one.

## What exists today (phase 2-1)

| Part | Where | Purpose |
| --- | --- | --- |
| `Rayo` | `rayohx.platform.facade` | One entry point: `from rayohx import Rayo`. Opens the folders, database, events and settings. |
| Paths | `rayohx.platform.paths` | Config, data and cache folders. `RAYOHX_HOME` moves everything under one folder; a `rayohx.portable` file beside a packaged program keeps everything beside it. |
| Database | `rayohx.platform.persistence` | SQLite in WAL mode, numbered migrations, a backup before any change to existing data, and recovery from a damaged file. |
| Events | `rayohx.platform.events` | `PlatformEvent` (secrets removed from every payload), a saved event log you can follow by id, and a bus that isolates failing listeners. |
| Errors | `rayohx.errors` | Every error has a stable `code` and a `category`. |

## The database

- Location: `<data folder>/rayohx.db`. Keep it on a local disk, because SQLite's write-ahead log does not work on network shares.
- Schema version: `PRAGMA user_version`, with each applied migration recorded in `schema_migrations`.
- Migrations live in `rayohx/platform/persistence/migrations.py` as code, so they are present in every packaged build. Never edit a migration that has shipped; add a new one.
- Opening a database upgrades it. If it already held data, a copy is saved in `<data folder>/backups/` first.
- A database written by a newer RayoHX is refused and left untouched.
- A file that is not a database, or fails SQLite's integrity check, is renamed to `rayohx.db.corrupt-<time>` and a new database is created; a `system.database_recovered` event records it.

## Errors, codes and categories

Use `error.code` and `error.category` (an `ErrorCategory`), not the message text, for retry rules, reports and exit codes. HTTP errors include the status: `HTTP_503`, `AUTH_403`.

## Events

```python
from rayohx import Rayo

with Rayo() as rayo:
    rayo.events.subscribe(print)
    rayo.events.emit("example.hello", job_id="abc", detail="visible")
    for event in rayo.event_store.query(after_id=0):
        ...
```

Events at `DEBUG` severity (such as one per downloaded segment) are delivered to listeners but not saved, so the log stays small.
