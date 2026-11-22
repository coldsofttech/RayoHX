# API architecture

How `rayohx_api` is put together. For running it and its settings, see [api](api.md); for the protections it applies, see [security](security.md).

## Layering

`rayohx_api` is a thin FastAPI layer over the `rayohx` library. A route validates its input, calls the library and shapes the response. Logic stays in `rayohx`, which never imports the API. The only dependencies the API adds are FastAPI (with Starlette), uvicorn and pydantic-settings.

## Modules

```text
packages/api/src/rayohx_api/
  __main__.py      python -m rayohx_api: checks the settings, then starts uvicorn
  main.py          create_app(): builds the app, middleware, handlers and routers
  config.py        Settings (RAYOHX_API_* variables or .env), AuthMode, get_settings()
  auth.py          authenticate(): the X-API-Key check, and the replacement used when embedded
  errors.py        problem-details responses and the exception handlers
  logs.py          JSON logging and the request ID middleware
  security.py      security headers and the request size limit
  build.py         turns a request into engine settings and holds the rules for what a client may ask
  jobs.py          runs downloads in background threads and keeps their state in memory
  schemas/
    health.py      models for /health and /ready
    v1/            /api/v1 models, one file per route group (inspect, downloads, settings, clean) and common.py for what they share
  routers/
    health.py      /health and /ready, at the root, no authentication
    v1/            the /api/v1 router: one file per route group, and deps.py for the shared state and helpers
```

## One app, two ways to run it

`create_app(embedded=False)` is the only place the app is built. There is no module-level app.

| | Standalone (`python -m rayohx_api`) | Embedded (`create_app(embedded=True)`) |
| --- | --- | --- |
| Hosted by | uvicorn | The UI window, behind Cornea's security gate |
| Authentication | `X-API-Key`, or none if `AUTH_MODE=none` | Already done by Cornea; `authenticate` is replaced by `embedded_principal` |
| Start-up check | Refuses to start without a key unless auth is off | Skipped |
| Security headers | Added by the API | Left to Cornea |

## A request, step by step

Middleware wraps the routes in this order, outermost first:

1. **CORS**, only when `RAYOHX_API_CORS_ORIGINS` is set.
2. **Request ID**: reuses the caller's `X-Request-ID` or creates one, and returns it on the response.
3. **Security headers**, standalone only.
4. **Body limit**: rejects a declared body above `RAYOHX_API_MAX_BODY_BYTES` with `413`.
5. **Route**: dependencies run first (`authenticate` for protected routes), then the handler, which returns a response model.

Any error raised on the way is turned into an `application/problem+json` response by the handlers in `errors.py`: HTTP errors keep their status, validation errors become `422` with the field errors, and anything unexpected becomes a `500` with no details (the exception goes to the log with the request ID).

## Settings

`Settings` is a pydantic-settings class with the prefix `RAYOHX_API_`. `get_settings()` reads it once per process. `check_auth()` runs at start-up, not on the first request, so a missing key stops the service immediately. Nothing else reads environment variables directly.

## Authentication

Protected routes depend on `authenticate`, which returns a `Principal` (who called, and how) or raises `401` with `WWW-Authenticate: ApiKey`. Keys are compared in constant time. The probes at the root never require authentication.

## Logging

All logs, including uvicorn's, go to stderr as one JSON object per line, with the time, level, logger, message and request ID. The request ID travels in a context variable, so any log line written while handling a request carries it.

## Versioning and the contract

- Probes (`/health`, `/ready`) live at the root.
- Everything else is mounted under `/api/v1`. A breaking change goes in a new `/api/v2` router.
- [`openapi.json`](openapi.json) is generated from the app. CI fails when it is out of date and `api-compat.yml` reports breaking changes on pull requests.
- `/docs`, `/redoc` and `/openapi.json` are served only when `RAYOHX_API_DOCS_ENABLED=true`.
