"""``rayohx daemon`` and ``rayohx migrate``: running the queue as a service, and upgrading."""

import logging
import signal
import sys
from types import FrameType
from typing import Annotated

import typer
from rayohx.platform.daemon import Daemon, configure_logging
from rayohx.platform.errors import RunnerLockedError

from rayohx_cli import output, params
from rayohx_cli.cli.common import EXIT_FAILED
from rayohx_cli.cli.queue import Home, open_platform
from rayohx_cli.cli.root import app


@app.command("daemon")
def daemon(
    host: Annotated[
        str, typer.Option(help="Address for the health endpoint (loopback unless you change it).")
    ] = "127.0.0.1",
    port: Annotated[
        int, typer.Option(min=0, max=65535, help="Health endpoint port; 0 picks a free one.")
    ] = 8765,
    no_health: Annotated[
        bool, typer.Option("--no-health", help="Do not open the endpoint.")
    ] = False,
    metrics: Annotated[
        bool, typer.Option("--metrics", help="Also serve /metrics (Prometheus text).")
    ] = False,
    max_active: Annotated[
        int | None, typer.Option("--max-active", min=1, max=16, help="Jobs at the same time.")
    ] = None,
    home: Home = None,
) -> None:
    """Run the queue in the foreground as a service, until SIGTERM or Ctrl-C.

    Writes one JSON log line per event to stderr and answers /health on loopback. Stopping puts
    running jobs back in the queue; the next start continues them. Exit status 1 if the queue
    could not start (for example because another process runs it).
    """
    configure_logging(sys.stderr)
    rayo = open_platform(home)
    service = Daemon(
        rayo, host=host, port=None if no_health else port, metrics=metrics, max_active=max_active
    )

    def stop(_signum: int, _frame: FrameType | None) -> None:
        service.request_stop()

    previous = [signal.signal(signal.SIGINT, stop), signal.signal(signal.SIGTERM, stop)]
    try:
        service.run()
    except RunnerLockedError as exc:
        output.error_from(exc)
        raise typer.Exit(EXIT_FAILED) from exc
    finally:
        signal.signal(signal.SIGINT, previous[0])
        signal.signal(signal.SIGTERM, previous[1])
        rayo.close()
    logging.getLogger("rayohx.daemon").info("bye")


@app.command("migrate")
def migrate(
    json_output: params.JsonOutput = False,
    home: Home = None,
) -> None:
    """Check the database after an upgrade from version 1 and show what was done.

    The database upgrades by itself when RayoHX starts, after a backup; this command shows the
    result. The API's saved default options are imported as a profile named Default the first
    time the API starts; the old file is never deleted.
    """
    from rayohx.platform.migrate import migrate as run_migration

    rayo = open_platform(home)
    try:
        report = run_migration(rayo)
    finally:
        rayo.close()
    if json_output:
        output.print_json(report.to_dict())
        return
    state = "up to date" if report.up_to_date else "needs attention"
    output.console.print(f"Database: version {report.schema_version} ({state})")
    if report.backup:
        output.console.print(f"A backup was made before upgrading: {report.backup}")
    if report.recovered_database:
        output.error(f"The database was damaged and moved to {report.recovered_database}.")
    for note in report.notes:
        output.console.print(f"[dim]{note}[/dim]")
