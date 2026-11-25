# Starts the compiled API (no auth, throwaway data) and inspects the first manual test stream.
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$server = Join-Path $PSScriptRoot ".venv\Scripts\rayohx-api.exe"
if (-not (Test-Path $server)) { throw "Run setup_venv.ps1 first" }
$url = (Get-Content (Join-Path $PSScriptRoot "test_links.txt") -TotalCount 1).Trim()
$port = 8765
$base = "http://127.0.0.1:$port"
$data = Join-Path $PSScriptRoot "data"
New-Item -ItemType Directory -Force $data | Out-Null

$env:RAYOHX_API_AUTH_MODE = "none"
$env:RAYOHX_API_PORT = "$port"
$env:RAYOHX_API_DOWNLOAD_DIR = $data
$env:RAYOHX_API_DB_PATH = Join-Path $data "rayohx.db"

$proc = Start-Process $server -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $data "out.log") -RedirectStandardError (Join-Path $data "err.log")
try {
    $ready = $false
    for ($i = 0; $i -lt 30 -and -not $ready; $i++) {
        if ($proc.HasExited) { throw "server exited; see $data\err.log" }
        try { Invoke-RestMethod "$base/health" | Out-Null; $ready = $true } catch { Start-Sleep 1 }
    }
    if (-not $ready) { throw "server did not become ready; see $data\err.log" }
    Write-Host "health: ok"

    Write-Host "inspecting: $url"
    $body = @{ url = $url } | ConvertTo-Json
    $res = Invoke-RestMethod "$base/api/v1/inspect" -Method Post -ContentType "application/json" -Body $body
    $res | ConvertTo-Json -Depth 8
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
}
