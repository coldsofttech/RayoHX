"""The ``profile`` commands, and using a profile with ``queue add`` and ``download``."""

import json
from pathlib import Path
from typing import Any

import pytest
from rayohx import OutputFormat, Rayo
from rayohx.capabilities import Capabilities
from rayohx.platform.secrets import MemorySecretStore
from typer.testing import CliRunner

from rayohx_cli.cli import app
from tests.conftest import FakeDownloader
from tests.helpers.cli import MASTER, last, run_with


@pytest.fixture(autouse=True)
def platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "platform"
    real = Rayo

    def make(home: Path | None = None, **kwargs: Any) -> Rayo:
        return real(
            home=tmp_path / "platform",
            download_dir=tmp_path / "dl",
            secrets=MemorySecretStore(),
            **kwargs,
        )

    monkeypatch.setattr("rayohx_cli.cli.queue.Rayo", make)
    return home


def invoke(runner: CliRunner, *args: str, ok: bool = True) -> Any:
    result = runner.invoke(app, list(args), catch_exceptions=False)
    if ok:
        assert result.exit_code == 0, result.stderr
    return result


def profiles(runner: CliRunner) -> list[dict[str, Any]]:
    return list(json.loads(invoke(runner, "profile", "list", "--json").stdout))


def test_list_shows_the_built_in_profiles(runner: CliRunner) -> None:
    items = profiles(runner)
    assert [p["id"] for p in items] == ["best-quality", "1080p", "mobile", "archive", "custom"]
    assert all(p["builtin"] and not p["default"] for p in items)
    table = invoke(runner, "profile", "list").stdout
    assert "Archive" in table
    assert "built-in" in table


def test_create_show_edit_and_delete(runner: CliRunner) -> None:
    result = invoke(
        runner, "profile", "create", "Movies", "--from", "1080p",
        "--set", "selection.audio_languages=en,de", "--set", "output.format=mp4",
        "--set", "network.retries=5", "--naming", "{name} {date}", "--verify", "strong",
        "--max-attempts", "4", "-d", "for films",
    )  # fmt: skip
    assert result.stdout.strip() == "movies"
    shown = json.loads(invoke(runner, "profile", "show", "movies", "--json").stdout)
    assert shown["options"] == {
        "selection": {
            "quality": "best",
            "max_resolution": "1080p",
            "audio_languages": ["en", "de"],
        },
        "output": {"format": "mp4"},
        "network": {"retries": 5},
    }
    assert (shown["naming"], shown["verify"], shown["description"]) == (
        "{name} {date}",
        "strong",
        "for films",
    )
    assert shown["retry"]["max_attempts"] == 4

    invoke(runner, "profile", "edit", "movies", "--set", "selection.max_resolution=720p",
           "--unset", "network.retries", "--naming", "")  # fmt: skip
    edited = json.loads(invoke(runner, "profile", "show", "movies", "--json").stdout)
    assert edited["options"]["selection"]["max_resolution"] == "720p"
    assert "network" not in edited["options"]
    assert edited["naming"] is None

    assert "Movies" in invoke(runner, "profile", "show", "movies").stdout
    invoke(runner, "profile", "delete", "movies", "--yes")
    assert "movies" not in [p["id"] for p in profiles(runner)]


def test_invalid_profiles_are_refused_with_a_reason(runner: CliRunner) -> None:
    for args, text in [
        (["create", "A", "--set", "selection.quality=hd"], "quality"),
        (["create", "A", "--set", "nonsense.key=1"], "not a setting"),
        (["create", "A", "--set", "network.cookies=x"], "secrets"),
        (["create", "A", "--naming", "{nope}"], "naming token"),
        (["create", "A", "--verify", "maybe"], "verification"),
        (["create", "A", "--set", "novalue"], "KEY=VALUE"),
        (["create", "Mobile"], "already exists"),
        (["edit", "mobile", "--description", "x"], "built-in"),
        (["delete", "archive", "--yes"], "built-in"),
        (["show", "ghost"], "no profile"),
    ]:
        result = invoke(runner, "profile", *args, ok=False)
        assert result.exit_code == 2, (args, result.stderr)
        assert text in result.stderr, (args, result.stderr)
    assert [p["id"] for p in profiles(runner)][-1] == "custom"


