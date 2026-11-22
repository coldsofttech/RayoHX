# Window guide

`rayohxu` is the RayoHX desktop window for Windows. It is a front end over the same engine as the
[command line](../../../cli/docs/guides/cli.md) and the [Python package](../../../core/docs/guides/python.md):
the window only shows your choices and results, and all the work is done by the `rayohx` library.

> **Not ready yet.** The window is still being built and currently shows an example page. The sections
> below are placeholders for what the finished window will cover, and will be filled in as the
> interface takes shape.

## Install

The window is installed with the Windows setup, `rayohxu-<version>-setup.exe`, from the
[releases page](https://github.com/coldsofttech/RayoHX/releases). It needs Windows 10 or 11 and the
Microsoft Edge WebView2 runtime, which both already include. It is not published on PyPI.

*Placeholder:* install steps with screenshots, silent install and uninstall, and upgrading.

## Open the window

*Placeholder:* starting from the Start Menu or desktop shortcut, and from a terminal with `rayohxu`.

```text
rayohxu --no-window    # serve the interface for a browser instead of a window
```

## Download a stream

Choose how to add a stream: **One address**, **Several addresses** (one per line; lines starting with
`#` are ignored) or **Playlist text** (paste the contents of an `.m3u8` file and give the base address
its relative links are resolved against). Look at what the stream offers, then choose
**Quick** (pick a quality) or **Advanced** (pick a stream, or narrow by size, bitrate, codec and range,
and choose audio and subtitle tracks the stream has). Only the open one is used, and one **Download**
button starts it. Picking a stream turns off the filters that no longer apply. For several addresses, **Download all** starts each one, and
**Inspect** looks at the first.

Open **Options** to set anything else: network (headers, cookies, proxy, retries and
speed limit), output, storage and engine. Fields left empty use the defaults. Fields that point to
files on this computer appear only when local files are allowed in the settings.

## Progress and results

*Placeholder:* the progress view, stopping and resuming a download, where the saved file goes, and what
errors look like.

## Settings

The download folder starts as `Downloads\RayoHX`. **Change** opens the system folder picker; the choice,
with theme, parallel segments, quality and replace-existing, is saved in the same SQLite database as the
download list. New downloads use it; existing ones stay where they are.

*Placeholder:* headers, cookies, proxy and certificates, and where the settings are kept.

## Keeping secrets safe

*Placeholder:* how the window handles headers, cookies and tokens. The protections that exist today are
in [security](../security.md).

## Troubleshooting

*Placeholder:* the window does not open (WebView2), the installer is blocked by Windows, and where to
find logs.

## Contents

| Page | What it covers |
|---|---|
| *Placeholder* | Pages for each screen, once the interface is built |
