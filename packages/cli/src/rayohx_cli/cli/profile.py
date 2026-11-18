"""The ``profile`` commands: named, reusable settings for downloads."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rayohx import Rayo
from rayohx.capabilities import detect
from rayohx.errors import ConfigurationError, RayoHXError
from rayohx.platform.jobs import RetryPolicy
from rayohx.platform.profiles import (
    METADATA_POLICIES,
    TOKENS,
    VERIFY_LEVELS,
    DownloadProfile,
    validate,
)
from rayohx.platform.profiles.rules import default_options

from rayohx_cli import output, params
from rayohx_cli.cli.common import EXIT_FAILED, EXIT_USAGE, usage_error
from rayohx_cli.cli.queue import Home, open_platform
from rayohx_cli.cli.root import app

profile_app = typer.Typer(
    name="profile",
    help="Saved, reusable download settings: quality, audio, output format, naming and more.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)
app.add_typer(profile_app)

Ref = Annotated[str, typer.Argument(help="A profile's id or name.")]
Setting = Annotated[
    list[str] | None,
    typer.Option(
        "--set",
        "-s",
        metavar="KEY=VALUE",
        help=(
            "A setting, such as selection.max_resolution=720p or output.format=mkv. Lists take "
            "commas (selection.audio_languages=en,de). Repeat for more."
        ),
    ),
]
Naming = Annotated[
    str | None,
    typer.Option(
        "--naming", help=f"File name template using {', '.join('{' + t + '}' for t in TOKENS)}."
    ),
]
Metadata = Annotated[
    str | None, typer.Option("--metadata", help=f"One of: {', '.join(METADATA_POLICIES)}.")
]
Verify = Annotated[
    str | None, typer.Option("--verify", help=f"One of: {', '.join(VERIFY_LEVELS)}.")
]
Attempts = Annotated[
    int | None,
    typer.Option("--max-attempts", min=1, max=20, help="Runs in total if a download fails."),
]


def parse_setting(text: str) -> tuple[str, Any]:
    """``section.key=value`` as a path and a value of the right kind."""
    path, sep, raw = text.partition("=")
    path = path.strip()
    if not sep or not path:
        usage_error(
            ConfigurationError(f"{text!r} is not KEY=VALUE.", hint="Example: output.format=mkv")
        )
    reference: Any = default_options()
    for part in path.split("."):
        reference = reference.get(part) if isinstance(reference, dict) else None
    if isinstance(reference, list):
        return path, [item.strip() for item in raw.split(",") if item.strip()]
    try:
        return path, json.loads(raw)
    except ValueError:
        return path, raw


def apply_settings(
    base: dict[str, Any], settings: list[str] | None, unset: list[str] | None = None
) -> dict[str, Any]:
    options: dict[str, Any] = json.loads(json.dumps(base))
    for text in settings or []:
        path, value = parse_setting(text)
        cursor = options
        *parents, last = path.split(".")
        for part in parents:
            if not isinstance(cursor.get(part), dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[last] = value
    for path in unset or []:
        cursor = options
        *parents, last = path.split(".")
        for part in parents:
            cursor = cursor.get(part, {})
            if not isinstance(cursor, dict):
                break
        else:
            cursor.pop(last, None)
    for key in [k for k, v in options.items() if v == {}]:
        del options[key]
    return options


def describe(profile: DownloadProfile) -> dict[str, Any]:
    data = profile.to_dict()
    data["id"] = profile.id
    data["builtin"] = profile.builtin
    return data


def run_store(home: Path | None, action: Any) -> Any:
    rayo = open_platform(home)
    try:
        return action(rayo)
    except RayoHXError as exc:
        usage_error(exc)
    finally:
        rayo.close()


def notes_for(profile: DownloadProfile, caps: Any) -> list[str]:
    return [f.message for f in validate(profile, caps, machine_checks=True) if f.level == "error"]


@profile_app.command("list")
def list_profiles(json_output: params.JsonOutput = False, home: Home = None) -> None:
    """Show the built-in profiles and yours."""

    def work(rayo: Rayo) -> tuple[list[DownloadProfile], str | None]:
        current = rayo.profiles.default()
        return rayo.profiles.list(), current.id if current else None

    profiles, default = run_store(home, work)
    caps = detect()
    if json_output:
        output.print_json(
            [
                {**describe(p), "default": p.id == default, "problems": notes_for(p, caps)}
                for p in profiles
            ]
        )
        return
    from rich.table import Table

    table = Table(box=None, pad_edge=False)
    for column in ("ID", "NAME", "KIND", "DEFAULT", "NOTES"):
        table.add_column(column)
    for p in profiles:
        problems = notes_for(p, caps)
        table.add_row(
            p.id,
            p.name,
            "built-in" if p.builtin else "yours",
            "yes" if p.id == default else "",
            problems[0] if problems else p.description,
        )
    output.console.print(table)


@profile_app.command("show")
def show(ref: Ref, json_output: params.JsonOutput = False, home: Home = None) -> None:
    """Show one profile and whether it can run on this machine."""
    profile = run_store(home, lambda rayo: rayo.profiles.require(ref))
    problems = [f.to_dict() for f in validate(profile, detect(), machine_checks=True)]
    if json_output:
        output.print_json({**describe(profile), "findings": problems})
        return
    output.console.print(
        f"[bold]{profile.name}[/bold] ({profile.id}, {'built-in' if profile.builtin else 'yours'})"
    )
    if profile.description:
        output.console.print(profile.description)
    output.console.print_json(
        json.dumps(dict(profile.options))
    ) if profile.options else output.console.print("Settings: the engine's defaults")
    output.console.print(
        f"retry: {profile.retry.max_attempts if profile.retry else 'default'} runs   "
        f"naming: {profile.naming or '-'}   metadata: {profile.metadata}   verify: {profile.verify}"
    )
    for finding in problems:
        output.error(f"{finding['field']}: {finding['message']}", finding["hint"])


def retry_of(attempts: int | None, current: RetryPolicy | None = None) -> RetryPolicy | None:
    if attempts is None:
        return current
    base = current or RetryPolicy()
    return RetryPolicy(
        max_attempts=attempts,
        initial_delay=base.initial_delay,
        factor=base.factor,
        max_delay=base.max_delay,
        categories=base.categories,
    )


@profile_app.command("create")
def create(
    name: Annotated[str, typer.Argument(help="The new profile's name.")],
    base: Annotated[str | None, typer.Option("--from", help="Start from this profile.")] = None,
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    setting: Setting = None,
    naming: Naming = None,
    metadata: Metadata = None,
    verify: Verify = None,
    max_attempts: Attempts = None,
    home: Home = None,
) -> None:
    """Save a new profile."""

    def work(rayo: Rayo) -> DownloadProfile:
        source = rayo.profiles.require(base) if base else None
        options = apply_settings(dict(source.options) if source else {}, setting)
        return rayo.profiles.create(
            name,
            description=description or (source.description if source else ""),
            options=options,
            retry=retry_of(max_attempts, source.retry if source else None),
            naming=naming if naming is not None else (source.naming if source else None),
            metadata=metadata or (source.metadata if source else "preserve"),
            verify=verify or (source.verify if source else "basic"),
        )

    profile = run_store(home, work)
    output.data(profile.id)
    output.message(f"Saved the profile {profile.name!r}.")


@profile_app.command("edit")
def edit(
    ref: Ref,
    setting: Setting = None,
    unset: Annotated[
        list[str] | None, typer.Option("--unset", metavar="KEY", help="Go back to the default.")
    ] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    naming: Naming = None,
    metadata: Metadata = None,
    verify: Verify = None,
    max_attempts: Attempts = None,
    home: Home = None,
) -> None:
    """Change a profile of yours. Built-in profiles are fixed: duplicate one first."""

    def work(rayo: Rayo) -> DownloadProfile:
        profile = rayo.profiles.require(ref)
        changes: dict[str, Any] = {}
        if setting or unset:
            changes["options"] = apply_settings(dict(profile.options), setting, unset)
        if description is not None:
            changes["description"] = description
        if naming is not None:
            changes["naming"] = naming or None
        if metadata is not None:
            changes["metadata"] = metadata
        if verify is not None:
            changes["verify"] = verify
        if max_attempts is not None:
            changes["retry"] = retry_of(max_attempts, profile.retry)
        return rayo.profiles.update(profile.id, **changes)

    profile = run_store(home, work)
    output.message(f"Saved the profile {profile.name!r}.")


@profile_app.command("duplicate")
def duplicate(
    ref: Ref,
    name: Annotated[str | None, typer.Argument(help="Name of the copy.")] = None,
    home: Home = None,
) -> None:
    """Copy a profile (built-in or yours) so you can change the copy."""
    copy = run_store(home, lambda rayo: rayo.profiles.duplicate(ref, name))
    output.data(copy.id)


@profile_app.command("rename")
def rename(ref: Ref, new_name: Annotated[str, typer.Argument()], home: Home = None) -> None:
    """Give a profile of yours another name."""
    run_store(home, lambda rayo: rayo.profiles.rename(ref, new_name))
    output.message("Renamed.")


@profile_app.command("delete")
def delete(
    ref: Ref,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask first.")] = False,
    home: Home = None,
) -> None:
    """Delete a profile of yours. Jobs already queued keep their settings."""
    if not yes and not typer.confirm(f"Delete the profile {ref!r}?"):
        raise typer.Exit(EXIT_FAILED)
    run_store(home, lambda rayo: rayo.profiles.delete(ref))
    output.message("Deleted.")


@profile_app.command("default")
def default(
    ref: Annotated[
        str | None, typer.Argument(help="The profile to use when none is named.")
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Use no default profile.")] = False,
    home: Home = None,
) -> None:
    """Show, set or clear the default profile (used by [bold]queue add[/bold])."""
    if ref and clear:
        usage_error(ConfigurationError("Give a profile or --clear, not both."))

    def work(rayo: Rayo) -> DownloadProfile | None:
        if clear:
            rayo.profiles.set_default(None)
            return None
        if ref:
            return rayo.profiles.set_default(ref)
        return rayo.profiles.default()

    profile = run_store(home, work)
    if profile:
        output.data(profile.id)
    elif not clear and not ref:
        output.message("There is no default profile.")


@profile_app.command("validate")
def validate_command(ref: Ref, home: Home = None) -> None:
    """Check a profile, including whether this machine can run it."""
    profile = run_store(home, lambda rayo: rayo.profiles.require(ref))
    findings = validate(profile, detect(), machine_checks=True)
    for finding in findings:
        output.error(f"{finding.field}: {finding.message}", finding.hint)
    if any(f.level == "error" for f in findings):
        raise typer.Exit(EXIT_USAGE)
    output.message(f"{profile.name} is valid.")


@profile_app.command("export")
def export(
    refs: Annotated[
        list[str] | None, typer.Argument(help="Profiles (default: all of yours).")
    ] = None,
    to: Annotated[Path | None, typer.Option("--output", "-o", help="Write to this file.")] = None,
    home: Home = None,
) -> None:
    """Write profiles as JSON. They never contain secrets."""
    data = run_store(home, lambda rayo: rayo.profiles.export_data(refs or None))
    text = json.dumps(data, indent=2, sort_keys=True)
    if to is None:
        output.data(text)
    else:
        to.write_text(text + "\n", encoding="utf-8")
        output.message(f"Wrote {len(data['profiles'])} profile(s) to {to}.")


@profile_app.command("import")
def import_profiles(
    file: Annotated[Path, typer.Argument(help="A file from 'profile export' (- is stdin).")],
    on_conflict: Annotated[
        str, typer.Option("--on-conflict", help="When a name is taken: rename, skip or error.")
    ] = "rename",
    home: Home = None,
) -> None:
    """Add the profiles in an exported file."""
    try:
        text = sys.stdin.read() if str(file) == "-" else file.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as exc:
        usage_error(ConfigurationError(f"{file} cannot be read as profiles: {exc}"))
    saved = run_store(home, lambda rayo: rayo.profiles.import_data(data, on_conflict=on_conflict))
    for profile in saved:
        output.data(profile.id)
    output.message(f"Added {len(saved)} profile(s).")
