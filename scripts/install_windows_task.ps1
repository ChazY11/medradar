#requires -Version 5.1
<#
.SYNOPSIS
    Register / update / inspect the MedRadarObservatory Windows scheduled task.

.DESCRIPTION
    Supervised Windows operation for the Live Observatory: a Task Scheduler task
    named "MedRadarObservatory" runs scripts\observatory_watch.ps1 every N minutes
    (default 360). Each trigger runs exactly ONE complete collection pass and
    exits:

        python -m medradar observatory watch --interval-minutes <N>
            --trigger schedule --max-cycles 1

    This is deliberately a one-shot timer, not a long-running watcher: on Windows
    a forced task end (schtasks /End, Stop-ScheduledTask) can terminate the
    PowerShell wrapper while the child `python -m medradar observatory watch`
    survives and keeps the ledger lease. A one-shot pass always exits by itself,
    so the supervisor lifecycle stays clean; StartWhenAvailable covers a missed
    slot and MultipleInstances IgnoreNew + the ledger lease prevent overlap.

    The long-running watcher (observatory_watch.ps1 without -MaxCycles) remains
    available for interactive terminal use, but the scheduled task does NOT use
    it (see deploy/windows/README.md for both modes).

    The task is registered for the CURRENT user (interactive token, RunLevel
    Limited) and is never elevated by this script.

    Safety properties:
      * -WhatIf prints the exact Register-ScheduledTask / schtasks command and
        changes nothing at all (no task, no file, no elevation prompt).
      * The task carries an ownership marker in its Description. If a task with
        the same name exists without that marker, the script REFUSES to touch it
        unless -Force is given: a name collision must never silently overwrite
        somebody else's task.
      * The script only ever references the single task name passed/given here
        (-TaskName). It never enumerates, modifies or deletes other tasks.
      * It never requests elevation (no Start-Process -Verb RunAs, no UAC).
        Creating a task for the current user does not require administrator
        rights; if Windows reports AccessDenied, ask an administrator to run the
        same command in your session context - do not elevate this script.
      * -StartWhenAvailable means a slot missed while the machine was off runs
        once the task becomes available; MultipleInstances IgnoreNew means a
        second instance is never started while the first is still running (the
        ledger lock is still the authoritative single-writer guard, so even a
        trigger that fires while a previous one-shot pass is still finishing
        cannot double-write).

    This script creates observability, not a deployment claim: the collector sets
    MEDRADAR_DEPLOYMENT_STATUS=DEPLOYED_LOCAL (see observatory_watch.ps1), which
    is NOT a service deployment.

.PARAMETER IntervalMinutes
    Task repetition interval in minutes. Default 360 (6 hours). The action also
    passes the same value to observatory_watch.ps1 as -IntervalMinutes (used for
    the pass interval/log bookkeeping); each trigger runs exactly one pass
    (-MaxCycles 1).

.PARAMETER TaskName
    Scheduled task name. Default MedRadarObservatory.

.PARAMETER Python
    Interpreter passed through to observatory_watch.ps1. Default python.

.PARAMETER WatcherPath
    Path to observatory_watch.ps1. Default: next to this script.

.PARAMETER Uninstall
    Remove the task (only if this installer owns it, unless -Force).

.PARAMETER Status
    Read-only: print whether the task exists, whether this installer owns it and
    its last/next run information. Never modifies anything.

.PARAMETER Force
    Allow modifying/removing a task that lacks the ownership marker. Only use
    after verifying the task really is this project's task.

.PARAMETER Help
    Print usage and exit 0.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -WhatIf

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 10080)]
    [int]$IntervalMinutes = 360,

    [string]$TaskName = "MedRadarObservatory",

    [string]$Python = "python",

    [string]$WatcherPath = "",

    [switch]$Uninstall,

    [switch]$Status,

    [switch]$Force,

    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$OwnershipMarker = "MedRadarObservatory collector managed by scripts/install_windows_task.ps1"
$TaskDescription = "$OwnershipMarker - do not edit by hand; use scripts/install_windows_task.ps1 -Uninstall."

