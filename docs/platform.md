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

## Profiles

```python
rayo.profiles.create("Movies", base="1080p", options={"output": {"format": "mkv"}}, naming="{name} {date}")
rayo.queue.add(url, profile="Movies", overrides={"selection": {"max_resolution": "720p"}})
```

A profile (`DownloadProfile`) is a name plus the settings it *changes*, in the shape of `config_to_options`, a retry policy, a file name template, and `metadata` and `verify` values that are stored now and applied when metadata handling and verification arrive. Five are built in (`best-quality`, `1080p`, `mobile`, `archive`, `custom`) and cannot be changed; yours live in the `profiles` table.

**Combining.** Engine defaults, then the profile, then the caller's overrides, section by section. A job stores the *result* (a snapshot), so editing or deleting the profile later never changes queued jobs. `profile=None` uses the default profile (`profiles.set_default`) when one is set.

**Validation** (`rayohx.platform.profiles.validate` / `check`) has two levels. *Structure* is always checked and blocks saving: unknown settings, invalid values (the settings are built into a real `DownloadConfig`), secrets, a bad naming template, bad `metadata` or `verify`. *This machine* is checked when a job is queued: an output format that needs FFmpeg (Matroska, audio-only) is refused if FFmpeg is missing or the native-only remux backend is set. Profiles never hold secrets: cookies, secret headers and proxy logins are refused, and are given per job.

**Import and export** use `{"rayohx_profiles": 1, "profiles": [...]}`. Import checks every profile first, renames or skips a taken name, and migrates old schema versions (`profiles.store.MIGRATIONS`).

**Naming.** A template (`{name}`, `{date}`, `{time}`, `{job}`, `{profile}`, `{host}`) is rendered when the job is queued, deterministically and without any path separator, into the job's `output_name`.

## Output formats

`OutputFormat` has `AUTO`, `ORIGINAL`, `TS`, `MP4`, `MKV`, `AUDIO` and `SEGMENTS`. The engine always prefers the least destructive route: keep the container (`ORIGINAL`, or `AUTO` for a stream that needs nothing), then copy the streams into another container, and it never re-encodes. `MKV` and `AUDIO` are made by FFmpeg copying the streams (`-c copy`) and fail before any download when FFmpeg is missing. An audio-only download of a stream with a separate audio track fetches only that track. A result's `OutputInfo.processing` says what happened: `copied`, `remuxed`, `muxed` or `extracted`. `rayohx.capabilities.detect()` reports what this machine can do.

## Verification

