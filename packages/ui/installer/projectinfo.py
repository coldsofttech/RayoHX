#!/usr/bin/env python3
"""The names the window's installer files and scripts need, read from its pyproject.toml.

Nothing here imports the project, so it runs before anything is installed. Renaming the window
means changing packages/ui/pyproject.toml and the code; the installer follows.

What is read:

- ``[project.gui-scripts]`` gives the executable name (its one key) and the function it runs
- ``[project] version`` is the version (the window has no ``__version__`` of its own)
- ``[tool.installer] api-package`` is the import name of the API package the window hosts
- ``[tool.installer]`` also gives the ``publisher`` and the ``install-dir`` (the setup's folder)
- the title is ``TITLE`` in ``<ui package>/app.py``
- the frontend lives in ``src/<ui package>/ui``
- description, author and homepage come from ``[project]``

Usage: ``python packages/ui/installer/projectinfo.py github`` adds the values to ``GITHUB_ENV``
(``UI_DIR``, ``UI_NAME``, ...); with no argument it prints them.
"""

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

UI_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class UiInfo:
    root: Path  # the repository
    ui_dir: Path  # packages/ui
    project: dict[str, Any]
    script: str  # executable name, the [project.gui-scripts] key
    entry_point: str  # "module:function" the executable runs
    package: str  # import name of the window
    api_package: str
    version: str
    title: str
    publisher: str
    install_dir: str

    @property
    def frontend_dir(self) -> Path:
        return self.ui_dir / "src" / self.package / "ui"

    def values(self) -> dict[str, str]:
        return {
            "UI_DIR": self.frontend_dir.relative_to(self.root).as_posix(),
            "UI_NAME": self.script,
            "UI_PACKAGE": self.package,
            "API_PACKAGE": self.api_package,
            "UI_VERSION": self.version,
            "UI_TITLE": self.title,
            "PUBLISHER": self.publisher,
            "INSTALL_DIR": self.install_dir.replace("/", "\\"),
        }


def _read(path: Path, pattern: str, what: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit(f"{what} not found in {path}")
    return match.group(1)


def load(ui_dir: Path = UI_DIR) -> UiInfo:
    pyproject = ui_dir / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project: dict[str, Any] = data["project"]
    settings = data.get("tool", {}).get("installer", {})
    scripts: dict[str, str] = project.get("gui-scripts", {})
    if len(scripts) != 1:
        raise SystemExit(f"{pyproject} needs exactly one [project.gui-scripts] entry.")
    try:
        api = settings["api-package"]
    except KeyError:
        raise SystemExit(f"{pyproject} needs [tool.installer] api-package.") from None
    try:
        publisher, install_dir = settings["publisher"], settings["install-dir"]
    except KeyError:
        raise SystemExit(f"{pyproject} needs [tool.installer] publisher, install-dir.") from None
    ((script, target),) = scripts.items()
    package = target.split(":")[0].split(".")[0]
    return UiInfo(
        root=ui_dir.parents[1],
        ui_dir=ui_dir,
        project=project,
        script=script,
        entry_point=target,
        package=package,
        api_package=api,
        version=project["version"],
        title=_read(ui_dir / "src" / package / "app.py", r'^TITLE\s*=\s*"([^"]+)"', "TITLE"),
        publisher=publisher,
        install_dir=install_dir,
    )


def main() -> None:
    values = load().values()
    if sys.argv[1:] == ["github"]:
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
            env.write("".join(f"{key}={value}\n" for key, value in values.items()))
    sys.stdout.write("".join(f"{key}={value}\n" for key, value in values.items()))


if __name__ == "__main__":
    main()
