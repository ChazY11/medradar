# SOURCE_DISCOVERY_EXTRAS — deep probe of the four non-Medtronic focus firms
## Phase 4 · Innovation Signals Observatory · recruitment lane (WP2a)

**Date:** 2026-11-04 (Asia/Shanghai) · **Probe window:** 20:55–21:25
**Network position:** mainland China — a material caveat (see §7)
**Supersedes** the four exploratory rows of `SOURCE_DISCOVERY.md` §2; the Medtronic
section of that document is unchanged and still the Lead's.
**A companion to, not a replacement for,** `SOURCE_DISCOVERY.md`: same status vocabulary,
same "measured, never assumed" rule.

> This file records only what requests returned: status codes, robots.txt rules verbatim,
> endpoint shapes, field presence, and the exact failure text where something failed.
> A route that could not be exercised is recorded as such — never as "probably works",
> and never as "the company is not hiring".

---

## 1. Verdict matrix (measured 2026-11-04)

| firm | accessible from this network? | platform | lawful listing route | stable id field | source date field → precision | full description | robots verdict for the needed paths | **verdict** |
|---|---|---|---|---|---|---|---|---|
| **GE HealthCare** | yes | Phenom (`careers.gehealthcare.com`) | sitemap `.../global/en/sitemap_index.xml` (advertised in robots) → 3 sub-sitemaps → **1,035** posting URLs `/global/en/job/<req>/<slug>` | JSON-LD `identifier.value` (`R4045928`) | `datePosted` → `SOURCE_DATE` (plain ISO date) | full HTML in JSON-LD `description` | robots.txt 200, disallows only `*/apply`, `*/jobcart`, `*/chatbot` …; sitemap + posting paths **allowed** | **VERIFIED** |
| **Philips** | yes | Phenom (`www.careers.philips.com`) | sitemap `.../global/en/sitemap_index.xml` (host publishes **no** robots.txt) → 2 sub-sitemaps → **805** posting URLs `/global/en/job/<id>/<slug>` | JSON-LD `identifier.value` (`594302`) | `datePosted` → `SOURCE_DATE`, **or** a midnight timestamp `2026-11-04T00:00:00.000+0000` → `SOURCE_DATETIME` with an explicit "day precision" note | full HTML in JSON-LD `description` | no robots.txt is published: `/robots.txt` returns the SPA HTML shell (`text/html`, no REP directives) → RFC 9309 unavailable path applied **explicitly** and recorded; site's own `<meta name="robots" content="index">` | **VERIFIED** |
| **Mindray** | yes | Beisen (`mindray.zhiye.com`) | official portal JSON: `POST /api/Jobad/GetJobAdPageList` (the site's own list request); detail `GET /api/JobAd/GetJobAdInfo`; page `/social/detail?jobAdId=<Id>` | JSON `Id` (GUID, used in the public detail URL) | `PostDateInt` epoch-ms → converted **once** to UTC `2026-11-04T07:49:34+00:00`; local rendering `PostDate` kept verbatim; UTC+8 agreement checked | `Duty` + `Require` text (both in the listing response; no detail call needed) | robots.txt `User-agent: * / Allow: /` → allowed | **VERIFIED** |
| **Dräger** | yes for the job board; no for the corporate CMS | Beesite e-recruitment portal (`erecruitment.draeger.com`) + UK Teamtailor board | public Beesite search JSON (the portal's own list request): **171** current postings; and portal sitemap `.../sitemap.xml` → **171** job-ad URLs. Job-ad pages carry schema.org `JobPosting` | job-ad URL id (`?ac=jobad&id=19717`); JSON-LD `identifier.value` (`J000019717`) kept as an alternate | JSON-LD `datePosted` → `SOURCE_DATE` (list API `PublicationStartDate`, same day) | full HTML in the job-ad page's JSON-LD `description` | `erecruitment` robots.txt = a bare `Sitemap:` line, no rules → allowed; Beesite host publishes **no** robots.txt (404 JSON) → RFC 9309 unavailable path recorded | **VERIFIED** |

**Collection evidence (bounded, ≤80 postings/firm):**

| firm | rows written | unique ids | description rate | source-date rate | location rate | detail failures | requests | artifact |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| GE HealthCare | 80 | 1.00 | **0.9125** | 0.9125 | 0.9125 | 7 (`410 Gone` sitemap entries, kept as `DETAIL_FAILED`) | 85 | `jobs_ge_healthcare.jsonl`, `collection_ge_healthcare.json` |
| Philips | 80 | 1.00 | **0.95** | 0.95 | 0.95 | 4 (`410 Gone`, kept) | 84 | `jobs_philips.jsonl`, `collection_philips.json` |
| Mindray | 80 | 1.00 | **1.00** | 1.00 | 1.00 | 0 | 6 | `jobs_mindray.jsonl`, `collection_mindray.json` |
| Dräger | 80 | 1.00 | **0.96** | 1.00 | 1.00 | 3 (kept as `DETAIL_FAILED`, listing date preserved) | 83 | `jobs_draeger.jsonl`, `collection_draeger.json` |

The Lead's `VERIFIED` floor (`SOURCE_DISCOVERY.md` §1) is ≥20 postings, id ≥0.95,
description ≥0.90, source date ≥0.50. All four clear it. **This does not mean the four
firms are now fully studied** — the figures are 80-posting samples of each firm's own
visible population, not a census, and the populations differ by orders of magnitude
(1,035 GE HealthCare sitemap URLs vs 171 Dräger postings in total).

**Bounded sample, not population.** The 80 rows per firm are the **first 80 postings of a
bounded, ordered enumeration**, not a complete ingest:
GE HealthCare = newest-`lastmod` 80 of 1,035 sitemap URLs; Philips = newest-`lastmod` 80 of
805 sitemap URLs; Mindray = 80 of 141 social-hire (category `1`) postings, first page(s) of
`GetJobAdPageList`; Dräger = newest-`PublicationStartDate` 80 of 171 current postings from
the Beesite search API (`SearchResultCountAll = 171`). The remaining postings were **not**
collected this round. `truncated_at_ceiling` in each `collection_*.json` records whether
the cap bit (it did for every firm).

---

## 2. Field contracts, measured

| firm | identity (and why not the slug) | date semantics | description completeness | legal entity |
|---|---|---|---|---|
| GE HealthCare | `identifier.value` = requisition id (`R4045928`). The URL token (`GEVGHLGLOBALR4045928EXTERNALENGLOBAL`) embeds the req id but is treated only as fallback, because a retitled posting can change the slug | `datePosted` is a plain ISO date on all sampled pages → `SOURCE_DATE`. Source's precision only; no time invented | JSON-LD `description` is HTML **escaped once inside the JSON string**; unescaped once then tag-stripped to text. Full JD (median ~9 k chars in the sample) | career site states brand only → `legal_entity = null`, `COMPANY_KEY_ONLY` |
| Philips | `identifier.value` = numeric posting id (`594302`) | two renderings observed: plain ISO date, and `2026-11-04T00:00:00.000+0000` — a timestamp whose time-of-day is exactly midnight. Kept **verbatim** as `SOURCE_DATETIME` with `raw.date_note` saying the meaningful precision is the day, so nobody shifts it by a timezone | same escaped-HTML JSON-LD path | brand only → `null` |
| Mindray | `Id` = GUID (`7fa91977-…`), the token the portal itself uses in the public detail URL. The integer `JobAdId` is a secondary key | `PostDateInt` epoch-ms → UTC exactly once. `PostDate` (`2026-11-04T15:49:34`) is the tenant's UTC+8 rendering, stored verbatim; the collector verifies `epoch + 8h == rendering` and records `epoch_matches_utc+8_rendering`. If the epoch were missing, quality would be `NONE` — the wall-clock string is never converted | `Duty` (responsibilities) + `Require` (requirements) concatenated in source order; both are returned by the **listing** endpoint, so `raw.description_source` says so instead of implying a detail page was read | brand only → `null` (the portal's tenant metadata names Shenzhen Mindray Bio-Medical Electronics, but that is site-level, not per posting) |
| Dräger | portal URL id (`19717`), which is what the sitemap and the job-ad URL use; JSON-LD `identifier.value` (`J000019717`) kept as `posting_id_alt` | `datePosted` plain date; Beesite list `PublicationStartDate` agrees | full HTML description on the job-ad page; the Beesite search API carries **no** description, so a collector must pair list + page | **stated by the source**: `ParentOrganizationName` per posting (`Drägerwerk AG & Co. KGaA`, `Dräger Safety AG & Co. KGaA`, `Dräger Medical ANSY GmbH`, `Dräger Norge AS`, …). Recorded as the source's claim, `COMPANY_KEY_ONLY` (not resolved to a universe entity key) |

**Sitemap staleness is recorded, not swallowed.** Both Phenom sitemaps list postings that
have since been removed: 7/80 GE HealthCare and 4/80 Philips detail requests returned
`410 Gone`. Each is kept as a `DETAIL_FAILED` observation carrying its source-derived id and
URL, so a fetched failure can never be read as "the posting never existed".

---

## 3. Dräger: what failed, and what actually works

The Lead's first-round probe concluded `BLOCKED（网络不可达）` for Dräger. **That is now
superseded for the job data, and the correction matters.** Three separate surfaces were
measured:

**(a) Corporate CMS `www.draeger.com` — not usable by a scripted client, and the guessed path is dead.**
The speculative `https://www.draeger.com/en/careers` is **not** a careers page: a real browser
reaches it and receives the site's own **HTTP 404** page. The CMS is fronted by Akamai bot
management: a browser-like `User-Agent` without a browser TLS/HTTP fingerprint gets its
connection held and then timed out (20–90 s), while a plain non-browser client is answered
`403` on `/` and `404` on that path in milliseconds. `robots.txt` is served statically and
answers 200. **No attempt was made to defeat the bot challenge**, and the CMS is not needed.

**(b) The real job board: `erecruitment.draeger.com` (Beesite front end).**
Linked from the German careers page. `robots.txt` is a bare
`Sitemap: https://erecruitment.draeger.com/sitemap.xml` with no rules; the sitemap lists
213 URLs of which **171 are job-ad URLs** (`/index.php?ac=jobad&id=<id>`); every sampled
job-ad page carries a schema.org `JobPosting` JSON-LD with `datePosted`, `identifier`
(`J0000…`), `hiringOrganization` (a real Dräger operating company) and a full description.

**(c) The public Beesite search API — the request the portal's own JavaScript makes.**
`GET https://draeger-beesite-production-gjb.app.beesite.de/search/?data=<url-encoded JSON>`
returns JSON with `SearchResultCountAll = 171` current postings and per posting: `ID`,
`PositionTitle`, `PositionURI`, `PublicationStartDate`, `ParentOrganizationName`,
location, category, career level, schedule. No login, captcha or access control. The host
publishes **no robots.txt** (HTTP 404 JSON) — the RFC 9309 unavailable case, recorded.
That is the end-to-end route: **list from Beesite API, description from the job-ad page.**

**(d) Secondary: UK & Ireland board `ukjobs.draeger.com` (Teamtailor).**
The UK careers page exposes it; 8 postings; `robots.txt` permits `/jobs` (disallows only
`/app/`, `/messages/`, `/jobs/internal/`); sitemap lists 8 job URLs; a sampled job page
carries full `JobPosting` JSON-LD (`identifier.value = 8636814`,
`datePosted = 2026-10-29T13:21:56+00:00`, description 9,919 chars). Also lawful and
collectable — but a separate regional board, not a global census.

**`SOURCE_UNAVAILABLE` verdict:** applies **only** to the corporate marketing CMS for
scripted clients from this network. It does **not** apply to Dräger job data. The exact
failures are in `source_probe_draeger.json` (`routes.corporate_careers_page`,
`routes.portal_*`, `routes.beesite_*`, `routes.uk_teamtailor_*`).

**Exact request results for the claims above** (a timeout, a 404, and a bot-stall are
three different things; this table keeps them apart):

| request | client | measured answer |
|---|---|---|
| `https://www.draeger.com/en/careers` | scripted, browser UA, one attempt | **no HTTP status** — `TimeoutError: The read operation timed out` after **20,233 ms** (a second ad-hoc run with a 90 s budget timed out at **90,030 ms**) |
| `https://www.draeger.com/en/careers` | `curl.exe`, default UA | **HTTP 404** in **106 ms** |
| `https://www.draeger.com/en/careers` | `curl.exe`, browser-like UA | connection stalled, no response: `curl` timed out at **40,002 ms** / one `Recv failure: Connection was reset` after **21,608 ms** |
| `https://www.draeger.com/en/careers` | **real Chromium browser** (this session) | **HTTP 404**, page title “Page not found (404)” — i.e. the path is *not* a careers page |
| `https://www.draeger.com/` | `curl.exe`, default UA | **HTTP 403** in **38 ms** |
| `https://www.draeger.com/` | **real Chromium browser** | **200** → `302` to `https://www.draeger.com/en_uk/Home` |
| `https://www.draeger.com/robots.txt` | scripted | **HTTP 200**, `text/plain`, **109 ms**, 1,256 B |
| `https://career.draeger.com/`, `https://draeger.taleo.net/…` | scripted | `URLError: [Errno 11001] getaddrinfo failed` — **DNS does not resolve** |
| `https://erecruitment.draeger.com/` | scripted | **HTTP 200** → `https://erecruitment.draeger.com/index.php?ac=start`, `text/html`, **37,379 B** |
| `https://erecruitment.draeger.com/robots.txt` | scripted | **HTTP 200**, 53 B: only `Sitemap: …/sitemap.xml` |
| `https://erecruitment.draeger.com/sitemap.xml` | scripted | **HTTP 200**, `application/xml`, 41,821 B, 213 `<loc>` of which **171** are job-ad URLs |
| `https://erecruitment.draeger.com/index.php?ac=jobad&id=18293` | scripted | **HTTP 200**, ~120,150 B HTML with `JobPosting` JSON-LD |
| `https://draeger-beesite-production-gjb.app.beesite.de/robots.txt` | scripted | **HTTP 404**, `application/json` (`{"error":{"code":404,…}}`) — no robots.txt |
| `GET https://draeger-beesite-production-gjb.app.beesite.de/search/?data=<url-encoded JSON>` | scripted | **HTTP 200**, `application/json`; `SearchResultCountAll = 171`; `MatchedObjectDescriptor` carries `ID`, `PositionTitle`, `PositionURI`, `PublicationStartDate`, `ParentOrganizationName`, location/category fields |

**Conditionality, stated plainly.** The 404 on `/en/careers` is a property of the source
(the same answer to a real browser and to a plain `curl`). The stall/timeout is a property
of **this scripted client vs. the source's Akamai bot management** (a plain non-browser UA
is answered `403`/`404` in milliseconds; a browser-like UA without a browser fingerprint
is held open until timeout). The script itself records only its own scripted answer
(`TimeoutError`); the browser and `curl` observations above are manual diagnostics recorded
here as such, not as script output. No attempt was made to defeat the bot challenge.

