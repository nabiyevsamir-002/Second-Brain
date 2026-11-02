# Second Brain - register Windows Task Scheduler jobs (run once, in PowerShell as your user):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\install-tasks.ps1
# Creates "SecondBrain-Backup": every night at 03:15 runs backup.ps1 (keeps 14 days).
# Docker Desktop itself must start at sign-in: Docker Desktop -> Settings -> General ->
# "Start Docker Desktop when you sign in to your computer". Containers restart on their own.
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$script = Join-Path $repo "scripts\windows\backup.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 3:15am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "SecondBrain-Backup" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Second Brain nightly database backup" -Force | Out-Null

Write-Host "[OK] Task 'SecondBrain-Backup' registered (daily 03:15)." -ForegroundColor Green
Write-Host "     Test it now: Start-ScheduledTask -TaskName SecondBrain-Backup ; then check .\backups"
