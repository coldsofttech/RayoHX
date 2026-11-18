"""Saving profiles, and finding them by name."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from rayohx.errors import ConfigurationError
from rayohx.platform.jobs.retry import RetryPolicy
from rayohx.platform.profiles.builtin import BUILTIN_PROFILES
from rayohx.platform.profiles.model import SCHEMA_VERSION, DownloadProfile, slug
from rayohx.platform.profiles.rules import check

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Iterable, Mapping

    from rayohx.platform.persistence import Database, SettingsStore

ProfileList = list[DownloadProfile]
DEFAULT_KEY = "profiles.default"
EXPORT_KEY = "rayohx_profiles"

#: Steps that bring stored or imported profile data from one schema version to the next.
#: ``MIGRATIONS[n]`` turns version ``n`` data into version ``n + 1`` data.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def migrate(data: Mapping[str, Any]) -> dict[str, Any]:
    """Bring profile data up to the current schema version."""
    current = dict(data)
    version = int(current.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise ConfigurationError(
            "The profile was made by a newer RayoHX.", hint="Update RayoHX to use it."
        )
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ConfigurationError(f"Profiles of version {version} cannot be read any more.")
        current = step(current)
        version += 1
        current["schema_version"] = version
    return current


class ProfileStore:
    """The built-in profiles and the ones you made."""

    def __init__(
        self, database: Database, settings: SettingsStore, *, clock: Callable[[], float] = time.time
    ) -> None:
        self._db = database
        self._settings = settings
        self._clock = clock
        self._builtin = {p.id: p for p in BUILTIN_PROFILES}

    # --- reading ---------------------------------------------------------------------------

    def list(self) -> list[DownloadProfile]:
        """Built-in profiles first, then yours by name."""
        rows = self._db.fetchall("SELECT * FROM profiles ORDER BY name COLLATE NOCASE")
        return [*BUILTIN_PROFILES, *(self._row(r) for r in rows)]

    def get(self, ref: str) -> DownloadProfile | None:
        """A profile by id or by name (ignoring case)."""
        wanted = ref.strip().lower()
        for profile in self.list():
            if wanted in {profile.id.lower(), profile.name.lower()}:
                return profile
        return None

    def require(self, ref: str) -> DownloadProfile:
        profile = self.get(ref)
        if profile is None:
            names = ", ".join(p.id for p in self.list())
            raise ConfigurationError(f"There is no profile {ref!r}.", hint=f"Profiles: {names}.")
        return profile

    @staticmethod
    def _row(row: sqlite3.Row) -> DownloadProfile:
        data = migrate({**json.loads(row["data_json"]), "schema_version": row["schema_version"]})
        data["name"], data["description"] = row["name"], row["description"]
        return DownloadProfile.from_dict(data, profile_id=row["id"])

    # --- the default -----------------------------------------------------------------------

    def default(self) -> DownloadProfile | None:
        """The profile used when a download names none."""
        ref = self._settings.get(DEFAULT_KEY)
        return self.get(ref) if ref else None

    def set_default(self, ref: str | None) -> DownloadProfile | None:
        if ref is None:
            self._settings.delete(DEFAULT_KEY)
            return None
        profile = self.require(ref)
        self._settings.set(DEFAULT_KEY, profile.id)
        return profile

    # --- changing --------------------------------------------------------------------------

    def create(
        self,
        name: str,
        *,
        description: str = "",
        options: Mapping[str, Any] | None = None,
        retry: RetryPolicy | None = None,
        naming: str | None = None,
        metadata: str = "preserve",
        verify: str = "basic",
        base: str | None = None,
    ) -> DownloadProfile:
        """Save a new profile. ``base`` starts from another profile's settings.

        Raises:
            ConfigurationError: If the name is taken or the profile is not valid.
        """
        if base is not None:
            source = self.require(base)
            options = options if options is not None else dict(source.options)
            retry = retry if retry is not None else source.retry
            naming = naming if naming is not None else source.naming
            description = description or source.description
            metadata, verify = (
                (source.metadata, source.verify)
                if (metadata, verify) == ("preserve", "basic")
                else (metadata, verify)
            )
        self._ensure_free(name)
        profile = DownloadProfile(
            id=self._free_id(name),
            name=name.strip(),
            description=description,
            options=options or {},
            retry=retry,
            naming=naming,
            metadata=metadata,
            verify=verify,
        )
        check(profile)
        self._store(profile, new=True)
        return profile

    def update(self, ref: str, **changes: Any) -> DownloadProfile:
        """Change a profile of yours. Built-in profiles are fixed: duplicate one instead."""
        profile = self._custom(ref)
        if "name" in changes and changes["name"].strip().lower() != profile.name.lower():
            self._ensure_free(changes["name"])
        updated = profile.changed(**changes)
        check(updated)
        self._store(updated, new=False)
        return updated

    def rename(self, ref: str, new_name: str) -> DownloadProfile:
        return self.update(ref, name=new_name.strip())

    def duplicate(self, ref: str, new_name: str | None = None) -> DownloadProfile:
        source = self.require(ref)
        name = new_name or self._unique_name(f"{source.name} copy")
        return self.create(name, base=source.id)

    def delete(self, ref: str) -> None:
        profile = self._custom(ref)
        with self._db.transaction() as c:
            c.execute("DELETE FROM profiles WHERE id = ?", (profile.id,))
        if self._settings.get(DEFAULT_KEY) == profile.id:
            self._settings.delete(DEFAULT_KEY)

    # --- export and import -----------------------------------------------------------------

    def export_data(self, refs: Iterable[str] | None = None) -> dict[str, Any]:
        """Profiles as plain data to save or share. Without ``refs``, all of yours."""
        chosen = (
            [self.require(r) for r in refs]
            if refs is not None
            else [p for p in self.list() if not p.builtin]
        )
        return {EXPORT_KEY: SCHEMA_VERSION, "profiles": [p.to_dict() for p in chosen]}

    def import_data(self, data: Mapping[str, Any], *, on_conflict: str = "rename") -> ProfileList:
        """Add the profiles in exported data.

        ``on_conflict`` says what to do when a name is taken: ``rename`` (add " (2)"), ``skip``
        or ``error``. Everything is checked first, so a bad profile imports nothing.
        """
        if (
            not isinstance(data, dict)
            or EXPORT_KEY not in data
            or not isinstance(data.get("profiles"), list)
        ):
            raise ConfigurationError("This is not an exported set of profiles.")
        if on_conflict not in {"rename", "skip", "error"}:
            raise ConfigurationError("on_conflict must be rename, skip or error.")
        prepared: list[DownloadProfile] = []
        taken = {p.name.lower() for p in self.list()}
        for raw in data["profiles"]:
            migrated = migrate(raw)
            profile = DownloadProfile.from_dict(
                migrated, profile_id=slug(str(migrated.get("name")))
            )
            check(profile)
            key = profile.name.lower()
            if key in taken:
                if on_conflict == "skip":
                    continue
                if on_conflict == "error":
                    raise ConfigurationError(f"A profile named {profile.name!r} already exists.")
                profile = profile.changed(name=self._unique_name(profile.name, taken))
            taken.add(profile.name.lower())
            prepared.append(profile)
        saved = []
        for profile in prepared:
            fresh = profile.changed(id=self._free_id(profile.name))
            self._store(fresh, new=True)
            saved.append(fresh)
        return saved

    # --- plumbing --------------------------------------------------------------------------

    def _custom(self, ref: str) -> DownloadProfile:
        profile = self.require(ref)
        if profile.builtin:
            raise ConfigurationError(
                f"{profile.name!r} is a built-in profile and cannot be changed.",
                hint="Duplicate it to make one you can change.",
            )
        return profile

    def _ensure_free(self, name: str) -> None:
        if not name.strip():
            raise ConfigurationError("A profile needs a name.")
        if self.get(name) is not None:
            raise ConfigurationError(f"A profile named {name.strip()!r} already exists.")

    def _free_id(self, name: str) -> str:
        base = slug(name)
        candidate, count = base, 1
        used = {p.id for p in self.list()}
        while candidate in used:
            count += 1
            candidate = f"{base}-{count}"
        return candidate

    def _unique_name(self, name: str, taken: set[str] | None = None) -> str:
        names = taken if taken is not None else {p.name.lower() for p in self.list()}
        candidate, count = name, 1
        while candidate.lower() in names:
            count += 1
            candidate = f"{name} ({count})"
        return candidate

    def _store(self, profile: DownloadProfile, *, new: bool) -> None:
        body = profile.to_dict()
        body.pop("name"), body.pop("description"), body.pop("schema_version")
        now = self._clock()
        text = json.dumps(body, sort_keys=True)
        with self._db.transaction() as c:
            if new:
                c.execute(
                    "INSERT INTO profiles (id, name, description, data_json, schema_version, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        profile.id,
                        profile.name,
                        profile.description,
                        text,
                        SCHEMA_VERSION,
                        now,
                        now,
                    ),
                )
            else:
                c.execute(
                    "UPDATE profiles SET name = ?, description = ?, data_json = ?, "
                    "schema_version = ?, updated_at = ? WHERE id = ?",
                    (profile.name, profile.description, text, SCHEMA_VERSION, now, profile.id),
                )
