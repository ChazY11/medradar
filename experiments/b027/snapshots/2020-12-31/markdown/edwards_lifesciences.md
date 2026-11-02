# Edwards Lifesciences — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Edwards Lifesciences: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 18 material events across 5 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| structural_heart | 7 | 2017-06 | 2020-09 | 39% | sufficient |
| patient_monitoring | 5 | 2018-03 | 2020-11 | 28% | sufficient |
| medical_ai | 4 | 2017-04 | 2019-08 | 22% | sufficient |
| wearable_remote | 1 | 2017-11 | 2017-11 | 6% | single event |
| vascular_access | 1 | 2020-03 | 2020-03 | 6% | single event |

## 3. Momentum

- no detectable change: 15 events in the last 24 months vs 13 before (ratio 1.15), p=0.851; minimum detectable ratio at 80% power is 2.89x
- Test: exact two-sided binomial p=0.851 (alpha=0.05), minimum detectable ratio at 80 % power 2.89x, detected=False

## 4. Concentration

- moderately concentrated: top track structural_heart holds 39% of 18 material events across 5 tracks (HHI 0.28)

## 5. Independent corroboration

- 1 of 5 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: medical_ai, patient_monitoring, vascular_access, wearable_remote

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 20 of 50 months (60% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: vascular_access, wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
- Hiring evidence: 40 archived postings across 14 months (posting-flow proxy, not headcount)
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
