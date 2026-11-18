# queue

`rayohx queue` keeps a list of downloads that survives restarts, runs several at once and lets you pause, reorder and retry them.

[Back to the command line guide](../cli.md)

```bash
rayohx queue add URL... [OPTIONS]     # add jobs
rayohx queue run                      # run the queue in this terminal
rayohx queue list                     # see what is waiting, running or done
```

A queue lives in a small database in your data folder (`RAYOHX_HOME` moves it). Adding a job does not start it: `queue run` does, and keeps going until you press Ctrl-C. Only one process runs a queue at a time. Every other command works while it runs, from another terminal.

## Commands

| Command | What it does |
| --- | --- |
| `queue add URL...` | Add one job for each address. Takes `--input-file`, `--priority`, `--name`, `--max-attempts` and the common stream options (`--quality`, `--audio`, `--header`, `--cookie`, `--proxy`, `--directory`, ...). Prints each job id. |
| `queue list` | Jobs in the order they will run. `--state` filters, `--json` is for programs. |
| `queue show JOB` | One job with every run it has had. |
| `queue stats` | Counts by state and who is running the queue. |
| `queue pause JOB...` | Stop a job and keep what it downloaded. A running job gives up its place. |
| `queue resume JOB...` | Queue a paused job again. It continues where it stopped. |
| `queue cancel JOB...` | Cancel a job. |
| `queue retry JOB...` | Queue a failed or cancelled job again, as new. |
| `queue remove JOB...` | Forget a job that is not running. Downloaded files are never deleted. |
| `queue clear` | Forget finished jobs (`--state` completed, failed or cancelled). |
| `queue priority LEVEL JOB...` | `low`, `normal` or `high`. |
| `queue move JOB` | `--top`, `--bottom` or `--before OTHER`. |
| `queue export`, `queue import FILE` | Move jobs to another queue as JSON. Secrets are not exported. |
| `queue run` | Run the queue. `--max-active N` jobs at a time (default 2), `--until-empty` to stop when nothing is left, `--events` for JSON lines. |

Finished files go to `~/Downloads/RayoHX`, or the folder in `RAYOHX_DOWNLOAD_DIR`, unless a job sets `--directory`.

## Order

Higher priority runs first. Within a priority, jobs run in the order you arranged them (new jobs go last). Ties are broken by when the job was added, so the order is always the same.

## Pausing, stopping and crashes

- **Pause** cancels the running download but keeps its resume state, so the job leaves its place and anything waiting can start. Resuming continues from the last written segment.
- **Ctrl-C** on `queue run` puts running jobs back in the queue. They continue the next time.
- If the process is killed or the machine loses power, the next `queue run` finds the jobs that were running, marks them *recovered* and continues them. Finished work is not downloaded again.

## Failures and retries

A job that fails for a reason that may pass (a dropped connection, a server error, a failed segment) is run again after a growing delay, up to `--max-attempts` runs in total. Sign-in problems, bad settings and a full disk are not retried. One failed job never stops the others.

## Secrets

Cookies, secret headers (such as `Authorization`) and proxy passwords are never written to the queue database, to exports or to logs. They are kept in the system credential store when the optional `keyring` package is installed. Without it they live only in memory, and a job that needs them after a restart waits with *needs credentials* until you supply them again.

The address itself is stored, because the job needs it to run. If it carries a signing token, treat the queue database (`<data folder>/rayohx.db`) as private. It is created readable only by you where the system allows.
