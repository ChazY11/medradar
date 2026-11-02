# Cycle 35 — a frozen prospective forecast set, and the 7 forecasts that do not count (2026-11-03)

**Status:** completed. Closes B-068. Decision: D-066.
Artifacts: `medradar/intelligence/forecasts.py` (+18 tests), `research/forecasts/FORECAST_SET_2026-11-03.json`,
`experiments/b068/register_forecasts.py`, `experiments/b068/maturate_forecasts.py`,
`experiments/b068/maturation.json`.

## What was built

- **Pure forecast module** with quarter arithmetic, fixed windows, registration, validation and scoring (Brier,
  log loss, accuracy, per-decision breakdown); pending forecasts are always reported so a partially matured set can
  never be summarised as complete.
- **A frozen set of 32 forecasts**, one per alert in the policy-v2 snapshot: 17 promoted (probability 0.800 that
  activity persists) and 15 not promoted (0.667). Those probabilities are the **measured end-to-end pipeline rates**
  (D-065), not guesses. The set is content-hashed (`d236b83f…`) and records the source snapshot's manifest hash.
- **A scorer that refuses to run on a modified set**: it recomputes the content hash and aborts on mismatch, so the
  predictions cannot be edited after outcomes arrive.

## The defect I found in my own registration

Because the snapshot's alerts include quarters whose outcome windows are **already observed**, **7 of the 32
forecasts matured immediately at registration**. A forecast registered after its outcome is known is not a
forecast — it is a backfilled label. Those 7 are reported separately and **excluded from prospective evidence**:

| group | matured | mean predicted p | observed persistence |
|---|---:|---:|---:|
| promoted | 4 | 0.800 | 0.500 |
| not promoted | 3 | 0.667 | 0.333 |
| overall | 7 | — | **Brier 0.337**, accuracy 0.429, log loss 0.896 |

The accuracy equals the majority-class base rate in that subsample: the forecasts carry **no discernible
information** there. That is consistent with D-065's end-to-end null and with the tiny sample — a sanity check that
failed to reassure, not evidence about the model.

## What is genuinely prospective

**25 forecasts**, maturing between **2026-Q4 and 2028-Q1**. They are the only ones that can count as prospective
evidence, and they are frozen: any edit breaks the hash and the scorer refuses to run.

**Rule now recorded:** a forecast set may only be registered from alerts whose outcome window is entirely in the
future at registration time; registration scripts must filter on that and report backfilled alerts separately. This
set predates the rule and is annotated as such.

## Verification

- `pytest tests/test_forecasts.py` → **18 passed**.
- `register_forecasts.py` → 32 registered, hash `d236b83f…`, earliest maturation 2026-Q2 (the backfilled tail).
- `maturate_forecasts.py` → hash verified, 7 resolved / 25 pending, exit 0.
- `python tools/round_end.py` → gate run for this round.

## Next

1. Re-register a **clean prospective set** using only future-maturing alerts, so the prospective count is honest.
2. Use `round_end.py` as the gate every round.
3. Consider a second paper focused on the measurement rules and the two confirmations.
