# LAUNCH-001 — Live Production & Mobile Alpha Acceptance

Measured on the Tencent Cloud Lighthouse host (2 vCPU, 3.7 GiB RAM, Ubuntu 24.04) on
2026-11-17 between 08:13 and 09:05 CST. Every number below was read from the running services or
the deployed databases; nothing is projected.

## 1. Deployment identity

| Item | Value |
| --- | --- |
| Release commit deployed | `bfcee0508451b93c6ecd70061568e71d20e69218` |
| Release tree | `/srv/medradar/radar/releases/<sha>` (symlinked as `/srv/medradar/radar/app`) |
| Virtualenv | `/srv/medradar/radar-venv` (editable install of the release) |
| Data directory | `/srv/medradar/data/radar` |
| Python module resolved from | the release tree (verified during deploy) |
| Existing FDA worktree | `/srv/medradar/app` — untouched, still `medradar-web.service` on 127.0.0.1:8787 |

## 2. Public alpha

- URL: `https://silly-facing-deferred-radar.trycloudflare.com`
- Transport: Cloudflare Quick Tunnel (outbound only). The host firewall exposes only :22, so a
  direct Caddy + Let's Encrypt deployment would have required changing inbound policy; the tunnel
  is the option that adds no inbound surface.
- Authentication: HTTP Basic, PBKDF2-SHA256 (240k iterations), single user `alpha`.
- The tunnel hostname is **temporary**: it changes when `medradar-radar-tunnel.service` restarts.
- TLS: `ssl_verify_result=0` (a valid chain) from a client outside the server.
- iPhone-shaped verification: Chromium at a 390 × 844 CSS px viewport. Feed, evidence drawer and
  technology map render in Chinese with no horizontal overflow (`document.scrollWidth` 390/390 on
  the feed, 375/390 on the map).

Public probe from outside the server (not localhost):

| Request | Result |
| --- | --- |
| `GET /healthz` | 200 |
| `GET /radar` without credentials | 401 + `WWW-Authenticate` |
| `GET /radar` with credentials | 200 |
| `GET /api/radar/feed?limit=2` with credentials | 200 |
| `GET /api/review/ledger` (even authenticated) | 404 |
| `GET /api/export/devices` | 404 |
| `GET /api/docs`, `/openapi.json` | 404 |
| `GET /api/identity/organizations` | 404 |
| `GET /radar.db`, `/data/radar/radar.db` | 404 |
| `POST /api/radar/feed` | 405 |
| `GET /..%2f..%2fetc%2fpasswd` | 400 (rejected before the app) |

## 3. Live monitoring

| Source | Cadence | Status | Last check | Watermark |
| --- | --- | --- | --- | --- |
| openfda_device | 24 h | OK | 2026-11-17T00:14:22Z | 2026-11-02 |
| pubmed | 6 h | OK | 2026-11-17T00:14:39Z | 2026-11-17 |
| crossref | 12 h | OK | 2026-11-17T00:15:03Z | 2026-11-17 |
| philips_official | 12 h | OK | 2026-11-17T01:01:33Z | 2026-11-16T07:30Z |
| draeger_official | 12 h | OK | 2026-11-17T01:01:36Z | 2026-11-09T12:41Z |
| gehealthcare_official | — | `BLOCKED_BY_ACCESS_POLICY` | never fetched | — |

- Scheduler: `medradar-radar-scheduler.service`, `Restart=always`, cycle every 300 s, source
  cadence evaluated per source. It had completed 18 cycles when measured (16 idle cycles drained the
  pipeline, two cycles performed real source checks).
- First real cycle: 08:13:34 → 08:19:14 CST (openFDA sweep, PubMed, Crossref, Philips, Dräger).
- Controlled second check (09:01 CST / 01:01 UTC): Philips and Dräger both returned
  `NEW_RECORDS=0, UPDATED=0, NO_CHANGE=true` — a real "nothing new", not silence.
- No duplicate writers: one `radar watch` process; the DATA-003 lock is taken every cycle.

## 4. Intelligence recorded

| Metric | Value |
| --- | --- |
| Observations | 8,227 |
| Versions / change events | 8,227 / 8,227 (first load, one version each) |
| FDA regulatory records | 6,936 |
| Publications | 1,255 (939 Crossref, 260 PubMed, 56 Crossref corroborations) |
| Vendor press releases | 36 (31 Dräger, 5 Philips) |
| Discovery phase | 100 % `INITIAL_DISCOVERY` — every record was public before the source was enabled |
| Cross-source works verified by DOI | 56 |
| `OFFICIAL_IDENTIFIER_MATCH` edges | 56, all `doi_exact_match` |
| Verified link sample | FDA 200, Dräger 200, Philips 200, PubMed 203 (non-authoritative but served); `doi.org` returns 403 to this bot for Wiley titles (publisher bot wall; unchanged for a browser) |

Relevance gate: in the two bounded corroboration batches, 100 candidate records were examined,
56 were admitted and 44 rejected — 41 of them as "a clinical study that uses monitoring data but
does not study monitoring technology" and 3 as DOI/registration mismatches.

