# Second Brain - Windows PC setup / start (run from the repo folder in PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1 -NoSleep   # also: never sleep on AC
# Safe to re-run: it only (re)builds and starts the containers.
param([switch]$NoSleep)

# Windows PowerShell 5.1: "Stop" + native stderr = terminating error; we check $LASTEXITCODE.
$ErrorActionPreference = "Continue"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")

function Fail($msg) { Write-Host "[X] $msg" -ForegroundColor Red; exit 1 }
function Info($msg) { Write-Host "[i] $msg" -ForegroundColor Cyan }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "Git not found. Install: https://git-scm.com/download/win" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker not found. Install Docker Desktop (WSL2): https://www.docker.com/products/docker-desktop/" }

# Docker Desktop must be running (start it if needed and wait up to ~3 minutes).
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dd = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) { Info "Starting Docker Desktop..."; Start-Process $dd }
    for ($i = 0; $i -lt 36; $i++) {
        Start-Sleep -Seconds 5
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop is not running. Start it, wait for 'Engine running', re-run." }
}

# Shell scripts must keep LF endings inside Linux containers (protects old CRLF clones).
foreach ($f in @("docker\entrypoint.sh") + (Get-ChildItem scripts\*.sh | ForEach-Object { $_.FullName })) {
    $text = [IO.File]::ReadAllText((Resolve-Path $f))
    if ($text.Contains("`r`n")) {
        [IO.File]::WriteAllText((Resolve-Path $f), $text.Replace("`r`n", "`n"))
        Info "Fixed CRLF line endings: $f"
    }
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Info ".env created from .env.example. Fill TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, CLAUDE_CODE_OAUTH_TOKEN (+ EMAIL_*), save, then re-run this script."
    Start-Process notepad .env
    exit 0
}

$envText = Get-Content .env -Raw
$missing = @()
foreach ($k in "TELEGRAM_BOT_TOKEN", "ALLOWED_USER_IDS", "CLAUDE_CODE_OAUTH_TOKEN") {
    if ($envText -notmatch "(?m)^\s*$k\s*=\s*[^\s#]+") { $missing += $k }
}
if ($missing.Count -gt 0) {
    Write-Host "[!] Empty in .env: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "    Claude token: docker compose run --rm -it -e RUN_MIGRATIONS=0 bot claude setup-token" -ForegroundColor Yellow
    if ($missing -contains "TELEGRAM_BOT_TOKEN") { Fail "TELEGRAM_BOT_TOKEN is required." }
}

if ($NoSleep) {
    Info "Disabling sleep/hibernate on AC power (24/7 server)..."
    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
}

Info "Building and starting containers (first build ~5-10 min; first start downloads ~1.5GB of AI models)..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed - see the output above." }

docker compose ps
Write-Host ""
Write-Host "[OK] Started. Watch the logs (Ctrl+C to stop watching):" -ForegroundColor Green
Write-Host "     docker compose logs -f bot"
Write-Host "     Look for: providers_initialized llm=subscription ... and 'Application started'."
Write-Host "     Then in Telegram send /health to the bot."
