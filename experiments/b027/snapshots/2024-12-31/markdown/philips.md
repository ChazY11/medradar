# Philips — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Philips: 36 resolved legal entities from 7 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 170 material events across 9 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 108 | 2016-11 | 2024-11 | 64% | sufficient |
| imaging_us | 25 | 2016-11 | 2024-12 | 15% | sufficient |
| patient_monitoring | 18 | 2017-03 | 2023-12 | 11% | sufficient |
| medical_ai | 8 | 2018-10 | 2024-03 | 5% | sufficient |
| wearable_remote | 4 | 2019-03 | 2024-07 | 2% | sufficient |
| cardiac_rhythm | 3 | 2019-06 | 2021-01 | 2% | sufficient |
| peripheral_vascular | 2 | 2016-12 | 2023-12 | 1% | sufficient |
| dental | 1 | 2017-07 | 2017-07 | 1% | single event |
| respiratory | 1 | 2024-07 | 2024-07 | 1% | single event |

## 3. Momentum

- no detectable change: 44 events in the last 24 months vs 41 before (ratio 1.07), p=0.828; minimum detectable ratio at 80% power is 1.84x
- Test: exact two-sided binomial p=0.828 (alpha=0.05), minimum detectable ratio at 80 % power 1.84x, detected=False

## 4. Concentration

- moderately concentrated: top track imaging_mr_ct holds 64% of 170 material events across 9 tracks (HHI 0.44)

## 5. Independent corroboration

- 8 of 9 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: cardiac_rhythm

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: dental, respiratory — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
- Hiring evidence: 669 archived postings across 38 months (posting-flow proxy, not headcount)
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
