# Second Brain - restore a .sql.gz dump (e.g. moved from the old VPS) into an EMPTY database.
#   powershell -ExecutionPolicy Bypass -File scripts\windows\restore.ps1 -Dump C:\path\brain.sql.gz
# Run it BEFORE the first bot start (or with -Force to wipe the current database first).
# After restore the bot re-embeds all notes with the local model automatically.
param(
    [Parameter(Mandatory = $true)][string]$Dump,
    [switch]$Force
)

# Windows PowerShell 5.1: "Stop" + native stderr = terminating error; we check $LASTEXITCODE.
$ErrorActionPreference = "Continue"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
if (-not (Test-Path $Dump)) { Write-Host "[X] File not found: $Dump" -ForegroundColor Red; exit 1 }

docker compose stop bot 2>$null | Out-Null
docker compose up -d db
for ($i = 0; $i -lt 30; $i++) {
    docker exec second_brain_db pg_isready -U postgres -d second_brain *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}

$tables = docker exec second_brain_db psql -U postgres -d second_brain -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
if ([int]$tables -gt 0) {
    if (-not $Force) {
        Write-Host "[X] Database is not empty ($tables tables). Re-run with -Force to WIPE it and restore." -ForegroundColor Red
        exit 1
    }
    Write-Host "[!] Wiping current database (backup first)..." -ForegroundColor Yellow
    & "$PSScriptRoot\backup.ps1"
    docker exec second_brain_db psql -U postgres -d postgres -c "DROP DATABASE second_brain WITH (FORCE);"
    docker exec second_brain_db psql -U postgres -d postgres -c "CREATE DATABASE second_brain;"
    docker exec second_brain_db psql -U postgres -d second_brain -c "CREATE EXTENSION IF NOT EXISTS vector;"
}

docker cp $Dump second_brain_db:/tmp/restore.sql.gz
# (Arqumentin içində cüt dırnaq yoxdur — PowerShell 5.1 onları native əmrə düzgün ötürmür.)
docker exec second_brain_db bash -c 'gunzip -c /tmp/restore.sql.gz | psql -q -U postgres -d second_brain > /tmp/restore.log 2>&1; echo restore errors: $(grep -c ERROR /tmp/restore.log)'
docker exec second_brain_db rm -f /tmp/restore.sql.gz | Out-Null
$notes = docker exec second_brain_db psql -U postgres -d second_brain -tAc "SELECT count(*) FROM notes"
Write-Host "[OK] Restored. Notes: $notes" -ForegroundColor Green

docker compose up -d bot
Write-Host "Bot started - it migrates the schema and re-embeds notes in the background." -ForegroundColor Green
