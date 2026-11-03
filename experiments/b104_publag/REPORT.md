# b104 — publication knowledge-lag sensitivity of the hist_v1 fusion result (backlog B-041)

**Status:** COMPLETE. Frozen design: `research/protocols/b104_publag_preregistration.md`.
**Artifact:** `experiments/b104_publag/publag.json` (all numbers below are read from it).
**Run:** `python experiments/b104_publag/publag.py` (stdlib only; ~5 min; reuses the frozen hist_v1 evaluator, no new
sampling and no new inferential test).

## What was tested

The hist_v1 fusion comparison (feature set C vs D on the 2016-Q1+ origins) assumes a publication year `y` is usable
from the start of `y+1`. This sensitivity re-runs the same comparison at assumed publication knowledge lags of
**0, 14, 30 and 90 days** after the end of the year, changing only which publication years are visible at each origin.
Trial features and every other element of the evaluation are unchanged.

## Result

| knowledge lag | publication join | mean AP(C) | mean AP(D) | ΔAP(D−C) | origins with Δ>0 |
|---:|---:|---:|---:|---:|---:|
| 0 d | 0.786 | 0.0401 | 0.0348 | **−0.0053** | 1 / 9 |
| 14 d | 0.786 | 0.0401 | 0.0348 | **−0.0053** | 1 / 9 |
| 30 d | 0.786 | 0.0401 | 0.0348 | **−0.0053** | 1 / 9 |
| 90 d | 0.200 | 0.0401 | 0.0384 | **−0.0017** | 1 / 9 |

At 0/14/30 days the run **reproduces hist_v1 exactly** (join 0.786, AP(C) 0.0401, AP(D) 0.0348, Δ −0.0053). At 90 days
the lag removes `year−1` at first-quarter origins in non-leap years (the knowledge date becomes 1 April, after the
31 March quarter end), the join rate falls to 0.200, and Δ improves to −0.0017 — still negative.

**Verdict (frozen rule): unchanged.** Fusion (D) does not rank better than C at any of the four tested knowledge lags.
The hist_v1 conclusion is robust to this sensitivity. The 90-day variant rests on only 20 % publication join coverage
and is reported as such.

## What this does not claim

No upgrade of the hist_v1 fusion conclusion; no claim that publication counts are the only possible scientific signal;
no causal reading. The sensitivity is descriptive and adds no new inferential test.

## Reproduction and limits

`python experiments/b104_publag/publag.py`; deterministic (the imported hist_v1 evaluator fixes seed 20261103). The
lag rule is annual and only affects first-quarter origins; it cannot speak to intra-year publication timing, which the
store does not record.
