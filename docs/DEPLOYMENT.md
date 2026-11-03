# MedRadar Observatory — Deployment Runbook

Status: **templates + local scripts; no production deployment.** This branch provides the
supervisor templates, the Windows scripts and this runbook so an operator (after authorisation)
can install one. Until a supervisor is actually installed, started **and verified** on a host,
the honest `deployment_status` is `NOT_DEPLOYED`; after a verified install on a workstation it is
at most `DEPLOYED_LOCAL`, and only an authorised always-on host may record `DEPLOYED_SERVICE`.
The recorded value lives in the host's ledger (`observatory deploy-status`) and is decided by the
Lead/operator — it is never inferred from these files. See docs/RELIABILITY_DESIGN.md §0 and §3,
and the "NOT DEPLOYED" section at the end of this file.

This runbook stays consistent with docs/LIVE_OBSERVATORY.md §4 (持续运行) — same pause/resume
switch, same watermark/backfill behaviour, same "GitHub Actions is not the system of record"
caveat — and with docs/BACKUP_AND_RECOVERY.md for backups.

---

## 1. Deployment modes at a glance

Pick one mode per ledger. The collector is a *polling* watchdog, not a real-time feed: a
missed pass is visible in the run history and is caught up by the source watermark, never
silently counted as success.

| mode | who it is for | supervisor | command | logs | after a verified install |
|---|---|---|---|---|---|
| **Windows dev/ops** | a workstation / lab PC that is on while the operator works | Task Scheduler task `MedRadarObservatory` → `scripts/observatory_watch.ps1` (one-shot: one pass per trigger) | `python -m medradar observatory watch --interval-minutes 360 --trigger schedule --max-cycles 1` | `logs\collector-yyyyMMdd.log` + Task Scheduler history | `DEPLOYED_LOCAL` |
| **Linux systemd long-running** (recommended production) | a small always-on VM/server | `medradar-observatory.service` (`Restart=always`) | same watch command | journald + `/srv/medradar/logs/collector.log` | `DEPLOYED_SERVICE` |
| **Linux systemd timer** | hosts that reboot often, or operators who prefer stateless one-shot passes | `medradar-observatory.timer` + documented drop-in → `observatory sync` | `python -m medradar observatory sync --trigger schedule` | journald | `DEPLOYED_SERVICE` |
| **manual one-shot** | debugging, ad-hoc catch-up, acceptance | none | `python -m medradar observatory sync --trigger manual` | stdout | no deployment claim |
| **GitHub Actions** | convenience only — **never a durable record** | Actions cron `17 */6 * * *` | `observatory sync --trigger ci` | ephemeral runner + artifact/cache | no deployment claim |

Rules of thumb:

- A machine that is always on, with a persistent disk → **Linux systemd long-running**.
- A machine the operator uses interactively → **Windows Task Scheduler**, knowing it runs only
  while that user is logged on (see deploy/windows/README.md, "What a reboot does"). The scheduled
  task is **one-shot**: every trigger runs one full collection pass and exits; the long-running
  watcher is for interactive terminal use only (see §5).
- GitHub Actions cron can be delayed or dropped and its workspace is ephemeral; it must never be
  the only copy of the ledger (docs/LIVE_OBSERVATORY.md §4.3).
- Never run two collectors against the same ledger. The ledger lock refuses the second writer,
  but the schedule would lie. Pause first if you need to overlap a maintenance action.

## 2. Prerequisites

- Python ≥ 3.10 with the `medradar` package installed for the interpreter the supervisor will
  call (`pip install .` in a checkout, or a virtualenv).
- Outbound HTTPS to the public sources; time sync (the ledger timestamps are UTC).
- A persistent disk for `data/observatory/` (the system of record) plus backups. A full ledger is
  small today (≈1.7 MB); plan ~50–150 MB/year of ledger and more for the regenerable raw cache.
- A **real, authorised contact address** for the SEC User-Agent (see §3). SEC enforces it.
- A supervisor installed by someone with the right to do so (root/sudo on Linux; current user on
  Windows) and a place to keep the environment file outside the repository.

## 3. Environment variables

