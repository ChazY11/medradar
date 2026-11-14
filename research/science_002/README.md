# SCIENCE-002 - Cross-source MedTech early-signal validation

**Verdict: NULL.** The experiment is valid - every feasibility gate and both
positive controls passed - and it found no detectable within-firm incremental
prediction from SEC R&D disclosure to future FDA 510(k) clearance events.

This directory is one empirical study, not a platform. It asks a single question
across two public sources and reports what came back, including the parts that
make the answer weaker.

---

## The question

> Using only what was publicly available to an investor at a point in time, can we
> predict whether a medical-technology issuer will have an FDA 510(k) clearance in
> the next 90 days - **beyond what that issuer's own clearance history already
> predicts**, and **inside the firm** rather than across firms?

SCIENCE-001 established two things that shape this design: firm identity is a very
strong baseline, and a pooled cross-company AUC is largely a measurement of
industry composition. SCIENCE-002 therefore (a) changes the outcome source from
SEC item codes to FDA clearance events, (b) moves the unit from filing to
issuer-month, and (c) makes the **within-firm** comparison the primary test, with a
pooled AUC reported only descriptively.

## What was built

| piece | where |
|---|---|
| cross-source identity resolution, SEC registrant <-> FDA applicant, three exact-match tiers with an exclusion ledger | `entity.py`, `universe.py`, `ENTITY_RESOLUTION.md` |
| openFDA bulk ingestion + streaming parser | `fda.py` |
| SEC submissions and XBRL with explicit point-in-time rules | `sec.py`, `TIME_SEMANTICS.md` |
| issuer-month panel, 90-day labels, censoring, availability-stamped features | `panel.py` |
| model ladder, firm-conditional estimator, permutation null, cluster bootstrap, LOFO, controls | `experiment.py` |
| pre-registered sensitivities S1-S3 | `sensitivity.py` |
| independent adversarial audit | `audit.py`, `AUDIT.md` |
| figures from committed artifacts only | `figures.py` |
| offline test suite, 25 tests | `tests/test_science_002.py` |

## The numbers

| | |
|---|---|
| SEC registrants investigated / in universe | 62 / **48** |
| issuer-months (complete case) | **2,554** (train 1,772, holdout 782) |
| attributable FDA 510(k) clearances 2015-2026 | **3,143** |
| holdout prevalence, 90-day clearance | **53.1%** |
| **primary: delta firm-stratified AUC (B3c - B2c)** | **-0.034**, permutation p = 0.096, CI [-0.083, +0.017] |
| pooled holdout AUC, firm history / + R&D | 0.829 / 0.833 (delta +0.005, CI [-0.005, +0.017]) |
| leave-one-firm-out AUC, + R&D vs + activity | 0.383 vs 0.385 (delta -0.002) |
| minimum detectable delta at 80% power | 0.055 |

Full tables, controls and caveats: `RESULTS.md`.

## Reproduce from a clean checkout

Python 3.10+, no third-party package for fetch/verify/build/experiment; matplotlib
only for the figures (same policy as SCIENCE-001).

```
python research/science_002/cli.py fetch        # network once: openFDA ZIPs + SEC JSON, ~330 MB
python research/science_002/cli.py universe     # offline: identity, inclusion ledger, source manifest
python research/science_002/cli.py panel        # offline: issuer-month panel
python research/science_002/cli.py experiment   # offline (~4 min): ladder, bootstrap, permutation, controls
python research/science_002/cli.py audit        # offline (~12 min): adversarial checks + reproducibility
python research/science_002/cli.py sensitivity  # offline (~8 min): S1-S3
python research/science_002/cli.py figures      # offline
python -m pytest tests/test_science_002.py -q   # offline, synthetic fixtures
```

`--offline` on any step replays the cache and forbids network access. Every step is
resumable; the raw cache lives in `research/science_002/data/cache/` and is
git-ignored.

## What is committed, and what is not

| committed | not committed |
|---|---|
| `artifacts/universe.csv` (48 firms), `entity_matches.csv` (189 links), `entity_exclusions.csv` (14) | the openFDA ZIPs (250 MB + 86 MB) |
| `artifacts/panel.csv` (2,771 rows, all features), `panel_summary.json` | the 62 SEC submissions documents |
| `artifacts/experiment_results.json`, `sensitivity_results.json`, `audit_results.json` | the 62 SEC companyfacts documents |
| `artifacts/source_manifest.json` - 204 URLs with SHA-256, bytes and collection time | |
| `artifacts/figures/*.png` + `figures_manifest.json` with input hashes | |
| `evidence/SOURCES.md` - captured quotes, byte sizes and hashes | |

Every non-committed byte has a committed URL and SHA-256, so any claim can be
re-derived by re-fetching.

## Science discipline enforced in code

* A cross-source match is never made from name *similarity*: only from exact
  equality of normalised token strings, at a named tier, with the evidence string
  stored. An applicant claimed by two registrants is dropped from both.
* A filing accepted after the prediction instant cannot enter a feature, and a
  clearance inside the outcome window cannot enter a historical count. Both are
  tested adversarially (`audit.py` A1/A2/A3/A6), not merely asserted.
* A forward window that is not fully observed is dropped, never labelled 0.
* The primary estimator has firm fixed effects, so it is identified from
  within-firm variation; a firm dummy cannot change a within-firm ranking. The
  pooled estimator is reported but never used for a claim.
* The permutation null is an exact conditional test within firm, not a
  shuffle-across-everything that would destroy the label structure.
* A null result is a result. The pre-registered decision rule returns NULL here,
  and the reasons the null is *interpretable* (positive controls pass) and *bounded*
  (the CI excludes improvements above +0.017 AUC) are reported with it.

## Files

| file | role |
|---|---|
| `PROTOCOL.md` | frozen design and analysis plan, committed before the reported run (commit `f5dad80`), including an honest account of what was already known at freeze time |
| `RESULTS.md` | every reported number, the controls, the power calculation |
| `AUDIT.md` | independent adversarial audit, including an executed future-filing injection test |
| `ENTITY_RESOLUTION.md` | the matching rules, the 189 accepted links, the 14 exclusions, and why 8.8% attribution coverage is the study's main measurement limit |
| `TIME_SEMANTICS.md` | what each timestamp can and cannot prove; why no lead time in days is claimed |
| `DATASET_CARD.md` | population, geometry, outcome distribution, limitations |
| `NEXT_STEPS.md` | what is worth doing next, in order |
| `evidence/SOURCES.md` | captured primary sources with hashes and quotes |
