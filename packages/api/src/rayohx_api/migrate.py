"""Bringing the version 1 saved default options into the platform as a profile."""

import logging
from pathlib import Path
from typing import Any

from rayohx import Rayo
from rayohx.errors import RayoHXError
from rayohx.platform.jobs import config_to_options
from rayohx.platform.migrate import MigrationReport, migrate

from rayohx_api.build import DEFAULT_CONCURRENCY, download_config
from rayohx_api.defaults import DefaultsStore
from rayohx_api.schemas_v1 import DownloadCreate

logger = logging.getLogger(__name__)
PLACEHOLDER = "https://example.invalid/placeholder.m3u8"


def defaults_to_options(defaults: dict[str, Any], download_dir: Path) -> dict[str, Any]:
    """Profile options for a version 1 defaults document (the shape of a download request)."""
    request = DownloadCreate.model_validate({**defaults, "url": PLACEHOLDER})
    config = download_config(
        request, base=download_dir, local=True, concurrency=DEFAULT_CONCURRENCY
    )
    options, _secrets = config_to_options(config)
    return options


def import_v1_defaults(
    rayo: Rayo, store: DefaultsStore, *, make_default: bool = False, dry_run: bool = False
) -> MigrationReport:
    """Import the saved defaults as the ``Default`` profile, once. Never raises for bad data."""
    options: dict[str, Any] | None = None
    notes: list[str] = []
    data = store.get()
    if data:
        try:
            options = defaults_to_options(data, rayo.download_dir)
        except (RayoHXError, ValueError) as exc:
            notes.append(f"The saved defaults in {store.path} could not be read: {exc}")
    report = migrate(rayo, defaults_options=options, make_default=make_default, dry_run=dry_run)
    if notes:
        logger.warning(notes[0])
        return MigrationReport(**{**_fields(report), "notes": (*report.notes, *notes)})
    return report


def _fields(report: MigrationReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "latest_version": report.latest_version,
        "backup": report.backup,
        "recovered_database": report.recovered_database,
        "defaults": report.defaults,
        "profile": report.profile,
        "made_default": report.made_default,
        "notes": report.notes,
    }
