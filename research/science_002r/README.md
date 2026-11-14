# SCIENCE-002R - independent audit of SCIENCE-002

**Subject.** PR #42, `research/science_002/`, commit
`a3c3516fc3395117763e28dd029c214fb7d3d0ee`.
**Audit branch.** `audit/science-002r-independent-review` (from the PR head, not
from main).

## Verdict

**REVISE BEFORE MERGE.** The NULL survives every attack that was executed, but the
study as committed has one methodological defect (universe inclusion decided by
post-training FDA events), four numeric inconsistencies in its own documents, and one
over-read precision claim. All are fixable; after the fixes the result is a valid
exploratory null. Nothing found justifies NO-GO.

| | |
|---|---|
| primary statistic reproduced | **-0.033663969385031994** (exact) |
| artifacts reproduced byte-for-byte | **10 / 10** |
| future-information leaks found | **0** (three executed injections) |
| double-attributed clearances | **0** of 8,176 k_numbers |
| documentation mismatches found | **4** (F2; all corrected in ERRATA.md) |
| selection-bias effect | delta -0.034 -> **-0.011** under pre-panel eligibility, verdict unchanged |
| SCIENCE-003 readiness | **not ready** - the proposed establishment-number fix does not exist in the data (F8) |

## The five findings that matter

1. **F1 - the sample is chosen using the future.** Eligibility uses clearances through
   2026-08-31. 17 of 48 firms would not qualify under a pre-panel rule; PROCEPT
   BioRobotics and Hyperfine have **zero** pre-2021 clearances. Rebuilding with
   pre-panel eligibility: 31 firms, prevalence 0.649, delta -0.011 (p = 0.63). The
   verdict is unchanged; the sample description is not. `SELECTION_BIAS.md`
2. **F2 - four numbers do not reconcile.** 78 vs 217 rows dropped; 48 vs 46 firms
   with rows; 15 vs 13 single-class holdout firms; 189 vs 148 links. `ERRATA.md`
3. **F3 - the interval was read as proof.** '+0.017 can be excluded at 95%' does not
   survive an independent jackknife (upper bound +0.032). `STATISTICAL_REVIEW.md`
4. **F4 - '8.8% coverage' is not recall.** It is the 48 firms' share of all FDA
   filings; recall is **unknown**; 167 unattributed brand-token applicants (444
   clearances) show visible blind spots. `ENTITY_AUDIT.md`
5. **F8 - the planned SCIENCE-003 fix does not exist.** The 510(k) establishment
   identifiers are product-code aggregates (median 104 registrations per record; one
   set shared by 1,104 applicants), not filing-level links. `SCIENCE003_READINESS.md`

## What was attacked, and held

| attack | method | result |
|---|---|---|
| future SEC filing entering a feature | injected an 8-K accepted 59 s after t (30 rows) | 0 changes |
| XBRL restatement backfilled into history | injected a later-filed restatement (40 rows) | 0 changes |
| outcome window bleeding into features | recomputed on all 2,554 complete-case rows | 0 violations |
| dependence ignored by the permutation | three-month block shift, 2,000 draws | p 0.223 (vs 0.094) |
| dependence ignored entirely | non-overlapping quarterly rebuild | delta +0.012, p 0.79 |
| bootstrap unreliable at 31 clusters | independent leave-one-firm-out jackknife | SE 0.034, CI [-0.100, +0.032] |
| artifacts not reproducible | fresh worktree, offline replay | 10/10 identical |
| attribution double counting | 148 links, 8,176 k_numbers | 0 shared |
| attribution contradicting FDA | check every link against the owner/operator file | 1 conflict (an acquisition) |

## Files

| file | content |
|---|---|
| `AUDIT_PLAN.md` | hypotheses and pre-declared decision rules, fixed before the experiments |
| `FINDINGS.md` | every defect, with severity and effect on the verdict |
| `SELECTION_BIAS.md` | the future-driven eligibility analysis |
| `STATISTICAL_REVIEW.md` | AUC, permutation, dependence, bootstrap, interval, power |
| `ENTITY_AUDIT.md` | coverage redefinition, tier audit, establishment-field result |
| `REPRODUCIBILITY.md` | the byte-level replay |
| `ERRATA.md` | every correction applied, and its effect |
| `SCIENCE003_READINESS.md` | what the next phase would need, and why it is not ready |
| `selection.py` `stats_review.py` `entity_audit.py` `internal_consistency.py` `establishments.py` | the executed analyses |
| `artifacts/*.json` | every number quoted, with its inputs |
| `tests/test_science_002r.py` | 11 offline unit tests for the audit's own logic |

## Reproduce

```
$env:MEDRADAR_S2_CACHE = "<path to science_002/data/cache>"   # the cache from PR #42's run
python -m research.science_002r.run consistency    # ~10 s, recomputes every reported number
python -m research.science_002r.run stats          # ~6 min, writes stats_review.json
python -m research.science_002r.run entity         # ~2 min, writes entity_audit.json
python -m research.science_002r.run selection      # ~10 min, three full experiment runs
python -m pytest tests/test_science_002r.py -q     # offline, synthetic fixtures
```

The audit never downloads: it reads the raw cache produced by the original run, whose
byte identities are committed in `research/science_002/artifacts/source_manifest.json`.

## Immutability

* No file in `research/science_002/artifacts/` was modified, and `PROTOCOL.md` was
  not edited (it is a frozen pre-registration).
* The only edits inside `research/science_002/` are documentation corrections listed
  in `ERRATA.md`, each marked where it appears and each leaving every computed number
  untouched.
* The audit code imports the frozen modules rather than editing them, so a reader can
  diff this branch against the PR head and see only additions plus the errata.

## Recommendation on PR #42

**Do not merge as-is; merge after applying the errata and adding the selection
disclosure.** Concretely:

1. apply ERRATA E1-E6 and E8 (documentation corrections; this branch already contains
   them and can be cherry-picked),
2. add the F1 disclosure to RESULTS/DATASET_CARD (already in this branch),
3. keep the NULL verdict and the frozen artifacts unchanged,
4. do not adopt the SCIENCE-003 plan until the clearance-letter pilot in
   SCIENCE003_READINESS.md section 5 has run.