| variable | required | default | meaning |
|---|---|---|---|
| `MEDRADAR_HOME` | recommended in production | repo root in a source checkout, else `~/.medradar` | write root; `data/`, `out/`, `cache/` live below it. The systemd unit sets `/srv/medradar`. |
| `MEDRADAR_OBSERVATORY_DB` | optional | `$MEDRADAR_HOME/data/observatory/observatory.sqlite` | explicit ledger path; useful for a relocated/volume-backed ledger. |
| `MEDRADAR_SEC_UA` | **yes for SEC sources** | code fallback (non-production example) | `User-Agent` identifying this deployment **and containing a real contact address your team monitors**. Without it SEC returns HTTP 403, which the health panel reports honestly as a degraded source. |
| `MEDRADAR_DEPLOYMENT_STATUS` | set by supervisors (contract flag) | absent → `NOT_DEPLOYED` | `DEPLOYED_LOCAL` (Windows watcher / local run) or `DEPLOYED_SERVICE` (systemd unit); the process' self-identification. The **ledger evidence** is recorded explicitly with `observatory deploy-status --status ... --supervisor ...` after verification (see §7). |
| `MEDRADAR_DEPLOYMENT_INSTALLED_AT` | optional | absent | the **real** installation instant (ISO-8601 UTC) for tools that read the environment; never back-date or fabricate it. `deploy-status` records the moment it is run, so run it right after verification. |
| `PYTHONUNBUFFERED` | recommended | unset | set to `1` by both supervisors so journald/log lines appear while a pass runs. |

### 3.1 `MEDRADAR_SEC_UA` — a real contact is mandatory

