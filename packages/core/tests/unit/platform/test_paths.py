from pathlib import Path

from rayohx.platform.paths import PORTABLE_FOLDER, PORTABLE_MARKER, resolve_paths


def test_rayohx_home_puts_everything_under_one_folder(tmp_path: Path) -> None:
    paths = resolve_paths({"RAYOHX_HOME": str(tmp_path)})
    assert paths.source == "home"
    assert paths.config_dir == tmp_path / "config"
    assert paths.data_dir == tmp_path / "data"
    assert paths.cache_dir == tmp_path / "cache"
    assert paths.database_path == tmp_path / "data" / "rayohx.db"
    assert not paths.portable


def test_a_marker_beside_a_frozen_program_means_portable(tmp_path: Path) -> None:
    (tmp_path / PORTABLE_MARKER).write_text("", encoding="utf-8")
    paths = resolve_paths({}, executable=tmp_path / "rayohx.exe", frozen=True)
    assert paths.portable
    assert paths.data_dir == tmp_path / PORTABLE_FOLDER / "data"


def test_the_marker_is_ignored_when_not_frozen(tmp_path: Path) -> None:
    (tmp_path / PORTABLE_MARKER).write_text("", encoding="utf-8")
    paths = resolve_paths(
        {"XDG_DATA_HOME": str(tmp_path / "x")}, executable=tmp_path / "py", frozen=False
    )
    assert not paths.portable


def test_no_marker_means_the_user_folders(tmp_path: Path) -> None:
    paths = resolve_paths(
        {
            "XDG_CONFIG_HOME": str(tmp_path / "c"),
            "XDG_DATA_HOME": str(tmp_path / "d"),
            "XDG_CACHE_HOME": str(tmp_path / "k"),
            "APPDATA": str(tmp_path / "c"),
            "LOCALAPPDATA": str(tmp_path / "d"),
        },
        executable=tmp_path / "rayohx",
        frozen=True,
    )
    assert paths.source == "user"
    assert paths.config_dir.name == "rayohx"
    assert tmp_path in paths.data_dir.parents


def test_home_beats_portable(tmp_path: Path) -> None:
    (tmp_path / PORTABLE_MARKER).write_text("", encoding="utf-8")
    other = tmp_path / "other"
    paths = resolve_paths({"RAYOHX_HOME": str(other)}, executable=tmp_path / "r", frozen=True)
    assert paths.source == "home"


def test_ensure_creates_the_folders(tmp_path: Path) -> None:
    paths = resolve_paths({"RAYOHX_HOME": str(tmp_path / "h")})
    assert not paths.data_dir.exists()
    paths.ensure()
    assert paths.config_dir.is_dir()
    assert paths.data_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.backups_dir.parent == paths.data_dir
