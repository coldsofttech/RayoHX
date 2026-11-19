# User guide

A tour of what RayoHX does beyond one download, with the same ideas in the command line, the window and the API.

## The queue

Jobs wait in a list that survives restarts. They run in priority order (`low`, `normal`, `high`), then in the order you put them; a few run at once.

```bash
rayohx queue add URL1 URL2 --profile 1080p --priority high
rayohx queue run                 # or: rayohx daemon
rayohx queue list
rayohx queue pause ID            # keeps the work already done
rayohx queue retry ID
```

In the window, the **Queue** page lists the same jobs. Tick several to pause, resume, cancel, retry, remove or change their priority together; move a waiting job to the top or bottom; open **Show details** to see why a job failed, how it was verified and every run it had. Over HTTP, see `/api/v2/queue` and `/api/v2/queue/actions`.

A failed job is retried by itself if the problem may pass (a network error, a busy server), with a growing delay. A wrong password or an expired link is not retried; you see why and what to do.

## Profiles

A profile is a named set of settings: quality, audio and subtitles, output format, file name, retries, verification, metadata. Built in: **Best quality**, **1080p**, **Mobile**, **Archive** and **Custom**. Make your own with `rayohx profile create`, and pick one with `--profile NAME`. A job copies its profile when queued, so editing a profile later never changes jobs already waiting. Anything you give on the command line wins over the profile.

## Checking and metadata

`--verify basic|strong` checks the finished file (structure, and with FFmpeg its streams and duration); a file that fails is kept as `.invalid` and the job fails rather than pretending to succeed. `--checksum HASH` compares a checksum. `--metadata preserve|minimal|none` decides what the file records (title, language, chapters, cover picture). `rayohx info URL --media` shows what a stream contains and whether it can be saved in a format before you start.

## When something goes wrong

```bash
rayohx diagnostics explain JOB_ID        # what happened, likely cause, what to do
rayohx diagnostics network URL           # name lookup, connection, TLS, response
rayohx diagnostics report --job JOB_ID   # a report that is safe to share
```

Reports remove tokens, cookies, headers, proxy passwords and your home folder name. The window offers the same in a job's details.

## Disk space

`rayohx storage status` shows free space and what downloads use. Set `warn`, `pause` and `stop` limits with `rayohx storage policy`; the queue then waits or stops before the disk is full, and continues by itself when space returns. `rayohx storage cleanup` shows (and with `--yes` removes) leftovers of interrupted downloads. Finished downloads are never touched. The window has the same on its **Storage** page.

## Upgrading from version 1

Nothing to do: the database upgrades itself (after a backup), and the API's saved defaults become a profile named **Default**. `rayohx migrate` shows what happened. See the [operations guide](operations.md).
