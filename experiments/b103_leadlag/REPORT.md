# b103 — Cross-source lead/lag at the company level (backlog B-021)

**Status:** descriptive association study, generated from `leadlag.json` only (schema `b103.leadlag.v1`). **Frozen protocol:** `research/protocols/b103_leadlag_preregistration.md` (SHA-256 `63189a5e1ce3f8135d10203e06da0955668a8c167dde6894e4927806def6ee3f`).

**Run:** `python experiments/b103_leadlag/leadlag.py` — standard library only, no network, deterministic: yes.

## Question

At the company level, does activity in financial, market or publication sources systematically lead or lag material regulatory events — and if a lead is claimed, does it survive a company-clustered bootstrap, a pre-declared circular-shift permutation null, Holm correction across sources, and an era split?

This is a *descriptive association* result. A leading correlation does **not** establish that the source causes or predicts the event.

## Data and window

* Analysis window: 2017-Q1 … 2025-Q4 (36 quarters). Lags −8…+8; a pair requires both grid positions, so for k=+8 the first usable milestone quarter is 2019-Q1.
* Company universe: 53 companies present in the frozen hist_v1 panel; per-source exclusions are counted in the coverage section.
* Material events in the window: 3550 events across 53 companies.

| source | series | resolution | knowledge time |
|---|---|---|---|
| Regulatory events (M) | material 510(k)/PMA counts per company-quarter | quarter | available_at (FDA decision date) |
| Financial R&D | trailing-4-quarter ResearchAndDevelopmentExpense (log) | quarter (fact available_at) | filing available_at quarter |
| Market return | quarterly adj_close return | quarter | quarter end |
| Market volatility (descriptive) | quarterly SD of daily log returns | quarter | quarter end |
| Publication | OpenAlex works per company-year / 4 | annual (declared) | 15 February of year+1 |
| Procurement | — | — | all announcement_date NULL, pit_usable=0 |

* Procurement: **NOT_EVALUABLE** — 3453 rows, 3453 with NULL announcement_date, 0 pit_usable rows; no proxy substituted.

## Method (frozen)

* Per-company z-scores over each series' own observed window; pooled Pearson `r(k) = corr(z(S_{c,t−k}), z(M_{c,t}))` for k = −8…+8; positive k = source precedes events.
* Primary per source: `k* = argmax_{k∈1..8} |r(k)|` (ties → smallest k).
* Company-clustered bootstrap: resample companies with replacement 2,000 times, recompute the whole r(k) profile; 95 % percentile intervals (linear interpolation); descriptive and uncorrected.
* Circular-shift permutation null: for each company independently rotate its z-scored source series by a random offset in 1..T-1 (T=36) and recompute max_{k in 1..8} |r(k)|; p = fraction of null maxima >= the observed maximum.
* Holm correction across the three primary sources (financial_rd, market_return, publication) at α = 0.05.
* Era split (descriptive): 2017-2021 vs 2022-2025. A lead is reported as stable only if the point estimate at k* has the same sign and the absolute value >= 50 % of the full-window value in both eras.
* MDE at 80 % power (alpha=0.05) = (z_{0.975} + z_{0.80}) * SD_b, with SD_b the bootstrap standard deviation of the max-lead statistic max_{k in 1..8} |r(k)| over the 2,000 company-clustered resamples.

## Decision summary

| source | k* | r(k*) | 95 % bootstrap CI | permutation p | Holm-adjusted p | era stable | MDE (80 %) | decision |
|---|---:|---:|---|---:|---:|---|---:|---|
| Financial R&D | 1 | -0.0441 | [-0.1193, 0.0366] | 0.6830 | 1.0000 | no | 0.0723 | no lead detected (well-powered negative) |
| Market return | 5 | -0.0278 | [-0.0870, 0.0288] | 0.9670 | 1.0000 | no | 0.0513 | no lead detected (well-powered negative) |
| Publication | 1 | -0.0387 | [-0.1033, 0.0239] | 0.6140 | 1.0000 | yes | 0.0570 | no lead detected (well-powered negative) |
| Market volatility (descriptive) | 8 | 0.0420 | [-0.0277, 0.1135] | 0.7540 | — | no | 0.0568 | descriptive only |

Bottom line: no source meets criterion (ii) of the frozen decision rule, so no lead is claimed; the null results are bounded by the MDE below, the procurement lane is NOT_EVALUABLE, and market volatility is descriptive only.

Frozen decision rule: A source is said to lead only if all hold: (i) k* > 0; (ii) Holm-adjusted p < 0.05; (iii) the era-split stability rule holds. Otherwise the result is reported as no lead detected with its MDE; a source whose data are insufficient is reported as NOT_EVALUABLE with the measured coverage.

