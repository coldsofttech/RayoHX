from typing import Any

import pytest
from pydantic import ValidationError

from rayohx_api.schemas.v1 import Limits, SettingsUpdate, SettingsView


def _view(**overrides: Any) -> SettingsView:
    data: dict[str, Any] = {
        "download_dir": "d",
        "max_active_downloads": 2,
        "allow_local_paths": False,
        "concurrency": 8,
        "limits": {"min_concurrency": 1, "max_concurrency": 64},
        "version": "1",
    }
    return SettingsView(**{**data, **overrides})


def test_view_defaults() -> None:
    view = _view()
    assert view.quality == "best"
    assert view.overwrite is False


@pytest.mark.parametrize("concurrency", [0, 65])
def test_view_rejects_concurrency_out_of_range(concurrency: int) -> None:
    with pytest.raises(ValidationError):
        _view(concurrency=concurrency)


def test_update_is_all_optional() -> None:
    assert SettingsUpdate().model_dump(exclude_unset=True) == {}
    update = SettingsUpdate(concurrency=64, quality="720p", overwrite=True)
    assert update.model_dump(exclude_none=True) == {
        "concurrency": 64,
        "quality": "720p",
        "overwrite": True,
    }


@pytest.mark.parametrize("overrides", [{"concurrency": 0}, {"concurrency": 65}, {"quality": "x"}])
def test_update_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SettingsUpdate(**overrides)


def test_limits_are_required_on_the_view() -> None:
    with pytest.raises(ValidationError):
        SettingsView(
            download_dir="d",
            max_active_downloads=2,
            allow_local_paths=False,
            concurrency=4,
            version="1",
        )  # type: ignore[call-arg]
    assert Limits(min_concurrency=1, max_concurrency=64).max_concurrency == 64


def test_concurrency_range_comes_from_the_engine() -> None:
    from rayohx.config.download import MAX_CONCURRENCY

    assert SettingsUpdate(concurrency=MAX_CONCURRENCY).concurrency == MAX_CONCURRENCY
    with pytest.raises(ValidationError):
        SettingsUpdate(concurrency=MAX_CONCURRENCY + 1)
