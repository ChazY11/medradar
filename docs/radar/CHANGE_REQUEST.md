# Production deployment change request — RADAR-001

**State: NOT DEPLOYED. Nothing in production was modified by this branch.**

Scope of this change request: adding the Live Intelligence Radar and the Company Technology
Graph to the existing MedRadar deployment **without touching** the current web service, the
DATA-003 FDA pipeline, its snapshots, systemd units, SSH or firewall.

| Item | Value |
| --- | --- |
| Branch | `feat/radar-001-live-intelligence-graph` |
| Base | `feat/product-004-intelligence-workbench` (PR #53 head) |
| Migration required | none on the existing FDA data |
| New data paths | `<MEDRADAR_RADAR_DIR>/radar.db`, `graph.db` (default `data/radar/` in a checkout) |
| New processes | none required; optionally one `medradar radar watch` scheduler |
| New dependencies | none for discovery; `torch` + `transformers` only for the optional AI worker |
| Rollback | stop the scheduler, remove the radar data directory, restore the previous web unit |

## 1. Why deploy at all

The product direction is continuous intelligence. The branch already runs against the real
sources, so the remaining risk is operational, not technical: does an always-on scheduler
disturb the existing 2 vCPU / 4 GB host that carries the FDA pipeline and the web service?

## 2. Preconditions to verify on the host (all must pass)

1. **Memory headroom.** `free -m` shows ≥ 900 MB available with the web service and the FDA
   sync at their normal footprint. The radar's discovery path is small (SQLite + HTTP), but its
   graph materialisation for a first load of ~9k observations is a Python loop.
2. **Disk.** ≥ 2 GB free under the radar data directory. The acceptance store is ~90 MB for
   8.6k observations; budget 10x for growth and backups.
3. **Existing web unit untouched.** The radar API is mounted only when `--radar-dir` or
   `MEDRADAR_RADAR_DIR` is set. Verify the production unit does **not** set it before the
   change, and set it only in the new unit or after an approved restart.
4. **No AI on this host by default.** The measured peak RSS of the 0.6B float32 worker is
   ~3.2 GB. On a 4 GB host the resource guard will defer every batch. Leave `MEDRADAR_AI_PYTHON`
   unset until a quantised build is measured.

## 3. Deployment steps (manual, supervised)

```bash
# 1. create the data directory OUTSIDE the web root and outside the FDA data path
sudo install -d -o medradar -g medradar -m 0750 /srv/medradar/data/radar

# 2. run one real check as the service user and inspect the result BEFORE scheduling
sudo -u medradar MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /opt/medradar/venv/bin/python -m medradar radar run
sudo -u medradar MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /opt/medradar/venv/bin/python -m medradar radar advance
sudo -u medradar MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /opt/medradar/venv/bin/python -m medradar radar status
sudo -u medradar MEDRADAR_RADAR_DIR=/srv/medradar/data/radar \
  /opt/medradar/venv/bin/python -m medradar radar verify     # exit 2 on any integrity problem
```

Only if `status` reports `state: ok` and `verify` exits 0:

```bash
# 3. install the scheduler unit (a separate unit; the web service is not restarted)
#    a unit file is provided as a template, not installed by this branch:
#    docs/radar/deploy/medradar-radar.service
sudo systemctl daemon-reload
sudo systemctl enable --now medradar-radar.service
```

```bash
# 4. expose the read-only API: ONLY on an approved restart of the web service
#    add --radar-dir /srv/medradar/data/radar to the existing unit's ExecStart,
#    then (approved window) systemctl restart medradar-web.service
```

## 4. What the scheduler does on the host

* one process, one file lock (`radar.db.lock`); a second instance exits with `LOCKED`;
* per-source cadence from `config/radar/sources.json` (FDA 24 h, PubMed 6 h, Crossref 12 h,
  vendors 12 h), so most cycles are `IDLE` and send no request;
* at most 400 HTTP requests per cycle (hard budget in the transport);
* AI deferred unless the guard passes (it will not, on this host);
* every cycle writes `last_cycle` + `cycle_counter` and appends nothing to the FDA pipeline.

## 5. Observability after deployment

| Check | Where | Expectation |
| --- | --- | --- |
| Process alive | `systemctl status medradar-radar` | active |
| Cycle | `radar status` → `last_cycle` | a new `finished_at` each interval |
| Sources | `radar status` | five `OK`, one `BLOCKED_BY_ACCESS_POLICY` |
| Integrity | `radar verify` | exit 0 |
| Backlog | `radar status` → `ai backlog` | grows; that is expected and harmless |
| Web | `GET /api/radar/health` | 200, `state: ok` |
| Memory | `systemd-cgtop` / `free -m` | radar discovery process < 150 MB |

## 6. Rollback

```bash
sudo systemctl disable --now medradar-radar.service
# if the web service was restarted with --radar-dir, remove the flag and restart in a window
sudo mv /srv/medradar/data/radar /srv/medradar/data/radar.rolled-back-$(date -u +%Y%m%dT%H%M%SZ)
```

The FDA pipeline and the product snapshot are not touched by any of these steps, so rollback
cannot affect them. The radar data directory is self-contained: `radar.db` (observations) and
`graph.db` (derived).

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Memory pressure from graph materialisation | it runs per observation with a bounded batch (`advance --limit`), and the first full load is a one-off; verify with `free -m` during step 2 |
| A scheduler bug burning the daily request budget | transport budget (400/cycle) + per-host rate limits + per-source cadence |
| A source changing its HTML and breaking a vendor adapter | the adapter records a failure, the cursor does not advance, the rest of the system keeps running; `radar status` shows `DEGRADED` |
| Graph rebuild deleting history | impossible: the graph is a projection in a separate file; the ledger is append-only, enforced by SQL triggers |
| Silent data loss on restart | interrupted runs are marked `INTERRUPTED`, checkpoints are reused, and `radar verify` fails on any inconsistency |

## 8. What is explicitly out of scope for this change

* merging the Draft PR;
* modifying the DATA-003 FDA pipeline, its snapshots or its units;
* enabling the AI worker on the production host;
* any change to SSH, firewall or external notification channels;
* sending email or enterprise-chat messages (the interface is left as an adapter point; no
  account is connected and no message is sent).
