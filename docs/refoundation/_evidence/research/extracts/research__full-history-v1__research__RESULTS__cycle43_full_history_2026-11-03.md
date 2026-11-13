# Cycle 43 — hist_v1: the full-history early-warning benchmark

**Date:** 2026-11-03 · **Branch:** `research/full-history-v1` · **Report:** `experiments/hist_v1/REPORT.md`
**Protocol:** `research/protocols/hist_v1_preregistration.md` (frozen; amendments A1–A5 logged before any fit)
**Gate:** `python tools/round_end.py` (the round-end log carries the exit code)

## What was asked

Can publicly observable multi-source temporal signals give early warning of a firm's first regulatory clearance in a
technology track over the full 1976–2026 device history — and does the answer change once the artificial 10-year
openFDA bulk window is removed?

## What was built

- `experiments/hist_v1/build_panel.py` → panel 1976-Q1…2026-Q2, 53 firms, 38 tracks, 528 pairs, 14,704 material
  events, SHA-256 `10f8c00a…`, deterministic, with entity/track/date/left-censoring audits.
- `config/hist_entity_aliases.json` — Dräger and Mindray resolved by 21 + 10 exact applicant strings (they are absent
  from the store's roster mapping).
- `experiments/hist_v1/eval.py` — expanding-window evaluation (30 origins 1995–2024), B0–B3 baselines, M1A/B/C,
  company-clustered paired bootstrap, 200-permutation null, lead-time frontier, ablations, heterogeneity.
- `experiments/hist_v1/five_firm_timeline.py` — descriptive five-company entry timelines.
- `tests/test_hist_eval.py` — 40 unit tests for AP, purge, bootstrap, lead time and feature definitions.
- `experiments/hist_v1/verify_report_numbers.py` — 152 checks that the report's numbers equal the artifacts'.

## What was found

1. **H1 is supported, marginally, on the pre-registered primary test.** `R_adj`, h=8, 30 origins, 8,415 candidate
   cells, 181 positives. Mean per-origin AP 0.1137 (M1C) vs 0.0553 (B1); Δ **+0.0584**, bootstrap 95 % CI
   **[+0.0020, +0.1213]**, p 0.045; the permutation null rejects at p **0.0299** (200 permutations). The MDE (0.090)
   exceeds the observed effect, the lower CI bound is 0.002, and the two-way exposure baseline B3 is **not** beaten
   (Δ +0.0438, CI −0.0184 … +0.0957): supported, not practically established.
2. **The signal is track tempo plus adjacency.** Firm-only features are *below* the company base rate (Δ −0.0064);
   adding industry/track features gives +0.0352; adding the firm's activity in other tracks of the same category gives
   +0.0584. Eras: +0.0879 (1995–2004), +0.0634 (2005–2014), +0.0239 (2015–2024).
3. **The unrestricted risk set repeats the pattern** (R_full, h=8: Δ +0.0371, CI [+0.0128, +0.0699]; h=4 +0.0281,
   CI [+0.0099, +0.0516]) and again does not beat B3 (+0.0225, CI −0.0087 … +0.0565).
4. **Fusion is negative**: trials + publications lower AP by 0.0053 on the 2016+ origins (H2 not supported).
5. **Lead-time frontier, with misses**: of 255 entry events in the window, 94 are inside the primary risk set; at a
   1 % budget 9/94 are alerted (precision 0.206, 5-quarter median lead, 5.9 false alarms/1,000); at 20 %, 38/94
   (precision 0.073). 56–85 entries are silently missed at every budget.
6. **The mandated firms are track-saturated**: last first-ever track entry 2012-Q4 (Medtronic, 32 tracks), 2000-Q4
   (GE HealthCare, 11), 2014-Q4 (Dräger, 4), 2011-Q1 (Mindray, 3); only Philips added tracks in 2016–2025 (4 of 15).
   161 of 255 entries are new-category entries that the primary risk set excludes by construction.
7. **The leak audit caught a real implementation defect.** The first execution (110 positive cells) was void: an
   unsorted company-category index corrupted both the risk-set definition and the feature matrix (184/300 replay
   mismatches). After the fix the replay mismatches are 0/300 and the verdict changes from UNRELIABLE to SUPPORTED —
   the first result was not published. This is the audit's purpose, demonstrated.

## What this means

The answer to the directive's question is **"yes, a real but marginal and not-yet-practically-useful early-warning
signal exists"**: public regulatory-sequence signals rank future first clearances better than firm persistence, with a
reliable interval and a permutation-null rejection, but not better than a two-way firm×track exposure baseline, and
with heavy recall losses. The next round must change the **design** (a coarser taxonomy for new-category entries, a
larger roster, and origins concentrated where entries occur), not the model.

## Record repairs done in the same round

- The independent audit (`research/audits/initial_research_audit.md`) found the "25 genuinely prospective" forecast
  set was 12/25 partially backfilled; corrected to **13** (D-075, R156).
- `b050/rolling_origin.py` crashed at HEAD; fixed and shown to reproduce its committed JSON identically (D-076, R157).

## Not done, on purpose

No human labels were created (the five-firm study remains blocked on its human reviewer); no prospective calibration
claim is possible before 2027-Q3; no causal claim is made; no taxonomy was re-specified after seeing results.
