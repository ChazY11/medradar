# S-029 Temporal Provenance Audit — what each "time" in our data actually is

**TEMPORAL_PROVENANCE** · study `relation_network_s029` · branch `research/s029-evidence-based-relations`
**Auditor role**: Temporal Provenance Auditor (independent of modelling and of hypothesis testing)
**Machine-readable result**: [`artifacts/clock_audit.json`](artifacts/clock_audit.json)
**Reproduction script**: [`code/s029_clock_audit.py`](code/s029_clock_audit.py)
**Stage**: 1 (live-source clock audit + observation-ledger audit) and 2 (claim-level completeness over
**20563** claims in `data/claims.jsonl`) both complete — see §4–§6.

> Every number in this document is produced by `code/s029_clock_audit.py` and stored in
> `artifacts/clock_audit.json`. `python code/s029_clock_audit.py --verify-report` re-reads this
> file and fails if any number here cannot be found in the JSON.

---

## 0. Scope, method, and what was actually spent

### 0.1 The question this audit answers

S-029 wants a **temporal** relation network: claims about who was related to whom, *and when that
became knowable*. That second half is a data question, not a modelling question. This audit
measures, for every live source, which of the four clocks the source actually supplies, at what
precision, and where the source supplies none. It then proves — by running the probes, not by
asserting — that **no historical point-in-time (PIT) state can be recovered** from these sources.

### 0.2 Method and request budget

* Live probes of four sources + a read-only audit of the MedRadar observation ledger.
* Hard budget enforced *in code*: ≤60 calls per source, ≤250 total, 0.4 s minimum spacing.
* Every call is appended to `request_ledger[]` in the JSON with URL, HTTP status, retrieval UTC
  timestamp, response `sha256`, byte length, elapsed ms, and a note.
* The ledger was opened **read-only** (`sqlite3.connect("file:...?mode=ro", uri=True)`); its
  `sha256` was computed **before and after** the audit and is identical — see §2.5.

| Budget item | Measured | Cap |
|---|---|---|
| Total recorded calls | **69** | 250 |
| Calls per audit pass | **23** (passes: 3) | — |
| ClinicalTrials.gov | **39** | 60 |
| Europe PMC | **15** | 60 |
| OpenAlex | **9** | 60 (plan guidance ≤8; see note) |
| Crossref | **6** | 60 |
| Minimum inter-request delay | **0.4** s | 0.4 s |

Disclosure, because an audit that hides its own waste is worthless: three pass-sets were made
(69 = 23 × 3). Pass 1 hit a harness bug after the calls had been made, pass 2 succeeded, pass 3
re-ran after the date-field enumerator was corrected. **Every call of every pass is in the
ledger** — none were deleted to make the numbers look tidy. The consequence is that OpenAlex
received **9** calls where the study guidance asked for ≤8; the analytical plan itself used 3
(one per firm stratum). No further OpenAlex calls were made after that.

### 0.3 What was sampled

| Source | Sampled | Frame / stratification measured |
|---|---|---|
| ClinicalTrials.gov API v2 | **128** studies | sponsor strata: Medtronic (40 of **1675**), GE HealthCare (40 of **343**), Philips (40 of **376**), Dräger (2 of **2**), Mindray (6 of **6**) |
| Europe PMC REST (`resultType=core`) | **100** papers | affiliation strata, 20 each: Medtronic (**3556** hits), GE HealthCare (**5107**), Philips (**8272**), Dräger (**36**), Mindray (**286**) |
| OpenAlex | **24** works | 12 Medtronic / 6 Philips / 6 GE HealthCare (frame counts 9666 / 50914 / 9767) |
| Crossref | **30** works | affiliation queries, 15 Medtronic (2510) + 15 Philips (9619) |
| Observation ledger | **400** observations | full table, read-only, plus all 34 `sync_run` rows |

The Dräger and Mindray ClinicalTrials.gov strata are censused, not sampled — the frame *is* 2 and
6 records. Their percentages are therefore exact for the frame but too small to support any
inference about Dräger/Mindray practice in general. All headline rates below are reported next to
their n for that reason.

---

## 1. The four clocks, and the only honest labels

Four clocks are **never** interchangeable. The rule this audit enforces:

| # | Clock | Meaning | Where it can legitimately come from |
|---|---|---|---|
| 1 | `event_at` | when the underlying event actually happened | trial `startDate`, paper publication date, FDA decision date |
| 2 | `published_at` | when the source made the record public | CT.gov `studyFirstPostDate`; EPMC `firstIndexDate`; Crossref `published-online` |
| 3 | `first_seen_at` | when **MedRadar** actually observed it — real wall clock | only `observatory.observation.first_seen_at` |
| 4 | `valid_from` / `valid_to` | the period during which a relation is supported by evidence | **no source supplies it** — it must be derived and declared |

Every relation and every date in S-029 must carry exactly one of these five time-basis labels:

| Label | When it applies |
|---|---|
| `HISTORICAL_PROXY` | the timestamp is reconstructed after the fact to stand in for "what was knowable then"; it is a simulation input, never evidence of contemporaneous knowledge |
| `SOURCE_PUBLISHED` | the timestamp is the source's own "this became public" stamp (registry post date, index date, online-publication date) |
| `ACTUAL_OBSERVATION` | a real MedRadar collection event observed the record; requires a `sync_run` row |
| `DATE_ONLY` | qualifier: the value is date-precision, so no sub-day claim may be built on it |
| `TIME_UNKNOWN` | no usable clock; the field must not be used as any of the four |

**The manufacture prohibition (binding on the whole study).**
> No historical point-in-time observation can be manufactured. A `first_seen_at` that the
> observation ledger does not contain does not exist. Writing `published_at` into a
> `first_seen_at` column, or back-dating an observation to "when we would have seen it", converts
> a reconstruction into a false claim of contemporaneous knowledge. Where no observation exists,
> the only truthful labels are `SOURCE_PUBLISHED`, `HISTORICAL_PROXY`, `DATE_ONLY`, or
> `TIME_UNKNOWN` — never `ACTUAL_OBSERVATION`.

---

## 2. Source-by-source empirical clock audit

### 2.1 ClinicalTrials.gov API v2

**Date fields present, enumerated from one full record** (`NCT06678841`, HTTP 200). Nine
date-bearing leaf fields exist, all under `protocolSection.statusModule`:

`startDateStruct.date`, `primaryCompletionDateStruct.date`, `completionDateStruct.date`,
`studyFirstPostDateStruct.date`, `lastUpdatePostDateStruct.date`,
`studyFirstSubmitDate`, `studyFirstSubmitQcDate`, `lastUpdateSubmitDate`, `statusVerifiedDate`.

Note what is **absent**: there is no `resultsFirstPostDateStruct` in this record (see coverage
below) and no field anywhere that says when the registry *state* changed during a prior period.

**Precision and coverage, 128 studies:**

| Field | Present | Missing | Month-only (`YYYY-MM`) | Day (`YYYY-MM-DD`) | Month share of present |
|---|---|---|---|---|---|
| `startDateStruct` | 128 | 0 (0.0% missing) | 57 | 71 | **44.53%** |
| `studyFirstPostDateStruct` | 128 | 0 (0.0%) | 0 | 128 | **0.0%** |
| `lastUpdatePostDateStruct` | 128 | 0 (0.0%) | 0 | 128 | **0.0%** |
| `primaryCompletionDateStruct` | 127 | 1 (0.78%) | 58 | 69 | **45.67%** |
| `resultsFirstPostDateStruct` | 42 | 86 (**67.19%**) | 0 | 42 | **0.0%** |

