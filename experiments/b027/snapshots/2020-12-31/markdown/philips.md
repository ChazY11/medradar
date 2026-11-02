# Philips — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Philips: 36 resolved legal entities from 7 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 93 material events across 8 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 57 | 2016-11 | 2020-12 | 61% | sufficient |
| imaging_us | 12 | 2016-11 | 2020-09 | 13% | sufficient |
| patient_monitoring | 12 | 2017-03 | 2020-09 | 13% | sufficient |
| medical_ai | 5 | 2018-10 | 2020-12 | 5% | sufficient |
| wearable_remote | 3 | 2019-03 | 2020-05 | 3% | sufficient |
| cardiac_rhythm | 2 | 2019-06 | 2020-07 | 2% | sufficient |
| peripheral_vascular | 1 | 2016-12 | 2016-12 | 1% | single event |
| dental | 1 | 2017-07 | 2017-07 | 1% | single event |

## 3. Momentum

- no detectable change: 49 events in the last 24 months vs 60 before (ratio 0.82), p=0.338; minimum detectable ratio at 80% power is 1.72x
- Test: exact two-sided binomial p=0.338 (alpha=0.05), minimum detectable ratio at 80 % power 1.72x, detected=False

## 4. Concentration

- moderately concentrated: top track imaging_mr_ct holds 61% of 93 material events across 8 tracks (HHI 0.41)

## 5. Independent corroboration

- 3 of 8 technology tracks have independent device-trial support; 5 do not
- Tracks with **no** trial support: cardiac_rhythm, imaging_mr_ct, patient_monitoring, peripheral_vascular, wearable_remote

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: dental, peripheral_vascular — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: patient_monitoring: 4 events in the last 24 months vs 8 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
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
