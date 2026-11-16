#!/usr/bin/env python3
"""Run the tests of every package, one pytest run each, with that package's own settings.

The packages each have a ``tests`` package of the same name, so they cannot be collected in one
run. Extra arguments go to every run:  python scripts/run_tests.py -n auto
"""

import subprocess
import sys
from pathlib import Path

PACKAGES = ("core", "cli", "api", "ui")
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failed = []
    for package in PACKAGES:
        base = ROOT / "packages" / package
        command = ["uv", "run", "pytest", "-c", str(base / "pyproject.toml"), str(base / "tests")]
        print(f"== {package}", flush=True)
        if subprocess.run([*command, *sys.argv[1:]], cwd=ROOT, check=False).returncode:
            failed.append(package)
    if failed:
        print(f"Failed: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
