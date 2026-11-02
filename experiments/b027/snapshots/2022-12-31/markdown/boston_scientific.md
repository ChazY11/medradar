# Boston Scientific — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Boston Scientific: 7 resolved legal entities from 6 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 89 material events across 15 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 19 | 2017-02 | 2022-09 | 21% | sufficient |
| coronary | 11 | 2016-12 | 2022-03 | 12% | sufficient |
| neurostimulation | 10 | 2017-08 | 2022-06 | 11% | sufficient |
| urology | 10 | 2017-12 | 2021-12 | 11% | sufficient |
| medical_ai | 9 | 2017-03 | 2021-10 | 10% | sufficient |
| peripheral_vascular | 8 | 2016-11 | 2022-09 | 9% | sufficient |
| imaging_us | 5 | 2017-11 | 2022-09 | 6% | sufficient |
| vascular_access | 4 | 2018-06 | 2020-10 | 4% | sufficient |
| ep_pfa | 3 | 2017-12 | 2022-06 | 3% | sufficient |
| surgical_energy | 3 | 2019-03 | 2020-12 | 3% | sufficient |
| cardiac_rhythm | 2 | 2017-07 | 2019-03 | 2% | sufficient |
| neurovascular | 2 | 2022-04 | 2022-04 | 2% | sufficient |
| structural_heart | 1 | 2019-04 | 2019-04 | 1% | single event |
| dental | 1 | 2021-04 | 2021-04 | 1% | single event |
| ortho_joint | 1 | 2022-03 | 2022-03 | 1% | single event |

## 3. Momentum

- no detectable change: 41 events in the last 24 months vs 54 before (ratio 0.76), p=0.218; minimum detectable ratio at 80% power is 1.79x
- Test: exact two-sided binomial p=0.218 (alpha=0.05), minimum detectable ratio at 80 % power 1.79x, detected=False

## 4. Concentration

- diversified: top track endoscopy holds 21% of 89 material events across 15 tracks (HHI 0.11)

## 5. Independent corroboration

- 8 of 15 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: coronary, dental, medical_ai, ortho_joint, structural_heart, surgical_energy, vascular_access

## 6. Contradictory evidence

- 5 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: dental, ortho_joint, structural_heart — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: peripheral_vascular: 1 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: medical_ai: 2 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: vascular_access: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: surgical_energy: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
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
