"""The layering rules that keep the engine, the platform and the front ends apart."""

import ast
from pathlib import Path

import pytest

CORE_SRC = Path(__file__).resolve().parents[2] / "src" / "rayohx"
PACKAGES = CORE_SRC.parents[2]
PLATFORM_SRC = CORE_SRC / "platform"


def imports(path: Path) -> list[tuple[int, str]]:
    """Every module a file imports; ``from rayohx import x`` counts as ``rayohx.x``."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module))
            found.extend((node.lineno, f"{node.module}.{alias.name}") for alias in node.names)
    return found


def is_private(module: str) -> bool:
    parts = module.split(".")
    return parts[0] == "rayohx" and any(
        part.startswith("_") and not part.startswith("__") for part in parts[1:]
    )


def python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_engine_never_imports_the_platform() -> None:
    offenders = []
    for path in python_files(CORE_SRC):
        if PLATFORM_SRC in path.parents or path == CORE_SRC / "__init__.py":
            continue  # the package's lazy exports may name the platform
        offenders += [
            f"{path.relative_to(CORE_SRC)}:{line} imports {module}"
            for line, module in imports(path)
            if module == "rayohx.platform" or module.startswith("rayohx.platform.")
        ]
    assert not offenders, "\n".join(offenders)


def test_the_platform_uses_only_the_public_engine() -> None:
    offenders = []
    for path in python_files(PLATFORM_SRC):
        offenders += [
            f"{path.relative_to(CORE_SRC)}:{line} imports {module}"
            for line, module in imports(path)
            if is_private(module)
        ]
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("package", ["api", "cli", "ui"])
def test_front_ends_use_only_the_public_engine(package: str) -> None:
    source = PACKAGES / package / "src"
    if not source.is_dir():
        pytest.skip(f"{package} is not in this checkout")
    offenders = []
    for path in python_files(source):
        offenders += [
            f"{path.relative_to(PACKAGES)}:{line} imports {module}"
            for line, module in imports(path)
            if is_private(module)
        ]
    assert not offenders, "\n".join(offenders)


def test_the_platform_is_not_loaded_by_importing_the_engine() -> None:
    import subprocess
    import sys

    code = (
        "import sys, rayohx, rayohx.downloader, rayohx.config;"
        "print('rayohx.platform' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"
