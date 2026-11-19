# storage

`rayohx storage` shows how much disk the queue uses, sets the low-space policy and removes abandoned working data.

[Back to the command line guide](../cli.md)

| Command | What it does |
| --- | --- |
| `storage status` | Free space, what downloads and working folders use, and the current level (`ok`, `low`, `pause`, `stop`). `--json` is for programs. |
| `storage workspaces` | Working folders, their size and age, and whether each can be removed. |
| `storage policy` | Show the policy; change it with `--warn`, `--pause`, `--stop` (sizes such as `5GB`), `--low-storage/--no-low-storage`; `--clear` removes it. |
| `storage cleanup` | Show what would be removed. `--yes` removes it. `--older-than DAYS` (default 7). |

When free space falls under `--pause`, running downloads wait and go on by themselves once there is room; under `--stop` they fail with `STORAGE_LOW` and keep their progress. Downloads you paused yourself are never resumed for you. Cleanup never touches finished downloads or the working folder of a job that can still be resumed.