function Write-Usage {
    @"
MedRadar Observatory scheduled-task installer (Task Scheduler, current user)

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 [-WhatIf]
      [-IntervalMinutes <1..10080>] [-Python <exe>] [-TaskName <name>] [-Force]

  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall [-WhatIf] [-Force]
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Help

Behavior:
  * Registers task '$TaskName' for the CURRENT user (interactive, RunLevel Limited).
  * The action runs ONE pass per trigger: powershell -NoProfile -ExecutionPolicy
    Bypass -File <repo>\scripts\observatory_watch.ps1 -IntervalMinutes <N>
    -MaxCycles 1 -Python <exe>
  * -StartWhenAvailable, MultipleInstances IgnoreNew, restart-on-failure.
  * One-shot per trigger on purpose: a forced Task Scheduler end can terminate the
    PowerShell wrapper while a long-running python collector survives, so the
    scheduled mode never starts one. The ledger lease still prevents overlap.
  * -WhatIf prints the exact command and creates/removes nothing.
  * Refuses to modify a task it does not own unless -Force; never elevates and
    never touches other tasks.
  * Doesn't prove a deployment: after registration the deployment status is
    DEPLOYED_LOCAL only (the ledger-level vocabulary), not DEPLOYED_SERVICE.
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

# ------------------------------------------------------- scheduled-task cmdlets
foreach ($cmdlet in @("Get-ScheduledTask", "Register-ScheduledTask", "New-ScheduledTaskAction",
                      "New-ScheduledTaskTrigger", "New-ScheduledTaskSettingsSet",
                      "New-ScheduledTaskPrincipal")) {
    if (-not (Get-Command -Name $cmdlet -ErrorAction SilentlyContinue)) {
        Write-Error -Message ("ScheduledTasks module (cmdlet '{0}') is not available in this PowerShell. " +
                              "Use Windows PowerShell 5.1 on Windows 8/Server 2012 or later." -f $cmdlet) `
                    -ErrorAction Continue
        exit 1
    }
}

# ---------------------------------------------------------------- resolve target
if (-not $WatcherPath) {
    if ($PSScriptRoot) {
        $WatcherPath = Join-Path $PSScriptRoot "observatory_watch.ps1"
    } else {
        $WatcherPath = Join-Path (Get-Location).Path "observatory_watch.ps1"
    }
}
if (-not (Test-Path -LiteralPath $WatcherPath)) {
    Write-Error -Message ("watcher script not found: {0}" -f $WatcherPath) -ErrorAction Continue
    exit 1
}
$WatcherPath = (Resolve-Path -LiteralPath $WatcherPath).Path

$userDomain = if ($env:USERDOMAIN) { $env:USERDOMAIN } else { $env:COMPUTERNAME }
$currentUser = "{0}\{1}" -f $userDomain, $env:USERNAME

# ---------------------------------------------------------- existing task state
$existingTask = $null
$existingOwned = $false
try {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {
    $existingTask = $null
}
if ($existingTask) {
    $description = [string]$existingTask.Description
    $existingOwned = ($description.Length -gt 0) -and $description.Contains($OwnershipMarker)
}

# ---------------------------------------------------------------- build objects
$startAt = (Get-Date).AddMinutes(1)
# One-shot pass per trigger (-MaxCycles 1): a Task Scheduler trigger cannot cleanly
# stop a long-running child python process, so the scheduled mode never starts one.
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -IntervalMinutes {1} -MaxCycles 1 -Python "{2}"' -f `
               $WatcherPath, $IntervalMinutes, $Python)
$trigger = New-ScheduledTaskTrigger -Once -At $startAt `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

$registerCommand = @"
Register-ScheduledTask -TaskName '$TaskName' -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '$($action.Arguments)') -Trigger (New-ScheduledTaskTrigger -Once -At '$($startAt.ToString("s"))' -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)) -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)) -Principal (New-ScheduledTaskPrincipal -UserId '$currentUser' -LogonType Interactive -RunLevel Limited) -Description '$TaskDescription' -Force
"@

# ---------------------------------------------------------------------- Status
if ($Status) {
    if (-not $existingTask) {
        Write-Host ("Task '{0}' is NOT registered. Nothing is scheduled." -f $TaskName)
        Write-Host "Install with: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -WhatIf"
        exit 0
    }
    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host ("TaskName            : {0}" -f $TaskName)
    Write-Host ("Registered          : True")
    Write-Host ("OwnedByThisInstaller: {0}" -f ([string]$existingOwned))
    Write-Host ("Description         : {0}" -f ([string]$existingTask.Description))
    Write-Host ("State               : {0}" -f ([string]$existingTask.State))
    if ($taskInfo) {
        Write-Host ("LastRunTime         : {0}" -f ([string]$taskInfo.LastRunTime))
        Write-Host ("LastTaskResult      : {0}" -f ([string]$taskInfo.LastTaskResult))
        Write-Host ("NextRunTime         : {0}" -f ([string]$taskInfo.NextRunTime))
        Write-Host ("NumberOfMissedRuns  : {0}" -f ([string]$taskInfo.NumberOfMissedRuns))
    }
    foreach ($taskAction in @($existingTask.Actions)) {
        Write-Host ("Action              : {0} {1}" -f ([string]$taskAction.Execute), ([string]$taskAction.Arguments))
    }
    $actionText = [string](@($existingTask.Actions)[0].Arguments)
    Write-Host ("Mode                : {0}" -f $(if ($actionText -match '-MaxCycles') { "one-shot pass per trigger (-MaxCycles 1)" } else { "long-running watcher (no -MaxCycles; interactive mode)" }))
    if (-not $existingOwned) {
        Write-Host "WARNING: this task was NOT created by this installer; -Uninstall refuses without -Force." -ForegroundColor Yellow
    }
    Write-Host "Ledger evidence: python -m medradar observatory status --json  (check heartbeat/last_run_at)"
    exit 0
}

# ------------------------------------------------------------------- Uninstall
if ($Uninstall) {
    if (-not $existingTask) {
        Write-Host ("Task '{0}' is not registered; nothing to remove." -f $TaskName)
        exit 0
    }
    if (-not $existingOwned -and -not $Force) {
        Write-Refusal ("Task '$TaskName' exists but does not carry the ownership marker " +
                       "('$OwnershipMarker'). It may belong to another project. " +
                       "Refusing to remove it without -Force.")
        exit 2
    }
    if ($WhatIfPreference) {
        Write-Host "[WhatIf] would remove the task (owned=$([string]$existingOwned)); nothing was changed:"
        if ([string]$existingTask.State -eq "Running") {
            Write-Host ("    Stop-ScheduledTask -TaskName '{0}' -Confirm:`$false" -f $TaskName)
        }
        Write-Host ("    Unregister-ScheduledTask -TaskName '{0}' -Confirm:`$false" -f $TaskName)
        Write-Host ("[WhatIf] equivalent: schtasks.exe /Delete /TN ""{0}"" /F" -f $TaskName)
        exit 0
    }
    if (-not $PSCmdlet.ShouldProcess($TaskName, "Unregister scheduled task")) { exit 0 }
    try {
        if ([string]$existingTask.State -eq "Running") {
            Stop-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    } catch {
        Write-Error -Message ("failed to remove task '{0}': {1}" -f $TaskName, $_.Exception.Message) -ErrorAction Continue
        Write-Host "This script does not elevate. If Windows reports AccessDenied, ask an administrator." -ForegroundColor Yellow
        exit 1
    }
    Write-Host ("Task '{0}' removed. Ledger data under data\observatory\ is untouched." -f $TaskName)
    exit 0
}

