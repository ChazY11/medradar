# E1b — SOURCE RECOVERY: retrospective public availability vs prospective observation

**Task:** `task-17` · REFOUNDATION-002 Phase 2, WORKFLOW C
**Worktree:** a local worktree of this repository (not pushed) · branch `research/e1b-source-recovery` (from `origin/main` `b2a14c0`)
**Experiment:** small real sample, 28 HTTP requests total, 1 page per source, 5 records per source.
**Collected:** 2026-11-12T18:45Z (Asia/Shanghai 2026-11-13 02:45).
**Scripts:** `research/e1b/collect_e1b.py` (network, reproducible), `research/e1b/derive_findings.py` (offline).
**Evidence:** `docs/refoundation/phase2/_evidence/e1b/` — `collection.jsonl` (28 request records with true timestamps + hashes), `retrospective.json`, `prospective.json`, `findings.json`, `summary.json`.

**Discipline (hard rules honoured):** `event_date` (what happened), `first_public_*` (when the world could know), and `first_observed_at_utc` (when *we* fetched) are three different fields in three different files. No collection time was copied into a public-time field. No event date was promoted to a public date. Nothing estimated was labelled observed. No identity was invented.

**Limits:** 5 records/source is a shape test, not a distribution; one regulator (FDA), one trial registry, one issuer (Medtronic plc, CIK 0001613103). CT.gov `first-post type` was `ACTUAL` in all 5 sampled records, so ESTIMATED behaviour is evidenced by the schema, not by a sampled case. EDGAR's acceptance timestamp timezone is `Z`-suffixed and corroborated by HTTP `Last-Modified` (21–75 s later), but the authoritative SEC timezone definition was not re-read. No bulk download; no authentication; rate limits respected via sleeps.

---

## 0. Verdict summary

| Source | Retrospective public availability recoverable? | Prospective observation | Overall verdict |
|---|---|---|---|
| **openFDA 510(k) / PMA** | **NO** — no public-posting date is exposed; `decision_date` is the event date | **YES** — polling can record first appearance | **WEAK / prospective-only** |
| **ClinicalTrials.gov v2** | **PARTIAL** — first-post **date** recoverable (`ACTUAL`/`ESTIMATED`); historical *content* state not recoverable | **YES** — polling detects updates | **MEDIUM** |
| **SEC EDGAR** | **YES** — `acceptanceDateTime` is a genuine public instant, immutable archive, amendments as new accessions | **YES** — and useful for amendment detection | **STRONG** |

**One-line verdict:** the database's missing "public time" is **recoverable for EDGAR**, **recoverable to date-granularity for CT.gov**, and **not recoverable retrospectively for openFDA** — for openFDA it can only be *observed prospectively* from now.

---

## 1. openFDA device 510(k) and PMA

**Sample:** 5 × 510(k) and 5 × PMA records with `decision_date` in 2024; 1 page each (`limit=5`); then one record per endpoint re-fetched twice by stable id.

### 1.1 Fields

| role | field | sample evidence |
|---|---|---|
| **Event date** | `decision_date` | 510(k) `K240778` 2024-12-13; PMA `P030011` 2024-11-25 |
| Second event field | `date_received` | `K221349` received 2022-05-09 → decided 2024-11-19 (**925 days**) |
| **First-public date** | **not present** | no `event_date_posted`/posting field in either endpoint |
| Dataset freshness | `meta.last_updated` | `2026-11-02` (dataset-level, not per record) |
| Identity | `k_number` / `pma_number` + `applicant` + `product_code` | `K240778`, `P030011`, `N16895` |

**Received→decision lag (n=10):** min 10 d · median 146 d · max 925 d. This is *intake* latency, not publication latency.

**[FACT] There is no public-availability date in the device endpoints.** `decision_date` answers "when did FDA decide", `date_received` answers "when did the submission arrive". Neither answers "when could a researcher have seen it". openFDA exposes only a dataset-level `meta.last_updated`; no per-record posting date and no version history.

