# Cycle 14 — full-roster profiles, a hash-verified snapshot, and what calibration bought (2026-11-03)

**Status:** completed. Closes B-049. Decision: D-034.
Artifacts: `medradar/intelligence/snapshot.py` (+23 tests), `tests/test_snapshot.py`,
`experiments/b027/freeze_snapshot.py`, `experiments/b027/snapshots/2026-11-02/`,
`experiments/b027/calibration_report.py`, `experiments/b027/momentum_calibration.json`.

## What was shipped

1. **Full-roster profiles — 53 companies.** The 51-company device roster plus the two mandated focus
   firms missing from it (Dräger, Mindray). `build_profiles.py --scope roster`.
2. **A frozen, verifiable snapshot** at `snapshots/2026-11-02/`: profiles, summary, one Markdown per
   company, and a manifest recording a SHA-256 per artifact, a SHA-256 per input source (lane DB,
   trial DB, three configs), the as-of date, the window and a manifest hash. The freezer re-reads its
   own output and verifies before reporting success.
3. **Snapshot verification in the self-check**: manifest hashes, summary/profile agreement, frozen
   Markdown reproducing exactly from JSON, as-of matching the directory name.

## What calibration bought, measured on all 53 companies

| rule | companies flagged |
|---|---:|
| naive rate-ratio rule used in cycle 12 (ratio ≥ 1.25 or ≤ 0.80) | **35 / 53** |
| exact binomial test at α = 0.05 (current) | **4 / 53** |

The four that survive:

| company | last 24 m | prior 24 m | ratio | p | MDE (80 %) |
|---|---:|---:|---:|---:|---:|
| Olympus | 50 | 12 | 4.17 | <0.0001 | 2.46× |
| Philips | 73 | 36 | 2.03 | 0.0005 | 1.77× |
| Steris | 18 | 36 | 0.50 | 0.020 | 2.25× |
| Medline | 11 | 25 | 0.44 | 0.029 | 2.76× |

**31 of the 35 naive flags are unsupported.** The instructive failures: iRhythm ratio 4.00 = 4 vs 1
events (p = 0.375, MDE 22.93×); ICU Medical ratio 2.25 = 9 vs 4 (p = 0.267, MDE 5.38×); Dentsply
Sirona ratio 2.09 = 23 vs 11 (p = 0.058, just short). A ratio rule would have published all of them
as "momentum".

## What this licenses, and what it does not

**Licensed:** per company, whether public filing activity changed over the last 24 months relative to
the 24 before, at a stated α, with the minimum detectable ratio reported whenever it did not.

**Not licensed:** ranking companies by "innovation". The MDEs range from 1.77× to 22.93×, so a
non-detection by a low-count firm means something very different from a non-detection by a high-count
one. The per-profile MDE is precisely what prevents that misreading.

## Why the snapshot matters

A point-in-time artifact is the precondition for any rolling-origin evaluation: without a frozen,
source-hashed record of what the system believed on a date, later "predictions" cannot be audited for
look-ahead. This snapshot is dated, hashed and self-verifying, so a future cycle can prove what this
one knew.

## Verification

- `tests/test_snapshot.py` — 23 tests (canonical JSON, hash stability, manifest construction,
  tamper detection, missing/extra artifacts, manifest-hash tampering, source-hash requirement).
- `experiments/b027/selfcheck.py` — 5/5 focus profiles plus **snapshot 2026-11-02 OK (53 companies,
  manifest 31af25c989f2…)**, all exit 0.
- `python -m medradar selftest` — 854 tests OK (skipped=3).

## Next

1. Wire the cycle-3c **detection frontier** into the per-track change field, so per-track "change" is
   calibrated against the controlled-truth benchmark rather than only a rate test.
2. Freeze a **second** snapshot at the next as-of date and diff the two — that is the first genuinely
   point-in-time comparison the programme can make.
3. B-039 deployment-resolution fix.
