#!/usr/bin/env python3
"""What the installer build scripts share: PyInstaller, NSIS, signing, branding and the driver.

Do not run this file. Each product has a script of its own that describes the product and hands it
to ``main`` here, so nothing is written twice:

    packages/cli/scripts/build_installer.py   the command line (Windows setup, Linux deb and rpm)
    packages/ui/scripts/build_installer.py    the window with the command line (Windows setup)

    uv sync --group installer
    uv run python packages/cli/scripts/build_installer.py [--sync] [--format exe,deb,rpm] [--smoke]
    uv run python packages/ui/scripts/build_installer.py [--sync] [--build-frontend] [--smoke]

Everything comes from the products' own metadata, so renaming a product needs no edit here. Icon
and setup art come from brand/. Tool versions are pinned in installer/tools.toml. The installers
are written to dist/installer/. See packages/cli/docs/packaging.md and packages/ui/docs/packaging.md for the details.

Signing is off by default. Set SIGN_COMMAND to a command that signs one file, with {file} where
its path goes (for example a signtool or SignPath call); the executables and then each setup.exe
are signed. Nothing in this script is tied to one provider.
"""

import argparse
import functools
import importlib.util
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TypeVar

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "installer"
WORK = ROOT / "build" / "installer-work"
OUT = ROOT / "dist" / "installer"
NSIS_DIR = ROOT / "installer" / "windows" / "nsis"
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
FORMATS = ("exe", "deb", "rpm")
T = TypeVar("T")


def load_module(name: str, path: Path) -> ModuleType:
    """Import a projectinfo.py by path; the products' share a file name."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Meta:
    """What one product's installers are built from."""

    project: dict[str, object]
    name: str  # executable and package name
    version: str
    title: str  # product name
    publisher: str = ""  # shown in Apps & features; the first author when empty
    install_dir: str = ""  # folder under Program Files, "/" between parts; the title when empty


@dataclass(frozen=True)
class Product:
    """One product's installer: what is specific to it. ``main`` does the rest."""

    key: str  # short id, names the work folder
    meta: Meta
    spec: Path  # the PyInstaller spec
    nsi: Path  # the NSIS script
    licence: Path
    smoke: tuple[tuple[Path, str], ...] = ()  # (folder to run pytest in, test file) pairs
    linux_formats: tuple[str, ...] = ()  # none: the product is built on Windows only
    #: Builds the Linux packages: (product, PyInstaller folder, formats, jobs) -> files written.
    package_linux: Callable[["Product", Path, list[str], int], list[Path]] | None = None
    #: More files to make on Windows beside the setup, each from (product, PyInstaller folder).
    windows_extras: tuple[Callable[["Product", Path], Path], ...] = ()
    add_arguments: Callable[[argparse.ArgumentParser], None] | None = None  # extra options
    prepare: Callable[[argparse.Namespace], None] | None = None  # runs before PyInstaller


def run(command: list[str], *, env: dict[str, str] | None = None, cwd: Path = ROOT) -> None:
    print("+", " ".join(shlex.quote(part) for part in command), flush=True)
    subprocess.run(command, check=True, cwd=cwd, env=env)


def run_parallel(tasks: list[Callable[[], T]], jobs: int) -> list[T]:
    """Run independent ``tasks`` on up to ``jobs`` threads; results keep the order of ``tasks``.

    The work is in subprocesses (PyInstaller, makensis, nfpm), so threads are enough. The first
    failure is raised once the others have finished.
    """
    with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(tasks) or 1))) as pool:
        futures = [pool.submit(task) for task in tasks]
        return [future.result() for future in futures]


def author(meta: Meta) -> dict[str, str]:
    authors = meta.project.get("authors") or [{}]
    return dict(authors[0])  # type: ignore[index]


# ---- PyInstaller -------------------------------------------------------------------------------
def freeze(product: Product) -> Path:
    """Run PyInstaller for one product and return its output folder."""
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(product.spec),
            "--noconfirm",
            "--distpath",
            str(BUILD),
            "--workpath",
            str(WORK / product.key),
        ]
    )
    return BUILD / product.meta.name


# ---- branding ----------------------------------------------------------------------------------
@functools.cache
def brand_icon() -> Path:
    """The installer icon: the .ico in brand/light (the same one the executables carry)."""
    icons = sorted((ROOT / "brand" / "light").glob("*.ico"))
    if not icons:
        raise SystemExit("No .ico found in brand/light.")
    return icons[0]


def brand_art() -> dict[str, str]:
    """The setup's header and welcome bitmaps from brand/dark/nsis, when they exist."""
    art = ROOT / "brand" / "dark" / "nsis"
    names = {"HEADER_IMAGE": "header.bmp", "WELCOME_IMAGE": "welcome.bmp"}
    return {key: str(art / name) for key, name in names.items() if (art / name).is_file()}


def brand_png_dir() -> Path:
    """The folder with the package icons (app-16.png ... app-256.png): brand/light/png."""
    folder = ROOT / "brand" / "light" / "png"
    if not sorted(folder.glob("app-*.png")):
        raise SystemExit("No app-*.png found in brand/light/png.")
    return folder


# ---- Windows: NSIS -----------------------------------------------------------------------------
def sign(files: list[Path]) -> None:
    """Sign ``files`` with SIGN_COMMAND, if it is set; otherwise do nothing."""
    template = os.environ.get("SIGN_COMMAND", "").strip()
    if not template:
        return
    if "{file}" not in template:
        raise SystemExit("SIGN_COMMAND must contain {file}, where the file to sign goes.")
    for file in files:
        command = template.replace("{file}", f'"{file}"')
        print("+", command, flush=True)
        # Windows takes the command line as written; elsewhere it is split like a shell would.
        # SIGN_COMMAND is set by whoever runs the build (a CI variable), so it is trusted input.
        subprocess.run(command if WINDOWS else shlex.split(command), check=True, cwd=ROOT)


