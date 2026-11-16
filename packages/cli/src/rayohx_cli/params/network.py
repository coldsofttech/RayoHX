"""Network options."""

from pathlib import Path
from typing import Annotated

import typer

from rayohx_cli.params.panels import NETWORK

Header = Annotated[
    list[str] | None,
    typer.Option(
        "--header",
        "-H",
        help="Send a header, as 'Name: value' (repeatable). @file reads them from a file.",
        rich_help_panel=NETWORK,
    ),
]
Cookie = Annotated[
    list[str] | None,
    typer.Option(
        "--cookie",
        help="Send a cookie, as name=value (repeatable). @file reads them from a file.",
        rich_help_panel=NETWORK,
    ),
]
UserAgent = Annotated[
    str | None,
    typer.Option(
        "--user-agent",
        envvar="RAYOHX_USER_AGENT",
        help="The User-Agent to send.",
        rich_help_panel=NETWORK,
    ),
]
Referer = Annotated[
    str | None,
    typer.Option(
        "--referer", envvar="RAYOHX_REFERER", help="The Referer to send.", rich_help_panel=NETWORK
    ),
]
Origin = Annotated[
    str | None,
    typer.Option(
        "--origin", envvar="RAYOHX_ORIGIN", help="The Origin to send.", rich_help_panel=NETWORK
    ),
]
Proxy = Annotated[
    str | None,
    typer.Option(
        "--proxy",
        envvar="RAYOHX_PROXY",
        help="An http:// or https:// proxy, for example http://user:pass@host:3128. "
        "Prefer the environment variable, since command lines can be seen by other users.",
        rich_help_panel=NETWORK,
    ),
]
Insecure = Annotated[
    bool,
    typer.Option(
        "--insecure",
        envvar="RAYOHX_INSECURE",
        help="Do not check TLS certificates. Only for servers you trust.",
        rich_help_panel=NETWORK,
    ),
]
CaBundle = Annotated[
    Path | None,
    typer.Option(
        "--ca-bundle",
        envvar="RAYOHX_CA_BUNDLE",
        help="A file of trusted certificate authorities (PEM), instead of the system's.",
        rich_help_panel=NETWORK,
    ),
]
ConnectTimeout = Annotated[
    float | None,
    typer.Option(
        "--connect-timeout",
        envvar="RAYOHX_CONNECT_TIMEOUT",
        help="Seconds to wait to connect.",
        rich_help_panel=NETWORK,
    ),
]
ReadTimeout = Annotated[
    float | None,
    typer.Option(
        "--read-timeout",
        envvar="RAYOHX_READ_TIMEOUT",
        help="Seconds to wait for data.",
        rich_help_panel=NETWORK,
    ),
]
Timeout = Annotated[
    float | None,
    typer.Option(
        "--timeout",
        envvar="RAYOHX_TIMEOUT",
        help="Most seconds one request may take, retries included.",
        rich_help_panel=NETWORK,
    ),
]
Retries = Annotated[
    int | None,
    typer.Option(
        "--retries",
        envvar="RAYOHX_RETRIES",
        min=0,
        help="Extra attempts after a failure.",
        rich_help_panel=NETWORK,
    ),
]
RateLimit = Annotated[
    str | None,
    typer.Option(
        "--rate-limit",
        envvar="RAYOHX_RATE_LIMIT",
        help="Most bytes per second to download in total, for example 2M.",
        rich_help_panel=NETWORK,
    ),
]
CredentialHost = Annotated[
    list[str] | None,
    typer.Option(
        "--credential-host",
        help="Also send headers like Authorization and your cookies to this host (repeatable). "
        "By default they go only to the host of the URL.",
        rich_help_panel=NETWORK,
    ),
]
