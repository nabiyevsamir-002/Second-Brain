# Second Brain - database backup to .\backups (same .sql.gz format as scripts/backup.sh).
#   powershell -ExecutionPolicy Bypass -File scripts\windows\backup.ps1
# Scheduled nightly by install-tasks.ps1. Keeps the last 14 days.
# The dump is gzipped INSIDE the container and copied out with `docker cp`, because
# PowerShell 5.1 '>' redirection would re-encode it as UTF-16 and corrupt the SQL.
param([int]$RetentionDays = 14)

# Windows PowerShell 5.1: "Stop" + native stderr = terminating error; we check $LASTEXITCODE.
$ErrorActionPreference = "Continue"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
New-Item -ItemType Directory -Force backups | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "backups\second_brain_$stamp.sql.gz"

docker exec second_brain_db bash -c "set -o pipefail; pg_dump -U postgres -d second_brain | gzip > /tmp/brain_backup.sql.gz"
if ($LASTEXITCODE -ne 0) { Write-Host "[X] pg_dump failed (is the db container running?)" -ForegroundColor Red; exit 1 }
docker cp second_brain_db:/tmp/brain_backup.sql.gz $out
docker exec second_brain_db rm -f /tmp/brain_backup.sql.gz | Out-Null

$size = [math]::Round((Get-Item $out).Length / 1KB, 1)
Write-Host "[OK] Backup: $out ($size KB)" -ForegroundColor Green

Get-ChildItem backups\second_brain_*.sql.gz |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
    Remove-Item -Force
