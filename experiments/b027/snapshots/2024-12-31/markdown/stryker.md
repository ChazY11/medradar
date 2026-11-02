# Stryker — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Stryker: 26 resolved legal entities from 11 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 237 material events across 18 technology tracks (4 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 65 | 2017-02 | 2024-12 | 27% | sufficient |
| trauma | 52 | 2017-02 | 2024-12 | 22% | sufficient |
| endoscopy | 32 | 2016-11 | 2024-08 | 14% | sufficient |
| spine | 19 | 2016-11 | 2024-11 | 8% | sufficient |
| surgical_energy | 16 | 2017-02 | 2024-10 | 7% | sufficient |
| neurovascular | 16 | 2018-03 | 2024-08 | 7% | sufficient |
| general_surgery | 8 | 2019-04 | 2023-02 | 3% | sufficient |
| vascular_access | 7 | 2019-11 | 2024-12 | 3% | sufficient |
| medical_ai | 5 | 2017-02 | 2024-01 | 2% | sufficient |
| patient_monitoring | 4 | 2022-03 | 2024-10 | 2% | sufficient |
| imaging_mr_ct | 3 | 2018-12 | 2023-06 | 1% | sufficient |
| ep_pfa | 2 | 2019-01 | 2020-05 | 1% | sufficient |
| coronary | 2 | 2019-05 | 2020-09 | 1% | sufficient |
| imaging_us | 2 | 2019-05 | 2023-07 | 1% | sufficient |
| wound_care | 1 | 2016-11 | 2016-11 | 0% | single event |
| cmf | 1 | 2018-09 | 2018-09 | 0% | single event |
| urology | 1 | 2024-02 | 2024-02 | 0% | single event |
| cardiac_rhythm | 1 | 2024-04 | 2024-04 | 0% | single event |

## 3. Momentum

- no detectable change: 78 events in the last 24 months vs 67 before (ratio 1.16), p=0.406; minimum detectable ratio at 80% power is 1.59x
- Test: exact two-sided binomial p=0.406 (alpha=0.05), minimum detectable ratio at 80 % power 1.59x, detected=False

## 4. Concentration

- diversified: top track ortho_joint holds 27% of 237 material events across 18 tracks (HHI 0.16)

## 5. Independent corroboration

- 5 of 18 technology tracks have independent device-trial support; 13 do not
- Tracks with **no** trial support: cardiac_rhythm, cmf, coronary, ep_pfa, imaging_mr_ct, imaging_us, medical_ai, spine

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 4 track(s) rest on a single event: cardiac_rhythm, cmf, urology, wound_care — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: patient_monitoring: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
- Hiring evidence: 8839 archived postings across 90 months (posting-flow proxy, not headcount)
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
