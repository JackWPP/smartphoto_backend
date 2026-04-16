# deploy-prod.ps1 — Build image and hot-update api/worker (Windows equivalent of deploy-prod.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$EnvFile     = if ($env:ENV_FILE)     { $env:ENV_FILE }     else { '.env.prod' }
$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { 'docker-compose.prod.yml' }
$ImageRepo   = if ($env:SMARTPHOTO_IMAGE_REPO) { $env:SMARTPHOTO_IMAGE_REPO } else { 'smartphoto-backend' }
$ReleaseDir  = Join-Path $RootDir '.release'
$SkipMigrate = $false
$ImageTag    = ''

function Show-Usage {
    Write-Host @"
Usage: .\scripts\deploy-prod.ps1 [-ImageTag <tag>] [-SkipMigrate]

Build a new app image locally, keep postgres/redis volumes intact, then hot-update api/worker.
"@
}

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        '--image-tag'    { $ImageTag    = $args[++$i] }
        '--skip-migrate' { $SkipMigrate = $true }
        { $_ -in '-h','--help' } { Show-Usage; exit 0 }
        default { Write-Error "Unknown argument: $($args[$i])"; Show-Usage; exit 1 }
    }
}

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing ${EnvFile}. Keep the server's .env.prod in place before deploying."
    exit 1
}
if (-not (Test-Path $ComposeFile)) {
    Write-Error "Missing ${ComposeFile}."
    exit 1
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

if (-not $ImageTag) {
    $ImageTag = Get-Date -Format 'yyyyMMddHHmmss'
}

$ImageRef     = "${ImageRepo}:${ImageTag}"
$CurrentImage = ''
$CurrentImageFile  = Join-Path $ReleaseDir 'current_image'
$PreviousImageFile = Join-Path $ReleaseDir 'previous_image'

if (Test-Path $CurrentImageFile) {
    $CurrentImage = (Get-Content $CurrentImageFile -Raw).Trim()
}
if ($CurrentImage) {
    Set-Content -Path $PreviousImageFile -Value $CurrentImage -NoNewline
}

Write-Host "Building ${ImageRef}"
docker build -t $ImageRef .

Write-Host "Ensuring postgres/redis are up"
docker compose --env-file $EnvFile -f $ComposeFile up -d postgres redis

if (-not $SkipMigrate) {
    Write-Host "Running migrations with ${ImageRef}"
    $env:SMARTPHOTO_IMAGE = $ImageRef
    docker compose --env-file $EnvFile -f $ComposeFile run --rm migrate
    Remove-Item Env:SMARTPHOTO_IMAGE -ErrorAction SilentlyContinue
}

Write-Host "Hot-updating api/worker to ${ImageRef}"
$env:SMARTPHOTO_IMAGE = $ImageRef
docker compose --env-file $EnvFile -f $ComposeFile up -d --no-deps api worker
Remove-Item Env:SMARTPHOTO_IMAGE -ErrorAction SilentlyContinue

Set-Content -Path $CurrentImageFile -Value $ImageRef -NoNewline

Write-Host "Deployed ${ImageRef}"
Write-Host "Current image recorded in ${CurrentImageFile}"
