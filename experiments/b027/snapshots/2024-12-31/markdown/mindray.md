# Mindray — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Mindray: 2 resolved legal entities from 2 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 67 material events across 3 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_us | 48 | 2016-12 | 2024-11 | 72% | sufficient |
| patient_monitoring | 14 | 2017-08 | 2022-12 | 21% | sufficient |
| respiratory | 5 | 2018-01 | 2024-10 | 7% | sufficient |

## 3. Momentum

- no detectable change: 11 events in the last 24 months vs 19 before (ratio 0.58), p=0.200; minimum detectable ratio at 80% power is 2.89x
- Test: exact two-sided binomial p=0.200 (alpha=0.05), minimum detectable ratio at 80 % power 2.89x, detected=False

## 4. Concentration

- highly concentrated: top track imaging_us holds 72% of 67 material events across 3 tracks (HHI 0.56)

## 5. Independent corroboration

- 0 of 3 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: imaging_us, patient_monitoring, respiratory

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 48 of 98 months (51% silent) — monthly series are mostly zeros; rate estimates are unstable
- `activity_decline_by_track`: patient_monitoring: 0 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

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
