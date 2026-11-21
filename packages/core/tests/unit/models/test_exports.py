"""The model packages hand their names out on first use; these tests keep that honest."""

import importlib
import subprocess
import sys
from types import ModuleType

import pytest

PACKAGES = [
    "rayohx.models",
    "rayohx.models.download",
    "rayohx.models.playlist",
    "rayohx.models.playlist.tracks",
    "rayohx.models.segment",
]


def package(name: str) -> ModuleType:
    return importlib.import_module(name)


def run_isolated(code: str) -> None:
    """Run ``code`` in a fresh interpreter, so what is already imported cannot hide a problem."""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", PACKAGES)
def test_every_public_name_can_be_reached_and_is_listed(name: str) -> None:
    module = package(name)
    assert module.__all__
    for public in module.__all__:
        assert getattr(module, public) is not None
        assert public in dir(module)


@pytest.mark.parametrize("name", PACKAGES)
def test_a_star_import_brings_in_every_public_name(name: str) -> None:
    namespace: dict[str, object] = {}
    exec(f"from {name} import *", namespace)  # noqa: S102 - a fixed, trusted statement
    assert set(package(name).__all__) <= set(namespace)


@pytest.mark.parametrize("name", PACKAGES)
def test_a_name_that_does_not_exist_is_an_attribute_error(name: str) -> None:
    with pytest.raises(AttributeError, match="no attribute 'Nope'"):
        getattr(package(name), "Nope")  # noqa: B009 - the lookup is the point of the test


def test_the_models_package_hands_out_the_same_classes_as_its_subpackages() -> None:
    models = package("rayohx.models")
    for sub in ("download", "playlist", "segment"):
        subpackage = package(f"rayohx.models.{sub}")
        for public in subpackage.__all__:
            assert getattr(models, public) is getattr(subpackage, public)


def test_every_name_of_the_subpackages_is_also_listed_by_the_models_package() -> None:
    listed = set(package("rayohx.models").__all__)
    for sub in ("download", "playlist", "segment"):
        assert set(package(f"rayohx.models.{sub}").__all__) <= listed


def test_the_playlist_alias_is_either_kind_of_playlist() -> None:
    models = package("rayohx.models")
    assert models.Playlist == models.MasterPlaylist | models.MediaPlaylist
    assert models.Playlist is package("rayohx.models.playlist").Playlist


def test_importing_the_models_package_loads_no_model_module() -> None:
    run_isolated(
        "import sys\n"
        "import rayohx.models\n"
        "loaded = [m for m in sys.modules if m.startswith('rayohx.models.') and m.count('.') > 2]\n"
        "assert not loaded, loaded\n"
    )


def test_a_name_loads_only_the_module_it_lives_in() -> None:
    run_isolated(
        "import sys\n"
        "import rayohx.models as models\n"
        "models.SegmentRange\n"
        "assert 'rayohx.models.segment.range' in sys.modules\n"
        "for other in ('rayohx.models.segment.segment', 'rayohx.models.playlist.master',\n"
        "              'rayohx.models.download.request', 'rayohx.models.download.result'):\n"
        "    assert other not in sys.modules, other\n"
    )
