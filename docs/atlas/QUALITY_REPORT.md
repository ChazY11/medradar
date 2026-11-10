# QUALITY_REPORT — ATLAS-001

**Generated from:** `research/atlas/reports/identity_pilot.json`,
`research/atlas/reports/quality_report.json`, `research/atlas/reports/verification.json`
**Database:** `research/atlas/staging/atlas.sqlite` (git-ignored, regenerable)
**Run date:** 2026-11-10/11 (final run after independent-audit corrections)

This report separates **test results** (does the code do what it claims), **data-quality
findings** (what is wrong or missing in the data), and **verification** (does an independent
process reproduce the numbers).

---

## 1. Automated tests

| Suite | Result |
|---|---|
| Pre-existing repository suite on the audited baseline (`main`) | **1,074 tests, exit 0** |
| Branch total after ATLAS tests | **1,128 tests** (1,074 + 54 ATLAS) |
| ATLAS identity tests | all pass |
| ATLAS evidence tests | all pass |
| ATLAS database/migration/graph tests | all pass |
| ATLAS research/as-of/prospective tests | all pass |
| ATLAS connector tests, offline payloads | all pass |
| CI verifier smoke test | 16/16 checks pass |

The ATLAS tests pin the mistakes that matter: candidate evidence cannot be confirmed, a shared
510(k) is not device identity, identical brand across firms is a rejection **only when the brand
is real** (registry placeholders such as `NA` are erased, with a regression test), clock copies
are flagged, versions are immutable, revocation keeps history, migrations refuse tampering, and
`as_of` never promotes derived dates.

CI: `.github/workflows/atlas.yml` runs the offline suite on Python 3.10/3.11/3.12 plus schema
migration, empty-store operations, historical queries and the verifier smoke test. CI does not
run the live pilot (no network tests in CI by design).

---

## 2. Data-quality findings (final real run)

`quality_report.json` contains **54 findings, zero error-severity**:

| Check | Severity | Count | Meaning |
|---|---|---:|---|
| `duplicate_same_source` | warning | 50 listed of 235 | MDALL publishes the same GTIN identifier under more than one licence. Real registry behaviour; recorded, not "fixed". |
| `duplicate_cross_source_expected` | info | 1 aggregate | 957 canonical keys appear in more than one source; most are the 934 intended UDI dedupes, the rest are licence/package-key overlaps. This is dedupe, **not independent corroboration**. |
| `missing_company_link` | info | 2 (aggregated) | Records outside the five-firm sample have no target-firm link. Expected; not evidence of a missing company. |
| `request_no_match` | info | 1 aggregate | 6 openFDA identifier batches returned HTTP 404 ("no match"), recorded as no-match rather than as a failure or as zero events. |
| error-severity findings | — | **0** | no impossible clocks, no identity contradictions, no restricted content, no failed runs |

There are **no `identity_contradiction` findings**: among the 934 bridged pairs, no pair carried
the same DI while disagreeing on model/brand.

### Collection completeness and request accounting

- **Seven** collection runs, all `status='ok'`: UDI, AccessGUDID, 510(k), MDALL table, identity
  bridge, MDALL licences, pair classification.
- **150 HTTP requests**, all present in `request_log` and the JSONL ledger:
  5 openFDA UDI pages + 48 identifier-bridge batches + 12 AccessGUDID lookups + 5 openFDA 510(k)
  pages + 80 MDALL licence/company lookups.
- `request_log` rows: **144 × HTTP 200, 6 × HTTP 404 (no-match), 0 × 5xx / transport failure**.
  404 from an openFDA search means "valid query, no matching record"; it is classified
  separately from a failure, and it is **not** reported as zero events.
- The MDALL identifier table itself was downloaded once (219,970,233 bytes, SHA-256 recorded) and
  reused from the git-ignored cache in this run, so it contributes 0 requests here.
- No run produced "zero records with requests".

---

## 3. Known data gaps (not bugs)

