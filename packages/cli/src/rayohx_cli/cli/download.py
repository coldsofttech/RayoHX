"""The ``download`` command: save a stream to a file."""

import typer
from rayohx import Downloader, OutputFormat, RemuxBackend, StorageStrategy
from rayohx.errors import ConfigurationError

from rayohx_cli import output, params
from rayohx_cli.cli.common import make_config, usage_error
from rayohx_cli.cli.lifecycle import finish, graceful_interrupt
from rayohx_cli.cli.root import app
from rayohx_cli.progress import MODES, make_reporter


@app.command()
def download(
    url: params.Url,
    output_path: params.OutputPath = None,
    quality: params.Quality = "best",
    max_resolution: params.MaxResolution = None,
    max_bitrate: params.MaxBitrate = None,
    audio: params.Audio = None,
    audio_name: params.AudioName = None,
    subtitles: params.Subtitles = None,
    subtitle_name: params.SubtitleName = None,
    video_only: params.VideoOnly = False,
    format_: params.Format = OutputFormat.AUTO,
    overwrite: params.Overwrite = False,
    validate: params.Validate = True,
    remux_backend: params.RemuxBackendOption = RemuxBackend.AUTO,
    ffmpeg: params.Ffmpeg = None,
    header: params.Header = None,
    cookie: params.Cookie = None,
    user_agent: params.UserAgent = None,
    referer: params.Referer = None,
    origin: params.Origin = None,
    proxy: params.Proxy = None,
    insecure: params.Insecure = False,
    ca_bundle: params.CaBundle = None,
    connect_timeout: params.ConnectTimeout = None,
    read_timeout: params.ReadTimeout = None,
    timeout: params.Timeout = None,
    retries: params.Retries = None,
    rate_limit: params.RateLimit = None,
    credential_host: params.CredentialHost = None,
    concurrency: params.Concurrency = None,
    resume: params.Resume = True,
    storage: params.Storage = StorageStrategy.AUTO,
    workspace: params.Workspace = None,
    buffer_size: params.BufferSize = None,
    max_temp_size: params.MaxTempSize = None,
    json_output: params.JsonOutput = False,
    progress: params.ProgressMode = "auto",
) -> None:
    """Download a stream to a file.

    The path of the saved file is printed on stdout. Interrupted downloads continue where they
    stopped when you run the same command again. Press Ctrl-C once to stop cleanly.
    """
    if progress not in MODES:
        raise typer.BadParameter(f"must be one of {', '.join(MODES)}.", param_hint="--progress")
    config = make_config(
        quality=quality,
        max_resolution=max_resolution,
        max_bitrate=max_bitrate,
        audio=audio or [],
        audio_name=audio_name or [],
        subtitles=subtitles or [],
        subtitle_name=subtitle_name or [],
        video_only=video_only,
        format=format_,
        overwrite=overwrite,
        validate=validate,
        remux_backend=remux_backend,
        ffmpeg=ffmpeg,
        header=header or [],
        cookie=cookie or [],
        user_agent=user_agent,
        referer=referer,
        origin=origin,
        proxy=proxy,
        insecure=insecure,
        ca_bundle=ca_bundle,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        timeout=timeout,
        retries=retries,
        rate_limit=rate_limit,
        credential_host=credential_host or [],
        concurrency=concurrency,
        resume=resume,
        storage=storage,
        workspace=workspace,
        buffer_size=buffer_size,
        max_temp_size=max_temp_size,
    )
    try:
        downloader = Downloader(url, output=output_path, config=config)
    except ConfigurationError as exc:
        usage_error(exc)
    reporter = make_reporter(
        progress,
        output.err_console,
        quiet=output.settings.quiet,
        json_output=json_output,
        verbose=output.settings.verbose,
    )
    downloader.events.subscribe(reporter)
    reporter.start()
    try:
        with graceful_interrupt(downloader):
            result = downloader.run()
    finally:
        reporter.close()
    finish(result, downloader, json_output=json_output)
