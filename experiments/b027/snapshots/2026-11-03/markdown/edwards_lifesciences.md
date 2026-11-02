# Edwards Lifesciences — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Edwards Lifesciences: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 58 material events across 6 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| medical_ai | 19 | 2017-04 | 2026-06 | 33% | sufficient |
| structural_heart | 17 | 2017-06 | 2025-12 | 29% | sufficient |
| patient_monitoring | 14 | 2018-03 | 2025-05 | 24% | sufficient |
| vascular_access | 5 | 2020-03 | 2026-04 | 9% | sufficient |
| peripheral_vascular | 2 | 2024-05 | 2024-05 | 3% | sufficient |
| wearable_remote | 1 | 2017-11 | 2017-11 | 2% | single event |

## 3. Momentum

- no detectable change: 19 events in the last 24 months vs 23 before (ratio 0.83), p=0.644; minimum detectable ratio at 80% power is 2.38x
- Test: exact two-sided binomial p=0.644 (alpha=0.05), minimum detectable ratio at 80 % power 2.38x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (37 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track medical_ai holds 33% of 58 material events across 6 tracks (HHI 0.26)

## 5. Independent corroboration

- 2 of 6 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: patient_monitoring, peripheral_vascular, vascular_access, wearable_remote

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 55 of 119 months (54% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: wearable_remote — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: patient_monitoring: 2 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
- Hiring evidence: 40 archived postings across 14 months (posting-flow proxy, not headcount)
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
