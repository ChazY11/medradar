# QUALITY_REPORT — ATLAS-001

**Generated from:** `research/atlas/reports/identity_pilot.json`,
`research/atlas/reports/quality_report.json`, `research/atlas/reports/verification.json`
**Database:** `research/atlas/staging/atlas.sqlite` (git-ignored, regenerable)
**Run date:** 2026-11-10

This report separates three things that are often conflated:
**test results** (does the code do what it claims), **data-quality findings** (what is wrong or
missing in the data), and **verification** (does an independent process reproduce the numbers).

---

## 1. Automated tests

| Suite | Result |
|---|---|
| Pre-existing repository suite on the audited baseline | **1,122 tests, exit 0** |
| ATLAS identity tests (`test_atlas_identity.py`) | all pass |
| ATLAS evidence tests (`test_atlas_evidence.py`) | all pass |
| ATLAS database/migration/graph tests (`test_atlas_db.py`) | all pass |
| ATLAS research/as-of/prospective tests (`test_atlas_research.py`) | all pass |
| ATLAS connector tests, offline payloads (`test_atlas_connectors.py`) | all pass |
| CI verifier smoke test (`tests/run_atlas_ci_verifier.py`) | 14/14 checks pass |

The ATLAS tests pin the mistakes that matter: candidate evidence cannot be confirmed, a shared
510(k) is not device identity, identical brand across firms is a rejection, clock copies are
flagged, versions are immutable, revocation keeps history, migrations refuse tampering, and
`as_of` never promotes derived dates.

CI: `.github/workflows/atlas.yml` runs the offline suite on Python 3.10/3.11/3.12 plus schema
migration, empty-store operations, historical queries and the verifier smoke test. CI does not
run the live pilot (no network tests in CI by design).

---

## 2. Data-quality findings (from the real pilot run)

`quality_report.json` contains **53 findings**:

| Check | Severity | Count | Meaning |
|---|---|---:|---|
| `duplicate_same_source` | warning | 50 (capped list) | MDALL publishes the same GTIN identifier under more than one licence. Real registry behaviour; recorded, not "fixed". |
| `duplicate_cross_source_expected` | info | 1 aggregate | 934 GTINs appear in both MDALL and GUDID — this is the intended dedupe, not independent corroboration. |
| `missing_company_link` | info | 2 (aggregated) | Records outside the five-firm sample have no target-firm link. Expected; not evidence of a missing company. |
| error-severity findings | — | **0** | no impossible clocks, no identity contradictions, no restricted content, no failed runs |

There are **no `identity_contradiction` findings**: among the 934 bridged pairs, no pair carried
the same DI while disagreeing on model/brand. (The resolver would have demoted them to
`CANDIDATE` and the check would have raised an error.)

### Collection completeness

- All four collection runs have `status='ok'`; every request is in `request_log` and the JSONL
  ledger.
- Pilot request accounting: **150 requests** (5 UDI pages, 12 AccessGUDID lookups, 5 510(k)
  pages, 1 MDALL table stream, 48 identifier-bridge batches, 80 licence/company lookups).
- No run produced "zero records with requests".
- A deliberately wrong company string (`"Medtronic plc"`) returned HTTP 404 during an early
  run; the pilot recorded it under `coverage.errors` rather than reporting zero devices. The
  final run uses the verified search terms and has no 404s.

---

## 3. Known data gaps (not bugs)

| Gap | Measured | Consequence |
|---|---|---|
| MDALL publishes UDI-DIs for only a small subset | 5,512 / 1,673,926 active identifier rows normalise to a 14-digit DI (**0.33 %**) | Cross-market identity can only be confirmed for UDI-adopting records; the rest stay unresolved. |
| MDALL identifier table has no brand/model | by design | A name/method comparison across the U.S.–Canada bridge is impossible for 99.67 % of Canadian rows. |
| GUDID API has no premarket-submission field | verified 2026-11-10 | Device↔510(k) cannot be confirmed at device level from this source; modelled as family/candidate, never identity. |
| openFDA UDI company search returns a page, not a population | 100/firm sampled from 88,142 (Medtronic), 4,241 (Philips), 1,602 (Mindray), 518 (GE), 316 (Draeger) | Sample is not random and not prevalence-weighted. |
| Only three target firms appear in the bridged set | Medtronic + GE HealthCare present; Philips/Mindray/Draeger absent from the resolved GTIN subset | Five-firm coverage is partial; reported as `missing_firms_in_bridge` rather than padded. |
| No publications/trials/patents collected for devices | ATLAS-001 scope | `device_research_candidates` returns `NOT_COLLECTED`, not an empty claim of no research. |

---

## 4. Independent verification

`tools/verify_atlas.py` opens the database **read-only** and re-derives with plain SQL and its
own canonical-JSON hash:

1. every head points at an existing version;
2. versions are contiguous;
3. head hashes match version hashes;
4. every payload hash recomputes;
5. every confirmed identity relation shares exactly one DI;
6. every rejection has a reason;
7. no duplicate live relations;
8. report counts equal database counts (identity relations only);
9. baseline arithmetic is internally consistent;
10. no restricted-licence evidence or oversized sample is committed.

**Result: 14/14 checks pass** (`research/atlas/reports/verification.json`).

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
| quality emitted 7,595 rows | report unreadable | aggregate per source/class → 53 |
| verifier held a Windows file handle | temp cleanup failed in CI | explicit close |

---

## 6. Residual risks

1. **No human labelling.** Precision/recall are computed on label sets derived from official
   identifiers; they are not adjudicated by a person. No population-level metric is claimed.
2. **Sampled coverage.** The 934 confirmed pairs are a bounded sample, not the complete set of
   U.S.–Canada device identity relations.
3. **MDALL table is a moving target.** The identifier table changes; the report records the
   table's byte size and SHA-256 when downloaded, and the cache is reused for 7 days.
4. **ASCII-only coverage of company names.** Curated aliases cover the five firms; other
   companies resolve to `none` by design.
5. **No licence review of every payload.** The source register records licence posture; the
   verifier checks that restricted sources never enter the store, but it does not re-read
   every licence page.
