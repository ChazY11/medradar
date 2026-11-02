# B. Braun — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- B. Braun: 8 resolved legal entities from 4 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 34 material events across 9 technology tracks (4 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 15 | 2017-04 | 2022-06 | 44% | sufficient |
| wound_care | 5 | 2016-11 | 2018-03 | 15% | sufficient |
| spine | 4 | 2016-12 | 2022-07 | 12% | sufficient |
| neurovascular | 3 | 2017-11 | 2021-12 | 9% | sufficient |
| surgical_energy | 3 | 2019-03 | 2020-12 | 9% | sufficient |
| coronary | 1 | 2017-06 | 2017-06 | 3% | single event |
| endoscopy | 1 | 2018-02 | 2018-02 | 3% | single event |
| ortho_joint | 1 | 2018-03 | 2018-03 | 3% | single event |
| imaging_mr_ct | 1 | 2021-01 | 2021-01 | 3% | single event |

## 3. Momentum

- no detectable change: 13 events in the last 24 months vs 19 before (ratio 0.68), p=0.377; minimum detectable ratio at 80% power is 2.74x
- Test: exact two-sided binomial p=0.377 (alpha=0.05), minimum detectable ratio at 80 % power 2.74x, detected=False

## 4. Concentration

- diversified: top track vascular_access holds 44% of 34 material events across 9 tracks (HHI 0.25)

## 5. Independent corroboration

- 1 of 9 technology tracks have independent device-trial support; 8 do not
- Tracks with **no** trial support: coronary, endoscopy, imaging_mr_ct, neurovascular, spine, surgical_energy, vascular_access, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 4 track(s) rest on a single event: coronary, endoscopy, imaging_mr_ct, ortho_joint — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: surgical_energy: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

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
