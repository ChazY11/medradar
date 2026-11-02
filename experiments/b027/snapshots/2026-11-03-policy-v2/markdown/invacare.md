# Invacare — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Invacare: 1 resolved legal entities from 2 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 9 material events across 1 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| rehab_exo | 9 | 2016-12 | 2021-03 | 100% | sufficient |

## 3. Momentum

- no material events in either 24-month period; momentum not estimable
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power not estimable, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (8 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- highly concentrated: top track rehab_exo holds 100% of 9 material events across 1 tracks (HHI 1.00)

## 5. Independent corroboration

- 0 of 1 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: rehab_exo

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 10 of 119 months (92% silent) — monthly series are mostly zeros; rate estimates are unstable

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