Reading of the precision table, which matters for every downstream claim:

* The two clocks we actually want from CT.gov are **asymmetric**. `published_at`
  (`studyFirstPostDateStruct`) is **100% day-precision**: perfect. `event_at`
  (`startDateStruct`) is **44.53% month-only**: for those trials the start date is a month, so any
  claim of the form "started before/after X" must be stated with month granularity.
* `primaryCompletionDateStruct` is also ~46% month-only **and** carries a type flag: 96 records
  say `ACTUAL`, 31 say `ESTIMATED`. An `ESTIMATED` completion date is a plan, not an event.
*`resultsFirstPostDateStruct` is unusable as a general clock: **67.19% missing** in this sample
  because most trials post no results.
* Type flags are themselves incomplete: `startDateStruct` has a type on 66 records as `ACTUAL` and
  11 as `ESTIMATED`; `studyFirstPostDateStruct` splits 69 / 59, `lastUpdatePostDateStruct` 102 / 26,
  `primaryCompletionDateStruct` 96 / 31, `resultsFirstPostDateStruct` 29 / 13. Where the type is
  `ESTIMATED` the field is not evidence that anything happened.

**Per-firm month-only share of `startDateStruct`** (the stratified detail):

| Firm | n | month-only | day | month share |
|---|---|---|---|---|
| Medtronic | 40 | 23 | 17 | **57.5%** |
| GE HealthCare | 40 | 22 | 18 | **55.0%** |
| Philips | 40 | 10 | 30 | **25.0%** |
| Mindray | 6 | 0 | 6 | **0.0%** |
| Dräger | 2 | 2 | 0 | **100.0%** |

The precision defect is **not uniform across firms**: Medtronic and GE HealthCare trial start dates
are month-only more than half the time, Philips a quarter, while the (small) Mindray stratum is
fully day-precision. A pooled "trial start date" column will therefore be *less* accurate for the
two largest sponsors — exactly the firms whose relations S-029 cares about most.

**`event_at` and `published_at` are independent clocks, measured:** comparing
`studyFirstPostDate − startDate` over 128 pairs, the distribution is min -1168 d, p25 -83 d,
median 0.5 d, p75 46 d, max 5010 d. **64 of 128 trials (50.0%) were posted before their recorded
start date** (pre-registration), and 64 were posted after. Consequence: for half the sample the
"publication" precedes the "event"; for the other half it follows it by up to 5010 days. Any
procedure that treats these as one time axis is wrong by years.

**Can CT.gov return a historical as-of state? No — tested, not assumed.** Using the sampled study
with the largest registry-history gap (`NCT00617175`: first posted **2008-02-15**, last updated
**2025-07-02**, a **6347**-day gap, current status `COMPLETED`), three kinds of probe were run:

| Probe | URL pattern | HTTP | Result |
|---|---|---|---|
| current state (baseline) | `/api/v2/studies/NCT00617175` | **200** | one record, current state only |
| `asOf` parameter | `...&asOf=2019-06-01` | **400** | rejected: no such parameter |
| `date` parameter | `...&date=2019-06-01` | **400** | rejected |
| `studyVersion` parameter | `...&studyVersion=1` | **400** | rejected |
| history endpoint | `/api/v2/studies/NCT00617175/history` | **404** | does not exist |
| versions endpoint | `/api/v2/studies/NCT00617175/versions` | **404** | does not exist |
| only time-indexed query | `filter.advanced=AREA[LastUpdatePostDate]RANGE[2019-01-01,2019-12-31]` | **200** | **31734** studies, but each is returned in its *current* state |

The last row is the decisive one. The only date filter the API offers indexes
`lastUpdatePostDate` — a stamp on the *current* record. The three records returned first carry
`lastUpdatePostDate` **2019-01-22** and `studyFirstPostDate` **2010-04-05**; what the API gives is
"a record whose last edit fell in 2019, as it looks today", **not** "the record as it looked in
2019". No payload contained any version or history block.

> **Finding §2.1**: CT.gov supplies `event_at` (44.53% month-only) and `published_at` (day
> precision) for the current state only. **`first_seen_at` is absent and unrecoverable.**
> **`valid_from`/`valid_to` are absent.** Historical registry state cannot be retrieved: the only
> route into the past is `lastUpdatePostDate`, which is not a pointer to a retrievable past state.

### 2.2 Europe PMC REST (`resultType=core`)

**Date fields present** (enumerated across 100 records): `firstPublicationDate`,
`firstIndexDate`, `dateOfCreation`, `dateOfRevision`, `electronicPublicationDate`,
`journalInfo.printPublicationDate`, `journalInfo.dateOfPublication`, `fullTextReceivedDate`,
`dateOfCompletion`. Nine date-bearing fields — but only three of them are clocks.

**Presence and precision:**

| Field | Present | Missing | Precision |
|---|---|---|---|
| `firstPublicationDate` | 100 | 0 (0.0%) | 100% day |
| `firstIndexDate` | 100 | 0 (0.0%) | 100% day |
| `dateOfCreation` | 100 | 0 (0.0%) | 100% day |
| `dateOfRevision` | 100 | 0 (0.0%) | 100% day |
| `electronicPublicationDate` | 75 | 25 (**25.0%**) | 75 day |
| `journalInfo.printPublicationDate` | 100 | 0 (0.0%) | 100% day |
| `journalInfo.dateOfPublication` | 100 | 0 (0.0%) | 13 year-only, 87 free-text month form |

`journalInfo.dateOfPublication` is *present but not machine-parseable* — 13 values are a bare year
and 87 are month-name strings. A pipeline that silently drops "unparseable" dates will lose 87% of
this field; a pipeline that parses it as a date will invent a day.

**`firstIndexDate − firstPublicationDate`, the publication→index lag (100 pairs):**
min -121 d, p25 1 d, **median 4.0 d**, p75 19 d, max 1245 d. Buckets: negative **7**, same day
**4**, 1 d **25**, 2–7 d **22**, 8–30 d **29**, 31–365 d **9**, >365 d **4**.

Per-firm medians: Medtronic **1.5** d, GE HealthCare **2.0** d, Philips **1.0** d, Dräger **21.5** d,
Mindray **12.0** d.

Two things follow. First, `firstIndexDate` (index availability) and `firstPublicationDate`
(journal publication) are **different events separated by a median of 4.0 days and a tail of up to
1245 days** — using either as the other is a real, measurable error. Second, **7 of 100 are
negative**, i.e. the record was indexed *before* its "publication date". Inspecting those:
`firstPublicationDate` equals `journalInfo.printPublicationDate` in each case, so the nominal
publication date is the **print issue date** while indexing followed earlier online availability
(e.g. -52 d, -40 d, -62 d, -10 d). The "publication date" is therefore sometimes an issue-date
artefact, not the day the paper became public.

**Metadata clocks are not science clocks:** `dateOfCreation − firstIndexDate` has median **-1.0**
d (76 negative) — the metadata record is created around indexing time. `dateOfRevision −
firstIndexDate` has median **35.5** d, p75 132 d, max 5289 d — the revision stamp moves forward
with every re-index and **preserves no history**. And `electronicPublicationDate` equals
`firstPublicationDate` in all **75** pairs where both exist (median 0, max 0), i.e. for these
records EPMC's "first publication" *is* the e-pub date; it is not an independent clock.

