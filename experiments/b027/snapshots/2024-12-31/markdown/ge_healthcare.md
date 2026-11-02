# GE HealthCare — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- GE HealthCare: 24 resolved legal entities from 5 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 225 material events across 5 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 118 | 2016-11 | 2024-12 | 52% | sufficient |
| imaging_us | 72 | 2016-11 | 2024-12 | 32% | sufficient |
| patient_monitoring | 22 | 2017-05 | 2024-04 | 10% | sufficient |
| medical_ai | 10 | 2019-08 | 2024-12 | 4% | sufficient |
| respiratory | 3 | 2017-08 | 2021-10 | 1% | sufficient |

## 3. Momentum

- no detectable change: 49 events in the last 24 months vs 62 before (ratio 0.79), p=0.255; minimum detectable ratio at 80% power is 1.71x
- Test: exact two-sided binomial p=0.255 (alpha=0.05), minimum detectable ratio at 80 % power 1.71x, detected=False

## 4. Concentration

- moderately concentrated: top track imaging_mr_ct holds 52% of 225 material events across 5 tracks (HHI 0.39)

## 5. Independent corroboration

- 4 of 5 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: medical_ai

## 6. Contradictory evidence

- no contradictory observation found across the 4 checks run

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
- Hiring evidence: 1 archived postings across 1 months (posting-flow proxy, not headcount)
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
