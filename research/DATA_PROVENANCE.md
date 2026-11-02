# Data provenance, timing semantics and known defects

Rule: a source is only usable for retrospective forecasting if we know **when a
researcher could have known a fact**, not merely when the fact was true. Where that
is unknown, the source is marked not point-in-time usable and is excluded from
predictive-gain claims.

## 1. Timing vocabulary (do not conflate)

| Term | Meaning |
|---|---|
| **Event time** (`event_date`) | when the underlying real-world event happened (e.g. FDA decision date) |
| **Publication time** (`published_at`) | when the source published it |
| **First seen** (`first_seen_at`) | when *our* collector first retrieved it |
| **Available at** (`available_at`) | our conservative estimate of the earliest knowledge time usable at a cutoff |
| **Ingestion time** (`fetched_at` / `retrieved_at`) | when we wrote the row |
| **Knowledge cutoff** (`τ`) | the prediction time; every feature must satisfy `available_at <= τ` |

A backfill knows everything today. Using `available_at = event_date + modelled lag`
is an *assumption about publication*, and it is logged as such.

## 2. Sources in the research lane (`data/research.sqlite`)

| Source | Rows | Event time | Knowledge-time rule | Lag | PIT verdict |
|---|---:|---|---|---|---|
| openFDA 510(k) bulk | 31,219 | `decision_date` | `decision_date + 14 days`, `timestamp_quality='estimated'` | 14 d (assumed) | usable with documented assumption |
| openFDA PMA bulk | 23,871 | `decision_date` | same rule | 14 d | usable, same assumption |
| SEC EDGAR Company Facts (XBRL) | 43,420 facts / 32 companies | `period_end` | `filed` (amendment-aware, latest filed row per period) | exact | usable; consolidated only |
| USAspending awards | 3,453 | performance period | retrieval time only | unknown | **`pit_usable=0` — excluded from predictive gain** |
| Market bars (Yahoo adjusted) | 95,725 | trading date | bar close date; vendor publication time unknown | unknown (day-level) | usable as day-level signal only |
| OpenAlex publication counts | 616 rows (51 companies, 150,087 works) | calendar year | complete years ≤ year(τ)−1 with 15-Feb lag | ~6.5 weeks | usable but alias matching is noisy |
| USPTO patents | 0 | — | adapter implemented, requires API key | — | **NOT COLLECTED — declared gap** |
| Public hiring / job postings | 0 | — | not implemented | — | **NOT COLLECTED — declared gap** |

`financial_facts` are company-consolidated. Company Facts does not reliably expose
the segment dimensions needed for product-line revenue, so no code converts total
company revenue into medical-device revenue. Philips and Smith & Nephew file IFRS and
have zero US-GAAP facts: their financial features are null, never fabricated.

## 3. Sources in the legacy full-history DB (`medradar/data/medradar.sqlite`, untouched)

375,378 events, 1966-12-14 .. 2026-10-30, 89 companies, 60 tracks.

| Source | Kind | Events | Notes |
|---|---|---:|---|
| openFDA device 510(k) | `510k` | 176,466 | full history |
| openFDA device recall | `device_recall` | 59,646 | |
| openFDA device PMA | `pma` | 57,372 | |
| ClinicalTrials.gov v2 | `trial` | 55,592 | sponsor-matched |
| SEC EDGAR 8-K corpus | `8k_catalyst` | 20,976 | classified catalyst types |
| openFDA drug Drugs@FDA | `drug_approval` | 5,326 | |

Linkage coverage in this DB: `company_key` 35.2%, `track_id` 52.4%, both 23.5%
(88,327 events, 1,192 distinct company×track pairs). `published_at` equals
`event_date` for every row, i.e. **no publication lag is modelled here** — this DB is
deliberately not used for retrospective forecasting in cycle 2.

## 4. Known defects that constrain inference

1. **510(k) linkage is the binding constraint.** In the research lane only 16.9% of
   510(k) rows (5,287/31,219) link to a curated company, and 510(k) is the main
   device-activity signal. Most unlinked rows are unrelated firms, but **284 rows do
   name a curated company and are still unlinked**.
2. **Two mandated focus companies are absent.** All 90 Shenzhen Mindray and all 25
   Dräger records in the lane are unlinked because those firms are not in the
   51-company roster at all. Other roster recall gaps: GE HealthCare 41, Envista 28,
   Teleflex 23, BD 18, Siemens Healthineers 14, Integra 14, Baxter 7, Alcon 7,
   Zimmer Biomet 5, Terumo 4, Merit 3, Edwards 3, Dentsply 1, Ambu 1.
3. **No resolution evidence is stored on events.** `company_key` on `events` carries
   no confidence, matched alias or rule/model version, so a linkage error cannot be
   audited from the row. (`company_identifiers` does carry evidence and confidence for
   SEC CIK links; the regulatory applicant links do not.)
4. **Entity granularity is inconsistent.** Curated parents sometimes fold in
   subsidiaries (Medtronic absorbs Covidien) and sometimes do not; the panel is
   therefore not a clean legal-entity panel. This is the subject of E12.
5. **Left-censoring.** The bulk window starts 2016-11-01. "Dormant" means "no event
   observed inside the window", never "provably inactive". Pre-2016 activity is
   unobservable, and the 120-month dormancy cap is a top-code, not a measurement.
6. **The track taxonomy is applied to history unversioned.** Tracks reflect the
   current curated product-code mapping, so "tracks observed by τ" uses present-day
   knowledge. This is a semantic-leakage channel that an as-of SQL replay cannot
   detect.
7. **Bulk and paged ingest lanes are semantically different.** The bulk lane writes
   `decision_date + 14d` with `INSERT OR REPLACE`; the paged lane writes
   `published_at or event_date`. Mixing them inside one backtest silently changes
   `available_at`. Only one lane may be used per experiment.
8. **The lane is not an industry census.** 51 curated companies are not a random
   sample of the industry. 322 observed company-track pairs against a 51×38=1,938
   cross product means most candidates were never observed — a left-censoring artefact
   that a larger entity universe partially addresses.
9. **The canonical forecast registry's knowledge clock is backfill time**, not
   historical publication time; and the 25 registered forecast records are nowcasts
   whose windows are already open, so they must never be merged into a pure-future
   headline cohort.

## 5. Access and licensing

Sources are public-domain US government data (openFDA, SEC EDGAR, USAspending,
ClinicalTrials.gov), public web publication metadata (OpenAlex, CC0) and
vendor-derived price series (Yahoo adjusted closes, used as a weak market signal
only). Redistribution of raw bulk downloads and the SQLite stores is not committed;
only small aggregates, config and reproduction commands are. No circumvention of
access controls, and no scraping behind authentication.
