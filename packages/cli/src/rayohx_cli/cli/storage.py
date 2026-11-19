"""The ``storage`` commands: disk use, the low-space policy and safe cleanup."""

from typing import Annotated, Any, cast

import typer
from rayohx.platform.storage import StoragePolicy, format_size, parse_size

from rayohx_cli import format as fmt
from rayohx_cli import output, params
from rayohx_cli.cli.common import EXIT_FAILED
from rayohx_cli.cli.profile import run_store as run_platform
from rayohx_cli.cli.queue import Home
from rayohx_cli.cli.root import app

storage_app = typer.Typer(
    name="storage",
    help="Disk space: what downloads use, the low-space policy and safe cleanup.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)
app.add_typer(storage_app)

Size = Annotated[str | None, typer.Option(metavar="SIZE", help="For example 5GB or 500MB.")]


@storage_app.command("status")
def status(json_output: params.JsonOutput = False, home: Home = None) -> None:
    """Free space, what the queue uses, and the current low-space level."""
    snapshot = run_platform(home, lambda rayo: rayo.storage.snapshot())
    if json_output:
        output.print_json(snapshot.to_dict())
        return
    for volume in snapshot.volumes:
        output.console.print(
            f"{volume.role:<10} {fmt.size(volume.usage.free_bytes)} free of "
            f"{fmt.size(volume.usage.total_bytes)}  [{volume.level.name.lower()}]"
        )
    output.console.print(
        f"downloads {fmt.size(snapshot.output_bytes)}   working folders "
        f"{fmt.size(snapshot.workspace_bytes)} ({snapshot.workspace_count}), of which "
        f"{fmt.size(snapshot.incomplete_bytes)} is not needed by a finished download   "
        f"reserved {fmt.size(snapshot.reserved_bytes)}"
    )
    output.console.print(f"policy: {snapshot.policy.describe()}")


@storage_app.command("workspaces")
def workspaces(json_output: params.JsonOutput = False, home: Home = None) -> None:
    """List the working folders and whether each can be removed."""
    found = run_platform(home, lambda rayo: rayo.storage.workspaces())
    if json_output:
        output.print_json([w.to_dict() for w in found])
        return
    if not found:
        output.console.print("There are no working folders.")
        return
    for w in found:
        flag = "in use" if w.in_use else ("removable" if w.safe_to_remove else "kept")
        output.console.print(
            f"{w.name}  {fmt.size(w.size_bytes)}  {w.age_days:.1f}d  {flag}  {w.reason}"
        )


@storage_app.command("policy")
def policy(
    warn: Size = None,
    pause: Size = None,
    stop: Size = None,
    low_storage: Annotated[
        bool | None,
        typer.Option("--low-storage/--no-low-storage", help="Prefer ways that keep little data."),
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Remove all thresholds.")] = False,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Show or change the low-space policy: warn, pause and stop thresholds."""

    def act(rayo: Any) -> StoragePolicy:
        current: StoragePolicy = rayo.storage.policy()
        if clear:
            return cast(StoragePolicy, rayo.storage.set_policy(StoragePolicy()))
        if all(v is None for v in (warn, pause, stop, low_storage)):
            return current

        def pick(new: str | None, old: int | None) -> int | None:
            return old if new is None else parse_size(new)

        return cast(
            StoragePolicy,
            rayo.storage.set_policy(
                StoragePolicy(
                    warn_below=pick(warn, current.warn_below),
                    pause_below=pick(pause, current.pause_below),
                    stop_below=pick(stop, current.stop_below),
                    low_storage_mode=current.low_storage_mode
                    if low_storage is None
                    else low_storage,
                    resume_margin=current.resume_margin,
                )
            ),
        )

    result = run_platform(home, act)
    if json_output:
        output.print_json(result.to_dict())
    else:
        output.console.print(result.describe())


@storage_app.command("cleanup")
def cleanup(
    older_than: Annotated[
        float, typer.Option(help="Only working folders unused this many days.")
    ] = 7,
    yes: Annotated[bool, typer.Option("--yes", help="Remove them. Without it, only show.")] = False,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Show (or with --yes remove) abandoned working data. Downloaded files are never touched."""
    result = run_platform(
        home, lambda rayo: rayo.storage.cleanup(dry_run=not yes, older_than_days=older_than)
    )
    if json_output:
        output.print_json(result.to_dict())
        return
    items = result.removed if yes else result.plan.items
    for item in items:
        output.console.print(
            f"{item.kind}  {item.name}  {fmt.size(item.size_bytes)}  {item.reason}"
        )
    for line in result.plan.kept:
        output.console.print(f"[dim]kept: {line}[/dim]")
    verb = "Freed" if yes else "Would free"
    output.console.print(
        f"{verb} {format_size(result.freed_bytes if yes else result.plan.total_bytes)}."
    )
    if result.skipped:
        for line in result.skipped:
            output.error(line)
        raise typer.Exit(EXIT_FAILED)
