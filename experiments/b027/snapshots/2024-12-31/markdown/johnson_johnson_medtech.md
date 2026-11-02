# Johnson & Johnson MedTech — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Johnson & Johnson MedTech: 31 resolved legal entities from 19 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 196 material events across 19 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 61 | 2017-06 | 2024-11 | 31% | sufficient |
| general_surgery | 18 | 2017-04 | 2024-10 | 9% | sufficient |
| trauma | 14 | 2017-02 | 2024-08 | 7% | sufficient |
| surgical_energy | 14 | 2017-02 | 2023-11 | 7% | sufficient |
| imaging_us | 13 | 2016-12 | 2024-09 | 7% | sufficient |
| wound_care | 11 | 2017-11 | 2024-07 | 6% | sufficient |
| ep_pfa | 11 | 2020-06 | 2024-11 | 6% | sufficient |
| endoscopy | 10 | 2017-01 | 2024-02 | 5% | sufficient |
| medical_ai | 10 | 2017-07 | 2023-09 | 5% | sufficient |
| ophthalmology | 7 | 2018-04 | 2023-04 | 4% | sufficient |
| vascular_access | 6 | 2017-07 | 2024-10 | 3% | sufficient |
| urology | 6 | 2018-06 | 2022-04 | 3% | sufficient |
| imaging_mr_ct | 4 | 2017-05 | 2024-04 | 2% | sufficient |
| spine | 3 | 2018-12 | 2022-10 | 2% | sufficient |
| neurovascular | 3 | 2023-03 | 2024-10 | 2% | sufficient |
| aesthetics | 2 | 2018-06 | 2018-06 | 1% | sufficient |
| wearable_remote | 1 | 2018-07 | 2018-07 | 1% | single event |
| cardiac_rhythm | 1 | 2018-08 | 2018-08 | 1% | single event |
| respiratory | 1 | 2019-04 | 2019-04 | 1% | single event |

## 3. Momentum

- no detectable change: 63 events in the last 24 months vs 51 before (ratio 1.24), p=0.303; minimum detectable ratio at 80% power is 1.70x
- Test: exact two-sided binomial p=0.303 (alpha=0.05), minimum detectable ratio at 80 % power 1.70x, detected=False

## 4. Concentration

- diversified: top track ortho_joint holds 31% of 196 material events across 19 tracks (HHI 0.14)

## 5. Independent corroboration

- 1 of 19 technology tracks have independent device-trial support; 18 do not
- Tracks with **no** trial support: aesthetics, cardiac_rhythm, endoscopy, ep_pfa, general_surgery, imaging_mr_ct, imaging_us, medical_ai

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: cardiac_rhythm, respiratory, wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: wound_care: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: ophthalmology: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

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