## 5. Technology map

- 13 topic branches with evidence; 3 companies switchable (Philips, GE HealthCare, Dräger).
- Evidence counts per company/topic come from: regulatory product codes, publication
  affiliations, and official documents.
- **Reported product capabilities: 0.** No vendor document in this batch contained an explicit
  launch statement that named a product, so no capability edge was created. This is the correct
  empty result, not a rendering omission.
- Research evidence (affiliated publications): Philips 8 publication-topic edges, GE HealthCare 1,
  Dräger 0 across all topics. Sparse because only 20 of 1,255 publications carry a monitored
  vendor affiliation.
- Every branch exposes its cited records (`evidence_id`, source URL, `valid_from`, `recorded_at`)
  and the UI opens a node/evidence drawer.

## 6. Infrastructure measurements

| Unit | Current RSS | Peak RSS | Restarts | Notes |
| --- | --- | --- | --- | --- |
| medradar-radar-web | 43.8 MB | 45.8 MB | 0 | `MemoryHigh=448M`, `MemoryMax=768M` |
| medradar-radar-scheduler | 19.4 MB | 19.5 MB (post-restart); 149.6 MB during the first full cycle | 1 (deliberate SIGKILL test) | `MemoryHigh=384M`, `MemoryMax=640M` |
| medradar-radar-tunnel | 17.3 MB | 24.3 MB | 0 | `MemoryMax=256M` |
| medradar-web (existing FDA) | 390.2 MB | 398.7 MB | 0 | untouched |

Host: 2.7 GB available, swap 205 MB of 1.9 GB used, load 0.57, PSI memory `some avg300=2.95`,
**0 OOM kills**, 0 cgroup `oom_kill` events, disk 10 GB / 59 GB used.
The FDA update timer ran at 08:38 CST while the Radar services were live and finished cleanly.

## 7. Backup and recovery

- Online backup: 40,620,032 bytes, `integrity_check=ok`, `verified=true`, SHA-256 recorded for
  source and copy, observation counts equal (8,227). Elapsed 0.36 s. Retention 14.
- Restore drill into an isolated directory: `ok=true`, integrity ok, 8,227 observations, graph
  rebuilt from the backup to **22,891 nodes** (edges 17,612). The live ledger was not touched.
- Crash recovery: `SIGKILL` of the scheduler main PID → systemd restarted it after 20 s, the lock
  was released, the next cycle ran, `radar verify` reported integrity OK with unchanged counts.
- Graph rebuild: `radar rebuild-graph` reproduced 22,891 nodes / 17,612 edges from the ledger.

## 8. Defects found by deploying (and fixed)

1. JSON-validity rate divided by parsed outputs (100 % instead of 78.6 %); organisation accuracy
   also excluded unparseable answers.
2. Idle cycles returned before advancing the pipeline, so a restart during materialisation left
   the graph partial for hours.
3. Release symlink broke the SPA static-file containment check: every asset request returned
   HTML and the app rendered nothing.
4. `rebuild-graph` and the restore drill both materialised nothing because the ledger still said
   everything was materialised in the graph being replaced; the drill also reported `ok` anyway.
5. A late-arriving DOI peer did not invalidate the already-materialised side, so 8 of 27 joins
   were missing.
6. The map page downloaded every graph assertion on load; the map response also returned
   hundreds of products per company (megabyte-scale). Both are now bounded/cached.
7. `--no-ai` cycles still queued enrichment work that nothing could claim.
8. On a 390 px viewport a chip kept `white-space: nowrap` around a long evidence title and grew
   the card to 625 px, scrolling the page sideways; and the technology-tree tab read `(0)` while
   the 2.5 s map snapshot loaded, which looks like a real empty result.

## 9. Limitations

- The public hostname is a Quick Tunnel address, not a stable domain; it changes on restart.
- Only one human user exists; there is no per-user account system.
- GE HealthCare news is not monitored (operator 403). GE evidence comes from FDA records and
  publication affiliations only.
- Reported product capability is empty because no launch document was captured in the first
  batch; regulatory evidence is not capability evidence.
- No local model runs in production. The 3.3 GB Qwen3-0.6B worker is disabled by policy; the
  queue is retired and the UI says enrichment is not enabled.
- Detection latency is only meaningful on `INCREMENTAL_DISCOVERY` records; the current median
  (447 h) is computed over 5 samples and describes first-load records, not steady-state latency.
- Publisher pages behind bot walls (e.g. Wiley) return 403 to the server's fetcher; a human
  browser can open them. The identifier itself is verified against Crossref metadata.
- Crossref corroboration is a bounded operator command (`--limit`), not an unbounded background
  sweep.
- Rate-limit exhaustion, disk-full and hostile-input paths are covered by unit tests, not by a
  production fault injection.
- The Windows development host cannot run the full e2e Playwright suite here; mobile acceptance
  used the live public URL at a phone viewport.

## 10. Verdict

**PUBLIC ALPHA LIVE** — continuous monitoring is running on the production host and the product is
reachable over HTTPS from outside the server, behind authentication, with a verified backup and a
tested restore path.