---

## 4. robots.txt / automated-access, per host (verbatim head in the probe JSONs)

| host | status | content type | relevant rules | decision |
|---|---|---|---|---|
| `careers.gehealthcare.com` | 200 | `text/plain` | disallows `*/phenomtrack.min.js`, `*/apply`, `*/jobcart`, `*/chatbot`, `*/glassdoor`, …; advertises 3 locale sitemaps | sitemap + posting pages **allowed** (no matching rule); robots is a real REP file |
| `www.careers.philips.com` | 200 | `text/html` | **none — not a robots file**: the SPA app shell is served for `/robots.txt` (309,710 B, no directives) | treated as **unavailable** (RFC 9309 §2.3.1.3 → unrestricted), recorded verbatim, not assumed away |
| `mindray.zhiye.com` | 200 | `text/plain` | `User-agent: *` / `Allow: /` | allowed |
| `erecruitment.draeger.com` | 200 | `text/plain` | only `Sitemap: …/sitemap.xml`; no Allow/Disallow rules | allowed |
| `draeger-beesite-production-gjb.app.beesite.de` | **404** | `application/json` | no robots.txt published | unavailable → RFC 9309 path, recorded |
| `ukjobs.draeger.com` | 200 | `text/plain` | disallows `/app/`, `/messages/`, `/messenger/`, `/facebook/tab/`, `/jobs/internal/`; `Sitemap: /sitemap.xml` | `/jobs` and `/jobs/<id>-<slug>` allowed |
| `www.draeger.com` | 200 | `text/plain` | `Disallow: /*api/`, locale/partner/search patterns | robots readable, but HTML pages are bot-managed; **not used** |