### Financial R&D

*Definition:* trailing-4-quarter ResearchAndDevelopmentExpense (USD, log); the fact enters the quarterly series in its available_at quarter and is carried forward between filings

**Primary:** k* = 1, r(k*) = -0.0441 (95 % bootstrap CI [-0.1193, 0.0366]; descriptive, uncorrected).

| k | r(k) | n pairs | 95 % bootstrap CI |
|---:|---:|---:|---|
| -8 | -0.0035 | 695 | [-0.0929, 0.0734] |
| -7 | -0.0117 | 715 | [-0.0920, 0.0662] |
| -6 | -0.0207 | 735 | [-0.0941, 0.0531] |
| -5 | -0.0305 | 755 | [-0.1131, 0.0519] |
| -4 | -0.0370 | 775 | [-0.1172, 0.0387] |
| -3 | -0.0260 | 795 | [-0.1049, 0.0550] |
| -2 | -0.0501 | 815 | [-0.1215, 0.0245] |
| -1 | -0.0550 | 835 | [-0.1280, 0.0238] |
| 0 | -0.0361 | 855 | [-0.1133, 0.0432] |
| 1 | -0.0441 | 828 | [-0.1193, 0.0366] |
| 2 | -0.0357 | 801 | [-0.1094, 0.0483] |
| 3 | -0.0093 | 774 | [-0.0839, 0.0725] |
| 4 | -0.0262 | 747 | [-0.0884, 0.0481] |
| 5 | -0.0276 | 720 | [-0.0955, 0.0549] |
| 6 | 0.0019 | 693 | [-0.0775, 0.0840] |
| 7 | -0.0064 | 666 | [-0.0834, 0.0730] |
| 8 | 0.0232 | 639 | [-0.0481, 0.0949] |

**Permutation null:** observed max |r| over k∈1..8 = 0.0441; p = 0.6830 (683/1000 null maxima ≥ observed; seed 20261103).

**Holm:** raw p = 0.6830, adjusted p = 1.0000 (family size 3).

**Era split at k*=1:** full-window r = -0.0441; 2017-Q1..2021-Q4 r = -0.0973 (n=415); 2022-Q1..2025-Q4 r = 0.0265 (n=413); stable = no.

**Power:** MDE(|r|) at 80 % power = 0.0723 (bootstrap SD of the max-lead statistic = 0.0258; formula (z_0.975 + z_0.80) × SD_b = 2.801585 × SD_b).

**Decision:** **no lead detected** (well-powered negative). Criteria: k*>0 = yes; Holm p<α = no; era stable = no.

### Market return

*Definition:* quarterly return of adj_close: quarter-end close / previous quarter-end close - 1

**Primary:** k* = 5, r(k*) = -0.0278 (95 % bootstrap CI [-0.0870, 0.0288]; descriptive, uncorrected).

| k | r(k) | n pairs | 95 % bootstrap CI |
|---:|---:|---:|---|
| -8 | -0.0208 | 1032 | [-0.0893, 0.0494] |
| -7 | -0.0262 | 1066 | [-0.0728, 0.0187] |
| -6 | -0.0070 | 1100 | [-0.0607, 0.0485] |
| -5 | -0.0034 | 1132 | [-0.0594, 0.0513] |
| -4 | 0.0105 | 1164 | [-0.0562, 0.0756] |
| -3 | 0.0385 | 1196 | [-0.0178, 0.0942] |
| -2 | 0.0097 | 1228 | [-0.0400, 0.0580] |
| -1 | 0.0397 | 1260 | [-0.0173, 0.0998] |
| 0 | -0.0035 | 1292 | [-0.0620, 0.0538] |
| 1 | 0.0198 | 1254 | [-0.0396, 0.0761] |
| 2 | -0.0083 | 1216 | [-0.0604, 0.0432] |
| 3 | 0.0004 | 1178 | [-0.0719, 0.0720] |
| 4 | 0.0230 | 1140 | [-0.0296, 0.0781] |
| 5 | -0.0278 | 1102 | [-0.0870, 0.0288] |
| 6 | 0.0054 | 1064 | [-0.0570, 0.0629] |
| 7 | -0.0185 | 1026 | [-0.0854, 0.0508] |
| 8 | -0.0138 | 988 | [-0.0653, 0.0387] |

**Permutation null:** observed max |r| over k∈1..8 = 0.0278; p = 0.9670 (967/1000 null maxima ≥ observed; seed 20261103).

**Holm:** raw p = 0.9670, adjusted p = 1.0000 (family size 3).

**Era split at k*=5:** full-window r = -0.0278; 2017-Q1..2021-Q4 r = 0.0071 (n=507); 2022-Q1..2025-Q4 r = -0.0539 (n=595); stable = no.

