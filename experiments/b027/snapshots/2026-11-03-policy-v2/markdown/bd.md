# Becton Dickinson — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Becton Dickinson: 20 resolved legal entities from 8 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 110 material events across 15 technology tracks (6 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 57 | 2016-11 | 2026-04 | 52% | sufficient |
| ivd_molecular | 11 | 2017-05 | 2025-10 | 10% | sufficient |
| peripheral_vascular | 9 | 2016-12 | 2023-03 | 8% | sufficient |
| dialysis | 9 | 2017-04 | 2021-07 | 8% | sufficient |
| insulin_delivery | 6 | 2016-12 | 2022-12 | 5% | sufficient |
| imaging_us | 4 | 2017-05 | 2023-09 | 4% | sufficient |
| medical_ai | 4 | 2017-07 | 2025-06 | 4% | sufficient |
| surgical_energy | 2 | 2017-05 | 2022-10 | 2% | sufficient |
| cardiac_rhythm | 2 | 2025-01 | 2025-05 | 2% | sufficient |
| coronary | 1 | 2022-05 | 2022-05 | 1% | single event |
| respiratory | 1 | 2022-05 | 2022-05 | 1% | single event |
| wearable_remote | 1 | 2025-02 | 2025-02 | 1% | single event |
| ivd_poct | 1 | 2025-06 | 2025-06 | 1% | single event |
| urology | 1 | 2026-02 | 2026-02 | 1% | single event |
| dental | 1 | 2026-03 | 2026-03 | 1% | single event |

## 3. Momentum

- no detectable change: 45 events in the last 24 months vs 34 before (ratio 1.32), p=0.260; minimum detectable ratio at 80% power is 1.89x
- Test: exact two-sided binomial p=0.260 (alpha=0.05), minimum detectable ratio at 80 % power 1.89x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (48 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track vascular_access holds 52% of 110 material events across 15 tracks (HHI 0.30)

## 5. Independent corroboration

- 5 of 15 technology tracks have independent device-trial support; 10 do not
- Tracks with **no** trial support: cardiac_rhythm, coronary, dental, dialysis, imaging_us, ivd_poct, peripheral_vascular, respiratory

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 6 track(s) rest on a single event: coronary, dental, ivd_poct, respiratory, urology — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
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
  - a spike can be separated from a sustained change, but a ramp cannot be separated from a level shift at this counting rate: no confirmation window between 1 and 6 months recovered ramps (best recall 0.229, D-051)
  - the alert detector is validated at quarterly resolution only; at monthly resolution the same detector ranks last (D-045)
  - alerts in this profile were governed by promotion policy promotion_policy_v2, which requires a named human sign-off before any change may be described as a technology change (D-054)
