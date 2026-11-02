# Fujifilm — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Fujifilm: 10 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 102 material events across 4 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 48 | 2017-03 | 2026-07 | 47% | sufficient |
| imaging_mr_ct | 32 | 2017-03 | 2026-09 | 31% | sufficient |
| imaging_us | 16 | 2017-06 | 2026-08 | 16% | sufficient |
| medical_ai | 6 | 2023-12 | 2026-08 | 6% | sufficient |

## 3. Momentum

- no detectable change: 31 events in the last 24 months vs 25 before (ratio 1.24), p=0.504; minimum detectable ratio at 80% power is 2.12x
- Test: exact two-sided binomial p=0.504 (alpha=0.05), minimum detectable ratio at 80 % power 2.12x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 3 calibrated alert(s) in the last 8 quarters across 2 track(s) (32 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `medical_ai` 2025-Q2: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **reject** — shape spike (post-alert rate 0.00x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `endoscopy` 2025-Q2: 4 events against a baseline of 0.75 (z=3.75)
    - promotion: **reject** — shape spike (post-alert rate 0.67x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `medical_ai` 2026-Q2: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track endoscopy holds 47% of 102 material events across 4 tracks (HHI 0.35)

## 5. Independent corroboration

- 2 of 4 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: imaging_us, medical_ai

## 6. Contradictory evidence

- no contradictory observation found across the 4 checks run

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
