# STERIS — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- STERIS: 4 resolved legal entities from 2 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 60 material events across 4 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 33 | 2018-04 | 2025-04 | 55% | sufficient |
| infection_control | 20 | 2017-03 | 2026-06 | 33% | sufficient |
| surgical_energy | 4 | 2022-08 | 2025-04 | 7% | sufficient |
| urology | 3 | 2021-11 | 2023-07 | 5% | sufficient |

## 3. Momentum

- activity decreasing: 18 events in the last 24 months vs 36 before (ratio 0.50), exact two-sided p=0.020
- Test: exact two-sided binomial p=0.020 (alpha=0.05), minimum detectable ratio at 80 % power 2.25x, detected=True

## 4. Concentration

- moderately concentrated: top track endoscopy holds 55% of 60 material events across 4 tracks (HHI 0.42)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: endoscopy, infection_control, surgical_energy, urology

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `activity_decline_by_track`: endoscopy: 5 events in the last 24 months vs 11 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
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
