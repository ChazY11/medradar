# Becton Dickinson — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Becton Dickinson: 20 resolved legal entities from 8 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 91 material events across 10 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 47 | 2016-11 | 2024-11 | 52% | sufficient |
| peripheral_vascular | 9 | 2016-12 | 2023-03 | 10% | sufficient |
| dialysis | 9 | 2017-04 | 2021-07 | 10% | sufficient |
| ivd_molecular | 9 | 2017-05 | 2024-12 | 10% | sufficient |
| insulin_delivery | 6 | 2016-12 | 2022-12 | 7% | sufficient |
| imaging_us | 4 | 2017-05 | 2023-09 | 4% | sufficient |
| medical_ai | 3 | 2017-07 | 2020-09 | 3% | sufficient |
| surgical_energy | 2 | 2017-05 | 2022-10 | 2% | sufficient |
| coronary | 1 | 2022-05 | 2022-05 | 1% | single event |
| respiratory | 1 | 2022-05 | 2022-05 | 1% | single event |

## 3. Momentum

- no detectable change: 34 events in the last 24 months vs 38 before (ratio 0.89), p=0.724; minimum detectable ratio at 80% power is 1.94x
- Test: exact two-sided binomial p=0.724 (alpha=0.05), minimum detectable ratio at 80 % power 1.94x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 52% of 91 material events across 10 tracks (HHI 0.30)

## 5. Independent corroboration

- 4 of 10 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: coronary, dialysis, imaging_us, peripheral_vascular, respiratory, surgical_energy

## 6. Contradictory evidence

- 4 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: coronary, respiratory — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: insulin_delivery: 0 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: peripheral_vascular: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: ivd_molecular: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
- Hiring evidence: 4709 archived postings across 68 months (posting-flow proxy, not headcount)
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
