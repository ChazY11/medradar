# Cook Medical — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Cook Medical: 11 resolved legal entities from 5 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 90 material events across 11 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 31 | 2017-05 | 2021-07 | 34% | sufficient |
| endoscopy | 22 | 2017-04 | 2022-04 | 24% | sufficient |
| coronary | 16 | 2016-12 | 2022-02 | 18% | sufficient |
| urology | 5 | 2018-02 | 2018-06 | 6% | sufficient |
| dental | 4 | 2017-01 | 2018-07 | 4% | sufficient |
| surgical_energy | 4 | 2017-08 | 2020-01 | 4% | sufficient |
| peripheral_vascular | 2 | 2017-02 | 2020-10 | 2% | sufficient |
| respiratory | 2 | 2017-02 | 2017-08 | 2% | sufficient |
| imaging_us | 2 | 2017-08 | 2018-07 | 2% | sufficient |
| dialysis | 1 | 2017-01 | 2017-01 | 1% | single event |
| neurovascular | 1 | 2018-12 | 2018-12 | 1% | single event |

## 3. Momentum

- activity decreasing: 11 events in the last 24 months vs 42 before (ratio 0.26), exact two-sided p=0.000
- Test: exact two-sided binomial p=0.000 (alpha=0.05), minimum detectable ratio at 80 % power 2.58x, detected=True

## 4. Concentration

- diversified: top track vascular_access holds 34% of 90 material events across 11 tracks (HHI 0.22)

## 5. Independent corroboration

- 1 of 11 technology tracks have independent device-trial support; 10 do not
- Tracks with **no** trial support: coronary, dental, dialysis, endoscopy, imaging_us, neurovascular, respiratory, surgical_energy

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: dialysis, neurovascular — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: coronary: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: endoscopy: 2 events in the last 24 months vs 10 before — this track is retreating, which cuts against a growth reading

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