def test_duplicate_rename_and_default(runner: CliRunner) -> None:
    assert (
        invoke(runner, "profile", "duplicate", "archive", "My Archive").stdout.strip()
        == "my-archive"
    )
    invoke(runner, "profile", "rename", "my-archive", "Keeper")
    assert "Keeper" in [p["name"] for p in profiles(runner)]
    assert "no default" in invoke(runner, "profile", "default").stderr
    assert invoke(runner, "profile", "default", "mobile").stdout.strip() == "mobile"
    assert invoke(runner, "profile", "default").stdout.strip() == "mobile"
    assert [p["id"] for p in profiles(runner) if p["default"]] == ["mobile"]
    invoke(runner, "profile", "default", "--clear")
    assert not any(p["default"] for p in profiles(runner))
    assert invoke(runner, "profile", "default", "mobile", "--clear", ok=False).exit_code == 2


def test_export_import_round_trip(runner: CliRunner, tmp_path: Path) -> None:
    invoke(runner, "profile", "create", "Mine", "--set", "output.format=mp4")
    file = tmp_path / "profiles.json"
    invoke(runner, "profile", "export", "-o", str(file))
    assert json.loads(file.read_text())["profiles"][0]["name"] == "Mine"
    invoke(runner, "profile", "delete", "mine", "--yes")
    assert invoke(runner, "profile", "import", str(file)).stdout.strip() == "mine"
    assert "Mine (2)" not in invoke(runner, "profile", "list").stdout
    again = invoke(runner, "profile", "import", str(file), "--on-conflict", "rename")
    assert again.stdout.strip() == "mine-2"
    assert (
        invoke(runner, "profile", "import", str(file), "--on-conflict", "error", ok=False).exit_code
        == 2
    )
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert invoke(runner, "profile", "import", str(bad), ok=False).exit_code == 2
    assert "Mine" in invoke(runner, "profile", "export").stdout


