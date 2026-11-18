"""Metadata: what a stream says about its media, and what is written into the output file."""

from rayohx.metadata.extract import extract_metadata
from rayohx.metadata.model import Chapter, MetadataInfo
from rayohx.metadata.policy import effective_metadata

__all__ = ["Chapter", "MetadataInfo", "effective_metadata", "extract_metadata"]