> **Finding §2.2**: EPMC supplies `event_at` (`firstPublicationDate`, day precision) and
> `published_at` as an index-availability proxy (`firstIndexDate`, day precision, measured median
> lag 4.0 d). It supplies **no `first_seen_at`**, **no `valid_from`**, and no as-of retrieval:
> `dateOfCreation`/`dateOfRevision` describe the metadata record's own maintenance, not a
> retrievable past state.

### 2.3 OpenAlex (tight shared budget)

**24 works**, `select=id,doi,publication_date,created_date,updated_date`. All three fields present
on 100% of records. `publication_date` is day precision (24/24); `created_date` and `updated_date`
are second-level datetimes (24/24).

| Comparison | min | p25 | median | p75 | max |
|---|---|---|---|---|---|
| `created_date − publication_date` | 8 d | 2598 d | **3567.5 d** | 4673 d | 24222 d |
| `updated_date − created_date` | 2976 d | 3781 d | **3781.0 d** | 3784 d | 3784 d |

The `created_date` column is **not** a publication clock and not an availability clock either. It
is a **bulk-ingest stamp**: for the legacy works in the sample, `created_date` is literally
`2016-06-24` across different papers Published in 2007, 2007 and 2012 alike (examples:
`10.1021/bm070313n` published 2007-06-19, `created_date` 2016-06-24, lag 3293 d;
`10.1109/tnsre.2012.2183617` published 2012-01-31, `created_date` 2016-06-24, lag 1606 d). Only
the recent record `10.1089/dia.2016.0421` (published 2017-01-30) has a plausible lag of 25 d.

`updated_date` is worse: `updated_date − created_date` spans only **2976**–**3784** d across all 24
works (p25 3781, median 3781.0, p75 3784) — a near-constant offset, which is the signature of a
**global refresh stamp** (values cluster on 2026-10-31 and 2026-11-03), not of per-record change
history.

> **Finding §2.3**: OpenAlex supplies `event_at` (`publication_date`, day precision) and **nothing
> else that is a legitimate clock**. `created_date` is a bulk-ingest timestamp with a measured
> median lag of 3567.5 days behind publication; `updated_date` is a refresh stamp whose
> entire 24-work spread is the 2976–3784 d range. Neither may be used as `published_at`,
> `first_seen_at`, or `valid_from`. OpenAlex cannot return a historical record state.

### 2.4 Crossref

**30 works** via affiliation queries. Crossref's date model is the most treacherous of the four
because it looks the most precise.

| Field | Present | Missing | Measured precision |
|---|---|---|---|
| `issued` | 30 | 0 (0.0%) | day **17**, month **12**, year **1** |
| `published-online` | 15 | 15 (**50.0%**) | day 14, month 1 |
| `published-print` | 27 | 3 (**10.0%**) | day 13, month 13, year 1 |
| `created` (deposit) | 30 | 0 (0.0%) | datetime, second |
| `deposited` | 30 | 0 (0.0%) | datetime, second |
| `indexed` | 30 | 0 (0.0%) | datetime, second |

`issued` — the field most pipelines treat as "the publication date" — is **day-precision on only
17 of 30 records**: 12 are month-only and 1 is year-only. **14 of 30 works carry a print date but no
`published-online`**, so for half the sample the earliest public date cannot be recovered from this
API at all.

**What `created` actually is, measured.** `created − issued`: min **-115** d, p25 0 d, median
**13.5** d, p75 1354 d, max **12598** d, with **6 of 30 negative**. Examples:
`10.37665/mexoota54470` has `issued` 2009-09 but `created` 2025-12-01 — a **5935**-day gap: the DOI
record was registered 16 years after the article was published. `10.1161/circulationaha.105.609420`
has `created` 7 days *before* `issued`. Meanwhile `deposited − created` runs from 0 to **6572** d
(median **1167.5**) because `deposited` is the *last* deposit and keeps moving.

`created` is therefore the moment **Crossref registered the DOI record** (the publisher's metadata
deposit). It is an infrastructure timestamp: not the scientific event, not the journal's
publication date, and certainly not an observation by MedRadar.

> **Finding §2.4**: Crossref supplies `event_at` (`issued`, mixed precision: only 17 of 30 at day
> level) and, when present, `published_at` via `published-online` (present on only 50.0% of the
> sample). `created` must be labelled `TIME_UNKNOWN`: measured to lag `issued` by a median of
> 13.5 d and by up to 12598 d. Crossref returns the latest deposit only; there is no as-of parameter.

### 2.5 The observation ledger — the only real observation in the project

Read-only audit of `D:\DEPPSKK\medradar\data\observatory\observatory.sqlite`
(**1945600** bytes, 13 tables, sha256
`3534b4c5cbd45f5d5974b8c18d4a21454e462a30c31e8271866e56cabd6d0e86`, schema `obs-ledger-v1`,
`meta.created_at` **2026-11-03T14:39:53+00:00**).

**Read-only proof (non-destructive).** Connection opened with URI `mode=ro`, then
`PRAGMA query_only=ON`; an attempted `CREATE TABLE` was **refused** (`OperationalError: attempt to
write a readonly database`). The file `sha256` **before** and **after** the audit is identical
(`file_unchanged = true`), as is its mtime (**2026-11-03T16:00:02Z**). Nothing was written.

**What the ledger contains:** 400 observations, 34 `sync_run` rows, 198 HTTP requests and 399 new
records across those runs, 142 sync checkpoints, 6 source failures.
**Its entire history covers one calendar day.**

| Metric | Measured |
|---|---|
| Observations | **400** |
| Distinct `first_seen_at` values | **4** |
| Distinct `first_seen_at` calendar days | **1** |
| `first_seen_at` range | 2026-11-03T14:39:53Z → 2026-11-03T14:49:51Z |
| `sync_run` rows / distinct dates | 34 / **1** (all 2026-11-03) |
| Observation coverage | **1** day |
| `observation_origin` | `LIVE` **400**, `BACKFILL` 0 |
| `backfill_reason` | null on all 400 |
| `observation_phase.method` | `reconstructed_from_run_history` **400** |
| `observation_phase.phase` | `INITIAL_DISCOVERY` **399**, `INCREMENTAL_DISCOVERY` 1 |
| `observation_status` / `current_change_state` | `ACTIVE` 400 / `NEW` 400 |
| `version_count` | all equal to 1 (400) |
| `observation_version` rows / distinct `captured_at` | 400 / **4** |

**How many rows carry a genuine `first_seen_at`?** Not "all 400 non-null" — that would be sloppy.
The tiers are computed row by row:

| Tier | Definition | Rows |
|---|---|---|
| `DIRECT_CAPTURE` | per-record timestamp written at capture time | **0** |
| `RUN_ANCHORED_RECONSTRUCTION` | `first_seen_at` equals its `sync_run.started_at` (±120 s) and `phase.method = reconstructed_from_run_history` | **400** |
| `RECONSTRUCTED_BACKFILL` | `observation_origin = BACKFILL` or a backfill reason present | **0** |
| `UNANCHORED` | `first_seen_at` not matching any run | **0** |

All **400** rows are therefore *run-anchored reconstructions*: a real collection demonstrably
happened (the `sync_run` row exists with a start timestamp), but the per-record timestamp was
assigned **after** the run from the run's start time. Resolution is the run start second. This is
honest evidence of a real observation; it is **not** an independently captured per-record stamp,
and the ledger says so itself in `observation_phase.method`.

