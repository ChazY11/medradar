# Globus Medical — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Globus Medical: 3 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 69 material events across 5 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 31 | 2017-01 | 2022-12 | 45% | sufficient |
| trauma | 27 | 2017-03 | 2022-09 | 39% | sufficient |
| ortho_joint | 8 | 2017-08 | 2022-10 | 12% | sufficient |
| endoscopy | 2 | 2018-03 | 2019-04 | 3% | sufficient |
| imaging_mr_ct | 1 | 2021-08 | 2021-08 | 1% | single event |

## 3. Momentum

- no detectable change: 16 events in the last 24 months vs 27 before (ratio 0.59), p=0.126; minimum detectable ratio at 80% power is 2.42x
- Test: exact two-sided binomial p=0.126 (alpha=0.05), minimum detectable ratio at 80 % power 2.42x, detected=False

## 4. Concentration

- moderately concentrated: top track spine holds 45% of 69 material events across 5 tracks (HHI 0.37)

## 5. Independent corroboration

- 0 of 5 technology tracks have independent device-trial support; 5 do not
- Tracks with **no** trial support: endoscopy, imaging_mr_ct, ortho_joint, spine, trauma

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: trauma: 4 events in the last 24 months vs 8 before — this track is retreating, which cuts against a growth reading

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
