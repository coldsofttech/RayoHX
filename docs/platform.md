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

## What exists today

| Part | Where | Purpose |
| --- | --- | --- |
| `Rayo` | `rayohx.platform.facade` | One entry point: `from rayohx import Rayo`. Opens the folders, database, events and settings. |
| Paths | `rayohx.platform.paths` | Config, data and cache folders. `RAYOHX_HOME` moves everything under one folder; a `rayohx.portable` file beside a packaged program keeps everything beside it. |
| Database | `rayohx.platform.persistence` | SQLite in WAL mode, numbered migrations, a backup before any change to existing data, and recovery from a damaged file. |
| Events | `rayohx.platform.events` | `PlatformEvent` (secrets removed from every payload), a saved event log you can follow by id, and a bus that isolates failing listeners. |
| Errors | `rayohx.errors` | Every error has a stable `code` and a `category`. |
| Queue | `rayohx.platform.queue` | The persistent job queue, its scheduler and the runner (below). |
| Secrets | `rayohx.platform.secrets` | Where job secrets live: the system credential store (optional `keyring`) or memory. |

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

## The queue

```python
from rayohx import Rayo

with Rayo() as rayo:
    job = rayo.queue.add("https://example.com/master.m3u8", priority="high")
    rayo.queue.start()        # run jobs in this process
    rayo.queue.wait_idle()
```

**Jobs and states.** A job is `queued`, then `preparing`, `downloading`, `finalizing` and `verifying` while it runs, and ends `completed`, `failed` or `cancelled`. It can be `paused` from `queued` or while running. The queue has its own state, separate from the engine's `DownloadState`; the runner maps engine events onto it.

**Order.** `pick_next` (a pure function) chooses what starts: higher priority first, then the user's order (rank), then the job added first, then the smaller id. Resource checks may skip a job but never reorder the rest.

**One runner.** A runner holds `runner.lock` in the data folder; a second one gets `RunnerLockedError`. Other processes read and change jobs in the database. To pause or cancel a job that a runner is working on, they write a `control_request` that the runner applies within a poll interval. If no runner exists, a job left in a running state by a crash is changed directly.

**Pause is a hard pause.** The run is cancelled with its resume state kept (the queue forces `keep_state_on_failure`), the job leaves its slot and releases its workspace lock, and resuming continues from the last written segment. The engine's token pause, which keeps the slot, is not used by the queue.

**Recovery.** `queue.start()` puts jobs left in a running state by a crash back in the queue, marked `recovered`. A graceful `stop()` puts them back without counting the interrupted run as an attempt.

**Retries.** A failed run is repeated after a growing delay when the error's category is retryable (network, HTTP, segment) and the error itself says a retry may help. Configuration, authentication and storage errors fail at once. Each run is recorded in `job_attempts`.

**Settings and secrets.** A job stores its `DownloadConfig` as JSON (`config_to_options`). Cookies, secret headers, proxy credentials and key passwords are split out into the secret store and never written to the database or to exports. The address is stored as given, because the job needs it; the database folder is created private.

**Events.** The runner publishes `queue.*` events (`job_added`, `job_state_changed`, `job_retry_scheduled`, `job_recovered`, `job_completed`, `job_failed`, `completed`, ...) and forwards the engine's events with the job id, so `event_store.query(job_id=...)` is a per-job log.

## Migrations so far

| Version | Name | Adds |
| --- | --- | --- |
| 1 | `initial` | settings, jobs, job attempts, events |
| 2 | `queue` | job columns for the display address, secret reference, recovery, output, retry time, control requests and progress |
