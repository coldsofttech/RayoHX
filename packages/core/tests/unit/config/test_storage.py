from pathlib import Path

import pytest

from rayohx.config import StorageConfig
from rayohx.errors import ConfigurationError


def test_storage_validation() -> None:
    with pytest.raises(ConfigurationError):
        StorageConfig(buffer_bytes=0)
    with pytest.raises(ConfigurationError):
        StorageConfig(max_temp_bytes=0)
    with pytest.raises(ConfigurationError):
        StorageConfig(reserve_bytes=-1)
    assert StorageConfig(workspace_dir=Path("/w")).as_dict()["workspace_dir"] == str(Path("/w"))
