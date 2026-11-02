# ResMed — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- ResMed: 2 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 9 material events across 1 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| respiratory | 9 | 2016-11 | 2020-12 | 100% | sufficient |

## 3. Momentum

- no detectable change: 2 events in the last 24 months vs 5 before (ratio 0.40), p=0.453; minimum detectable ratio at 80% power is 10.42x
- Test: exact two-sided binomial p=0.453 (alpha=0.05), minimum detectable ratio at 80 % power 10.42x, detected=False

## 4. Concentration

- highly concentrated: top track respiratory holds 100% of 9 material events across 1 tracks (HHI 1.00)

## 5. Independent corroboration

- 1 of 1 technology tracks have independent device-trial support; 0 do not

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 9 of 50 months (82% silent) — monthly series are mostly zeros; rate estimates are unstable
- `activity_decline_by_track`: respiratory: 2 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

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
