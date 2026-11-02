# Medtronic — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Medtronic: 30 resolved legal entities from 13 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 299 material events across 24 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 62 | 2016-11 | 2026-07 | 21% | sufficient |
| surgical_energy | 36 | 2016-11 | 2026-09 | 12% | sufficient |
| ortho_joint | 28 | 2017-04 | 2026-02 | 9% | sufficient |
| medical_ai | 20 | 2017-03 | 2026-08 | 7% | sufficient |
| general_surgery | 18 | 2017-03 | 2026-09 | 6% | sufficient |
| ep_pfa | 13 | 2016-11 | 2024-10 | 4% | sufficient |
| insulin_delivery | 13 | 2018-02 | 2026-03 | 4% | sufficient |
| coronary | 12 | 2017-04 | 2026-08 | 4% | sufficient |
| peripheral_vascular | 12 | 2017-06 | 2026-09 | 4% | sufficient |
| cardiac_rhythm | 10 | 2017-02 | 2025-04 | 3% | sufficient |
| respiratory | 9 | 2017-10 | 2026-07 | 3% | sufficient |
| endoscopy | 8 | 2016-11 | 2026-06 | 3% | sufficient |
| neurovascular | 8 | 2017-09 | 2026-06 | 3% | sufficient |
| imaging_mr_ct | 8 | 2017-12 | 2024-06 | 3% | sufficient |
| wound_care | 8 | 2023-02 | 2026-07 | 3% | sufficient |
| structural_heart | 7 | 2017-02 | 2025-08 | 2% | sufficient |
| vascular_access | 6 | 2016-11 | 2021-07 | 2% | sufficient |
| patient_monitoring | 4 | 2016-11 | 2021-12 | 1% | sufficient |
| dialysis | 4 | 2018-07 | 2022-01 | 1% | sufficient |
| trauma | 3 | 2017-10 | 2020-08 | 1% | sufficient |
| diabetes_cgm | 3 | 2018-03 | 2025-08 | 1% | sufficient |
| neurostimulation | 3 | 2022-01 | 2025-11 | 1% | sufficient |
| heart_failure | 2 | 2017-09 | 2023-04 | 1% | sufficient |
| ent | 2 | 2020-12 | 2026-02 | 1% | sufficient |

## 3. Momentum

- no detectable change: 90 events in the last 24 months vs 66 before (ratio 1.36), p=0.065; minimum detectable ratio at 80% power is 1.57x
- Test: exact two-sided binomial p=0.065 (alpha=0.05), minimum detectable ratio at 80 % power 1.57x, detected=False

## 4. Concentration

- diversified: top track spine holds 21% of 299 material events across 24 tracks (HHI 0.09)

## 5. Independent corroboration

- 14 of 24 technology tracks have independent device-trial support; 10 do not
- Tracks with **no** trial support: coronary, dialysis, endoscopy, ent, neurostimulation, ortho_joint, patient_monitoring, surgical_energy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `activity_decline_by_track`: surgical_energy: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: ep_pfa: 1 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
- Hiring evidence: 5107 archived postings across 60 months (posting-flow proxy, not headcount)
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
