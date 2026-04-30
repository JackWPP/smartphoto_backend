# rollback-prod.ps1 — Rollback api/worker to previous image (Windows equivalent of rollback-prod.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$EnvFile     = if ($env:ENV_FILE)     { $env:ENV_FILE }     else { '.env.prod' }
$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { 'docker-compose.prod.yml' }
$ReleaseDir  = Join-Path $RootDir '.release'
$TargetImage = if ($args.Count -gt 0) { $args[0] } else { '' }

function Show-Usage {
    Write-Host @"
Usage: .\scripts\rollback-prod.ps1 [image-ref]

If image-ref is omitted, use .release\previous_image.
"@
}

if ($TargetImage -in '-h','--help') { Show-Usage; exit 0 }

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing ${EnvFile}."
    exit 1
}
if (-not (Test-Path $ComposeFile)) {
    Write-Error "Missing ${ComposeFile}."
    exit 1
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

$CurrentImageFile  = Join-Path $ReleaseDir 'current_image'
$PreviousImageFile = Join-Path $ReleaseDir 'previous_image'

if (-not $TargetImage) {
    if (Test-Path $PreviousImageFile) {
        $TargetImage = (Get-Content $PreviousImageFile -Raw).Trim()
    }
}
if (-not $TargetImage) {
    Write-Error "No rollback image found. Pass an explicit image ref or deploy once first."
    exit 1
}

$CurrentImage = ''
if (Test-Path $CurrentImageFile) {
    $CurrentImage = (Get-Content $CurrentImageFile -Raw).Trim()
}

Write-Host "Ensuring postgres/redis are up"
docker compose --env-file $EnvFile -f $ComposeFile up -d postgres redis

Write-Host "Rolling back api/worker to ${TargetImage}"
$env:SMARTPHOTO_IMAGE = $TargetImage
docker compose --env-file $EnvFile -f $ComposeFile up -d --no-deps api worker
Remove-Item Env:SMARTPHOTO_IMAGE -ErrorAction SilentlyContinue

if ($CurrentImage -and $CurrentImage -ne $TargetImage) {
    Set-Content -Path $PreviousImageFile -Value $CurrentImage -NoNewline
}
Set-Content -Path $CurrentImageFile -Value $TargetImage -NoNewline

Write-Host "Rollback complete: ${TargetImage}"
