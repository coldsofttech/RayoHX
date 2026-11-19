# daemon and migrate

`rayohx daemon` runs the queue as a service. `rayohx migrate` shows the result of an upgrade.

[Back to the command line guide](../cli.md)

```bash
rayohx daemon [--port 8765] [--host 127.0.0.1] [--no-health] [--metrics] [--max-active N]
rayohx migrate [--json]
```

## daemon

Runs the queue in the foreground until SIGTERM or Ctrl-C, writes one JSON log line per event to stderr, and answers `GET /health`, `GET /ready` and (with `--metrics`) `GET /metrics` on loopback. Stopping puts running jobs back in the queue; the next start continues them. It exits with 1 if another process already runs the queue.

See the [operations guide](../../../../../docs/operations.md) for a systemd unit, Docker and monitoring.

## migrate

Checks the database after an upgrade and shows whether a backup was made. The database upgrades by itself when RayoHX starts; this command only reports. With `--json` it prints `schema_version`, `latest_version`, `up_to_date`, `backup` and `recovered_database`. The API's saved default options (version 1) are imported as a profile named Default the first time the API starts.
