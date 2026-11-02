# Stryker — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Stryker: 26 resolved legal entities from 11 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 284 material events across 18 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 83 | 2017-02 | 2026-08 | 29% | sufficient |
| trauma | 57 | 2017-02 | 2026-07 | 20% | sufficient |
| endoscopy | 38 | 2016-11 | 2026-07 | 13% | sufficient |
| surgical_energy | 21 | 2017-02 | 2026-09 | 7% | sufficient |
| spine | 20 | 2016-11 | 2026-07 | 7% | sufficient |
| neurovascular | 19 | 2018-03 | 2026-06 | 7% | sufficient |
| vascular_access | 11 | 2019-11 | 2026-07 | 4% | sufficient |
| general_surgery | 9 | 2019-04 | 2025-03 | 3% | sufficient |
| medical_ai | 6 | 2017-02 | 2026-03 | 2% | sufficient |
| imaging_mr_ct | 4 | 2018-12 | 2026-05 | 1% | sufficient |
| patient_monitoring | 4 | 2022-03 | 2024-10 | 1% | sufficient |
| wound_care | 2 | 2016-11 | 2026-07 | 1% | sufficient |
| ep_pfa | 2 | 2019-01 | 2020-05 | 1% | sufficient |
| coronary | 2 | 2019-05 | 2020-09 | 1% | sufficient |
| imaging_us | 2 | 2019-05 | 2023-07 | 1% | sufficient |
| urology | 2 | 2024-02 | 2025-07 | 1% | sufficient |
| cmf | 1 | 2018-09 | 2018-09 | 0% | single event |
| cardiac_rhythm | 1 | 2024-04 | 2024-04 | 0% | single event |

## 3. Momentum

- no detectable change: 76 events in the last 24 months vs 75 before (ratio 1.01), p=1.000; minimum detectable ratio at 80% power is 1.58x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 1.58x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 3 calibrated alert(s) in the last 8 quarters across 2 track(s) (103 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `neurovascular` 2025-Q4: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **promote_pending_signoff** — shape ramp (post-alert rate is elevated and still rising); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `vascular_access` 2024-Q4: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `vascular_access` 2025-Q1: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **reject** — shape spike (post-alert rate 0.00x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- diversified: top track ortho_joint holds 29% of 284 material events across 18 tracks (HHI 0.16)

## 5. Independent corroboration

- 5 of 18 technology tracks have independent device-trial support; 13 do not
- Tracks with **no** trial support: cardiac_rhythm, cmf, coronary, ep_pfa, imaging_mr_ct, imaging_us, medical_ai, spine

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: cardiac_rhythm, cmf — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: spine: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: medical_ai: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
- Hiring evidence: 8839 archived postings across 90 months (posting-flow proxy, not headcount)
- What would change the conclusion:
  - a sustained activity change beyond the detector's measured minimum detectable effect
  - independent evidence (trials, hiring, publications) that contradicts the track reading
  - taxonomy changes that reclassify existing activity into new product codes
  - entity-resolution changes that move filings between legal entities
- Known limits:
  - a detection is a statement about public regulatory activity rate, never about intent, capability or internal R&D
  - the lane holds ~0.2 events per cell-month, so monthly per-track rates are noisy
  - product-code taxonomy is not versioned by effective date
  - the final month of the window is partially observed
