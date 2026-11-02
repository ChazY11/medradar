# Boston Scientific — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Boston Scientific: 7 resolved legal entities from 6 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 144 material events across 17 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 26 | 2017-02 | 2026-08 | 18% | sufficient |
| urology | 19 | 2017-12 | 2026-09 | 13% | sufficient |
| coronary | 14 | 2016-12 | 2026-03 | 10% | sufficient |
| neurostimulation | 14 | 2017-08 | 2024-08 | 10% | sufficient |
| medical_ai | 13 | 2017-03 | 2026-08 | 9% | sufficient |
| surgical_energy | 13 | 2019-03 | 2026-09 | 9% | sufficient |
| peripheral_vascular | 9 | 2016-11 | 2024-07 | 6% | sufficient |
| imaging_us | 7 | 2017-11 | 2026-04 | 5% | sufficient |
| vascular_access | 7 | 2018-06 | 2025-03 | 5% | sufficient |
| ep_pfa | 6 | 2017-12 | 2024-02 | 4% | sufficient |
| dental | 4 | 2021-04 | 2026-05 | 3% | sufficient |
| neurovascular | 3 | 2022-04 | 2023-06 | 2% | sufficient |
| imaging_mr_ct | 3 | 2025-10 | 2026-07 | 2% | sufficient |
| cardiac_rhythm | 2 | 2017-07 | 2019-03 | 1% | sufficient |
| structural_heart | 2 | 2019-04 | 2025-07 | 1% | sufficient |
| ortho_joint | 1 | 2022-03 | 2022-03 | 1% | single event |
| wearable_remote | 1 | 2026-01 | 2026-01 | 1% | single event |

## 3. Momentum

- no detectable change: 44 events in the last 24 months vs 46 before (ratio 0.96), p=0.916; minimum detectable ratio at 80% power is 1.81x
- Test: exact two-sided binomial p=0.916 (alpha=0.05), minimum detectable ratio at 80 % power 1.81x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 1 calibrated alert(s) in the last 8 quarters across 1 track(s) (90 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `endoscopy` 2025-Q1: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **promote_pending_signoff** — shape ramp (post-alert rate is elevated and still rising); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- diversified: top track endoscopy holds 18% of 144 material events across 17 tracks (HHI 0.10)

## 5. Independent corroboration

- 9 of 17 technology tracks have independent device-trial support; 8 do not
- Tracks with **no** trial support: dental, imaging_mr_ct, medical_ai, ortho_joint, structural_heart, surgical_energy, vascular_access, wearable_remote

## 6. Contradictory evidence

- 4 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: ortho_joint, wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: neurostimulation: 0 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: ep_pfa: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: surgical_energy: 3 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
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
