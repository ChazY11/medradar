# W. L. Gore & Associates — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- W. L. Gore & Associates: 2 resolved legal entities from 5 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 7 material events across 4 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| neurovascular | 4 | 2018-11 | 2024-04 | 57% | sufficient |
| vascular_access | 1 | 2018-01 | 2018-01 | 14% | single event |
| structural_heart | 1 | 2018-03 | 2018-03 | 14% | single event |
| peripheral_vascular | 1 | 2025-12 | 2025-12 | 14% | single event |

## 3. Momentum

- no detectable change: 3 events in the last 24 months vs 7 before (ratio 0.43), p=0.344; minimum detectable ratio at 80% power is 6.91x
- Test: exact two-sided binomial p=0.344 (alpha=0.05), minimum detectable ratio at 80 % power 6.91x, detected=False

## 4. Concentration

- moderately concentrated: top track neurovascular holds 57% of 7 material events across 4 tracks (HHI 0.39)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: neurovascular, peripheral_vascular, structural_heart, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 21 of 119 months (82% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 3 track(s) rest on a single event: peripheral_vascular, structural_heart, vascular_access — a single filing is an anecdote; treat these tracks as unconfirmed

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
