# Pentax Medical — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Pentax Medical: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 21 material events across 2 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 17 | 2018-01 | 2025-06 | 81% | sufficient |
| surgical_energy | 4 | 2019-05 | 2024-07 | 19% | sufficient |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 9 before (ratio 0.44), p=0.267; minimum detectable ratio at 80% power is 5.38x
- Test: exact two-sided binomial p=0.267 (alpha=0.05), minimum detectable ratio at 80 % power 5.38x, detected=False

## 4. Concentration

- highly concentrated: top track endoscopy holds 81% of 21 material events across 2 tracks (HHI 0.69)

## 5. Independent corroboration

- 1 of 2 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: endoscopy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 33 of 119 months (72% silent) — monthly series are mostly zeros; rate estimates are unstable
- `activity_decline_by_track`: endoscopy: 1 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

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
