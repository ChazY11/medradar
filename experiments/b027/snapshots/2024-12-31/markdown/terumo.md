# Terumo — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Terumo: 11 resolved legal entities from 4 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 18 material events across 5 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 9 | 2017-07 | 2023-06 | 50% | sufficient |
| coronary | 5 | 2017-01 | 2024-11 | 28% | sufficient |
| ivd_poct | 2 | 2018-11 | 2024-04 | 11% | sufficient |
| peripheral_vascular | 1 | 2023-09 | 2023-09 | 6% | single event |
| ophthalmology | 1 | 2023-10 | 2023-10 | 6% | single event |

## 3. Momentum

- no detectable change: 8 events in the last 24 months vs 6 before (ratio 1.33), p=0.791; minimum detectable ratio at 80% power is 4.54x
- Test: exact two-sided binomial p=0.791 (alpha=0.05), minimum detectable ratio at 80 % power 4.54x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 50% of 18 material events across 5 tracks (HHI 0.35)

## 5. Independent corroboration

- 1 of 5 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: coronary, ivd_poct, ophthalmology, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 32 of 98 months (67% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: ophthalmology, peripheral_vascular — a single filing is an anecdote; treat these tracks as unconfirmed

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
