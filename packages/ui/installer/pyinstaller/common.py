"""Used by ui.spec: where the window's names, version, icon and dependencies come from.

The window is built together with the command line (the build folder holds both executables).
Everything is read from packages/ui and packages/cli (see ../projectinfo.py and the command line's
own), so renaming either needs no edit here.

- executable names: the ``[project.gui-scripts]`` key of the window and the ``[project.scripts]``
  key of the command line (the entry scripts are generated from their targets)
- version and title: the window's from ``[project]`` and ``TITLE``, the command line's likewise
- icon: the ``.ico`` in ``brand/light``
- description and author: ``[project]`` of each package
"""

import importlib.util
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> ModuleType:
    """Import a projectinfo.py by path; the window's and the command line's share a file name."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UI = _load("ui_projectinfo", HERE.parent / "projectinfo.py").load()
CLI = _load("cli_projectinfo", UI.root / "packages" / "cli" / "installer" / "projectinfo.py").load()
REPO_ROOT = UI.root
UI_DIR = UI.frontend_dir
ICON_SOURCE = next(iter(sorted((REPO_ROOT / "brand" / "light").glob("*.ico"))), None)

CLI_SCRIPT, UI_SCRIPT = CLI.script, UI.script
#: Per executable: (entry point "module:function", pyproject [project], version, title).
PROGRAMS: dict[str, tuple[str, dict[str, Any], str, str]] = {
    CLI.script: (CLI.entry_point, CLI.project, CLI.version, CLI.title),
    UI.script: (UI.entry_point, UI.project, UI.version, UI.title),
}
WINDOWS = sys.platform == "win32"

# Not part of any program.
EXCLUDES = ["tkinter", "pytest"]
# The command line imports neither the API nor the window.
CLI_EXCLUDES = [
    *EXCLUDES,
    UI.api_package,
    UI.package,
    "cornea",
    "webview",
    "fastapi",
    "uvicorn",
]


class Collected:
    """Data files, native libraries and hidden imports gathered for one executable."""

    def __init__(self) -> None:
        self.datas: list[Any] = []
        self.binaries: list[Any] = []
        self.hiddenimports: list[str] = []

    def package(self, name: str) -> None:
        """Collect a package whole: code, data files, native libraries and submodules."""
        if importlib.util.find_spec(name) is None:
            return
        datas, binaries, hidden = collect_all(name)
        self.datas.extend(datas)
        self.binaries.extend(binaries)
        self.hiddenimports.extend(hidden)

    def metadata(self, *distributions: str) -> None:
        """Keep the package metadata that ``importlib.metadata`` reads at run time."""
        for distribution in distributions:
            self.datas.extend(copy_metadata(distribution))


def cli_dependencies() -> Collected:
    """What the command line needs. The window's build includes these too."""
    collected = Collected()
    collected.metadata(CLI.project["name"])
    collected.hiddenimports.extend(collect_submodules(CLI.core_package))
    collected.hiddenimports.extend(collect_submodules(CLI.package))
    # rich lazily imports a Unicode-version-specific submodule that static analysis cannot see.
    collected.package("rich")
    collected.package("typer")
    return collected


def ui_dependencies() -> Collected:
    """What the window needs, on top of the command line's. Windows only.

    Cornea serves the frontend and the API with uvicorn, FastAPI and Starlette, which load protocol
    and middleware modules by name; pywebview reaches WebView2 through pythonnet and clr_loader.
    """
    if not WINDOWS or importlib.util.find_spec("cornea") is None:
        raise SystemExit("The UI build needs Windows and cornea-shell (uv sync --group installer).")
    if not (UI_DIR / "dist" / "index.html").is_file():
        raise SystemExit(f"Build the frontend first: npm ci && npm run build in {UI_DIR}")
    collected = Collected()
    collected.metadata(
        UI.project["name"],
        "cornea-shell",
        "pywebview",
        "fastapi",
        "starlette",
        "uvicorn",
        "pydantic",
        "pydantic-settings",
    )
    for package in (
        "cornea", "webview", "clr_loader", "pythonnet", "proxy_tools", "bottle", "uvicorn",
        "fastapi", "starlette", "pydantic", "pydantic_settings", "pydantic_core", "anyio", "h11",
    ):  # fmt: skip
        collected.package(package)
    collected.hiddenimports.extend(collect_submodules(UI.api_package))
    collected.hiddenimports.extend(collect_submodules(UI.package))
    # The window finds the bundle through its package (Static(package=<ui package>, ...)).
    collected.datas.append((str(UI_DIR / "dist"), f"{UI.package}/ui/dist"))
    return collected


def _entry_script(script: str) -> str:
    """Write the small script PyInstaller freezes for one program of the build."""
    module, function = PROGRAMS[script][0].split(":")
    path = Path(CONF["workpath"]) / f"entry_{script}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import multiprocessing\n"
        f"from {module} import {function}\n\n"
        'if __name__ == "__main__":\n'
        "    multiprocessing.freeze_support()\n"
        f"    raise SystemExit({function}())\n",
        encoding="utf-8",
    )
    return str(path)


def _version_info(script: str) -> Any:
    """Windows file properties (Explorer > Properties > Details) of one program."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    _, project, version_text, title = PROGRAMS[script]
    numbers = [int(n) for n in re.findall(r"\d+", version_text)[:4]]
    version = tuple(numbers + [0] * (4 - len(numbers)))
    author = (project.get("authors") or [{}])[0].get("name", "")
    strings = {
        "CompanyName": author,
        "FileDescription": project.get("description", title),
        "FileVersion": version_text,
        "ProductName": title,
        "ProductVersion": version_text,
        "LegalCopyright": f"MIT License. {author}".strip(),
    }
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=version,
            prodvers=version,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [StringTable("040904B0", [StringStruct(k, v) for k, v in strings.items()])]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


def executable(
    script: str,
    collected: Collected,
    shared: Iterable[Collected] = (),
    excludes: Sequence[str] = (),
    *,
    console: bool = True,
) -> tuple[Analysis, EXE]:
    """Analyse one program and describe its executable.

    ``shared`` are extra collections added to this executable only (the window's, for example);
    each executable carries its own pure-Python modules, and the build folder shares one ``lib/``.
    """
    parts = [collected, *shared]
    analysis = Analysis(
        [_entry_script(script)],
        pathex=[str(UI.ui_dir / "src"), str(CLI.cli_dir / "src")],
        binaries=[item for part in parts for item in part.binaries],
        datas=[item for part in parts for item in part.datas],
        hiddenimports=[item for part in parts for item in part.hiddenimports],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=list(excludes),
        noarchive=False,
    )
    exe = EXE(
        PYZ(analysis.pure),
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=script,
        console=console,
        icon=str(ICON_SOURCE) if WINDOWS and ICON_SOURCE else None,
        version=_version_info(script) if WINDOWS else None,
        upx=False,
        # Everything but the executables goes in lib/ (COLLECT follows the EXE).
        contents_directory="lib",
    )
    return analysis, exe
