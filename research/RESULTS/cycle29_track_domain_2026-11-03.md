# Cycle 29 — third-unit validation: market-aggregate level, and a density scaling for ramps (2026-11-03)

**Status:** completed. Closes B-062. Pre-registered in D-056, outcome in D-057.
Artifacts: `experiments/b026/validate_track_domain.py`, `validate_track_domain.json`, `validate_track.log`.

## Why this unit

The rule had been tested on company cells, legal-entity cells and a second recording process (job postings) —
all **sparse** counting regimes. The untested threat was that the rule depends on sparsity. **Technology-track
aggregates** are the opposite regime: 38 tracks, all eligible, **median 270 events per track**, roughly a
thousand times denser per series than a company cell.

## Design (fixed before running)

Same detector (three-month rate ≥ twice the eighteen-month baseline), same classifier (two months after the
alert, alert month excluded), same shapes and 3× elevation, three fresh origins per track, seed 5150, tracks
resampled in the bootstrap. **297 scored alerts.**

## Result: CONSISTENT

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (92) | 67 | 17 | 8 | 0.728 |
| level (114) | 0 | 63 | 51 | 0.553 |
| ramp (91) | 5 | 50 | 36 | **0.396** |

- balanced accuracy **0.559** (95 % CI 0.514–0.605), floor 0.50 → pass
- sustained-change precision **0.889** (95 % CI 0.851–0.925), floor 0.85 → pass
- sustained base rate **0.690**; precision interval above it
- bootstrap interval width **0.074**

## The result beyond the verdict: ramp recoverability scales with density

| unit | series density | ramp recall |
|---|---:|---:|
| legal entity × track | ~0.05 events/series-month | 0.117 |
| company × track | ~0.2 | 0.142 |
| company job postings | 2.9–98 | 0.300 |
| technology track (aggregate) | ~2.3 | **0.396** |

This is the first coherent scaling relationship the programme has found: **ramp recoverability is a function of
how many events a series carries**, not of the classifier. It also explains, after the fact, why the
window-length sensitivity analysis (D-051) could not rescue ramps — sparse series do not contain the counts, and
a longer window cannot add information that is not there.

## Scope

**Buys:** the promotion rule holds across three units, a ~1000× density range and two recording processes.
That is materially stronger than the two-unit confirmation at D-048.

**Does not buy:** portability to another taxonomy, corpus or country; a claim that market-aggregate alerts are
the right decision unit; and the ramp scaling is a **cross-unit observational gradient**, not a controlled
experiment — density and unit type vary together. A controlled test would hold the unit fixed and vary density
artificially; this run did not.

**Policy unchanged:** the deployed detector and two-month window stay as fixed in D-045/D-049. This run
validates them elsewhere; it does not re-tune them.

## Verification

- `python experiments/b026/validate_track_domain.py` → exit 0, 1.4 s, deterministic (seed 5150).
- `python -m medradar selftest` → 889 tests OK (skipped=3).
- `python tools/audit_objectives.py` → expected to remain 11 PASS / 0 FAIL / 1 N/A.

## Next

1. Add the third-unit result and the density scaling to the paper (with the observational caveat).
2. Third domain only if a genuinely different one exists; the density dimension is now covered.
3. Test the density hypothesis directly by down-sampling a dense track series to sparse counts and re-running
   the classifier — that would convert the gradient from observational to experimental.
