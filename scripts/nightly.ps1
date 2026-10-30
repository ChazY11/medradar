<#
.SYNOPSIS
    MedRadar nightly pipeline: collect -> trade -> replay -> analyze -> report -> stats.

.DESCRIPTION
    Runs the whole weekly/nightly refresh as one command and appends every
    step's output to a UTF-8 log (``out/nightly.log`` by default). A failing
    stage is logged and the pipeline continues: a broken price feed must not
    stop the FDA collectors from refreshing, and a partial report beats no
    report.

    Stage order mirrors ``python -m medradar run --with-trade --with-replay``:
    trade and replay run *before* ``analyze`` so ``out/metrics.json`` (and the
    report built from it) can embed their output. ``report`` then publishes the
    artefacts into ``out/`` and mirrors the dashboard into ``docs/`` for GitHub
    Pages.

    The final ``stats`` stage writes ``out/data_stats.json`` and appends/replaces
    today's row in the growth table of ``docs/DATA.md`` (between
    ``<!-- growth:start -->`` / ``<!-- growth:end -->``), so data scale is
    tracked without manual copy-paste.

    Exit code: 0 when ``collect``/``analyze``/``report`` all succeeded (or were
    skipped), 1 when one of those core stages failed. Per-stage statuses are
    always written to ``out/nightly_status.json``.

.PARAMETER Python
    Python executable to use (default: ``python`` from PATH).

.PARAMETER Database
    SQLite database path, relative to the repo root (default: data/medradar.sqlite).

.PARAMETER Months
    Look-back window for the collectors; existing rows are upserted, so this is
    an incremental refresh (default: 24).

.PARAMETER OutDir
    Output directory for metrics/report/replay artefacts (default: out).

.PARAMETER Log
    Log file path relative to the repo root (default: out/nightly.log).

.PARAMETER ReplayDays
    Replay window in days (default: 30).

.PARAMETER ReplayCosts
    Comma separated cost tiers in bps for replay (default: 10,25,50).

.PARAMETER Offline
    Replay cached HTTP responses / cached price bars only (no new requests).

.PARAMETER SkipCollect
    Do not run the collectors.

.PARAMETER SkipTrade
    Skip the paper-trading study.

.PARAMETER SkipReplay
    Skip the replay timeline build.

.PARAMETER SkipAnalyze
    Skip metrics computation (report then uses the existing metrics.json).

.PARAMETER SkipReport
    Skip report rendering.

.PARAMETER SkipStats
    Skip the data-scale snapshot and DATA.md growth row.

.PARAMETER NoDataMd
    Write out/data_stats.json but do not touch docs/DATA.md.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/nightly.ps1

.EXAMPLE
    ./scripts/nightly.ps1 -Months 36 -Offline -NoDataMd
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Database = "data/medradar.sqlite",
    [int]$Months = 24,
    [string]$OutDir = "out",
    [string]$Log = "out/nightly.log",
    [int]$ReplayDays = 30,
    [string]$ReplayCosts = "10,25,50",
    [switch]$Offline,
    [switch]$SkipCollect,
    [switch]$SkipTrade,
    [switch]$SkipReplay,
    [switch]$SkipAnalyze,
    [switch]$SkipReport,
    [switch]$SkipStats,
    [switch]$NoDataMd
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$logFile = [System.IO.Path]::GetFullPath($Log)
$outPath = [System.IO.Path]::GetFullPath($OutDir)
$dbPath = [System.IO.Path]::GetFullPath($Database)
$dataMd = [System.IO.Path]::GetFullPath("docs/DATA.md")
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logFile) | Out-Null
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

# Python prints UTF-8; make sure both Windows PowerShell 5.1 and pwsh 7 decode it.
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    [System.IO.File]::AppendAllText($logFile, $line + [Environment]::NewLine, $utf8NoBom)
    Write-Host $line
}

function Write-LogBlock([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return }
    [System.IO.File]::AppendAllText(
        $logFile,
        $Text.TrimEnd() + [Environment]::NewLine,
        $utf8NoBom
    )
}

$startedAt = Get-Date
Write-Log ("=== MedRadar nightly start ({0}) ===" -f $startedAt.ToString("yyyy-MM-dd HH:mm:ss"))
Write-Log ("repo={0}" -f $repoRoot)
Write-Log ("python={0} db={1} out={2}" -f $Python, $dbPath, $outPath)

try {
    $pythonVersion = & $Python --version 2>&1
} catch {
    Write-Log ("ERROR cannot execute python ({0}): {1}" -f $Python, $_.Exception.Message)
    Pop-Location
    exit 1
}
if ($LASTEXITCODE -ne 0) {
    Write-Log ("ERROR python is not usable: {0}" -f ($pythonVersion -join " "))
    Pop-Location
    exit 1
}
Write-Log ("python version: {0}" -f ($pythonVersion -join " "))

$offlineFlag = @()
if ($Offline) { $offlineFlag = @("--offline") }

