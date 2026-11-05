#requires -Version 5.1
<#
.SYNOPSIS
    Daily consistent backup + retention for the MedRadar observation ledger.

.DESCRIPTION
    Runs, in the foreground and with exit codes:

        python -m medradar observatory backup --dest <BackupDir> --verify --prune

    The backup uses the SQLite online-backup API (never a file copy of a live WAL
    database), writes a SHA-256 MANIFEST and re-verifies it before reporting OK,
    then applies the retention policy (7 daily / 4 weekly / 6 monthly; unverifiable
    bundles are quarantined, never deleted; the newest bundle is always kept).

    This script is intended for Windows Task Scheduler (daily). It is deliberately
    one-shot: it exits when the backup is finished, so a task end can never orphan
    a long-running child. Linux operators should use a systemd timer invoking the
    same CLI command (docs/BACKUP_AND_RECOVERY.md).

    The LEDGER remains the system of record; a backup is only trustworthy when its
    manifest has been verified, which this script requires.

.PARAMETER RepoRoot
    Repository root. Default: parent of this script's directory.

.PARAMETER BackupDir
    Backup destination. Default: <RepoRoot>\data\observatory\backups

.PARAMETER LogFile
    Append one timestamped line per run. Default: <RepoRoot>\logs\backup-yyyyMMdd.log

.PARAMETER Python
    Interpreter with the medradar package. Default: python.

.PARAMETER Help
    Print usage and exit 0.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoRoot = "",
    [string]$BackupDir = "",
    [string]$LogFile = "",
    [string]$Python = "python",
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Detailed
    exit 0
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $BackupDir = Join-Path $RepoRoot "data\observatory\backups"
}
if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $stamp = (Get-Date).ToString("yyyyMMdd")
    $LogFile = Join-Path $RepoRoot "logs\backup-$stamp.log"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogFile) | Out-Null
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$arguments = @("-m", "medradar", "observatory", "backup", "--dest", $BackupDir, "--verify", "--prune", "--json")
$commandLine = "$Python $($arguments -join ' ')"

function Write-Log([string]$message) {
    $line = "$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) $message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Output $line
}

Write-Log "[backup] start: $commandLine"
Push-Location $RepoRoot
try {
    if ($PSCmdlet.ShouldProcess($BackupDir, "create verified observatory backup")) {
        $output = & $Python @arguments 2>&1
        $code = $LASTEXITCODE
        $output | ForEach-Object { Add-Content -Path $LogFile -Value $_ -Encoding UTF8 }
        Write-Log "[backup] exit: code=$code"
        if ($code -ne 0) { exit $code }
        Write-Log "[backup] done; manifest verified by the CLI (exit 0)"
        exit 0
    }
    Write-Log "[backup] WhatIf: nothing was written"
    exit 0
}
catch {
    Write-Log "[backup] FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Pop-Location
}
