# Merit Medical — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Merit Medical: 5 resolved legal entities from 3 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 25 material events across 6 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 9 | 2017-04 | 2024-05 | 36% | sufficient |
| coronary | 8 | 2017-03 | 2024-12 | 32% | sufficient |
| peripheral_vascular | 3 | 2017-12 | 2021-11 | 12% | sufficient |
| endoscopy | 2 | 2019-10 | 2022-03 | 8% | sufficient |
| dialysis | 2 | 2021-12 | 2024-12 | 8% | sufficient |
| patient_monitoring | 1 | 2023-03 | 2023-03 | 4% | single event |

## 3. Momentum

- no detectable change: 13 events in the last 24 months vs 11 before (ratio 1.18), p=0.839; minimum detectable ratio at 80% power is 3.15x
- Test: exact two-sided binomial p=0.839 (alpha=0.05), minimum detectable ratio at 80 % power 3.15x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 36% of 25 material events across 6 tracks (HHI 0.26)

## 5. Independent corroboration

- 0 of 6 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: coronary, dialysis, endoscopy, patient_monitoring, peripheral_vascular, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 45 of 98 months (54% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: patient_monitoring — a single filing is an anecdote; treat these tracks as unconfirmed

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
