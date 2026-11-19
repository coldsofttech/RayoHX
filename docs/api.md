# API

`rayohx_api` is a FastAPI app over `rayohx`. It runs on its own on any system, and the same routes are mounted inside the UI window (see [UI](ui.md)). Routes only validate input, call the library and shape the response; logic stays in `rayohx`.

## Running it

```bash
cp .env.example .env              # set RAYOHX_API_API_KEYS, or RAYOHX_API_AUTH_MODE=none
uv run python -m rayohx_api      # http://127.0.0.1:8000
```

The app refuses to start without an API key unless authentication is switched off. This is on purpose, so the API is never open by accident. See [security](security.md).

## Settings

Read from `RAYOHX_API_*` environment variables or a `.env` file. List values are JSON.

| Variable | Default | Purpose |
| --- | --- | --- |
| `RAYOHX_API_HOST` | `127.0.0.1` | Address to listen on |
| `RAYOHX_API_PORT` | `8000` | Port to listen on |
| `RAYOHX_API_LOG_LEVEL` | `info` | Log level |
| `RAYOHX_API_AUTH_MODE` | `api_key` | `api_key`, or `none` for local development |
| `RAYOHX_API_API_KEYS` | none | Accepted keys, sent in the `X-API-Key` header |
| `RAYOHX_API_DOCS_ENABLED` | `false` | Serve `/docs`, `/redoc` and `/openapi.json` |
| `RAYOHX_API_MAX_BODY_BYTES` | `1048576` | Largest request body |
| `RAYOHX_API_CORS_ORIGINS` | none | Origins allowed by CORS |
| `RAYOHX_API_HOME` | none | Folder for the queue database and other platform data (default: the per-user folders) |
| `RAYOHX_API_MAX_ACTIVE_DOWNLOADS` | `2` | Downloads that run at once; the rest wait in the queue |

## Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /health`, `GET /ready` | Liveness and readiness probes, no authentication |
| `POST /api/v1/inspect` | Look at a playlist without downloading it |
| `GET/POST /api/v1/downloads`, `GET/DELETE /api/v1/downloads/{id}` | Start, list, read and forget downloads |
| `POST /api/v1/downloads/{id}/pause`, `/resume`, `/cancel` | Control one download |
| `GET /api/v1/downloads/{id}/log`, `/events` | The engine's log, and a server-sent event stream |
| `GET /api/v1/settings`, `PUT /api/v1/settings/defaults` | Server settings and saved default options |
| `POST /api/v1/clean` | Remove working folders left by interrupted downloads |
| `GET/POST /api/v2/queue` | The persistent queue: list in running order, add jobs with a priority and retry policy |
| `GET /api/v2/queue/{id}` | One job with every run it has had |
| `POST /api/v2/queue/actions` | Pause, resume, cancel, retry, remove, set priority, move to top or bottom, for many jobs at once |
| `POST /api/v2/queue/{id}/move` | Put a job just before another |
| `GET /api/v2/queue/stats`, `PUT /api/v2/queue/settings` | Counts, and how many jobs run at once |
| `POST /api/v2/media-info` | Everything a stream offers (codecs, tracks, size, metadata) and whether it can be saved in a given format |
| `GET /api/v2/queue/{id}/verification` | How a finished job was checked |
| `GET /api/v2/profiles`, `/profiles/{id}` | The built-in and saved profiles, and why one cannot run on this server |
| `GET /api/v2/capabilities` | Whether FFmpeg was found and which output formats this server can make |
| `GET /api/v2/events`, `/events/stream` | The saved event log; follow it with `after_id` or `Last-Event-ID` |

Errors use the problem-details format (`application/problem+json`).

## The queue

Downloads are jobs in a database (see [platform](platform.md)), so they survive a restart of the API. The API runs the queue while it is up: `max_active_downloads` jobs run at once and the rest wait in priority order. A job that was running when the API stopped goes back to the queue and continues.

`/api/v1/downloads` keeps its behavior as a thin layer over the same queue: it adds a job (never retried, as before) and the other routes act on it. `/api/v2` adds priorities, retries, ordering, bulk actions and the event log. Job addresses are returned with signing tokens removed, and secrets (cookies, headers, proxy passwords) are never returned.

`POST /api/v2/queue` also takes `verify` (`level`, `checksum`), `metadata` (`policy`, `title`, `description`, `language`, `artwork`, `chapters`) and `name_template`. A finished job reports its `verification` and `notes`, and `GET /api/v2/queue/{id}/verification` returns every check that was made or skipped.

A request to `POST /api/v2/queue` can name a `profile`. The profile's settings apply and only the options the request itself sets are laid over them (a field left out never overrides the profile). With no profile named, the default profile is used if one is set; otherwise the platform's own defaults apply (verify the finished file's structure, write the stream's metadata where the file can hold it). The saved default options of `/api/v1/settings/defaults` belong to `/api/v1` only. Profiles are created and edited with the command line or the Python API, not over HTTP.

When another process (for example `rayohx queue run`) is running the queue, the API does not start a second runner: it reports `"runner": "another process"` in the queue stats and passes pause and cancel requests through the database.

## Storage, diagnostics and metrics

* `GET /api/v2/storage`, `PUT /api/v2/storage/policy`, `GET /api/v2/storage/workspaces` and `POST /api/v2/storage/cleanup` (a dry run unless `dry_run` is false; downloaded files are never removed).
* `GET /api/v2/diagnostics/explain/{code}`, `GET /api/v2/diagnostics/jobs/{id}`, `POST /api/v2/diagnostics/network`, `POST /api/v2/diagnostics/stream`, `POST /api/v2/diagnostics/report` and `GET /api/v2/diagnostics/reports`. Reports have secrets, query values and home folders removed; only a file name is returned for the saved copy.
* `GET /api/v2/metrics` (JSON) and `GET /api/v2/metrics/prometheus` (text).

The network and stream checks fetch the address you give, so they need the same authentication as every other route.

## The contract

`docs/openapi.json` is generated by `uv run python scripts/export_openapi.py`. CI fails when it is out of date, `api-compat.yml` warns about breaking changes on pull requests, and a Schemathesis test fuzzes the running server for server errors. Put breaking changes in a new `/api/v3` router.
