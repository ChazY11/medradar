#requires -Version 5.1
<#
.SYNOPSIS
    Remove the MedRadarObservatory Windows scheduled task.

.DESCRIPTION
    Symmetrical counterpart of scripts\install_windows_task.ps1. It removes ONLY
    the scheduled task named -TaskName (default MedRadarObservatory); it never
    enumerates or touches other tasks, never elevates and never deletes ledger
    data.

    -WhatIf prints the exact removal commands and changes nothing (no task is
    stopped or deleted, no file is written).

    Ownership safety: the task registered by the installer carries the marker
    "MedRadarObservatory collector managed by scripts/install_windows_task.ps1"
    in its Description. If a task with the same name exists without that marker,
    this script REFUSES to remove it unless -Force is passed (a name collision is
    not an invitation to delete somebody else's task).

    Graceful stop first (recommended): pause the collector in the ledger, let the
    current pass finish, then remove the task. Removing a RUNNING task stops the
    process abruptly; the collector's lock heartbeat then goes stale and the next
    collector takes over after ~90 s, but a clean stop is always preferable:

        python -m medradar observatory pause --reason "decommissioning this host"
        # wait for the current pass to end (observatory status --json)
        powershell -File scripts\uninstall_windows_task.ps1

.PARAMETER TaskName
    Scheduled task name to remove. Default MedRadarObservatory.

.PARAMETER Force
    Remove the task even if it does not carry the ownership marker. Only use after
    verifying the task really is this project's task.

.PARAMETER Help
    Print usage and exit 0.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 -WhatIf

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 -Status
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "MedRadarObservatory",
    [switch]$Status,
    [switch]$Force,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$OwnershipMarker = "MedRadarObservatory collector managed by scripts/install_windows_task.ps1"

function Write-Usage {
    @"
MedRadar Observatory scheduled-task uninstaller

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 [-WhatIf] [-Force]
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 -Status
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 -Help

Behavior:
  * Removes ONLY task '$TaskName'. No other task is enumerated or touched.
  * -WhatIf prints the exact commands and changes nothing.
  * Refuses to remove a task without the ownership marker unless -Force.
  * Never elevates. Never deletes ledger data (data\observatory\ stays).
  * Prefer `observatory pause` and a completed pass before removing a running task.
"@ | Write-Host
}

function Write-Refusal {
    param([string]$Message)
    Write-Error -Message $Message -ErrorAction Continue
    Write-Host "Refusing to continue. No task was changed." -ForegroundColor Yellow
}

if ($Help) {
    Write-Usage
    exit 0
}

foreach ($cmdlet in @("Get-ScheduledTask", "Unregister-ScheduledTask", "Stop-ScheduledTask")) {
    if (-not (Get-Command -Name $cmdlet -ErrorAction SilentlyContinue)) {
        Write-Error -Message ("ScheduledTasks module (cmdlet '{0}') is not available in this PowerShell. " +
                              "Use Windows PowerShell 5.1 on Windows 8/Server 2012 or later." -f $cmdlet) `
                    -ErrorAction Continue
        exit 1
    }
}

$existingTask = $null
try {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {
    $existingTask = $null
}

if ($Status) {
    if (-not $existingTask) {
        Write-Host ("Task '{0}' is NOT registered." -f $TaskName)
        exit 0
    }
    $owned = ([string]$existingTask.Description).Contains($OwnershipMarker)
    Write-Host ("TaskName            : {0}" -f $TaskName)
    Write-Host ("State               : {0}" -f ([string]$existingTask.State))
    Write-Host ("OwnedByThisInstaller: {0}" -f ([string]$owned))
    Write-Host ("Description         : {0}" -f ([string]$existingTask.Description))
    exit 0
}

if (-not $existingTask) {
    Write-Host ("Task '{0}' is not registered; nothing to remove." -f $TaskName)
    exit 0
}

$owned = ([string]$existingTask.Description).Contains($OwnershipMarker)
if (-not $owned -and -not $Force) {
    Write-Refusal ("Task '$TaskName' exists but does not carry the ownership marker " +
                   "('$OwnershipMarker'). It may belong to another project. " +
                   "Refusing to remove it without -Force. This script never touches other tasks.")
    exit 2
}

$isRunning = ([string]$existingTask.State -eq "Running")
$stopCommand = "Stop-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
$unregisterCommand = "Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"

if ($WhatIfPreference) {
    Write-Host ("[WhatIf] would remove the scheduled task; nothing was changed (owned={0}, running={1}):" -f `
                ([string]$owned), ([string]$isRunning))
    if ($isRunning) {
        Write-Host ("    " + $stopCommand)
    }
    Write-Host ("    " + $unregisterCommand)
    Write-Host ("[WhatIf] equivalent for `"schtasks`" users: schtasks.exe /Delete /TN `"{0}`" /F" -f $TaskName)
    Write-Host ("[WhatIf] ledger data under data\observatory\ is NOT touched")
    exit 0
}

if ($isRunning) {
    Write-Host ("WARNING: task '{0}' is currently RUNNING. It will be stopped abruptly; the collector " +
                "lock goes stale and the next collector takes over after ~90 s. " +
                "Prefer `observatory pause` + a completed pass first." -f $TaskName) -ForegroundColor Yellow
}

if (-not $PSCmdlet.ShouldProcess($TaskName, "Unregister scheduled task")) { exit 0 }

try {
    if ($isRunning) {
        Stop-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
} catch {
    Write-Error -Message ("failed to remove task '{0}': {1}" -f $TaskName, $_.Exception.Message) -ErrorAction Continue
    Write-Host "This script does not elevate. If Windows reports AccessDenied, ask an administrator." -ForegroundColor Yellow
    exit 1
}

Write-Host ("Task '{0}' removed. Ledger data under data\observatory\ was not touched." -f $TaskName)
Write-Host "The collector is now unsupervised on this host. Deployment status is back to NOT_DEPLOYED for this host."
exit 0
