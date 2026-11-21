#!/usr/bin/env python3
"""Build the window's installer: a Windows setup.

What is specific to the window is here: its metadata (packages/ui/installer/projectinfo.py) and
the frontend build. The rest is shared (scripts/build_installer.py).

    uv sync --group installer
    uv run python packages/ui/scripts/build_installer.py [--sync] [--build-frontend] [--smoke]

The installer is written to dist/installer/. See docs/packaging.md in this package.
"""

import argparse
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]  # packages/ui
ROOT = PACKAGE.parents[1]
# The shared build_installer.py, not this file (they have the same name).
sys.path.insert(0, str(ROOT / "scripts"))
import build_installer as shared  # noqa: E402

INSTALLER = PACKAGE / "installer"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--build-frontend", action="store_true", help="run npm ci && npm run build first"
    )


def prepare(args: argparse.Namespace) -> None:
    """Build the frontend, which the window's build freezes in."""
    if not args.build_frontend:
        return
    info = shared.load_module("ui_projectinfo", INSTALLER / "projectinfo.py").load()
    frontend = info.frontend_dir
    npm = "npm.cmd" if shared.WINDOWS else "npm"
    shared.run([npm, "ci"], cwd=frontend)
    shared.run([npm, "run", "build"], cwd=frontend)


def product() -> shared.Product:
    info = shared.load_module("ui_projectinfo", INSTALLER / "projectinfo.py").load()
    return shared.Product(
        key="ui",
        meta=shared.Meta(
            info.project,
            info.script,
            info.version,
            info.title,
            info.publisher,
            info.install_dir,
        ),
        spec=INSTALLER / "pyinstaller" / "ui.spec",
        nsi=INSTALLER / "windows" / "ui.nsi",
        licence=PACKAGE / "LICENSE",
        smoke=((PACKAGE, "tests/integration/test_frozen_ui.py"),),
        add_arguments=add_arguments,
        prepare=prepare,
    )


if __name__ == "__main__":
    shared.main(product())
