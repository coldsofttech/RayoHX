"""Builds the compiled (Nuitka) rayohx wheel and installs it into scripts/smoke/.venv.

It needs uv and a C compiler.

Usage: ``python scripts/smoke/setup_venv.py [--python 3.11]``
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VENV = HERE / ".venv"
WHEELS = HERE / "wheels"


def venv_python() -> Path:
    """The interpreter inside the smoke environment."""
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*command: str | Path, env: dict[str, str] | None = None) -> None:
    """Run a command in the package folder, stopping the script if it fails."""
    subprocess.run([str(part) for part in command], check=True, cwd=ROOT, env=env)  # noqa: S603


def create_venv(version: str | None) -> None:
    """Make a fresh environment, with the requested Python version or the default one."""
    if VENV.exists():
        shutil.rmtree(VENV)
    python = ["--python", version] if version else []
    run("uv", "venv", *python, VENV)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", help="Python version for the environment, for example 3.11")
    args = parser.parse_args()

    create_venv(args.python)
    python = venv_python()
    run(
        "uv", "pip", "install", "--python", python,
        "build", "nuitka", "setuptools", "wheel", "mypy>=1.13",
    )  # fmt: skip

    # Compile rayohx into a single extension module and build the wheel.
    if WHEELS.exists():
        shutil.rmtree(WHEELS)
    run(
        python, "-m", "build", "--wheel", "--no-isolation", "--outdir", WHEELS,
        env={**os.environ, "PYD_BUILD": "1"},
    )  # fmt: skip

    wheel = next(WHEELS.glob("rayohx-*.whl"))
    run("uv", "pip", "install", "--python", python, "--force-reinstall", wheel)
    run(python, "-c", "import rayohx; print('installed:', rayohx.__file__)")


if __name__ == "__main__":
    main()