**[FACT] Identity signals are free-text and not stable:** `applicant` appears as both `Medtronic, Inc.` and `Medtronic Cardiac Rhythm Disease Management` in the same sample; PMA ids mix `P######`, `N#####` (`N16895`) and supplements; no registrant/company id is provided in these endpoints.

### 1.2 Re-fetchability and revision exposure

| test | result |
|---|---|
| Re-fetch by `k_number=K240778` ×2 | HTTP 200 both times, **identical sha256 `78e18c24544a…`** (3,167 B) |
| Re-fetch by `pma_number=P030011` ×2 | HTTP 200 both times, **identical sha256 `b26865715cb9…`** |
| Absence probe (`k_number=K231234`, not in DB) | HTTP **404**, deterministic body hash — absence checks are reliable |
| Revision/version endpoint | **none** — openFDA offers no per-record history or change feed |
| Record-change exposure | **unknown** — a changed record would return a new hash, but there is no API to enumerate changes; only the dataset-wide `last_updated` moves |

**[INFERENCE]** Storing `(url, k_number, sha256, fetched_at)` is enough to detect *that* a record changed between our observations, but not *what* it was before our first observation. openFDA cannot provide an as-of reconstruction.

### 1.3 Licence / storage

**[FACT]** openFDA `meta.terms` = `https://open.fda.gov/terms/`; openFDA data is public domain / CC0 1.0 (documented in the response metadata and in the REFOUNDATION-001 licence audit). Raw storage is permitted; we stored **only normalized sample fields + response hashes**, not bulk data.

---

## 2. ClinicalTrials.gov v2

**Sample:** 1 page, `pageSize=5`, `sort=LastUpdatePostDate:desc`; one study re-fetched twice; three candidate version-history endpoints probed.

### 2.1 Fields

| role | field | sample evidence |
|---|---|---|
| **Event date** | `statusModule.startDateStruct.date` | `NCT07578363` start 2026-09-27 |
| **First-public date** | `statusModule.studyFirstPostDateStruct.date` + **`.type`** | `NCT03712605` first posted 2018-10-19, type `ACTUAL` |
| Submission (pre-public) | `studyFirstSubmitDate`, `studyFirstSubmitQcDate` | `NCT07672483`: submit/QC 2026-06-26 → posted **2026-06-29** (+3 d) |
| Last public update | `lastUpdatePostDateStruct.date`, `lastUpdateSubmitDate` | `NCT07672483` last update 2026-11-12 (+136 d after first post; max in sample **+2,946 d**) |
| Identity | `nctId` (stable) + `leadSponsor.name` / `.class` | sponsor is display text |

**Submit→post lag (n=5):** 2, 3, 5, 5, 6 days. **Post→last-update:** 71, 136, 185, 703, 2,946 days.

**[FACT] The first-public date is recoverable, but only at date granularity and only with its type:** `studyFirstPostDateStruct.type` is `ACTUAL` or `ESTIMATED`. An `ESTIMATED` first-post date is the registry's *expected* posting date and **must not be labelled observed**. All 5 sampled records were `ACTUAL`; the `ESTIMATED` branch is schema-evidenced, not sampled.

**[FACT] `studyFirstSubmitDate` is a lower bound, not a public time:** the record exists internally from submission/QC, but becomes public at first post. Using submission date would overstate availability.

### 2.2 Re-fetchability and revision exposure

| test | result |
|---|---|
| Re-fetch same study ×2 | HTTP 200 both, **identical sha256 `5def6e895350…`** (20,070 B) |
| `GET /api/v2/studies/{NCT}/history` | **404** (0 B) |
| `GET /api/v2/studies/{NCT}/versions` | **404** (0 B) |
| `GET /api/v2/studies/{NCT}?history=true` | **400** (30 B) |
| Machine-readable prior version | **none exposed by the v2 API** |

