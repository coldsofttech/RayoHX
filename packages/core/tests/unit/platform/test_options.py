import json
from pathlib import Path

import pytest

from rayohx.config import (
    DownloadConfig,
    MetadataConfig,
    NetworkConfig,
    OutputConfig,
    ProxyConfig,
    SelectionConfig,
    StorageConfig,
    VerifyConfig,
)
from rayohx.enums import OutputFormat, RemuxBackend, StorageStrategy
from rayohx.errors import ConfigurationError
from rayohx.platform.jobs import config_from_options, config_to_options


def rich_config(tmp_path: Path) -> DownloadConfig:
    return DownloadConfig(
        concurrency=7,
        resume=False,
        allow_file_keys=True,
        network=NetworkConfig(
            headers={"Authorization": "Bearer top-secret", "Referer": "https://site.test/"},
            cookies={"sid": "cookie-secret"},
            user_agent="Tester/1",
            connect_timeout=3,
            read_timeout=4,
            total_timeout=99,
            retries=5,
            backoff_factor=1.5,
            max_redirects=2,
            verify_tls=tmp_path / "ca.pem",
            proxy=ProxyConfig(
                url="socks5h://proxy.test:1080", username="bob", password="pw-secret"
            ),
            client_cert=tmp_path / "c.pem",
            client_key=tmp_path / "k.pem",
            client_key_password="key-secret",
            rate_limit=5000,
            credential_hosts=("cdn.test",),
        ),
        storage=StorageConfig(
            strategy=StorageStrategy.TEMPORARY,
            workspace_dir=tmp_path / "ws",
            buffer_bytes=1024,
            max_temp_bytes=9999,
            reserve_bytes=0,
            keep_state_on_failure=False,
            check_space=False,
        ),
        output=OutputConfig(
            directory=tmp_path / "out",
            format=OutputFormat.MP4,
            overwrite=True,
            validate=False,
            remux_backend=RemuxBackend.FFMPEG,
            ffmpeg_path=tmp_path / "ffmpeg",
            name_template="{title} [{date}]",
        ),
        verify=VerifyConfig(
            level="strong",
            expected_checksum="ab" * 32,
            keep_invalid=False,
            ffprobe_path=tmp_path / "ffprobe",
        ),
        metadata=MetadataConfig(
            policy="custom",
            title="T",
            description="D",
            language="en",
            artwork=False,
            chapters=False,
        ),
        selection=SelectionConfig(
            quality="720p",
            max_bitrate=3_000_000,
            audio_languages=("en", "de"),
            subtitle_names=("English",),
            video_only=False,
            codec="h264",
            video_range="sdr",
            max_frame_rate=30,
        ),
    )


def test_default_config_round_trips() -> None:
    config = DownloadConfig()
    options, secrets = config_to_options(config)
    assert secrets == {}
    assert config_from_options(options, secrets) == config


def test_rich_config_round_trips_through_json(tmp_path: Path) -> None:
    config = rich_config(tmp_path)
    options, secrets = config_to_options(config)
    rebuilt = config_from_options(json.loads(json.dumps(options)), json.loads(json.dumps(secrets)))
    assert rebuilt == config


def test_secrets_are_split_from_options(tmp_path: Path) -> None:
    options, secrets = config_to_options(rich_config(tmp_path))
    text = json.dumps(options)
    for secret in ("top-secret", "cookie-secret", "pw-secret", "key-secret", "bob"):
        assert secret not in text
    assert options["network"]["headers"] == {"Referer": "https://site.test/"}
    assert secrets["headers"] == {"Authorization": "Bearer top-secret"}
    assert secrets["cookies"] == {"sid": "cookie-secret"}
    assert secrets["proxy_password"] == "pw-secret"
    assert secrets["client_key_password"] == "key-secret"


def test_credentials_inside_a_proxy_address_are_secret() -> None:
    config = DownloadConfig(
        network=NetworkConfig(proxy=ProxyConfig(url="http://u:p@proxy.test:8080"))
    )
    options, secrets = config_to_options(config)
    assert "u:p" not in json.dumps(options)
    assert secrets["proxy_url"] == "http://u:p@proxy.test:8080"
    assert config_from_options(options, secrets) == config


def test_options_without_secrets_still_build_a_config(tmp_path: Path) -> None:
    options, _ = config_to_options(rich_config(tmp_path))
    config = config_from_options(options, {})
    assert "Authorization" not in config.network.headers
    assert not config.network.cookies


def test_a_key_fetcher_cannot_be_queued() -> None:
    with pytest.raises(ConfigurationError, match="key_fetcher"):
        config_to_options(DownloadConfig(key_fetcher=lambda _u: b"0" * 16))


def test_the_default_output_folder_fills_in_only_when_unset(tmp_path: Path) -> None:
    options, _ = config_to_options(DownloadConfig())
    assert config_from_options(options, default_directory=tmp_path).output.directory == tmp_path
    options["output"]["directory"] = str(tmp_path / "x")
    assert (
        config_from_options(options, default_directory=tmp_path).output.directory == tmp_path / "x"
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"concurrency": 0},
        {"network": {"retries": -1}},
        {"storage": {"strategy": "nonsense"}},
        {"output": {"format": "avi"}},
        {"selection": {"video_range": 5, "quality": ["x"]}},
        {"network": {"headers": {"bad header": "x"}}},
    ],
)
def test_invalid_options_fail_as_configuration_errors(bad: dict) -> None:
    with pytest.raises(ConfigurationError):
        config_from_options(bad)


def test_empty_options_mean_defaults() -> None:
    assert config_from_options({}) == DownloadConfig()
