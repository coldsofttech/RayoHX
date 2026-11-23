# API security

How the API protects requests when it runs on its own. To report a vulnerability, see [SECURITY.md](../../../SECURITY.md). How requests are protected under the UI window is in the [UI security notes](../../ui/docs/security.md), and in the download engine in the [core security notes](../../core/docs/security.md).

## Standalone API

When run alone (`python -m rayohx_api`), Cornea is absent, so the API protects itself:

- **API key:** protected routes need an `X-API-Key` header matching `RAYOHX_API_API_KEYS`. The app will not start without a key unless `RAYOHX_API_AUTH_MODE=none`, which is for local development only. Keys are compared in constant time and never logged.
- **Headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive CSP, `Cache-Control: no-store` on `/api/` and HSTS over HTTPS.
- **Body limit:** requests declaring more than `RAYOHX_API_MAX_BODY_BYTES` get `413`. Also set a limit at your reverse proxy, since chunked bodies have no declared size.
- **Server files:** requests may not name files on the server (cookie files, certificates, FFmpeg, key files) unless `RAYOHX_API_ALLOW_LOCAL_PATHS=true`, which suits only a client you fully trust. Output and working folders must stay inside the download folder, and symbolic links that leave it are refused.
- **Docs hidden:** `/docs`, `/redoc` and `/openapi.json` are off unless `RAYOHX_API_DOCS_ENABLED=true`.
- **Saved data:** the download list, engine logs and default options are kept in a small SQLite file (`RAYOHX_API_DB_PATH`). Proxy user names and passwords and key passwords are never saved, and saved defaults follow the same rules as a request, so they cannot name server files unless `RAYOHX_API_ALLOW_LOCAL_PATHS=true`. Keep the file private to the account that runs the API.
- **Errors:** a `500` never shows details; they go to the log with the request ID.
- **Not included:** HTTPS, rate limiting, JWT and multi-user authentication, a shared or networked database. Add them, or put the API behind a proxy, before exposing it publicly.

## Under the UI window

When the UI window mounts the API routes, Cornea's security gate guards every request, so the API switches its own key check and duplicate response headers off (`create_app(embedded=True)`). The only client is the person at the window, so the window also sets `RAYOHX_API_ALLOW_LOCAL_PATHS=true` for its own process. Never expose these routes any other way. The details are in the [UI security notes](../../ui/docs/security.md).
