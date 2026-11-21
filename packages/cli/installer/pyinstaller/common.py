"""Used by cli.spec: where the command line's names, version, icon and dependencies come from.

Everything is read from packages/cli (see ../projectinfo.py), so renaming the command line needs no
edit here. The window has its own, in packages/ui/installer/pyinstaller/common.py.
"""

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projectinfo

INFO = projectinfo.load()
ICON_SOURCE = next(iter(sorted((INFO.root / "brand" / "light").glob("*.ico"))), None)
CLI_SCRIPT = INFO.script
WINDOWS = sys.platform == "win32"

# The command line imports neither the API nor the window, nor the libraries they need.
EXCLUDES = [
    "tkinter",
    "pytest",
    "rayohx_api",
    "rayohx_ui",
    "cornea",
    "webview",
    "fastapi",
    "uvicorn",
]


class Collected:
    """Data files, native libraries and hidden imports gathered for the executable."""

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


def dependencies() -> Collected:
    """What the command line needs."""
    collected = Collected()
    collected.datas.extend(copy_metadata(INFO.project["name"]))
    collected.hiddenimports.extend(collect_submodules(INFO.core_package))
    collected.hiddenimports.extend(collect_submodules(INFO.package))
    # rich lazily imports a Unicode-version-specific submodule that static analysis cannot see.
    collected.package("rich")
    collected.package("typer")
    return collected


def _entry_script() -> str:
    """Write the small script PyInstaller freezes for the console script of pyproject.toml."""
    module, function = INFO.entry_point.split(":")
    path = Path(CONF["workpath"]) / f"entry_{CLI_SCRIPT}.py"
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


def _version_info() -> Any:
    """Windows file properties (Explorer > Properties > Details) built from the project metadata."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numbers = [int(n) for n in re.findall(r"\d+", INFO.version)[:4]]
    version = tuple(numbers + [0] * (4 - len(numbers)))
    author = (INFO.project.get("authors") or [{}])[0].get("name", "")
    strings = {
        "CompanyName": author,
        "FileDescription": INFO.project.get("description", INFO.title),
        "FileVersion": INFO.version,
        "ProductName": INFO.title,
        "ProductVersion": INFO.version,
        "LegalCopyright": f"Apache License 2.0. {author}".strip(),
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


def executable(collected: Collected) -> tuple[Analysis, EXE]:
    """Analyse the console script and describe its executable."""
    analysis = Analysis(
        [_entry_script()],
        pathex=[str(INFO.cli_dir / "src")],
        binaries=collected.binaries,
        datas=collected.datas,
        hiddenimports=collected.hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=EXCLUDES,
        noarchive=False,
    )
    exe = EXE(
        PYZ(analysis.pure),
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=CLI_SCRIPT,
        console=True,
        icon=str(ICON_SOURCE) if WINDOWS and ICON_SOURCE else None,
        version=_version_info() if WINDOWS else None,
        upx=False,
        # Everything but the executable goes in lib/ (COLLECT follows the EXE).
        contents_directory="lib",
    )
    return analysis, exe
