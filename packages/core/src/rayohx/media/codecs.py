"""Reading the codec names a playlist gives (RFC 6381, such as ``avc1.640028``)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodecInfo:
    """What a codec string tells us, without looking at any media."""

    #: ``video``, ``audio`` or ``subtitle`` (``other`` if the family is not known).
    kind: str
    #: A short lower-case name: ``h264``, ``hevc``, ``av1``, ``aac`` ...
    codec: str
    #: A name to show: ``H.264 High@4.0``.
    label: str
    profile: str | None = None
    level: str | None = None


_H264_PROFILES = {
    66: "Baseline",
    77: "Main",
    88: "Extended",
    100: "High",
    110: "High 10",
    122: "High 4:2:2",
    244: "High 4:4:4 Predictive",
}
_HEVC_PROFILES = {1: "Main", 2: "Main 10", 3: "Main Still Picture", 4: "Range Extensions"}
_AV1_PROFILES = {0: "Main", 1: "High", 2: "Professional"}
_AAC_OBJECTS = {
    "1": "AAC Main",
    "2": "AAC-LC",
    "5": "HE-AAC",
    "29": "HE-AAC v2",
    "34": "MP3",
}
_SIMPLE = {
    "ac-3": ("audio", "ac3", "Dolby Digital"),
    "ec-3": ("audio", "eac3", "Dolby Digital Plus"),
    "ac-4": ("audio", "ac4", "Dolby AC-4"),
    "mp3": ("audio", "mp3", "MP3"),
    "opus": ("audio", "opus", "Opus"),
    "flac": ("audio", "flac", "FLAC"),
    "alac": ("audio", "alac", "Apple Lossless"),
    "vorbis": ("audio", "vorbis", "Vorbis"),
    "wvtt": ("subtitle", "webvtt", "WebVTT"),
    "stpp": ("subtitle", "ttml", "TTML"),
    "mp4v": ("video", "mpeg4", "MPEG-4 Visual"),
}


def _hex(text: str) -> int | None:
    try:
        return int(text, 16)
    except ValueError:
        return None


def _video_level(raw: int | None, divisor: int) -> str | None:
    return None if raw is None else f"{raw / divisor:.1f}"


def _label(name: str, profile: str | None, level: str | None) -> str:
    text = f"{name} {profile}" if profile else name
    return f"{text}@{level}" if level else text


def describe_codec(text: str) -> CodecInfo:
    """Describe one codec string. An unknown one comes back as its own name."""
    name, _, rest = text.strip().partition(".")
    family = name.lower()
    parts = rest.split(".") if rest else []
    if family in {"avc1", "avc2", "avc3", "avc4"}:
        digits = parts[0] if parts else ""
        profile_id = _hex(digits[0:2]) if len(digits) == 6 else None
        level = _video_level(_hex(digits[4:6]) if len(digits) == 6 else None, 10)
        profile = _H264_PROFILES.get(profile_id or 0)
        return CodecInfo("video", "h264", _label("H.264", profile, level), profile, level)
    if family in {"hvc1", "hev1"}:
        profile = _HEVC_PROFILES.get(int(parts[0]) if parts and parts[0].isdigit() else 0)
        level = None
        for part in parts:
            if part[:1] in {"L", "H"} and part[1:].isdigit():
                level = _video_level(int(part[1:]), 30)
        return CodecInfo("video", "hevc", _label("HEVC", profile, level), profile, level)
    if family in {"dvh1", "dvhe"}:
        profile = parts[0].lstrip("0") if parts else None
        return CodecInfo("video", "dolby-vision", f"Dolby Vision {profile or ''}".strip(), profile)
    if family == "vp09":
        level = None
        if len(parts) > 1 and parts[1].isdigit():
            level = f"{int(parts[1]) / 10:.1f}"
        profile = str(int(parts[0])) if parts and parts[0].isdigit() else None
        return CodecInfo("video", "vp9", _label("VP9", None, level), profile, level)
    if family == "av01":
        profile = _AV1_PROFILES.get(int(parts[0]) if parts and parts[0].isdigit() else -1)
        level = None
        if len(parts) > 1 and parts[1][:2].isdigit():
            index = int(parts[1][:2])
            level = f"{2 + index // 4}.{index % 4}"
        return CodecInfo("video", "av1", f"AV1 {profile or ''}".strip(), profile, level)
    if family == "mp4a":
        object_type = parts[0].lower() if parts else ""
        if object_type in {"69", "6b"}:
            return CodecInfo("audio", "mp3", "MP3")
        if object_type == "40" and len(parts) > 1:
            kind = _AAC_OBJECTS.get(parts[1])
            codec = "mp3" if parts[1] == "34" else "aac"
            return CodecInfo("audio", codec, kind or "AAC", kind)
        return CodecInfo("audio", "aac", "AAC")
    if family in _SIMPLE:
        kind, codec, label = _SIMPLE[family]
        return CodecInfo(kind, codec, label)
    return CodecInfo("other", family or text, text)
