import subprocess
import sys
from pathlib import Path

import rayohx


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_module_entrypoint() -> None:
    result = _run(sys.executable, "-m", "rayohx_cli", "--version")

    assert result.returncode == 0
    assert rayohx.__version__ in result.stdout


def test_console_script() -> None:
    script = Path(sys.executable).parent / ("rayohx.exe" if sys.platform == "win32" else "rayohx")

    result = _run(str(script), "--version")

    assert result.returncode == 0
    assert rayohx.__version__ in result.stdout
