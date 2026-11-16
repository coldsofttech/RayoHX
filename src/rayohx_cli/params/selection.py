"""Choosing what to download."""

from typing import Annotated

import typer

from rayohx_cli.params.panels import SELECTION

Url = Annotated[
    str,
    typer.Argument(
        help="The address of the playlist (.m3u8). Quote it if it contains & or ?.",
        metavar="URL",
    ),
]

Quality = Annotated[
    str,
    typer.Option(
        "--quality",
        envvar="RAYOHX_QUALITY",
        help="best, worst, auto (up to 1080p), or a height such as 720p (the best at or below it).",
        rich_help_panel=SELECTION,
    ),
]
MaxResolution = Annotated[
    str | None,
    typer.Option(
        "--max-resolution",
        envvar="RAYOHX_MAX_RESOLUTION",
        help="Never pick a picture taller than this, for example 1080p.",
        rich_help_panel=SELECTION,
    ),
]
MaxBitrate = Annotated[
    str | None,
    typer.Option(
        "--max-bitrate",
        envvar="RAYOHX_MAX_BITRATE",
        help="Never pick a stream above this many bits per second, for example 4M.",
        rich_help_panel=SELECTION,
    ),
]
Audio = Annotated[
    list[str] | None,
    typer.Option(
        "--audio",
        "-a",
        help="Audio language to download (repeat for several), for example en.",
        rich_help_panel=SELECTION,
    ),
]
AudioName = Annotated[
    list[str] | None,
    typer.Option(
        "--audio-name",
        help="Download the audio track with this exact name (repeatable).",
        rich_help_panel=SELECTION,
    ),
]
Subtitles = Annotated[
    list[str] | None,
    typer.Option(
        "--subtitles",
        "-s",
        help="Subtitle language to save beside the video (repeat for several).",
        rich_help_panel=SELECTION,
    ),
]
SubtitleName = Annotated[
    list[str] | None,
    typer.Option(
        "--subtitle-name",
        help="Save the subtitle track with this exact name (repeatable).",
        rich_help_panel=SELECTION,
    ),
]
VideoOnly = Annotated[
    bool,
    typer.Option(
        "--video-only",
        envvar="RAYOHX_VIDEO_ONLY",
        help="Download only the video, leaving out separate audio and subtitle tracks.",
        rich_help_panel=SELECTION,
    ),
]