**Prospective vs backfilled, measured (`first_seen_at − published_at`, 400 pairs):**
min 0 d, p25 19 d, **median 65 d**, p75 320 d, max **7613** d.
Buckets: same day **5**, 1 d **1**, 2–7 d **29**, 8–30 d **68**, 31–365 d **202**, >365 d **95**.

| Criterion | Rows | Share |
|---|---|---|
| lag ≤ 0 d | **5** | **1.25%** |
| **lag ≤ 1 d (genuinely prospective)** | **6** | **1.5%** |
| lag > 7 d (functionally a backfill) | **365** | **91.25%** |

Per source / record type:

| Source / type | n | median lag | max lag | prospective (≤1 d) | lag > 7 d |
|---|---|---|---|---|---|
| `ctgov/trial` | **157** | **683** d | 7613 d | **1** | **98.09%** |
| `europepmc/publication` | **237** | **45** d | 320 d | **4** | **87.76%** |
| `sec_edgar/sec_8k` | 4 | 27.5 d | 46 d | 0 | 75.0% |
| `sec_edgar/sec_10q` | 1 | 6 d | 6 d | 0 | 0.0% |
| `sec_edgar/sec_6k` | 1 | 0 d | 0 d | **1** | 0.0% |

**Precision of the ledger's own clocks:** `event_at` is `date` on **383** rows and `year` on
**17**; `published_at` is `date` on **394** and `datetime` on **6**; `source_updated_at` is `date`
on **394** and `unknown` on **6**. So even inside the ledger, **17 of 400 event dates are year-only**
and cannot support any sub-annual statement.

**Governance facts that bear on provenance:** `observation_mapping` has **401** rows for **400**
distinct `observation_id` (one duplicate); `entity_status` is `MAPPED` **102**, `PENDING_REVIEW`
**238**, `UNMAPPED` **61** — i.e. **most ledger records are still unreviewed**, and the S-029
relation layer must not treat them as settled. `source_failure` = 6 rows.

> **Finding §2.5**: the ledger is the **only** `ACTUAL_OBSERVATION` evidence in the project, and it
> is thin: **400** observations over **1** day, **0** direct captures, **6** prospective (lag ≤ 1 d,
> **1.5%**), **365** with lag > 7 d (**91.25%**). The `first_seen_at` values are honest but
> **reconstructed from run history**, not stamped per record.

### 2.6 Comparison with S-028: improved, unchanged, or worse?

The S-028 audit (`graph_early_signal_s028/RELATION_AND_TIME_EVIDENCE_AUDIT.md`, read-only) reported
the same observation ledger. Its values were re-measured here, not copied, and the frozen S-028
research input was independently re-checked read-only.

| Metric | S-028 reported | S-029 measured | Same? |
|---|---|---|---|
| Ledger observations | 400 | **400** | yes |
| `observation_origin = LIVE` | 400 | **400** | yes |
| `observation_origin = BACKFILL` | 0 | **0** | yes |
| Distinct `first_seen_at` values | 4 | **4** | yes |
| Distinct `first_seen_at` calendar days | 1 | **1** | yes |
| `sync_run` rows | 34 | **34** | yes |
| `phase.method = reconstructed_from_run_history` | 400 | **400** | yes |
| median lag (`first_seen_at − published_at`) | 65 d | **65** d | yes |
| min / max lag | 0 d / 7613 d | **0** d / **7613** d | yes |
| prospective (lag ≤ 1 d) | 6 | **6** | yes |
| prospective share | 1.5% | **1.5%** | yes |
| lag > 7 d | 365 | **365** | yes |
| lag > 7 d share | 91.25% | **91.25%** | yes |
| lag ≤ 0 d | 5 | **5** | yes |
| `version_count` = 1 | 400 | **400** | yes |
| `observation_mapping` rows | 401 | **401** | yes |
| `source_failure` rows | 6 | **6** | yes |
| frozen input events | 55090 | **55090** | yes |
| frozen distinct `first_seen_at` | 1 | **1** | yes |
| frozen `first_seen_at` value | 2026-11-01 | **2026-11-01** | yes |
| frozen `available_at − event_date` | 14 d | **14** d | yes |
| frozen `available_at = published_at` | 55090 | **55090** | yes |
| frozen lag > 365 d share | 89.92% | **89.92%** | yes |
| frozen rows with lag ≤ 1 d | 1 | **1** | yes |
| frozen `timestamp_quality = estimated` | 55090 | **55090** | yes |

**29 metrics compared, 0 changed.**

> **Verdict: `STAYED_THE_SAME`.** The situation did **not** improve and did not get worse. The
> ledger still contains a single day of collection history and the same **6** prospective
> observations (**1.5%**), because **no new collection cycle has run** since S-028 — `sync_run`
> still stops at 2026-11-03 and `source_state.last_new_records` is 0 for all three sources. S-029
> inherits S-028's clock deficit unchanged: the project still has **no historical PIT observation**
> and **6** genuinely prospective records in total.

### 2.7 The as-of question, answered once for all four sources

| Source | Test performed | Result | Historical state retrievable? |
|---|---|---|---|
| ClinicalTrials.gov | `asOf` / `date` / `studyVersion` params (HTTP 400 each), `/history` and `/versions` endpoints (404 each), `LastUpdatePostDate` range filter (200, current state) | rejected / absent / current-state only | **No** |
| Europe PMC | current-state search only; `dateOfCreation` / `dateOfRevision` describe the metadata record | no as-of parameter exists | **No** |
| OpenAlex | `created_date` (bulk-ingest) + `updated_date` (refresh stamp) | timestamps overwrite, no versioned query | **No** |
| Crossref | latest deposit per DOI; `created` immutable but infrastructure-only | no as-of parameter | **No** |
| Observation ledger | 1 day of runs, `NEW` change state on all 400 | the only true per-record observation, and it starts 2026-11-03 | **Only forward, from 2026-11-03** |

### 2.8 The study's own extract — precision is preserved, but `first_seen_at` is the ETL clock

The four APIs above are what we query; what the claims will be built from is the study's own extract
(`data/ctgov_trials.jsonl`, `data/epmc_pubs.jsonl`). Auditing those files read-only answers two
questions the source probe cannot:

| Extract | Records | Field | Month-only | Day |
|---|---|---|---|---|
| `ctgov_trials.jsonl` | **2498** | `start_date` | **56.22%** of present | remainder |
| | | `primary_completion_date` | **54.85%** of present | remainder |
| | | `study_first_post_date` | 0.0% | 100.0% |
| | | `last_update_post_date` | 0.0% | 100.0% |
| | | `results_first_post_date` | 0.0% | 789 present of 2498 |
| `epmc_pubs.jsonl` | **770** | `first_publication_date` | 0.0% | 100.0% |
| | | `first_index_date` | 0.0% | 100.0% |
| | | `electronic_publication_date` | 0.0% | 671 present of 770 |

**Good news:** the extractor does **not** destroy precision — month-only source values stay
month-only (`start_date` month share **56.22%** in the corpus vs **44.53%** in the live sample), and
nothing is silently promoted to a day. The precision constraint is therefore *at least* as binding
on the claims as on the live sample, not less.

**Bad news:** the per-record `first_seen_at` stored in those extract files is **not** an observation
recorded by the observation ledger. The evidence is structural:

| Extract | `first_seen_at` distinct values | Window spanned |
|---|---|---|
| `ctgov_trials.jsonl` | **14** for 2498 records | **13** seconds (2026-11-03T19:39:54.982Z → 2026-11-03T19:40:08.805Z) |
| `epmc_pubs.jsonl` | **94** for 770 records | **85** seconds (2026-11-03T19:41:50.058Z → 2026-11-03T19:43:15.598Z) |

