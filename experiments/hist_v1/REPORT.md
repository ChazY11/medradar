# hist_v1 — Full-history early-warning benchmark (1976–2026): report

**Status:** COMPLETE. The pre-registered primary test is **SUPPORTED** on the 24-month horizon (R_adj), and the
support does **not** extend to the two-way exposure baseline. All numbers below are read from
`experiments/hist_v1/results.json` (the panel it consumed is hashed there), from `experiments/hist_v1/audits.json`, or
from `experiments/hist_v1/five_firm_timeline.json`; `experiments/hist_v1/verify_report_numbers.py` re-checks the
report's numbers against those artifacts.
**Protocol:** `research/protocols/hist_v1_preregistration.md` (frozen; amendments A1–A5 logged before any fit or
metric). **Branch:** `research/full-history-v1` · **Worktree:** `D:/DEPPSKK/worktrees/hist-v1`.

> **Answer to the directive's core question, as far as this study can take it.** Publicly observable regulatory-sequence
> signals rank future first clearances better than firm persistence: on the pre-registered primary risk set the
> 24-month mean per-origin AP is **0.1137 vs 0.0553** for the company base rate, Δ **+0.0584**, company-clustered
> 95 % CI **[+0.0020, +0.1213]**, permutation p **0.030** (200 permutations). That is a real but **marginal** positive:
> the interval's lower bound is 0.002, the minimum detectable effect (0.090) is larger than the observed effect, and
> the advantage disappears against the stronger two-way exposure baseline (Δ +0.0438, CI −0.018 … +0.096). No added
> source (trials, publications) improves the ranking. The result is a **candidate early-warning signal whose existence
> is now supported and whose practical value is not yet established**.

---

## 1. Why the study exists

The programme's previous panels were built from a 2016–2026 openFDA **bulk** lane (55,090 events) against a diagnosis
that data density, not modelling, was the binding constraint. The store actually holds the full openFDA device
history: 510(k) 176,466 records from 1976-07-15 and PMA 57,372 records from 1968-10-09. This study rebuilds the panel
over the whole history, pre-registers a discrete-time entry-hazard target, and evaluates it with expanding-window
origins from 1995 to 2024.

## 2. Panel (new artifact)

`experiments/hist_v1/build_panel.py` → `out/hist_v1/panel.json` (474,686 B, SHA-256 `10f8c00a…350e20`).
Contract: `experiments/hist_v1/README.md`; audits: `experiments/hist_v1/audits.json`.

| quantity | value |
|---|---|
| unit | company × technology track × quarter |
| grid | 1976-Q1 … 2026-Q2 (202 quarters; 2026-Q3 partial, excluded) |
| companies | 53 (5 mandated deep cases + 48-company roster; Dräger and Mindray resolved by exact-string registry) |
| tracks | 38 (the tracks that appear in `events.track_id`; 12 of the 50 configured tracks never occur) |
| observed (company, track) pairs | **528** |
| material events in panel | **14,704** (14,090 510(k) + 614 PMA under the panel materiality rule) |
| material device events in store | 178,417 (510(k) 176,466 + PMA 1,951 material) |

**The funnel is the first finding.** Of 178,417 material device events, 98,254 (55.1 %) have no track mapping and
153,676 (86.1 %) have no company in the 51-company roster; 118 fall after the grid. Only **14,704 (8.2 %)** enter the
panel. 510(k) company linkage in the main store is 13.4 %. The panel is a *curated-roster* panel, not an industry
panel, and the five mandated firms are the only entities for which the study makes firm-level claims.

**Deep cases** (material events / tracks ever entered): Medtronic 1,298 / 32 · GE HealthCare 875 / 11 ·
Philips 808 / 15 · Dräger 133 / 4 · Mindray 152 / 3. The three roster deep cases are audited applicant by applicant;
Dräger and Mindray are resolved by explicit exact-string aliases (`config/hist_entity_aliases.json`, 21 and 10
accepted strings, rejected strings recorded).

