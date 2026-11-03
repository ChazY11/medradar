# MedRadar Observatory — Windows deployment (Task Scheduler)

Templates + local scripts only. Running them creates **supervision**, not a deployment claim:
the collector reports `deployment_status=DEPLOYED_LOCAL` (docs/RELIABILITY_DESIGN.md §0), which
means "a local operator runs this on their machine" — **not** `DEPLOYED_SERVICE`. Until a
supervisor is actually installed on an authorised always-on host, the production/project-level
status is `NOT_DEPLOYED` (see docs/DEPLOYMENT.md, "NOT DEPLOYED"). A local install is recorded
explicitly with `observatory deploy-status` and never inferred from these files.

Read this together with docs/LIVE_OBSERVATORY.md §4.2 (Windows 计划任务), which documents the
same mode, and docs/DEPLOYMENT.md (the full operator runbook).

## Files

| file | purpose |
|---|---|
| `scripts\observatory_watch.ps1` | Foreground watcher in two modes: **one-shot** (`-MaxCycles 1`, used by the scheduled task: one full pass per trigger, then exit) and **long-running** (default, interactive terminal: poll until interrupted). Runs `python -m medradar observatory watch --interval-minutes <N> --trigger schedule`, streams every pass into a rotating log, sets `MEDRADAR_DEPLOYMENT_STATUS=DEPLOYED_LOCAL`, exits non-zero on failure. Supports `-Help` and `-WhatIf`. |
| `scripts\install_windows_task.ps1` | Registers `MedRadarObservatory` in Task Scheduler for the current user, with the one-shot action (`-MaxCycles 1`). `-WhatIf`, `-Status`, `-Uninstall`, `-Force`; refuses foreign tasks and never elevates. |
| `scripts\uninstall_windows_task.ps1` | Symmetrical removal. `-WhatIf` supported; never deletes ledger data. |

No `Start-Process` is involved in the collector path: the watcher stays in the foreground, so
Task Scheduler supervises the whole process tree. The scheduled action uses **one-shot mode**
(`-MaxCycles 1`): each trigger runs one collection pass and exits by itself, which keeps the
supervisor lifecycle clean on Windows (see "One-shot per trigger vs long-running watcher" below).
`MultipleInstances IgnoreNew` and the ledger lock still prevent overlap.

## Prerequisites

- Windows 10/11 or Windows Server 2016+ with Windows PowerShell 5.1 (the `ScheduledTasks` module).
- Python ≥ 3.10 with the `medradar` package installed for the interpreter that the task will
  call (`-Python`; default `python` from `PATH`). A checkout + `pip install -e .` is fine.
- A repository checkout at a stable path (the task stores the absolute watcher path).
- A real SEC contact in `MEDRADAR_SEC_UA` if SEC sources are collected (see Environment).

## Install

Always dry-run first — `-WhatIf` creates/changes **nothing** and prints the exact command:

```powershell
cd D:\path\to\medradar
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -WhatIf
```

Then register (default: every 360 minutes, current user, no elevation):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1
```

Options:

```powershell
# different cadence / interpreter
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -IntervalMinutes 60 -Python C:\Python312\python.exe

# read-only inspection
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status

# removal (WhatIf first)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall
```

What the registration does:

- task name `MedRadarObservatory`, registered for **the current user** with an interactive
  token and `RunLevel Limited` — the installer never requests elevation and never creates a
  task for another user;
- action: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <repo>\scripts\observatory_watch.ps1 -IntervalMinutes <N> -MaxCycles 1 -Python <exe>`
  — one collection pass per trigger, then the wrapper exits;
- trigger: once, one minute after registration, repeating every `<N>` minutes;
- `-StartWhenAvailable` (a missed slot runs when the machine becomes available),
  `MultipleInstances IgnoreNew` (no duplicate task instance while one is running),
  restart-on-failure 3× / 1 min, and no execution-time limit;
- a Description marker that identifies the task as owned by this installer. If a task with the
  same name exists **without** that marker, the installer refuses to touch it unless `-Force` is
  given; it only ever references `MedRadarObservatory` and never enumerates or modifies other
  tasks.

