# package-prod.ps1 — Create release tarball from git-tracked files (Windows equivalent of package-prod.sh)
# Requires: git, tar (built-in on Windows 10/11)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$OutDir  = Join-Path $RootDir 'dist'
$Stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$GitRev  = (git rev-parse --short HEAD 2>$null) ?? 'workspace'
$ArchivePath = Join-Path $OutDir "smartphoto_backend_deploy_${Stamp}_${GitRev}.tar.gz"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$IncludePaths = @(
    'Dockerfile'
    '.dockerignore'
    'docker-compose.prod.yml'
    '.env.prod.example'
    'AGENTS.md'
    'pyproject.toml'
    'Readme.md'
    'alembic.ini'
    'app'
    'alembic'
    'adminfront'
    'scripts'
    'docs/运行与排障手册.md'
    'docs/生产上线SOP.md'
)

# Get only git-tracked files from the whitelist (null-separated, then split)
$raw = git -c core.quotePath=false ls-files -z -- @IncludePaths
$PackageFiles = ($raw -split "`0") | Where-Object { $_ -ne '' }

if ($PackageFiles.Count -eq 0) {
    Write-Error "No tracked files matched the package whitelist."
    exit 1
}

# tar on Windows 10/11 (bsdtar) supports -czf
tar -czf $ArchivePath @PackageFiles

Write-Host "Package created: ${ArchivePath}"
