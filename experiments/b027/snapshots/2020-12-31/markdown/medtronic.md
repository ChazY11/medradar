# Medtronic — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Medtronic: 30 resolved legal entities from 13 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 158 material events across 22 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 31 | 2016-11 | 2020-10 | 20% | sufficient |
| surgical_energy | 25 | 2016-11 | 2020-12 | 16% | sufficient |
| ortho_joint | 16 | 2017-04 | 2020-12 | 10% | sufficient |
| general_surgery | 9 | 2017-03 | 2020-12 | 6% | sufficient |
| cardiac_rhythm | 7 | 2017-02 | 2020-05 | 4% | sufficient |
| peripheral_vascular | 7 | 2017-06 | 2020-11 | 4% | sufficient |
| imaging_mr_ct | 7 | 2017-12 | 2020-04 | 4% | sufficient |
| ep_pfa | 6 | 2016-11 | 2020-06 | 4% | sufficient |
| structural_heart | 6 | 2017-02 | 2020-07 | 4% | sufficient |
| coronary | 6 | 2017-04 | 2020-09 | 4% | sufficient |
| neurovascular | 6 | 2017-09 | 2020-05 | 4% | sufficient |
| vascular_access | 5 | 2016-11 | 2018-10 | 3% | sufficient |
| medical_ai | 5 | 2017-03 | 2020-07 | 3% | sufficient |
| endoscopy | 4 | 2016-11 | 2020-08 | 3% | sufficient |
| insulin_delivery | 4 | 2018-02 | 2020-08 | 3% | sufficient |
| patient_monitoring | 3 | 2016-11 | 2020-05 | 2% | sufficient |
| trauma | 3 | 2017-10 | 2020-08 | 2% | sufficient |
| dialysis | 3 | 2018-07 | 2020-04 | 2% | sufficient |
| respiratory | 2 | 2017-10 | 2020-11 | 1% | sufficient |
| heart_failure | 1 | 2017-09 | 2017-09 | 1% | single event |
| diabetes_cgm | 1 | 2018-03 | 2018-03 | 1% | single event |
| ent | 1 | 2020-12 | 2020-12 | 1% | single event |

## 3. Momentum

- no detectable change: 99 events in the last 24 months vs 119 before (ratio 0.83), p=0.198; minimum detectable ratio at 80% power is 1.46x
- Test: exact two-sided binomial p=0.198 (alpha=0.05), minimum detectable ratio at 80 % power 1.46x, detected=False

## 4. Concentration

- diversified: top track spine holds 20% of 158 material events across 22 tracks (HHI 0.09)

## 5. Independent corroboration

- 7 of 22 technology tracks have independent device-trial support; 15 do not
- Tracks with **no** trial support: cardiac_rhythm, coronary, dialysis, endoscopy, ent, ep_pfa, general_surgery, heart_failure

## 6. Contradictory evidence

- 5 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: diabetes_cgm, ent, heart_failure — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: vascular_access: 0 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: structural_heart: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: coronary: 1 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: insulin_delivery: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
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
