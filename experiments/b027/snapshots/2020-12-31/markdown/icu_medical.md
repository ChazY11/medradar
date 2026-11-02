# ICU Medical — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- ICU Medical: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 7 material events across 3 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 4 | 2017-07 | 2020-09 | 57% | sufficient |
| patient_monitoring | 2 | 2017-05 | 2017-11 | 29% | sufficient |
| wearable_remote | 1 | 2017-08 | 2017-08 | 14% | single event |

## 3. Momentum

- activity decreasing: 5 events in the last 24 months vs 16 before (ratio 0.31), exact two-sided p=0.027
- Test: exact two-sided binomial p=0.027 (alpha=0.05), minimum detectable ratio at 80 % power 4.20x, detected=True

## 4. Concentration

- moderately concentrated: top track vascular_access holds 57% of 7 material events across 3 tracks (HHI 0.43)

## 5. Independent corroboration

- 0 of 3 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: patient_monitoring, vascular_access, wearable_remote

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 15 of 50 months (70% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
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
