# HistoryShorts — Windows Task Scheduler Setup
# Run this script ONCE as Administrator to schedule 3 uploads per day
# Usage: Right-click -> "Run with PowerShell" (as Admin)

$pythonPath = (Get-Command python).Source
$scriptPath = "C:\Users\91979\Downloads\history-shorts\main.py"
$workDir = "C:\Users\91979\Downloads\history-shorts"
$logDir = "C:\Users\91979\Downloads\history-shorts\logs"

# Create logs directory
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Task settings
$taskName = "HistoryShorts"
$description = "Automated YouTube Shorts pipeline for Buried channel"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: run main.py, log output
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $workDir

# Trigger: 3x daily (8am, 2pm, 8pm)
$triggers = @(
    New-ScheduledTaskTrigger -Daily -At "08:00AM",
    New-ScheduledTaskTrigger -Daily -At "02:00PM",
    New-ScheduledTaskTrigger -Daily -At "08:00PM"
)

# Settings
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable

# Run as current user
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Description $description `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host ""
Write-Host "=== HistoryShorts Task Scheduler Setup Complete ==="
Write-Host "Task: $taskName"
Write-Host "Schedule: 8:00 AM, 2:00 PM, 8:00 PM daily"
Write-Host "Working dir: $workDir"
Write-Host ""
Write-Host "To verify: Open Task Scheduler -> Task Scheduler Library -> HistoryShorts"
Write-Host "To run now: schtasks /run /tn HistoryShorts"
Write-Host "To disable: schtasks /change /tn HistoryShorts /disable"
