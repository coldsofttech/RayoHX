"""Imports the compiled rayohx from the environment built by setup_venv.py and inspects the first
test stream.

Usage: ``python scripts/smoke/test_core.py``
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = HERE / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
LINKS = HERE / "test_links.txt"


def inspect_stream() -> None:
    """Runs inside the smoke environment, where the compiled rayohx is installed."""
    import rayohx

    url = LINKS.read_text(encoding="utf-8").splitlines()[0].strip()

    # Nuitka modules report __file__ as rayohx/__init__.py, so check the loader instead.
    loader = type(rayohx.__spec__.loader).__name__
    print("rayohx:", rayohx.__file__, f"(loader: {loader})")
    if "nuitka" not in loader.lower() and "Extension" not in loader:
        print("WARNING: not a compiled build", file=sys.stderr)

    print("inspecting:", url)
    print(rayohx.inspect(url))


def main() -> None:
    if "--inside" in sys.argv:
        inspect_stream()
        return
    if not PYTHON.exists():
        sys.exit("Run setup_venv.py first")
    command = [str(PYTHON), str(Path(__file__).resolve()), "--inside"]
    result = subprocess.run(command, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.exit(f"rayohx inspect failed (exit {result.returncode})")


if __name__ == "__main__":
    main()
