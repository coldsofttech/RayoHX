#!/usr/bin/env python3
"""Build the command line's installers: a Windows setup and zip, or Linux deb and rpm packages.

What is specific to the command line is here: its metadata (packages/cli/installer/projectinfo.py),
the portable zip and the nfpm packages. The rest is shared (scripts/build_installer.py).

    uv sync --group installer
    uv run python packages/cli/scripts/build_installer.py [--sync] [--format exe,deb,rpm] [--smoke]

The installers are written to dist/installer/. See packages/cli/docs/packaging.md.
"""

import functools
import os
import platform
import shlex
import shutil
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]  # packages/cli
# The shared build_installer.py, not this file (they have the same name).
sys.path.insert(0, str(PACKAGE.parents[1] / "scripts"))
import build_installer as shared  # noqa: E402

INSTALLER = PACKAGE / "installer"
NFPM_CONFIG = INSTALLER / "linux" / "nfpm.yaml"


def package_zip(product: shared.Product, folder: Path) -> Path:
    """The command line as a portable zip (what the Scoop manifest installs)."""
    shared.OUT.mkdir(parents=True, exist_ok=True)
    meta = product.meta
    target = shared.OUT / f"{meta.name}-{meta.version}-windows-x64"
    return Path(shutil.make_archive(str(target), "zip", root_dir=folder))


def package_linux(
    product: shared.Product, folder: Path, formats: list[str], jobs: int
) -> list[Path]:
    """Build the deb and rpm packages of the command line."""
    shared.normalise_modes(folder)
    shared.OUT.mkdir(parents=True, exist_ok=True)
    machine = platform.machine().lower()
    meta = product.meta
    who = shared.author(meta)
    maintainer = who.get("name", "")
    if who.get("email"):
        maintainer = f"{maintainer} <{who['email']}>"
    urls = meta.project.get("urls") or {}
    env = {
        **os.environ,
        "PKG_NAME": meta.name,
        "PKG_VERSION": meta.version,
        "PKG_ARCH": {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64"}.get(machine, machine),
        "PKG_DESCRIPTION": str(meta.project.get("description", meta.name)),
        "PKG_MAINTAINER": maintainer,
        "PKG_HOMEPAGE": str(urls.get("Homepage", "")),  # type: ignore[attr-defined]
        "PKG_LICENSE": str(meta.project.get("license", "")),
        "PKG_SOURCE_DIR": str(folder),
        "PKG_LICENSE_FILE": str(product.licence),
        "PKG_ICON_DIR": str(shared.brand_png_dir()),
    }
    nfpm = shlex.split(os.environ.get("NFPM", "nfpm"))
    if shutil.which(nfpm[0]) is None:
        raise SystemExit(
            "nfpm not found. Install it (version in installer/tools.toml) or set NFPM."
        )
    before = set(shared.OUT.iterdir())

    def package(packager: str) -> None:
        shared.run(
            [*nfpm, "package", "--config", str(NFPM_CONFIG), "--packager", packager,
             "--target", str(shared.OUT)],
            env=env,
        )  # fmt: skip

    shared.run_parallel([functools.partial(package, packager) for packager in formats], jobs)
    return sorted(set(shared.OUT.iterdir()) - before)


def product() -> shared.Product:
    info = shared.load_module("cli_projectinfo", INSTALLER / "projectinfo.py").load()
    return shared.Product(
        key="cli",
        meta=shared.Meta(
            info.project, info.script, info.version, info.title, info.publisher, info.install_dir
        ),
        spec=INSTALLER / "pyinstaller" / "cli.spec",
        nsi=INSTALLER / "windows" / "cli.nsi",
        licence=PACKAGE / "LICENSE",
        smoke=((PACKAGE, "tests/integration/test_frozen_cli.py"),),
        linux_formats=("deb", "rpm"),
        package_linux=package_linux,
        windows_extras=(package_zip,),
    )


if __name__ == "__main__":
    shared.main(product())
