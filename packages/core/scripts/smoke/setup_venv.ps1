# Builds the compiled (Nuitka .pyd) rayohx wheel and installs it into packages/core/scripts/smoke/.venv.
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$core = Resolve-Path (Join-Path $here "..\..")
$venv = Join-Path $here ".venv"

if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
py -3.11 -m venv $venv
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip build nuitka setuptools wheel "mypy>=1.13"

# Compile rayohx into a single extension module and build the wheel.
$wheelDir = Join-Path $here "wheels"
if (Test-Path $wheelDir) { Remove-Item -Recurse -Force $wheelDir }
Push-Location $core
try {
    $env:PYD_BUILD = "1"
    & $python -m build --wheel --no-isolation --outdir $wheelDir
    if ($LASTEXITCODE -ne 0) { throw "wheel build failed" }
} finally {
    Remove-Item Env:\PYD_BUILD -ErrorAction SilentlyContinue
    Pop-Location
}

$wheel = Get-ChildItem $wheelDir -Filter "rayohx-*.whl" | Select-Object -First 1
& $python -m pip install --force-reinstall $wheel.FullName
& $python -c "import rayohx, sys; print('installed:', rayohx.__file__)"
