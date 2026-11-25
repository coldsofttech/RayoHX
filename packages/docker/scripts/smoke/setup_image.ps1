# Builds the RayoHX Docker image from packages/docker/Dockerfile (from the repo root, so core and
# cli are in the build context). The image installs the packages as plain Python on Linux; the
# Windows .pyd wheels from the core and cli smoke scripts can't be used inside it.
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
$image = "rayohx:local-test"

Push-Location $root
try {
    docker build -f packages/docker/Dockerfile -t $image --build-arg VERSION=0.0.0-local .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
} finally {
    Pop-Location
}
docker image ls $image