def test_validate_reports_problems_for_this_machine(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rayohx.platform.profiles.rules.detect", lambda _p=None: Capabilities())
    monkeypatch.setattr("rayohx_cli.cli.profile.detect", lambda _p=None: Capabilities())
    result = invoke(runner, "profile", "validate", "archive", ok=False)
    assert result.exit_code == 2
    assert "needs FFmpeg" in result.stderr
    assert "is valid" in invoke(runner, "profile", "validate", "mobile").stderr
    listing = invoke(runner, "profile", "list").stdout
    assert "needs FFmpeg" in listing
    shown = json.loads(invoke(runner, "profile", "show", "archive", "--json").stdout)
    assert shown["findings"][0]["field"] == "output.format"


# --- using profiles ----------------------------------------------------------------------------

URL = "https://media.example.com/a.m3u8"


def queued(runner: CliRunner) -> list[dict[str, Any]]:
    return list(json.loads(invoke(runner, "queue", "list", "--json").stdout)["items"])


def job_options(runner: CliRunner, job: str) -> dict[str, Any]:
    exported = json.loads(invoke(runner, "queue", "export", job).stdout)
    return dict(exported[0]["options"])


def test_queue_add_uses_the_profile_and_only_the_options_you_give(runner: CliRunner) -> None:
    job = invoke(runner, "queue", "add", URL, "--profile", "mobile").stdout.strip()
    options = job_options(runner, job)
    assert options["selection"]["max_resolution"] == "480p"
    assert options["output"]["format"] == "mp4"
    assert queued(runner)[0]["profile"] == "mobile"

    other = invoke(runner, "queue", "add", URL, "--profile", "mobile", "--max-resolution", "720p",
                   "--quality", "best").stdout.strip()  # fmt: skip
    options = job_options(runner, other)
    assert options["selection"]["max_resolution"] == "720p"  # given, so it wins
    assert options["selection"]["max_bitrate"] == 1_500_000  # not given, so the profile's stays
    assert options["output"]["format"] == "mp4"


def test_the_default_profile_applies_to_queue_add(runner: CliRunner) -> None:
    invoke(runner, "profile", "default", "1080p")
    job = invoke(runner, "queue", "add", URL).stdout.strip()
    assert job_options(runner, job)["selection"]["max_resolution"] == "1080p"
    assert queued(runner)[0]["profile"] == "1080p"


def test_profile_retry_applies_unless_max_attempts_is_given(runner: CliRunner) -> None:
    invoke(runner, "queue", "add", URL, "--profile", "archive")
    invoke(runner, "queue", "add", URL, "--profile", "archive", "--max-attempts", "2")
    plain = invoke(runner, "queue", "add", URL, "--profile", "mobile")
    assert plain.exit_code == 0
    attempts = sorted((j["created_at"], j["max_attempts"]) for j in queued(runner))
    assert [a for _, a in attempts] == [5, 2, 3]


def test_secrets_given_on_the_command_line_stay_out_of_the_profile_settings(
    runner: CliRunner,
) -> None:
    job = invoke(
        runner, "queue", "add", URL, "--profile", "mobile",
        "--header", "Authorization: Bearer HUSH", "--header", "Accept: */*",
    ).stdout.strip()  # fmt: skip
    text = invoke(runner, "queue", "export", job).stdout
    assert "HUSH" not in text
    assert json.loads(text)[0]["options"]["network"]["headers"] == {"Accept": "*/*"}


def test_an_unknown_profile_is_a_usage_error(runner: CliRunner) -> None:
    result = invoke(runner, "queue", "add", URL, "--profile", "ghost", ok=False)
    assert result.exit_code == 2
    assert "no profile" in result.stderr
    assert queued(runner) == []


def test_download_with_a_profile(runner: CliRunner, fake_downloader: type[FakeDownloader]) -> None:
    config = run_with(runner, fake_downloader, ["download", MASTER, "--profile", "mobile"])
    assert config.selection.max_resolution == "480p"
    assert config.output.format is OutputFormat.MP4
    config = run_with(
        runner, fake_downloader,
        ["download", MASTER, "--profile", "mobile", "--max-resolution", "720p", "--format", "auto"],
    )  # fmt: skip
    assert config.selection.max_resolution == "720p"
    assert config.output.format is OutputFormat.AUTO  # given on the command line
    assert last(fake_downloader).config is config


def test_download_without_a_profile_is_unchanged(
    runner: CliRunner, fake_downloader: type[FakeDownloader]
) -> None:
    config = run_with(runner, fake_downloader, ["download", MASTER])
    assert config.selection.max_resolution is None
    assert config.output.format is OutputFormat.AUTO


def test_download_with_an_unknown_profile_stops_before_downloading(
    runner: CliRunner, fake_downloader: type[FakeDownloader]
) -> None:
    before = len(fake_downloader.instances)
    result = invoke(runner, "download", MASTER, "--profile", "ghost", ok=False)
    assert result.exit_code == 2
    assert len(fake_downloader.instances) == before


# --- verification, metadata and details --------------------------------------------------------


def test_queue_add_takes_verification_and_metadata_options(runner: CliRunner) -> None:
    job = invoke(
        runner, "queue", "add", URL, "--profile", "mobile", "--verify", "strong",
        "--checksum", "ab" * 32, "--metadata", "minimal", "--title", "My title",
        "--name-template", "{title} [{date}]",
    ).stdout.strip()  # fmt: skip
    options = job_options(runner, job)
    assert options["verify"]["level"] == "strong"
    assert options["verify"]["expected_checksum"] == "ab" * 32
    assert options["metadata"]["policy"] == "minimal"
    assert options["metadata"]["title"] == "My title"
    assert options["output"]["name_template"] == "{title} [{date}]"


def test_the_platform_default_applies_without_the_options(runner: CliRunner) -> None:
    job = invoke(runner, "queue", "add", URL).stdout.strip()
    options = job_options(runner, job)
    assert options["verify"]["level"] == "basic"
    assert options["metadata"]["policy"] == "preserve"


def test_a_title_alone_means_custom_metadata(runner: CliRunner) -> None:
    job = invoke(runner, "queue", "add", URL, "--title", "Only").stdout.strip()
    metadata = job_options(runner, job)["metadata"]
    assert metadata["title"] == "Only"  # replaces the stream's own title
    assert metadata["policy"] == "preserve"  # the policy is the profile's or the default


def test_bad_verification_options_are_usage_errors(runner: CliRunner) -> None:
    for args in (["--verify", "paranoid"], ["--checksum", "nothex"], ["--metadata", "all"]):
        result = invoke(runner, "queue", "add", URL, *args, ok=False)
        assert result.exit_code == 2, args
    assert queued(runner) == []


def test_download_with_verification_flags(
    runner: CliRunner, fake_downloader: type[FakeDownloader]
) -> None:
    config = run_with(
        runner, fake_downloader,
        [
            "download", MASTER, "--verify", "strong", "--checksum", "cd" * 32,
            "--metadata", "preserve",
        ],
    )  # fmt: skip
    assert config.verify.level.value == "strong"
    assert config.verify.expected_checksum == "cd" * 32
    assert config.metadata.policy.value == "preserve"
    plain = run_with(runner, fake_downloader, ["download", MASTER])
    assert not plain.verify.requested
    assert not plain.metadata.writes_anything


def test_the_queue_shows_how_a_job_was_checked(runner: CliRunner) -> None:
    job = invoke(runner, "queue", "add", URL).stdout.strip()
    assert "not verified" in invoke(runner, "queue", "verification", job).stderr
    assert invoke(runner, "queue", "verification", "ghost", ok=False).exit_code == 1
