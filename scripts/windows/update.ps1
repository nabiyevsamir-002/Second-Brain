# Second Brain - update to the latest code and rebuild the bot:
#   powershell -ExecutionPolicy Bypass -File scripts\windows\update.ps1
# Windows PowerShell 5.1: "Stop" + native stderr = terminating error; we check $LASTEXITCODE.
$ErrorActionPreference = "Continue"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")

git pull --ff-only
if ($LASTEXITCODE -ne 0) { Write-Host "[X] git pull failed (local changes?)." -ForegroundColor Red; exit 1 }

docker compose up -d --build bot
if ($LASTEXITCODE -ne 0) { Write-Host "[X] rebuild failed." -ForegroundColor Red; exit 1 }
docker image prune -f | Out-Null
docker compose ps
Write-Host "[OK] Updated. Logs: docker compose logs -f bot" -ForegroundColor Green
