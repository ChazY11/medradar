# MedRadar Observatory — systemd deployment templates

Templates only. Copying or reading these files deploys **nothing** and changes no status:
`deployment_status` stays `NOT_DEPLOYED` (docs/RELIABILITY_DESIGN.md §0) until a supervisor
is actually installed, started and verified on a host. The service never writes into
`site-packages`, and no credential or personal contact address is committed here.

This README is the Linux counterpart of docs/LIVE_OBSERVATORY.md §4 (持续运行) and the
short-form companion of docs/DEPLOYMENT.md (the operator runbook). Read DEPLOYMENT.md first;
it has the Windows mode, the environment-variable reference, the upgrade/uninstall procedure
and the honest "NOT DEPLOYED" checklist.

## Files

| file | purpose |
|---|---|
| `medradar-observatory.service` | Long-running collector: `python -m medradar observatory watch --interval-minutes 60 --trigger schedule --log-file /srv/medradar/logs/collector.log` |
| `medradar-observatory.timer` | 6-hourly one-shot variant: `OnCalendar=*-*-* 00/6:17:00`, `Persistent=true`, `RandomizedDelaySec=120` |

## Pick ONE mode per ledger

Both modes append to the **same** observation ledger; they are alternatives, not layers.

| mode | who should use it | supervisor | process shape | logs |
|---|---|---|---|---|
| **A. long-running** (default) | one small VM/box that is always on | `medradar-observatory.service` (`Restart=always`) | one process, in-loop 60 min interval, heartbeat + exponential backoff | journald + `/srv/medradar/logs/collector.log` |
| **B. timer (6-hourly)** | hosts that reboot often, or operators who prefer stateless one-shot passes | `medradar-observatory.timer` + a drop-in that turns the service into `observatory sync` | a short-lived process per slot | journald |
| manual | one-off / debugging | none | `python -m medradar observatory sync --trigger manual` | stdout |
| GitHub Actions | convenience only | Actions cron `17 */6 * * *` | ephemeral runner | artifact/cache — **never the system of record** |

Enable **A** or **B**, never both. With both installed the timer would try to start an
already-active long-running unit (harmless no-op) and the schedule would misrepresent what is
actually running.

## Prerequisites

- Linux with systemd, root/sudo for installation only.
- Python ≥ 3.10 with `medradar` installed for the interpreter named in `ExecStart`
  (`/usr/bin/python3` in the template).
- Outbound HTTPS. Optional: a dedicated system user (`medradar`) and `/srv/medradar`.
- A real SEC contact address supplied through `MEDRADAR_SEC_UA` (see below). No contact or
  credential is committed in this repository.

## Mode A — long-running service (recommended)

```bash
# 1. user + persistent layout (data survives reboot)
sudo useradd --system --home-dir /srv/medradar --shell /usr/sbin/nologin medradar 2>/dev/null || true
sudo mkdir -p /srv/medradar/{data/observatory,backups,logs}
sudo chown -R medradar:medradar /srv/medradar

# 2. install the package for the service interpreter
sudo /usr/bin/python3 -m pip install /srv/medradar
#    If the distro marks the system Python as externally managed (PEP 668) or you
#    want isolation, use a venv instead and the venv drop-in shown below:
#      sudo -u medradar /usr/bin/python3 -m venv /srv/medradar/venv
#      sudo -u medradar /srv/medradar/venv/bin/python -m pip install /srv/medradar

# 3. environment file OUTSIDE the repo (see "Environment file")
sudo install -d -m 0750 -o root -g medradar /etc/medradar
sudo install -m 0640 -o root -g medradar /dev/null /etc/medradar/observatory.env
sudoedit /etc/medradar/observatory.env

# 4. install + enable the unit
sudo cp /srv/medradar/deploy/systemd/medradar-observatory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medradar-observatory.service

# 5. verify (below)
systemctl status medradar-observatory.service
journalctl -u medradar-observatory.service -n 100 --no-pager
```

A virtualenv also works; override the interpreter with a drop-in instead of editing the
template:

```ini
# /etc/systemd/system/medradar-observatory.service.d/venv.conf
[Service]
ExecStart=
ExecStart=/srv/medradar/venv/bin/python -m medradar observatory watch --interval-minutes 60 --trigger schedule --log-file /srv/medradar/logs/collector.log
```

(A venv under `/home` needs `ProtectHome=false` in the same drop-in.)

## Mode B — 6-hourly timer (one-shot syncs)

Install the service unit and the environment file exactly as in Mode A, then add the drop-in
that turns the unit into a one-shot `sync`:

```bash
sudo mkdir -p /etc/systemd/system/medradar-observatory.service.d
sudo tee /etc/systemd/system/medradar-observatory.service.d/oneshot.conf >/dev/null <<'CONF'
[Unit]
Description=MedRadar Observatory one-shot collector (timer-driven)
[Service]
Type=oneshot
Restart=no
ExecStart=
ExecStart=/usr/bin/python3 -m medradar observatory sync --trigger schedule
CONF

sudo cp /srv/medradar/deploy/systemd/medradar-observatory.service /etc/systemd/system/
sudo cp /srv/medradar/deploy/systemd/medradar-observatory.timer     /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medradar-observatory.timer
```

Why a drop-in: it keeps one collector identity (`medradar-observatory`), so
`systemctl status`, `journalctl -u` and the resource limits are identical in both modes. The
timer activates `medradar-observatory.service`, so the drop-in must exist *before* the timer
is enabled.
`Persistent=true` runs a missed 6-hourly slot once on the next boot; `RandomizedDelaySec=120`
de-synchronises hosts. A missed slot is still visible in the run history and is never counted
as a success.

## Environment file and the SEC contact requirement

`EnvironmentFile=-/etc/medradar/observatory.env` is optional in the unit (leading `-`) but
**required for production**: SEC's published access policy wants a `User-Agent` that
identifies the client and a real, monitored contact address. Generic/placeholder values are
rejected with HTTP 403, which would show up honestly as a `DEGRADED` source, not as "no news".

Put these values in the env file, never in Git:

| variable | required | meaning |
|---|---|---|
| `MEDRADAR_SEC_UA` | **yes for SEC sources** | `MedRadar observatory (<real contact address your team monitors>)`. The address must be authorised for this deployment; the repository ships only the code's non-production fallback. |
| `MEDRADAR_DEPLOYMENT_INSTALLED_AT` | optional | The **real** installation instant (ISO-8601 UTC) for tools that read the environment; never back-date or fabricate it. The authoritative ledger record is the `observatory deploy-status` command below, which timestamps the moment it is run — run it right after verification. |
| `MEDRADAR_OBSERVATORY_DB` | optional | Alternate ledger path; default `$MEDRADAR_HOME/data/observatory/observatory.sqlite`. |
| `MEDRADAR_DEPLOYMENT_STATUS` | set by the unit | Supervisor-contract flag (`DEPLOYED_SERVICE`). The ledger evidence is still recorded explicitly with `observatory deploy-status`; only override the env value if you know why. |

`MEDRADAR_HOME=/srv/medradar` is set by the unit itself. File permissions: `0640 root:medradar`.

## Verify after installation

```bash
# unit + timer state
systemctl status medradar-observatory.service --no-pager
systemctl list-timers medradar-observatory.timer --no-pager   # Mode B only

# logs (journald is authoritative)
journalctl -u medradar-observatory.service -n 100 --no-pager
journalctl -u medradar-observatory.service -f

# ledger evidence — run as the service user so MEDRADAR_HOME/DB resolve the same way
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory status --json
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory health --json
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory deploy-status
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory reconcile

# record the verified installation (timestamps the moment it is run)
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory deploy-status \
  --status DEPLOYED_SERVICE --supervisor systemd \
  --evidence "systemctl is-active=active; journal shows a completed pass"
```

What "verified" means: the unit is `active (running)` (Mode A) or the timer shows a recent
`LAST` pass (Mode B), the journal shows a collection pass, `observatory status --json` shows a
fresh `heartbeat`/`last_run_at`, `deploy-status` reports `DEPLOYED_SERVICE` with the
supervisor `systemd`, and `reconcile` exits 0. Only then does the honest deployment status for
that host become `DEPLOYED_SERVICE`; `observatory health` overall stays `DEGRADED` while any
source is failing and only becomes `OPERATIONAL` after a real validation window passes — a
freshly started collector is not "operational".

`observatory health` and `observatory deploy-status` are available on
`feat/observatory-reliability-v1` (wired alongside these templates). On an older checkout that
lacks them, use `observatory status --json` and `observatory reconcile` instead.

## Pause, stop, graceful shutdown

Two different controls — do not confuse them:

| control | scope | command |
|---|---|---|
| **pause** | ledger-level switch honoured by *every* supervisor (systemd, Windows task, Actions) | `sudo -u medradar env MEDRADAR_HOME=/srv/medradar /usr/bin/python3 -m medradar observatory pause --reason "maintenance window"` |
| **resume** | clears the ledger-level pause | `... observatory resume` |
| **stop** | stops this process only; the supervisor will restart it unless disabled | `sudo systemctl stop medradar-observatory.service` |

A paused collector keeps running but skips passes and records `PAUSED` heartbeats; stopping the
service is for maintenance of the process itself. `systemctl stop` sends SIGTERM
(`KillSignal=SIGTERM`); the scheduler finishes or abandons the current pass cleanly, records
the interrupted run, releases `collector.lock` and exits 0 within `TimeoutStopSec=120`. Never
`kill -9` a collector that is writing the ledger.