| Gap | Measured | Consequence |
|---|---|---|
| MDALL publishes UDI-DIs for only a small subset | 5,512 / 1,673,926 active identifier rows normalise to a 14-digit DI (**0.33 %**); 5,477 are already bare 14 digits | Cross-market identity can only be confirmed for UDI-adopting records; the rest stay unresolved. |
| MDALL identifier table has no brand/model | by design | A name comparison across the U.S.–Canada bridge is impossible for 99.67 % of Canadian rows. |
| GUDID API has no premarket-submission field | verified 2026-11-10 | Device↔510(k) cannot be confirmed at device level from this source; modelled as family/candidate, never identity. |
| openFDA UDI company search returns a page, not a population | 100/firm sampled from 88,142 (Medtronic), 4,241 (Philips), 1,602 (Mindray), 518 (GE), 316 (Draeger) | Sample is not random and not prevalence-weighted. |
| Only two target firms appear in the bridged set | Medtronic + GE HealthCare present; Philips, Mindray, Draeger absent from the resolved GTIN subset | Five-firm coverage is partial; reported as `missing_firms_in_bridge`, not padded. |
| No real cross-firm label collisions in the sample | 0 hard negatives after placeholder labels (`NA`, `NONE`, …) were erased | The baseline's failure is "finds nothing", not "produces false positives" on this sample. Stated as such; the earlier 33 "collisions" were a placeholder artefact and were removed. |
| No publications/trials/patents collected for devices | ATLAS-001 scope | `device_research_candidates` returns `NOT_COLLECTED`, not an empty claim of no research. |

---

## 4. Independent verification

`tools/verify_atlas.py` opens the database **read-only** and re-derives with plain SQL and its
own canonical-JSON hash. **16 checks**:

1. every head points at an existing version;
2. versions are contiguous;
3. head hashes match version hashes;
4. every payload hash recomputes;
5. every confirmed identity relation shares at least one DI;
6. every rejection has a reason;
7. every revoked relation has a reason and exactly one revocation event;
8. every run's request counter is covered by `request_log` rows;
9. no duplicate live relations;
10. report evidence counts equal database counts;
11. report identity-relation counts equal database counts;
12. baseline arithmetic is internally consistent;
13. tracked sample files are bounded;
14. tracked samples use open sources only;
15. tracked samples cite an official open source;
16. no restricted-licence evidence is stored.

**Result: 16/16 pass** (`research/atlas/reports/verification.json`).

This is a genuine second implementation of the arithmetic, not a re-run of the pipeline. It
does **not** provide human adjudication: confirmed relations rest on exact official-identifier
equality, and candidates remain candidates.

---

## 5. Engineering defects found and fixed during this round

| Defect | Impact | Fix |
|---|---|---|
| Umlaut folding dropped the `e` in `Dräger` | curated ASCII alias never matched; a firm could silently lose records | two-letter transliteration + regression test |
| AccessGUDID duplicates counted by source-scoped id | same GUDID record looked independent | dedupe by canonical key; report calls it a duplicate |
| MDALL identifier compared as a model number | every true UDI bridge became a contradiction (0 confirmed) | MDALL view carries no fabricated model; 934 confirmed after fix |
| `executescript` committed inside a transaction | a failed migration could leave a half-applied schema | statement-by-statement transaction |
| `as_of` applied the capture boundary to public visibility | inferable history was hidden | boundary only for the observed basis |
| quality emitted 7,595 rows | report unreadable | aggregate per source/class → 54 |
| **`request_log` never written** | quality checks could not see HTTP failures; docs claim was false | every stage flushes the ledger into `request_log`; verifier checks coverage |
| **`NA` placeholder brands counted as real labels** | 33 fake "hard-negative" false positives | placeholder filter + regression test; real hard-negative count now 0 and reported as such |
| **verifier had a check that could never fail** | fake assurance | replaced with revocation-history and request-log invariants |
| **canonical key used a package DI, not the primary DI** | dedupe could miss the same device | primary DI preferred; regression test |
| **committed examples lacked content hashes** | docs claimed hashes that were not there | evidence hashes added to example JSON |
| report snapshot preceded graph/prospective writes | stale `prospective_candidates=0` | explicit `db_stats_note`; verifier checks the stable fields |

Residual risks: no human labels; sampled coverage; a moving Canadian registry; ASCII-only curated
aliases; no independent re-read of every licence page.
