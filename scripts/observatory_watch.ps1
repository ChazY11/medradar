#requires -Version 5.1
<#
.SYNOPSIS
    Windows dev/ops watcher for the MedRadar Live Observatory.

.DESCRIPTION
    Runs the real collector loop in the FOREGROUND. Two modes:

      * ONE-SHOT (used by the scheduled task): pass -MaxCycles 1. Each invocation
        runs exactly one full collection pass and exits, so the supervisor
        lifecycle is clean. The Task Scheduler installer registers this mode on
        purpose: a forced task end (schtasks /End, Stop-ScheduledTask) can
        terminate this PowerShell wrapper while the python child survives, which
        is only acceptable when the child will finish its single pass and exit by
        itself. The ledger single-writer lease still refuses overlap if a trigger
        fires while a previous pass is running.

      * LONG-RUNNING (interactive use): omit -MaxCycles (0 = until interrupted).
        The collector loop keeps polling and sleeping in this foreground process.
        Do not register this mode with Task Scheduler - use the installer.

    The command is always:

        python -m medradar observatory watch --interval-minutes <N> --trigger schedule

    plus `--max-cycles <N>` in one-shot mode. This script deliberately does NOT
    use Start-Process: the collector stays a child of this PowerShell process, and
    the ledger single-writer lock (data/observatory/collector.lock) prevents a
    second collector from writing the same ledger.

    Every line the collector writes (one per pass, plus pass failures and the
    final summary) is timestamped and appended to a rotating log file. The file
    rotates by size at start-up (<LogFile>.1 keeps the previous segment); the
    default file name also changes daily. journald does not exist on Windows, so
    this file is the operator's log; the LEDGER is the system of record.

    The process gets MEDRADAR_DEPLOYMENT_STATUS=DEPLOYED_LOCAL unless the caller
    already set it, which is what `observatory deploy-status` records on this
    branch. This is the local/deployed-equivalent vocabulary from
    docs/RELIABILITY_DESIGN.md section 0 - it is NOT a claim of a service
    deployment and it must never be set to DEPLOYED_SERVICE by this script.

.PARAMETER IntervalMinutes
    Minutes between collection passes (passed to `observatory watch`). Default 60.
    In one-shot mode it only labels the pass (the process exits after one pass).

.PARAMETER LogFile
    Rotating log file path. Default: <repo>\logs\collector-yyyyMMdd.log.

.PARAMETER Python
    Interpreter that has the `medradar` package available. Default: python.

.PARAMETER MaxCycles
    Stop after N passes (0 = run until interrupted). Use 1 for one-shot mode
    (what the scheduled task registers); leave 0 for an interactive long-running
    watcher.

.PARAMETER RepoRoot
    Repository root used as the working directory. Default: the parent of this
    script's directory.

.PARAMETER MaxLogBytes
    Rotate the log file once it reaches this size. Default 10485760 (10 MiB).

.PARAMETER Help
    Print usage and exit 0 without starting the collector.

.EXAMPLE
    # long-running interactive watcher
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\observatory_watch.ps1 -IntervalMinutes 60

.EXAMPLE
    # one-shot pass (what the scheduled task runs on every trigger)
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\observatory_watch.ps1 -IntervalMinutes 360 -MaxCycles 1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\observatory_watch.ps1 -MaxCycles 2 -IntervalMinutes 1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\observatory_watch.ps1 -Help
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 10080)]
    [int]$IntervalMinutes = 60,

    [string]$LogFile = "",

    [string]$Python = "python",

    [ValidateRange(0, 1000000)]
    [int]$MaxCycles = 0,

    [string]$RepoRoot = "",

    [ValidateRange(1024, 1073741824)]
    [int]$MaxLogBytes = 10485760,

    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Usage {
    @"
MedRadar Observatory Windows watcher

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\observatory_watch.ps1 `
      [-IntervalMinutes <1..10080>] [-MaxCycles <0..>] [-LogFile <path>] `
      [-Python <exe>] [-RepoRoot <path>] [-MaxLogBytes <bytes>] [-WhatIf] [-Help]

Modes:
  * One-shot (scheduled task): -MaxCycles 1 -> one full pass per trigger, then exit.
    This is what scripts\install_windows_task.ps1 registers.
  * Long-running (interactive): default -MaxCycles 0 -> keep polling until interrupted.
    A Task Scheduler trigger cannot cleanly stop a long-running child, so do not
    register this mode with Task Scheduler.

Behavior:
  * Runs `python -m medradar observatory watch --interval-minutes <N> --trigger schedule`
    in the foreground (no Start-Process).
  * Appends every collector line to a rotating log (default logs\collector-yyyyMMdd.log).
  * Sets MEDRADAR_DEPLOYMENT_STATUS=DEPLOYED_LOCAL for the child unless already set.
  * Exits with the collector's exit code (0 only on a clean stop).
  * -WhatIf prints the exact command and exits 0 without starting anything.

Install as a scheduled task (WhatIf first):
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -WhatIf
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1
"@ | Write-Host
}

if ($Help) {
    Write-Usage
    exit 0
}

