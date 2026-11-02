# AtriCure — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- AtriCure: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 14 material events across 3 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ep_pfa | 12 | 2017-01 | 2025-07 | 86% | sufficient |
| surgical_energy | 1 | 2018-02 | 2018-02 | 7% | single event |
| vascular_access | 1 | 2024-02 | 2024-02 | 7% | single event |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 6 before (ratio 0.67), p=0.754; minimum detectable ratio at 80% power is 6.10x
- Test: exact two-sided binomial p=0.754 (alpha=0.05), minimum detectable ratio at 80 % power 6.10x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (14 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- highly concentrated: top track ep_pfa holds 86% of 14 material events across 3 tracks (HHI 0.74)

## 5. Independent corroboration

- 1 of 3 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: ep_pfa, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 28 of 119 months (76% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: surgical_energy, vascular_access — a single filing is an anecdote; treat these tracks as unconfirmed

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
