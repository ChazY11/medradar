# Johnson & Johnson MedTech — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Johnson & Johnson MedTech: 31 resolved legal entities from 19 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 232 material events across 19 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 70 | 2017-06 | 2026-09 | 30% | sufficient |
| general_surgery | 22 | 2017-04 | 2026-05 | 9% | sufficient |
| wound_care | 17 | 2017-11 | 2026-06 | 7% | sufficient |
| surgical_energy | 16 | 2017-02 | 2026-09 | 7% | sufficient |
| medical_ai | 15 | 2017-07 | 2026-07 | 6% | sufficient |
| imaging_us | 14 | 2016-12 | 2026-07 | 6% | sufficient |
| trauma | 14 | 2017-02 | 2024-08 | 6% | sufficient |
| endoscopy | 12 | 2017-01 | 2026-07 | 5% | sufficient |
| ep_pfa | 12 | 2020-06 | 2026-07 | 5% | sufficient |
| ophthalmology | 8 | 2018-04 | 2026-03 | 3% | sufficient |
| neurovascular | 7 | 2023-03 | 2026-08 | 3% | sufficient |
| vascular_access | 6 | 2017-07 | 2024-10 | 3% | sufficient |
| urology | 6 | 2018-06 | 2022-04 | 3% | sufficient |
| imaging_mr_ct | 4 | 2017-05 | 2024-04 | 2% | sufficient |
| spine | 3 | 2018-12 | 2022-10 | 1% | sufficient |
| aesthetics | 2 | 2018-06 | 2018-06 | 1% | sufficient |
| wearable_remote | 2 | 2018-07 | 2026-06 | 1% | sufficient |
| cardiac_rhythm | 1 | 2018-08 | 2018-08 | 0% | single event |
| respiratory | 1 | 2019-04 | 2019-04 | 0% | single event |

## 3. Momentum

- no detectable change: 53 events in the last 24 months vs 61 before (ratio 0.87), p=0.512; minimum detectable ratio at 80% power is 1.69x
- Test: exact two-sided binomial p=0.512 (alpha=0.05), minimum detectable ratio at 80 % power 1.69x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 2 calibrated alert(s) in the last 8 quarters across 2 track(s) (102 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `medical_ai` 2026-Q1: 3 events against a baseline of 0.12 (z=8.13)
    - promotion: **promote_pending_signoff** — shape ramp (post-alert rate is elevated and still rising); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `wound_care` 2025-Q4: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- diversified: top track ortho_joint holds 30% of 232 material events across 19 tracks (HHI 0.13)

## 5. Independent corroboration

- 1 of 19 technology tracks have independent device-trial support; 18 do not
- Tracks with **no** trial support: aesthetics, cardiac_rhythm, endoscopy, ep_pfa, general_surgery, imaging_mr_ct, imaging_us, medical_ai

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: cardiac_rhythm, respiratory — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: imaging_us: 1 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: vascular_access: 1 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
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