# ---------------------------------------------------------------- resolve paths
if (-not $RepoRoot) {
    if ($PSScriptRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    } else {
        $RepoRoot = (Get-Location).Path
    }
}
if (-not (Test-Path -LiteralPath $RepoRoot)) {
    Write-Error -Message "repository root not found: $RepoRoot" -ErrorAction Continue
    exit 1
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

if (-not $LogFile) {
    $LogFile = Join-Path $RepoRoot ("logs\collector-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
} elseif (-not [System.IO.Path]::IsPathRooted($LogFile)) {
    $LogFile = Join-Path $RepoRoot $LogFile
}
$logDirectory = Split-Path -Parent $LogFile
if (-not $logDirectory) { $logDirectory = $RepoRoot }

# ------------------------------------------------------- validate interpreter
$pythonCommand = Get-Command -Name $Python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    Write-Error -Message ("python not found: '{0}'. Use -Python to point at the interpreter " +
                 "that has the medradar package installed (for example the venv python.exe)." -f $Python) `
                 -ErrorAction Continue
    exit 1
}

# ------------------------------------------------------------ compose arguments
$collectorArguments = @(
    "-m", "medradar", "observatory", "watch",
    "--interval-minutes", [string]$IntervalMinutes,
    "--trigger", "schedule"
)
if ($MaxCycles -gt 0) {
    $collectorArguments += @("--max-cycles", [string]$MaxCycles)
}

$commandForDisplay = "{0} {1}" -f $Python, ($collectorArguments -join " ")

# -WhatIf must genuinely change nothing: no directory creation, no child process.
if ($WhatIfPreference) {
    $modeText = if ($MaxCycles -gt 0) { "one-shot: $MaxCycles pass(es) then exit" } else { "long-running: poll until interrupted" }
    Write-Host "[WhatIf] would run in the foreground (no Start-Process):"
    Write-Host ("    " + $commandForDisplay)
    Write-Host ("[WhatIf] mode              : {0}" -f $modeText)
    Write-Host ("[WhatIf] working directory: {0}" -f $RepoRoot)
    Write-Host ("[WhatIf] rotating log      : {0}" -f $LogFile)
    Write-Host ("[WhatIf] MEDRADAR_DEPLOYMENT_STATUS: {0}" -f `
        $(if ($env:MEDRADAR_DEPLOYMENT_STATUS) { $env:MEDRADAR_DEPLOYMENT_STATUS } else { "DEPLOYED_LOCAL" }))
    Write-Host "[WhatIf] no collector started and nothing was written."
    exit 0
}

# ---------------------------------------------------------------- log rotation
try {
    if (-not (Test-Path -LiteralPath $logDirectory)) {
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    }
    if (Test-Path -LiteralPath $LogFile) {
        $length = (Get-Item -LiteralPath $LogFile).Length
        if ($length -ge $MaxLogBytes) {
            $rotated = "$LogFile.1"
            Move-Item -LiteralPath $LogFile -Destination $rotated -Force
        }
    }
} catch {
    Write-Error -Message ("cannot prepare log directory '{0}': {1}" -f $logDirectory, $_.Exception.Message) `
        -ErrorAction Continue
    exit 1
}

function Add-LogLine {
    param([string]$Text)
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $line = "{0} {1}" -f $timestamp, $Text
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

# ----------------------------------------------------------- deployment status
if (-not $env:MEDRADAR_DEPLOYMENT_STATUS) {
    $env:MEDRADAR_DEPLOYMENT_STATUS = "DEPLOYED_LOCAL"
}
# Unbuffered child output so each pass appears in the log while it happens.
if (-not $env:PYTHONUNBUFFERED) {
    $env:PYTHONUNBUFFERED = "1"
}

Add-LogLine ("[watcher] start: {0}" -f $commandForDisplay)
Add-LogLine ("[watcher] repo={0} log={1} deployment_status={2} interval_minutes={3} max_cycles={4}" -f `
    $RepoRoot, $LogFile, $env:MEDRADAR_DEPLOYMENT_STATUS, $IntervalMinutes, $MaxCycles)

# ------------------------------------------------------ foreground execution
$exitCode = 1
Push-Location -LiteralPath $RepoRoot
try {
    # 2>&1 merges the collector's stderr (its per-pass log) into this pipeline.
    # ErrorActionPreference is lowered only around the native child: native stderr
    # records must not be promoted to terminating errors.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Python @collectorArguments 2>&1 | ForEach-Object {
            $lineText = if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.ToString()
            } else {
                [string]$_
            }
            Add-LogLine $lineText
        }
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) { $exitCode = 0 }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
} catch {
    $message = $_.Exception.Message
    try { Add-LogLine ("[watcher] collector invocation failed: {0}" -f $message) } catch { }
    Write-Error -Message ("collector invocation failed: {0}" -f $message) -ErrorAction Continue
    $exitCode = 1
} finally {
    Pop-Location
}

Add-LogLine ("[watcher] exit: code={0} at={1}" -f $exitCode, (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
if ($exitCode -ne 0) {
    Write-Error -Message ("collector exited with code {0}; see {1}" -f $exitCode, $LogFile) -ErrorAction Continue
    exit $exitCode
}
exit 0

