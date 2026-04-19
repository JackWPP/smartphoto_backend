# dev-worker.ps1 — Run migrations then start Celery worker (Windows equivalent of dev-worker.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$Alembic = Join-Path $RootDir '.venv\Scripts\alembic.exe'
$Celery  = Join-Path $RootDir '.venv\Scripts\celery.exe'
$Queues = if ($env:CELERY_QUEUES) {
    $env:CELERY_QUEUES
} else {
    'q.analysis,q.copy,q.generation.main,q.generation.detail,q.quality'
}
$WorkerPool = if ($env:CELERY_WORKER_POOL) {
    $env:CELERY_WORKER_POOL
} elseif ($env:CELERY_POOL) {
    $env:CELERY_POOL
} else {
    'solo'
}
$WorkerConcurrency = if ($env:CELERY_WORKER_CONCURRENCY) {
    $env:CELERY_WORKER_CONCURRENCY
} elseif ($env:CELERY_CONCURRENCY) {
    $env:CELERY_CONCURRENCY
} elseif ($WorkerPool -eq 'solo') {
    '1'
} else {
    $null
}

& $Alembic upgrade head

Write-Host "dev-worker.ps1: starting Celery with pool=${WorkerPool} queues=${Queues}" -ForegroundColor Cyan

$CeleryArgs = @(
    '-A', 'app.workers.celery_app.celery_app',
    'worker',
    '-Q', $Queues,
    '--loglevel=info',
    '--pool', $WorkerPool
)

if ($WorkerConcurrency) {
    $CeleryArgs += @('--concurrency', $WorkerConcurrency)
}

& $Celery @CeleryArgs
