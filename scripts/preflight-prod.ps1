# preflight-prod.ps1 — Validate production environment (Windows equivalent of preflight-prod.sh)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$EnvFile     = if ($env:ENV_FILE)     { $env:ENV_FILE }     else { '.env.prod' }
$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { 'docker-compose.prod.yml' }

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing ${EnvFile}."
    exit 1
}
if (-not (Test-Path $ComposeFile)) {
    Write-Error "Missing ${ComposeFile}."
    exit 1
}

# Load env file into current process environment
foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
    if ($line -match '^([^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}

function Mask-DatabaseUrl {
    param([string]$Url)
    return $Url -replace '(://)[^:@/]+(:[^@/]+)?@', '$1***:***@'
}

function Invoke-PsqlExec {
    param([string]$Sql)
    $result = docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres `
        psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -Atqc $Sql
    return $result
}

Write-Host "== Release image =="
$CurrentImageFile  = Join-Path $RootDir '.release\current_image'
$PreviousImageFile = Join-Path $RootDir '.release\previous_image'

if (Test-Path $CurrentImageFile) {
    Write-Host "current_image=$(Get-Content $CurrentImageFile -Raw)"
} else {
    Write-Host "current_image=<none>"
}
if (Test-Path $PreviousImageFile) {
    Write-Host "previous_image=$(Get-Content $PreviousImageFile -Raw)"
} else {
    Write-Host "previous_image=<none>"
}

Write-Host ""
Write-Host "== Runtime env =="
Write-Host "PUBLIC_BASE_URL=$($env:PUBLIC_BASE_URL)"
Write-Host "CORS_ALLOW_ORIGINS=$($env:CORS_ALLOW_ORIGINS)"
Write-Host "DATABASE_URL=$(Mask-DatabaseUrl $env:DATABASE_URL)"
Write-Host "ADMIN_DATABASE_URL=$($env:ADMIN_DATABASE_URL)"
Write-Host "STORAGE_BACKEND=$($env:STORAGE_BACKEND)"
Write-Host "S3_ENDPOINT=$($env:S3_ENDPOINT)"
Write-Host "S3_BUCKET=$($env:S3_BUCKET)"

Write-Host ""
Write-Host "== Compose config =="
docker compose --env-file $EnvFile -f $ComposeFile config | Out-Null
Write-Host "docker compose config: ok"

Write-Host ""
Write-Host "== Container status =="
docker compose --env-file $EnvFile -f $ComposeFile ps

Write-Host ""
Write-Host "== Database checks =="
$AlembicVersion = (Invoke-PsqlExec "SELECT version_num FROM alembic_version ORDER BY version_num;") -join ' '
Write-Host "alembic_version=$($AlembicVersion.Trim() -replace '\s+', ' ')"

$TablesSql = @"
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
  AND table_name IN (
    'users',
    'user_refresh_tokens',
    'credit_wallets',
    'rule_packs',
    'rule_pack_versions'
  )
ORDER BY table_name;
"@
$TablesPresent = Invoke-PsqlExec $TablesSql
Write-Host "tables:"
$TablesPresent | ForEach-Object { Write-Host $_ }

$RulePackColumnsSql = @"
SELECT table_name || '.' || column_name
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('rule_packs', 'rule_pack_versions')
ORDER BY table_name, ordinal_position;
"@
$RulePackColumns = Invoke-PsqlExec $RulePackColumnsSql
Write-Host ""
Write-Host "rule_pack columns:"
$RulePackColumns | ForEach-Object { Write-Host $_ }

$Failed = $false

if ($AlembicVersion -match '20260322_0007') {
    Write-Error "[FAIL] alembic_version contains 20260322_0007. Stop and reconcile schema before release."
    $Failed = $true
}

foreach ($required in @('users','user_refresh_tokens','credit_wallets','rule_packs','rule_pack_versions')) {
    if ($TablesPresent -notcontains $required) {
        Write-Host "[FAIL] missing required table: ${required}" -ForegroundColor Red
        $Failed = $true
    }
}

$ExpectedColumns = @(
    'rule_packs.asset_family','rule_packs.rule_pack_key','rule_packs.current_version_no',
    'rule_pack_versions.asset_family','rule_pack_versions.rule_pack_key',
    'rule_pack_versions.config_snapshot','rule_pack_versions.is_published'
)
foreach ($col in $ExpectedColumns) {
    if ($RulePackColumns -notcontains $col) {
        Write-Host "[FAIL] missing expected recovery-schema column: ${col}" -ForegroundColor Red
        $Failed = $true
    }
}

$IncompatibleColumns = @(
    'rule_packs.family','rule_packs.draft_payload','rule_packs.latest_version_no',
    'rule_pack_versions.payload','rule_pack_versions.change_note'
)
foreach ($col in $IncompatibleColumns) {
    if ($RulePackColumns -contains $col) {
        Write-Host "[FAIL] found incompatible 20260322 schema column: ${col}" -ForegroundColor Red
        $Failed = $true
    }
}

Write-Host ""
if ($Failed) {
    Write-Host "preflight result: FAILED" -ForegroundColor Red
    exit 2
}
Write-Host "preflight result: OK" -ForegroundColor Green