2498 trials "first seen" inside 13 seconds is an ETL write batch, not 2498 observations. Every one of
those stamps is also **later** than the observation ledger's last `sync_run`
(2026-11-03T15:58:46Z), so it cannot have come from the ledger. This is a third clock family that
must not be confused with either of the others:

| Clock family | Values | Meaning |
|---|---|---|
| observation ledger `first_seen_at` | **4** distinct | run-anchored reconstruction of a real collection |
| extract `first_seen_at` | **14** / **94** distinct, second-level | ETL write time of the extraction run |
| `published_at` | per record | when the source published |

The claim-level audit in §4 measures how many claims carry the middle family, and §6 forbids
presenting it as the first.

**Pre-read for the RQ2 within-year ordering question.** Both *declaration* clocks are **100.0%**
day-precision in the corpus (`study_first_post_date` for trial relations, `first_index_date` for
publication relations), so *when a relation was declared* can be ordered inside a year. What cannot
be ordered inside a year is the *event*: `start_date` is **56.22%** month-only. §4 confirms this
on the actual claims, per relation family.

---

## 3. Field → clock legitimacy matrix

The rule for every row below: the **clock** column is the only clock that field may populate. The
**forbidden** column lists substitutions that this audit treats as a provenance defect.

### 3.1 ClinicalTrials.gov (all fields under `protocolSection.statusModule`)

| Field | Measured precision | Present % | Legitimate clock | Label | Must never be substituted for |
|---|---|---|---|---|---|
| `startDateStruct.date` | mixed (day 71, month 57) | 100.0 | `event_at` | `DATE_ONLY` | `published_at`, `first_seen_at`, `valid_from` |
| `studyFirstPostDateStruct.date` | `YYYY-MM-DD` | 100.0 | `published_at` | `SOURCE_PUBLISHED`, `DATE_ONLY` | `event_at`, `first_seen_at` |
| `lastUpdatePostDateStruct.date` | `YYYY-MM-DD` | 100.0 | **none** | `TIME_UNKNOWN` | any of the four; it is a freshness stamp on the current record |
| `primaryCompletionDateStruct.date` | mixed (day 69, month 58) | 99.22 | `event_at` (planned/estimated) | `DATE_ONLY`, `TIME_UNKNOWN` | `published_at`, `first_seen_at`, `valid_from` |
| `resultsFirstPostDateStruct.date` | `YYYY-MM-DD` | 32.81 | `published_at` (results disclosure, a **second** event) | `SOURCE_PUBLISHED`, `DATE_ONLY` | `studyFirstPostDateStruct`, `event_at`, `first_seen_at` |
| `studyFirstSubmitDate` / `lastUpdateSubmitDate` | internal submission dates | — | **none** | `TIME_UNKNOWN` | `published_at`, `first_seen_at` |

### 3.2 Europe PMC

| Field | Measured precision | Present % | Legitimate clock | Label | Must never be substituted for |
|---|---|---|---|---|---|
| `firstPublicationDate` | `YYYY-MM-DD` | 100.0 | `event_at` | `SOURCE_PUBLISHED`, `DATE_ONLY` | `published_at` when `firstIndexDate` exists |
| `firstIndexDate` | `YYYY-MM-DD` | 100.0 | `published_at` (index availability) | `SOURCE_PUBLISHED`, `DATE_ONLY` | `event_at`, `first_seen_at` |
| `dateOfCreation` | `YYYY-MM-DD` | 100.0 | **none** | `TIME_UNKNOWN` | any of the four |
| `dateOfRevision` | `YYYY-MM-DD` | 100.0 | **none** | `TIME_UNKNOWN` | any of the four; it moves forward and keeps no history |
| `electronicPublicationDate` / `journalInfo.printPublicationDate` | `YYYY-MM-DD` | 75.0 | `event_at` (version-specific) | `DATE_ONLY` | merging e-pub and print without a version label |

### 3.3 OpenAlex

| Field | Measured precision | Present % | Legitimate clock | Label | Must never be substituted for |
|---|---|---|---|---|---|
| `publication_date` | `YYYY-MM-DD` | 100.0 | `event_at` | `DATE_ONLY` | `published_at`, `first_seen_at` |
| `created_date` | datetime (second) | 100.0 | **none** (bulk ingest; median lag 3567.5 d) | `TIME_UNKNOWN` | `published_at`, `event_at`, `first_seen_at` |
| `updated_date` | datetime (second) | 100.0 | **none** (refresh stamp) | `TIME_UNKNOWN` | any of the four |

### 3.4 Crossref

| Field | Measured precision | Present % | Legitimate clock | Label | Must never be substituted for |
|---|---|---|---|---|---|
| `issued` | mixed (day 17, month 12, year 1) | 100.0 | `event_at` | `DATE_ONLY` | `published_at`; `first_seen_at` |
| `published-print` | mixed (day 13, month 13, year 1) | 90.0 | `event_at` (print event) | `DATE_ONLY` | `published-online`; `published_at` without a version label |
| `published-online` | mixed (day 14, month 1) | 50.0 | `published_at` | `SOURCE_PUBLISHED`, `DATE_ONLY` | `event_at` for print-only venues; `first_seen_at` |
| `created` | datetime (second) | 100.0 | **none** (DOI deposit) | `TIME_UNKNOWN` | `event_at`, `published_at`, `first_seen_at` |
| `deposited` / `indexed` | datetime (second) | 100.0 | **none** | `TIME_UNKNOWN` | any of the four |

### 3.5 Observation ledger

| Field | Measured precision | Present % | Legitimate clock | Label | Must never be substituted for |
|---|---|---|---|---|---|
| `observation.first_seen_at` | datetime (second), run-anchored reconstruction | 100.0 | `first_seen_at` | `ACTUAL_OBSERVATION` | any other clock; and never propagated to records the ledger never saw |
| `observation.published_at` | date 394 / datetime 6 | 100.0 | `published_at` | `SOURCE_PUBLISHED`, `DATE_ONLY` | `event_at`, `first_seen_at` |
| `observation.event_at` | date 383 / year 17 | 100.0 | `event_at` | `HISTORICAL_PROXY`, `DATE_ONLY` | `published_at`, `first_seen_at` |
| `observation_phase.method` | categorical | 100.0 | provenance of `first_seen_at` | `ACTUAL_OBSERVATION` | must not be ignored when claiming prospective knowledge |
| `observation.source_updated_at` | date 394 / unknown 6 | 100.0 | **none** | `TIME_UNKNOWN` | `published_at`, `first_seen_at` |
| `valid_from` / `valid_to` | **not present in any source API** | 0.0 | `valid_from` (derived only) | `HISTORICAL_PROXY` | copying `event_at` / `published_at` / `created` / `lastUpdatePostDate` / `first_seen_at` into it without a stated derivation rule |

### 3.6 Which time basis may each S-029 relation carry?

Derived mechanically from the matrix above (`clock_availability` in the JSON):

| Source | `event_at` | `published_at` | `first_seen_at` | `valid_from` |
|---|---|---|---|---|
| ClinicalTrials.gov | yes (44.53% month-only) | yes (day) | **absent** | **absent** |
| Europe PMC | yes (day) | yes (day, index proxy) | **absent** | **absent** |
| OpenAlex | yes (day) | **absent** | **absent** | **absent** |
| Crossref | yes (mixed precision) | yes, but only 50.0% present | **absent** | **absent** |
| Observation ledger | yes (17 of 400 year-only) | yes | **yes (400 rows, 1 day)** | **absent** |

