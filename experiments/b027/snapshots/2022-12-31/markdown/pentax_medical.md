# Pentax Medical — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Pentax Medical: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 15 material events across 2 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 12 | 2018-01 | 2022-12 | 80% | sufficient |
| surgical_energy | 3 | 2019-05 | 2021-11 | 20% | sufficient |

## 3. Momentum

- no detectable change: 10 events in the last 24 months vs 16 before (ratio 0.63), p=0.327; minimum detectable ratio at 80% power is 3.09x
- Test: exact two-sided binomial p=0.327 (alpha=0.05), minimum detectable ratio at 80 % power 3.09x, detected=False

## 4. Concentration

- highly concentrated: top track endoscopy holds 80% of 15 material events across 2 tracks (HHI 0.68)

## 5. Independent corroboration

- 1 of 2 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: endoscopy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 24 of 74 months (68% silent) — monthly series are mostly zeros; rate estimates are unstable
- `activity_decline_by_track`: endoscopy: 3 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

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