# --------------------------------------------------------------------- Install
if ($existingTask -and -not $existingOwned -and -not $Force) {
    Write-Refusal ("A scheduled task named '$TaskName' already exists but does not carry the " +
                   "ownership marker ('$OwnershipMarker'). It may belong to another project. " +
                   "Refusing to modify it without -Force. This script never touches other tasks.")
    exit 2
}

if ($WhatIfPreference) {
    Write-Host "[WhatIf] would register/update the scheduled task; nothing was changed:"
    Write-Host ""
    Write-Host $registerCommand
    Write-Host ""
    Write-Host ("[WhatIf] equivalent for `"schtasks /Query`" users: schtasks.exe /Query /TN `"{0}`" /V /FO LIST" -f $TaskName)
    Write-Host ("[WhatIf] note: schtasks.exe /Create cannot express StartWhenAvailable/IgnoreNew, " +
                "so the exact command above uses Register-ScheduledTask.")
    Write-Host ""
    Write-Host ("[WhatIf] task name          : {0}" -f $TaskName)
    Write-Host ("[WhatIf] mode               : one-shot pass per trigger (-MaxCycles 1)")
    Write-Host ("[WhatIf] run as             : {0} (interactive, RunLevel Limited - never elevated)" -f $currentUser)
    Write-Host ("[WhatIf] watcher            : {0}" -f $WatcherPath)
    Write-Host ("[WhatIf] repetition         : every {0} minutes (StartWhenAvailable)" -f $IntervalMinutes)
    Write-Host ("[WhatIf] existing task      : {0}" -f $(if ($existingTask) { "present (owned=" + [string]$existingOwned + ")" } else { "none" }))
    Write-Host ("[WhatIf] ownership marker   : {0}" -f $OwnershipMarker)
    Write-Host "[WhatIf] nothing was registered, no file was written and no task was started."
    exit 0
}

if (-not $PSCmdlet.ShouldProcess($TaskName, "Register/update scheduled task")) { exit 0 }

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Description $TaskDescription -Force | Out-Null
} catch {
    Write-Error -Message ("failed to register task '{0}': {1}" -f $TaskName, $_.Exception.Message) -ErrorAction Continue
    Write-Host "" 
    Write-Host "This script never elevates. Creating a task for the current user normally does not" -ForegroundColor Yellow
    Write-Host "require administrator rights; if Windows reports AccessDenied, ask an administrator." -ForegroundColor Yellow
    exit 1
}

Write-Host ("Task '{0}' registered for {1}, repeating every {2} minute(s); each trigger runs ONE collection pass." -f $TaskName, $currentUser, $IntervalMinutes)
Write-Host ("Action: powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""{0}"" -IntervalMinutes {1} -MaxCycles 1 -Python ""{2}""" -f `
    $WatcherPath, $IntervalMinutes, $Python)
Write-Host ""
Write-Host "Verify:"
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "  python -m medradar observatory status --json"
Write-Host "Logs: <repo>\logs\collector-yyyyMMdd.log; ledger lock: data\observatory\collector.lock"
Write-Host "Remove: scripts\install_windows_task.ps1 -Uninstall (or scripts\uninstall_windows_task.ps1)"
exit 0
