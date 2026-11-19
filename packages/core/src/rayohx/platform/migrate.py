"""Moving from version 1 to version 2 without losing anything.

Version 1 kept one thing outside the engine: the API's saved default options. Version 2 keeps
settings in profiles, so the defaults become a profile named ``Default``. Nothing is deleted: the
old file stays where it is, and the import runs once (a stored marker remembers that it did).
The database itself upgrades when it is opened, after a backup (see ``Database``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rayohx.errors import ConfigurationError
from rayohx.platform.persistence.migrations import latest_version

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rayohx.platform.facade import Rayo

DEFAULTS_MARKER = "migration.v1_defaults"
DEFAULTS_PROFILE = "Default"


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """What a migration found and did."""

    schema_version: int
    latest_version: int
    backup: str | None = None
    recovered_database: str | None = None
    #: ``imported``, ``already_imported``, ``nothing_to_import`` or ``would_import``.
    defaults: str = "nothing_to_import"
    profile: str | None = None
    made_default: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def up_to_date(self) -> bool:
        return self.schema_version == self.latest_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "latest_version": self.latest_version,
            "up_to_date": self.up_to_date,
            "backup": self.backup,
            "recovered_database": self.recovered_database,
            "defaults": self.defaults,
            "profile": self.profile,
            "made_default": self.made_default,
            "notes": list(self.notes),
        }


def migrate(
    rayo: Rayo,
    *,
    defaults_options: Mapping[str, Any] | None = None,
    make_default: bool = False,
    dry_run: bool = False,
) -> MigrationReport:
    """Report on the database and import the version 1 defaults (as profile options) once.

    ``defaults_options`` are profile options converted by the caller (the API knows the version 1
    format). With ``dry_run`` nothing is changed. Opening ``rayo`` already upgraded the database.
    """
    database = rayo.database
    notes: list[str] = []
    status = "nothing_to_import"
    profile_id: str | None = None
    made_default = False

    if defaults_options:
        if rayo.settings.get(DEFAULTS_MARKER):
            status = "already_imported"
            profile_id = str(rayo.settings.get(DEFAULTS_MARKER))
        elif dry_run:
            status = "would_import"
        else:
            name = DEFAULTS_PROFILE
            if rayo.profiles.get(name) is not None:
                name = f"{DEFAULTS_PROFILE} (version 1)"
            try:
                profile = rayo.profiles.create(
                    name,
                    description="Imported from the version 1 saved default options.",
                    options=defaults_options,
                )
            except ConfigurationError as exc:
                notes.append(f"The version 1 defaults could not be imported: {exc}")
            else:
                rayo.settings.set(DEFAULTS_MARKER, profile.id)
                status, profile_id = "imported", profile.id
                if make_default:
                    rayo.profiles.set_default(profile.id)
                    made_default = True
    if status == "imported":
        notes.append("The version 1 file was left where it was; delete it when you are ready.")
    return MigrationReport(
        schema_version=database.schema_version,
        latest_version=latest_version(),
        backup=str(database.backup_path) if database.backup_path else None,
        recovered_database=str(database.recovered_from) if database.recovered_from else None,
        defaults=status,
        profile=profile_id,
        made_default=made_default,
        notes=tuple(notes),
    )
