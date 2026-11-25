# Runs the image built by setup_image.ps1: checks it runs as a non-root user, then runs
# `rayohx info` on the first manual test stream.
$ErrorActionPreference = "Stop"
$image = "rayohx:local-test"
docker image inspect $image *> $null
if ($LASTEXITCODE -ne 0) { throw "Run setup_image.ps1 first" }
$url = (Get-Content (Join-Path $PSScriptRoot "test_links.txt") -TotalCount 1).Trim()

Write-Host "user:"
docker run --rm --entrypoint id $image
if ($LASTEXITCODE -ne 0) { throw "id failed" }

Write-Host "inspecting: $url"
docker run --rm $image info $url
if ($LASTEXITCODE -ne 0) { throw "rayohx info failed (exit $LASTEXITCODE)" }
