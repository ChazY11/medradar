# Cycle 16 — point-in-time rebuild: three frozen historical snapshots, zero leakage (2026-11-03)

**Status:** completed. Creates and closes B-051. Decision: D-037.
Artifacts: `experiments/b027/snapshots/{2020-12-31,2022-12-31,2024-12-31}/`,
`experiments/b027/snapshot_diff.py`, `snapshot_diff.json`, `verdict_stability.py`,
`verdict_stability.json`.

## The leakage path found while implementing it

Cycle 14's builder claimed a window but read two inputs in full regardless of any as-of date: the
**trial lane** and the **product-code first-seen map**. A historical rebuild would therefore have
carried future evidence into a "point-in-time" profile. Fifth self-caught defect of the programme, and
the first that would have silently invalidated a point-in-time claim.

## The fix

`build_profiles.py --as-of D` now truncates regulatory events at `D`, ends the window at `month(D)`,
filters the trial lane at `D`, recomputes code first-seen from the truncated events only, and writes a
`leakage_audit` block per profile recording the latest regulatory event, latest trial event and latest
code first-seen that actually entered it.

## Three backdated snapshots, frozen and verified

| as-of | lane events used | window ends | detected momentum | profiles |
|---|---:|---|---:|---:|
| 2020-12-31 | 12,853 | 2020-12 | 5 | 53 |
| 2022-12-31 | 19,182 | 2022-12 | 5 | 53 |
| 2024-12-31 | 25,772 | 2024-12 | 1 | 53 |
| 2026-11-02 (cycle 14) | full lane | 2026-09 | 4 | 53 |

Each is written with a manifest (per-artifact and per-source SHA-256) and re-read for verification by
the freezer. `snapshot_diff.py` audits all four:

- **0 leakage problems** in the three auditable snapshots — every recorded latest event is on or before
  its as-of date and every window ends on or before the as-of month;
- the cycle-14 snapshot is reported **not auditable** (it predates the audit block), which is a
  different statement from *leaky* and is kept different.

## What the diffs show

| step | momentum verdict changes | track-set changes | roster events |
|---|---:|---:|---:|
| 2020-12-31 → 2022-12-31 | 8 | 21 | 1,797 → 2,503 |
| 2022-12-31 → 2024-12-31 | 5 | 21 | 2,503 → 3,235 |
| 2024-12-31 → 2026-11-02 | 7 | 16 | 3,235 → 3,928 |

Track changes are always entries, never drops: the lane accumulates, so a "dropped track" would be a
bug signal, and none appeared.

## Verdict stability across the chain

Of 53 companies present in all four snapshots: **40 stable, 13 change at least once, 2 reverse
outright**:

- `hologic`: no-change → decreasing → increasing → no-change
- `zimmer_biomet`: increasing → decreasing → no-change → no-change

A quarter of companies changing verdict with the as-of date is consistent with the calibrated test's
measured low power (MDEs 1.8×–22.9×), and it is the honest way to present a nowcast: the verdict is a
statement about this data at this date, not a property of the company.

## Why this matters

The objective asks for point-in-time datasets and rolling-origin benchmarks. This round makes a
profile's **provenance auditable to a date**: a future cycle can rebuild the 2022-12-31 view and verify
it against the frozen manifest, and prove no evidence after that date entered it. That is the
precondition for any honest rolling-origin evaluation of the Understand layer.

## Not claimed

That the 2022-12 verdicts were "right" or "wrong" — there is no ground truth for a technology position.
What is claimed is only that the pipeline is now cut at the date it says it is.

## Verification

- `python experiments/b027/snapshot_diff.py` → exit 0, 0 leakage problems, 3 diffs written.
- `python experiments/b027/verdict_stability.py` → exit 0.
- `python -m medradar selftest` → 854 tests OK (skipped=3).
- `freeze_snapshot.py` verifies each snapshot by re-reading it before reporting success.