**[INFERENCE]** The current record + `lastUpdatePostDate` prove *that* a record changed, but the pre-change content is not retrievable from the API. Retrospective "what did this trial record say on date D" is **not answerable** from the public API; only "was it first posted by D" and "when was it last updated" are.

### 2.3 Licence / storage

**[FACT]** ClinicalTrials.gov data is publicly available for use and not subject to US copyright restrictions (public domain). Raw storage permitted; we stored normalized fields + hashes only.

---

## 3. SEC EDGAR

**Sample:** one issuer (`Medtronic plc`, CIK 0001613103), 5 most-recent 8-K/8-K/A filings from `data.sec.gov/submissions`; for each, the filing `index.json` and the primary document fetched, then the primary document re-fetched to test immutability. `User-Agent` carries a real contact; requests spaced ≥0.4 s.

### 3.1 Fields

| role | field | sample evidence |
|---|---|---|
| **Event date** | `reportDate` | 8-K `0001628280-26-066291`: report 2026-10-15 |
| **First-public instant** | **`acceptanceDateTime`** | same filing: **2026-10-19T20:23:27.000Z** |
| Calendar date | `filingDate` (ET day) | 2026-10-19 |
| Stable id | `accessionNumber` | `0001628280-26-066291` |
| Document identity | `primaryDocument` | `mdt-20261015.htm` |
| Identity | `cik`, `name`, `tickers`, `sic` | CIK `0001613103`, `Medtronic plc`, `MDT`, SIC 3845; **`lei` null in this response** |

**[FACT] `acceptanceDateTime` is a genuine public timestamp**, corroborated independently by the HTTP `Last-Modified` of the archived primary document, which trails acceptance by **21–75 s** (5/5 filings: 25, 25, 25, 21, 75 s). That agreement also indicates the `Z` suffix is UTC (a 4–5 h ET offset would have shown a multi-hour delta).

**Report→acceptance lag (n=5):** 0, 0, 0, 0, 4 days. Filing and acceptance are same-day in all sampled cases.

### 3.2 Re-fetchability and revision exposure

| test | result |
|---|---|
| Filing `index.json` re-fetch | HTTP 200, deterministic |
| Primary document re-fetch | HTTP 200, **byte-identical** for all 5 filings (`e988da97…`, `75ebcf51…`, `a03ed94f…`, `2cc249ac…`, `810577c6…`) |
| Amendments | **separate filings** with form `8-K/A` and their own accession + acceptance time; **53** amendment forms in the last 1,000 filings of this issuer |
| In-place edit of an accession | **not observed** — archives are immutable; corrections arrive as new accessions |

**[INFERENCE]** EDGAR is the only one of the three sources that supports **true as-of reconstruction**: "public on date D" ⇔ `acceptanceDateTime ≤ D`. Revisions are detectable because each amendment is a distinct accession; the original remains retrievable, so both versions exist.

### 3.3 Licence / storage

**[FACT]** EDGAR filings are public records; SEC fair-access policy requires a real `User-Agent` and ≤10 req/s (we used ~2 req/s). Small-sample storage of filing metadata and document hashes is permitted; we stored index metadata + hashes (not the 103 KB HTML bodies) to keep the repository small.

---

## 4. Per-source table (requested summary)

