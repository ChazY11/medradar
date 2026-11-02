# Penumbra — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Penumbra: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 48 material events across 4 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| peripheral_vascular | 22 | 2017-05 | 2026-04 | 46% | sufficient |
| neurovascular | 18 | 2017-04 | 2026-06 | 38% | sufficient |
| vascular_access | 6 | 2022-05 | 2024-12 | 12% | sufficient |
| endoscopy | 2 | 2017-08 | 2019-08 | 4% | sufficient |

## 3. Momentum

- no detectable change: 8 events in the last 24 months vs 11 before (ratio 0.73), p=0.648; minimum detectable ratio at 80% power is 3.68x
- Test: exact two-sided binomial p=0.648 (alpha=0.05), minimum detectable ratio at 80 % power 3.68x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 1 calibrated alert(s) in the last 8 quarters across 1 track(s) (24 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `vascular_access` 2024-Q4: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **reject** — shape spike (post-alert rate 0.00x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track peripheral_vascular holds 46% of 48 material events across 4 tracks (HHI 0.37)

## 5. Independent corroboration

- 1 of 4 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: endoscopy, neurovascular, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 46 of 119 months (61% silent) — monthly series are mostly zeros; rate estimates are unstable
- `activity_decline_by_track`: peripheral_vascular: 3 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

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