The trigger repetition and the watcher's `-IntervalMinutes` are the same N (the installer passes
both; in one-shot mode the interval only labels the pass). If a trigger fires while a previous
pass is still running, `MultipleInstances IgnoreNew` normally skips the second instance and, if
it does start, the ledger lease refuses the write — a trigger during an in-flight pass cannot
double-write.

## One-shot per trigger vs long-running watcher

| | one-shot (scheduled task) | long-running (interactive) |
|---|---|---|
| watcher invocation | `observatory_watch.ps1 -IntervalMinutes <N> -MaxCycles 1` | `observatory_watch.ps1` (default `-MaxCycles 0`) |
| process lifetime | one collection pass, then exits | polls every `<N>` minutes until interrupted |
| supervisor | Task Scheduler trigger every `<N>` minutes | your terminal / process manager |
| stop | the pass ends by itself; no orphan to chase | Ctrl+C in the terminal; a forced Task Scheduler end is **not** clean (see below) |

**Why the scheduled task is one-shot (operational finding).** On Windows a forced task end
(`schtasks /End`, `Stop-ScheduledTask`) can terminate the PowerShell wrapper while the child
`python -m medradar observatory watch` keeps running and keeps the ledger lease. In short, a Task
Scheduler trigger **cannot cleanly stop a long-running child**; "graceful stop" of a long-running
scheduled watcher degrades to a manual `taskkill`. The collector is still safe (checkpoints + lease
takeover on the next start, and the next run logged `lock_recovery` and took over cleanly), but the
supervisor lifecycle is not clean. A one-shot pass does not have this problem: the wrapper waits
for the single pass, which exits on its own, so a trigger cannot leave an unbounded orphan
behind. `StartWhenAvailable` still covers missed slots and the lease still prevents overlap.

Interactive long-running mode is unchanged and documented in the watcher's own `-Help`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\observatory_watch.ps1 -IntervalMinutes 60
```

Do **not** register that long-running form with Task Scheduler; use `install_windows_task.ps1`,
which always registers the one-shot action.

## Environment

| variable | where | meaning |
|---|---|---|
| `MEDRADAR_SEC_UA` | user/session environment or the task's process environment | SEC's access policy requires an identifying User-Agent with a **real, monitored contact address**. Set it yourself (`setx MEDRADAR_SEC_UA "MedRadar observatory (<your contact>)"` in a shell, or via System Properties → Environment Variables). Never commit it. |
| `MEDRADAR_HOME` | optional | Write root; defaults to the repo root in a source checkout (`data\` below it). |
| `MEDRADAR_OBSERVATORY_DB` | optional | Alternate ledger path; default `data\observatory\observatory.sqlite`. |
| `MEDRADAR_DEPLOYMENT_STATUS` | set by the watcher | `DEPLOYED_LOCAL` unless the caller already set it (supervisor-contract flag for the process). The ledger evidence is recorded explicitly with `observatory deploy-status` after verification. |

`setx` affects new processes only; the scheduled task picks it up on its next start. There is no
credential/contact value committed in this repository.

## Verify

```powershell
# task registered + owned + last/next run + last result
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status
schtasks /Query /TN MedRadarObservatory /V /FO LIST
Get-ScheduledTaskInfo -TaskName MedRadarObservatory | Format-List

# collector evidence in the ledger (run from the repo root)
python -m medradar observatory status --json
python -m medradar observatory health --json
python -m medradar observatory deploy-status
python -m medradar observatory reconcile

# record the verified local installation (timestamps the moment it is run)
python -m medradar observatory deploy-status --status DEPLOYED_LOCAL --supervisor windows_task `
  --evidence "schtasks state=Ready; log shows a completed pass"
```

`observatory health` and `observatory deploy-status` are available on
`feat/observatory-reliability-v1` (wired alongside these templates); on an older checkout use
`observatory status --json` + `observatory reconcile`.