To keep the service from coming back after a stop:

```bash
sudo systemctl disable --now medradar-observatory.service          # Mode A
sudo systemctl disable --now medradar-observatory.timer            # Mode B
```

## Logging and rotation

- journald gets stdout/stderr (`StandardOutput=journal`, `StandardError=journal`,
  `SyslogIdentifier=medradar-observatory`). Use `journalctl -u medradar-observatory.service`.
- The template also writes `/srv/medradar/logs/collector.log` via `--log-file` as a
  convenience copy. It grows, so rotate it:

```ini
# /etc/logrotate.d/medradar-observatory
/srv/medradar/logs/*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

journald retention is managed by systemd (`SystemMaxUse=` in `/etc/systemd/journald.conf`);
ensure it is large enough for the evidence window you claim to keep.

## Resource limits and why

| directive | value | rationale |
|---|---|---|
| `MemoryMax=512M` | 512 MB | polling + SQLite fits in tens of MB; 512 MB catches a runaway page loop before the host swap-thrashes |
| `CPUQuota=50%` | half a core | the collector is I/O-bound and deliberately polite; >50% sustained means a bug, not normal load |
| `Restart=always` + `RestartSec=30` | supervision | crash/resume without a human, but no hot loop: 5 starts / 5 min trips `StartLimit` and leaves the unit failed for an operator |
| `KillSignal=SIGTERM` + `TimeoutStopSec=120` | graceful stop | finish/abandon the pass, record it, release the lock |
| `NoNewPrivileges`, `PrivateTmp`, `PrivateDevices`, `ProtectSystem=strict`, `ProtectHome`, `ReadWritePaths=/srv/medradar` | sandbox | the collector only needs network + `/srv/medradar`; everything else stays read-only |

Hitting a limit is a signal to investigate, not a reason to raise the ceiling silently.

## Upgrade

```bash
# 1. backup first (consistent SQLite online backup; verify the manifest/bundle)
sudo -u medradar env MEDRADAR_HOME=/srv/medradar \
  /usr/bin/python3 -m medradar observatory backup --dest /srv/medradar/backups

# 2. stop the collector so the new code is not imported mid-pass
sudo systemctl stop medradar-observatory.service        # or disable the timer, Mode B

# 3. install the new code into the service interpreter (use the venv python if you
#    installed a virtualenv - see the venv drop-in above)
sudo /usr/bin/python3 -m pip install --upgrade /srv/medradar

# 4. update units if they changed, then reload + start
sudo cp /srv/medradar/deploy/systemd/medradar-observatory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start medradar-observatory.service

# 5. verify (see above); roll back by restoring the previous package/unit and ledger backup
```

The ledger schema migrates forward on open; the backup in step 1 is the rollback boundary.

## Uninstall

```bash
sudo systemctl disable --now medradar-observatory.timer            # if Mode B
sudo systemctl disable --now medradar-observatory.service          # if Mode A
sudo rm -f /etc/systemd/system/medradar-observatory.service \
           /etc/systemd/system/medradar-observatory.timer
sudo rm -rf /etc/systemd/system/medradar-observatory.service.d
sudo systemctl daemon-reload
```

This removes the supervisor only. Keep `/srv/medradar/data/` (the system of record) and
`/srv/medradar/backups/`; delete `/etc/medradar/observatory.env` and the `medradar` user only
after a final verified backup and copy.

## Troubleshooting

| symptom | likely cause / action |
|---|---|
| unit `failed`, "start request repeated too quickly" | crash loop; read `journalctl -u ... -n 200`, fix, `systemctl reset-failed`, start again |
| "collector lock held by ..." in the journal | another collector (manual run, Windows task, Actions runner) owns the ledger; `observatory lock status` shows the holder, wait for the 90 s stale heartbeat takeover, or — after confirming nothing is live — use the audited `observatory lock release --reason "why"`. Never delete `collector.lock` by hand |
| HTTP 403 from SEC | `MEDRADAR_SEC_UA` missing or not a real contact; set it in the env file and restart |
| "Permission denied" writing the ledger/log | `/srv/medradar` ownership vs `User=medradar`, or a path outside `ReadWritePaths`; fix ownership rather than loosening the sandbox |
| timer installed but nothing runs | `systemctl list-timers`, check the drop-in exists and `systemctl start medradar-observatory.service` manually to see the error |
| health says `PAUSED` | someone ran `observatory pause`; `observatory resume` when the maintenance window ends |

## What this does not prove

Installing these units proves only that *this host* is supervised. It does not create the
offsite backup target, does not authorise a paid host, does not supply the SEC contact, and
does not run the seven-day validation window. Until those are done, the project-level
`deployment_status` remains `NOT_DEPLOYED` and docs/DEPLOYMENT.md lists exactly what still
requires the Lead's authorisation.
