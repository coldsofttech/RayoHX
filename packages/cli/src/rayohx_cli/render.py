"""Showing what ``info`` found, as tables."""

from typing import Any

from rich.table import Table
from rich.text import Text

from rayohx_cli import format as fmt
from rayohx_cli import output


def show(data: dict[str, Any]) -> None:
    """Print a described playlist (see ``rayohx.playlist_to_dict``) to stdout."""
    if data["type"] == "master":
        _master(data)
    else:
        _media(data)


def _yes(value: object) -> str:
    return "yes" if value else ""


def _master(data: dict[str, Any]) -> None:
    output.data(f"Master playlist: {data['url']}")
    selection = data.get("selection") or {}
    variants = data["variants"]
    # Columns nobody fills in only take up room, so they are left out.
    optional = {
        "Average": any(v["average_bandwidth"] for v in variants),
        "FPS": any(v["frame_rate"] for v in variants),
        "Audio": any(v["audio_group"] for v in variants),
        "Subtitles": any(v["subtitle_group"] for v in variants),
    }
    table = Table(title="Streams", title_justify="left")
    table.add_column("", no_wrap=True)
    table.add_column("#", no_wrap=True)
    table.add_column("Size", no_wrap=True)
    table.add_column("Bit rate", no_wrap=True)
    for name, used in optional.items():
        if used:
            table.add_column(name, no_wrap=True)
    table.add_column("Codecs", overflow="fold")
    for variant in variants:
        row = [
            "*" if selection.get("variant") == variant["index"] else "",
            str(variant["index"]),
            variant["resolution"] or "audio only",
            fmt.bitrate(variant["bandwidth"]),
        ]
        values = {
            "Average": fmt.bitrate(variant["average_bandwidth"])
            if variant["average_bandwidth"]
            else "",
            "FPS": f"{variant['frame_rate']:g}" if variant["frame_rate"] else "",
            "Audio": variant["audio_group"] or "",
            "Subtitles": variant["subtitle_group"] or "",
        }
        row += [values[name] for name, used in optional.items() if used]
        row.append(", ".join(variant["codecs"]))
        table.add_row(*row)
    output.console.print(table)
    _tracks(data["audio_tracks"], "Audio tracks", with_channels=True)
    _tracks(data["subtitle_tracks"], "Subtitle tracks", with_channels=False)
    if selection:
        _selection(data, selection)


def _tracks(tracks: list[dict[str, Any]], title: str, *, with_channels: bool) -> None:
    if not tracks:
        return
    show_channels = with_channels and any(track.get("channels") for track in tracks)
    show_forced = any(track.get("forced") for track in tracks)
    table = Table(title=title, title_justify="left")
    columns = ["Group", "Name", "Language", "Default"]
    if show_forced:
        columns.append("Forced")
    if show_channels:
        columns.append("Channels")
    columns.append("Separate")
    for column in columns:
        table.add_column(column, no_wrap=column != "Name")
    for track in tracks:
        row = [track["group"], track["name"], track.get("language") or "", _yes(track["default"])]
        if show_forced:
            row.append(_yes(track.get("forced")))
        if show_channels:
            row.append(track.get("channels") or "")
        row.append(_yes(track["separate"]))
        table.add_row(*row)
    output.console.print(table)


def _selection(data: dict[str, Any], selection: dict[str, Any]) -> None:
    variant = data["variants"][selection["variant"] - 1]
    size = variant["resolution"] or "audio only"
    lines = [
        "With these settings a download would take:",
        f"  stream {selection['variant']}: {size}, {fmt.bitrate(variant['bandwidth'])}",
        "  audio: " + (", ".join(selection["audio"]) or "the audio in the stream"),
        "  subtitles: " + (", ".join(selection["subtitles"]) or "none"),
    ]
    lines += [f"  note: {note}" for note in selection["notes"]]
    for line in lines:
        output.console.print(Text(line), soft_wrap=True)


def _media(data: dict[str, Any]) -> None:
    output.data(f"Media playlist: {data['url']}")
    table = Table(show_header=False)
    rows = [
        ("Segments", str(data["segments"])),
        ("Duration", fmt.duration(data["duration"])),
        ("Format", data["container"]),
        ("Complete", "yes" if data["complete"] else "no (a live stream)"),
        ("Encryption", ", ".join(data["encryption"]) or "none"),
        ("Byte ranges", _yes(data["byte_ranges"]) or "no"),
        ("Discontinuities", str(data["discontinuities"])),
    ]
    for key, value in rows:
        table.add_row(key, value)
    output.console.print(table)


def show_media(media: dict[str, Any], compatibility: list[dict[str, str]]) -> None:
    """Print the detail ``inspect_media`` found, and anything to know before saving."""
    output.data("")
    output.data("Details")
    rows: list[tuple[str, str]] = []
    if media.get("title"):
        rows.append(("Title", str(media["title"])))
    if media.get("duration") is not None:
        rows.append(("Duration", fmt.duration(media["duration"])))
    elif media.get("live"):
        rows.append(("Duration", "live stream"))
    rows.append(("Segments", f"{media['segment_count']} ({media.get('container') or 'unknown'})"))
    if media.get("encryption"):
        rows.append(("Encryption", str(media["encryption"])))
    size = media["size"]
    if size["bytes"] is not None:
        shown = fmt.size(size["bytes"])
        rows.append(("Size", f"{shown} ({size['kind']}: {size['basis']})"))
    else:
        rows.append(("Size", f"unavailable ({size['basis']})"))
    video = media.get("video")
    if video:
        parts = [video.get("label") or video.get("codec") or "video"]
        if video.get("width"):
            parts.append(f"{video['width']}x{video['height']}")
        if video.get("frame_rate"):
            parts.append(f"{video['frame_rate']:g} fps")
        if video.get("bit_rate"):
            parts.append(fmt.bitrate(video["bit_rate"]))
        if video.get("pixel_format"):
            parts.append(video["pixel_format"])
        rows.append(("Video", ", ".join(parts)))
    for key, value in rows:
        output.console.print(Text(f"  {key:10} {value}"), soft_wrap=True)
    if media["audio"]:
        table = Table(title="Audio", title_justify="left")
        for column in ("", "Name", "Language", "Codec", "Channels", "Rate", "Where"):
            table.add_column(column, no_wrap=True)
        for track in media["audio"]:
            table.add_row(
                "*" if track.get("selected") else "",
                track.get("name") or "",
                track.get("language") or "",
                track.get("label") or track.get("codec") or "",
                str(track.get("channels") or ""),
                f"{track['sample_rate']} Hz" if track.get("sample_rate") else "",
                "separate" if track.get("separate") else "in the video",
            )
        output.console.print(table)
    meta = media.get("metadata") or {}
    extras = []
    if meta.get("description"):
        extras.append(("Description", str(meta["description"])))
    if meta.get("chapters"):
        extras.append(("Chapters", ", ".join(c["title"] for c in meta["chapters"])))
    if meta.get("artwork_url"):
        extras.append(("Cover", "yes"))
    for key, value in extras:
        output.console.print(Text(f"  {key:10} {value}"), soft_wrap=True)
    for note in compatibility:
        style = {"error": "bold red", "warning": "yellow"}.get(note["level"], "dim")
        output.err_console.print(Text(f"{note['level']}: {note['message']}", style=style))
    for note_text in media.get("notes", []):
        output.err_console.print(Text(note_text, style="dim"))
