# diagnostics

`rayohx diagnostics` explains failures and makes a report you can share without leaking passwords.

[Back to the command line guide](../cli.md)

| Command | What it does |
| --- | --- |
| `diagnostics explain JOB_OR_CODE` | What happened, the likely cause, what was tried and what to do, for a job id or an error code such as `HTTP_403`. |
| `diagnostics network URL` | Checks name lookup, connection, TLS and the first response. `--job` uses that job's headers and proxy. Exits 1 if a step fails. |
| `diagnostics stream URL` | Describes a playlist and points out what is unusual. |
| `diagnostics report` | Saves a report (`--job`, `--url`, `--network`, `--stream`, `--out FILE`). Tokens, cookies, headers, proxy credentials and home folders are removed. |
| `diagnostics reports` | Lists saved reports. |
