# Operations guide

Running RayoHX unattended: on a server, a NAS, in a container or in CI.

## Run the queue as a service

`rayohx daemon` runs the queue in the foreground until it gets SIGTERM or Ctrl-C. It writes one JSON object per log line to stderr and answers health checks on loopback.

```bash
rayohx --non-interactive daemon --port 8765 --metrics
```

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | 200 while the process works. The body shows the runner, queued and active jobs, the storage level and the schema version. |
| `GET /ready` | 200 once the runner has started, otherwise 503. Use it for readiness probes. |
| `GET /metrics` | Prometheus text. Only with `--metrics`. |

The endpoint binds to `127.0.0.1` and shows state, never settings or secrets. Put it behind a proxy if you need it elsewhere; the daemon logs a warning if you bind it to another address. `--no-health` turns it off.

Stopping is safe at any time: running jobs go back to the queue and continue on the next start. If the process is killed, the next start finds them half done (`recovered`) and continues them.

A systemd unit is in [examples/rayohx.service](examples/rayohx.service). For Docker use the `rayohx-headless` image (see [Docker](../packages/docker/docs/docker.md)), with the data folder on a volume and `/health` as the health check.

Only one process runs a queue. A second `rayohx daemon` (or `queue run`) on the same data folder exits with an error; the API detects the running process and reports `"runner": "another process"`.

## Where things are

`RAYOHX_HOME` puts the database, backups, reports and lock in one folder. Without it the user's data folders are used; a `portable` marker file next to the program keeps everything beside it. `RAYOHX_DOWNLOAD_DIR` sets where finished files go.

## Adding work

- `rayohx queue add URL... --profile NAME --priority high` from a script or cron.
- `POST /api/v2/queue` from another service (use an API key; see [security](security.md)).
- The daemon picks new jobs up at once.

## Disk space

Set limits so a full disk never corrupts anything:

```bash
rayohx storage policy --warn 20GB --pause 10GB --stop 2GB
```

Under the pause limit, downloads wait and continue by themselves when space returns; under the stop limit they fail with `STORAGE_LOW` (exit code 5) and keep their progress. `rayohx storage cleanup` previews and removes abandoned working folders.

## CI and scripts

- `--non-interactive` (or `RAYOHX_NON_INTERACTIVE=1`) never waits for an answer: a command that needs confirmation exits with 2 and says to add `--yes`.
- `--json` prints a JSON document on stdout; messages stay on stderr.
- Exit codes tell a script why it failed: `0` success, `1` failed, `2` usage, `3` verification, `4` authentication, `5` storage, `6` automation, `7` some of a batch failed, `130` cancelled. `RAYOHX_EXIT_CODES=legacy` makes every failure `1` again (it exists for scripts written for version 1 and will be removed in a later release).
- `rayohx queue run --until-empty` is the batch mode: it exits when the queue is empty, with the failed jobs' code.

## Upgrading

1. Stop the daemon.
2. Install the new version.
3. Start it. The database upgrades by itself, after a backup in `backups/` next to it. Run `rayohx migrate` to see the result.

A database written by a newer version is refused rather than damaged. To go back, stop RayoHX and restore the backup that was made before the upgrade.

### From version 1

Version 1 kept one thing outside the engine: the API's saved default options (`api-defaults.json`). The first time the API starts, they are imported as a profile named **Default** (not made the default profile, so nothing changes for jobs you queue without a profile). The old file stays where it is. Make the profile the default with `rayohx profile default default`.

Scripts: `/api/v1` keeps working. Failures that used to exit `1` may now return `3`, `4` or `5` (see above); set `RAYOHX_EXIT_CODES=legacy` for one release if you need the old behavior.

## Monitoring

- Scrape `/metrics` (daemon) or `GET /api/v2/metrics/prometheus` (API).
- Watch for `storage.paused`, `storage.stopped` and `queue.job_failed` events in the log.
- `rayohx diagnostics report --job ID` makes a report you can attach to an issue without exposing tokens, cookies or personal paths.

## Performance

`scripts/benchmark.py --platform` measures the queue itself. On a development machine: adding a job takes about 1 ms, running instant jobs about 4 ms each, writing events about 12,000 per second, and a 500-job queue plus 5,000 events fit in about 230 MB of memory. See [benchmarks](benchmarks.md).