**Audits that change interpretation** (all in `audits.json`):
1. `company_key` is a **current corporate-group** mapping: 217 Medtronic events from Covidien / Tyco / Kendall are
   attributed retroactively to Medtronic. `pairs_no_acquired` removes them; the sensitivity is declared in A5.
2. **Date quality is clean**: `available_at == event_date` for 100 % of rows; no missing values.
3. **Left-censoring**: 25 pairs have their first event in the first four grid quarters (1976); 18 material pre-1976 PMA
   records belong to no panel company, so grid truncation costs the panel 0 events.
4. The product-code fallback **rescued zero** material events: every event without `track_id` also has a product code
   absent from `config/product_code_tracks.json` (1,958 entries). The taxonomy costs 55.1 % of material events.

## 3. Design (one paragraph)

At origin quarter *t* a (company, track) pair is a candidate if the company has ≥1 material event by *t*, the pair has
**no** material event by *t*, and (primary risk set `R_adj`) the company already has an event in **another track of the
same category**. The label `Y8` (`Y4`) is 1 iff the pair's first material event falls in `(t, t+8]` (`(t, t+4]`).
Features are 15 point-in-time quantities (firm activity/growth/tempo/tenure/size; track industry activity, growth,
entrants, recent competitor entries, age; adjacency activity/share; category share), computed only from events with
`available_at ≤ end of t`. Model M1 is an L2 logistic regression (training-only standardisation and median imputation,
λ = 1.0, fixed 120 epochs, no tuning). Baselines: B0 prevalence, B1 company base rate, B2 track base rate, B3 B1×B2.
Expanding-window walk-forward: 30 annual origins 1995-Q1…2024-Q1 for h=8 (31 for h=4), training on all candidate cells
with `t' + h ≤ t` (purge asserted, 0 violations; training capped by the pre-declared case-control rule, A2, at
12,000 rows). Primary metric: mean per-origin AP on `R_adj`, h=8; primary comparison M1C−B1 with a company-clustered
paired bootstrap (2,000 resamples, seed 20261103).

## 4. Primary result: H1 is supported, marginally

`R_adj`, h=8: 30 origins, **8,415 candidate cells**, **181 positive cell-rows**, mean **6.0 positives per origin**
(range 4–12). The company-clustered bootstrap is **reliable** (0.1 % of resamples below the pre-declared
computable-origin gate; median 29 of 30 origins).

| model | mean per-origin AP | 95 % CI (bootstrap) |
|---|---:|---|
| B0 constant prevalence | 0.0229 | — |
| B1 company base rate | 0.0553 | [0.0361, 0.0922] |
| B2 track base rate | 0.0468 | [0.0427, 0.0853] |
| B3 B1×B2 (two-way exposure) | **0.0699** | [0.0518, 0.1201] |
| M1A firm features only | 0.0489 | — |
| M1B + industry/track | 0.0905 | — |
| **M1C + adjacency (primary)** | **0.1137** | [0.0753, 0.1837] |

| comparison | point ΔAP | bootstrap 95 % CI | p | MDE (80 %) | verdict |
|---|---:|---|---:|---:|---|
| **M1C − B1 (pre-registered primary)** | **+0.0584** | **[+0.0020, +0.1213]** | 0.045 | 0.090 | **SUPPORTED** |
| M1C − B2 | +0.0669 | [+0.0147, +0.1198] | 0.004 | 0.081 | supported (secondary) |
| M1C − B3 (strongest no-feature baseline) | +0.0438 | [−0.0184, +0.0957] | 0.198 | 0.087 | **not established** |

**Reading.** The pre-registered criterion (CI excludes 0, positive point estimate) is met, so H1 is supported on the
24-month horizon. The support is thin and this report does not oversell it: (a) the lower bound is 0.002; (b) the MDE
(0.090) is larger than the observed effect (0.058), so the design could not reliably detect an effect of this size;
(c) the model does **not** beat the two-way exposure baseline B3 (CI includes 0). What is established is that the
time-varying features beat *firm persistence* and *track tempo* separately; their incremental value over the product
of the two is not established.

