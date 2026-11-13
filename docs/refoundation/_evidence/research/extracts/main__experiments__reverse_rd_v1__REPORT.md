# Reverse R&D v1 — real-data experiment report (purged re-evaluation)

Regenerated 2026-11-02 from the frozen 2026-11-01 collection. Configuration: `config.json` (frozen before the final holdout; unchanged). Full machine-readable values: `metrics.json`; every number below is read from that file or from the regenerated `data_provenance.json`.

## What this revision fixes

The previously published table was computed with an unpurged rolling origin: at each origin the model trained on examples whose 12-month label window had not yet matured, so part of the training labels occurred inside the test window. This revision:

1. makes purged/embargoed training the default (`cutoff + horizon_months <= origin`, section `purge` in `metrics.json`);
2. keeps the old overlapping-label run as an explicitly labelled diagnostic (`leaky_labels_diagnostic`) so the size of the previous bias is measurable rather than hidden;
3. adds no-feature point-in-time persistence baselines and a paired bootstrap of model minus per-pair baseline (`baselines`, `model_vs_pair_baseline`);
4. replaces the tautological leakage check with an independent as-of replay of all 21 features from the source tables, and states honestly that this is a consistency audit, not a proof of absence of semantic leakage;
5. labels forecast evidence with raw and standardized scales (`raw_value`, `standardized_value`, `median_imputed`).

## Data actually used

- openFDA bulk exports dated 2026-10-30: 176,466 510(k) and 57,373 PMA source records; 31,219 510(k) + 23,871 PMA rows inside the ten-year window (55,090). After the resolved-company/track and material-PMA rules the research event set contains 3,833 events over 51 companies and 322 active company–track pairs.
- SEC EDGAR XBRL Company Facts: 43,420 consolidated observations across 32 resolved companies. The two IFRS filers (`philips`, `smith_nephew`) have zero `us-gaap` facts, so all their financial features are null. XBRL R&D aliases include `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` because Medtronic and Boston Scientific use it.
- USAspending: 3,453 real award records, 3,372 resolved to a curated company. All 3,453 remain `pit_usable=0`, i.e. none is point-in-time usable.
- Temporal examples: 6,701 mature rows over 25 quarterly origins. The purged development evaluation covers 5,466 rows / 2,530 positives; the untouched 2025-10-01 holdout contains 307 rows / 129 positives. FDA coverage ends 2026-10-15.
- Purge cost at the holdout: 5,491 matured training rows are available, versus 6,394 for the old leaky rule (5,491 is also the pair-baseline training set).
- Leakage replay: 6,701 examples and 140,721 feature values across 25 cutoffs, 0 mismatches, method `independent_as_of_replay`. The temporal graph materialized 2,174 observed product/company/technology edges and zero inferred investment edges.

The target is continued material public FDA activity in an already-active company–track pair over the next 12 months. It is not first entry, product-level sales, internal R&D start time or a causal market→R&D effect.

## Main results — purged/embargoed default

| Metric | R&D only, development | R&D + financial, development | R&D only, holdout | R&D + financial, holdout |
|---|---:|---:|---:|---:|
| PR-AUC | 0.797350 | 0.790040 | **0.793476** | **0.792199** |
| Brier ↓ | 0.181515 | 0.184231 | 0.172134 | 0.172104 |
| ECE-10 ↓ | 0.074719 | 0.074457 | 0.081120 | 0.073737 |
| FPR@0.5 ↓ | 0.323910 | 0.314714 | 0.275281 | 0.264045 |
| Precision@10% | 0.937843 | 0.936015 | 0.935484 | 0.935484 |
| Mean positive-target lead time | 134.081818 d | 134.081818 d | 139.038760 d | 139.038760 d |

Adding consolidated financial features **did not improve ranking**: development PR-AUC falls from 0.797350 to 0.790040 (−0.007310) and the holdout PR-AUC falls from 0.793476 to 0.792199 (−0.001278). Precision@K is unchanged. On the holdout, financial features change Brier by −0.000030 (0.172134→0.172104), ECE by −0.007383 (0.081120→0.073737) and FPR@0.5 by −0.011236 (0.275281→0.264045), so the only repeatable benefit is a small calibration/threshold shift, not ranking skill. Development origin PR-AUC standard deviation is 0.023854 (R&D only) and 0.026507 (with financials); holdout deltas are far smaller than that spread.

