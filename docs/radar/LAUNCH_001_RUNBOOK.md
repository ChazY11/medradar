# LAUNCH-001 — Live Radar production runbook

This runbook describes the **deployed** Radar services on the Tencent Cloud Lighthouse host, how
to verify them, how to back up and restore, and how to roll back. It is written for the operator
who has SSH access to `ubuntu@170.106.142.49` and `sudo`.

Nothing here replaces the FDA production worktree at `/srv/medradar/app`. The Radar deployment is
deliberately separate: its own release tree, virtualenv, data directory and systemd units.

## 1. What is deployed

| Piece | Unit | Listener / path | Purpose |
| --- | --- | --- | --- |
| Scheduler | `medradar-radar-scheduler.service` | none (outbound only) | Runs a cycle every 300 s, checks each source only when its cadence is due |
| Web | `medradar-radar-web.service` | `127.0.0.1:8791` | Read-only Live Intelligence + Technology Map API and the built UI |
| Ledger backup | `medradar-radar-backup.timer` → `.service` | `/srv/medradar/data/radar/backups` | Daily 03:40 local, online SQLite backup + verification, 14-day retention |
| Public tunnel | `medradar-radar-tunnel.service` | outbound to Cloudflare | Quick Tunnel to the loopback web; the only public path |

Release layout:

```
/srv/medradar/radar/releases/<sha>/   immutable release tree (git archive of the commit)
/srv/medradar/radar/app -> releases/<sha>   current release symlink
/srv/medradar/radar/DEPLOYED_SHA      the commit actually deployed
/srv/medradar/radar-venv/             dedicated virtualenv (editable install of the release)
/srv/medradar/data/radar/radar.db     observation ledger (the irreplaceable data)
/srv/medradar/data/radar/graph.db     derived technology graph (rebuildable)
/srv/medradar/data/radar/backups/     verified ledger copies + JSON manifests
/etc/medradar/radar-alpha.env         alpha credential hash (root:medradar 0640)
```

The existing FDA services (`medradar-web.service` on `127.0.0.1:8787`,
`medradar-data-update.timer`, `medradar-data-backup.timer`) are untouched and independent.

## 2. Verify it is running

```bash
systemctl status medradar-radar-scheduler.service medradar-radar-web.service \
                 medradar-radar-tunnel.service medradar-radar-backup.timer
journalctl -u medradar-radar-scheduler -n 50 --no-pager
curl -s http://127.0.0.1:8791/healthz            # liveness, no data
sudo -u medradar MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /srv/medradar/radar-venv/bin/python -m medradar radar status
```

`radar status` prints per-source state, watermark, consecutive failures, detection latency and an
integrity check. `NO_CHANGE` is a real result and is printed as one.

### The public URL

