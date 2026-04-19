# dev-api.ps1 — Run migrations then start uvicorn (Windows equivalent of dev-api.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$Alembic = Join-Path $RootDir '.venv\Scripts\alembic.exe'
$Uvicorn = Join-Path $RootDir '.venv\Scripts\uvicorn.exe'

$HOST_ADDR = if ($env:HOST) { $env:HOST } else { '0.0.0.0' }
$PORT = if ($env:PORT) { [int]$env:PORT } else { 8000 }
$PORT_SEARCH_LIMIT = if ($env:PORT_SEARCH_LIMIT) { [int]$env:PORT_SEARCH_LIMIT } else { 10 }

function Test-PortBusy {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $conn)
}

function Resolve-Port {
    param([int]$RequestedPort)
    $candidate = $RequestedPort
    $offset = 0
    while (Test-PortBusy $candidate) {
        $offset++
        if ($offset -gt $PORT_SEARCH_LIMIT) {
            Write-Error "dev-api.ps1: no free port found in range ${RequestedPort}-$($RequestedPort + $PORT_SEARCH_LIMIT)"
            exit 1
        }
        $candidate = $RequestedPort + $offset
    }
    if ($candidate -ne $RequestedPort) {
        Write-Host "dev-api.ps1: port ${RequestedPort} is busy, fallback to ${candidate}" -ForegroundColor Yellow
    }
    return $candidate
}

& $Alembic upgrade head
$PORT = Resolve-Port $PORT
Write-Host "dev-api.ps1: starting uvicorn on http://${HOST_ADDR}:${PORT}" -ForegroundColor Cyan

& $Uvicorn app.main:app `
    --reload `
    --reload-dir app `
    --reload-dir scripts `
    --reload-dir alembic `
    "--reload-exclude=runtime/*" `
    "--reload-exclude=storage/*" `
    "--reload-exclude=.git/*" `
    --host $HOST_ADDR `
    --port $PORT
