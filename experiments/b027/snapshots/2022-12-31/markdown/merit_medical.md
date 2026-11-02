# Merit Medical — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Merit Medical: 5 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 19 material events across 5 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 7 | 2017-04 | 2022-01 | 37% | sufficient |
| coronary | 6 | 2017-03 | 2020-10 | 32% | sufficient |
| peripheral_vascular | 3 | 2017-12 | 2021-11 | 16% | sufficient |
| endoscopy | 2 | 2019-10 | 2022-03 | 11% | sufficient |
| dialysis | 1 | 2021-12 | 2021-12 | 5% | single event |

## 3. Momentum

- no detectable change: 11 events in the last 24 months vs 12 before (ratio 0.92), p=1.000; minimum detectable ratio at 80% power is 3.22x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 3.22x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 37% of 19 material events across 5 tracks (HHI 0.27)

## 5. Independent corroboration

- 0 of 5 technology tracks have independent device-trial support; 5 do not
- Tracks with **no** trial support: coronary, dialysis, endoscopy, peripheral_vascular, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 36 of 74 months (51% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: dialysis — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
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
