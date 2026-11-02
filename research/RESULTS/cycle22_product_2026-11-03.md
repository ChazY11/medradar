# Cycle 22 — the validated detector is now in the product, with its provenance (2026-11-03)

**Status:** completed. Closes B-056. Decision: D-046.
Artifacts: `medradar/intelligence/profile.py` (deployment_alerts), `tests/test_profile.py` (44 tests),
`experiments/b027/profiles/*.md` regenerated, `experiments/b027/selfcheck.py` extended.

## What changed

Each profile's momentum field now carries a **`deployment_alerts`** block that applies the detector the
programme actually validated rather than a hand-picked rule:

- **3-month (quarterly) resolution**, memory 12 months, baseline 24 months (D-045);
- **rolling z-score, threshold 3.5** — the operating point that achieved a **0.018** false-alarm rate in the
  controlled-truth sweep, with measured sensitivity **0.147**;
- alerts reported for the **last 8 quarters** only, because a 2019 alert is not a live decision input;
- each alert lists track, quarter, events, baseline mean and z; the block states the measured false-alarm
  rate and sensitivity **inside the profile**.

The block is nested inside `momentum`, so the top-level contract is still the seven required fields and the
frozen historical snapshots stay verifiable as they were.

## What it looks like on real data

Medtronic now shows two live alerts — `coronary` 2026-Q3 and `insulin_delivery` 2025-Q3 — each **2 events
against a baseline of 0.25** (z = 3.5). Both are legitimate at the measured false-alarm rate and both are
substantively thin. That is what a 0.147-sensitivity detector at ~0.2 events per cell-month looks like, and
the profile prints the counts beside the alert so "calibrated" cannot be read as "substantial".

## Verification enforced by code

`selfcheck.py` now fails a profile if its deployment block names a detector or resolution other than the
validated one, if any alert fails to clear its own threshold, or if the Markdown omits the detector line or
the false-alarm rate. Profile tests grew **36 → 44**: resolution lock, provenance fields, steady-series
silence, burst flagging, recency window, empty history, Markdown statement.

## Deliberately not done

The **promotion rule** (D-043: two-month post-alert window, precision 0.914 vs 0.696 base rate) is **not wired
in automatically**. Promotion needs a live alert stream and an explicit decision; automating it would convert
a measured rule into an opaque default. It is recorded in `STATE.json` as an available, measured rule for the
Understand layer to invoke deliberately.

## Not claimed

That these alerts are technology changes; that a two-event alert is actionable alone; or that the quarterly
detector is the best possible — only that it is the one measured to be deployable at this resolution.

## Verification

- `python -m pytest tests/test_profile.py` → 44 tests pass.
- `python experiments/b027/selfcheck.py` → 5/5 focus profiles OK, **4/4 frozen snapshots OK**, exit 0.
- `python -m medradar selftest` → see commit; suite extended to 862 tests.
