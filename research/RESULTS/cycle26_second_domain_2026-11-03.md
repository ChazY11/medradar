# Cycle 26 — second-domain validation: the promotion rule survives a different recording process (2026-11-03)

**Status:** completed. Closes B-059. Pre-registered in D-052, outcome in D-053.
Artifacts: `experiments/b026/validate_hiring_domain.py`, `validate_hiring_domain.json`,
`inspect_hiring_lane.py`, `inspect_trial_lane.py`.

## Why a second domain, and how it was chosen

The rule had been confirmed twice — company cells and legal-entity cells — but both are the **same corpus and
the same recording process** (FDA premarket submissions). The obvious remaining threat is that the rule is a
property of that corpus.

Two candidate independent lanes were **measured before choosing**:

| lane | series available | cells meeting the unchanged floors |
|---|---|---|
| ClinicalTrials.gov device trials | 180 company-track cells | **5** |
| archived job postings (Internet Archive) | 13 company series | **8** |

The trial lane is too sparse to test anything. The hiring lane was used, and its size was declared as a power
limitation **before** the run.

## Result: CONSISTENT

8 of 13 hiring series met the floors (rates 2.9–98.2 postings per month), three fresh origins each, seed
9091, identical detector/classifier/shapes/3× elevation. **43 scored alerts.**

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (7) | 5 | 2 | 0 | 0.714 |
| level (17) | 0 | 13 | 4 | 0.765 |
| ramp (10) | 1 | 6 | 3 | 0.300 |

- balanced accuracy **0.593** (95 % CI 0.503–0.806), floor 0.50 → pass
- sustained-change precision **0.929** (95 % CI 0.872–1.000), floor 0.85 → pass
- sustained base rate **0.794**; precision interval above it
- bootstrap interval width **0.128**, below the declared 0.30 underpowered threshold

## What this buys, and what it does not

**Buys:** the rule is not a property of the FDA filing corpus alone. Applied to a web-archive posting-flow
series it shows the same qualitative behaviour — spike separated, sustained promoted, precision above base
rate. The programme may now say its one confirmed decision rule transfers **once** to a different recording
process.

**Does not buy:** not a second confirmation — 43 alerts against 494 and 1,196 in the registry runs, eight
series, one non-registry domain. Ramp recall 0.300 rests on ten cases and cannot be claimed different from
the registry's 0.117–0.142. No portability to a third domain, another resolution, or another country's
filings, and the policy's error rates remain the registry-measured ones.

## A detail worth keeping

The trial lane was inspected **first** and rejected on measured grounds. The domain choice was made by
feasibility data, not by picking the flattering option; both probe scripts are committed.

## Verification

- `python experiments/b026/validate_hiring_domain.py` → exit 0, deterministic (seed 9091).
- `python -m medradar selftest` → 882 tests OK (skipped=3).
- Probe scripts committed so the domain choice is reproducible.

## Next

1. Add the window analysis and this validation to the paper as a negative-with-diagnosis and a scoped
   positive.
2. Decide how promoted changes enter the results ledger (a promoted alert is not a finding).
3. Record sign-off identity in the snapshot manifest.
