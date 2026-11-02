# Cycle 30 — controlled density test: strong trend, pre-declared bar not cleared (2026-11-03)

**Status:** completed. Closes B-063. **Negative against its own pre-registered criterion**; opens B-064.
Pre-registered in D-058, outcome in D-059.
Artifacts: `experiments/b026/density_experiment.py`, `density_experiment.json`, `density_experiment.log`.

## Why this test

D-057 found ramp recall rising with series density across units (0.117 entity → 0.142 company → 0.300 hiring →
0.396 track). That is **observational**: density and unit type vary together. Holding the unit fixed and varying
density artificially is the only way to separate them.

## Design (fixed before running)

The 38 dense track series, thinned by **binomial down-sampling** at τ ∈ {1, 2, 5, 10, 20}, then the same
shapes, detector and classifier. Seed 6161; three origins per track per factor.

## Result

| τ | density (events/series-month) | ramp recall | 95 % CI | sustained precision |
|---:|---:|---:|---|---:|
| 1 | 4.16 | **0.440** | 0.333–0.556 | 0.926 |
| 2 | 2.08 | 0.415 | 0.295–0.532 | 0.889 |
| 5 | 0.84 | 0.300 | 0.200–0.407 | 0.927 |
| 10 | 0.43 | 0.318 | 0.182–0.456 | 0.893 |
| 20 | 0.21 | **0.222** | 0.106–0.356 | 0.885 |

## Verdict as pre-registered: NOT SUPPORTED

- Spearman ρ = **0.882** (floor 0.8) → **pass**
- **strict monotonicity fails** by one inversion: τ = 5 (0.300) is 0.018 below τ = 10 (0.318)
- **interval separation fails** by a 0.023 overlap between the dense interval's lower bound and the sparse
  interval's upper bound

Two of three criteria fail, so by the rule fixed in D-058 the density scaling is **not established as a density
effect**. This is the reported result and it is not revised after the fact.

## "Not supported" is not "disconfirmed"

The point estimate **halves** (0.440 → 0.222) as density falls twentyfold, ρ = 0.88, and precision is stable
across every factor (0.885–0.927). The failures are narrow: a 0.018 inversion between adjacent factors whose
intervals almost entirely overlap, and a 0.023 edge overlap. What the experiment shows is that the **effect size
is large and directionally consistent while the evidence cannot certify strict monotonicity** with 50–100 ramp
cases per factor.

## The pre-registration's own flaw

Requiring *strict* monotonicity across five noisy point estimates is a brittle gate — a single 0.018 wobble voids
the claim even at ρ = 0.88. Recorded as a defect of **my** pre-registration, not of the data.

## Consequence, and what happens next

- **Paper:** the scaling must be presented as *suggestive*, not established.
- **Product:** the profile keeps its per-unit measured limits; no density threshold is introduced.
- **Policy:** no detector, window or promotion rule changes on a result that failed its own bar.
- **B-064:** a revised criterion (rank correlation ≥ 0.8 **and** dense ramp recall ≥ 2× sparse, no strict
  monotonicity clause) will be pre-registered and confirmed on **fresh seeds and a fresh thinning draw**.

## Verification

- `python experiments/b026/density_experiment.py` → exit 0, 2.8 s, deterministic (seed 6161).
- `python -m medradar selftest` → 889 tests OK (skipped=3).
- Audit expected to remain 11 PASS / 0 FAIL / 1 N/A.