```bash
journalctl -u medradar-radar-tunnel --no-pager | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

The Quick Tunnel hostname is random and **changes when the tunnel restarts**. It is an alpha
experience address, not a permanent domain. Access requires the alpha credentials in
`/etc/medradar/radar-alpha.env` (HTTP Basic, uploaded by the operator, never stored here).

## 3. The access gate

The web process itself enforces the public-alpha policy (`medradar/radar/alpha_gate.py`):

- Basic auth, PBKDF2-SHA256 (240k iterations), constant-time comparison;
- only `GET`/`HEAD`;
- only `/`, `/radar`, `/radar/technology-map`, `/favicon.svg`, `/api/meta`, `/api/radar/*` and the
  two Vite build files. Everything else — workbench review/export APIs, `/api/docs`,
  `/openapi.json` — is a 404 even with valid credentials;
- `/healthz` is open and returns no data;
- ten failed attempts from one address within ten minutes lock that address for fifteen minutes;
- security headers on every response (nosniff, DENY framing, same-origin referrer, no-store,
  noindex, HSTS when the forwarded protocol is HTTPS).

`MEDRADAR_PUBLIC_ALPHA=1` also stops FastAPI from generating the OpenAPI schema and redacts
absolute server paths from `/api/radar/meta`.

To rotate the password:

```bash
/srv/medradar/radar-venv/bin/python -m medradar.radar.alpha_gate --hash 'new long password'
# put the printed value in /etc/medradar/radar-alpha.env as MEDRADAR_ALPHA_HASH
sudo systemctl restart medradar-radar-web.service
```

## 4. Sources and cadence

| Source | Cadence | Notes |
| --- | --- | --- |
| `pubmed` | 6 h | Entrez date window with 3-day overlap |
| `crossref` | 12 h | `from-created-date` window with 2-day overlap |
| `philips_official` | 12 h | news index set difference |
| `draeger_official` | 12 h | sitemap `lastmod` watermark |
| `openfda_device` | 24 h | official endpoint version + product-code sweeps |
| `gehealthcare_official` | — | `BLOCKED_BY_ACCESS_POLICY`: the operator returns 403; never fetched |

The scheduler wakes every 300 s but **only checks a source when its own cadence is due**. An idle
cycle sends no request and still drains any pending pipeline work (for example after a restart
during graph materialisation).

## 5. Backup

```bash
sudo systemctl start medradar-radar-backup.service          # on demand
sudo journalctl -u medradar-radar-backup -n 20 --no-pager
sudo ls -l /srv/medradar/data/radar/backups/
```

Each backup is one consistent copy of `radar.db` taken with SQLite's online backup API while the
scheduler keeps running. The copy is verified (`PRAGMA integrity_check` plus observation and
version counts against the source), then written with a JSON manifest holding both SHA-256
digests. A failed verification leaves `verified: false` in the manifest and the unit exits
non-zero. `graph.db` is deliberately not copied: it is a projection and can be rebuilt.

## 6. Restore drill

```bash
sudo -u medradar MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /srv/medradar/radar-venv/bin/python -m medradar radar restore-check \
  --backup /srv/medradar/data/radar/backups/<file>.db \
  --work-dir /srv/medradar/data/radar/restore-drill
```

The drill copies the backup into the isolated directory, opens it read-only, runs the ledger's
consistency check, rebuilds `graph.db` from it, and reports counts. It never touches the live
data directory. Delete the drill directory afterwards.

To promote the restored copy after a real loss: stop the scheduler and web, move the damaged
`radar.db` aside (never delete it), copy the backup into place, run `radar rebuild-graph`, start
the services, and run `radar verify`.

## 7. Rollback

The Radar deployment cannot affect the FDA pipeline; rolling it back is local to these units.

```bash
# stop the Radar surface
sudo systemctl disable --now medradar-radar-tunnel.service \
                          medradar-radar-web.service \
                          medradar-radar-scheduler.service \
                          medradar-radar-backup.timer
```

To go back to a previous release:

```bash
sudo ln -sfn /srv/medradar/radar/releases/<previous-sha> /srv/medradar/radar/app
sudo /srv/medradar/radar-venv/bin/python -m pip install -e \
     "/srv/medradar/radar/releases/<previous-sha>[product]"
sudo systemctl start medradar-radar-scheduler.service medradar-radar-web.service
```

(The editable install must be re-run because the venv's path points at the release directory, not
at the `app` symlink.) `DEPLOYED_SHA` records the commit in service.

If only the tunnel is unhealthy, restart `medradar-radar-tunnel.service`; the data and the
scheduler are unaffected. If the alpha credential env file is lost, the web service fails closed
(401 for everything except `/healthz`) rather than opening up.

## 8. Resource envelope (measured on this host)

`systemd` cgroup limits in the unit files are set from measurements on the 2 vCPU / 3.6 GiB
Lighthouse instance; see `docs/radar/LAUNCH_001_ACCEPTANCE.md` for the numbers. The scheduler and
the web process are independent cgroups, so a runaway adapter cannot take memory from the FDA
pipeline, and `OOMPolicy=stop` fails the affected Radar unit rather than the host.

## 9. Known limitations

- Quick Tunnel hostname changes on restart and is not a production domain. A stable address
  requires a domain (or `sslip.io`) plus inbound 80/443, which needs the Lighthouse firewall to
  be opened; the current firewall exposes only 22, so the tunnel is the only option that does not
  change the host's network posture.
- No model runs in production. The 3.3 GB Qwen3-0.6B worker is disabled; the AI queue grows and
  is reported as deferred.
- GE HealthCare news is not monitored (operator blocks automated access). GE evidence in the
  graph comes from FDA records and publication affiliations, and is labelled as such.
- Crossref corroboration of PubMed DOIs is bounded per invocation
  (`radar corroborate-doi --limit N`); it is an explicit operator step, not an unbounded sweep.
