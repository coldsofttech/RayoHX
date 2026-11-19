# UI

The desktop window is hosted by [Cornea Shell](https://github.com/coldsofttech/CorneaShell) (`cornea-shell`). It runs on Windows only; the library, command line and API work on every system.

## Static files, dynamic app

Cornea serves the built files in `src/rayohx_ui/ui/dist`, but the page is a normal single-page app that talks to Python while it runs. `ui/` holds only the interface; everything dynamic lives in `rayohx_api` and `rayohx`:

- **Data:** `fetch('/api/v1/...')` (the New and Settings pages) and `fetch('/api/v2/...')` (the Queue and Storage pages, job details and diagnostics) call the `rayohx_api` routes and get JSON.
- **Native actions:** `POST /api/bridge/<action>` runs a Python function registered in `rayohx_ui/app.py`. The example is `app_info`. Cornea also provides file and folder pickers, opening links and platform info.
- **State:** lives in React in the page, and in Python behind the routes.

Cornea hosts the page and the API on one address, behind a start-up token that becomes a session cookie, a host and origin check, and strict response headers. See [security](security.md).

## Pages

| Page | What it does | API |
| --- | --- | --- |
| New | Inspect a stream, choose tracks, start a download | `/api/v1` |
| Queue | Every job with its priority and progress; select several to pause, resume, cancel, retry, remove or set a priority; move a waiting job to the top or bottom; details with the failure explanation, verification checks, runs, events and a report to share | `/api/v2/queue`, `/api/v2/diagnostics`, `/api/v2/events` |
| Storage | Free space, the low-space policy (warn, pause, stop, low-storage mode), working folders and a cleanup that previews before it removes | `/api/v2/storage` |
| Settings | The saved default options for new downloads | `/api/v1/settings` |

Profiles are not editable in the window yet (they are managed with `rayohx profile`, and listed by `GET /api/v2/profiles`); moving the New and Settings pages to `/api/v2` and a profile editor are next.

## Layout

```text
src/rayohx_ui/__main__.py   the `rayohx-ui` command: options, output, exit code
src/rayohx_ui/app.py        builds the Cornea shell: serves dist, mounts the API, registers actions
src/rayohx_ui/ui/           React + Vite (JavaScript): src/, index.html, package.json, tests
src/rayohx_ui/ui/dist/      build output, not committed; frozen into the Windows build
```

`app.py` only wires things together. It must not hold business logic, and `rayohx_api` and `rayohx` must never import `rayohx_ui`.

## Running it

```bash
uv sync
npm ci --prefix src/rayohx_ui/ui
npm run build --prefix src/rayohx_ui/ui
uv run python -m rayohx_ui                 # window
uv run python -m rayohx_ui --no-window     # prints an address for a browser
uv run python -m rayohx_ui --dev           # Vite with hot reload (needs Node)
```

`--dev` starts `npm run dev` through Cornea and relaxes the content security policy for Vite. Use it only while developing.

## Writing the frontend

- Plain JavaScript with JSX. Call Python only through `src/api.js`.
- Cornea's policy forbids inline scripts and styles, so put styles in CSS files.
- The interface uses Fluent UI (`@fluentui/react-components`). Colours live in one place, `src/theme.js`, built from the brand slate with an orange accent, red for danger and yellow for warnings. Fluent adds its styles through the browser's style API, which Cornea's `style-src 'self'` policy allows; check this in the window after upgrading Fluent.
- `npm run lint`, `npm test` (Vitest, Testing Library and an accessibility check) and `npm run build` run in CI.

## Packaging

The window is not part of the Python package: `uv build` publishes only the core library and the command line. Users get the window from the Windows installer, which freezes `ui/dist` into the build (`installer/pyinstaller/ui.spec`) and needs no Node. The `rayohx-ui` command exists in that build; from the source tree you start it with `python -m rayohx_ui`.

The window and taskbar icon is `src/rayohx_ui/ui/public/icon.png` (copied into `dist` by the build), and the app id, title and version are constants at the top of `rayohx_ui/app.py`. The Windows setup and the standalone executables are described in [packaging](packaging.md).

## Tests

The Python tests in `tests/ui/` replace Cornea's `Shell`, so no window opens. In `tests/ui/integration/`, a Windows-only test starts the real server without a window and needs a built `dist`, and another starts the built `rayohx-ui.exe` (see [packaging](packaging.md)).
