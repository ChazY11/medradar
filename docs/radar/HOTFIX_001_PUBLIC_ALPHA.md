# HOTFIX-001 — Public Alpha mobile experience

Status: fixed and deployed. This file records what was actually broken, how it was proven, and
what changed. Every number was measured on the production host or through the public URL.

## 1. Symptoms reported

On an iPhone, pages stayed on grey skeletons; the site felt frozen. The server journal for the
user's session (19:34–19:36 CST) showed the workbench navigation calling APIs that the public
gate correctly refuses:

```
/api/events 404, /api/organizations 404, /api/review/* 404, /api/metrics 404,
/api/devices 404, /api/data-status 404, /api/changes 404, /api/compare 404, /api/attribution 404
```

## 2. Root causes (confirmed, not inferred)

1. **PBKDF2 on the event loop, on every request.** HTTP Basic means the browser re-sends the
   password for every script, style and API call. The gate verified a 240 000-iteration
   PBKDF2-SHA256 hash *synchronously inside the ASGI middleware*. A `py-spy` dump of the wedged
   process showed `MainThread → verify_password` while two AnyIO workers decoded graph snapshots.
   Measured: `/healthz` took **224.6 s**; the tunnel returned nothing for 90 s; the worker had to
   be restarted to recover.
2. **The serving process opened `graph.db` read-write.** `open_graph()` → `TKGStore()` ran the
   schema script and committed on **every** request, so concurrent views serialised on a write
   transaction against a file the scheduler also writes.
3. **Every graph view rebuilt a full snapshot.** 22 891 nodes / 17 612 edges were re-read and
   JSON-decoded per request (≈2.5 s of CPU). The map page also fetched compare *and* changes on
   mount; `changes` returned every assertion (multi-megabyte).
4. **Navigation contradicted the route allowlist.** The SPA still rendered the whole workbench
   (Overview, Brief, Organizations, Events, Compare, Sources, Data Status, Devices, Review) plus
   a search box calling `/api/search`. Every one of those calls is a 404 by design, and several
   of those pages render a loading block when data never arrives — the persistent skeleton.
5. **Company chips toggled instead of selected.** Tapping Dräger hid Dräger and left the other
   two, which reads as a broken filter.

## 3. Fixes

| Area | Change | File |
| --- | --- | --- |
| Auth cost | Verify the password off the event loop and issue an HMAC session cookie (HttpOnly, SameSite=Lax, Secure over TLS); later requests never re-hash | `medradar/radar/alpha_gate.py` |
| Legacy URLs | Known old workbench addresses 302 to `/radar`; unknown paths still 404 | `medradar/radar/alpha_gate.py` |
| Graph locking | Serving opens the graph read-only | `medradar/radar/graph.py`, `medradar/radar/api.py` |
| Graph cost | File-identity-keyed snapshot cache (20 s, max 2 entries) + serialised view builds; compare cached; changes capped at 300 rows with explicit totals | `medradar/tkg/query.py`, `medradar/radar/api.py` |
| Status cost | `/api/radar/health` cached 15 s (reports `cache_ttl_seconds`) | `medradar/radar/api.py` |
| Public navigation | The server injects `window.__MEDRADAR_ALPHA__`; the SPA renders only 实时雷达 + 科技地图, hides search/snapshot, sends the brand to `/radar`, and routes everything else there | `medradar/product/api.py`, `web/src/App.tsx`, `web/src/components/AppShell.tsx`, `web/src/lib/alpha.ts` |
| Tab loading | The map page fetches only the open tab (map / compare / changes) | `web/src/pages/TechnologyMapPage.tsx` |
| Company switch | Exclusive selection (全部 / Philips / GE HealthCare / Dräger) | `web/src/pages/TechnologyMapPage.tsx` |

## 4. Before / after

| Measurement | Before | After |
| --- | --- | --- |
| `/healthz` (loopback) | **224.6 s**, then unreachable | **0.002–0.003 s** |
| Public page request | 90 s timeout (no response) | 0.9–1.6 s to first card |
| First Contentful Paint (public, 390 px) | never painted | **0.93–1.06 s** |
| First intelligence card visible | never | **1.43–1.62 s** |
| Reload with a warm session | n/a | **2.1 s** |
| 10 parallel technology-map requests | all timed out at 90 s; worker wedged | **0.09–0.10 s each**, worker healthy |
| Authenticated request with session cookie | n/a (hash per request) | **0.002 s** |
| `graph/changes` response | every assertion (multi-MB) | **205 KB**, truncated with totals |
| Radar web memory | 45 MB idle, then wedged | **210 MB current / 212 MB peak**, no OOM |

## 5. Browser acceptance through the public HTTPS URL

Chromium, mobile viewport 390 × 844, authenticated:

- `/organizations` → 302 → `/radar` (no bare 404).
- Home/feed: 20 cards, company filter (request `organization=philips`, 223 matching records),
  evidence drawer opens, official PubMed link present (`https://pubmed.ncbi.nlm.nih.gov/43040325/`).
- Phone menu contains exactly 实时雷达 / 科技地图.
- Technology map: 13 branches, `科技树 (13)`; switching to Dräger sends
  `companies=draeger` and removes the Philips column; switching to GE HealthCare sends
  `companies=ge_healthcare`; evidence table expands with cited rows.
- 企业对比: 16 topic rows, header follows the selected company (技术主题 / GE 医疗).
- Back to the feed and refresh: 20 cards again.
- Zero failed requests, zero console errors, `document.scrollWidth` 375–390 vs viewport 390.

WebKit/Safari was **not** executed: this harness drives Chromium only. The iPhone-shaped
viewport is Chromium at 390 × 844, not real Safari.

## 6. Remaining issues

- TLS/domain: the address is still a Cloudflare Quick Tunnel hostname that changes on restart.
- The relevance gate still admits borderline clinical papers that merely mention a monitored
  measurement (observed card: a TIMI risk-score study matched the ECG topic).
- 企业对比 and 变化 are English-labelled in a few places; the main tree is Chinese.
- The first `/api/radar/health` and first `technology-map` call after a restart are still
  ~2–2.3 s (cold cache). The feed paints independently, so this no longer blocks first content.
- WebKit/iOS Safari verification remains open; it needs a real WebKit driver.
