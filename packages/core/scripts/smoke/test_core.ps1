# Runs test_core.py with the venv created by setup_venv.ps1.
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Run setup_venv.ps1 first" }
& $python (Join-Path $PSScriptRoot "test_core.py")
