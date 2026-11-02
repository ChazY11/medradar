# Penumbra — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Penumbra: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 23 material events across 3 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| neurovascular | 11 | 2017-04 | 2020-08 | 48% | sufficient |
| peripheral_vascular | 10 | 2017-05 | 2020-11 | 43% | sufficient |
| endoscopy | 2 | 2017-08 | 2019-08 | 9% | sufficient |

## 3. Momentum

- no detectable change: 14 events in the last 24 months vs 11 before (ratio 1.27), p=0.690; minimum detectable ratio at 80% power is 3.09x
- Test: exact two-sided binomial p=0.690 (alpha=0.05), minimum detectable ratio at 80 % power 3.09x, detected=False

## 4. Concentration

- moderately concentrated: top track neurovascular holds 48% of 23 material events across 3 tracks (HHI 0.43)

## 5. Independent corroboration

- 1 of 3 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: endoscopy, neurovascular

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 23 of 50 months (54% silent) — monthly series are mostly zeros; rate estimates are unstable

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
