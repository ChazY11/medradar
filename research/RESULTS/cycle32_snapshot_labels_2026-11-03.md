# Cycle 32 — labelled snapshots and a promotion-label diff (2026-11-03)

**Status:** completed. Closes B-065. Decision: D-062.
Artifacts: `experiments/b027/snapshots/2026-11-03-policy-v2/`, `experiments/b027/snapshot_diff.json`,
`experiments/b027/freeze_snapshot.py` (`--label`), `experiments/b027/snapshot_diff.py` (promotion diff).

## The problem this fixes

D-061 changed the promotion policy to v2, which relabels some alerts from `ramp` to `sustained_unresolved`. A
point-in-time chain that cannot show **which claims a policy change altered** is only half a record: a reader
comparing two snapshots would see identical data, zero momentum changes and zero track changes, and could
reasonably conclude nothing happened.

## What was built

1. **Labelled snapshots.** `freeze_snapshot.py --label` permits a second snapshot at the same as-of
   (`2026-11-03-policy-v2`). The manifest records the true as-of; the directory carries the suffix; the
   self-check and the diff accept `as-of` or `as-of-<label>`, and the leakage audit uses the manifest's as-of.
2. **A promotion-label diff.** `snapshot_diff.py` compares, per alert, the triple (verdict, shape, policy
   version) and records every change.
3. **The sixth auditable snapshot**, `2026-11-03-policy-v2`, frozen and verified (manifest `44abde16…`), which
   also hashes the promotion ledger so its labels are tied to the signed ledger at that moment.

## What the diff shows

Data-level: **identical** — 3,928 events, 0 momentum changes, 0 track changes.

Label-level: **32 alerts changed**, of which **8 changed shape** from `ramp` to `sustained_unresolved` — exactly
the claims the density finding disqualified. Examples:

| alert | before | after |
|---|---|---|
| `medtronic \| insulin_delivery \| 2025-Q3` | promote_pending_signoff / **ramp** / v1 | promote_pending_signoff / **sustained_unresolved** / v2 |
| `johnson_johnson_medtech \| medical_ai \| 2026-Q1` | promote_pending_signoff / **ramp** / v1 | promote_pending_signoff / **sustained_unresolved** / v2 |
| `abbott \| ivd_immuno \| 2026-Q2` | promote_pending_signoff / level / v1 | promote_pending_signoff / level / v2 |
| `medtronic \| coronary \| 2026-Q3` | reject / unknown / v1 | reject / unknown / v2 |

Both readings are correct and only reporting one would mislead. The record can now answer a question that
previously had no artefact: **what did the policy change alter, and what did it leave alone?**

## What is not claimed

That the relabelled alerts are now *wrong* — the binary promotion verdict is unchanged
(`promote_pending_signoff` for all eight); only the shape label was withdrawn. Nor that the 1.0-event-per-month
floor is optimal: D-061 already states it is a conservative point on a measured curve.

## Verification

- `snapshot_diff.py` → exit 0, **0 leakage problems across 6 auditable snapshots**, 5 consecutive diffs written.
- `selfcheck.py` → 5/5 profiles OK, **6/6 snapshots OK** (including the labelled one).
- `python -m medradar selftest` → 892 tests OK (skipped=3).
- Audit expected to remain 11 PASS / 0 FAIL / 1 N/A.

## Next

1. Wire the audit into the round-end routine so every round reports it.
2. Consider a second paper focused on the measurement rules and the density confirmation.
3. Review whether the promotion ledger should record the relabelling events as an audit trail.
