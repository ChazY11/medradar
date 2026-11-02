# Boston Scientific — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Boston Scientific: 7 resolved legal entities from 6 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 119 material events across 15 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 21 | 2017-02 | 2023-08 | 18% | sufficient |
| urology | 15 | 2017-12 | 2024-11 | 13% | sufficient |
| neurostimulation | 14 | 2017-08 | 2024-08 | 12% | sufficient |
| coronary | 12 | 2016-12 | 2024-02 | 10% | sufficient |
| medical_ai | 11 | 2017-03 | 2024-08 | 9% | sufficient |
| surgical_energy | 11 | 2019-03 | 2024-10 | 9% | sufficient |
| peripheral_vascular | 9 | 2016-11 | 2024-07 | 8% | sufficient |
| imaging_us | 6 | 2017-11 | 2023-05 | 5% | sufficient |
| ep_pfa | 6 | 2017-12 | 2024-02 | 5% | sufficient |
| vascular_access | 6 | 2018-06 | 2023-11 | 5% | sufficient |
| neurovascular | 3 | 2022-04 | 2023-06 | 3% | sufficient |
| cardiac_rhythm | 2 | 2017-07 | 2019-03 | 2% | sufficient |
| structural_heart | 1 | 2019-04 | 2019-04 | 1% | single event |
| dental | 1 | 2021-04 | 2021-04 | 1% | single event |
| ortho_joint | 1 | 2022-03 | 2022-03 | 1% | single event |

## 3. Momentum

- no detectable change: 48 events in the last 24 months vs 41 before (ratio 1.17), p=0.525; minimum detectable ratio at 80% power is 1.81x
- Test: exact two-sided binomial p=0.525 (alpha=0.05), minimum detectable ratio at 80 % power 1.81x, detected=False

## 4. Concentration

- diversified: top track endoscopy holds 18% of 119 material events across 15 tracks (HHI 0.10)

## 5. Independent corroboration

- 8 of 15 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: coronary, dental, medical_ai, ortho_joint, structural_heart, surgical_energy, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: dental, ortho_joint, structural_heart — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: endoscopy: 2 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
- Hiring evidence: 4999 archived postings across 123 months (posting-flow proxy, not headcount)
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