Consequences, stated before any claim is built:

* A relation whose evidence comes from **CT.gov / EPMC / OpenAlex / Crossref** can legitimately be
  labelled `SOURCE_PUBLISHED` or `HISTORICAL_PROXY`. It **cannot** be labelled
  `ACTUAL_OBSERVATION` unless a matching ledger row exists.
* A relation can only be `ACTUAL_OBSERVATION` if its `first_seen_at` is one of the 4 ledger
  timestamps **and** its lag to `published_at` is ≤ 1 d — measured to be **6** observations, and
  those 6 are 1 `ctgov` trial, 4 `europepmc` publications and 1 `sec_edgar` `sec_6k`.
* `valid_from` / `valid_to` must be **declared derived** for every relation; no source returns them.

---

## 4. Claim-level clock completeness (Stage 2 — measured on 20563 claims)

**Source of truth**: `data/claims.jsonl`, **20563** claims, **0** parse errors, **18433356** bytes.
The exact file snapshot audited here is pinned by `sha256` in
`clock_audit.json → claims_clock_completeness.claims_file_sha256`; **re-run `--stage2` if that file
is rewritten.** Every number below is in `clock_audit.json → claims_clock_completeness`.

### 4.1 Completeness per clock

| Clock field | Present | % present | Missing | % missing | Distinct values | Precision |
|---|---|---|---|---|---|---|
| `published_at` | **20563** | **100.0** | 0 | **0.0** | 2276 | all day (20563) |
| `event_at` | **16198** | **78.77** | **4365** | **21.23** | 1631 | month **2618**, day **13580** |
| `valid_from` | **20563** | **100.0** | 0 | **0.0** | 2285 | all day (20563) |
| `valid_to` | **0** | **0.0** | **20563** | **100.0** | 0 | — |
| `first_seen_at` | **20563** | **100.0** | 0 | **0.0** | **107** | all datetime (20563) |
| `declared_at` | **20563** | **100.0** | 0 | **0.0** | 2557 | all day (20563) |

Two of these rows are the whole story:

* `valid_to` is **100.0% absent**. Every relation in the dataset is an **open-ended interval**; the
  data contains no statement that any relation ever ended.
* `first_seen_at` is 100% present but has only **107 distinct values** for **20563** claims. A real
  observation clock does not look like that (see §4.2).

`event_at` is missing on **4365** claims (21.23%) — almost exactly the **4351** `REFERENCES_PUBLICATION`
claims, which have no event date by construction, plus **14** trial claims.

### 4.2 The claim-level `first_seen_at` is the ETL clock, not an observation

| Check | Measured |
|---|---|
| Distinct `first_seen_at` values across 20563 claims | **107** |
| Values that exist in the observation ledger | **0** |
| Values that do **not** exist in the observation ledger | **20563** |
| Earliest → latest | 2026-11-03T19:39:54.982Z → 2026-11-03T19:43:15.598Z |
| Claims whose stamp is **after** the ledger's last `sync_run` (2026-11-03T15:58:46Z) | **20563** (**100.0%**) |
| Distinct values in the ledger itself | **4** |

**20563 claims were "first seen" inside 200 seconds.** That is the extraction run writing its output,
not 20563 observations. No claim-level `first_seen_at` can be traced to an observation the project
actually recorded.

### 4.3 ACTUAL_OBSERVATION — the strict and lenient numbers

The study now reports **two** numbers, and they answer different questions. Both are measured here,
independently of the claims builder's labels:

| Number | Definition | Claims | % of 20563 |
|---|---|---|---|
| **STRICT** (the verdict) | `first_seen_at` value exists in the observation ledger **and** lag ≤ 1 d | **0** | **0.0** |
| **LENIENT** | `0 ≤ lag ≤ 7` d, using whatever `first_seen_at` the extract stored — **no** requirement that it came from the ledger | **76** | **0.37** |
| — of which labelled `ACTUAL_OBSERVATION` | builder's own label | **60** | — |
| — of which labelled `SOURCE_PUBLISHED` (the `HAS_TOPIC` family, hard-coded) | builder's own label | **16** | — |
| — distinct source records behind the 76 claims | `source_record_id` | **10** | — |
| — distinct evidence records behind the 76 claims | `evidence_id` | **10** | — |

Why the two differ, precisely: the lenient count asks only "was our fetch close in time to the
publication date?". Every one of the **76** lenient claims gets its `first_seen_at` from the
extraction run, and **none** of those timestamps is in the observation ledger (§4.2). So the lenient
number describes *this study's own fetch*, and it is only a statement about the past in the sense
that the fetched record already existed. **It is not an observation of when the record appeared.**

Additional splits that matter:

| Measure | Claims |
|---|---|
| Declared `ACTUAL_OBSERVATION` but not in the ledger | **60** |
| Declared `ACTUAL_OBSERVATION` with lag > 1 d | **38** |
| Max lag among declared `ACTUAL_OBSERVATION` | **6** d |
| Claims with lag ≤ 1 d at all (still not observations) | **34** |
| Genuinely strict but **not** declared | **0** |

### 4.3b The pipeline's own strict field — audited, not trusted

The rebuilt claims file was meant to carry `strict_observed_asof` on every claim. Measured:

| Field | Claims carrying it | Values |
|---|---|---|
| `strict_observed_asof` | **0** of **20563** | — (absent everywhere) |
| `observation_system` | **2517** of 20563 | `NONE` **2514**, `THIS_STUDY_COLLECTION` **3** |

This audit re-derives strictness per claim from the ledger, so the verdict does not depend on that
field. But two things follow for the delivered artifact: the `strict_observed_asof` field is **not
present on any claim** in this snapshot, and the **3** claims marked `THIS_STUDY_COLLECTION` are
**all** `strict=False` under the ledger test — marking a record as observed by this study does not
make its timestamp a ledger observation.

Rewriting the declaration table with the audit's verdict:

| Declared `time_basis` | Claims | After audit |
|---|---|---|
| `HISTORICAL_PROXY` | **13048** | unchanged |
| `SOURCE_PUBLISHED` | **7455** | unchanged |
| `ACTUAL_OBSERVATION` | **60** | **must be downgraded to `HISTORICAL_PROXY`** |
| `DATE_ONLY` | **0** | never used |
| `TIME_UNKNOWN` | **0** | never used |
| missing | **0** | — |

`DATE_ONLY` and `TIME_UNKNOWN` are never used as labels even though §4.4 shows the precision
constraint applies to **2618** claims and `event_at` is missing on **4365**. The label vocabulary is
being under-used.

**Lag distribution `first_seen_at − published_at` (20563 pairs)**: min 0 d, p25 **1615** d, median
**3327** d, p75 **5052** d, max **9434** d. Buckets: same day **32**, 1 d **2**, 2–7 d **42**,
8–30 d **61**, 31–365 d **1815**, >365 d **18611**.

### 4.4 Which families can be ordered inside a year?

Measured per relation family (all eight present in the dataset):

