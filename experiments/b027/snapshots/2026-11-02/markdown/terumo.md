# Terumo — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Terumo: 11 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 25 material events across 7 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 11 | 2017-07 | 2025-12 | 44% | sufficient |
| coronary | 6 | 2017-01 | 2026-03 | 24% | sufficient |
| peripheral_vascular | 3 | 2023-09 | 2026-07 | 12% | sufficient |
| ivd_poct | 2 | 2018-11 | 2024-04 | 8% | sufficient |
| ophthalmology | 1 | 2023-10 | 2023-10 | 4% | single event |
| imaging_us | 1 | 2025-07 | 2025-07 | 4% | single event |
| insulin_delivery | 1 | 2025-11 | 2025-11 | 4% | single event |

## 3. Momentum

- no detectable change: 11 events in the last 24 months vs 7 before (ratio 1.57), p=0.481; minimum detectable ratio at 80% power is 3.88x
- Test: exact two-sided binomial p=0.481 (alpha=0.05), minimum detectable ratio at 80 % power 3.88x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 44% of 25 material events across 7 tracks (HHI 0.28)

## 5. Independent corroboration

- 1 of 7 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: coronary, imaging_us, insulin_delivery, ivd_poct, ophthalmology, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 39 of 119 months (67% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 3 track(s) rest on a single event: imaging_us, insulin_delivery, ophthalmology — a single filing is an anecdote; treat these tracks as unconfirmed

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
