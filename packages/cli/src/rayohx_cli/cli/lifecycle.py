"""How a download runs and ends: stopping on Ctrl-C, and reporting the result."""

import signal
from collections.abc import Generator
from contextlib import contextmanager
from types import FrameType

import typer
from rayohx import Downloader, DownloadResult, result_to_dict
from rayohx.errors import RayoHXError

from rayohx_cli import format as fmt
from rayohx_cli import output
from rayohx_cli.cli.common import EXIT_CANCELLED, EXIT_FAILED


@contextmanager
def graceful_interrupt(downloader: Downloader) -> Generator[None]:
    """The first Ctrl-C stops the download cleanly; a second one quits at once."""
    presses = 0

    def handler(signum: int, frame: FrameType | None) -> None:
        nonlocal presses
        presses += 1
        if presses == 1:
            downloader.cancel()
            output.message("Stopping... press Ctrl-C again to quit at once.")
        else:
            raise KeyboardInterrupt

    def toggle_pause(signum: int, frame: FrameType | None) -> None:
        if downloader.is_paused:
            downloader.resume()
            output.message("Resumed.")
        else:
            downloader.pause()
            output.message("Paused. Send the same signal again to continue.")

    try:
        previous = signal.signal(signal.SIGINT, handler)
    except ValueError:  # not the main thread: signals cannot be handled here
        yield
        return
    # SIGUSR1 pauses and continues where the system has it (not on Windows).
    pause_signal = getattr(signal, "SIGUSR1", None)
    previous_pause = signal.signal(pause_signal, toggle_pause) if pause_signal else None
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
        if pause_signal is not None and previous_pause is not None:
            signal.signal(pause_signal, previous_pause)


def finish(
    result: DownloadResult,
    downloader: Downloader,
    *,
    json_output: bool,
    documents: list[dict[str, object]] | None = None,
) -> None:
    """Report how the download ended and set the exit code.

    With ``documents`` (several downloads), the JSON result is added to it instead of printed,
    so the caller can print one array at the end.
    """
    if json_output and documents is not None:
        documents.append(result_to_dict(result))
    elif json_output:
        output.print_json(result_to_dict(result))
    if result.success and result.output is not None:
        if not json_output:
            output.data(str(result.output.path))
        output.message(
            f"Saved {result.output.path.name} ({fmt.size(result.output.size_bytes)}) "
            f"in {fmt.duration(result.elapsed_seconds)}",
            style="green",
        )
        return
    if result.cancelled:
        output.message("Cancelled.", style="yellow")
        raise typer.Exit(EXIT_CANCELLED)
    exc = downloader.exception
    if isinstance(exc, RayoHXError):
        output.error_from(exc)
    elif exc is not None:
        raise exc  # unexpected: reported once, by run()
    else:
        output.error(result.error or "The download failed.")
    raise typer.Exit(EXIT_FAILED)
