"""Deciding what file to write.

The rules exist to stop the old mistake of raw MPEG-TS bytes being saved under an ``.mp4`` name.
The file name must match what is inside. A request that would need remuxing (for example MPEG-TS
into MP4) is refused with an explanation rather than quietly mislabelled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from rayohx.enums import ContainerFormat, OutputFormat


@dataclass(frozen=True, slots=True)
class OutputPlan:
    """The file (or folder) to write and what goes in it."""

    path: Path
    format: OutputFormat
    container: ContainerFormat
    #: Whether the segments have to be re-wrapped into a new MP4 rather than just joined.
    mux: bool = False

    @property
    def is_directory(self) -> bool:
        """Whether the output is a folder of separate segment files."""
        from rayohx.enums import OutputFormat

        return self.format is OutputFormat.SEGMENTS


def plan_output(
    *,
    path: Path | None,
    requested: OutputFormat,
    container: ContainerFormat,
    url: str,
    directory: Path | None = None,
    allow_remux: bool = False,
    merge: bool = False,
) -> OutputPlan:
    """Choose the output path and format for a stream.

    Args:
        path: Where the user wants the output, or ``None`` to name it after the address.
        requested: The format asked for. ``AUTO`` follows the file name, else the stream.
        container: What the segments are.
        url: The address downloaded; used to name the file when ``path`` is ``None``.
        directory: Where an unnamed output goes. Defaults to the current folder.
        allow_remux: Whether MPEG-TS may be re-wrapped into MP4.
        merge: Whether separate audio tracks have to be joined in, which needs an MP4.

    Raises:
        OutputFormatError: If the stream cannot be written in that format without remuxing, or
            the file name does not match the format.
    """
    from pathlib import Path

    from rayohx._download._output._names import name_from_url
    from rayohx.enums import ContainerFormat, OutputFormat
    from rayohx.errors import OutputFormatError

    suffix_formats = {
        ".ts": OutputFormat.TS,
        ".m2ts": OutputFormat.TS,
        ".mts": OutputFormat.TS,
        ".mp4": OutputFormat.MP4,
        ".m4v": OutputFormat.MP4,
        ".m4a": OutputFormat.MP4,
    }
    natives = {
        ContainerFormat.MPEG_TS: (OutputFormat.TS, ".ts"),
        ContainerFormat.FMP4: (OutputFormat.MP4, ".mp4"),
    }

    if container is ContainerFormat.WEBVTT:
        raise OutputFormatError(
            "This playlist contains subtitles only, which cannot be saved on their own yet.",
            hint="Download the video stream instead.",
        )
    if container is ContainerFormat.UNKNOWN:
        raise OutputFormatError(
            "The format of the segments could not be recognised.",
            hint="Only MPEG-TS and fragmented MP4 streams are supported.",
        )
    native_format, native_suffix = natives[container]

    if requested is OutputFormat.SEGMENTS:
        folder = path if path is not None else (directory or Path.cwd()) / name_from_url(url)
        return OutputPlan(Path(folder), OutputFormat.SEGMENTS, container)

    suffix = path.suffix.lower() if path is not None else ""
    if path is not None and suffix and suffix not in suffix_formats:
        raise OutputFormatError(
            f"Files ending in {path.suffix!r} are not supported.",
            hint=f"Use {native_suffix} for this stream.",
        )
    from_name = suffix_formats.get(suffix)
    if requested is not OutputFormat.AUTO and from_name not in (None, requested):
        assert path is not None  # noqa: S101 - a suffix exists only when there is a path
        raise OutputFormatError(
            f"The file name ends in {path.suffix!r} but the format {requested.value!r} "
            "was asked for."
        )
    if merge:
        if requested not in (OutputFormat.AUTO, OutputFormat.MP4) or from_name is OutputFormat.TS:
            raise OutputFormatError(
                "Joining a separate audio track into the video needs an MP4 file.",
                hint="Save it as .mp4.",
            )
        chosen = OutputFormat.MP4
    else:
        chosen = requested if requested is not OutputFormat.AUTO else (from_name or native_format)

    mux = merge or (chosen is OutputFormat.MP4 and container is ContainerFormat.MPEG_TS)
    if chosen is OutputFormat.TS and container is not ContainerFormat.MPEG_TS:
        raise OutputFormatError(
            f"This stream is {_describe(container)} and cannot be saved as TS.",
            hint=f"Save it as {native_suffix} instead.",
        )
    if mux and not allow_remux:
        raise OutputFormatError(
            f"This stream is {_describe(container)} and cannot be saved as "
            f"{chosen.value.upper()} without remuxing, which is not available.",
            hint=f"Save it as {native_suffix} instead.",
        )
    suffix_for_chosen = ".mp4" if chosen is OutputFormat.MP4 else ".ts"
    if path is None:
        name = f"{name_from_url(url)}{suffix_for_chosen}"
        return OutputPlan((directory or Path.cwd()) / name, chosen, container, mux)
    if not suffix:
        path = path.with_name(path.name + suffix_for_chosen)
    return OutputPlan(path, chosen, container, mux)


def _describe(container: ContainerFormat) -> str:
    from rayohx.enums import ContainerFormat

    return "MPEG-TS" if container is ContainerFormat.MPEG_TS else "fragmented MP4"