Lead time is measured from cutoff to the first positive target event; it is a target-property summary, not proof that the added features detected change earlier (it is identical by construction across the two feature sets).

## The old numbers were optimistic — diagnostic block, NOT results to cite

The previous publication reported the unpurged variant. It is retained only to quantify its bias (`leaky_labels_diagnostic` in `metrics.json`; `purge=false`).

| Metric | Leaky rd_only dev | Leaky rd_fin dev | Leaky rd_only holdout | Leaky rd_fin holdout |
|---|---:|---:|---:|---:|
| PR-AUC | 0.805317 | 0.805652 | 0.792370 | 0.790946 |
| Brier ↓ | 0.175237 | 0.175047 | 0.168737 | 0.168934 |
| ECE-10 ↓ | 0.052423 | 0.045151 | 0.060511 | 0.050781 |
| FPR@0.5 ↓ | 0.293058 | 0.281925 | 0.241573 | 0.219101 |

Purged minus leaky (`delta_purged_minus_leaky`, holdout): PR-AUC +0.001106 (rd_only) / +0.001253 (rd_fin); Brier +0.003397 / +0.003169; ECE +0.020610 / +0.022956; FPR +0.033708 / +0.044944 (i.e. 3.37 and 4.49 percentage points). Development PR-AUC falls by 0.007967 (rd_only) and 0.015612 (rd_fin) under purge. In short: the headline ranking was roughly robust, but the **calibration, Brier and false-positive numbers in the old report were optimistic** because of label overlap.

## The 0.79 PR-AUC is mostly pair persistence — persistence baselines

No-feature, point-in-time predictors on the same 307-row holdout, fitted only on the 5,491 matured training rows (unseen companies/tracks/pairs fall back to constant training prevalence; 95.77% of holdout pairs have matured history):

| Predictor | PR-AUC | Brier ↓ |
|---|---:|---:|
| constant training prevalence | 0.420195 | 0.247641 |
| company base rate | 0.570689 | 0.230847 |
| track base rate | 0.506832 | 0.246112 |
| **per-pair historical base rate (purged)** | **0.791259** | 0.173290 |
| purged logistic model, R&D only | 0.793476 | 0.172134 |
| purged logistic model, R&D + financial | 0.792199 | 0.172104 |

Deterministic paired bootstrap (2,000 resamples, seed 7) of AP(model) − AP(pair base rate):

- R&D only: point Δ +0.002218, bootstrap mean +0.002945, 95% CI **[−0.031599, +0.036774]**, P(Δ≤0) = 0.431.
- R&D + financial: point Δ +0.000940, bootstrap mean +0.001694, 95% CI **[−0.032642, +0.035645]**, P(Δ≤0) = 0.465.

Both intervals include zero. The per-pair base rate already captures 99.4% (rd_only) / 99.7% (rd_fin) of the AP lift over constant prevalence. **The headline PR-AUC mainly measures stable per-pair activity persistence; the ten R&D features add no statistically detectable incremental ranking value on this holdout.** Any claim of model-specific foresight from 0.79 is unjustified.

## Required research questions

