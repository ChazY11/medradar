# Tandem Diabetes Care — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Tandem Diabetes Care: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 5 material events across 2 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| insulin_delivery | 4 | 2018-06 | 2020-06 | 80% | sufficient |
| diabetes_cgm | 1 | 2017-08 | 2017-08 | 20% | single event |

## 3. Momentum

- no detectable change: 5 events in the last 24 months vs 2 before (ratio 2.50), p=0.453; minimum detectable ratio at 80% power is 10.42x
- Test: exact two-sided binomial p=0.453 (alpha=0.05), minimum detectable ratio at 80 % power 10.42x, detected=False

## 4. Concentration

- highly concentrated: top track insulin_delivery holds 80% of 5 material events across 2 tracks (HHI 0.68)

## 5. Independent corroboration

- 0 of 2 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: diabetes_cgm, insulin_delivery

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 6 of 50 months (88% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: diabetes_cgm — a single filing is an anecdote; treat these tracks as unconfirmed

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
