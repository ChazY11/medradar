# Baxter — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Baxter: 10 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 34 material events across 6 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 15 | 2016-11 | 2025-03 | 44% | sufficient |
| dialysis | 8 | 2017-01 | 2024-03 | 24% | sufficient |
| medical_ai | 7 | 2018-05 | 2025-07 | 21% | sufficient |
| patient_monitoring | 2 | 2025-12 | 2026-01 | 6% | sufficient |
| endoscopy | 1 | 2020-01 | 2020-01 | 3% | single event |
| imaging_mr_ct | 1 | 2026-05 | 2026-05 | 3% | single event |

## 3. Momentum

- no detectable change: 8 events in the last 24 months vs 14 before (ratio 0.57), p=0.286; minimum detectable ratio at 80% power is 3.46x
- Test: exact two-sided binomial p=0.286 (alpha=0.05), minimum detectable ratio at 80 % power 3.46x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 1 calibrated alert(s) in the last 8 quarters across 1 track(s) (25 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `vascular_access` 2025-Q1: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **reject** — shape spike (post-alert rate 0.00x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track vascular_access holds 44% of 34 material events across 6 tracks (HHI 0.30)

## 5. Independent corroboration

- 0 of 6 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: dialysis, endoscopy, imaging_mr_ct, medical_ai, patient_monitoring, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 47 of 119 months (61% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: endoscopy, imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
- Hiring evidence: 69 archived postings across 21 months (posting-flow proxy, not headcount)
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