$steps = @()
if (-not $SkipCollect) {
    $steps += @{
        name = "collect"
        args = @("-m", "medradar", "collect",
            "--sources", "device,drug,trials,nmpa",
            "--months", $Months,
            "--db", $dbPath) + $offlineFlag
    }
}
if (-not $SkipTrade) {
    $steps += @{
        name = "trade"
        args = @("-m", "medradar", "trade",
            "--db", $dbPath,
            "--out-dir", $outPath)
    }
}
if (-not $SkipReplay) {
    $steps += @{
        name = "replay"
        args = @("-m", "medradar", "replay",
            "--db", $dbPath,
            "--days", $ReplayDays,
            "--costs", $ReplayCosts,
            "--out-dir", (Join-Path $outPath "replay")) + $offlineFlag
    }
}
if (-not $SkipAnalyze) {
    $steps += @{
        name = "analyze"
        args = @("-m", "medradar", "analyze",
            "--db", $dbPath,
            "--out", (Join-Path $outPath "metrics.json"))
    }
}
if (-not $SkipReport) {
    $steps += @{
        name = "report"
        args = @("-m", "medradar", "report",
            "--metrics", (Join-Path $outPath "metrics.json"),
            "--out-dir", $outPath)
    }
}

$results = @()
foreach ($step in $steps) {
    $name = $step.name
    Write-Log ("--- {0} ---" -f $name)
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $output = & $Python @($step.args) 2>&1 | Out-String
    $code = $LASTEXITCODE
    $watch.Stop()
    Write-LogBlock $output
    $seconds = [math]::Round($watch.Elapsed.TotalSeconds, 1)
    if ($code -eq 0) {
        Write-Log ("OK   {0} ({1}s)" -f $name, $seconds)
    } else {
        Write-Log ("WARN {0} exited {1} ({2}s); continuing" -f $name, $code, $seconds)
    }
    $results += [pscustomobject]@{
        name = $name
        exit_code = $code
        seconds = $seconds
    }
}

# ---------------------------------------------------------------- data statistics
if (-not $SkipStats) {
    Write-Log "--- stats ---"
    $statsStarted = Get-Date
    $noDataMdLiteral = if ($NoDataMd) { "True" } else { "False" }
    $statsCode = @"
import json
from pathlib import Path
from medradar.db import DB
from medradar.stats_cmd import append_growth_row, data_stats, update_stats_markdown

db_path = Path(r"$($dbPath -replace '\\', '/')")
out_dir = Path(r"$($outPath -replace '\\', '/')")
data_md = Path(r"$($dataMd -replace '\\', '/')")

with DB(db_path) as db:
    stats = data_stats(db)

out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "data_stats.json").write_text(
    json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8"
)
print(json.dumps({
    "events": stats["events"]["total"],
    "earliest": stats["events"]["earliest"],
    "latest": stats["events"]["latest"],
    "db": stats["db"]["size_human"],
    "errors": stats["errors"],
}, ensure_ascii=False))
if not $noDataMdLiteral and data_md.exists():
    print(json.dumps(update_stats_markdown(stats, data_md), ensure_ascii=False))
    print(json.dumps(append_growth_row(stats, data_md, note="nightly"), ensure_ascii=False))
"@
    $statsOutput = $statsCode | & $Python - 2>&1 | Out-String
    $statsCode2 = $LASTEXITCODE
    $statsSeconds = [math]::Round(((Get-Date) - $statsStarted).TotalSeconds, 1)
    Write-LogBlock $statsOutput
    if ($statsCode2 -eq 0) {
        Write-Log ("OK   stats ({0}s)" -f $statsSeconds)
    } else {
        Write-Log ("WARN stats exited {0} ({1}s); continuing" -f $statsCode2, $statsSeconds)
    }
    $results += [pscustomobject]@{
        name = "stats"
        exit_code = $statsCode2
        seconds = $statsSeconds
    }
}

# ---------------------------------------------------------------------- summary
$finishedAt = Get-Date
$failed = @($results | Where-Object { $_.exit_code -ne 0 })
$core = @("collect", "analyze", "report")
$coreFailed = @($results | Where-Object { $_.exit_code -ne 0 -and $core -contains $_.name })
$summary = [ordered]@{
    started_at = $startedAt.ToString("o")
    finished_at = $finishedAt.ToString("o")
    seconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 1)
    repo = $repoRoot
    python = $Python
    db = $dbPath
    log = $logFile
    offline = [bool]$Offline
    steps = @($results)
    failed = @($failed | ForEach-Object { $_.name })
    core_failed = @($coreFailed | ForEach-Object { $_.name })
}
$statusPath = Join-Path $outPath "nightly_status.json"
[System.IO.File]::WriteAllText($statusPath, ($summary | ConvertTo-Json -Depth 5), $utf8NoBom)
Write-Log ("summary -> {0}" -f $statusPath)
Write-Log ("=== nightly done in {0}s: {1} ok, {2} failed ===" -f `
    $summary.seconds, ($results.Count - $failed.Count), $failed.Count)

Pop-Location
if ($coreFailed.Count -gt 0) { exit 1 }
exit 0
