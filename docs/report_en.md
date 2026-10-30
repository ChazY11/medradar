# MedRadar: FDA Device & Drug Industry Radar

_Generated 2026-10-31T02:10:00Z (UTC) · Window 2024-11-01 to 2026-10-31 (8 quarters) · Baseline 2021-11-01 to 2024-10-31 (20 quarters)_

## Key takeaways

1. Top device track: Electrophysiology / PFA (THI 4.8, P(up) 99.7%), 42 events in window vs 1.1/quarter baseline.
2. 4 of 6 tracked device segments are in a heating-up regime (THI 95% CI above 1.0).
3. Strongest big-pharma momentum: Intuitive Surgical (THI 1.88), Boston Scientific (THI 1.53), Abbott (THI 1.25). Regulatory cadence is a proxy, not revenue.
4. 4 first-seen records in the last 90 days; latest: Medtronic into ep_pfa.
5. Recall clusters: Philips (3), Spine Frontier (2), Medtronic (2); watch product-line ageing and software-related causes.

## Data status

- Device / drug / trials: `ok`, `ok`, `ok`
- NMPA (China registrations): `unavailable` - **unavailable (NMPA data not loaded)**; China-gap numbers are not inferred.
- Prices: `partial`
- Events in window: 1,302

## Hottest device tracks

| # | Track | THI | 95% CI | P(up) | Recent | Trend |
|---|---|---|---|---|---|---|
| 1 | Electrophysiology / PFA | 4.8 | [3.1, 6.9] | 99.7% | 42 | heating |
| 2 | Surgical Robotics | 2.77 | [1.9, 3.9] | 97.8% | 31 | heating |
| 3 | CGM | 1.78 | [1.2, 2.5] | 91.0% | 27 | heating |
| 4 | Structural Heart | 1.25 | [0.95, 1.6] | 74.0% | 36 | heating |
| 5 | Spine & Orthopedics | 1.04 | [0.85, 1.28] | 55.0% | 44 | steady |
| 6 | Imaging & Diagnostics | 0.77 | [0.55, 0.98] | 21.0% | 19 | cooling |

## Big-pharma momentum (top 5)

| Company | Ticker | THI | P(up) | Recent |
|---|---|---|---|---|
| Intuitive Surgical | ISRG | 1.88 | 93.0% | 9 |
| Boston Scientific | BSX | 1.53 | 81.0% | 11 |
| Abbott | ABT | 1.25 | 70.0% | 14 |
| Medtronic | MDT | 1.1 | 58.0% | 18 |
| Philips | PHG | 0.83 | 27.0% | 12 |

## Portfolio migration

- Intuitive Surgical moved towards surgical_robotics: share 35% vs baseline 12% (+23.0pp).
- Philips moved towards imaging: share 31% vs baseline 52% (-21.0pp).
- Boston Scientific moved towards ep_pfa: share 46% vs baseline 28% (+18.0pp).

## First seen in the last 90 days

- 2026-10-20 · Medtronic · ep_pfa · Pulsed Field Ablation System
- 2026-10-14 · Intuitive Surgical · surgical_robotics · da Vinci 6 Surgical System
- 2026-09-28 · Abbott · cgm · Glucose Monitoring Sensor
- 2026-08-30 · Boston Scientific · structural_heart · Transcatheter Valve Delivery Set

## Recall clusters

| Company | Recalls in window | Baseline / quarter | Top reason |
|---|---|---|---|
| Philips | 3 | 0.50 | Software |
| Spine Frontier | 2 | 0.30 | Labeling |
| Medtronic | 2 | 1.20 | Battery / power |

## Drug side

Top NDA/BLA momentum: Eli Lilly (THI 1.6), Novo Nordisk (THI 1.11), Merck (THI 0.94).
Hottest therapeutic areas: t_cardiometabolic (P 95.0%), t_oncology (P 70.0%), t_neuro (P 30.0%).
Trial starts: Novo Nordisk (19), Lilly (24), Merck (21).

## China gap

**Unavailable (NMPA data not loaded).** China registration counts are `null`, not zero; no China-vs-US gap is inferred for this run.

## Signals and paper trading

- Signals generated: 8
- Paper portfolio: total return +8.3%, max drawdown -6.1%, win rate 57.1%, trades 21.
- Equity curve: 22 trading days, 2026-01-05 to 2026-10-30.

## Method and limitations

- Data lag of 2-12 days; rates are computed on the earliest public date (`event_date`) to limit look-ahead bias.
- Company attribution is alias-based fuzzy matching: false negatives are kept visible, false positives are bounded.
- Approvals are a regulatory activity proxy, not R&D spend or revenue.
- Small samples are shrunk with a Gamma-Poisson empirical-Bayes prior; read THI together with its 95% interval.
- Track mapping is a curated product-code / keyword dictionary and can misclassify edge cases.
- NMPA data are never imputed: unavailable stays `null` and is reported as unavailable.

## Disclaimer

This report is generated automatically for open-source research and engineering demonstration only. It is **not investment advice**, not a recommendation and not an offer to trade. Public data may be delayed, incomplete or inconsistent; verify the original sources before any decision.
