"""Safe file names, from text and from web addresses."""

from rayohx._download._output._names import MAX_NAME_LENGTH, name_from_url, sanitize_filename

__all__ = ["MAX_NAME_LENGTH", "name_from_url", "sanitize_filename"]
