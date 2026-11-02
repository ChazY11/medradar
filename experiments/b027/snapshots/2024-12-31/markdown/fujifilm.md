# Fujifilm — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Fujifilm: 10 resolved legal entities from 4 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 76 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 39 | 2017-03 | 2024-11 | 51% | sufficient |
| imaging_mr_ct | 25 | 2017-03 | 2024-08 | 33% | sufficient |
| imaging_us | 11 | 2017-06 | 2023-12 | 14% | sufficient |
| medical_ai | 1 | 2023-12 | 2023-12 | 1% | single event |

## 3. Momentum

- no detectable change: 25 events in the last 24 months vs 19 before (ratio 1.32), p=0.451; minimum detectable ratio at 80% power is 2.35x
- Test: exact two-sided binomial p=0.451 (alpha=0.05), minimum detectable ratio at 80 % power 2.35x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 51% of 76 material events across 4 tracks (HHI 0.39)

## 5. Independent corroboration

- 1 of 4 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: imaging_mr_ct, imaging_us, medical_ai

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: medical_ai — a single filing is an anecdote; treat these tracks as unconfirmed

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