No route used logs in, solves a captcha, pays, or bypasses an access control. No candidate /
applicant data is read; only the employer's public advert. Every collector asserts robots
before the first data request and writes the verbatim evidence next to the run
(`collection_*.json → policy.robots_evidence` + `report.robots_interpretation`).

**Explicit Terms / automated-access statements.** No separate Terms-of-Use or
anti-automation statement was located on any career site's listing or posting pages during
this probe (the sites' full legal-terms pages were **not** reviewed this round). The only
machine-readable access statement found is `robots.txt`, which is exactly what the
collectors enforce. In particular, Philips' `robots.txt` being absent is recorded as
*unavailable* (RFC 9309 §2.3.1.3 → unrestricted), **not** as "explicitly permitted"; the
positive signal on that site is its own `<meta name="robots" content="index">`.

---

## 5. Dräger interface: resolved during this round

`medradar.recruitment.records.PLATFORMS` originally ended at `("workday", "phenom",
"beisen")`, so a Dräger row could not be a valid `JobObservation`. The Lead added
`PLATFORM_BEESITE = "beesite"` to that enum and in `PLATFORMS` (kept distinct from
`"phenom"` on purpose: a source platform is part of a record's provenance). With that
change this round shipped:

* `medradar/recruitment/beesite.py` — the Beesite collector, modelled on `workday.py`:
  `JobObservation` objects, `CollectionPolicy` robots authorisation for **both** hosts
  before any data request, bounded posting/request ceilings, `DETAIL_FAILED` handling, and
  `PLATFORM_BEESITE` provenance;
* `scripts/collect_recruitment_beesite.py` — the bounded run entry point;
* `jobs_draeger.jsonl` (80 `JobObservation` rows, id 1.00, desc 0.96, date 1.00,
  location 1.00, legal entity 1.00) and `collection_draeger.json`.

A throwaway `source_rows_draeger.jsonl` / `sources/collect_draeger.py` pair existed only
while the enum was missing; it was **deleted** once the real collector produced
`JobObservation` rows. There is no second, parallel record format in the tree.

**Still missing on the Dräger route:** a dedicated offline test file
(`tests/test_recruitment_beesite.py`) — outside this task's original write scope. The
JSON-LD parsing it depends on is already covered by `tests/test_recruitment_phenom.py`
(same `phenom.find_jobposting` / `description_to_text` helpers); a sibling test file should
be added when the Lead opens that scope. The live 80-posting run exercised the
robots-refusal, page-failure and date-fallback paths.

---

## 6. What this changes in `SOURCE_DISCOVERY.md`

| row | old status (21:10) | measured status now | basis |
|---|---|---|---|
| GE HealthCare | EXPLORATORY (upper bound) | **VERIFIED** | sitemap + JSON-LD + 80 collected (id 1.00, desc 0.9125, date 0.9125) |
| Philips | EXPLORATORY (upper bound) | **VERIFIED** | same, plus the robots.txt-absence finding (80 collected: id 1.00, desc 0.95, date 0.95) |
| Mindray | EXPLORATORY (upper bound) | **VERIFIED** | official JSON list+detail, 80 collected (id/desc/date/location 1.00) |
| Dräger | BLOCKED（网络不可达） | **VERIFIED** (corporate CMS unusable; official portal + public search API work; 171 current postings, 80 `JobObservation` rows collected) | `source_probe_draeger.json`, `jobs_draeger.jsonl` |
| coverage-control firm (Boston Scientific / Siemens Healthineers) | — | **NOT_RUN** (optional; not probed this round) | — |

The historical-archive failures of D-028/D-029/D-030/D-031 are **not** revisited or
re-packaged here; this round is live, source-based collection only. The earlier WayBack
routes for Philips (`philips.taleo.net`) and Dräger (`draeger.taleo.net`,
`career.draeger.com`) are confirmed dead by DNS non-resolution — recorded as dead routes,
not as coverage.

---

## 7. Limits of this evidence (honest position)

* **Network position matters.** Akamai's treatment of `www.draeger.com` is a property of this
  client/network, not necessarily of the site. A different network may get a different
  answer; this file reports this network's measurement.
* **Samples, not censuses.** 80 postings/firm were collected under a hard cap. GE HealthCare
  has 1,035 sitemap URLs, Philips 805, Mindray 141 social postings, Dräger 171 portal
  postings. The collection is a bounded snapshot, not a full ingest.
* **Mindray: social-hire category only.** The portal also has a campus category
  (`Category = "2"`, `/campus/jobs`), not collected here.
* **Dräger: regional boards.** The portal is the one reachable from the German careers page;
  the UK & Ireland Teamtailor board is separate (8 postings) and other country boards were
  not enumerated. Neither is a complete global Dräger census.
* **Phenom midnight timestamps.** The `T00:00:00.000+0000` rendering is recorded as
  `SOURCE_DATETIME` verbatim with a "day precision" note rather than being truncated to a
  date; downstream consumers must read the note, not assume a time of day.
* **A stale sitemap is not a posting.** 410/404 detail answers are recorded as
  `DETAIL_FAILED`, never dropped and never written as "no description".
* **No third-party scraper was used**, and no anti-bot mechanism was circumvented. The one
  browser-based observation (below) was discovery only.

**Manual, non-script-reproducible observation (declared as such).** A real Chromium browser
in this session (2026-11-04 ~21:04–21:10 local) reached the Akamai-fronted CMS and:
`https://www.draeger.com/` → `302` to `/en_uk/Home` (UK locale); `https://www.draeger.com/en/careers`
→ the site's own **404 page**; the UK navigation links `https://ukjobs.draeger.com/jobs`; the
German careers page (`/de_de/Career`) links `https://erecruitment.draeger.com/`; and the
`/index.php?ac=search_result` page's own JavaScript calls the Beesite `.../search/?data=…`
endpoint. These observations were then re-tested by script wherever possible
(`deep_probe.py` does re-test everything except the CMS HTML, which bot management blocks).

---

## 8. Reproduce

```powershell
# 1. the evidence probe (4 firms, ~35 bounded requests, ≥1.2 s/host)
python experiments/innovation_signals_observatory/sources/deep_probe.py `
    --out experiments/innovation_signals_observatory/results/2026-11-04

# 2. collectors (each ≤80 postings; from the repo root)
python scripts/collect_recruitment_phenom.py --company ge_healthcare --limit 80 `
    --out experiments/innovation_signals_observatory/results/2026-11-04
python scripts/collect_recruitment_phenom.py --company philips --limit 80 `
    --out experiments/innovation_signals_observatory/results/2026-11-04
python scripts/collect_recruitment_beisen.py --company mindray --limit 80 `
    --out experiments/innovation_signals_observatory/results/2026-11-04
python scripts/collect_recruitment_beesite.py --company draeger --limit 80 `
    --out experiments/innovation_signals_observatory/results/2026-11-04

# 3. offline tests (no network)
python -m pytest tests/test_recruitment_phenom.py tests/test_recruitment_beisen.py -q
```

`--no-cache` on the collection scripts keeps the raw-response cache out of the tree (the
run reports still carry request counts and robots evidence). If the cache is written, it
goes to `_httpcache_<company>/` — git-ignored, never part of the dataset.

**Request budget (measured):** probe 35; GE HealthCare 85; Philips 84; Mindray 6;
Dräger 83; total ≈293 requests for the four firms. All bounded by `CollectionPolicy`
(≥1.0 s between requests to one host, hard per-run ceilings).

---

## 9. Artifacts

| file | what it is |
|---|---|
| `results/2026-11-04/source_probe_<company>.json` | per-firm probe record: every request (status, content type, elapsed), robots evidence + path decisions, listing counts, sampled JSON-LD shapes, verdict and reason |
| `results/2026-11-04/source_probe_summary.json` | probe run summary: client identification, request log, per-firm verdicts |
| `results/2026-11-04/jobs_ge_healthcare.jsonl` / `jobs_philips.jsonl` / `jobs_mindray.jsonl` | `JobObservation` snapshots (one per line, schema `recruitment-obs-v1`) |
| `results/2026-11-04/jobs_draeger.jsonl` | `JobObservation` snapshot from the Beesite collector (schema `recruitment-obs-v1`, platform `beesite`) |
| `results/2026-11-04/collection_<company>.json` | run report: policy + robots evidence + interpretation, request stats, field-availability rates, failures |
| `medradar/recruitment/phenom.py` / `beisen.py` / `beesite.py` | collectors, modelled on `workday.py` (same records, robots policy, caps, `DETAIL_FAILED` handling) |
| `scripts/collect_recruitment_phenom.py` / `collect_recruitment_beisen.py` / `collect_recruitment_beesite.py` | bounded collection entry points |
| `sources/deep_probe.py` | the reproducible probe (request log, robots decisions, listing counts, JSON-LD shapes, verdicts) |
| `tests/test_recruitment_phenom.py` / `tests/test_recruitment_beisen.py` | offline contract tests (25 tests, no network) |