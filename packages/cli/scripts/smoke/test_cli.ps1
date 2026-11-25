# Runs `rayohx info` from the venv built by setup_venv.ps1 against the first manual test stream.
$rayohx = Join-Path $PSScriptRoot ".venv\Scripts\rayohx.exe"
if (-not (Test-Path $rayohx)) { throw "Run setup_venv.ps1 first" }
$url = (Get-Content (Join-Path $PSScriptRoot "test_links.txt") -TotalCount 1).Trim()

Write-Host "inspecting: $url"
& $rayohx info $url
if ($LASTEXITCODE -ne 0) { throw "rayohx info failed (exit $LASTEXITCODE)" }
