# Dräger — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Dräger: 5 resolved legal entities from 4 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 4 material events across 2 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| patient_monitoring | 3 | 2020-08 | 2022-02 | 75% | sufficient |
| respiratory | 1 | 2019-01 | 2019-01 | 25% | single event |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 3 before (ratio 1.33), p=1.000; minimum detectable ratio at 80% power is 8.50x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 8.50x, detected=False

## 4. Concentration

- highly concentrated: top track patient_monitoring holds 75% of 4 material events across 2 tracks (HHI 0.62)

## 5. Independent corroboration

- 0 of 2 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: patient_monitoring, respiratory

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 11 of 74 months (85% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: respiratory — a single filing is an anecdote; treat these tracks as unconfirmed

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
