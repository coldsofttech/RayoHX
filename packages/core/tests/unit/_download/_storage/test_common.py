import errno

from rayohx._download._storage import DEFAULT_SPILL_BYTES, translate_os_error
from rayohx.errors import InsufficientStorageError, OutputError


def test_the_default_spill_limit_is_one_gibibyte() -> None:
    assert DEFAULT_SPILL_BYTES == 1024**3


def test_a_full_disk_is_recognised_by_its_error_number() -> None:
    error = translate_os_error(OSError(errno.ENOSPC, "No space left on device"), "out/video.mp4")
    assert isinstance(error, InsufficientStorageError)
    assert "out/video.mp4" in error.message
    assert error.hint


def test_a_full_disk_is_recognised_by_the_windows_error_code() -> None:
    exc = OSError(0, "There is not enough space on the disk")
    exc.winerror = 112
    assert isinstance(translate_os_error(exc, "video.mp4"), InsufficientStorageError)


def test_another_failed_write_is_an_output_error_that_names_the_file() -> None:
    error = translate_os_error(OSError(errno.EACCES, "Permission denied"), "out/video.mp4")
    assert type(error) is OutputError
    assert "out/video.mp4" in error.message
    assert "Permission denied" in error.message


def test_an_error_without_a_system_message_is_shown_as_it_is() -> None:
    error = translate_os_error(OSError("something odd"), "video.mp4")
    assert type(error) is OutputError
    assert "something odd" in error.message