A download is not finished just because every request succeeded. `VerifyConfig` (and the profile's `verify`) decides how much is checked afterwards:

| Level | What is checked |
| --- | --- |
| `none` | Only what every download does: status, sizes, segment signatures, and a spot-check of the finished file. |
| `basic` | The output exists and holds something, and its container is well formed (transport stream packets line up, MP4 and Matroska structure). |
| `strong` | Also ffprobe (when installed): the file reads, it has the expected streams, and its length matches the playlist. Segments are checked for being cut off (a packet or MP4 box that stops short), which fails that segment, so it is retried. |

A checksum can be requested on its own (`verify.checksum`) or as an expected value (`verify.expected_checksum`, with the algorithm told from its length). Nothing is hashed unless asked for.

The engine moves a verifying download through `VERIFYING` and returns an `IntegrityReport` with every check, and the checks that could not run (listed as *skipped*, so a report never claims more than was looked at). A file that fails is renamed `<name>.invalid` (or deleted with `keep_invalid: false`) and never left under its proper name; the job fails with `VERIFICATION_FAILED`, which is not retried automatically because a damaged file is not a passing problem.

The queue stores the report: `job.verification` is `not_requested`, `verified` or `failed`, `queue.verification(job_id)` returns the report, and `verification.*` events record it. A job queued with no profile is verified at `basic`; complete settings (`config=`) keep the engine's quiet defaults.

## Metadata

`MetadataConfig` (and the profile's `metadata`) says what to write into the output file: `none`, `minimal` (title and language), `preserve` (everything the stream says: title, description, language, chapters, cover picture, start time and source), or `custom` (only values the settings give). The settings' own `title`, `description` and `language` replace the stream's. The stream's information comes from `EXT-X-SESSION-DATA` (`com.apple.hls.title`, `title`, `description`, `artwork`, `language`), `EXT-X-PROGRAM-DATE-TIME` and `EXT-X-DATERANGE` (chapters, from tags with an `X-TITLE`, placed relative to the first segment's date).

Metadata is written by FFmpeg, so it goes into Matroska and audio files, and into MP4 files made with `remux_backend=ffmpeg`. Files made without FFmpeg (a transport stream, the built-in MP4 remuxer, separate segments) cannot hold it: the result says so in `notes` and nothing is guessed. A cover picture must really be a JPEG or PNG; if it cannot be fetched or is something else, the download goes on without it and says so.

`{title}` and `{language}` can be used in a naming template: the platform fills in what it knows when the job is queued and passes the rest to the engine (`OutputConfig.name_template`), which fills in the title once the stream is read.

## Media information

`rayohx.media.inspect_media(url, ...)` describes a stream without downloading it: duration, segment count and container, encryption, every variant (with the chosen one marked), the video (codec and profile from the playlist's codec string, resolution, frame rate, range), audio and subtitle tracks (with the ones a download would pick marked), the metadata above and a size. With ffprobe installed it also examines the first segment, which fills in the details a playlist does not state (pixel format, channels, sample rate); each value says whether it came from the `playlist` or the `probe`. `size.kind` is `exact` (every byte accounted for), `estimated` (with the basis: average or peak bandwidth times duration) or `unavailable` (a live stream, or no bit rate), and an estimate is never presented as exact. `check_compatibility(info, format)` lists what to know before saving in a format: FFmpeg needed, codecs the built-in MP4 remuxer cannot copy, separate audio that the format cannot hold, live and SAMPLE-AES streams.

## Storage management

`rayo.storage` keeps track of disk space and reacts before the disk fills.

- **Policy.** `StoragePolicy` has three optional free-space thresholds for the downloads disk: `warn_below`, `pause_below` and `stop_below` (largest first), plus `low_storage_mode`. Sizes are bytes or text such as `5GB`. With no thresholds the queue only counts and reports. Easing back needs `resume_margin` (10% by default) of extra room, so the level does not flap around a threshold.
- **Admission and reservations.** A job only starts when the room left, after what running downloads still have to write (`total_bytes` x 1.05 minus `written_bytes`, taken from live progress), stays above the pause threshold. A job that does not fit waits in the queue.
- **Reacting.** Below `pause_below` running jobs are paused by the queue itself (`auto_paused`) and go on by themselves when room returns; a job you paused yourself is never resumed for you. Below `stop_below` jobs fail with `STORAGE_LOW`, keeping their resume state. Each change of level is an event (`storage.low`, `storage.paused`, `storage.stopped`, `storage.recovered`).
- **Low-storage mode.** Asked for, or entered when the disk is low: jobs use the streaming strategy and cap their temporary data at 256 MiB.
- **Accounting.** `rayo.storage.snapshot()` reports free space, finished output, working folders (and the part no finished download needs), reserved bytes, the peak temporary use and the platform's own data. The engine announces each working folder (`workspace_opened` event) so the queue knows which job owns it (`job_workspaces`).
- **Cleanup.** `rayo.storage.cleanup()` looks first (`dry_run=True` is the default). It removes only working folders that no running or resumable job owns and that are older than a limit, and old diagnostic reports. It never touches downloaded files, and it lists what it kept and why.

## Diagnostics

`rayo.diagnostics` answers "why did this fail?" without exposing secrets.

- `explain(code)` and `explain_job(id)` give a title, what happened, the likely cause, what was tried and what to do next, for every stable error code (`HTTP_*` codes by status). Unknown codes get their category's explanation.
- `network(url, job_id=...)` checks name lookup, connection, TLS (with certificate expiry), proxy and the first response, using a job's headers and proxy. `stream(url)` describes a playlist and lists what is unusual (live, discontinuities, encryption, missing codecs).
- `report(job_id=...)` collects the environment, queue, storage, recent problems, the job (settings, attempt history, failed segments, verification and finalization) and optional network and stream checks into one JSON file in the reports folder (mode 0600). Every string is sanitized: URL query values, headers, cookies, proxy credentials and the literal secrets of the job (also percent-encoded) are removed, home folders become `~`, and only the *names* of protected settings are listed. A test seeds a token, cookie and header into a failing job and checks none of them reaches the report.

## Metrics

`rayo.metrics()` returns counts and sizes from the database and live progress: queue (queued, active, completed, failed, wait time, average duration), downloads (bytes, throughput, retries, failures), storage (level, free, working and reserved bytes) and verification. `rayohx.platform.metrics.to_prometheus()` writes the same numbers as Prometheus text (`rayohx_<section>_<name>`).

## Daemon and migration

`Daemon(rayo, port=8765, metrics=False)` runs the queue and serves `/health`, `/ready` and optionally `/metrics` on loopback; `request_stop()` makes `run()` return after a clean stop. `configure_logging()` writes JSON log lines (never a traceback with local values). `rayohx.platform.migrate.migrate(rayo, defaults_options=...)` reports the schema state and backup, and imports the version 1 saved defaults as a profile once (a settings marker records it; `dry_run` changes nothing). See the [operations guide](operations.md).

## Migrations so far

| Version | Name | Adds |
| --- | --- | --- |
| 1 | `initial` | settings, jobs, job attempts, events |
| 2 | `queue` | job columns for the display address, secret reference, recovery, output, retry time, control requests and progress |
| 3 | `profiles` | the profiles table, and the profile a job came from |
| 4 | `storage_diagnostics` | `auto_paused` on jobs, the `job_workspaces` table, and the `diagnostic_reports` table |
