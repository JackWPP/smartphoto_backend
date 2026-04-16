# dev-worker.ps1 — Run migrations then start Celery worker (Windows equivalent of dev-worker.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$Alembic = Join-Path $RootDir '.venv\Scripts\alembic.exe'
$Celery  = Join-Path $RootDir '.venv\Scripts\celery.exe'

& $Alembic upgrade head
& $Celery -A app.workers.celery_app.celery_app worker `
    -Q q.analysis,q.copy,q.generation.main,q.generation.detail `
    --loglevel=info
