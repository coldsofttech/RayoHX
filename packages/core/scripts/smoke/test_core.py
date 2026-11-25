"""Imports the installed (compiled) rayohx and inspects the first manual test stream."""

import sys
from pathlib import Path

import rayohx

LINKS = Path(__file__).resolve().parent / "test_links.txt"
url = LINKS.read_text(encoding="utf-8").splitlines()[0].strip()

# Nuitka modules report __file__ as rayohx/__init__.py, so check the loader instead.
loader = type(rayohx.__spec__.loader).__name__
print("rayohx:", rayohx.__file__, f"(loader: {loader})")
if "nuitka" not in loader.lower() and "Extension" not in loader:
    print("WARNING: not a compiled build", file=sys.stderr)

print("inspecting:", url)
playlist = rayohx.inspect(url)
print(playlist)