| Family | Claims | `declared_at` day % | `event_at` day % | `event_at` month/year % | `event_at` missing % | `valid_from` day % | Time basis carried |
|---|---|---|---|---|---|---|---|
| `HAS_TOPIC` | **7455** | **100.0** | **100.0** | 0.0 | 0.0 | 100.0 | `SOURCE_PUBLISHED` 7455 |
| `REFERENCES_PUBLICATION` | **4351** | **100.0** | **0.0** | 0.0 | **100.0** | 100.0 | `HISTORICAL_PROXY` 4351 |
| `SPONSORS_TRIAL` | **4309** | **100.0** | **46.9** | **52.77** | 0.32 | 100.0 | `HISTORICAL_PROXY` 4305, `ACTUAL_OBSERVATION` 4 |
| `AFFILIATED_WITH` | **2175** | **100.0** | **100.0** | 0.0 | 0.0 | 100.0 | `HISTORICAL_PROXY` 2144, `ACTUAL_OBSERVATION` 31 |
| `CO_AFFILIATED_ON` | **1567** | **100.0** | **100.0** | 0.0 | 0.0 | 100.0 | `HISTORICAL_PROXY` 1543, `ACTUAL_OBSERVATION` 24 |
| `HOSTS_TRIAL_SITE` | **598** | **100.0** | **42.81** | **57.19** | 0.0 | 100.0 | `HISTORICAL_PROXY` 598 |
| `FUNDED_BY` | **105** | **100.0** | **100.0** | 0.0 | 0.0 | 100.0 | `HISTORICAL_PROXY` 104, `ACTUAL_OBSERVATION` 1 |
| `RESPONSIBLE_FOR_TRIAL` | **3** | **100.0** | **33.33** | **66.67** | 0.0 | 100.0 | `HISTORICAL_PROXY` 3 |

**Direct answer for RQ2.** `declared_at` is **100.0% day-precision in every family**, so *when a
relation was declared* can be ordered inside a year everywhere. `event_at` cannot: the three trial
families are **52.77%** / **57.19%** / **66.67%** month-or-year only, and `REFERENCES_PUBLICATION` has
no event date at all. So:

* ordering relations by **declaration** (who announced first): possible for all 20563 claims;
* ordering relations by the **event** (which trial actually started first): not possible for roughly
  half of the trial-related claims, and impossible for the citation family;
* `valid_from` is day-precision on **100.0** of present values — but it is a *derived* clock, so its
  precision is not evidence that the date is right.

### 4.5 The builder's arithmetic is internally consistent — but the lag field is incomplete

`observed_lag_days` is present on **13108** of 20563 claims (**the other 7455 — the `HAS_TOPIC`
family — carry no lag field**). On all **13108** claims where it exists, recomputing
`first_seen_at − published_at` from the stored timestamps gives **0** mismatches. So the lag numbers
the builder reports are arithmetically correct; the defect is the *semantics* of `first_seen_at`, not
the subtraction.

---

## 5. Temporal contradictions

### 5.1 Measured at source level, already

| Contradiction | Measured | Reading |
|---|---|---|
| Ledger `first_seen_at` **before** `published_at` | **0** of 400 | impossible value, correctly absent — a good sign |
| Ledger `published_at` **before** `event_at`, CT.gov | **106** of 157 (**67.52%**) | **not** an error: a trial is often registered before it starts (pre-registration) |
| Ledger `published_at` **before** `event_at`, Europe PMC | **18** of 237 (**7.59%**) | real: indexed before the nominal print publication date, because that date is an issue date |
| Ledger `first_seen_at` **before** `event_at` | **9** of 400 | these are future-dated events: **9** rows (**2.25%**) have `event_at` after the audit date (e.g. `2027-02-23`) — planned starts. A relation whose event has not happened cannot be evidence that it happened |
| CT.gov `studyFirstPostDate` before `startDate` | **64** of 128 (**50.0%**) | confirms `event_at` and `published_at` are independent axes |

The 67.52% figure is the single most misreadable statistic in this dataset. It is a **clock-ordering
fact, not a data defect**: for a trial, registration normally precedes the start date, so
`published_at < event_at` is expected. The same shape in Europe PMC is a genuine artefact. Any
contradiction check must therefore be **conditioned on record type** — a blanket
"published_at must not precede event_at" rule would falsely condemn two thirds of the trial sample.

### 5.2 Claim level — measured

**How the two ACTUAL_OBSERVATION numbers relate to this section** (§4.3): the **strict** count is
**0**; the **lenient** window holds **76** claims, of which **60** are labelled `ACTUAL_OBSERVATION`
and **16** `SOURCE_PUBLISHED`. Every one of the 76 uses an extraction stamp, never a ledger
observation, so **no contradiction count below changes** if the lenient set is excluded — the lenient
label adds no temporal evidence, it only narrows the lag.

| Contradiction check | Claims | % of 20563 | Reading |
|---|---|---|---|
| `published_at < event_at` | **2775** | **13.5** | must be split, see below |
| — of which trial relations | **2169** | — | **legitimate pre-registration** |
| — of which non-trial relations | **606** | — | index-date < issue-date artefact (§2.2) |
| `first_seen_at < published_at` | **0** | **0.0** | correctly absent |
| `valid_to < valid_from` | **0** | **0.0** | vacuous — `valid_to` is never populated |
| `declared_at < valid_from` ("anachronism") | **284** | **1.38** | almost all `AFFILIATED_WITH`; explained below |
| Builder's `anachronism = true` flag | **282** | — | a **different** notion (entity mapping, not clock order) |
| Both flags agree | **0** | — | the two checks share no claims |

**`published_at < event_at`: 2775 claims, but only 606 are interesting.** 2169 of them are trial
relations where the registry posted the record before the trial started — pre-registration, exactly
as in §5.1. The **606** non-trial cases are `AFFILIATED_WITH` claims where `published_at` is the
Europe PMC **index** date and `event_at` is the **journal** date; the index can precede a print issue
date (§2.2 measured 7.59% of that shape in the ledger). So this is a **date-semantics** defect, not
look-ahead. Conclusion unchanged: contradiction checks must be conditioned on record type and on
which field each clock was taken from.

**Anachronism (`declared_at < valid_from`): 284 claims.** These are `AFFILIATED_WITH` claims where
`declared_at` = `firstIndexDate` and `valid_from` = `firstPublicationDate`, i.e. the same issue-date
artefact. They are **not** evidence of using future knowledge.

**The builder's `anachronism` flag measures something else entirely.** It is present on **2517**
claims, true on **282**. It is driven by entity mapping (`anachronism_if_mapped`) — attributing a
relation to a parent company before the acquisition completed — not by clock ordering. The two sets
**do not overlap (0 claims carry both)**. Both checks are worth keeping, but the report must not
merge them: one is entity-history leakage, the other is timestamp ordering.

### 5.3 `REFERENCES_PUBLICATION`: a family that cannot be dated as built

This class is the one the Lead asked about specifically. Measured over all **4351**
`REFERENCES_PUBLICATION` claims:

| Measure | Claims | % of 4351 |
|---|---|---|
| Total reference claims | **4351** | 100.0 |
| Resolvable to a publication year in our corpus | **26** | **0.6** |
| Not resolvable (citation has no DOI/PMID, or paper not in our extract) | **4325** | **99.4** |
| — **Cited paper published in a LATER year than the trial's first post** (impossible) | **23** | **0.53** |
| — Cited paper in the **same** year | **2** | 0.05 |
| — Cited paper published **before** the trial (legitimate, but must be dated by the paper) | **1** | 0.02 |
| Largest impossible gap | **14** years | — |
| Largest legitimate "before" gap | **5** years | — |

