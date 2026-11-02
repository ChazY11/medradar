# Karl Storz — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Karl Storz: 3 resolved legal entities from 2 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 36 material events across 7 technology tracks (4 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 19 | 2017-03 | 2024-10 | 53% | sufficient |
| urology | 10 | 2017-07 | 2024-08 | 28% | sufficient |
| ent | 3 | 2019-03 | 2020-08 | 8% | sufficient |
| surgical_energy | 1 | 2017-08 | 2017-08 | 3% | single event |
| medical_ai | 1 | 2020-07 | 2020-07 | 3% | single event |
| imaging_mr_ct | 1 | 2020-12 | 2020-12 | 3% | single event |
| dental | 1 | 2023-09 | 2023-09 | 3% | single event |

## 3. Momentum

- no detectable change: 16 events in the last 24 months vs 13 before (ratio 1.23), p=0.711; minimum detectable ratio at 80% power is 2.85x
- Test: exact two-sided binomial p=0.711 (alpha=0.05), minimum detectable ratio at 80 % power 2.85x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 53% of 36 material events across 7 tracks (HHI 0.37)

## 5. Independent corroboration

- 0 of 7 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: dental, endoscopy, ent, imaging_mr_ct, medical_ai, surgical_energy, urology

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 47 of 98 months (52% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 4 track(s) rest on a single event: dental, imaging_mr_ct, medical_ai, surgical_energy — a single filing is an anecdote; treat these tracks as unconfirmed

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
