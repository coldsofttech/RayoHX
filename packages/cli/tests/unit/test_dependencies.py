"""Each published package imports only what it declares."""

import ast
import sys
import tomllib
from pathlib import Path

import pytest

PACKAGES = Path(__file__).resolve().parents[3]
#: The packages in this repository, which may import one another.
OWN = {"rayohx", "rayohx_cli"}


def _declared(directory: str) -> set[str]:
    path = PACKAGES / directory / "pyproject.toml"
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    names = set()
    for requirement in project["dependencies"]:
        name = requirement
        for separator in ">=<~! ;[":
            name = name.split(separator)[0]
        names.add(name.lower().replace("-", "_"))
    return names


def _imported(directory: str, package: str) -> set[str]:
    found: set[str] = set()
    for path in (PACKAGES / directory / "src" / package).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize(("directory", "package"), [("core", "rayohx"), ("cli", "rayohx_cli")])
def test_every_third_party_import_is_a_declared_dependency(directory: str, package: str) -> None:
    declared = _declared(directory)
    third_party = {
        name for name in _imported(directory, package) if name not in sys.stdlib_module_names | OWN
    }
    assert third_party <= declared, f"{package} imports {third_party - declared}"
