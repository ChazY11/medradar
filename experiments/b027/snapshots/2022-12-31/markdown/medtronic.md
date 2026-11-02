# Medtronic — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Medtronic: 30 resolved legal entities from 13 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 204 material events across 23 technology tracks (4 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 44 | 2016-11 | 2022-12 | 22% | sufficient |
| surgical_energy | 28 | 2016-11 | 2022-02 | 14% | sufficient |
| ortho_joint | 22 | 2017-04 | 2022-09 | 11% | sufficient |
| general_surgery | 16 | 2017-03 | 2022-11 | 8% | sufficient |
| ep_pfa | 9 | 2016-11 | 2022-12 | 4% | sufficient |
| peripheral_vascular | 9 | 2017-06 | 2021-12 | 4% | sufficient |
| medical_ai | 8 | 2017-03 | 2021-08 | 4% | sufficient |
| cardiac_rhythm | 7 | 2017-02 | 2020-05 | 3% | sufficient |
| coronary | 7 | 2017-04 | 2022-09 | 3% | sufficient |
| imaging_mr_ct | 7 | 2017-12 | 2020-04 | 3% | sufficient |
| vascular_access | 6 | 2016-11 | 2021-07 | 3% | sufficient |
| endoscopy | 6 | 2016-11 | 2022-06 | 3% | sufficient |
| structural_heart | 6 | 2017-02 | 2020-07 | 3% | sufficient |
| neurovascular | 6 | 2017-09 | 2020-05 | 3% | sufficient |
| insulin_delivery | 5 | 2018-02 | 2022-04 | 2% | sufficient |
| patient_monitoring | 4 | 2016-11 | 2021-12 | 2% | sufficient |
| dialysis | 4 | 2018-07 | 2022-01 | 2% | sufficient |
| trauma | 3 | 2017-10 | 2020-08 | 1% | sufficient |
| respiratory | 3 | 2017-10 | 2022-01 | 1% | sufficient |
| heart_failure | 1 | 2017-09 | 2017-09 | 0% | single event |
| diabetes_cgm | 1 | 2018-03 | 2018-03 | 0% | single event |
| ent | 1 | 2020-12 | 2020-12 | 0% | single event |
| neurostimulation | 1 | 2022-01 | 2022-01 | 0% | single event |

## 3. Momentum

- activity decreasing: 71 events in the last 24 months vs 99 before (ratio 0.72), exact two-sided p=0.038
- Test: exact two-sided binomial p=0.038 (alpha=0.05), minimum detectable ratio at 80 % power 1.55x, detected=True

## 4. Concentration

- diversified: top track spine holds 22% of 204 material events across 23 tracks (HHI 0.10)

## 5. Independent corroboration

- 10 of 23 technology tracks have independent device-trial support; 13 do not
- Tracks with **no** trial support: coronary, dialysis, endoscopy, ent, ep_pfa, heart_failure, imaging_mr_ct, neurostimulation

## 6. Contradictory evidence

- 6 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 4 track(s) rest on a single event: diabetes_cgm, ent, heart_failure, neurostimulation — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: surgical_energy: 3 events in the last 24 months vs 8 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: cardiac_rhythm: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: peripheral_vascular: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: neurovascular: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: imaging_mr_ct: 0 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
- Hiring evidence: 5107 archived postings across 60 months (posting-flow proxy, not headcount)
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
