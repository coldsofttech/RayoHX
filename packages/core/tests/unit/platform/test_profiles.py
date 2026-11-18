"""Download profiles: the built-in ones, saving, validation, import and export, and naming."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from rayohx.capabilities import Capabilities
from rayohx.enums import OutputFormat
from rayohx.errors import ConfigurationError
from rayohx.platform import Rayo
from rayohx.platform.jobs import JobState, RetryPolicy
from rayohx.platform.profiles import (
    BUILTIN_PROFILES,
    DownloadProfile,
    Finding,
    check,
    render_name,
    resolve_options,
    to_config,
    validate,
    validate_template,
)
from rayohx.platform.profiles import model as model_module
from rayohx.platform.profiles import rules as rules_module
from rayohx.platform.profiles import store as store_module
from rayohx.platform.profiles.naming import tokens_for
from tests.unit.platform import fakes
from tests.unit.platform.conftest import wait_state

NO_FFMPEG = Capabilities()
WITH_FFMPEG = Capabilities(ffmpeg=Path("/usr/bin/ffmpeg"))
URL = "https://media.test/show/master.m3u8"


def errors(profile: DownloadProfile, caps: Capabilities | None = None, **kw: Any) -> list[Finding]:
    return [f for f in validate(profile, caps, **kw) if f.level == "error"]


# --- the built-in profiles ---------------------------------------------------------------------


def test_the_five_built_in_profiles_exist_and_are_valid() -> None:
    assert [p.id for p in BUILTIN_PROFILES] == [
        "best-quality",
        "1080p",
        "mobile",
        "archive",
        "custom",
    ]
    assert {p.name for p in BUILTIN_PROFILES} == {
        "Best Quality", "1080p", "Mobile", "Archive", "Custom",
    }  # fmt: skip
    for profile in BUILTIN_PROFILES:
        assert profile.builtin
        assert errors(profile) == [], profile.id


def test_each_built_in_profile_builds_the_settings_it_describes() -> None:
    by_id = {p.id: to_config(p) for p in BUILTIN_PROFILES}
    assert by_id["best-quality"].selection.quality == "best"
    assert by_id["1080p"].selection.max_resolution == "1080p"
    mobile = by_id["mobile"]
    assert (mobile.selection.max_resolution, mobile.selection.max_bitrate) == ("480p", 1_500_000)
    assert mobile.output.format is OutputFormat.MP4
    archive = by_id["archive"]
    assert archive.output.format is OutputFormat.MKV
    assert archive.selection.audio_languages == ("*",)
    assert archive.selection.subtitle_languages == ("*",)
    assert by_id["custom"].selection.quality == "best"


def test_archive_needs_ffmpeg_and_says_so() -> None:
    archive = next(p for p in BUILTIN_PROFILES if p.id == "archive")
    problems = errors(archive, NO_FFMPEG, machine_checks=True)
    assert [f.field for f in problems] == ["output.format"]
    assert "FFmpeg" in problems[0].message
    assert errors(archive, WITH_FFMPEG, machine_checks=True) == []
    assert errors(archive, NO_FFMPEG) == []  # saving elsewhere is fine
    with pytest.raises(ConfigurationError, match="needs FFmpeg"):
        check(archive, NO_FFMPEG, machine_checks=True)


def test_the_native_only_backend_cannot_make_matroska() -> None:
    profile = DownloadProfile(
        id="x", name="X", options={"output": {"format": "mkv", "remux_backend": "native"}}
    )
    fields = [f.field for f in errors(profile, WITH_FFMPEG, machine_checks=True)]
    assert "output.remux_backend" in fields


# --- validation --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("options", "field"),
    [
        ({"colour": {"x": 1}}, "colour"),
        ({"selection": {"flavour": "x"}}, "selection.flavour"),
        ({"selection": "best"}, "selection"),
        ({"selection": {"quality": "hd"}}, "options"),
        ({"output": {"format": "avi"}}, "options"),
        ({"concurrency": 0}, "options"),
        ({"network": {"headers": {"Authorization": "Bearer x"}}}, "network.headers.Authorization"),
        ({"network": {"cookies": {"sid": "x"}}}, "network.cookies"),
        ({"network": {"proxy": {"url": "http://u:p@proxy.test:8080"}}}, "network.proxy.url"),
        ({"network": {"client_key_password": "x"}}, "network.client_key_password"),
    ],
)
def test_bad_options_are_found_before_anything_runs(options: dict, field: str) -> None:
    profile = DownloadProfile(id="x", name="X", options=options)
    assert field in [f.field for f in errors(profile)]
    with pytest.raises(ConfigurationError):
        check(profile)


def test_plain_headers_are_fine() -> None:
    profile = DownloadProfile(
        id="x", name="X", options={"network": {"headers": {"Referer": "https://site.test/"}}}
    )
    assert errors(profile) == []


def test_other_settings_are_checked_too() -> None:
    assert errors(DownloadProfile(id="x", name="X", metadata="maybe"))[0].field == "metadata"
    assert errors(DownloadProfile(id="x", name="X", verify="paranoid"))[0].field == "verify"
    assert errors(DownloadProfile(id="x", name="X", naming="{nope}"))[0].field == "naming"
    assert errors(DownloadProfile(id="x", name="X", schema_version=99))[0].field == "schema_version"
    with pytest.raises(ConfigurationError, match="needs a name"):
        DownloadProfile(id="x", name="  ")
    with pytest.raises(ConfigurationError, match="at most"):
        DownloadProfile(id="x", name="n" * 200)


def test_every_problem_is_reported_not_just_the_first() -> None:
    profile = DownloadProfile(
        id="x", name="X", options={"nonsense": {}, "network": {"cookies": {"a": "b"}}}, verify="no"
    )
    assert len(errors(profile)) == 3
    with pytest.raises(ConfigurationError, match="and 2 more"):
        check(profile)


def test_overrides_win_over_the_profile_which_wins_over_defaults() -> None:
    mobile = next(p for p in BUILTIN_PROFILES if p.id == "mobile")
    merged = resolve_options(mobile, {"selection": {"max_resolution": "720p"}})
    assert merged["selection"]["max_resolution"] == "720p"
    assert merged["selection"]["max_bitrate"] == 1_500_000  # from the profile
    assert merged["network"]["retries"] == 3  # the engine default
    assert mobile.options["selection"]["max_resolution"] == "480p"  # nothing was changed in place


# --- naming ------------------------------------------------------------------------------------


def test_names_are_filled_from_tokens_safely() -> None:
    tokens = tokens_for(url=URL, job_id="abc", profile="Archive", moment=0)
    assert tokens["name"] == "show"
    assert tokens["host"] == "media.test"
    assert render_name("{name} [{profile}] {date}", tokens).startswith("show [Archive] 19")
    assert render_name("{job}", tokens) == "abc"
    assert render_name("a/b".replace("/", "-"), tokens) == "a-b"
    assert render_name("{name}", {"name": 'a/b:c*d?"e'}) == "a_b_c_d_e"
    assert render_name("{name}", {"name": "  ..hidden.. "}) == "hidden"
    assert render_name("{name}", {"name": "CON"}) == "_CON"
    assert len(render_name("{name}", {"name": "x" * 500})) <= 120
    assert render_name("{name}", {"name": "Zażółć gęślą"}) == "Zażółć gęślą"  # unicode is kept


def test_names_are_deterministic() -> None:
    tokens = tokens_for(url=URL, job_id="j", profile="P", moment=1_700_000_000)
    assert render_name("{name}-{date}-{time}", tokens) == render_name(
        "{name}-{date}-{time}", tokens
    )


@pytest.mark.parametrize(
    "template", ["", "  ", "{nope}", "{name", "name}", "{{name}}", "a/b", "a\\b"]
)
def test_bad_templates_are_refused(template: str) -> None:
    with pytest.raises(ConfigurationError):
        validate_template(template)


def test_a_template_that_gives_nothing_is_an_error() -> None:
    with pytest.raises(ConfigurationError, match="empty name"):
        render_name("{name}", {"name": "///"})


# --- the store ---------------------------------------------------------------------------------


def test_built_ins_come_first_and_can_be_found_by_id_or_name(rayo: Rayo) -> None:
    store = rayo.profiles
    assert [p.id for p in store.list()][:5] == [
        "best-quality",
        "1080p",
        "mobile",
        "archive",
        "custom",
    ]
    assert store.get("MOBILE") is store.get("mobile")
    assert store.get("best quality") is not None
    assert store.get("nope") is None
    with pytest.raises(ConfigurationError, match="no profile"):
        store.require("nope")


def test_creating_editing_renaming_duplicating_and_deleting(rayo: Rayo) -> None:
    store = rayo.profiles
    mine = store.create(
        "My Movies",
        description="for films",
        options={"selection": {"max_resolution": "720p"}},
        retry=RetryPolicy(max_attempts=2),
        naming="{name} {date}",
        verify="strong",
    )
    assert (mine.id, mine.builtin) == ("my-movies", False)
    got = store.get("my movies")
    assert got is not None
    assert got.retry == RetryPolicy(max_attempts=2)
    assert (got.naming, got.verify, got.description) == ("{name} {date}", "strong", "for films")

    edited = store.update(mine.id, description="films", options={"selection": {"quality": "720p"}})
    assert store.require(mine.id).options["selection"] == {"quality": "720p"}
    assert edited.description == "films"

    renamed = store.rename(mine.id, "Films")
    assert (renamed.id, renamed.name) == ("my-movies", "Films")  # the id never changes
    assert store.get("My Movies") is None

    copy = store.duplicate("Films")
    assert copy.name == "Films copy"
    assert dict(copy.options) == {"selection": {"quality": "720p"}}
    again = store.duplicate("Films")
    assert again.name == "Films copy (2)"
    from_builtin = store.duplicate("archive", "Mine")
    assert from_builtin.builtin is False
    assert dict(from_builtin.options) == dict(store.require("archive").options)
    assert from_builtin.verify == "strong"

    store.delete("Films")
    assert store.get("films") is None
    assert store.get("Films copy") is not None


def test_names_are_unique_whatever_the_case_and_built_ins_are_protected(rayo: Rayo) -> None:
    store = rayo.profiles
    store.create("Travel")
    for name in ("travel", "TRAVEL", "mobile", "Best Quality"):
        with pytest.raises(ConfigurationError, match="already exists"):
            store.create(name)
    with pytest.raises(ConfigurationError, match="needs a name"):
        store.create("   ")
    for action in (
        lambda: store.update("mobile", description="x"),
        lambda: store.rename("archive", "Other"),
        lambda: store.delete("1080p"),
    ):
        with pytest.raises(ConfigurationError, match="built-in"):
            action()


def test_an_invalid_profile_cannot_be_saved_or_updated(rayo: Rayo) -> None:
    store = rayo.profiles
    with pytest.raises(ConfigurationError):
        store.create("Bad", options={"selection": {"quality": "hd"}})
    assert store.get("Bad") is None
    good = store.create("Good")
    with pytest.raises(ConfigurationError):
        store.update(good.id, naming="{nope}")
    assert store.require("Good").naming is None


def test_profiles_survive_a_restart(make_rayo: Callable[..., Rayo]) -> None:
    first = make_rayo()
    first.profiles.create("Keep", options={"output": {"format": "mp4"}}, verify="none")
    first.profiles.set_default("keep")
    first.close()
    second = make_rayo()
    kept = second.profiles.require("keep")
    assert dict(kept.options) == {"output": {"format": "mp4"}}
    assert kept.verify == "none"
    default = second.profiles.default()
    assert default is not None
    assert default.id == "keep"


def test_the_default_profile(rayo: Rayo) -> None:
    store = rayo.profiles
    assert store.default() is None
    assert store.set_default("Mobile").id == "mobile"  # type: ignore[union-attr]
    assert store.default().id == "mobile"  # type: ignore[union-attr]
    mine = store.create("Mine")
    store.set_default(mine.id)
    store.delete(mine.id)  # deleting the default clears it
    assert store.default() is None
    store.set_default("mobile")
    store.set_default(None)
    assert store.default() is None
    with pytest.raises(ConfigurationError):
        store.set_default("nope")


# --- export, import and migration --------------------------------------------------------------


def test_export_and_import_round_trip(
    rayo: Rayo, make_rayo: Callable[..., Rayo], tmp_path: Path
) -> None:
    store = rayo.profiles
    store.create(
        "A", options={"selection": {"max_resolution": "480p"}}, naming="{name}", verify="none"
    )
    store.create("B", retry=RetryPolicy(max_attempts=4))
    data = json.loads(json.dumps(store.export_data()))  # as a file would carry it
    assert [p["name"] for p in data["profiles"]] == ["A", "B"]  # built-ins are not exported
    assert "id" not in data["profiles"][0]

    other = make_rayo(home=tmp_path / "other")
    imported = other.profiles.import_data(data)
    assert [p.name for p in imported] == ["A", "B"]
    a = other.profiles.require("A")
    assert dict(a.options) == {"selection": {"max_resolution": "480p"}}
    assert (a.naming, a.verify) == ("{name}", "none")
    assert other.profiles.require("B").retry == RetryPolicy(max_attempts=4)


def test_export_can_name_built_in_profiles(rayo: Rayo) -> None:
    data = rayo.profiles.export_data(["archive"])
    assert data["profiles"][0]["name"] == "Archive"


def test_importing_a_name_that_exists(rayo: Rayo) -> None:
    store = rayo.profiles
    store.create("A")
    data = store.export_data()
    assert [p.name for p in store.import_data(data)] == ["A (2)"]
    assert store.import_data(data, on_conflict="skip") == []
    with pytest.raises(ConfigurationError, match="already exists"):
        store.import_data(data, on_conflict="error")
    with pytest.raises(ConfigurationError, match="on_conflict"):
        store.import_data(data, on_conflict="overwrite")


def test_a_bad_file_imports_nothing(rayo: Rayo) -> None:
    store = rayo.profiles
    good = {"name": "Fine", "options": {}}
    bad = {"name": "Broken", "options": {"selection": {"quality": "hd"}}}
    with pytest.raises(ConfigurationError):
        store.import_data({"rayohx_profiles": 1, "profiles": [good, bad]})
    assert store.get("Fine") is None
    for junk in ({}, {"profiles": []}, {"rayohx_profiles": 1, "profiles": "x"}, [], "x"):
        with pytest.raises(ConfigurationError, match="not an exported"):
            store.import_data(junk)  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError):
        store.import_data({"rayohx_profiles": 1, "profiles": [{"options": {}}]})


def test_imported_secrets_are_refused(rayo: Rayo) -> None:
    data = {
        "rayohx_profiles": 1,
        "profiles": [{"name": "Leaky", "options": {"network": {"cookies": {"sid": "x"}}}}],
    }
    with pytest.raises(ConfigurationError, match="secrets"):
        rayo.profiles.import_data(data)


def test_old_profile_data_is_migrated_and_newer_data_refused(
    rayo: Rayo, monkeypatch: pytest.MonkeyPatch
) -> None:
    for module in (store_module, rules_module, model_module):
        monkeypatch.setattr(module, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(
        store_module.MIGRATIONS,
        1,
        lambda d: {**d, "options": {"selection": {"quality": d.pop("old_quality")}}},
    )
    old = {"name": "Old", "old_quality": "720p", "schema_version": 1}
    imported = rayo.profiles.import_data({"rayohx_profiles": 1, "profiles": [old]})
    assert dict(imported[0].options) == {"selection": {"quality": "720p"}}
    assert imported[0].schema_version == 2
    with pytest.raises(ConfigurationError, match="newer"):
        store_module.migrate({"name": "x", "schema_version": 3})
    monkeypatch.setitem(store_module.MIGRATIONS, 1, None)  # type: ignore[arg-type]
    monkeypatch.delitem(store_module.MIGRATIONS, 1)
    with pytest.raises(ConfigurationError, match="cannot be read"):
        store_module.migrate({"name": "x", "schema_version": 1})


# --- using a profile when queueing -------------------------------------------------------------


def test_a_job_takes_its_settings_from_the_profile(rayo: Rayo) -> None:
    job = rayo.queue.add(URL, profile="Mobile")
    assert job.profile_id == "mobile"
    assert job.spec.options["selection"]["max_resolution"] == "480p"
    assert job.spec.options["output"]["format"] == "mp4"
    assert job.to_dict()["profile"] == "mobile"
    assert rayo.queue.get(job.id).profile_id == "mobile"  # type: ignore[union-attr]


def test_overrides_and_secrets_apply_on_top_of_the_profile(rayo: Rayo) -> None:
    job = rayo.queue.add(
        URL,
        profile="mobile",
        overrides={"selection": {"max_resolution": "720p"}},
        secrets={"cookies": {"sid": "HUSH"}},
    )
    assert job.spec.options["selection"]["max_resolution"] == "720p"
    assert job.spec.options["selection"]["max_bitrate"] == 1_500_000
    assert "HUSH" not in job.spec.to_json()


def test_the_default_profile_is_used_when_none_is_named(rayo: Rayo) -> None:
    rayo.profiles.set_default("1080p")
    assert rayo.queue.add(URL).profile_id == "1080p"
    assert rayo.queue.add(URL, profile="mobile").profile_id == "mobile"
    rayo.profiles.set_default(None)
    plain = rayo.queue.add(URL)
    assert plain.profile_id is None
    assert plain.spec.options["selection"]["max_resolution"] is None


def test_profile_and_complete_settings_do_not_mix(rayo: Rayo) -> None:
    from rayohx.config import DownloadConfig

    with pytest.raises(ConfigurationError, match="or complete settings"):
        rayo.queue.add(URL, profile="mobile", config=DownloadConfig())
    with pytest.raises(ConfigurationError, match="or complete settings"):
        rayo.queue.add(URL, overrides={"selection": {}}, options={})
    with pytest.raises(ConfigurationError, match="no profile"):
        rayo.queue.add(URL, profile="ghost")


def test_a_job_keeps_the_settings_it_was_queued_with(rayo: Rayo) -> None:
    mine = rayo.profiles.create("Mine", options={"selection": {"max_resolution": "480p"}})
    job = rayo.queue.add(URL, profile=mine.id)
    rayo.profiles.update(mine.id, options={"selection": {"max_resolution": "1080p"}})
    assert rayo.queue.get(job.id).spec.options["selection"]["max_resolution"] == "480p"  # type: ignore[union-attr]
    rayo.profiles.delete(mine.id)
    assert rayo.queue.get(job.id) is not None


def test_the_profile_sets_retries_unless_the_caller_does(rayo: Rayo) -> None:
    assert rayo.queue.add(URL, profile="archive").spec.retry.max_attempts == 5
    assert (
        rayo.queue.add(
            URL, profile="archive", retry=RetryPolicy(max_attempts=2)
        ).spec.retry.max_attempts
        == 2
    )
    assert rayo.queue.add(URL, profile="mobile").spec.retry == RetryPolicy()


def test_the_profile_names_the_file(rayo: Rayo) -> None:
    mine = rayo.profiles.create("Named", naming="{name} - {profile}")
    assert rayo.queue.add(URL, profile=mine.id).spec.output_name == "show - Named"
    explicit = rayo.queue.add(URL, profile=mine.id, output_name="mine.ts")
    assert explicit.spec.output_name == "mine.ts"
    assert rayo.queue.add(URL, profile="mobile").spec.output_name is None


def test_a_profile_this_machine_cannot_run_is_refused_when_queued(
    rayo: Rayo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rayohx.platform.profiles.rules.detect", lambda _path=None: NO_FFMPEG)
    with pytest.raises(ConfigurationError, match="needs FFmpeg"):
        rayo.queue.add(URL, profile="archive")
    with pytest.raises(ConfigurationError, match="needs FFmpeg"):
        rayo.queue.add(URL, profile="mobile", overrides={"output": {"format": "audio"}})
    assert rayo.queue.list() == []  # nothing was queued
    monkeypatch.setattr("rayohx.platform.profiles.rules.detect", lambda _path=None: WITH_FFMPEG)
    assert rayo.queue.add(URL, profile="archive").profile_id == "archive"


def test_a_profile_job_runs_with_the_profiles_settings(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    seen: list[Any] = []

    def capture(d: fakes.FakeDownloader) -> Any:
        seen.append((d.config.selection.max_resolution, d.config.output.format))
        return fakes.ok(d)

    fakes.FakeDownloader.scripts["*"] = capture
    job = rayo.queue.add(URL, profile="mobile")
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.COMPLETED)
    assert seen == [("480p", OutputFormat.MP4)]


# --- verification, metadata and naming in profiles ---------------------------------------------


def test_a_profile_sets_how_a_job_is_verified_and_labelled(rayo: Rayo) -> None:
    strong = rayo.queue.add(URL, profile="archive")
    assert strong.spec.options["verify"]["level"] == "strong"
    assert strong.spec.options["metadata"]["policy"] == "preserve"
    quick = rayo.queue.add(URL, profile="mobile")
    assert quick.spec.options["verify"]["level"] == "basic"
    off = rayo.profiles.create("Quiet", verify="none", metadata="none")
    plain = rayo.queue.add(URL, profile=off.id)
    assert plain.spec.options["verify"]["level"] == "none"
    assert plain.spec.options["metadata"]["policy"] == "none"


def test_without_a_profile_the_platform_verifies_and_keeps_metadata(rayo: Rayo) -> None:
    job = rayo.queue.add(URL)
    assert job.spec.options["verify"]["level"] == "basic"
    assert job.spec.options["metadata"]["policy"] == "preserve"
    # Complete settings are used exactly as given: the engine's own defaults stay quiet.
    from rayohx.config import DownloadConfig

    exact = rayo.queue.add(URL, config=DownloadConfig())
    assert exact.spec.options["verify"]["level"] == "none"
    assert exact.spec.options["metadata"]["policy"] == "none"


def test_overrides_can_ask_for_a_checksum_or_a_policy(rayo: Rayo) -> None:
    job = rayo.queue.add(
        URL,
        profile="mobile",
        overrides={"verify": {"expected_checksum": "ab" * 32}, "metadata": {"policy": "minimal"}},
    )
    assert job.spec.options["verify"]["expected_checksum"] == "ab" * 32
    assert job.spec.options["metadata"]["policy"] == "minimal"
    with pytest.raises(ConfigurationError):
        rayo.queue.add(URL, profile="mobile", overrides={"verify": {"expected_checksum": "nothex"}})


def test_a_title_in_the_name_template_waits_for_the_stream(rayo: Rayo) -> None:
    mine = rayo.profiles.create("Titled", naming="{title} - {profile} - {name}")
    job = rayo.queue.add(URL, profile=mine.id)
    assert job.spec.output_name is None
    assert job.spec.options["output"]["name_template"] == "{title} - Titled - show"
    fixed = rayo.profiles.create("Fixed", naming="{name} {profile}")
    plain = rayo.queue.add(URL, profile=fixed.id)
    assert plain.spec.output_name == "show Fixed"
    assert plain.spec.options["output"]["name_template"] is None
    assert rayo.queue.add(URL, profile=mine.id, output_name="own.ts").spec.output_name == "own.ts"
