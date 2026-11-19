"""The ``diagnostics`` commands: why something failed, and a report that is safe to share."""

from pathlib import Path
from typing import Annotated, Any

import typer

from rayohx_cli import output, params
from rayohx_cli.cli.common import EXIT_FAILED
from rayohx_cli.cli.profile import run_store
from rayohx_cli.cli.queue import Home
from rayohx_cli.cli.root import app

diagnostics_app = typer.Typer(
    name="diagnostics",
    help="Find out why a download failed, check the network or a stream, and make a safe report.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)
app.add_typer(diagnostics_app)

JobArg = Annotated[str | None, typer.Option("--job", "-j", help="A job id from the queue.")]


def _explanation(data: dict[str, Any]) -> None:
    output.console.print(f"[bold]{data['title']}[/bold]  ({data['code']}, {data['category']})")
    output.console.print(data["what_happened"])
    if data.get("likely_cause"):
        output.console.print(f"Why: {data['likely_cause']}")
    if data.get("what_was_tried"):
        output.console.print(f"Tried: {data['what_was_tried']}")
    for step in data.get("next_steps", []):
        output.console.print(f"  - {step}")


@diagnostics_app.command("explain")
def explain(
    target: Annotated[str, typer.Argument(help="A job id, or an error code such as HTTP_403.")],
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Explain a failed job, or an error code, and what to do about it."""

    def act(rayo: Any) -> dict[str, Any]:
        detail: dict[str, Any] | None = rayo.diagnostics.explain_job(target)
        if detail is not None:
            return detail
        return {"job": None, "explanation": rayo.diagnostics.explain(target).to_dict()}

    data = run_store(home, act)
    if json_output:
        output.print_json(data)
        return
    if data.get("job"):
        job = data["job"]
        output.console.print(f"Job {job['id']}: {job['state']}, {job['attempts']} run(s)")
    if data.get("explanation"):
        _explanation(data["explanation"])
    else:
        output.console.print("Nothing went wrong with this job.")


@diagnostics_app.command("network")
def network(
    url: Annotated[str, typer.Argument(help="The address to check.")],
    job: JobArg = None,
    timeout: Annotated[float, typer.Option(help="Seconds to wait for each step.")] = 10.0,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Check each step of reaching a server: name lookup, connection, TLS, response."""
    report = run_store(
        home, lambda rayo: rayo.diagnostics.network(url, job_id=job, timeout=timeout)
    )
    if json_output:
        output.print_json(report.to_dict())
    else:
        for step in report.steps:
            mark = "--  " if step.ok is None else ("ok  " if step.ok else "FAIL")
            output.console.print(f"{mark} {step.name}  {step.detail}")
        for note in report.notes:
            output.console.print(f"[dim]{note}[/dim]")
        if report.code:
            _explanation(
                run_store(home, lambda rayo: rayo.diagnostics.explain(report.code).to_dict())
            )
    if not report.ok:
        raise typer.Exit(EXIT_FAILED)


@diagnostics_app.command("stream")
def stream(
    url: Annotated[str, typer.Argument(help="A playlist address.")],
    job: JobArg = None,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Describe a stream and point out what is unusual about it."""
    report = run_store(home, lambda rayo: rayo.diagnostics.stream(url, job_id=job))
    if json_output:
        output.print_json(report.to_dict())
        return
    if not report.findings:
        output.console.print("Nothing unusual found.")
    for finding in report.findings:
        output.console.print(f"{finding.level}: {finding.title}  {finding.detail}")


@diagnostics_app.command("report")
def report(
    job: JobArg = None,
    url: Annotated[str | None, typer.Option(help="Also check this address.")] = None,
    network_check: Annotated[
        bool, typer.Option("--network", help="Include a network check.")
    ] = False,
    stream_check: Annotated[bool, typer.Option("--stream", help="Include a stream check.")] = False,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Also copy it here.")] = None,
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Make a report with no passwords, tokens or personal paths in it, safe to share."""
    result = run_store(
        home,
        lambda rayo: rayo.diagnostics.report(
            job, url=url, include_network=network_check, include_stream=stream_check
        ),
    )
    if out is not None:
        try:
            out.write_text(result.text + "\n", encoding="utf-8")
        except OSError as exc:
            output.error(f"Could not write {out}: {exc.strerror}")
            raise typer.Exit(EXIT_FAILED) from exc
    if json_output:
        output.data(result.text)
        return
    output.console.print(f"Report saved to {result.path}")
    problems = [f for f in result.data.get("findings", []) if f["level"] != "info"]
    for finding in problems:
        output.console.print(f"{finding['level']}: {finding['title']}")


@diagnostics_app.command("reports")
def reports(json_output: params.JsonOutput = False, home: Home = None) -> None:
    """List the reports that were saved."""
    found = run_store(home, lambda rayo: rayo.diagnostics.reports())
    if json_output:
        output.print_json(found)
        return
    for item in found:
        output.console.print(f"{item['id']}  {item['name']}  {item['summary']}")
    if not found:
        output.console.print("No reports saved yet.")
