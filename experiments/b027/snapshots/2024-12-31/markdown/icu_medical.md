# ICU Medical — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- ICU Medical: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 8 material events across 4 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 4 | 2017-07 | 2020-09 | 50% | sufficient |
| patient_monitoring | 2 | 2017-05 | 2017-11 | 25% | sufficient |
| wearable_remote | 1 | 2017-08 | 2017-08 | 12% | single event |
| medical_ai | 1 | 2023-08 | 2023-08 | 12% | single event |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 2 before (ratio 2.00), p=0.688; minimum detectable ratio at 80% power is 11.32x
- Test: exact two-sided binomial p=0.688 (alpha=0.05), minimum detectable ratio at 80 % power 11.32x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 50% of 8 material events across 4 tracks (HHI 0.34)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: medical_ai, patient_monitoring, vascular_access, wearable_remote

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 20 of 98 months (80% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: medical_ai, wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
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
