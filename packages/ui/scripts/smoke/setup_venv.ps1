# Builds the compiled (Nuitka .pyd) rayohx-ui wheel and installs it into packages/ui/scripts/smoke/.venv.
# rayohx (core) and rayohx-api come from the compiled wheels built by the core and api smoke scripts.
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$ui = Resolve-Path (Join-Path $here "..\..")
$coreWheels = Join-Path $here "..\..\..\core\scripts\smoke\wheels"
$apiWheels = Join-Path $here "..\..\..\api\scripts\smoke\wheels"
$venv = Join-Path $here ".venv"

foreach ($dir in @($coreWheels, $apiWheels)) {
    if (-not (Test-Path $dir)) { throw "Run packages\core\scripts\smoke\setup_venv.ps1 and packages\api\scripts\smoke\setup_venv.ps1 first ($dir missing)" }
}

# The wheel carries the built front end (ui/dist); build it if it isn't there.
$frontend = Join-Path $ui "src\rayohx_ui\ui"
if (-not (Test-Path (Join-Path $frontend "dist"))) {
    Push-Location $frontend
    try {
        npm ci
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "front end build failed" }
    } finally { Pop-Location }
}

if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
py -3.11 -m venv $venv
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip build nuitka setuptools wheel "mypy>=1.13"

# Install the compiled core and API first, then the UI's own dependency.
& $python -m pip install --find-links $coreWheels --find-links $apiWheels rayohx rayohx-api
& $python -m pip install "cornea-shell>=0.1.1"

$wheelDir = Join-Path $here "wheels"
if (Test-Path $wheelDir) { Remove-Item -Recurse -Force $wheelDir }
Push-Location $ui
try {
    $env:PYD_BUILD = "1"
    & $python -m build --wheel --no-isolation --outdir $wheelDir
    if ($LASTEXITCODE -ne 0) { throw "wheel build failed" }
} finally {
    Remove-Item Env:\PYD_BUILD -ErrorAction SilentlyContinue
    Pop-Location
}

$wheel = Get-ChildItem $wheelDir -Filter "rayohx_ui-*.whl" | Select-Object -First 1
& $python -m pip install --force-reinstall --no-deps $wheel.FullName
& $python -c "import rayohx_ui, rayohx; print('installed:', rayohx_ui.__file__)"
