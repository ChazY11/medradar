# Reverse R&D v1 — real-data experiment report

Run date: 2026-11-01. Configuration: `config.json` (frozen before the final holdout). Full machine-readable values: `metrics.json`.

## Data actually used

- Official openFDA bulk exports dated 2026-10-30: 31,219 510(k) and 23,871 PMA rows in the ten-year collection window. After resolved company/track and material-PMA rules, the research event set contains 3,833 events and 322 historically active company–track pairs.
- SEC EDGAR XBRL Company Facts: 43,420 consolidated observations across 32 companies with usable facts. XBRL R&D aliases were needed because Medtronic and Boston Scientific use `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost`.
- USAspending: 3,453 real award records, 3,372 resolved to a curated company. These remain descriptive because all 3,453 have `pit_usable=0`.
- Temporal examples: 6,701 mature rows over 25 quarterly origins. Development evaluation contains 5,704 rows; the untouched 2025-10-01 holdout contains 307 rows and 129 positive targets. FDA coverage ends 2026-10-15.
- Leakage audit: 6,701 examples checked, zero violations. The temporal graph materialized 2,174 observed product/company/technology edges and zero inferred investment edges.

The target is continued material public FDA activity in an already-active company–track pair over the next 12 months. It is not first entry, product-level sales, internal R&D start time or a causal market→R&D effect.

## Main results

| Metric | R&D only, development | R&D + financial, development | R&D only, holdout | R&D + financial, holdout |
|---|---:|---:|---:|---:|
| PR-AUC | 0.805317 | 0.805652 | **0.792370** | **0.790946** |
| Brier ↓ | 0.175237 | 0.175047 | 0.168737 | 0.168934 |
| ECE-10 ↓ | 0.052423 | 0.045151 | 0.060511 | 0.050781 |
| FPR@0.5 ↓ | 0.293058 | 0.281925 | 0.241573 | 0.219101 |
| Precision@10% | 0.938704 | 0.947461 | 0.935484 | 0.935484 |
| Mean positive-target lead time | 132.81 d | 132.81 d | 139.04 d | 139.04 d |

Development PR-AUC improved by only 0.000335 with financial features, but holdout PR-AUC changed by **−0.001424**. Holdout Brier was 0.000198 worse, ECE was 0.009729 better, FPR was 2.25 percentage points lower and Precision@K was unchanged. Development origin PR-AUC standard deviation was 0.02698 (R&D only) and 0.02719 (with financials).

Lead time is measured from cutoff to the first positive target event; it is a target-property summary, not proof that the added features detected change earlier.

## Required research questions

1. **Did the new data improve prediction?** Not consistently. There was a negligible development gain and a small holdout PR-AUC/Brier loss. Calibration and thresholded false positives improved, but this does not establish general predictive value.
2. **Did it discover change earlier?** No supported claim. The v1 target measures continuation of public activity, not first research entry. Mean positive-target lead time is identical by construction across the two feature sets.
3. **Did it create more false positives?** At the fixed 0.5 threshold, no: holdout FPR fell from 24.16% to 21.91%. This benefit did not come with better PR-AUC or Precision@K.
4. **Which companies or tracks benefited most?** No company showed a meaningful gain in the small holdout groups; Johnson & Johnson MedTech changed by −0.01818 PR-AUC (n=19), while other eligible company groups were unchanged. Endoscopy (+0.01409, n=21), vascular access (+0.01136, n=21) and peripheral vascular (+0.01111, n=12) gained slightly; ortho joint and wound care each lost 0.01111 (n=10). These are exploratory small-group differences, not stable segment conclusions.
5. **Which sources added no clear information?** Consolidated SEC financials added no reproducible ranking gain in v1. Procurement was not eligible for a historical gain test because first-publication history is unavailable. Market, patent, publication and jobs sources were not evaluated and must not be described as negative or positive results.
6. **Did improvement replicate in an independent time window?** No. The sign of the PR-AUC delta flipped between development and the final holdout. More independent windows and prospective forecasts are required before adding model complexity.

## Horizon registry

The trained model registered 25 forecasts at the latest quarterly cutoff. Every row contains probability, baseline probability, temporal-ensemble spread, positive and negative feature contributions, model version and an exact event verification condition. All 25 are pending because their 12-month horizons have not matured. Verified-forecast calibration is therefore `insufficient_verified_forecasts`, with null metrics rather than fabricated values.

## Interpretation and next experiment

The simple historical model remains the reference model. v1 does not justify a transformer, temporal graph network or a claim that financial markets direct R&D. The next useful step is prospective collection and an actually point-in-time demand source, followed by a preregistered first-entry/continuation comparison with more company coverage. Product-level segment-footnote extraction is a separate task; consolidated revenue must not be substituted for it.

## Reproducibility caveats

- openFDA bulk files do not provide historical first-publication timestamps. This run uses decision date +14 days as a conservative estimated availability time and marks it `estimated`; quarterly horizons reduce but do not eliminate this limitation.
- Current product-code/track mappings are not versioned historical knowledge.
- The experiment covers companies and pairs resolved by the current curated registry, so it is not an industry-wide random sample.
- One final holdout can show failure to replicate; it cannot prove stability even when metrics improve.
