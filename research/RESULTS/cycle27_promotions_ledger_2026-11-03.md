# Cycle 27 — promotions get their own ledger, and a promotion is not a finding (2026-11-03)

**Status:** completed. Closes B-060. Decision: D-054.
Artifacts: `research/RESULTS/PROMOTIONS.md`, `experiments/b027/log_promotion.py`,
`medradar/intelligence/promotion.py` (record builder), `tests/test_promotion.py` (25 tests),
`experiments/b027/freeze_snapshot.py` (ledger hashed in manifests).

## The accounting problem

The results ledger records findings. A promoted alert is **not** a finding: it is an operational decision that
one alert's change persisted under a measured rule. Mixing the two would let the programme inflate its record
with its own outputs — the failure mode every retraction in this project was about, one level up.

## What was built

1. **A separate append-only ledger**, `research/RESULTS/PROMOTIONS.md`, written only by
   `log_promotion.py`. Each row: promotion id, company, track, alert quarter, shape, relative post rate, policy
   version, verdict, **signer**, timestamp, justification. A one-line header states that these are promotion
   decisions, not findings.
2. **Sign-off enforced, not requested.** `build_promotion_record` raises on an empty signer, missing
   justification, missing timestamp, or a non-promotable verdict. The logger therefore cannot write an
   unattributed promotion.
3. **Attribution reaches the snapshot.** `freeze_snapshot.py` now hashes the promotion ledger as an input
   source, so every future manifest ties its profiles to the exact ledger it was built with (7 sources now).
4. **The results ledger states the rule**: nothing in `README.md` may cite a promotion as evidence.

## The first entry, and why it is unsigned

The Medtronic `insulin_delivery` 2025-Q3 alert is recorded as **PENDING_SIGNOFF**. The logger was run without a
signer and refused, printing the pending row:

```
| medtronic:insulin_delivery:2025-Q3 | medtronic | insulin_delivery | 2025-Q3 | ramp | 6.0 |
| promotion_policy_v1 | PENDING_SIGNOFF | — | — | — |
```

That is the correct state for an autonomous session: the programme can prepare a promotion but **cannot sign
one for a human**. Inventing a signer would defeat the mechanism the ledger exists to provide.

## Verification

- `pytest tests/test_promotion.py` → **25 passed** (7 new ledger tests: signer, justification, timestamp,
  non-promotable verdict, column order, statement).
- `log_promotion.py` without a signer → exit 2 and a pending row (expected).
- Freezer verified to hash 7 sources including the ledger.
- `python -m medradar selftest` → 889 tests OK (skipped=3).

## What this does not do

It does not make promotions correct — the measured precision (0.914–0.929) means roughly one promotion in
twelve is expected to be a miss. It makes them **attributable and separable from findings**, which is what the
auditing requirement needs.

## Next

1. Add a reviewer checklist to the promotion ledger (what evidence a signer must inspect).
2. Extend the profile's limits field with the promotion policy version so a profile states which policy
   governed its alerts.
3. A third domain only if ≥15 eligible series exist at these floors.