**Power:** MDE(|r|) at 80 % power = 0.0513 (bootstrap SD of the max-lead statistic = 0.0183; formula (z_0.975 + z_0.80) × SD_b = 2.801585 × SD_b).

**Decision:** **no lead detected** (well-powered negative). Criteria: k*>0 = yes; Holm p<α = no; era stable = no.

### Publication

*Definition:* OpenAlex works per company-year divided equally across the year's quarters (works/4), usable from 15 February of the following year

**Primary:** k* = 1, r(k*) = -0.0387 (95 % bootstrap CI [-0.1033, 0.0239]; descriptive, uncorrected).

| k | r(k) | n pairs | 95 % bootstrap CI |
|---:|---:|---:|---|
| -8 | 0.0182 | 1352 | [-0.0429, 0.0770] |
| -7 | 0.0106 | 1400 | [-0.0573, 0.0742] |
| -6 | -0.0133 | 1448 | [-0.0813, 0.0549] |
| -5 | -0.0164 | 1496 | [-0.0787, 0.0442] |
| -4 | -0.0079 | 1544 | [-0.0653, 0.0489] |
| -3 | -0.0303 | 1590 | [-0.0908, 0.0253] |
| -2 | -0.0372 | 1636 | [-0.0931, 0.0133] |
| -1 | -0.0230 | 1682 | [-0.0805, 0.0279] |
| 0 | -0.0365 | 1728 | [-0.0956, 0.0178] |
| 1 | -0.0387 | 1678 | [-0.1033, 0.0239] |
| 2 | 0.0028 | 1628 | [-0.0642, 0.0663] |
| 3 | -0.0010 | 1578 | [-0.0633, 0.0582] |
| 4 | 0.0125 | 1528 | [-0.0424, 0.0656] |
| 5 | 0.0142 | 1480 | [-0.0398, 0.0714] |
| 6 | 0.0180 | 1432 | [-0.0332, 0.0743] |
| 7 | -0.0102 | 1384 | [-0.0599, 0.0440] |
| 8 | -0.0053 | 1336 | [-0.0537, 0.0466] |

**Permutation null:** observed max |r| over k∈1..8 = 0.0387; p = 0.6140 (614/1000 null maxima ≥ observed; seed 20261103).

**Holm:** raw p = 0.6140, adjusted p = 1.0000 (family size 3).

**Era split at k*=1:** full-window r = -0.0387; 2017-Q1..2021-Q4 r = -0.0264 (n=902); 2022-Q1..2025-Q4 r = -0.0280 (n=776); stable = yes.

**Power:** MDE(|r|) at 80 % power = 0.0570 (bootstrap SD of the max-lead statistic = 0.0203; formula (z_0.975 + z_0.80) × SD_b = 2.801585 × SD_b).

**Decision:** **no lead detected** (well-powered negative). Criteria: k*>0 = yes; Holm p<α = no; era stable = yes.

### Market volatility (descriptive)

*Definition:* quarterly sample SD of daily log adj_close returns

**Primary:** k* = 8, r(k*) = 0.0420 (95 % bootstrap CI [-0.0277, 0.1135]; descriptive, uncorrected).

| k | r(k) | n pairs | 95 % bootstrap CI |
|---:|---:|---:|---|
| -8 | -0.0145 | 1036 | [-0.0782, 0.0515] |
| -7 | -0.0108 | 1070 | [-0.0654, 0.0493] |
| -6 | -0.0334 | 1104 | [-0.0861, 0.0179] |
| -5 | -0.0206 | 1138 | [-0.0828, 0.0409] |
| -4 | -0.0640 | 1170 | [-0.1193, -0.0123] |
| -3 | -0.0232 | 1202 | [-0.0863, 0.0377] |
| -2 | 0.0363 | 1234 | [-0.0281, 0.1025] |
| -1 | -0.0219 | 1266 | [-0.0859, 0.0400] |
| 0 | -0.0164 | 1298 | [-0.0687, 0.0353] |
| 1 | -0.0272 | 1260 | [-0.0755, 0.0220] |
| 2 | -0.0064 | 1222 | [-0.0642, 0.0599] |
| 3 | -0.0377 | 1184 | [-0.0848, 0.0095] |
| 4 | -0.0288 | 1146 | [-0.0778, 0.0252] |
| 5 | 0.0394 | 1108 | [-0.0190, 0.1015] |
| 6 | -0.0065 | 1070 | [-0.0618, 0.0512] |
| 7 | -0.0019 | 1032 | [-0.0431, 0.0408] |
| 8 | 0.0420 | 994 | [-0.0277, 0.1135] |