Worked examples of the impossible class: trial `NCT01534299` first posted **2012-02-16** is recorded
as citing `10.1097/hjh.0000000000004219`, published **2025-12-10** — a **14**-year gap, and that
trial's registry record was last updated **2026-10-23**; `NCT02752737` (2016) cites a
**2023-12-12** paper, last updated **2025-07-30**; `NCT01970501` (2013) cites a **2017-12-06** paper,
last updated **2022-09-26**.

**Mechanism — why this is back-dating, not a contradiction.** The ClinicalTrials.gov reference list is
**current-state**. The registry retains no history of when a reference was added; the only stamp it
exposes is `lastUpdatePostDate`. A trial first posted in 2012 that lists a 2025/2026 paper therefore
means **the reference was added at a later registry update** — the trial cannot have cited a paper
that did not exist yet. The defect is that the claim dates the citation by the **trial's** first-post
date, so the citation inherits a date that predates its own evidence.

Testing that mechanism against the only stamp available, per impossible claim:

| Test | Claims |
|---|---|
| Impossible-dated reference claims | **23** |
| — trial's `lastUpdatePostDate` is **on/after** the paper's publication date (a later update could have added it — mechanism consistent) | **16** |
| — trial's `lastUpdatePostDate` is **before** the paper's publication date (mechanism cannot explain it — unexplained defect) | **7** |

**Reading.** Because these claims date the relation with the **trial's** dates (`published_at =
declared_at = valid_from =` trial first-post, `event_at =` null), a reference to a paper published
later appears as a temporal impossibility, and a reference to an older paper is silently
mis-dated. On the tiny resolvable subset the defect rate is **23 of 26 (88.46%)**. The family cannot
be used as a dated relation without being re-based on the **publication's** date. Recommendation:
carry these edges as `TIME_UNKNOWN`, or re-date them from the cited paper and re-run.

**Recommended sentence for the pilot document** (attributed to TEMPORAL_PROVENANCE.md §5.3):

> 23 of the 4351 `REFERENCES_PUBLICATION` claims (0.53% of the family) cite a paper whose publication
> date is later than the trial's first-post date, by up to 14 years. The ClinicalTrials.gov reference
> list is current-state — the registry keeps no history of when a reference was added — so these are
> references added at a later registry update, not future citations: the relation is back-dated
> because it is dated by the trial's first-post date instead of the paper's publication date. For 16
> of the 23 the trial's last-update date is on or after the paper's publication date, which is
> consistent with that mechanism; for 7 it is not, and those 7 remain unexplained and should be
> checked individually.

---

## 6. What a downstream temporal network may and may not claim

**Binding rules for S-029.** These follow directly from the measurements above, and now also from the
claim-level audit in §4–§5.

1. **No historical PIT observation can be manufactured — and at claim level there is none.** A claim
   may carry `ACTUAL_OBSERVATION` only if its `first_seen_at` appears in the observation ledger and its
   lag to `published_at` is ≤ 1 d. Measured on the real dataset: **0** of **20563** claims qualify.
   The ledger's own ceiling is **6** prospective observations out of **400**, over **1** day. Every
   claim-level `ACTUAL_OBSERVATION` label (**60** of them) must be downgraded to `HISTORICAL_PROXY`.

2. **An "as-of T" graph for T before 2026-11-03 is a historical-proxy construction, not an
   observation.** The correct sentence is: *"we reconstructed what would have been knowable at T
   under rule R"* — never *"we knew this at T"*. The claim-level lag distribution makes this concrete:
   median **3327** days, p75 **5052** days, max **9434** days, with **18611** claims beyond one year.

3. **`date_precision` must travel with every timestamp.** At claim level, `event_at` is month-only on
   **2618** of **16198** present values (**16.16%**) and missing entirely on **4365**; CT.gov trial
   start dates are **44.53%** month-only in the live sample and **56.22%** in the study corpus
   (Medtronic **57.5%**, GE HealthCare **55.0%**); Crossref `issued` is day-precision on only
   **17 of 30**. A network edge dated `2018-07` cannot support "in the week of 2018-07-15".

4. **`event_at` and `published_at` must be separate edge attributes, never one column.** Measured:
   **50.0%** of trials are posted before they start; EPMC indexing lags publication by a median of
   **4.0** days with a 1245-day tail; Crossref deposits lag by a median of **13.5** days with a
   12598-day tail. At claim level the two clocks disagree in **2775** claims (**13.5%**), of which
   **606** are the genuine index-date artefact and **2169** are legitimate pre-registration.

5. **`valid_from` / `valid_to` must be declared derived, and the study has no expiry clock.**
   `valid_to` is populated on **0** of **20563** claims (**0.0%**), so no relation in this dataset can
   be claimed to have ended. If the study sets `valid_from = published_at`, that rule must be written
   in the paper; it is a modelling assumption, not a datum.

6. **Never propagate a ledger `first_seen_at` onto records the ledger never saw — and do not accept
   the extract's `first_seen_at` as a substitute.** The claims carry **107** distinct `first_seen_at`
   values, **none** of which is in the ledger and **all** of which post-date its last run
   (2026-11-03T15:58:46Z). The ledger's own `observation_mapping` still shows **238**
   `PENDING_REVIEW` of **401** rows.

7. **Do not date a relation by the wrong side of it.** `REFERENCES_PUBLICATION` is the worked example:
   it is built with the **trial's** dates, is resolvable for only **26** of **4351** claims
   (**0.6%**), and among the resolvable ones **23** are impossible (cited paper published up to
   **14** years *after* the trial was first posted; **88.46%** of resolvable cases). The mechanism is
   that the registry reference list is **current-state**, so those references were added at a later
   update and the claim back-dates them: **16** of the 23 are consistent with that mechanism (the
   trial's `lastUpdatePostDate` is on/after the paper's publication date) and **7** are not, so they
   need individual checking. Either re-base this family on the publication's date or mark it
   `TIME_UNKNOWN`.

8. **Report strict and lenient separately, and never let the lenient one be called an observation.**
   Strict is **0**; lenient is **76** claims (**60** labelled `ACTUAL_OBSERVATION`, **16**
   `SOURCE_PUBLISHED`) behind **10** distinct source records. The lenient number measures this study's
   own fetch latency, not knowledge available at the time.

9. **State the clock deficit in the paper.** The honest one-line summary: *this study has real
   observation evidence for 400 records over 1 day, 6 of which are prospective; none of its 20563
   relations carries a genuine observation timestamp, every one is a source-published or reconstructed
   proxy, and no relation has an end date.* If a reviewer asks "did you know this at the time?", the
   answer for every pre-2026-11-03 edge is **no**.

---

## 7. Reproduction

| Command | Effect | Network |
|---|---|---|
| `python code/s029_clock_audit.py --stage1` | live probes + ledger audit → `artifacts/clock_audit.json` | yes, budgeted |
| `python code/s029_clock_audit.py --refresh` | recompute ledger audit, field map, S-028 comparison, budget from the **already recorded** calls | **0 calls** |
| `python code/s029_clock_audit.py --stage2` | claim-level completeness from `data/claims.jsonl` | none |
| `python code/s029_clock_audit.py --verify-report` | fail if a number in this document is absent from the JSON | none |

Read-only guarantees: the ledger is opened with URI `mode=ro` and `query_only=ON`, an attempted
write is refused, and its `sha256` is identical before and after. The frozen S-028 research input is
likewise opened `mode=ro` for the comparison in §2.6. No git command was run and no file outside
this study directory was written.
