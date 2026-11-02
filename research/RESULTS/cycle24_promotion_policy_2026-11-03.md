# Cycle 24 — promotion policy as code, and a sixth frozen snapshot (2026-11-03)

**Status:** completed. Closes B-057. Decision: D-049.
Artifacts: `medradar/intelligence/promotion.py`, `tests/test_promotion.py` (18 tests),
`research/PREDICTION_PROTOCOL.md` §8, `experiments/b027/snapshots/2026-11-03/`.

## Why a policy at all

The programme has one confirmed rule (D-043, replicated at the entity unit in D-048) and a deployed detector
(D-045), but nothing stated **when a detected change may be called a technology change**. Leaving that to
prose would repeat the failure mode this programme keeps catching: a claim that lives in a methods note and
gets upgraded in a slide.

## The policy, as code

`decide_promotion` gates an alert through four conditions and can return only two verdicts:

1. **Calibrated alert** — validated detector provenance (rolling z-score, 3-month bins, threshold 3.5) and
   the alert clears its own threshold;
2. **Confirmation window** — the two quarters after the alert, never including it, must classify as
   sustained under the confirmed rule;
3. **Contradiction check** — the profile's checks-run record must exist (the schema already forbids its
   absence);
4. **Human sign-off** — `requires_signoff: True` on every decision; the policy sets
   `automated_promotion_allowed: False`, and a test asserts no third verdict can be produced.

Every decision ships the sentence *"promotion marks a sustained change in PUBLIC FILING RATE; it is not
evidence of intent, capability, internal R&D or technological significance"*.

## What it does on the frozen data

| alert | verdict | why |
|---|---|---|
| Medtronic `coronary` 2026-Q3 | **reject** | no confirmation quarters exist yet |
| Medtronic `insulin_delivery` 2025-Q3 | **promote_pending_signoff** | ramp: elevated and still rising |

Both appear in the profile with the sign-off requirement and the filing-rate statement attached.

## Sixth frozen snapshot

`snapshots/2026-11-03` frozen and verified (manifest `5b7062d2…`), now carrying the deployment block and
promotion verdicts. Diff against `2026-11-02`: **identical data** — 3,928 events, 0 momentum changes, 0 track
changes. That is the correct reading: what changed between snapshots is **knowledge about the data**, not the
data. The four earlier snapshots remain verifiable as frozen; none was rewritten.

## Verification

- `pytest tests/test_promotion.py` → 18 passed; `tests/test_profile.py` → 44 passed.
- `selfcheck.py` → 5/5 profiles OK, **5/5 snapshots OK**, exit 0. It now fails a profile whose alert lacks a
  promotion decision, whose verdict is outside the allowed pair, whose `requires_signoff` is not true, whose
  statement lacks the filing-rate wording, or whose Markdown omits the verdict.
- `snapshot_diff.py` → 0 leakage problems across all five auditable snapshots.
- `python -m medradar selftest` → 880 tests OK (skipped=3).

## Not claimed

That a promoted change is technological; that the gate is adequate for another corpus, resolution or
regulatory lane.

## Next

1. Second-domain validation before any portability claim.
2. Decide how promoted changes enter the paper's results ledger (a promoted alert is not a finding).
3. Consider a longer confirmation window for ramps and report the precision/recall trade-off.
