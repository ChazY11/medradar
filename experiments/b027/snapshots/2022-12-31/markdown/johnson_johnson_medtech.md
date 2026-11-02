# Johnson & Johnson MedTech — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Johnson & Johnson MedTech: 31 resolved legal entities from 19 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 143 material events across 18 technology tracks (4 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 41 | 2017-06 | 2022-12 | 29% | sufficient |
| general_surgery | 15 | 2017-04 | 2022-07 | 10% | sufficient |
| trauma | 12 | 2017-02 | 2022-09 | 8% | sufficient |
| surgical_energy | 12 | 2017-02 | 2022-08 | 8% | sufficient |
| wound_care | 10 | 2017-11 | 2022-11 | 7% | sufficient |
| medical_ai | 8 | 2017-07 | 2022-08 | 6% | sufficient |
| ep_pfa | 8 | 2020-06 | 2022-11 | 6% | sufficient |
| imaging_us | 7 | 2016-12 | 2022-08 | 5% | sufficient |
| endoscopy | 7 | 2017-01 | 2021-07 | 5% | sufficient |
| ophthalmology | 6 | 2018-04 | 2021-11 | 4% | sufficient |
| urology | 6 | 2018-06 | 2022-04 | 4% | sufficient |
| spine | 3 | 2018-12 | 2022-10 | 2% | sufficient |
| imaging_mr_ct | 2 | 2017-05 | 2019-10 | 1% | sufficient |
| aesthetics | 2 | 2018-06 | 2018-06 | 1% | sufficient |
| vascular_access | 1 | 2017-07 | 2017-07 | 1% | single event |
| wearable_remote | 1 | 2018-07 | 2018-07 | 1% | single event |
| cardiac_rhythm | 1 | 2018-08 | 2018-08 | 1% | single event |
| respiratory | 1 | 2019-04 | 2019-04 | 1% | single event |

## 3. Momentum

- no detectable change: 51 events in the last 24 months vs 64 before (ratio 0.80), p=0.263; minimum detectable ratio at 80% power is 1.69x
- Test: exact two-sided binomial p=0.263 (alpha=0.05), minimum detectable ratio at 80 % power 1.69x, detected=False

## 4. Concentration

- diversified: top track ortho_joint holds 29% of 143 material events across 18 tracks (HHI 0.13)

## 5. Independent corroboration

- 1 of 18 technology tracks have independent device-trial support; 17 do not
- Tracks with **no** trial support: aesthetics, cardiac_rhythm, endoscopy, ep_pfa, general_surgery, imaging_mr_ct, imaging_us, medical_ai

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 4 track(s) rest on a single event: cardiac_rhythm, respiratory, vascular_access, wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: trauma: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: general_surgery: 2 events in the last 24 months vs 8 before — this track is retreating, which cuts against a growth reading

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
