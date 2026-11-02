# Medtronic — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Medtronic: 30 resolved legal entities from 13 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 246 material events across 24 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 52 | 2016-11 | 2024-10 | 21% | sufficient |
| surgical_energy | 34 | 2016-11 | 2024-07 | 14% | sufficient |
| ortho_joint | 24 | 2017-04 | 2023-07 | 10% | sufficient |
| general_surgery | 16 | 2017-03 | 2022-11 | 7% | sufficient |
| medical_ai | 14 | 2017-03 | 2024-12 | 6% | sufficient |
| ep_pfa | 13 | 2016-11 | 2024-10 | 5% | sufficient |
| peripheral_vascular | 9 | 2017-06 | 2021-12 | 4% | sufficient |
| cardiac_rhythm | 8 | 2017-02 | 2023-10 | 3% | sufficient |
| coronary | 8 | 2017-04 | 2023-10 | 3% | sufficient |
| imaging_mr_ct | 8 | 2017-12 | 2024-06 | 3% | sufficient |
| endoscopy | 7 | 2016-11 | 2023-09 | 3% | sufficient |
| insulin_delivery | 7 | 2018-02 | 2024-07 | 3% | sufficient |
| vascular_access | 6 | 2016-11 | 2021-07 | 2% | sufficient |
| structural_heart | 6 | 2017-02 | 2020-07 | 2% | sufficient |
| neurovascular | 6 | 2017-09 | 2020-05 | 2% | sufficient |
| wound_care | 6 | 2023-02 | 2024-12 | 2% | sufficient |
| respiratory | 5 | 2017-10 | 2024-09 | 2% | sufficient |
| patient_monitoring | 4 | 2016-11 | 2021-12 | 2% | sufficient |
| dialysis | 4 | 2018-07 | 2022-01 | 2% | sufficient |
| trauma | 3 | 2017-10 | 2020-08 | 1% | sufficient |
| heart_failure | 2 | 2017-09 | 2023-04 | 1% | sufficient |
| diabetes_cgm | 2 | 2018-03 | 2024-07 | 1% | sufficient |
| ent | 1 | 2020-12 | 2020-12 | 0% | single event |
| neurostimulation | 1 | 2022-01 | 2022-01 | 0% | single event |

## 3. Momentum

- no detectable change: 68 events in the last 24 months vs 71 before (ratio 0.96), p=0.865; minimum detectable ratio at 80% power is 1.61x
- Test: exact two-sided binomial p=0.865 (alpha=0.05), minimum detectable ratio at 80 % power 1.61x, detected=False

## 4. Concentration

- diversified: top track spine holds 21% of 246 material events across 24 tracks (HHI 0.09)

## 5. Independent corroboration

- 13 of 24 technology tracks have independent device-trial support; 11 do not
- Tracks with **no** trial support: coronary, dialysis, endoscopy, ent, ep_pfa, neurostimulation, ortho_joint, patient_monitoring

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: ent, neurostimulation — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: general_surgery: 0 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: ortho_joint: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
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