| Source | Official event date | Source first-public date/time | Our collection time (separate) | Revision exposure | Re-fetch (HTTP + hash) | Licence / raw storage | Identity signals |
|---|---|---|---|---|---|---|---|
| **openFDA 510(k)/PMA** | `decision_date` (+ `date_received`) | **UNKNOWN — not exposed** (only dataset `meta.last_updated`) | 2026-11-12T18:45:10Z | **none** per record; no version API | 200; identical `78e18c24…` (K) / `b2686571…` (PMA); 404 deterministic | US public domain / CC0; raw OK (stored normalized only) | `k_number`/`pma_number` (mixed P/N/supplement), free-text `applicant`, `product_code` |
| **ClinicalTrials.gov v2** | `startDateStruct.date` | `studyFirstPostDateStruct.date` + `.type ACTUAL/ESTIMATED` | 2026-11-12T18:45:22Z | last-update date only; **no version endpoint** (404/400) | 200; identical `5def6e89…` | US public domain; raw OK (stored normalized only) | `nctId` (stable) + `leadSponsor.name` (display text) |
| **SEC EDGAR** | `reportDate` | **`acceptanceDateTime`** (UTC instant; `Last-Modified` +21–75 s) | 2026-11-12T18:45:27Z | amendments = separate `8-K/A` accessions (53/1,000); originals immutable | 200; identical hashes 5/5 | public filings; UA + ≤10 req/s; raw OK (stored metadata + hashes) | `cik` (stable), `name`, `tickers`, `sic`; `lei` absent here |

---

## 5. RETROSPECTIVE PUBLIC AVAILABILITY — what could have been public on date D

> This section uses **only source-provided publication fields**. It never uses our collection time and never uses `event_date` as a proxy for publication.

| Source | Reconstructable statement | Basis | Archive / revision limitations |
|---|---|---|---|
| **openFDA** | **Not reconstructable** | no public-posting field exists | only `decision_date` (event) and dataset `meta.last_updated` (2026-11-02). Any historical "public on D" claim for openFDA is **UNVERIFIABLE** from this source |
| **ClinicalTrials.gov** | "First publicly posted by D" **iff** `studyFirstPostDateStruct.date ≤ D` **and** `.type = ACTUAL` | `studyFirstPostDateStruct` (+ submit/QC dates as lower bound) | date granularity only (no time); **content as-of D not recoverable** (no version API); `ESTIMATED` records must be excluded/marked `unverifiable` |
| **SEC EDGAR** | "Public by instant T" **iff** `acceptanceDateTime ≤ T`; content = the archived document hash | `acceptanceDateTime` + accession + document hash | no in-place revisions; amendments are separate accessions, so both versions remain; timezone basis is `Z` (UTC) corroborated by `Last-Modified` |

