# Dexcom — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Dexcom: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 14 material events across 1 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| diabetes_cgm | 14 | 2016-12 | 2022-12 | 100% | sufficient |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 6 before (ratio 0.67), p=0.754; minimum detectable ratio at 80% power is 6.10x
- Test: exact two-sided binomial p=0.754 (alpha=0.05), minimum detectable ratio at 80 % power 6.10x, detected=False

## 4. Concentration

- highly concentrated: top track diabetes_cgm holds 100% of 14 material events across 1 tracks (HHI 1.00)

## 5. Independent corroboration

- 1 of 1 technology tracks have independent device-trial support; 0 do not

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 13 of 74 months (82% silent) — monthly series are mostly zeros; rate estimates are unstable

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
- Hiring evidence: 1259 archived postings across 47 months (posting-flow proxy, not headcount)
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
