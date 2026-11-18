# profile

`rayohx profile` saves the settings you use again and again under a name.

[Back to the command line guide](../cli.md)

```bash
rayohx profile list
rayohx download URL --profile archive
rayohx queue add URL --profile mobile --max-resolution 720p
```

## Built-in profiles

| Profile | What it does |
| --- | --- |
| `best-quality` | The highest quality the stream offers. |
| `1080p` | The best quality up to 1080p. |
| `mobile` | Up to 480p and 1.5 Mbps, as MP4, using little working space. |
| `archive` | The best quality with every audio and subtitle track, as Matroska, five attempts, strong verification. Needs FFmpeg. |
| `custom` | The engine's defaults. Duplicate it to start your own. |

Built-in profiles cannot be changed. Duplicate one, then change the copy.

## Commands

| Command | What it does |
| --- | --- |
| `profile list` | The profiles, and why one cannot run here (for example no FFmpeg). `--json` is for programs. |
| `profile show NAME` | One profile in full. |
| `profile create NAME` | Save a new profile: `--from BASE`, `--set KEY=VALUE` (repeat), `--naming`, `--verify`, `--metadata`, `--max-attempts`, `-d`. |
| `profile edit NAME` | Change a profile of yours: the same options, plus `--unset KEY`. |
| `profile duplicate NAME [NEW]` | Copy any profile. |
| `profile rename NAME NEW` | Give a profile of yours another name. Its id stays. |
| `profile delete NAME` | Delete a profile of yours. Queued jobs keep their settings. |
| `profile default [NAME]` | Show, set (or `--clear`) the profile `queue add` uses when none is named. |
| `profile validate NAME` | Check a profile, including whether this machine can run it. |
| `profile export [NAME...]`, `profile import FILE` | Move profiles between machines as JSON. |

## Settings

`--set` takes `section.key=value`. The sections are `selection`, `output`, `storage` and `network`, plus the top-level `concurrency`, `resume` and `allow_file_keys`.

```bash
rayohx profile create Movies --from 1080p \
  --set selection.audio_languages=en,de \
  --set output.format=mkv \
  --naming "{name} {date}"
```

Lists take commas. `selection.audio_languages=*` and `selection.subtitle_languages=*` mean every track. A value is checked when you save, so a mistake shows up now and not hours into a download. A profile **never holds secrets** (cookies, `Authorization` and similar headers, proxy logins): give those when you add the download.

## How a profile and your options combine

1. The engine's defaults.
2. The profile's settings.
3. The options you give on this command line (or in the environment).

The settings file (`rayohx.toml`) is below the profile. A job copies its settings when it is added, so editing or deleting the profile later does not change jobs already in the queue.

`queue add` uses the default profile when you name none. `download` uses a profile only when you pass `--profile`.

## File names

`--naming` is a template made of text and these tokens: `{name}` (from the address), `{date}`, `{time}`, `{job}`, `{profile}`, `{host}`. It cannot contain folders. The same input always gives the same name, and anything unsafe on Windows, macOS or Linux is replaced. A name you give with `--name` or `-o` wins over the template.

## `metadata` and `verify`

These are stored in the profile now (`metadata`: `preserve`, `minimal`, `none`, `custom`; `verify`: `none`, `basic`, `strong`) and take effect when metadata handling and verification arrive in a later release.
