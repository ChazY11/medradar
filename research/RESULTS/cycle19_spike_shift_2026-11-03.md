# Cycle 19 — can an alert's shape be recovered? Pre-registered failure, post-hoc success (2026-11-03)

**Status:** completed. Closes B-026; opens B-054 for confirmation. Decision: D-041.
Artifacts: `experiments/b026/spike_vs_shift.py`, `spike_vs_shift.json`, `spike_vs_shift.log`.

## Why this task

An alert that cannot be classified is half useless: a one-month burst and a genuine level shift demand
different responses. B-026 asked whether the **shape** of a detected change can be recovered from a short
confirmation window, with accuracy measured against **known injected shapes**.

## Design

171 injections of spike / level / ramp into real (company, track) series from **65 cells** with a
measurable baseline. A fixed detector (three-month rate ≥ twice the eighteen-month baseline) produced
**151 alerts** (88 %). A pre-registered rule then classified each alert from the alert month plus two
confirmation months. Company-clustered bootstrap, 2,000 replications.

## Pre-registered result: failure by its own criterion

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (41) | 7 | 34 | 0 | **0.171** |
| level (57) | 0 | 49 | 8 | 0.860 |
| ramp (53) | 0 | 45 | 8 | 0.151 |

Balanced accuracy **0.394** (95 % CI 0.361–0.438) against the 0.333 chance line; sustained-change
precision **0.764** against a **0.728** base rate. The always-"level" reference scores 0.333 / 0.728, so
the rule was barely better than a constant answer.

## Diagnosis and the declared post-hoc variant

The pre-registered window started at the alert month, which for a spike *is* the pulse: the burst inflated
the "post-alert" rate and the rule almost never called a spike. Excluding the alert month:

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (41) | 34 | 2 | 5 | **0.829** |
| level (57) | 0 | 47 | 10 | 0.825 |
| ramp (53) | 1 | 43 | 9 | 0.170 |

Balanced accuracy **0.608** (95 % CI 0.552–0.659); sustained-change precision **0.940** (95 % CI
0.903–0.978) against the 0.728 base rate, recall 0.991.

## What this licenses

The binary decision that actually matters — **promote an alert to "technology change", or treat it as a
transient spike** — becomes meaningfully better than blanket promotion: precision 0.94 instead of 0.73,
driven by catching 83 % of spikes. The three-way distinction does **not** work: ramp recall stays at 0.17,
so "ramp versus level" is not recoverable from a two-month window at this counting rate.

## Why the good number is labelled post-hoc

The improvement came from changing the rule after seeing it fail. It cannot be treated as confirmed.
**B-054** will re-pre-register the corrected window against fresh injections (different origins and cells)
before it is allowed to justify promotion logic. Until then the reported classification accuracy is the
pre-registered **0.394**, and 0.608 is a hypothesis.

## Never claimed

Shape recovery says nothing about whether a change is technological. It classifies the time series, not
the technology. Promotion remains a human judgement supported by the profile's other evidence fields.

## Verification

- Runs in ~2 s, deterministic (seed 7), artifact committed.
- `python -m medradar selftest` → 854 tests OK (skipped=3).
