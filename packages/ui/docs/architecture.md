# UI architecture

How `rayohx_ui` (the `rayohxu` window) is put together. For working on it, see [development](development.md); for the installer, see [packaging](packaging.md).

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
- **Native actions:** `POST /api/bridge/<action>` runs a Python function registered in `app.py`: `app_info` and `open_downloads`. Cornea also provides file and folder pickers, opening links and platform info.
- **State:** the page holds only what is on screen. The download list, its logs and the saved default options (including the download folder and theme) are kept by `rayohx_api` and survive a restart.

Cornea hosts the page and the API on one address, behind a start-up token, a host and origin check and strict response headers. See [security](security.md).

## Frontend

Plain JavaScript with JSX, built by Vite. Python is called only through `src/api/`. Cornea's policy forbids inline scripts and styles, so styles live in CSS files.

```text
src/
  api/          the only place that calls Python: client (fetch), bridge, downloads, settings, inspect, clean
  components/
    new/        add a stream: inspect, Quick or Advanced selection, several addresses, playlist text
      options/  the option fields, drawn from data/options-sections.json
    downloads/  the live list, each card, and its engine log
    settings/   defaults, download folder, theme, clean-up, about
  data/         option sections, qualities, codecs, formats and other lists as JSON
  options.js    reads the option sections and looks up values by field id
  theme.js      Fluent UI themes
```

Each folder holds small components with a test beside each one. The option list lives in `data/options-sections.json`; adding an option there adds its field to the form.

**Default options.** Settings saves the default options for new downloads. The form shows them as hints through the `Inherited` context in `components/new/options/inherited.js`, and a download sends only the options the user changed, so everything else follows the saved defaults. Fields marked `defaultsOnly` (such as quality) appear only in Settings and, for quality, in Quick selection.

**Download log.** A card shows a log button when the download reports `has_log`. The log is fetched when opened and lists what the engine reported.

## Window actions

| Action | Result |
| --- | --- |
| `app_info` | the app name and version |
| `open_downloads` | shows the download folder in Explorer; the page names no path |

## Packaging

The window is not part of the Python package. The Windows installer freezes `ui/dist` into the build and needs no Node; the `rayohxu` command exists in that build. See [packaging](packaging.md).
