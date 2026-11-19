"""Saying what went wrong in plain words, and what to do about it.

Every error has a stable code (``HTTP_403``, ``NETWORK_TIMEOUT``, ``STORAGE_LOW`` ...). This module
turns a code into four things a person can use: what happened, the likely cause, what RayoHX
already tried, and what to do next. It works from the code, never from the message text, which
may change.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any

from rayohx import errors as engine_errors
from rayohx.enums import ErrorCategory
from rayohx.errors import RayoHXError

_HTTP = re.compile(r"^(HTTP|AUTH)_(\d{3})$")


def _known_codes() -> dict[str, ErrorCategory]:
    codes: dict[str, ErrorCategory] = {}
    for _, cls in inspect.getmembers(engine_errors, inspect.isclass):
        if issubclass(cls, RayoHXError):
            codes[cls.error_code] = cls.category
    codes.update(
        {
            "INTERNAL": ErrorCategory.INTERNAL,
            "UNEXPECTED": ErrorCategory.INTERNAL,
            "PERSISTENCE_ERROR": ErrorCategory.INTERNAL,
            "QUEUE_ERROR": ErrorCategory.INTERNAL,
            # Found by the network probe rather than raised by a download.
            "DNS_FAILED": ErrorCategory.NETWORK,
            "CONNECT_FAILED": ErrorCategory.NETWORK,
            "CONNECT_TIMEOUT": ErrorCategory.NETWORK,
            "NOT_A_PLAYLIST": ErrorCategory.PLAYLIST,
        }
    )
    return codes


CODES = _known_codes()


def category_of(code: str | None) -> ErrorCategory:
    """The category an error code belongs to."""
    if not code:
        return ErrorCategory.INTERNAL
    match = _HTTP.match(code)
    if match:
        return ErrorCategory.AUTHENTICATION if match[1] == "AUTH" else ErrorCategory.HTTP
    return CODES.get(code, ErrorCategory.INTERNAL)


@dataclass(frozen=True, slots=True, kw_only=True)
class Explanation:
    """A failure, explained."""

    code: str
    category: ErrorCategory
    title: str
    what: str
    why: str
    next_steps: tuple[str, ...]
    #: What RayoHX did before giving up, if known.
    tried: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value,
            "title": self.title,
            "what_happened": self.what,
            "likely_cause": self.why,
            "what_was_tried": self.tried,
            "next_steps": list(self.next_steps),
        }

    def text(self) -> str:
        """The explanation as a few lines for a terminal."""
        lines = [self.title, f"  What happened: {self.what}", f"  Likely cause: {self.why}"]
        if self.tried:
            lines.append(f"  What was tried: {self.tried}")
        lines += ["  What to do:", *(f"    - {step}" for step in self.next_steps)]
        return "\n".join(lines)


# code -> (title, what happened, likely cause, next steps)
_TABLE: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "CONFIGURATION_INVALID": (
        "A setting is not valid",
        "The download was refused before it started because of a setting.",
        "An option has a value that cannot work, or two options contradict each other.",
        (
            "Read the message for which setting it is.",
            "Check it with: rayohx profile validate NAME.",
        ),
    ),
    "PLAYLIST_INVALID": (
        "The address did not return an HLS playlist",
        "What came back is not a playlist (it does not start with #EXTM3U).",
        "The link may be a web page, an error page or a sign-in page, or it has expired.",
        (
            "Open the address in a browser and look at what it shows.",
            "Copy the .m3u8 address again from the page that plays the video.",
            "If a sign-in is needed, pass the cookies or headers the browser sends.",
        ),
    ),
    "PLAYLIST_UNSUPPORTED": (
        "The playlist uses something that is not supported",
        "The playlist is valid but uses a feature this tool does not handle.",
        "Protected (DRM) streams and a few unusual playlist features are refused.",
        (
            "Streams protected by DRM cannot be downloaded.",
            "Try a different stream of the same video.",
        ),
    ),
    "PLAYLIST_NOT_FOUND": (
        "The playlist does not exist",
        "The server answered that the playlist address is not there.",
        "The link has expired or was copied wrongly.",
        ("Copy the address again from the page that plays the video.",),
    ),
    "RESPONSE_INVALID": (
        "The server answered with something unexpected",
        "The server replied, but not with media (a web page, nothing, or too little).",
        "A sign-in or error page is being served in place of the video, or a range request was ignored.",
        (
            "Check the Referer, Origin and cookies.",
            "Try again later in case the server is struggling.",
        ),
    ),
    "NETWORK_CONNECTION": (
        "The server could not be reached",
        "The connection could not be made or broke during the download.",
        "The network dropped, a proxy or firewall is in the way, or the server refused many connections.",
        (
            "Run: rayohx diagnostics network ADDRESS to see where it fails.",
            "Lower the number of segments fetched at once (--concurrency).",
            "Check the proxy settings if you use one.",
        ),
    ),
    "NETWORK_TIMEOUT": (
        "The server took too long",
        "A request did not finish within its time limit.",
        "A slow or overloaded server, a poor connection, or timeouts that are too short for it.",
        (
            "Raise --connect-timeout and --read-timeout.",
            "Lower --concurrency so each request gets more bandwidth.",
            "Try again later.",
        ),
    ),
    "TLS_FAILED": (
        "The secure connection could not be trusted",
        "The server's certificate was refused.",
        "The certificate is expired, self-signed, for another name, or your system does not know its issuer.",
        (
            "If you trust the server, give its certificate authority with --ca-bundle.",
            "Check the computer's date and time.",
            "Use --insecure only for a server you trust completely: it turns off the check.",
        ),
    ),
    "SEGMENT_FAILED": (
        "A piece of the video could not be fetched",
        "One segment kept failing after the retries.",
        "The server is unstable or the link's signature expired part way through.",
        (
            "Run the download again: segments already saved are not fetched again.",
            "If it fails at the same place each time, the link has probably expired: copy it again.",
        ),
    ),
    "DOWNLOAD_FAILED": (
        "The download failed",
        "The download stopped with an error.",
        "See the message for the cause.",
        ("Run: rayohx diagnostics report JOB to collect the details.",),
    ),
    "DECRYPTION_FAILED": (
        "A segment could not be decrypted",
        "The data did not decrypt into video.",
        "The key is wrong, or the key server refused the request and sent something else.",
        (
            "The key request needs the same cookies and headers as the video: pass them.",
            "Copy the link again; keys can expire like links.",
        ),
    ),
    "WORKSPACE_LOCKED": (
        "Another download is using the same working folder",
        "The working folder for this download is held by a running download.",
        "The same stream is already being downloaded, here or from another window.",
        ("Wait for it to finish, or run: rayohx queue list to see it.",),
    ),
    "STORAGE_LOW": (
        "There is not enough free disk space",
        "The disk does not have room for the download.",
        "The disk is nearly full, or other downloads are using the space.",
        (
            "Free some space, or choose another folder with --directory.",
            "Run: rayohx storage show to see what uses the space, and rayohx storage clean to remove leftovers.",
            "A storage strategy that keeps less working data may help: --storage streaming.",
            "Then retry: rayohx queue retry JOB.",
        ),
    ),
    "OUTPUT_EXISTS": (
        "The output file already exists",
        "A file with that name is already there and overwriting is off.",
        "The same download was made before, or another file has the name.",
        ("Choose another name, or allow overwriting with --overwrite.",),
    ),
    "OUTPUT_FORMAT": (
        "The stream cannot be saved in that format",
        "The chosen output format does not suit this stream.",
        "The format needs a different container than the stream uses, or FFmpeg.",
        (
            "Run: rayohx info ADDRESS --media --format FORMAT to see what it needs.",
            "Try --format auto.",
        ),
    ),
    "CODEC_UNSUPPORTED": (
        "A codec is not supported by the built-in remuxer",
        "The stream uses a codec that cannot be copied into an MP4 by RayoHX itself.",
        "FFmpeg is needed for streams like this and was not available.",
        (
            "Install FFmpeg, or set its path with --ffmpeg.",
            "Save as .ts instead, which needs no conversion.",
        ),
    ),
    "FINALIZATION_FAILED": (
        "The finished file could not be put together",
        "Joining or checking the downloaded data failed at the end.",
        "Some segments were damaged, or FFmpeg failed on the data.",
        ("Run the download again.", "Use --verify strong to find out which check fails."),
    ),
    "VERIFICATION_FAILED": (
        "The finished file did not pass verification",
        "The download completed but the file failed its checks.",
        "The data is damaged or incomplete, or it differs from the checksum you expected.",
        (
            "Look at the report: rayohx queue verification JOB.",
            "The file was kept as NAME.invalid if you want to inspect it.",
            "Retry the download; if a checksum was expected, check that it is the right one.",
        ),
    ),
    "CANCELLED": (
        "The download was cancelled",
        "It was stopped on request.",
        "A person or a program cancelled it.",
        ("Run it again to continue; saved work is kept.",),
    ),
    "INTERNAL": (
        "An unexpected error",
        "RayoHX hit a problem it did not expect.",
        "This is probably a bug.",
        ("Run: rayohx diagnostics report JOB and attach the file to a bug report.",),
    ),
    "DNS_FAILED": (
        "The server's name could not be found",
        "The name of the server could not be turned into an address.",
        "The address is misspelled, the DNS is not reachable, or the link is for a private network.",
        ("Check the spelling of the address.", "Try opening it in a browser on the same computer."),
    ),
    "CONNECT_FAILED": (
        "The connection was refused",
        "The server's address was found but it would not accept a connection.",
        "The server is down, the port is wrong, or a firewall blocks it.",
        ("Try again later.", "Check any proxy or firewall settings."),
    ),
    "CONNECT_TIMEOUT": (
        "The connection timed out",
        "The server did not answer in time.",
        "The server or the network is not reachable from here.",
        ("Check the network, VPN or proxy.", "Try again later."),
    ),
    "NOT_A_PLAYLIST": (
        "The address answered, but not with a playlist",
        "The server replied successfully with something that is not an HLS playlist.",
        "A web page or sign-in page is served instead.",
        ("Open the address in a browser.", "Pass the cookies or headers the browser sends."),
    ),
}
_TABLE["UNEXPECTED"] = _TABLE["INTERNAL"]
_TABLE["STATE_INVALID"] = _TABLE["INTERNAL"]

_HTTP_STATUS: dict[int, tuple[str, str, str, tuple[str, ...]]] = {
    400: (
        "The server rejected the request",
        "The server did not understand the request.",
        "A header or cookie it dislikes, or a damaged address.",
        ("Copy the address again.", "Remove custom headers you do not need."),
    ),
    401: (
        "The server asks for a sign-in",
        "The server answered 401: credentials are needed.",
        "The stream needs an account, or the token or cookie has expired.",
        (
            "Pass the Authorization header or cookies the browser uses (--header, --cookie).",
            "Get a fresh link: tokens often last only a few minutes.",
        ),
    ),
    403: (
        "The server refused access",
        "The server answered 403: you may not have this.",
        "The link's signature expired, the server wants a Referer, Origin or User-Agent, "
        "or the video is restricted by region or account.",
        (
            "Copy the link again from the page, and download soon after.",
            "Pass the Referer and Origin of the page that plays it (--referer, --origin).",
            "Pass the browser's cookies if the page needs you to be signed in.",
        ),
    ),
    404: (
        "The address does not exist",
        "The server answered 404: nothing is there.",
        "The link has expired or was copied wrongly.",
        ("Copy the address again from the page that plays the video.",),
    ),
    407: (
        "The proxy asks for a sign-in",
        "The proxy answered 407.",
        "The proxy needs a user name and password.",
        ("Pass them with --proxy-username and --proxy-password.",),
    ),
    410: (
        "The video is gone",
        "The server answered 410: this was removed on purpose.",
        "The link has been withdrawn or has expired for good.",
        ("Get a new link.",),
    ),
    429: (
        "The server is limiting requests",
        "The server answered 429: too many requests.",
        "Too many segments are being fetched at once for this server.",
        (
            "Lower --concurrency, or set --rate-limit.",
            "Wait a while and retry; RayoHX already honors the server's Retry-After.",
        ),
    ),
}


def _http_entry(status: int) -> tuple[str, str, str, tuple[str, ...]]:
    if status in _HTTP_STATUS:
        return _HTTP_STATUS[status]
    if status >= 500:
        return (
            "The server had an error",
            f"The server answered {status}: a fault on its side.",
            "Usually temporary: the server is overloaded or being restarted.",
            ("Try again in a few minutes.", "Lower --concurrency to be gentler on it."),
        )
    return (
        "The server refused the request",
        f"The server answered {status}.",
        "The request was not accepted.",
        ("Check the address and the headers you pass.",),
    )


def describe_attempts(attempts: list[dict[str, Any]] | None) -> str:
    """What the queue did before giving up, from a job's run history."""
    if not attempts:
        return ""
    runs = len(attempts)
    failed = [a for a in attempts if a.get("outcome") == "failed"]
    codes = sorted({str(a["error_code"]) for a in failed if a.get("error_code")})
    began = attempts[0].get("started_at")
    ended = attempts[-1].get("finished_at") or attempts[-1].get("started_at")
    span = ""
    if isinstance(began, int | float) and isinstance(ended, int | float) and ended > began:
        span = f" over {ended - began:.0f} s"
    text = f"{runs} run{'s' if runs != 1 else ''}{span}"
    if codes:
        text += f"; {len(failed)} failed with {', '.join(codes)}"
    return text + "."


def explain(code: str | None, *, attempts: list[dict[str, Any]] | None = None) -> Explanation:
    """Explain an error code. An unknown code gets the explanation of its category."""
    shown = code or "INTERNAL"
    match = _HTTP.match(shown)
    if match:
        title, what, why, steps = _http_entry(int(match[2]))
    elif shown in _TABLE:
        title, what, why, steps = _TABLE[shown]
    else:
        title, what, why, steps = _TABLE["INTERNAL"]
        title = f"Failed with {shown}"
    return Explanation(
        code=shown,
        category=category_of(code),
        title=title,
        what=what,
        why=why,
        next_steps=steps,
        tried=describe_attempts(attempts),
    )
