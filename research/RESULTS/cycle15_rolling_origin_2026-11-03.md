# Cycle 15 — the first rolling-origin benchmark: a null, and a design flaw caught inside it (2026-11-03)

**Status:** completed. Closes B-050. Decisions: D-035 (pre-registration), D-036 (outcome).
Evidence: `experiments/b050/rolling_origin.json`, `experiments/b050/rolling_origin.log`.

## What was built

The objective names **rolling-origin benchmarks** and the programme had none. This is the first:

- **376** (curated company, technology track) cells;
- **12 origins**, every six months from 2019-12 to 2025-06;
- **717** company-origin-cell observations;
- at each origin the signal uses **only events up to that month**; the outcome is the following 12
  months; company-clustered bootstrap (2,000 reps) because cells within a company are not independent.

## The pre-registered result — and why it cannot be read at face value

| predictor | flags | P(outcome\|flag) | P(outcome\|no flag) | lift | 95 % CI |
|---|---:|---:|---:|---:|---|
| calibrated increase | 5 | 0.00 | 0.41 | 0.00 | [0.00, 0.00] |
| naive increase (ratio ≥ 1.25) | 149 | 0.22 | 0.46 | 0.49 | [0.32, 0.66] |
| persistence increase | 173 | 0.21 | 0.47 | 0.46 | [0.31, 0.61] |
| naive decrease | 434 | 0.32 | 0.63 | 0.50 | [0.40, 0.61] |

Taken at face value this says extrapolation is **anti-predictive** with tight intervals. It is wrong,
and the design is why: the outcome compares the future block with the **recent** block, and a cell is
flagged precisely because its recent block is high. At a constant rate the next block is mechanically
lower. **Regression to the mean is built into the numerator.**

## The declared post-hoc correction

Comparing the same future block with the cell's **long-run rate** up to the origin removes that
dependence:

| predictor (vs long-run baseline) | flags | P(outcome\|flag) | P(outcome\|no flag) | lift | 95 % CI |
|---|---:|---:|---:|---:|---|
| calibrated increase | 5 | 0.20 | 0.33 | 0.60 | [0.00, 2.08] |
| naive increase | 149 | 0.39 | 0.32 | **1.22** | [0.95, 1.53] |
| persistence increase | 173 | 0.38 | 0.32 | 1.20 | [0.94, 1.49] |
| calibrated decrease | 16 | 0.88 | 0.65 | 1.35 | [0.90, 1.57] |
| naive decrease | 434 | 0.67 | 0.63 | 1.06 | [0.92, 1.23] |

**The sign flips**: naive increase goes from 0.49 to 1.22 once the baseline is fixed. The pre-registered
negative lift was the bias, not a finding.

## Verdict

1. **No predictor's 95 % interval excludes 1.** There is no evidence that a change signal predicts
   12-month-ahead activity above the cell's long-run rate.
2. The naive-increase point estimate (1.22, CI 0.95–1.53) is a hint, not a result — and it belongs to
   the raw ratio rule that cycle 13 dismantled, not to the calibrated signal.
3. **The calibrated signal is too rare to predict with**: 5 flags in 717 observations. Calibration made
   momentum honest and, in the same move, too sparse to trigger on. That is a property of ~0.2 events
   per cell-month.

## What this licenses

A statement about the predictability of **public filing activity** at this granularity: no detectable
12-month-ahead predictability above baseline, with intervals reported. It is **not** a claim that
corporate technological evolution is unpredictable — the data cannot see far enough, and the observation
is about filing rates, not technology.

## Design lesson

**A benchmark outcome must not be defined relative to the same window that triggered the signal.** This
is the programme's fourth self-caught design flaw (entry denominator → post-hoc nomination → collector
pagination → benchmark numerator), and the first one caught *inside a benchmark* before it became a
finding.

## Verification

- `python experiments/b050/rolling_origin.py` → PASS, exit 0, 5 s; artifact written and re-runnable.
- `python -m medradar selftest` → see the round's commit; no library change this cycle beyond the
  benchmark script.
