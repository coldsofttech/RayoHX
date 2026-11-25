# Starts the compiled UI without a window, reads the address it prints, loads the front page and
# inspects the first manual test stream through the UI's own /api/v1 routes, then stops it.
$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot ".venv\Scripts\rayohxu.exe"
if (-not (Test-Path $exe)) { throw "Run setup_venv.ps1 first" }
$url = (Get-Content (Join-Path $PSScriptRoot "test_links.txt") -TotalCount 1).Trim()
$out = Join-Path $PSScriptRoot "ui.out.log"
$err = Join-Path $PSScriptRoot "ui.err.log"
Remove-Item $out, $err -ErrorAction SilentlyContinue

$proc = Start-Process $exe -ArgumentList "--no-window" -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $out -RedirectStandardError $err
try {
    $ready = $null
    for ($i = 0; $i -lt 30 -and -not $ready; $i++) {
        if ($proc.HasExited) { throw "UI exited; see $err" }
        if (Test-Path $out) { $ready = Get-Content $out -TotalCount 1 }
        if (-not $ready) { Start-Sleep 1 }
    }
    if (-not $ready) { throw "UI printed no address; see $err" }
    Write-Host "ready: $ready"

    $address = [regex]::Match($ready, 'https?://[^"\s]+').Value
    if (-not $address) { throw "no address in the ready line" }
    $origin = ([uri]$address).GetLeftPart([System.UriPartial]::Authority)

    # The address carries a one-time token; loading it starts the session the API calls need.
    $page = Invoke-WebRequest $address -SessionVariable session -UseBasicParsing
    Write-Host "front page: $($page.StatusCode) $($page.Headers['Content-Type'])"

    Write-Host "inspecting: $url"
    $body = @{ url = $url } | ConvertTo-Json
    $res = Invoke-RestMethod "$origin/api/v1/inspect" -Method Post -ContentType "application/json" `
        -Body $body -WebSession $session -Headers @{ Origin = $origin }
    $res | ConvertTo-Json -Depth 8
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
}
