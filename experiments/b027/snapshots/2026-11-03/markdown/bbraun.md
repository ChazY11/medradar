# B. Braun — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- B. Braun: 8 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 41 material events across 11 technology tracks (6 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 19 | 2017-04 | 2026-05 | 46% | sufficient |
| wound_care | 5 | 2016-11 | 2018-03 | 12% | sufficient |
| spine | 5 | 2016-12 | 2023-07 | 12% | sufficient |
| neurovascular | 3 | 2017-11 | 2021-12 | 7% | sufficient |
| surgical_energy | 3 | 2019-03 | 2020-12 | 7% | sufficient |
| coronary | 1 | 2017-06 | 2017-06 | 2% | single event |
| endoscopy | 1 | 2018-02 | 2018-02 | 2% | single event |
| ortho_joint | 1 | 2018-03 | 2018-03 | 2% | single event |
| imaging_mr_ct | 1 | 2021-01 | 2021-01 | 2% | single event |
| dialysis | 1 | 2024-12 | 2024-12 | 2% | single event |
| urology | 1 | 2026-09 | 2026-09 | 2% | single event |

## 3. Momentum

- no detectable change: 5 events in the last 24 months vs 8 before (ratio 0.63), p=0.581; minimum detectable ratio at 80% power is 4.94x
- Test: exact two-sided binomial p=0.581 (alpha=0.05), minimum detectable ratio at 80 % power 4.94x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (19 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track vascular_access holds 46% of 41 material events across 11 tracks (HHI 0.26)

## 5. Independent corroboration

- 4 of 11 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: dialysis, endoscopy, imaging_mr_ct, surgical_energy, urology, vascular_access, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 53 of 119 months (55% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 6 track(s) rest on a single event: coronary, dialysis, endoscopy, imaging_mr_ct, ortho_joint — a single filing is an anecdote; treat these tracks as unconfirmed

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
