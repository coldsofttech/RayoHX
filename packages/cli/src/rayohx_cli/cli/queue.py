"""The ``queue`` commands: a download queue that survives restarts.

Jobs are stored in the platform database. ``queue add`` only adds a job; ``queue run`` runs the
queue in this terminal until you stop it. Every other command works whether or not a runner is
active, in this or another process: a running job is paused or cancelled through the database.
"""

import signal
import time
from pathlib import Path
from types import FrameType
from typing import Annotated, Any

import typer
from rayohx import OutputFormat, Rayo, StorageStrategy
from rayohx.config import validate_url
from rayohx.errors import ConfigurationError, RayoHXError
from rayohx.platform import BulkResult, JobRecord, JobState, QueuePriority, RetryPolicy
from rayohx.platform.errors import RunnerLockedError
from rayohx.platform.events import PlatformEvent

from rayohx_cli import format as fmt
from rayohx_cli import output, params
from rayohx_cli.cli.common import EXIT_FAILED, EXIT_USAGE, gather_urls, make_config, usage_error
from rayohx_cli.cli.overrides import overrides_from
from rayohx_cli.cli.root import app

queue_app = typer.Typer(
    name="queue",
    help="Queue downloads, order them and run them. Jobs survive restarts.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)
app.add_typer(queue_app)

Ids = Annotated[list[str], typer.Argument(help="Job ids (see [bold]rayohx queue list[/bold]).")]
Json = Annotated[bool, typer.Option("--json", help="Print JSON on stdout, for other programs.")]
PriorityArg = Annotated[
    str, typer.Option("--priority", "-p", help="low, normal or high.", case_sensitive=False)
]
HOME_HELP = "Keep the queue under this folder instead of the user folders."
Home = Annotated[
    Path | None, typer.Option("--home", envvar="RAYOHX_HOME", help=HOME_HELP, hidden=True)
]


def open_platform(home: Path | None = None, **kwargs: Any) -> Rayo:
    try:
        return Rayo(home=home, **kwargs)
    except RayoHXError as exc:
        output.error_from(exc)
        raise typer.Exit(EXIT_FAILED) from exc


def retry_given(ctx: typer.Context) -> bool:
    """Whether --max-attempts was given (otherwise the profile's retry policy applies)."""
    from rayohx_cli.cli.overrides import given

    return "max_attempts" in given(ctx)


def priority_of(value: str) -> QueuePriority:
    try:
        return QueuePriority.parse(value)
    except ValueError as exc:
        usage_error(ConfigurationError(str(exc)))


def short(record: JobRecord) -> str:
    return record.url if len(record.url) <= 60 else record.url[:57] + "..."


def progress_text(record: JobRecord) -> str:
    if record.state is JobState.COMPLETED:
        return fmt.size(record.output_size or 0)
    progress = record.progress or {}
    fraction = progress.get("fraction")
    return f"{fraction * 100:.0f}%" if isinstance(fraction, float) else ""


def show_jobs(records: list[JobRecord]) -> None:
    from rich.table import Table

    table = Table(box=None, pad_edge=False)
    for column in ("ID", "STATE", "PRIORITY", "PROGRESS", "TRIES", "URL"):
        table.add_column(column)
    for r in records:
        state = r.state.value + (" (needs credentials)" if r.needs_credentials else "")
        table.add_row(
            r.id,
            state,
            r.priority.name.lower(),
            progress_text(r),
            f"{r.attempts}/{r.spec.retry.max_attempts}",
            short(r),
        )
    output.console.print(table)


def report(result: BulkResult, verb: str) -> None:
    for job_id in result.done:
        output.message(f"{verb} {job_id}")
    for job_id, why in result.failed.items():
        output.error(f"{job_id}: {why}")
    if result.failed:
        raise typer.Exit(EXIT_FAILED)


def run_action(ids: list[str], home: Path | None, verb: str, action: str) -> None:
    rayo = open_platform(home)
    try:
        report(getattr(rayo.queue, action)(ids), verb)
    finally:
        rayo.close()


@queue_app.command("add")
def add(
    ctx: typer.Context,
    urls: params.Urls = None,
    input_file: params.InputFile = None,
    name: Annotated[
        str | None, typer.Option("--name", help="File name for a single address.")
    ] = None,
    priority: PriorityArg = "normal",
    max_attempts: Annotated[
        int, typer.Option("--max-attempts", min=1, max=20, help="Runs in total if it fails.")
    ] = 3,
    quality: params.Quality = "best",
    max_resolution: params.MaxResolution = None,
    max_bitrate: params.MaxBitrate = None,
    codec: params.Codec = None,
    audio: params.Audio = None,
    subtitles: params.Subtitles = None,
    video_only: params.VideoOnly = False,
    format_: params.Format = OutputFormat.AUTO,
    overwrite: params.Overwrite = False,
    directory: params.Directory = None,
    verify: params.Verify = None,
    checksum: params.Checksum = None,
    metadata: params.Metadata = None,
    title: params.Title = None,
    name_template: params.NameTemplate = None,
    header: params.Header = None,
    cookie: params.Cookie = None,
    user_agent: params.UserAgent = None,
    referer: params.Referer = None,
    origin: params.Origin = None,
    proxy: params.Proxy = None,
    proxy_username: params.ProxyUsername = None,
    proxy_password: params.ProxyPassword = None,
    retries: params.Retries = None,
    concurrency: params.Concurrency = None,
    storage: params.Storage = StorageStrategy.AUTO,
    profile: params.ProfileOption = None,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Add one job for each address, with the settings of a profile and any options you give.

    Without --profile the default profile is used, if one is set ([bold]rayohx profile
    default[/bold]). Secrets (cookies, headers, passwords) are kept apart from the settings.
    """
    addresses = gather_urls(urls or [], input_file)
    if name and len(addresses) > 1:
        usage_error(ConfigurationError("--name can only be used with a single address."))
    config = make_config(
        quality=quality,
        max_resolution=max_resolution,
        max_bitrate=max_bitrate,
        codec=codec,
        audio=audio or [],
        subtitles=subtitles or [],
        video_only=video_only,
        format=format_,
        overwrite=overwrite,
        directory=directory,
        verify=verify,
        checksum=checksum,
        metadata=metadata,
        title=title,
        name_template=name_template,
        header=header or [],
        cookie=cookie or [],
        user_agent=user_agent,
        referer=referer,
        origin=origin,
        proxy=proxy,
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        retries=retries,
        concurrency=concurrency,
        storage=storage,
    )
    level = priority_of(priority)
    overrides, secrets = overrides_from(ctx, config)
    try:
        for address in addresses:  # check them all first: nothing is added if one is wrong
            validate_url(address)
    except ConfigurationError as exc:
        usage_error(exc)
    rayo = open_platform(home)
    records: list[JobRecord] = []
    try:
        for address in addresses:
            records.append(
                rayo.queue.add(
                    address,
                    profile=profile,
                    overrides=overrides,
                    secrets=secrets,
                    priority=level,
                    output_name=name,
                    retry=RetryPolicy(max_attempts=max_attempts) if retry_given(ctx) else None,
                )
            )
    except RayoHXError as exc:
        usage_error(exc)
    finally:
        rayo.close()
    if json_output:
        output.print_json([r.to_dict() for r in records])
    else:
        for r in records:
            output.data(r.id)
        output.message(f"Added {len(records)} job(s). Run them with: rayohx queue run")


@queue_app.command("list")
def list_jobs(
    state: Annotated[
        list[JobState] | None, typer.Option("--state", "-s", help="Only these states.")
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", "-n", min=1)] = None,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Show jobs in the order they will run."""
    rayo = open_platform(home)
    try:
        records = rayo.queue.list(states=state, limit=limit)
        stats = rayo.queue.stats()
    finally:
        rayo.close()
    if json_output:
        output.print_json({"items": [r.to_dict() for r in records], "stats": stats})
    elif records:
        show_jobs(records)
    else:
        output.message("The queue is empty.")


@queue_app.command("show")
def show(job: str, json_output: params.JsonOutput = False, home: Home = None) -> None:
    """Show one job and every run it has had."""
    rayo = open_platform(home)
    try:
        record = rayo.queue.get(job)
        history = rayo.queue.attempts(job) if record else []
    finally:
        rayo.close()
    if record is None:
        output.error(f"No job {job}.")
        raise typer.Exit(EXIT_FAILED)
    if json_output:
        output.print_json({**record.to_dict(), "attempt_history": history})
        return
    for key, value in record.to_dict().items():
        if value not in (None, False) and key != "progress":
            output.console.print(f"[bold]{key}[/bold]: {value}")
    for run in history:
        output.console.print(
            f"  run {run['attempt']}: {run['outcome'] or 'running'} {run['error_code'] or ''}"
        )


@queue_app.command("verification")
def verification(job: str, json_output: params.JsonOutput = False, home: Home = None) -> None:
    """Show how a finished job was checked: every check, and what could not be done."""
    rayo = open_platform(home)
    try:
        record = rayo.queue.get(job)
        report = rayo.queue.verification(job)
    finally:
        rayo.close()
    if record is None:
        output.error(f"No job {job}.")
        raise typer.Exit(EXIT_FAILED)
    if report is None:
        output.message("This job was not verified.")
        return
    if json_output:
        output.print_json(report)
        return
    output.console.print(f"[bold]{report['status']}[/bold] ({report['level']} verification)")
    for check in report["checks"]:
        detail = f": {check['detail']}" if check["detail"] else ""
        output.console.print(f"  {check['status']:8} {check['name']}{detail}")
    if report.get("checksum"):
        sums = report["checksum"]
        output.console.print(f"  {sums['algorithm']} {sums['value']}")
    if report.get("invalid_path"):
        output.console.print(f"  The file was kept as {report['invalid_path']}")
    if report["status"] == "failed":
        raise typer.Exit(EXIT_FAILED)


@queue_app.command("stats")
def stats(json_output: params.JsonOutput = False, home: Home = None) -> None:
    """Counts of jobs by state."""
    rayo = open_platform(home)
    try:
        data = rayo.queue.stats()
    finally:
        rayo.close()
    if json_output:
        output.print_json(data)
    else:
        for state, count in data["counts"].items():
            if count:
                output.console.print(f"{state:12} {count}")
        output.console.print(f"{'runner':12} {data['runner']}")


@queue_app.command("pause")
def pause(ids: Ids, home: Home = None) -> None:
    """Stop jobs and keep what they downloaded. A running job gives up its place."""
    run_action(ids, home, "Pausing", "pause")


@queue_app.command("resume")
def resume(ids: Ids, home: Home = None) -> None:
    """Queue paused jobs again."""
    run_action(ids, home, "Resumed", "resume")


@queue_app.command("cancel")
def cancel(ids: Ids, home: Home = None) -> None:
    """Cancel jobs."""
    run_action(ids, home, "Cancelling", "cancel")


@queue_app.command("retry")
def retry(ids: Ids, home: Home = None) -> None:
    """Queue failed or cancelled jobs again."""
    run_action(ids, home, "Queued again", "retry")


@queue_app.command("remove")
def remove(ids: Ids, home: Home = None) -> None:
    """Forget jobs that are not running. Downloaded files are never deleted."""
    run_action(ids, home, "Removed", "remove")


@queue_app.command("clear")
def clear(
    state: Annotated[
        list[JobState] | None,
        typer.Option("--state", "-s", help="completed, failed or cancelled (default: completed)."),
    ] = None,
    home: Home = None,
) -> None:
    """Forget every finished job of the chosen states."""
    chosen = state or [JobState.COMPLETED]
    if any(not s.is_terminal for s in chosen):
        usage_error(ConfigurationError("Only completed, failed or cancelled jobs can be cleared."))
    rayo = open_platform(home)
    try:
        ids = [j.id for j in rayo.queue.list(states=chosen)]
        if ids:
            report(rayo.queue.remove(ids), "Removed")
        else:
            output.message("Nothing to clear.")
    finally:
        rayo.close()


@queue_app.command("priority")
def priority_command(
    level: Annotated[str, typer.Argument(help="low, normal or high.")], ids: Ids, home: Home = None
) -> None:
    """Change the priority of jobs."""
    chosen = priority_of(level)
    rayo = open_platform(home)
    try:
        report(rayo.queue.set_priority(ids, chosen), f"Priority {chosen.name.lower()} for")
    finally:
        rayo.close()


@queue_app.command("move")
def move(
    job: str,
    before: Annotated[str | None, typer.Option("--before", help="Put it before this job.")] = None,
    top: Annotated[bool, typer.Option("--top", help="Put it first.")] = False,
    bottom: Annotated[bool, typer.Option("--bottom", help="Put it last.")] = False,
    home: Home = None,
) -> None:
    """Change where a job stands among jobs of its priority."""
    if [bool(before), top, bottom].count(True) != 1:
        usage_error(ConfigurationError("Choose exactly one of --before, --top and --bottom."))
    rayo = open_platform(home)
    try:
        if before:
            rayo.queue.move_before(job, before)
        elif top:
            report(rayo.queue.move_to_top(job), "Moved to the top:")
        else:
            report(rayo.queue.move_to_bottom(job), "Moved to the bottom:")
    except RayoHXError as exc:
        output.error_from(exc)
        raise typer.Exit(EXIT_FAILED) from exc
    finally:
        rayo.close()


@queue_app.command("export")
def export_jobs(
    ids: Annotated[list[str] | None, typer.Argument()] = None, home: Home = None
) -> None:
    """Print jobs as JSON (without secrets) to move them to another queue."""
    rayo = open_platform(home)
    try:
        output.print_json(rayo.queue.export(ids or None))
    finally:
        rayo.close()


@queue_app.command("import")
def import_jobs(
    file: Annotated[Path, typer.Argument(help="A file written by 'queue export' (- is stdin).")],
    home: Home = None,
) -> None:
    """Add the jobs in an exported file."""
    import json
    import sys

    try:
        text = sys.stdin.read() if str(file) == "-" else file.read_text(encoding="utf-8")
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError("expected a list")
    except (OSError, ValueError) as exc:
        usage_error(ConfigurationError(f"{file} is not an exported queue: {exc}"))
    rayo = open_platform(home)
    try:
        try:
            records = rayo.queue.import_jobs(items)
        except (RayoHXError, KeyError, TypeError) as exc:
            usage_error(exc if isinstance(exc, RayoHXError) else ConfigurationError(str(exc)))
    finally:
        rayo.close()
    output.message(f"Added {len(records)} job(s).")


def event_line(event: PlatformEvent, as_json: bool) -> str | None:
    import json

    if as_json:
        return json.dumps(event.to_dict(), sort_keys=True)
    if event.type in {"queue.job_state_changed", "queue.job_retry_scheduled"}:
        detail = event.payload.get("new") or f"retry in {event.payload.get('delay_seconds')}s"
        return f"{event.job_id}  {detail}  {event.payload.get('error') or ''}".rstrip()
    if event.type in {"queue.completed", "queue.job_recovered"}:
        return f"{event.type}  {event.job_id or ''}".rstrip()
    return None


@queue_app.command("run")
def run(
    max_active: Annotated[
        int | None, typer.Option("--max-active", min=1, max=16, help="Jobs at the same time.")
    ] = None,
    until_empty: Annotated[
        bool, typer.Option("--until-empty", help="Stop when nothing is left to run.")
    ] = False,
    events: Annotated[
        bool, typer.Option("--events", help="Print platform events as JSON lines on stdout.")
    ] = False,
    home: Home = None,
) -> None:
    """Run the queue in this terminal until you press Ctrl-C (or, with --until-empty, it is empty).

    Only one process runs a queue at a time. Press Ctrl-C once to stop cleanly: running jobs go
    back to the queue and continue the next time. Exit status is 1 if a job failed.
    """
    rayo = open_platform(home)
    if max_active is not None:
        rayo.queue.max_active = max_active

    def show_event(event: PlatformEvent) -> None:
        line = event_line(event, events)
        if line:
            output.data(line)

    rayo.events.subscribe(show_event)
    stop = {"requested": False}

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop["requested"] = True

    previous = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    try:
        try:
            recovered = rayo.queue.start()
        except RunnerLockedError as exc:
            output.error_from(exc)
            raise typer.Exit(EXIT_FAILED) from exc
        if recovered:
            output.message(f"Recovered {len(recovered)} interrupted job(s).")
        output.message("Running the queue. Press Ctrl-C to stop.")
        finished = wait_until(rayo, stop, until_empty)
        output.message("Stopping..." if not finished else "The queue is empty.")
        rayo.queue.stop()
        failed = rayo.queue.list(states=[JobState.FAILED])
    finally:
        signal.signal(signal.SIGINT, previous)
        signal.signal(signal.SIGTERM, previous_term)
        rayo.close()
    if failed and until_empty:
        raise typer.Exit(EXIT_FAILED)


def wait_until(rayo: Rayo, stop: dict[str, bool], until_empty: bool) -> bool:
    """Wait for a stop request, or (with ``until_empty``) for the queue to empty."""
    while not stop["requested"]:
        if rayo.queue.wait_idle(0.2) and until_empty:
            return True
        if not until_empty:
            time.sleep(0.1)
    return False


__all__ = ["EXIT_USAGE", "queue_app"]
