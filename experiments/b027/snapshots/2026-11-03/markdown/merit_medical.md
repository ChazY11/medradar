# Merit Medical — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Merit Medical: 5 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 32 material events across 7 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| coronary | 13 | 2017-03 | 2026-07 | 41% | sufficient |
| vascular_access | 10 | 2017-04 | 2025-04 | 31% | sufficient |
| peripheral_vascular | 3 | 2017-12 | 2021-11 | 9% | sufficient |
| endoscopy | 2 | 2019-10 | 2022-03 | 6% | sufficient |
| dialysis | 2 | 2021-12 | 2024-12 | 6% | sufficient |
| patient_monitoring | 1 | 2023-03 | 2023-03 | 3% | single event |
| wound_care | 1 | 2026-05 | 2026-05 | 3% | single event |

## 3. Momentum

- no detectable change: 18 events in the last 24 months vs 11 before (ratio 1.64), p=0.265; minimum detectable ratio at 80% power is 2.92x
- Test: exact two-sided binomial p=0.265 (alpha=0.05), minimum detectable ratio at 80 % power 2.92x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 1 calibrated alert(s) in the last 8 quarters across 1 track(s) (26 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `coronary` 2026-Q1: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track coronary holds 41% of 32 material events across 7 tracks (HHI 0.28)

## 5. Independent corroboration

- 0 of 7 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: coronary, dialysis, endoscopy, patient_monitoring, peripheral_vascular, vascular_access, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 56 of 119 months (53% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: patient_monitoring, wound_care — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
- Hiring evidence: no archived hiring board found for this company (coverage absence, not zero hiring)
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