SEC's published access policy requires a `User-Agent` that identifies the client and provides a
contact (see <https://www.sec.gov/os/webmaster-faq#developers> and <https://www.sec.gov/developer>).
A generic or placeholder value is rejected.

How to get authorisation (do this before installing a production supervisor):

1. Ask the team/legal owner of the deployment which role mailbox may receive SEC traffic. **Do
   not use a personal address** and do not reuse somebody else's contact without permission.
2. Confirm the mailbox is monitored (SEC may use it to reach the operator) and that automated
   requests are acceptable under your organisation's policy and SEC's published guidance.
3. Put the value in the supervisor's environment file, never in Git:

   - Linux: `/etc/medradar/observatory.env`, mode `0640 root:medradar` (unit:
     `deploy/systemd/medradar-observatory.service`).
   - Windows: a user environment variable under the account that runs the task (or the task's
     process environment), documented in deploy/windows/README.md.
4. The value has the shape `MedRadar observatory (<role contact address>)`. The repository ships
   only the code's non-production fallback; no address, key or credential is committed.
5. Rotate/update the value via the env file and restart the supervisor if the contact changes;
   `observatory status`/`health` will show a SEC 403 as a source failure, not as "no news".

## 4. Install — Linux systemd (recommended production)

Full file-by-file guide: deploy/systemd/README.md. Short form (run as an operator with sudo):

```bash
# user + persistent layout
sudo useradd --system --home-dir /srv/medradar --shell /usr/sbin/nologin medradar 2>/dev/null || true
sudo mkdir -p /srv/medradar/{data/observatory,backups,logs}
sudo chown -R medradar:medradar /srv/medradar

# package for the interpreter in ExecStart
sudo /usr/bin/python3 -m pip install /srv/medradar
#   PEP 668 ("externally managed") distros or isolation: use a venv and override
#   ExecStart with the drop-in documented in deploy/systemd/README.md:
#   sudo -u medradar /usr/bin/python3 -m venv /srv/medradar/venv
#   sudo -u medradar /srv/medradar/venv/bin/python -m pip install /srv/medradar

# environment file (OUTSIDE the repo, 0640 root:medradar)
sudo install -d -m 0750 -o root -g medradar /etc/medradar
sudo install -m 0640 -o root -g medradar /dev/null /etc/medradar/observatory.env
sudoedit /etc/medradar/observatory.env      # MEDRADAR_SEC_UA + MEDRADAR_DEPLOYMENT_INSTALLED_AT

# long-running mode
sudo cp /srv/medradar/deploy/systemd/medradar-observatory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medradar-observatory.service
```

For the 6-hourly one-shot variant (Mode B) install the timer and its documented drop-in instead
of enabling the long-running service — exact commands in deploy/systemd/README.md.

## 5. Install — Windows Task Scheduler (dev/ops)

Full guide: deploy/windows/README.md. Dry-run first — `-WhatIf` changes nothing:

```powershell
cd D:\path\to\medradar
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1
```

The task runs `scripts\observatory_watch.ps1` with `-MaxCycles 1`, i.e.
`python -m medradar observatory watch --interval-minutes 360 --trigger schedule --max-cycles 1`,
for the current user every 360 minutes by default: **each trigger runs exactly one full
collection pass and exits**. That is deliberate — on Windows a forced task end
(`schtasks /End`, `Stop-ScheduledTask`) can terminate the PowerShell wrapper while a long-running
python collector survives and keeps the ledger lease, so "graceful stop" of a long-running
scheduled watcher degrades to a manual `taskkill`. A one-shot pass always exits by itself, so the
supervisor lifecycle is clean; `StartWhenAvailable` covers a missed slot and the ledger lease
prevents overlap if a trigger fires while an earlier pass is still finishing. The long-running
watcher (no `-MaxCycles`, foreground polling) remains available for interactive terminal use
only — do not register that mode with Task Scheduler. It runs only while that user is logged on;
for unattended 24/7 collection use the Linux systemd mode.

## 6. Manual one-shot

For a single polite pass without installing a supervisor:

```bash
python -m medradar observatory sync --trigger manual
# or a short acceptance run with two passes:
python -m medradar observatory watch --max-cycles 2 --interval-minutes 1
```

`sync` takes the lock, resumes an interrupted run if one exists, and exits non-zero when a source
reports a hard failure. It creates no deployment evidence: `deploy-status` stays `NOT_DEPLOYED`.

## 7. First-run verification (required before claiming any deployment)

Run these **as the same user/environment the supervisor uses** (on Linux:
`sudo -u medradar env MEDRADAR_HOME=/srv/medradar /usr/bin/python3 -m medradar ...`) so paths and
the env file resolve identically.

```bash
python -m medradar observatory status            # human summary of ledger + sources
python -m medradar observatory status --json     # machine-readable evidence
python -m medradar observatory health --json     # overall + per-source + deployment/validation
python -m medradar observatory deploy-status     # current recorded deployment evidence
python -m medradar observatory reconcile         # consistency + SQLite integrity (exit 0)
python -m medradar observatory sources           # verified per-source coverage
```

`observatory health` and `observatory deploy-status` are available on
`feat/observatory-reliability-v1` (wired alongside these templates). On an older checkout that
lacks them, use `observatory status --json` + `observatory reconcile`; the deployment evidence is
in `runtime_state`.

Supervisor checks:

```bash
systemctl status medradar-observatory.service --no-pager        # Linux, Mode A
journalctl -u medradar-observatory.service -n 100 --no-pager    # at least one pass
systemctl list-timers medradar-observatory.timer --no-pager     # Linux, Mode B
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1 -Status
schtasks /Query /TN MedRadarObservatory /V /FO LIST
Get-Content logs\collector-*.log -Tail 40
```

What "verified" means:

1. the supervisor is active (service `active (running)`, or a recent timer `LAST` pass, or the
   task `Ready`/`Running` with a sensible last result);
2. the journal/log shows a real collection pass with no unhandled crash;
3. `observatory status --json` shows a fresh `heartbeat` and `last_run_at`;
4. `observatory deploy-status` reports the expected supervisor and `DEPLOYED_LOCAL` /
   `DEPLOYED_SERVICE` once you record it (below);
5. `observatory reconcile` exits 0.

Record the verified installation — the command timestamps the moment it is run, so run it
immediately after the checks above:

```bash
# Linux (as the service user, same environment as the unit)
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory deploy-status \
  --status DEPLOYED_SERVICE --supervisor systemd \
  --evidence "systemctl is-active=active; journal shows a completed pass"
```

```powershell
# Windows (from the repo root, same environment as the task)
python -m medradar observatory deploy-status --status DEPLOYED_LOCAL --supervisor windows_task `
  --evidence "schtasks state=Ready; log shows a completed pass"
```

`deploy-status` without `--status` only shows the currently recorded evidence; it does not
upgrade anything by itself. Never record `DEPLOYED_SERVICE` for a host you have not verified.

`observatory health --json` will **not** show `OPERATIONAL` right after a first run: `overall`
follows the documented precedence (`NOT_DEPLOYED` → `PAUSED` → `DEGRADED` → `VALIDATION_IN_PROGRESS`
→ `OPERATIONAL`). Expect `VALIDATION_IN_PROGRESS`/`DEGRADED` while sources warm up or the
seven-day validation has not passed; a green HTTP 200 is never accepted as evidence.

Single-writer confirmation: `<ledger-dir>/collector.lock` (default
`data/observatory/collector.lock`) contains the owning `pid/host/mode/run_id/started_at/
heartbeat_at`, with a heartbeat every ~15 s. `python -m medradar observatory lock status` shows
it read-only. A second collector refuses to start; a dead owner's lock is taken over after the
90 s stale window and the takeover is audited. If (and only after) you have confirmed no collector
process is alive, the audited escape hatch is
`python -m medradar observatory lock release --reason "why"` — never delete `collector.lock` by
hand. See deploy/windows/README.md for read-only inspection commands.

## 8. Graceful stop, restart and pause

| goal | Linux | Windows |
|---|---|---|
| stop collecting for a while, keep the process | `observatory pause --reason "..."` (ledger-level; every supervisor honours it) | `python -m medradar observatory pause --reason "..."` |
| resume | `observatory resume` | `python -m medradar observatory resume` |
| stop the process gracefully | `systemctl stop medradar-observatory.service` → SIGTERM; scheduler finishes/abandons the pass, records it, releases the lock, exits 0 within `TimeoutStopSec=120` | one-shot mode: the pass exits by itself, so between triggers there is nothing to stop; pause first, let the current pass finish, then `-Uninstall`. Ending a task mid-pass may leave the single pass child to finish; the ledger records it (`INTERRUPTED`/checkpoint, `lock_recovery` if a lease was taken over). The interactive long-running watcher is stopped with Ctrl+C, not a forced task end |
| restart after a code/env change | `systemctl restart ...` (or `daemon-reload` first if units changed) | uninstall + reinstall with the same `-WhatIf`-checked options (each trigger is one pass, so the next pass picks up the new code) |

Crash/interruption recovery is built in: the next `sync` marks leftover `RUNNING` runs as
`INTERRUPTED`, resumes from `sync_checkpoint`, and never rewrites committed pages. Consecutive
failures back off exponentially inside `watch` (up to 8× interval) and are recorded in
`source_failure`. Never `kill -9` a collector that is writing the ledger.

## 9. Log locations

| mode | where | retention |
|---|---|---|
| Linux systemd | journald, `journalctl -u medradar-observatory.service`; convenience copy `/srv/medradar/logs/collector.log` (logrotate snippet in deploy/systemd/README.md) | journald policy on the host; logrotate keeps 8 weekly copies of the file |
| Windows task | `<repo>\logs\collector-yyyyMMdd.log`, size-rotated to `.1`; Task Scheduler history (`schtasks /Query ... /V`, Event Log → TaskScheduler) | operator-managed |
| manual | stdout/stderr | terminal |
| GitHub Actions | run log + uploaded artifact (bounded retention) | not durable |

The **ledger** (`data/observatory/observatory.sqlite`) is the system of record, not the log. The
log proves the process ran; the ledger proves what was observed and when.

## 10. Upgrade procedure

1. **Back up first** (consistent SQLite online backup + raw cache):
   `python -m medradar observatory backup --dest <backups-dir>`; verify the bundle manifest
   (docs/BACKUP_AND_RECOVERY.md).
2. Stop the supervisor (systemd `stop` / disable the timer; Windows `-Uninstall` after pause) so
   the new code is not imported mid-pass.
3. Install the new package for the same interpreter (`pip install --upgrade <checkout>`).
4. If the unit/task definition changed, reinstall it from the updated template (`daemon-reload`
   + `cp` on Linux; `install_windows_task.ps1` again on Windows — same `-WhatIf` first).
5. Start the supervisor and repeat §7 verification.

Rollback boundary: restore the previous package/unit **and** the ledger backup from step 1. The
schema migrates forward on open, so a newer ledger is not readable by an older code path —
that is why step 1 is mandatory.

## 11. Uninstall

Linux:

```bash
sudo systemctl disable --now medradar-observatory.timer     # if Mode B
sudo systemctl disable --now medradar-observatory.service   # if Mode A
sudo rm -f /etc/systemd/system/medradar-observatory.service /etc/systemd/system/medradar-observatory.timer
sudo rm -rf /etc/systemd/system/medradar-observatory.service.d
sudo systemctl daemon-reload
```

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1 -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_windows_task.ps1
```

Both remove supervision only. **Keep** `data/observatory/` (the system of record) and
`backups/`; take a final verified backup, copy it off the host, and only then delete the
`medradar` user and `/etc/medradar/observatory.env`.

## 12. Resource limits

Linux: `MemoryMax=512M`, `CPUQuota=50%` (systemd). The workload is polite polling + SQLite
writes; hitting a limit repeatedly points at a source/structure change, not at needing a bigger
box. `Restart=always` + `RestartSec=30` with a 5-starts/5-minutes start limit prevents hot crash
loops. Windows Task Scheduler has no per-task memory/CPU cap in these scripts (a job object is
out of scope for this branch, documented in docs/RELIABILITY_DESIGN.md §3) — watch
`observatory status`/`health` instead. See deploy/systemd/README.md for the full rationale.

## 13. Security and secret handling

- No credential, token, API key or personal contact address is committed to this repository. The
  SEC User-Agent comes from the environment file (Linux) / user environment (Windows); the code's
  built-in fallback is a non-production example that SEC may reject.
- The systemd unit runs as the unprivileged `medradar` user with `NoNewPrivileges`,
  `PrivateTmp`, `PrivateDevices`, `ProtectSystem=strict`, `ProtectHome` and only
  `ReadWritePaths=/srv/medradar`; the Windows installer runs as the current user with
  `RunLevel Limited` and never elevates.
- Env files: `0640 root:medradar` (Linux), not in the repo, not in backups of the code tree.
- Backup encryption/keys (age/restic) are the operator's responsibility and require
  authorisation — see the "NOT DEPLOYED" section.

## 14. NOT DEPLOYED — what the Lead must still authorise

Nothing in this branch creates a paid resource, credential or production deployment. A local
supervisor may be installed on a workstation/lab machine as part of acceptance; that is
`DEPLOYED_LOCAL` and is **not** a production claim. **Before any production/`DEPLOYED_SERVICE`
claim the Lead/operator must authorise and complete each of the following:**

| # | item | why it is blocked / what it needs |
|---|---|---|
| 1 | **Host / VM** (size, provider, region, monthly budget) | a paid resource; docs/RELIABILITY_DESIGN.md §1 estimates ≈ €5–8/month. Creating it is a spending decision, not a code change. |
| 2 | **Persistent disk + backup target** | the always-on disk is the system of record; the offsite copy needs object storage/S3-compatible credentials (or rclone/restic target) and an owner for the encryption keys. |
| 3 | **SEC contact authorisation** | a real, monitored role mailbox approved for automated SEC requests; stored only in the env file. No address is supplied by this repo. |
| 4 | **Supervisor installation + verification** | copy the unit / register the task on the authorised host, run §7, and record the `deploy-status`/`health` evidence. Until then the status is `NOT_DEPLOYED` (and `DEPLOYED_LOCAL` at most for a workstation). |
| 5 | **Seven-day continuous validation** | `observatory validate start` and the protocol in docs/CONTINUOUS_VALIDATION_PROTOCOL.md; only an ended, computed window may set `VALIDATION_PASSED`. A few hours of running is `VALIDATION_IN_PROGRESS`, never `PASSED`. |
| 6 | **Optional public web/TLS/DNS** | only if the Observatory page must be reachable outside the host; also a paid/authorised service. |

Honest status of this branch:

- storage/backup architecture: designed, locally verified (backup + isolated restore drill);
- supervisors: templates, Windows scripts and runbook provided; whether one is installed on a
  given host is recorded in that host's ledger (`observatory deploy-status`), not inferred from
  these files;
- GitHub Actions: convenience runner only, **not a system of record**;
- `deployment_status`: per host and always explicit. A workstation install is `DEPLOYED_LOCAL`;
  production stays `NOT_DEPLOYED` until the items above are authorised and a verified supervisor
  on the authorised host records `DEPLOYED_SERVICE`;
- `validation_status`: `VALIDATION_NOT_STARTED` until a real seven-day window is started and ends;
  a run of a few hours is `VALIDATION_IN_PROGRESS`, **never** `VALIDATION_PASSED`.

When items 1–5 are done and verified, record the status explicitly — never infer
`DEPLOYED_SERVICE` from the existence of these files.
