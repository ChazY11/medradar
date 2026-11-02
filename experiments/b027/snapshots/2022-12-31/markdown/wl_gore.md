# W. L. Gore & Associates — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- W. L. Gore & Associates: 2 resolved legal entities from 5 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 5 material events across 3 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| neurovascular | 3 | 2018-11 | 2022-05 | 60% | sufficient |
| vascular_access | 1 | 2018-01 | 2018-01 | 20% | single event |
| structural_heart | 1 | 2018-03 | 2018-03 | 20% | single event |

## 3. Momentum

- no detectable change: 2 events in the last 24 months vs 2 before (ratio 1.00), p=1.000; minimum detectable ratio at 80% power is 16.47x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 16.47x, detected=False

## 4. Concentration

- moderately concentrated: top track neurovascular holds 60% of 5 material events across 3 tracks (HHI 0.44)

## 5. Independent corroboration

- 0 of 3 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: neurovascular, structural_heart, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 13 of 74 months (82% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: structural_heart, vascular_access — a single filing is an anecdote; treat these tracks as unconfirmed

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
