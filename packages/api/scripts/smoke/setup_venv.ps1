# Builds the compiled (Nuitka .pyd) rayohx-api wheel and installs it into packages/api/scripts/smoke/.venv.
# rayohx (core) is taken from the compiled wheel built by packages/core/scripts/smoke/setup_venv.ps1.
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$api = Resolve-Path (Join-Path $here "..\..")
$coreWheels = Join-Path $here "..\..\..\core\scripts\smoke\wheels"
$venv = Join-Path $here ".venv"

if (-not (Test-Path $coreWheels)) { throw "Run packages\core\scripts\smoke\setup_venv.ps1 first (compiled core wheel missing)" }

if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
py -3.11 -m venv $venv
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip build nuitka setuptools wheel "mypy>=1.13"

# Install the compiled core first, then the API's own dependencies.
& $python -m pip install --find-links $coreWheels rayohx
& $python -m pip install "fastapi>=0.162.4" "pydantic-settings>=2.16.3" "uvicorn>=0.32"

$wheelDir = Join-Path $here "wheels"
if (Test-Path $wheelDir) { Remove-Item -Recurse -Force $wheelDir }
Push-Location $api
try {
    $env:PYD_BUILD = "1"
    & $python -m build --wheel --no-isolation --outdir $wheelDir
    if ($LASTEXITCODE -ne 0) { throw "wheel build failed" }
} finally {
    Remove-Item Env:\PYD_BUILD -ErrorAction SilentlyContinue
    Pop-Location
}

$wheel = Get-ChildItem $wheelDir -Filter "rayohx_api-*.whl" | Select-Object -First 1
& $python -m pip install --force-reinstall --no-deps $wheel.FullName
& $python -c "import rayohx_api, rayohx; print('installed:', rayohx_api.__file__)"
