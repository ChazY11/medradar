# Tandem Diabetes Care — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Tandem Diabetes Care: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 6 material events across 2 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| insulin_delivery | 5 | 2018-06 | 2022-02 | 83% | sufficient |
| diabetes_cgm | 1 | 2017-08 | 2017-08 | 17% | single event |

## 3. Momentum

- no detectable change: 1 events in the last 24 months vs 5 before (ratio 0.20), p=0.219; minimum detectable ratio at 80% power is 21.52x
- Test: exact two-sided binomial p=0.219 (alpha=0.05), minimum detectable ratio at 80 % power 21.52x, detected=False

## 4. Concentration

- highly concentrated: top track insulin_delivery holds 83% of 6 material events across 2 tracks (HHI 0.72)

## 5. Independent corroboration

- 2 of 2 technology tracks have independent device-trial support; 0 do not

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 7 of 74 months (91% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: diabetes_cgm — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: insulin_delivery: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

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