**h=4 (secondary horizon).** Δ +0.0565, but the bootstrap is UNRELIABLE (descriptive interval −0.002 … +0.114):
not confirmatory.

**Permutation null (pre-registered).** 200 permutations (seed 20261103) scramble labels among cells sharing
(origin, track), preserving every origin's prevalence and every (origin, track) entry count; M1C and B1 are refitted on
the permuted training labels. Observed ΔAP 0.0584 vs null distribution mean 0.0239 (sd 0.0129, max 0.0667); only
6 of 200 permutations reach the observed value: **empirical p = 0.0299** (resolution floor 0.0050). The ranking
advantage is not an artefact of the label scramble.

## 5. Where the signal is, and where it is not

### 5.1 The gain is track tempo plus adjacency, not firm momentum

| feature group | mean per-origin AP | Δ vs B1 |
|---|---:|---:|
| A firm only (activity, growth, tempo, tenure, size) | 0.0489 | **−0.0064** (below persistence) |
| B + industry/track (activity, growth, entrants, competitor entries, age) | 0.0905 | +0.0352 |
| C + adjacency (firm's activity in other tracks of the same category) | **0.1137** | +0.0584 |

Firm-level momentum and tempo alone do **not** beat the company base rate. Track-level activity raises AP by 0.035,
and the company's own recent activity in *other tracks of the same category* adds a further 0.023. Whether a firm is
currently active inside the technology area it is about to enter is the informative signal — a testable mechanism
statement for the next design.

### 5.2 Eras (descriptive)

| era | B1 | B3 | M1C | Δ M1C−B1 |
|---|---:|---:|---:|---:|
| 1995–2004 | 0.0670 | 0.0925 | 0.1550 | +0.0879 |
| 2005–2014 | 0.0795 | 0.0818 | 0.1429 | +0.0634 |
| 2015–2024 | 0.0194 | 0.0355 | 0.0433 | +0.0239 |

The direction is stable in all three eras; the modern era has few positives (mean 2 per origin), so its magnitude is
not estimable.

### 5.3 The unrestricted risk set (pre-registered robustness estimand)

`R_full` (established filer, pair unentered, no adjacency restriction): 30 origins, 41,892 candidate cells, 459
positives (mean 15.3/origin).

| horizon | model | mean per-origin AP | point Δ(M1C−B1) | bootstrap 95 % CI |
|---|---|---:|---:|---|
| h=8 | B1 / B3 / M1C | 0.0307 / 0.0397 / **0.0607** | **+0.0300** | **[+0.0128, +0.0699]** (bootstrap mean 0.0371) |
| h=8 | M1C − B3 | — | +0.0210 | [−0.0087, +0.0565] (bootstrap mean 0.0225) |
| h=4 | M1C − B1 | — | +0.0204 | [+0.0099, +0.0516] (bootstrap mean 0.0281) |

The same pattern as the primary: a reliable advantage over persistence, none over the two-way baseline.

### 5.4 Fusion (H2) adds nothing

On the 9 origins from 2016-Q1, the trial and publication lanes joined at cell level (2,902 candidate cells;
publication join rate 0.786; trial-track present 0.910; 2,663 trial events, 1,364 unmapped to panel tracks).
Adding them (feature set D) moved mean per-origin AP from 0.0401 to 0.0348: Δ **−0.0053** with an UNRELIABLE
bootstrap. **H2 is not supported**: no cross-source gain, consistent with the earlier annual-publication ablation.

### 5.5 Lead time and the H5 frontier (descriptive, with misses)

255 first-entry events fall inside the evaluation window; **94** are inside the `R_adj` risk set at an origin within
the 8 quarters before the entry (the other 161 are new-category entries, excluded by construction). At each origin the
alert threshold is that origin's 90th-percentile training score; entries never alerted inside the 8-quarter window are
**missed**.

| alert budget | precision | recall | entries alerted | entries missed | median lead | false alarms / 1,000 candidate-quarters |
|---:|---:|---:|---:|---:|---:|---:|
| 1 % | 0.206 | 0.072 | 9 / 94 | 85 | 5 quarters | 5.9 |
| 5 % | 0.137 | 0.177 | 19 / 94 | 75 | 6 quarters | 24.0 |
| 10 % | 0.094 | 0.243 | 24 / 94 | 70 | 6 quarters | 50.6 |
| 20 % | 0.073 | 0.359 | 38 / 94 | 56 | 6 quarters | 98.3 |

**H5 answer.** Earlier warning trades against reliability, and the trade is unfavourable at low budgets: at a 1 %
alert rate the system finds 9.6 % of the entries it could see (9/94) with 20.6 % precision (about 14× the 1.5 % cell
base rate) and a 5-quarter median lead; at a 20 % alert rate it finds 40 % (38/94) but precision falls to 7.3 %,
close to the base rate. A useful operating point exists around a 1–5 % budget for *ranking* use, not for autonomous
alerting. Between 56 and 85 of the 94 in-scope entries are silently missed at every budget.

### 5.6 Heterogeneity (H3/H4, descriptive)

Three companies have ≥10 positive test cells: Abbott Δ +0.192 (11 positives), B. Braun +0.397 (12), Medtronic +0.286
(24). The deep-case vs auxiliary difference is −0.038 (95 % CI −0.168 … +0.093): no detectable difference, and the
sample is not random. By category: orthopedics +0.342 (17 positives), diabetes +0.308 (8), neuroscience +0.144 (6),
surgery +0.095 (31), specialty +0.044 (45), cardiovascular +0.033 (39), imaging +0.024 (12), **monitoring −0.077 (14),
IVD −0.099 (9)**. H3 is supported only descriptively; H4 direction is heterogeneous but each category has 6–45
positives, so this remains a hypothesis.

## 6. The five-company case studies: the target is structurally saturated

From `experiments/hist_v1/five_firm_timeline.json` and `FIVE_FIRM_TIMELINE.md` (counts only, no inference):

| firm | material events | tracks ever entered | first entry | last new-track entry | 1976–1995 | 1996–2005 | 2006–2015 | 2016–2026 |
|---|---:|---:|---|---|---:|---:|---:|---:|
| Medtronic | 1,298 | 32 | 1977-Q4 | **2012-Q4** | 16 | 12 | 4 | **0** |
| GE HealthCare | 875 | 11 | 1978-Q1 | 2000-Q4 | 7 | 4 | 0 | 0 |
| Philips | 808 | 15 | 1977-Q2 | 2025-Q2 | 7 | 4 | 0 | 4 |
| Dräger | 133 | 4 | 1977-Q1 | 2014-Q4 | 3 | 0 | 1 | 0 |
| Mindray | 152 | 3 | 2004-Q1 | 2011-Q1 | 0 | 1 | 2 | 0 |

**The finding is the saturation.** At this 38-track resolution the mandated firms' portfolios were essentially
complete by 2015: Medtronic, GE HealthCare, Dräger and Mindray added **no new track** in the last decade (Philips
added 4). Consequently (a) the primary target is rare in the modern era, and (b) most entries are new-category entries
that the primary risk set excludes by construction (161 of 255 in the evaluation window). A future study that wants to
predict the more strategic "new-category" entries must use a coarser or different taxonomy and a larger firm sample;
with 53 firms it cannot be powered.

## 7. Failure analysis (what went wrong, and what is not claimed)

1. **An implementation defect voided the first full evaluation.** The first execution of the frozen protocol produced
   110 positive cells and an UNRELIABLE bootstrap. The pre-registered leak audit then found 184/300 feature-replay
   mismatches: `company_cat_q` was built in pair-record order, not sorted, so the bisect in the feature builder
   returned wrong adjacency counts, and the same unsorted index corrupted the risk-set definition (7,556 candidates
   instead of 8,415). After sorting the index the replay mismatches fall to **0/300**, positives rise to 181, the
   bootstrap becomes reliable, and the verdict changes from UNRELIABLE to SUPPORTED. The audit did its job; the first
   result was not published.
2. **The primary result is marginal.** Lower CI bound 0.002; MDE 0.090 > observed 0.058; and the two-way baseline B3 is
   not beaten. "Supported" here means the pre-registered criterion was met, not that the signal is practically strong.
3. **The primary risk set excludes most milestones.** 161 of 255 entries are new-category entries.
4. **The taxonomy is the binding constraint on the modern era.** 55.1 % of material events have no track; the five
   deep-case firms saturate 3–32 tracks; only 94 same-category entries are inside the risk set during evaluation.
5. **Fusion is negative.** Trial + publication features lowered AP; the trial lane covers 2016+ only and 1,364 of its
   2,663 events do not map to a panel track; the publication lane is annual and company-level. No proxy was used.
6. **Entity attribution is a current-corporate-group mapping.** 217 Medtronic acquired-brand events are retroactive;
   the sensitivity removes them. For the 48 roster companies the mapping is unaudited, the main external-validity
   limitation.
7. **The taxonomy is unversioned.** Applying the 2026 mapping to 1976–2026 can make a track look younger than it is;
   `track_age` is computed from observed events as a partial mitigation.
8. **No causal claim.** An entry is a public clearance, not an internal decision.

## 8. What is established, and what is not

**Established.**
- A reproducible full-history panel (1976-Q1…2026-Q2; 53 companies; 38 tracks; 528 pairs; 14,704 material events) with
  source-hash manifest, entity/track/date audits and a determinism check.
- **H1 is supported on the pre-registered primary test** (R_adj, h=8): M1C beats firm persistence by ΔAP +0.0584,
  95 % CI [+0.0020, +0.1213], permutation p = 0.0299; the direction is stable in all three eras.
- The signal is carried by **track-level and adjacency** features; firm momentum alone is below persistence.
- **H2 is not supported**: trial + publication fusion does not improve ranking (Δ −0.0053, unreliable).
- A quantified lead-time/reliability frontier (1 % → 9/94 entries at 20.6 % precision; 20 % → 38/94 at 7.3 %), with
  the missed entries reported.
- The five mandated firms' track portfolios are saturated: no new track after 2012 (Medtronic), 2000 (GE HealthCare),
  2014 (Dräger), 2011 (Mindray); only Philips added tracks in 2016–2025.

**Not established.**
- Any advantage over the **two-way exposure baseline B3** (Δ +0.0438, CI −0.0184 … +0.0957): the incremental value of
  the time-varying features over the product of firm and track base rates is **not** established.
- Anything about the 12-month horizon (h=4 bootstrap unreliable) or about individual firms/categories beyond
  description.
- Any causal, internal-R&D, or "strategic intent" reading. Any prospective calibration (the forecast registry has no
  matured forecast; D-075).
- That the result generalises beyond the 53-company curated roster (86.1 % of device events are outside it).

## 9. Reproduction

```bash
python experiments/hist_v1/build_panel.py          # out/hist_v1/panel.json (deterministic; SHA-256 in manifest.json)
python experiments/hist_v1/eval.py --panel out/hist_v1/panel.json --out experiments/hist_v1/results.json --workers 12
python experiments/hist_v1/five_firm_timeline.py   # five_firm_timeline.json + FIVE_FIRM_TIMELINE.md
python experiments/hist_v1/verify_report_numbers.py # re-checks this report's numbers against the artifacts
python -m unittest tests.test_hist_eval            # 40 metric/model/purge/lead-time tests
```

Determinism: the panel is byte-identical across two runs; the evaluator fixes all seeds (20261103) and has no random
split. The full evaluation takes ~30 minutes on this workstation (12 workers for the 200-permutation null); `--quick`
reduces repetitions for smoke tests. The panel is a regenerable intermediate in `out/` (git-ignored); its SHA-256 is in
`experiments/hist_v1/manifest.json` and in `results.json`.
