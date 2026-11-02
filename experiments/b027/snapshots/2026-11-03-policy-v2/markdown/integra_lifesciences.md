# Integra LifeSciences — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Integra LifeSciences: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 23 material events across 8 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| general_surgery | 9 | 2017-09 | 2025-10 | 39% | sufficient |
| ortho_joint | 3 | 2018-06 | 2019-12 | 13% | sufficient |
| neurovascular | 3 | 2019-01 | 2024-02 | 13% | sufficient |
| trauma | 2 | 2018-11 | 2021-07 | 9% | sufficient |
| surgical_energy | 2 | 2018-11 | 2021-05 | 9% | sufficient |
| endoscopy | 2 | 2024-01 | 2025-04 | 9% | sufficient |
| wound_care | 1 | 2021-10 | 2021-10 | 4% | single event |
| dialysis | 1 | 2026-06 | 2026-06 | 4% | single event |

## 3. Momentum

- no detectable change: 5 events in the last 24 months vs 7 before (ratio 0.71), p=0.774; minimum detectable ratio at 80% power is 5.16x
- Test: exact two-sided binomial p=0.774 (alpha=0.05), minimum detectable ratio at 80 % power 5.16x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (23 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- diversified: top track general_surgery holds 39% of 23 material events across 8 tracks (HHI 0.21)

## 5. Independent corroboration

- 2 of 8 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: dialysis, endoscopy, general_surgery, ortho_joint, surgical_energy, trauma

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 31 of 119 months (74% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: dialysis, wound_care — a single filing is an anecdote; treat these tracks as unconfirmed

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
  - a spike can be separated from a sustained change, but a ramp cannot be separated from a level shift at this counting rate: no confirmation window between 1 and 6 months recovered ramps (best recall 0.229, D-051)
  - the alert detector is validated at quarterly resolution only; at monthly resolution the same detector ranks last (D-045)
  - alerts in this profile were governed by promotion policy promotion_policy_v2, which requires a named human sign-off before any change may be described as a technology change (D-054)
