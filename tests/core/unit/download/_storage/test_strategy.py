import pytest

from rayohx.download._storage import (
    choose_strategy,
    validate_strategy,
)
from rayohx.errors import ConfigurationError
from tests.helpers.storage import S


def test_auto_writes_straight_to_a_file_or_streams() -> None:
    assert choose_strategy(S.AUTO, sink_supports_resume=True) is S.DIRECT
    assert choose_strategy(S.AUTO, sink_supports_resume=False) is S.STREAMING
    for explicit in (S.TEMPORARY, S.HYBRID, S.BUFFERED, S.DIRECT, S.STREAMING):
        assert choose_strategy(explicit, sink_supports_resume=True) is explicit


def test_direct_needs_a_resumable_file() -> None:
    validate_strategy(S.DIRECT, sink_supports_resume=True)
    validate_strategy(S.STREAMING, sink_supports_resume=False)
    with pytest.raises(ConfigurationError, match="DIRECT"):
        validate_strategy(S.DIRECT, sink_supports_resume=False)
