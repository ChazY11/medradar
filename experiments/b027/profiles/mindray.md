# Mindray — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Mindray: 2 resolved legal entities from 2 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 82 material events across 3 technology tracks (0 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_us | 58 | 2016-12 | 2026-05 | 71% | sufficient |
| patient_monitoring | 16 | 2017-08 | 2026-05 | 20% | sufficient |
| respiratory | 8 | 2018-01 | 2026-06 | 10% | sufficient |

## 3. Momentum

- no detectable change: 18 events in the last 24 months vs 12 before (ratio 1.50), p=0.362; minimum detectable ratio at 80% power is 2.84x
- Test: exact two-sided binomial p=0.362 (alpha=0.05), minimum detectable ratio at 80 % power 2.84x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 1 calibrated alert(s) in the last 8 quarters across 1 track(s) (18 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `respiratory` 2026-Q2: 2 events against a baseline of 0.25 (z=3.5)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- highly concentrated: top track imaging_us holds 71% of 82 material events across 3 tracks (HHI 0.55)

## 5. Independent corroboration

- 0 of 3 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: imaging_us, patient_monitoring, respiratory

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 58 of 119 months (51% silent) — monthly series are mostly zeros; rate estimates are unstable

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
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
