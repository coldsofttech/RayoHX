"""Deciding what to write: the stream's information, shaped by the metadata policy."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from rayohx.enums import MetadataPolicy
from rayohx.metadata.model import MetadataInfo

if TYPE_CHECKING:
    from rayohx.config.metadata import MetadataConfig


def effective_metadata(info: MetadataInfo, config: MetadataConfig) -> MetadataInfo:
    """What to write, given what the stream says (``info``) and the settings.

    * ``none``: nothing.
    * ``minimal``: the title and the language.
    * ``preserve``: everything the stream gave, minus the chapters or the artwork if switched off.
    * ``custom``: only what the settings themselves give.

    Whatever the settings give (``title``, ``description``, ``language``) replaces the stream's
    own value, under every policy except ``none``.
    """
    policy = config.policy
    if policy is MetadataPolicy.NONE:
        return MetadataInfo()
    if policy is MetadataPolicy.MINIMAL:
        chosen = MetadataInfo(title=info.title, language=info.language)
    elif policy is MetadataPolicy.PRESERVE:
        chosen = dataclasses.replace(
            info,
            chapters=info.chapters if config.chapters else (),
            artwork_url=info.artwork_url if config.artwork else None,
        )
    else:
        chosen = MetadataInfo()
    return dataclasses.replace(
        chosen,
        title=config.title or chosen.title,
        description=config.description or chosen.description,
        language=config.language or chosen.language,
    )
