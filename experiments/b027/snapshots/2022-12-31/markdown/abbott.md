# Abbott — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Abbott: 26 resolved legal entities from 10 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 78 material events across 17 technology tracks (5 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| medical_ai | 18 | 2016-12 | 2022-12 | 23% | sufficient |
| ivd_molecular | 10 | 2017-05 | 2022-07 | 13% | sufficient |
| diabetes_cgm | 9 | 2017-09 | 2022-05 | 12% | sufficient |
| coronary | 8 | 2017-08 | 2022-06 | 10% | sufficient |
| ep_pfa | 5 | 2017-02 | 2022-12 | 6% | sufficient |
| heart_failure | 4 | 2017-08 | 2022-02 | 5% | sufficient |
| imaging_us | 4 | 2019-04 | 2022-12 | 5% | sufficient |
| vascular_access | 4 | 2019-04 | 2021-07 | 5% | sufficient |
| cardiac_rhythm | 3 | 2016-11 | 2022-03 | 4% | sufficient |
| structural_heart | 3 | 2019-03 | 2021-09 | 4% | sufficient |
| ivd_immuno | 3 | 2019-09 | 2022-08 | 4% | sufficient |
| peripheral_vascular | 2 | 2018-02 | 2022-05 | 3% | sufficient |
| ophthalmology | 1 | 2017-05 | 2017-05 | 1% | single event |
| neurovascular | 1 | 2019-07 | 2019-07 | 1% | single event |
| neurostimulation | 1 | 2020-01 | 2020-01 | 1% | single event |
| ivd_poct | 1 | 2020-04 | 2020-04 | 1% | single event |
| respiratory | 1 | 2022-12 | 2022-12 | 1% | single event |

## 3. Momentum

- no detectable change: 52 events in the last 24 months vs 39 before (ratio 1.33), p=0.208; minimum detectable ratio at 80% power is 1.81x
- Test: exact two-sided binomial p=0.208 (alpha=0.05), minimum detectable ratio at 80 % power 1.81x, detected=False

## 4. Concentration

- diversified: top track medical_ai holds 23% of 78 material events across 17 tracks (HHI 0.11)

## 5. Independent corroboration

- 9 of 17 technology tracks have independent device-trial support; 8 do not
- Tracks with **no** trial support: coronary, ep_pfa, ivd_molecular, ivd_poct, medical_ai, neurovascular, ophthalmology, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 5 track(s) rest on a single event: ivd_poct, neurostimulation, neurovascular, ophthalmology, respiratory — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: vascular_access: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
- Hiring evidence: 566 archived postings across 34 months (posting-flow proxy, not headcount)
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
