# Fujifilm — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Fujifilm: 10 resolved legal entities from 4 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 56 material events across 3 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 31 | 2017-03 | 2022-11 | 55% | sufficient |
| imaging_mr_ct | 17 | 2017-03 | 2022-11 | 30% | sufficient |
| imaging_us | 8 | 2017-06 | 2022-04 | 14% | sufficient |

## 3. Momentum

- no detectable change: 19 events in the last 24 months vs 32 before (ratio 0.59), p=0.092; minimum detectable ratio at 80% power is 2.25x
- Test: exact two-sided binomial p=0.092 (alpha=0.05), minimum detectable ratio at 80 % power 2.25x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 55% of 56 material events across 3 tracks (HHI 0.42)

## 5. Independent corroboration

- 1 of 3 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: imaging_mr_ct, imaging_us

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `activity_decline_by_track`: imaging_us: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

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
