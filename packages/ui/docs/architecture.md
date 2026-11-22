# UI architecture

How `rayohx_ui` (the `rayohxu` window) is put together. For working on it, see [development](development.md); for the installer, see [packaging](packaging.md).

> The interface is not built yet. The window shows an example page, and the sections marked *Placeholder* describe what is planned.

## Layering

The desktop window is hosted by [Cornea Shell](https://github.com/coldsofttech/CorneaShell) (`cornea-shell`), on Windows only. `rayohx_ui` only wires things together. The data comes from `rayohx_api` and the work from `rayohx`, and neither of them may import `rayohx_ui`.

## Modules

```text
packages/ui/src/rayohx_ui/
  __main__.py   the `rayohxu` command: options, output, exit code
  app.py        builds the Cornea shell: serves dist, mounts the API, registers actions
  ui/           React + Vite (JavaScript): src/, index.html, package.json, tests
  ui/dist/      build output, not committed; frozen into the Windows build
```

`app.py` holds the app id, title and version as constants at the top, and must not hold business logic.

## Static files, dynamic app

Cornea serves the built files in `ui/dist`, but the page is a normal single-page app that talks to Python while it runs:

- **Data:** `fetch('/api/v1/...')` calls the `rayohx_api` routes and gets JSON.
- **Native actions:** `POST /api/bridge/<action>` runs a Python function registered in `app.py`. The example is `app_info`. Cornea also provides file and folder pickers, opening links and platform info.
- **State:** lives in React in the page, and in Python behind the routes.

Cornea hosts the page and the API on one address, behind a start-up token, a host and origin check and strict response headers. See [security](security.md).

## Frontend

Plain JavaScript with JSX, built by Vite. Python is called only through `src/api/`. Cornea's policy forbids inline scripts and styles, so styles live in CSS files.

*Placeholder:* screens, navigation, state handling and the component structure are to be described once the interface is designed.

## Window actions

*Placeholder:* the list of registered bridge actions (beyond the `app_info` example), their inputs and results.

## Packaging

The window is not part of the Python package. The Windows installer freezes `ui/dist` into the build and needs no Node; the `rayohxu` command exists in that build. See [packaging](packaging.md).