1. **Did the new data improve prediction?** No. Under purge, financial features lose PR-AUC in both development (−0.007310) and holdout (−0.001278); only small calibration/threshold gains appear. This does not establish predictive value.
2. **Did it discover change earlier?** No supported claim. The target measures continuation of public activity, and mean positive-target lead time is identical across feature sets.
3. **Did it create more false positives?** Not relative to the persistence baseline, and financial features lower the model's own FPR (0.275281→0.264045). But the honest purged FPR is higher than the old published 0.241573 / 0.219101 — that earlier improvement was partly leaky-label optimism.
4. **Which companies or tracks benefited most?** Exploratory holdout subgroup deltas for financial features: Abbott +0.020000 (n=17); Johnson & Johnson MedTech −0.006612 (n=19) and Medtronic −0.006421 (n=24); by track, imaging US +0.009091 (n=13), endoscopy +0.006818 (n=21), ortho joint and wound care each −0.011111 (n=10), vascular access −0.008929 (n=21). These are small-group differences, not stable segment conclusions.
5. **Which sources added no clear information?** Consolidated SEC financials added no ranking gain in v1 under the purged evaluation. Procurement was not eligible for a historical gain test because first-publication history is unavailable (3,453 awards, 0 point-in-time usable). Market, patent, publication and jobs sources were not evaluated and must not be described as negative or positive results.
6. **Did improvement replicate in an independent time window?** No. The PR-AUC delta sign flips between development and holdout, and the model-versus-persistence interval includes zero. More independent windows and prospective forecasts are required before adding model complexity.

## Horizon registry

The trained model registered 25 forecasts at the latest quarterly cutoff (2025-10-01). Every row contains probability, baseline probability, temporal-ensemble spread, positive/negative feature contributions, model version and an exact event verification condition. Evidence records now carry both scales explicitly: `contribution = coefficient × standardized_value`, with `raw_value` (null when missing), `standardized_value`, `median_imputed` and `coefficient`; a null raw value can still have a nonzero contribution because the training median was imputed at the z-scale. All 25 forecasts are pending, so verified-forecast calibration is `insufficient_verified_forecasts` with null metrics rather than fabricated values.

## What did NOT improve (and why the result is weak)

- **The model does not beat a one-parameter per-pair persistence baseline.** AP difference CI [−0.031599, +0.036774] (rd_only) and [−0.032642, +0.035645] (rd_fin).
- **Consolidated financial data did not improve ranking** under purge; its development PR-AUC is tied-to-worse (0.790040 vs 0.797350) and holdout is slightly worse (0.792199 vs 0.793476).
- **Calibration got worse once labels were purged** (ECE 0.081120 vs the old 0.060511, Brier 0.172134 vs 0.168737); the old values were optimistic, not evidence of better calibration.
- **One 307-row holdout is not proof.** The bootstrap interval spans roughly ±0.035 AP; no stability claim can be made from a single window. The purged evaluation skips the first eligible origin because it has no matured training data, which slightly reduces the development sample (5,466 rows) relative to the old 5,704.
- **The leakage audit is an as-of replay/consistency check, not a proof of absence of semantic leakage.** Current product-code/track mappings, company aliases and target-definition choices applied to history cannot be detected this way.
- Procurement cannot support historical gain claims (current snapshot, first-publication unknown); SEC facts are consolidated company revenue, never product/segment revenue; two IFRS companies have zero US-GAAP facts.

## Interpretation and next experiment

The simple historical model remains the reference model, and the honest reading of v1 is a **negative result for the added financial data** and a **null result for model skill beyond per-pair persistence**. v1 does not justify a transformer, temporal graph network or a claim that financial markets direct R&D. The next useful step is prospective collection and an actually point-in-time demand source, followed by a preregistered first-entry/continuation comparison with more company coverage and more independent time windows. Product-level segment-footnote extraction is a separate task; consolidated revenue must not be substituted for it.

## Reproducibility caveats

- This regeneration reused the frozen 2026-11-01 collected database instead of re-downloading the bulk sources; the collect-side provenance blocks are therefore unchanged, and the data counts were independently re-verified from the official sources during the audit.
- openFDA bulk files do not provide historical first-publication timestamps. This run uses decision date +14 days as a conservative estimated availability time and marks it `estimated`; quarterly horizons reduce but do not eliminate this limitation.
- The paged-API collection lane uses different availability semantics and does not reproduce these metrics; the exact frozen recipe is in `docs/REVERSE_RD.md`.
- Current product-code/track mappings are not versioned historical knowledge.
- The experiment covers companies and pairs resolved by the current curated registry, so it is not an industry-wide random sample.
- One final holdout can show failure to replicate; it cannot prove stability even when metrics improve.
