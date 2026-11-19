"""What is worth saying about how the disk is used."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.platform.diagnostics.stream import Finding
from rayohx.platform.storage.policy import StorageLevel
from rayohx.platform.storage.sizes import format_size

if TYPE_CHECKING:
    from rayohx.platform.storage.cleanup import WorkspaceReport
    from rayohx.platform.storage.service import StorageSnapshot

ABANDONED_DAYS = 7


def storage_findings(snapshot: StorageSnapshot, workspaces: list[WorkspaceReport]) -> list[Finding]:
    """Problems and hints from a storage snapshot and the working folders."""
    found: list[Finding] = []
    for volume in snapshot.volumes:
        if volume.role != "downloads":
            continue
        free = volume.usage.free_bytes
        if volume.level >= StorageLevel.STOP:
            found.append(
                Finding(
                    "error", "The disk is almost full", f"{format_size(free)} free: downloads stop."
                )
            )
        elif volume.level >= StorageLevel.PAUSE:
            found.append(
                Finding(
                    "warning",
                    "The disk is nearly full",
                    f"{format_size(free)} free: downloads wait.",
                )
            )
        elif volume.level >= StorageLevel.LOW:
            found.append(Finding("warning", "Free space is low", f"{format_size(free)} free."))
        if snapshot.reserved_bytes and snapshot.reserved_bytes > free:
            found.append(
                Finding(
                    "error",
                    "Running downloads may not fit",
                    f"They still have to write {format_size(snapshot.reserved_bytes)} "
                    f"but only {format_size(free)} is free.",
                )
            )
    old = [w for w in workspaces if w.safe_to_remove and w.age_days >= ABANDONED_DAYS]
    if old:
        total = sum(w.size_bytes for w in old)
        found.append(
            Finding(
                "info",
                f"{len(old)} abandoned working folder(s)",
                f"They hold {format_size(total)}. Run: rayohx storage clean",
            )
        )
    if snapshot.incomplete_bytes and not old:
        found.append(
            Finding(
                "info",
                "Unfinished downloads hold space",
                f"{format_size(snapshot.incomplete_bytes)} in working folders of downloads "
                "that are not finished.",
            )
        )
    if not snapshot.policy.active:
        found.append(
            Finding(
                "info",
                "No low-space thresholds are set",
                "Set them with: rayohx storage policy --warn 20G --pause 10G --stop 5G",
            )
        )
    return found