def find_makensis() -> str:
    found = shutil.which("makensis")
    if found:
        return found
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        candidate = Path(os.environ.get(variable, "")) / "NSIS" / "makensis.exe"
        if candidate.is_file():
            return str(candidate)
    raise SystemExit("makensis not found. Install NSIS (version in installer/tools.toml).")


def numeric_version(version: str) -> str:
    numbers = re.findall(r"\d+", version)[:4]
    return ".".join(numbers + ["0"] * (4 - len(numbers)))


def package_exe(product: Product, folder: Path) -> Path:
    """Build the NSIS setup for one product."""
    OUT.mkdir(parents=True, exist_ok=True)
    m = product.meta
    sign(sorted(folder.glob("*.exe")))
    setup = OUT / f"{m.name}-{m.version}-setup.exe"
    urls = m.project.get("urls") or {}
    flags = {
        "APP_NAME": m.title,
        "APP_VERSION": m.version,
        "APP_VERSION_NUMERIC": numeric_version(m.version),
        "SOURCE_DIR": str(folder),
        "OUT_FILE": str(setup),
        "ICON_FILE": str(brand_icon()),
        **brand_art(),
        "LICENSE_FILE": str(product.licence),
        "PUBLISHER": m.publisher or author(m).get("name", ""),
        "INSTALL_DIR": m.install_dir.replace("/", "\\"),
        "INSTALL_DIR_DEPTH": len(m.install_dir.split("/")) if m.install_dir else "",
        "SUPPORT_URL": str(urls.get("Issues", "")),  # type: ignore[attr-defined]
        "UPDATE_URL": str(urls.get("Changelog", "")),  # type: ignore[attr-defined]
        "URL": str(urls.get("Homepage", "")),  # type: ignore[attr-defined]
    }
    command = [find_makensis(), "/V2"]
    command += [f"/D{key}={value}" for key, value in flags.items() if value]
    run([*command, str(product.nsi)])
    sign([setup])
    return setup


# ---- Linux -------------------------------------------------------------------------------------
def normalise_modes(folder: Path) -> None:
    """Folders 755, files 644, and 755 for anything executable, whatever the build umask was."""
    for path in [folder, *folder.rglob("*")]:
        if path.is_symlink():
            continue
        if path.is_dir() or path.stat().st_mode & stat.S_IXUSR or ".so" in path.name:
            path.chmod(0o755)
        else:
            path.chmod(0o644)


# ---- driver ------------------------------------------------------------------------------------
def sync(product: Product) -> None:
    """Install the product and the installer dependency group, and nothing else."""
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("--sync needs uv on PATH.")
    dist = str(product.meta.project["name"])
    run([uv, "sync", "--package", dist, "--group", "installer", "--no-dev"])


def smoke(product: Product) -> None:
    """Start each built executable and check it answers (the test_frozen_*.py integration tests)."""
    for folder, test in product.smoke:
        run(
            [sys.executable, "-m", "pytest", "-m", "integration", "--no-cov",
             "-p", "no:cacheprovider", test],
            cwd=folder,
        )  # fmt: skip


def main(product: Product) -> None:
    """Build one product's installers from the command line: the options every product has."""
    parser = argparse.ArgumentParser(description=f"Build the {product.meta.title} installers.")
    parser.add_argument("--sync", action="store_true", help="uv sync the installer group first")
    parser.add_argument("--smoke", action="store_true", help="run the smoke tests on the build")
    allowed = ["exe"] if WINDOWS else list(product.linux_formats)
    parser.add_argument(
        "--format",
        metavar="exe,deb,rpm",
        help=f"comma-separated formats, here: {', '.join(allowed) or 'none'} (default: all)",
    )
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                        help="builds to run at once (1 = one after the other)")  # fmt: skip
    if product.add_arguments:
        product.add_arguments(parser)
    args = parser.parse_args()

    if not (WINDOWS or LINUX):
        raise SystemExit("Installers are built on Windows (setup.exe) and Linux (deb, rpm) only.")
    if not allowed:
        raise SystemExit(f"The {product.meta.title} installer is built on Windows only.")
    formats = [f.strip() for f in args.format.split(",") if f.strip()] if args.format else []
    unknown = sorted(set(formats) - set(FORMATS))
    if unknown:
        parser.error(f"unknown format: {', '.join(unknown)} (choose from {', '.join(FORMATS)})")
    wrong = [f for f in formats if f not in allowed]
    if wrong:
        raise SystemExit(
            f"--format {','.join(wrong)} cannot be built on this OS (here: {', '.join(allowed)})."
        )
    formats = formats or allowed

    if args.sync:
        sync(product)
    if product.prepare:
        product.prepare(args)
    folder = freeze(product)
    if WINDOWS:
        brand_icon()  # fail early, before the setup and its extras are built side by side
        tasks: list[Callable[[], Path]] = [functools.partial(package_exe, product, folder)]
        tasks += [functools.partial(extra, product, folder) for extra in product.windows_extras]
        built = run_parallel(tasks, args.jobs)
    else:
        if product.package_linux is None:
            raise SystemExit(f"{product.meta.title} has no Linux package.")
        built = product.package_linux(product, folder, formats, args.jobs)
    if args.smoke:
        smoke(product)
    print("\nBuilt:")
    for path in built:
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    raise SystemExit(__doc__)
