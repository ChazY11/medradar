# Invacare — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Invacare: 1 resolved legal entities from 2 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 8 material events across 1 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| rehab_exo | 8 | 2016-12 | 2020-01 | 100% | sufficient |

## 3. Momentum

- no detectable change: 3 events in the last 24 months vs 4 before (ratio 0.75), p=1.000; minimum detectable ratio at 80% power is 8.50x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 8.50x, detected=False

## 4. Concentration

- highly concentrated: top track rehab_exo holds 100% of 8 material events across 1 tracks (HHI 1.00)

## 5. Independent corroboration

- 0 of 1 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: rehab_exo

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 8 of 50 months (84% silent) — monthly series are mostly zeros; rate estimates are unstable
- `activity_decline_by_track`: rehab_exo: 1 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

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