**Retrospective verdict:** EDGAR **PASS** (true instant + immutable artefact); CT.gov **PARTIAL** (publication date recoverable at day granularity, evidence state not); openFDA **FAIL / UNVERIFIABLE** (no publication timestamp exists in the API — the shipped DB's `published_at = decision_date` is exactly the promotion E3/E3i warned about).

---

## 6. PROSPECTIVE OBSERVATION — from now, recorded separately

> Observation begins at the first fetch performed by this experiment. These timestamps are **collection times**, stored apart from every publication field. There is no earlier observation in this system, so the series is not back-filled.

| Source | First observation (UTC) | Records observed | What we can record going forward |
|---|---|---:|---|
| openFDA | **2026-11-12T18:45:10.695790+00:00** | 6 successful record fetches | first-seen timestamp per `k_number`/`pma_number`, response `sha256`, dataset `meta.last_updated`; later hash change ⇒ record changed (no history) |
| ClinicalTrials.gov | **2026-11-12T18:45:22.314078+00:00** | 3 | first-seen per `nctId`, `sha256`, `lastUpdatePostDate`; poll interval defines update-detection resolution |
| SEC EDGAR | **2026-11-12T18:45:27.189879+00:00** | 16 | first-seen per accession + `acceptanceDateTime` (so observation is *corroborated* by a source timestamp, not replaced by it); new accessions = revisions |

**Prospective verdict:** all three sources support a prospective observation store. For **openFDA this is the only route to a public-availability timestamp** — the historical one does not exist. For CT.gov it adds update detection. For EDGAR it is supplementary (retrospective already gives a true public instant).

**Hard separation is preserved:** `prospective.json` contains only observation metadata; `retrospective.json` contains only source-derived publication fields. No field in either file was populated from the other.

---

## 7. What this implies for E1b full recovery

| Source | Feasible recovery | Engineering needed | Fatal risk if mishandled |
|---|---|---|---|
| **EDGAR** | **High** — per-filing public instant (`acceptanceDateTime`), immutable document hash, amendment graph | submissions index per CIK → accession → index.json + primary doc hash; incremental by accession | using `filingDate` (ET day) instead of acceptance loses intraday ordering; ignoring 8-K/A loses revisions |
| **CT.gov** | **Medium** — first-post date with ACTUAL filter; update dates; no version history | v2 API paging + per-NCT snapshots; poll to accumulate versions we cannot retrieve retroactively | treating `ESTIMATED` as observed; treating `submitDate` as public; claiming as-of content |
| **openFDA** | **Low retrospectively / Medium prospectively** | poll the endpoints; store first-seen + hash; do not claim historical public time | promoting `decision_date` to `published_at` (the defect already in the legacy DB) |

**Bottom line for E1b:** full historical point-in-time recovery is **not uniform**. Build EDGAR first (it can carry a true public timestamp today), add CT.gov with the `ACTUAL` guard and explicit "date-only / content-not-recoverable" limits, and treat openFDA as **prospective-only** — its historical public availability is `UNKNOWN`, not estimated.

---

## 8. Evidence inventory and reproduction

| File | Content |
|---|---|
| `_evidence/e1b/collection.jsonl` | 28 request records: url, purpose, HTTP status, bytes, `sha256`, `fetched_at_utc`, response headers (`Date`, `Last-Modified`, `ETag`) |
| `_evidence/e1b/retrospective.json` | source-derived publication fields + samples (no collection time) |
| `_evidence/e1b/prospective.json` | first-observation timestamps + observation basis (no publication fields) |
| `_evidence/e1b/findings.json` | machine-readable derived findings (lags, refetch determinism, revision exposure, identity) |
| `_evidence/e1b/summary.json` | request counts, refetch results, history-probe results, entity |

```powershell
cd <path-to-worktree>
python research\e1b\collect_e1b.py      # network: 28 requests, 1 page/source
python research\e1b\derive_findings.py  # offline derivation
```

**Requests:** 28 total (25×200, 2×404 version probes, 1×400 version probe). No bulk download, no pagination beyond page 1, no authentication, no personal data stored. Only normalized sample fields and hashes are committed — not raw bulk payloads.

---

## 9. Unknowns and explicit non-claims

- **openFDA publication lag** is `UNKNOWN`; anything claiming otherwise would be fabricated. Whether FDA posts clearances same-day is *not* established here.
- **CT.gov `ESTIMATED` first-post behaviour** is schema-evidenced only (0/5 sampled). Full recovery must filter `type='ACTUAL'` or label `unverifiable`.
- **EDGAR timezone authority**: `Z` + `Last-Modified` agreement indicate UTC; the SEC's definitive timezone documentation was not re-read in this experiment.
- **Sample size** (5/source, 1 issuer, 1 page) establishes field semantics and mechanism, not population rates.
- **No identity resolution** was performed: `applicant` free text (openFDA) and `leadSponsor.name` (CT.gov) are *recorded*, not resolved to companies; CIK is the only stable entity key observed.

---

## 10. Repository state

Committed on `research/e1b-source-recovery` only (no push): `research/e1b/collect_e1b.py`, `research/e1b/derive_findings.py`, `docs/refoundation/phase2/E1B_SOURCE_RECOVERY.md`, `docs/refoundation/phase2/_evidence/e1b/*`. No other branch, no `main`, no push.

**Labels:** `[FACT]` = measured in this experiment; `[INFERENCE]` = reasoned from those measurements; anything not measured is marked `UNKNOWN`/`UNVERIFIABLE`/`not_applicable` rather than estimated.