"Verified" for this mode means: the task exists and is `Ready`/`Running`, a log file contains at
least one collection pass, `observatory status --json` shows a fresh `heartbeat` / `last_run_at`,
`deploy-status` reports `DEPLOYED_LOCAL` with supervisor `windows_task`, and `reconcile` exits 0.
`observatory health` overall may still be `DEGRADED` (a source failing) or `VALIDATION_IN_PROGRESS`
— neither is hidden by a local install.

## What a reboot does

- The task definition is stored by Task Scheduler and survives reboot.
- It is an **interactive, current-user** task: it starts only while that user is logged on. After
  a reboot it starts when the user logs in; `StartWhenAvailable` runs a slot that was missed while
  the machine was off.
- Each run is one-shot: after logon it executes **one** collection pass for the missed slot and
  exits; there is no long-running process to resume or re-supervise. The next trigger starts the
  next pass.
- While no user is logged on (or the machine is asleep), the collector does not run — that is
  visible in the run history as a missed slot and is **not** back-filled as if it had run. The
  source watermark makes the next pass catch up, so the ledger stays honest.
- If you need unattended 24/7 collection, do not treat a desktop Task Scheduler job as a server
  service: use the Linux systemd mode (deploy/systemd/README.md) on an always-on host. The
  "what a reboot does" honestly differs between the two modes; neither is a paid service.

## Log locations

- Collector log: `<repo>\logs\collector-yyyyMMdd.log` (daily file name), appended line by line
  with UTC timestamps. Rotated by size at start-up: when it reaches 10 MiB it is renamed to
  `<file>.1` (one previous segment is kept; adjust `-MaxLogBytes` / `-LogFile` in the watcher or
  task action).
- Task Scheduler history: `schtasks /Query /TN MedRadarObservatory /V /FO LIST` shows
  `Last Run Time` / `Last Result`; the Event Log "TaskScheduler" channel has the full history.
- The **ledger is the system of record**, not the log: `data\observatory\observatory.sqlite`.

## Confirm the collector is not running twice

Two independent guards:

1. **Task Scheduler**: `MultipleInstances IgnoreNew` — Windows will not start a second instance
   while the first is running. In one-shot mode the first instance normally finishes in minutes,
   so this prevents a duplicated pass when a trigger fires during a slow one. `-Status` prints the
   registered `Mode` (`one-shot pass per trigger` vs `long-running watcher`).
2. **Ledger lock** (authoritative, also covers manual runs, interactive watchers and GitHub
   Actions): before every pass the collector holds `data\observatory\collector.lock`, a JSON lease
   with `pid`, `host`, `mode`, `run_id`, `started_at`, `heartbeat_at`. A second collector on the
   same ledger refuses with a clear "lock held" message instead of writing — so even if a trigger
   overlaps a slow pass, the ledger is never double-written.

```powershell
# inspect the lease read-only (preferred over reading/deleting the JSON by hand)
python -m medradar observatory lock status
python -m medradar observatory lock status --json
# inspect the lock file directly (same data)
Get-Content data\observatory\collector.lock -Raw | ConvertFrom-Json
# is the owning process still alive on this host?
Get-Process -Id (Get-Content data\observatory\collector.lock -Raw | ConvertFrom-Json).pid
# heartbeat freshness + last run
python -m medradar observatory status --json
```

A lock whose owner is dead or whose heartbeat is older than 90 seconds is stale and the next
collector takes it over (recorded in `runtime_state` as an audit entry). **Do not delete
`collector.lock` by hand** while a process might still be alive; wait for the takeover, stop the
owner first, or — only when you have confirmed nothing is running — use the audited escape hatch
`python -m medradar observatory lock release --reason "why"`.

## Pause / resume / graceful stop

```powershell
# ledger-level pause: every supervisor (task, manual run, Actions) honours it
python -m medradar observatory pause --reason "maintenance window"
python -m medradar observatory resume

# stop supervision (does not delete data)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall
```

