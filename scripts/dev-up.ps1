# dev-up.ps1 — Start postgres and redis (Windows equivalent of dev-up.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

docker compose up -d postgres redis
