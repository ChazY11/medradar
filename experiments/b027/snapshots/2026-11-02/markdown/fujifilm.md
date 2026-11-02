# Fujifilm — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Fujifilm: 10 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 102 material events across 4 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 48 | 2017-03 | 2026-07 | 47% | sufficient |
| imaging_mr_ct | 32 | 2017-03 | 2026-09 | 31% | sufficient |
| imaging_us | 16 | 2017-06 | 2026-08 | 16% | sufficient |
| medical_ai | 6 | 2023-12 | 2026-08 | 6% | sufficient |

## 3. Momentum

- no detectable change: 31 events in the last 24 months vs 25 before (ratio 1.24), p=0.504; minimum detectable ratio at 80% power is 2.12x
- Test: exact two-sided binomial p=0.504 (alpha=0.05), minimum detectable ratio at 80 % power 2.12x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 47% of 102 material events across 4 tracks (HHI 0.35)

## 5. Independent corroboration

- 2 of 4 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: imaging_us, medical_ai

## 6. Contradictory evidence

- no contradictory observation found across the 4 checks run

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
