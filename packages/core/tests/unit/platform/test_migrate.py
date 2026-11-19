"""Moving from version 1: the report, and importing the saved defaults once."""

from rayohx.platform import Rayo
from rayohx.platform.migrate import DEFAULTS_MARKER, migrate

OPTIONS = {"selection": {"max_resolution": "720p"}}


def test_a_report_without_defaults(rayo: Rayo) -> None:
    report = migrate(rayo)
    assert report.up_to_date
    assert report.defaults == "nothing_to_import"
    assert report.to_dict()["schema_version"] == rayo.schema_version


def test_the_defaults_become_a_profile_once(rayo: Rayo) -> None:
    report = migrate(rayo, defaults_options=OPTIONS)
    assert report.defaults == "imported"
    assert report.profile == "default"
    profile = rayo.profiles.require("default")
    assert profile.options["selection"]["max_resolution"] == "720p"
    assert rayo.profiles.default() is None or rayo.profiles.default().id != "default"
    again = migrate(rayo, defaults_options=OPTIONS)
    assert again.defaults == "already_imported"
    assert len([p for p in rayo.profiles.list() if p.name.startswith("Default")]) == 1


def test_a_dry_run_changes_nothing(rayo: Rayo) -> None:
    assert migrate(rayo, defaults_options=OPTIONS, dry_run=True).defaults == "would_import"
    assert rayo.settings.get(DEFAULTS_MARKER) is None
    assert rayo.profiles.get("default") is None


def test_it_can_become_the_default_profile(rayo: Rayo) -> None:
    report = migrate(rayo, defaults_options=OPTIONS, make_default=True)
    assert report.made_default
    default = rayo.profiles.default()
    assert default is not None
    assert default.id == "default"


def test_a_name_that_is_taken_gets_another(rayo: Rayo) -> None:
    rayo.profiles.create("Default", options={})
    report = migrate(rayo, defaults_options=OPTIONS)
    assert report.defaults == "imported"
    assert report.profile != "default"