Windows has no SIGTERM. In **one-shot** mode this is simple: a trigger's pass runs to completion
and exits by itself, so between passes there is nothing to stop and the lifecycle is clean. To
stop supervision, pause first and let the current pass finish, then uninstall the task:

```powershell
python -m medradar observatory pause --reason "decommissioning this host"
# wait until observatory status --json shows no active pass / heartbeat sleeping/ok
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Uninstall
```

If you force-end the task mid-pass (`schtasks /End`, `Stop-ScheduledTask`), Windows may kill the
wrapper while the single pass child finishes on its own; that pass still exits shortly and its
lease keeps a second collector out. The ledger records the interruption honestly (`INTERRUPTED`
+ checkpoint/resume, and `lock_recovery` if a lease had to be taken over). Never edit or delete
`collector.lock` by hand.

For the **long-running interactive** watcher (not registered with Task Scheduler), stop it with
Ctrl+C so the scheduler shuts down gracefully; do not rely on a forced Task Scheduler end to stop
that mode — it can terminate the wrapper and leave the python child running (the reason the
scheduled task is one-shot).

## Uninstall

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1
```

Removes only `MedRadarObservatory` (refuses a foreign task without `-Force`, never elevates).
Ledger data under `data\observatory\` and backups are untouched. Optionally remove
`logs\collector-*.log` afterwards.

## Resource limits (honest note)

Unlike the systemd unit (`MemoryMax`/`CPUQuota`), Windows Task Scheduler has no per-task memory
or CPU cap here; a job object for the collector is out of scope for this branch (documented in
docs/RELIABILITY_DESIGN.md §3). That is acceptable because the scheduled mode is one-shot: the
process lives only for one collection pass, then exits, so there is no long-lived runaway to
contain. Supervision relies on the trigger + restart settings, the ledger lock/heartbeat, and the
operator watching `observatory status` / `health`. Do not start a second manual `watch` for the
same ledger while a scheduled pass is running.

## GitHub Actions is NOT a system of record

`.github/workflows/observatory.yml` runs the same collector every 6 hours on ephemeral GitHub
runners. Its cron can be delayed or silently dropped, its workspace is temporary, and
cache/artifact retention is bounded. It is a **convenience** runner — never the durable record of
what MedRadar observed. The durable record is the SQLite ledger on a persistent host (this
Windows task or the Linux systemd mode), backed up offsite per docs/BACKUP_AND_RECOVERY.md.
A GitHub Actions run never upgrades `deployment_status` beyond the honest value.

## Troubleshooting

| symptom | action |
|---|---|
| one-shot task ends quickly with `Last Result 0` | expected: one trigger = one collection pass, then exit. Check `logs\collector-yyyyMMdd.log` / the ledger for that pass |
| task shows `Running` for unusually long | the pass is slow (large source backlog/network); `observatory status --json` and the log show live progress; the lease prevents a duplicate |
| task runs but "python not found" in the log | pass `-Python <full path>` to the installer (use the interpreter where `medradar` is importable, e.g. a venv) |
| `Last Result` non-zero | open the log; run the same command in a terminal as the task user; the watcher exits with the collector's code |
| task exists but does nothing | `-Status`: is it owned? is it running? `NextRunTime` in the past + `NumberOfMissedRuns` large → machine was off/asleep; `StartWhenAvailable` will run it at next opportunity |
| must remove someone else's task | don't: `-Status` shows `OwnedByThisInstaller: False`; the scripts refuse without `-Force`. Only `-Force` if you have verified it is this project's task |
| log grows too fast | the collector logs one line per pass; rotate/archive `logs\` and adjust `-MaxLogBytes` / `-LogFile` in the watcher |
| lock held by a dead process | wait for the ~90 s stale takeover; never delete the lock by hand while unsure |

## What this does not prove

Registering this task does not deploy a service: it is `DEPLOYED_LOCAL`. It does not create the
offsite backup target, does not authorise a paid host, does not supply/authorise the SEC contact,
and does not run the seven-day validation window. Those remain in docs/DEPLOYMENT.md,
"NOT DEPLOYED — what the Lead must still authorise".
