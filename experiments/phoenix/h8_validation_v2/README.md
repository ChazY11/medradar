# PHOENIX-002 — adversarial re-validation of the H8 "growth features" result

This directory contains the PHOENIX-002 study: an independent methodology audit of
PHOENIX-001 and a stricter re-run of its one positive predictive result (H8), designed to
**try to refute it**. It does not modify any PHOENIX-001 file and does not write to the
database.

Read first:

- frozen protocol: [`docs/phoenix/PHOENIX_002_PROTOCOL.md`](../../../docs/phoenix/PHOENIX_002_PROTOCOL.md)
- methodology audit: [`docs/phoenix/PHOENIX_002_METHOD_AUDIT.md`](../../../docs/phoenix/PHOENIX_002_METHOD_AUDIT.md)
- results: [`docs/phoenix/PHOENIX_002_H8_RESULTS.md`](../../../docs/phoenix/PHOENIX_002_H8_RESULTS.md)
- conclusion & next steps: [`docs/phoenix/PHOENIX_002_CONCLUSION_AND_NEXT_STEPS.md`](../../../docs/phoenix/PHOENIX_002_CONCLUSION_AND_NEXT_STEPS.md)

## Reproduce (CPU only, no network, no new packages)

Run from the repository root. The system Python needs pandas, numpy, scipy, scikit-learn
(the versions used are recorded in every result JSON).

```bash
cd experiments/phoenix/h8_validation_v2

# 1) unit tests / self-checks (40 checks, ~40 s)
python selftest.py

# 2) Experiment 1 — clean-cache end-to-end reproduction of PHOENIX-001 with its own frozen code
python exp1_v1_replication.py          # ~150 s

# 3) Experiments 2-6 + the pre-registered adversarial battery (~10-12 min)
python run_phoenix002.py

# 4) exploratory mechanism probes used in the report (not part of the frozen gates)
python exp_extra_mechanism.py          # ~3 min
```

## Files

| file | role |
|---|---|
| `protocol.py` | machine-readable frozen protocol (constants, maturity/risk-set rules, gates) |
| `data.py` | independent read-only panel builder, labels Y1–Y4, PIT eligibility, coverage/duplicate diagnostics |
| `features.py` | B1 persistence features and the 7 H8 growth features (same definitions as PHOENIX-001) |
| `arms.py` | the 8 model arms (incidence, persistence, MA/level, trend, H8, regularised full, HGB, mean-reversion) |
| `metrics.py` | AP, clustered bootstrap, paired contrasts, alert budget, Holm |
| `runner.py` | walk-forward folds + maturity audit + out-of-fold scoring + placebos |
| `run_phoenix002.py` | experiments 2–6, adversarial battery, mechanical verdict, `summary.json` |
| `exp1_v1_replication.py` | runs the frozen PHOENIX-001 code with redirected output dirs, compares to published |
| `exp_extra_mechanism.py` | denominator-free targets (Y5/Y6) and H8 feature-block decomposition (exploratory) |
| `selftest.py` | 40 assertions, including exact panel/label equality against the v1 cache and the maturity assertion |
| `audits/` | the three independent audit scripts + findings (`A_FINDINGS.md`, `B_FINDINGS.md`, `C_FINDINGS.md`) |
| `verify/` | independent verification of the headline numbers from saved OOF predictions |
| `results/` | one JSON per experiment, `summary.json` (verdict), `oof_*.csv` (out-of-fold scores for independent recomputation) |
| `evidence/` | real stdout logs for every run |

## Guardrails that are actually enforced in code

- database hash re-verified on every run; mismatch aborts (`data.verify_db`);
- raw data read with `mode=ro&immutable=1`;
- the panel builder is checked against the frozen PHOENIX-001 panel in `selftest.py`
  (identical labels and counts, 0 mismatching rows);
- every fold's training origins satisfy
  `label_observable_quarter(q_train) <= test_first_quarter - 1` (`maturity_audit`, asserted in selftest);
- every arm is fitted on the same training rows and scored on the same test rows;
- paired contrasts use identical rows and identical bootstrap resamples for both arms;
- no outcome-dependent choice is made after seeing a result (see protocol §8/§10).