**Permutation null:** observed max |r| over k∈1..8 = 0.0420; p = 0.7540 (754/1000 null maxima ≥ observed; seed 20261103).

**Holm:** not in the Holm family (descriptive only).

**Era split at k*=8:** full-window r = 0.0420; 2017-Q1..2021-Q4 r = 0.0859 (n=403); 2022-Q1..2025-Q4 r = 0.0182 (n=591); stable = no.

**Power:** MDE(|r|) at 80 % power = 0.0568 (bootstrap SD of the max-lead statistic = 0.0203; formula (z_0.975 + z_0.80) × SD_b = 2.801585 × SD_b).

**Decision:** **descriptive only**. Criteria: k*>0 = yes; Holm p<α = —; era stable = no.

## Market volatility — descriptive only

Quarterly return volatility is secondary/descriptive and outside the Holm family. k* = 8, r(k*) = 0.0420, permutation p = 0.7540, MDE = 0.0568. No lead is claimed from this series.

## Coverage and exclusions

| source | with data | included | no data | <8 quarters | other | company-quarters observed |
|---|---:|---:|---:|---:|---:|---:|
| Financial R&D | 30 | 27 | 23 | 0 | 3 | 963 / 1908 |
| Market return | 38 | 38 | 15 | 0 | 0 | 1292 / 1908 |
| Publication | 51 | 51 | 2 | 0 | 0 | 1728 / 1908 |
| Market volatility (descriptive) | 38 | 38 | 15 | 0 | 0 | 1298 / 1908 |

Exclusion reasons per source are recorded verbatim in the JSON (`sources.<id>.coverage.exclusions`).

### Excluded companies

* Financial R&D: constant_source_series (3): alcon, fresenius_medical_care, zimmer_biomet; no_source_data (23): ambu, bbraun, biotronik, boston_scientific, canon_medical, cook_medical, draeger, fujifilm, hologic, invacare, karl_storz, masimo, medline, medtronic, mindray, nevro, olympus, pentax_medical, philips, siemens_healthineers, smith_nephew, terumo, wl_gore.
* Market return: no_source_data (15): bbraun, biotronik, canon_medical, cook_medical, draeger, hologic, invacare, karl_storz, masimo, medline, mindray, nevro, olympus, pentax_medical, wl_gore.
* Publication: no_source_data (2): draeger, mindray.
* Market volatility (descriptive): no_source_data (15): bbraun, biotronik, canon_medical, cook_medical, draeger, hologic, invacare, karl_storz, masimo, medline, mindray, nevro, olympus, pentax_medical, wl_gore.

## Limits (inherited, not corrected)

* Descriptive association only: a leading correlation does not establish that the source causes or predicts a material regulatory event; no causal language is used.
* Publication data are annual; the quarterly series is a step function and cannot resolve within-year timing.
* Market data are auxiliary: the return/volatility lanes only describe co-movement, and volatility is outside the Holm family.
* The financial series is carried forward between annual filings, so its quarterly resolution is coarser than the grid; companies whose filings stop early keep a flat value and are measured, not repaired.
* The event lane inherits the hist_v1 limitations: current-corporate-group entity mapping, current unversioned track taxonomy, FDA-decision-date availability, and a materiality rule that excludes 96.6 % of PMA supplements.
* Procurement is NOT_EVALUABLE: every announcement_date is NULL and every row has pit_usable=0, so no PIT procurement series exists.
* The era split is a descriptive stability check on point estimates, not a separate significance test.

## Interpretation notes fixed before the run

* The analysis grid is the 36 frozen quarters 2017-Q1..2025-Q4; all series are indexed on that grid, so a lag-k pair exists only when both t and t-k are inside the grid (for k=8 the first usable milestone quarter is 2019-Q1, as the protocol states).
* The event series is a count with zero-filled quarters: the frozen panel monitors every company over the whole grid, so a quarter without an event is a true 0.
* The financial series is a step function: at each quarter end it carries the most recently filed trailing-4-quarter (reported period 300-400 days) R&D fact, which enters at its available_at quarter; log(USD); non-positive values are missing.
* The publication series uses works(y)/4 for the most recent complete year known under the declared 15-February rule; years without a persisted row are missing, not zero.
* The z-score denominator is the sample SD (n-1) over the company's own observed quarters of that series; constant or <3-observation series have no z-score.
* Market volatility is descriptive only and excluded from the Holm family, as the protocol requires.
* The 'underpowered / well-powered negative' label is a reporting convention only: the null is labelled well-powered negative when the measured MDE <= 0.10, otherwise underpowered; it never converts a null into a lead.
* No b103 statistic had been computed before these interpretation decisions were fixed; the frozen protocol file was not edited.
