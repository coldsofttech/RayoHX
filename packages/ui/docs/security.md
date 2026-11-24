# UI security

How the desktop window protects requests and data. To report a vulnerability, see [SECURITY.md](../../../SECURITY.md). The engine's protections are in the [core security notes](../../core/docs/security.md); the API's are in the [API security notes](../../api/docs/security.md); the command line's are in the [CLI security notes](../../cli/docs/security.md).

## Under the window

Cornea's `SecurityMiddleware` guards every mounted route, so the API adds no token of its own:

- the `Host` must be on the allow-list (the bound `127.0.0.1:<port>` only)
- state-changing requests (POST, PUT, PATCH, DELETE) must carry a matching `Origin`
- a one-time start-up token is exchanged for an `HttpOnly`, `SameSite=Strict` session cookie
- responses carry a strict content security policy and other protective headers

`rayohx_ui` therefore mounts the routes with API-key checks switched off. Never expose these routes any other way.

## Frontend

- Inline scripts and styles are forbidden by the content security policy, so all code and styles are in files.
- `--dev` relaxes the policy for Vite; use it only while developing.
- Python is reached only through `src/api/` and the registered bridge actions.

- **Secrets in forms.** Fields of type `secret` (such as passwords) are hidden while typed. The saved default options never keep logins or passwords; they are sent only with the download they were typed for.
- **Output is escaped.** Addresses, errors and the engine log are shown as text by React. The page never builds HTML from them.
- **Local paths.** Fields that point at files on this computer (cookie files, certificates, the download folder) appear only when the API allows local paths.
- **Fixed native actions.** `open_downloads` takes no path, so the page can only open the folder downloads are saved in.

## The installer

- **Per user by default.** The setup installs for the current user and offers all users, which asks for administrator rights.
- **No PATH changes.** The window's setup never touches `PATH`.
- **Uninstalling is narrow.** It removes only what setup installed; settings and data stay unless `/PURGE` is used.
- **Check what you download.** Each release carries `SHA256SUMS.txt`. Installers are unsigned unless signing is set up, so Windows may show SmartScreen warnings. See the [releasing notes](../../../docs/releasing.md).

## Not included

The window runs with your permissions and does not sandbox the media it downloads; only download from sources you trust.
