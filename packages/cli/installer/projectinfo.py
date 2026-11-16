#!/usr/bin/env python3
"""The names the command line's installer files and scripts need, read from its pyproject.toml.

Nothing here imports the project, so it runs before anything is installed. Renaming the command
line means changing packages/cli/pyproject.toml and the code; the installer follows.

What is read:

- ``[project.scripts]`` gives the executable name (its one key) and the function it runs
- ``[tool.installer]`` gives the product ``title``, the ``publisher`` and the ``install-dir`` (the
  folder under Program Files, with ``/`` between the parts) and the ``core-package`` it uses
- ``__version__`` comes from the command line package's ``__init__.py``
- description, author, license and homepage come from ``[project]``

Usage: ``python packages/cli/installer/projectinfo.py github`` adds the values to ``GITHUB_ENV``
(``CLI_NAME``, ``APP_VERSION``, ...); with no argument it prints them.
"""

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLI_DIR = Path(__file__).resolve().parents[1]
ROOT = CLI_DIR.parents[1]


@dataclass(frozen=True)
class CliInfo:
    root: Path
    cli_dir: Path
    project: dict[str, Any]
    script: str  # executable name, the [project.scripts] key
    module: str  # module holding the Typer app and the function to run
    package: str  # import name of the command line
    core_package: str
    title: str
    publisher: str
    install_dir: str
    version: str

    @property
    def entry_point(self) -> str:
        return self.project["scripts"][self.script]

    def values(self) -> dict[str, str]:
        return {
            "CLI_NAME": self.script,
            "CLI_MODULE": self.module,
            "CLI_PACKAGE": self.package,
            "CORE_PACKAGE": self.core_package,
            "APP_VERSION": self.version,
            "APP_TITLE": self.title,
            "PUBLISHER": self.publisher,
            "INSTALL_DIR": self.install_dir.replace("/", "\\"),
        }


def load(cli_dir: Path = CLI_DIR) -> CliInfo:
    data = tomllib.loads((cli_dir / "pyproject.toml").read_text(encoding="utf-8"))
    project: dict[str, Any] = data["project"]
    settings = data.get("tool", {}).get("installer", {})
    scripts: dict[str, str] = project.get("scripts", {})
    if len(scripts) != 1:
        raise SystemExit(f"{cli_dir / 'pyproject.toml'} needs exactly one [project.scripts] entry.")
    try:
        title, core = settings["title"], settings["core-package"]
        publisher, install_dir = settings["publisher"], settings["install-dir"]
    except KeyError as missing:
        raise SystemExit(
            f"{cli_dir / 'pyproject.toml'} needs [tool.installer] title, publisher, install-dir "
            f"and core-package ({missing} is missing)."
        ) from None
    ((script, target),) = scripts.items()
    module = target.split(":")[0]
    package = module.split(".")[0]
    version_file = cli_dir / "src" / package / "__init__.py"
    text = version_file.read_text("utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit(f"__version__ not found in {version_file}")
    return CliInfo(
        root=cli_dir.parents[1],
        cli_dir=cli_dir,
        project=project,
        script=script,
        module=module,
        package=package,
        core_package=core,
        title=title,
        publisher=publisher,
        install_dir=install_dir,
        version=match.group(1),
    )


def main() -> None:
    values = load().values()
    if sys.argv[1:] == ["github"]:
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
            env.write("".join(f"{key}={value}\n" for key, value in values.items()))
    sys.stdout.write("".join(f"{key}={value}\n" for key, value in values.items()))


if __name__ == "__main__":
    main()
