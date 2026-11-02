# iRhythm Technologies — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- iRhythm Technologies: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 8 material events across 2 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| medical_ai | 6 | 2018-08 | 2026-05 | 75% | sufficient |
| rehab_exo | 2 | 2017-06 | 2024-10 | 25% | sufficient |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 1 before (ratio 4.00), p=0.375; minimum detectable ratio at 80% power is 22.93x
- Test: exact two-sided binomial p=0.375 (alpha=0.05), minimum detectable ratio at 80 % power 22.93x, detected=False

## 4. Concentration

- highly concentrated: top track medical_ai holds 75% of 8 material events across 2 tracks (HHI 0.62)

## 5. Independent corroboration

- 0 of 2 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: medical_ai, rehab_exo

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 9 of 119 months (92% silent) — monthly series are mostly zeros; rate estimates are unstable

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
