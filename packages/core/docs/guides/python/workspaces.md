# Leftover folders

A download that is interrupted keeps a working folder (`.rayohx-…`, or a hash-named folder inside
the `workspace` folder you chose) so the next run can resume. If you never run it again, the folder
stays. These functions find and remove such folders. Removing one means that download starts again
from the beginning.

[Back to the Python guide](../python.md) · To resume a download, see [Downloading](downloading.md).

| Name | Module | Returns |
|---|---|---|
| [`find_workspaces(folders=None, older_than_days=0)`](#find_workspaces) | `rayohx` | `list[LeftoverWorkspace]` |
| [`remove_workspaces(workspaces)`](#remove_workspaces) | `rayohx` | `list[Path]` |
| [`LeftoverWorkspace`](#leftoverworkspace) | `rayohx` | a frozen dataclass |

## find_workspaces

```python
rayohx.find_workspaces(folders: Iterable[Path] | None = None, older_than_days: float = 0) -> list[LeftoverWorkspace]
```

Looks directly inside each folder (default: the current folder) and returns the working folders it
finds: only those not used for at least `older_than_days`. Folders that cannot
be read are skipped. Nothing is changed.

## remove_workspaces

```python
rayohx.remove_workspaces(workspaces: Iterable[LeftoverWorkspace]) -> list[Path]
```

Deletes the given folders and returns the paths removed. A workspace with `in_use` set is skipped.

## LeftoverWorkspace

| Field | Type | Meaning |
|---|---|---|
| `path` | `Path` | The folder. |
| `size` | `int` | Bytes on disk. |
| `age_days` | `float` | Days since it was last used. |
| `in_use` | `bool` | A running download holds it. |

```python
import rayohx

old = [w for w in rayohx.find_workspaces(older_than_days=7) if not w.in_use]
print(f"{len(old)} folders, {sum(w.size for w in old)} bytes")
rayohx.remove_workspaces(old)
```
