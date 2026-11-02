# STERIS — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- STERIS: 4 resolved legal entities from 2 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 35 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 17 | 2018-04 | 2022-09 | 49% | sufficient |
| infection_control | 15 | 2017-03 | 2022-09 | 43% | sufficient |
| surgical_energy | 2 | 2022-08 | 2022-12 | 6% | sufficient |
| urology | 1 | 2021-11 | 2021-11 | 3% | single event |

## 3. Momentum

- no detectable change: 24 events in the last 24 months vs 29 before (ratio 0.83), p=0.583; minimum detectable ratio at 80% power is 2.17x
- Test: exact two-sided binomial p=0.583 (alpha=0.05), minimum detectable ratio at 80 % power 2.17x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 49% of 35 material events across 4 tracks (HHI 0.42)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: endoscopy, infection_control, surgical_energy, urology

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: urology — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
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
