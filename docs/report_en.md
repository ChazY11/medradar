# MedRadar: FDA Device & Drug Industry Radar

_Generated 2026-10-30T18:39:23Z (UTC) · Window 2025-01-01 to 2026-10-30 (8 quarters) · Baseline 2020-01-01 to 2024-12-31 (20 quarters)_

## Key takeaways

1. Top device track: Cardiac Rhythm (THI 1.94, P(up) 98.2%), 11 events in window vs 0.6/quarter baseline.
2. 16 of 24 tracked device segments are in a heating-up regime (THI 95% CI above 1.0).
3. Strongest big-pharma momentum: ResMed (THI 2.35), Olympus (THI 2.25), ICU Medical (THI 2.09). Regulatory cadence is a proxy, not revenue.
4. 19 first-seen records in the last 90 days; latest: Ge Healthcare into imaging_mr_ct.
5. Recall clusters: Medline (101), Philips (87), Bd (64); watch product-line ageing and software-related causes.

## Data status

- Device / drug / trials: `ok`, `ok`, `ok`
- NMPA (China registrations): `unavailable` - **unavailable (NMPA data not loaded)**; China-gap numbers are not inferred.
- Prices: `ok`
- Events in window: 83,578

## Hottest device tracks

| # | Track | THI | 95% CI | P(up) | Recent | Trend |
|---|---|---|---|---|---|---|
| 1 | Cardiac Rhythm | 1.94 | [1.03, 3.11] | 98.2% | 11 | heating |
| 2 | Wearable & Remote Monitoring | 1.8 | [1.42, 2.24] | 100.0% | 64 | heating |
| 3 | Structural Heart | 1.57 | [0.93, 2.37] | 95.9% | 15 | heating |
| 4 | Medical AI / SaMD | 1.54 | [1.41, 1.68] | 100.0% | 422 | heating |
| 5 | Surgical Robotics | 1.54 | [1.09, 2.08] | 99.1% | 30 | heating |
| 6 | Rehabilitation / Exoskeleton | 1.51 | [1.28, 1.77] | 100.0% | 124 | heating |
| 7 | Aesthetics | 1.42 | [1.24, 1.63] | 100.0% | 162 | heating |
| 8 | Women's Health | 1.38 | [0.75, 2.21] | 85.6% | 11 | heating |

## Big-pharma momentum (top 5)

| Company | Ticker | THI | P(up) | Recent |
|---|---|---|---|---|
| ResMed | RMD | 2.35 | 98.5% | 8 |
| Olympus | OCPNY | 2.25 | 100.0% | 49 |
| ICU Medical | ICUI | 2.09 | 98.0% | 9 |
| Terumo | TRUMY | 1.85 | 98.3% | 13 |
| Teleflex | TFX | 1.7 | 95.5% | 11 |

## Portfolio migration

- Orthofix moved towards trauma: share 75% vs baseline 23% (+51.7pp).
- Tandem Diabetes moved towards insulin_delivery: share 33% vs baseline 80% (-46.7pp).
- Orthofix moved towards spine: share 0% vs baseline 43% (-43.3pp).
- Wl Gore moved towards neurovascular: share 0% vs baseline 33% (-33.3pp).

## First seen in the last 90 days

- 2026-10-02 · Ge Healthcare · imaging_mr_ct · GE Medical Systems Ultrasound & Primary Care Diagnostics, L…
- 2026-10-01 · Edwards Lifesciences · structural_heart · Edwards Lifesciences, LLC PMA 批准 P260007：Autus Size-Adjusta…
- 2026-09-24 · Karl Storz · endoscopy · Karl Storz SE & CO. KG 510(k)：KARL STORZ SUPRALOOP
- 2026-09-23 · Teleflex · __untracked__ · Teleflex Medical 510(k)：Liquick X-treme, Liquick X-treme Pl…
- 2026-09-18 · Icu Medical · __untracked__ · ICU Medical 510(k)：NORMOFLO Irrigation Fluid Warming Sets …

## Recall clusters

| Company | Recalls in window | Baseline / quarter | Top reason |
|---|---|---|---|
| Medline | 101 | 3.70 | Medline Industries, LP is issuing a recall for specific item |
| Philips | 87 | 6.15 | To provide clarification and labelling to define the useful |
| Bd | 64 | 3.50 | Infusion pump module used with compatible  pump infusion set |
| Medtronic | 63 | 6.50 | The device cap label may not adhere to the sensor, compromis |
| Ge Healthcare | 45 | 3.35 | GE HealthCare has become aware that certain Nuclear Medicine |

## Drug side

Top NDA/BLA momentum: Ionis Pharmaceuticals (THI 3.91), Daiichi Sankyo (THI 3.91), Otsuka (THI 3.91), Sanofi (THI 2.09), Boehringer Ingelheim (THI 2.09).
Hottest therapeutic areas: t_vaccines (P 100.0%), t_dermatology (P 100.0%), t_cardiometabolic (P 100.0%), t_neuroscience (P 100.0%).
Trial starts: Novartis (暂无数据), Pfizer (暂无数据), AstraZeneca (暂无数据), Eli Lilly (暂无数据), Merck & Co. (暂无数据).

## China gap

**Unavailable (NMPA data not loaded).** China registration counts are `null`, not zero; no China-vs-US gap is inferred for this run.

## Signals and paper trading

- Signals generated: 303
- Paper portfolio: total return +20.6%, max drawdown -6.6%, win rate 74.4%, trades 39.
- Equity curve: 48 trading days, 2025-11-21 to 2026-10-30.

## Replay and research hygiene

- Replay: 60 steps from 2025-11-01 to 2026-10-31; multi-cost summary for 3 cost buckets.
- Timestamp quality: date 83,578; excluded from trading: 0.
- Multiple testing: holm correction over 24 tests.
- Survivorship flags: 4.
- Assumption register: `docs/ASSUMPTIONS.md`.


## Method and limitations

- Data lag of 2-12 days; rates are computed on the earliest public date (`event_date`) to limit look-ahead bias.
- Company attribution is alias-based fuzzy matching: false negatives are kept visible, false positives are bounded.
- Approvals are a regulatory activity proxy, not R&D spend or revenue.
- Small samples are shrunk with a Gamma-Poisson empirical-Bayes prior; read THI together with its 95% interval.
- Track mapping is a curated product-code / keyword dictionary and can misclassify edge cases.
- NMPA data are never imputed: unavailable stays `null` and is reported as unavailable.

## Disclaimer

This report is generated automatically for open-source research and engineering demonstration only. It is **not investment advice**, not a recommendation and not an offer to trade. Public data may be delayed, incomplete or inconsistent; verify the original sources before any decision.
