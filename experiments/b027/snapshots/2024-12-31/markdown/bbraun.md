# B. Braun — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- B. Braun: 8 resolved legal entities from 4 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 38 material events across 10 technology tracks (5 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 17 | 2017-04 | 2024-07 | 45% | sufficient |
| wound_care | 5 | 2016-11 | 2018-03 | 13% | sufficient |
| spine | 5 | 2016-12 | 2023-07 | 13% | sufficient |
| neurovascular | 3 | 2017-11 | 2021-12 | 8% | sufficient |
| surgical_energy | 3 | 2019-03 | 2020-12 | 8% | sufficient |
| coronary | 1 | 2017-06 | 2017-06 | 3% | single event |
| endoscopy | 1 | 2018-02 | 2018-02 | 3% | single event |
| ortho_joint | 1 | 2018-03 | 2018-03 | 3% | single event |
| imaging_mr_ct | 1 | 2021-01 | 2021-01 | 3% | single event |
| dialysis | 1 | 2024-12 | 2024-12 | 3% | single event |

## 3. Momentum

- no detectable change: 8 events in the last 24 months vs 13 before (ratio 0.62), p=0.383; minimum detectable ratio at 80% power is 3.52x
- Test: exact two-sided binomial p=0.383 (alpha=0.05), minimum detectable ratio at 80 % power 3.52x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 45% of 38 material events across 10 tracks (HHI 0.25)

## 5. Independent corroboration

- 3 of 10 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: dialysis, endoscopy, imaging_mr_ct, spine, surgical_energy, vascular_access, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 5 track(s) rest on a single event: coronary, dialysis, endoscopy, imaging_mr_ct, ortho_joint — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: vascular_access: 2 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

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
