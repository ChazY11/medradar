# STERIS — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- STERIS: 4 resolved legal entities from 2 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 55 material events across 4 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 31 | 2018-04 | 2024-12 | 56% | sufficient |
| infection_control | 18 | 2017-03 | 2023-10 | 33% | sufficient |
| urology | 3 | 2021-11 | 2023-07 | 5% | sufficient |
| surgical_energy | 3 | 2022-08 | 2024-05 | 5% | sufficient |

## 3. Momentum

- no detectable change: 40 events in the last 24 months vs 24 before (ratio 1.67), p=0.060; minimum detectable ratio at 80% power is 2.06x
- Test: exact two-sided binomial p=0.060 (alpha=0.05), minimum detectable ratio at 80 % power 2.06x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 56% of 55 material events across 4 tracks (HHI 0.43)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: endoscopy, infection_control, surgical_energy, urology

## 6. Contradictory evidence

- no contradictory observation found across the 4 checks run

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
