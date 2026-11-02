# Smith & Nephew — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Smith & Nephew: 5 resolved legal entities from 4 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 63 material events across 4 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 28 | 2016-11 | 2020-10 | 44% | sufficient |
| trauma | 14 | 2016-11 | 2020-12 | 22% | sufficient |
| wound_care | 14 | 2017-04 | 2020-10 | 22% | sufficient |
| endoscopy | 7 | 2017-06 | 2020-07 | 11% | sufficient |

## 3. Momentum

- no detectable change: 29 events in the last 24 months vs 36 before (ratio 0.81), p=0.457; minimum detectable ratio at 80% power is 2.01x
- Test: exact two-sided binomial p=0.457 (alpha=0.05), minimum detectable ratio at 80 % power 2.01x, detected=False

## 4. Concentration

- moderately concentrated: top track ortho_joint holds 44% of 63 material events across 4 tracks (HHI 0.31)

## 5. Independent corroboration

- 2 of 4 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: endoscopy, ortho_joint

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `activity_decline_by_track`: ortho_joint: 8 events in the last 24 months vs 18 before — this track is retreating, which cuts against a growth reading

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
