"""Errors raised by the platform."""

from typing import ClassVar

from rayohx.enums import ErrorCategory
from rayohx.errors import RayoHXError


class PersistenceError(RayoHXError):
    """The platform's database could not be used."""

    error_code: ClassVar[str] = "PERSISTENCE_ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.INTERNAL


class SchemaTooNewError(PersistenceError):
    """The database was written by a newer RayoHX than this one."""

    error_code: ClassVar[str] = "PERSISTENCE_SCHEMA_TOO_NEW"

    def __init__(self, found: int, supported: int) -> None:
        self.found = found
        self.supported = supported
        super().__init__(
            f"The database uses schema version {found}, but this RayoHX understands up to "
            f"{supported}.",
            hint="Update RayoHX. The database was not changed.",
        )


class QueueError(RayoHXError):
    """The queue could not do what was asked."""

    error_code: ClassVar[str] = "QUEUE_ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.INTERNAL


class RunnerLockedError(QueueError):
    """Another process is already running the queue for this data folder."""

    error_code: ClassVar[str] = "QUEUE_RUNNER_LOCKED"

    def __init__(self) -> None:
        super().__init__(
            "Another RayoHX process is already running the queue.",
            hint="Only one process runs downloads at a time. Control it with the same commands, "
            "or stop it first.",
        )
