# Cook Medical — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Cook Medical: 11 resolved legal entities from 5 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 101 material events across 11 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 35 | 2017-05 | 2024-06 | 35% | sufficient |
| endoscopy | 24 | 2017-04 | 2026-07 | 24% | sufficient |
| coronary | 17 | 2016-12 | 2025-11 | 17% | sufficient |
| surgical_energy | 6 | 2017-08 | 2025-09 | 6% | sufficient |
| urology | 5 | 2018-02 | 2018-06 | 5% | sufficient |
| dental | 4 | 2017-01 | 2018-07 | 4% | sufficient |
| imaging_us | 3 | 2017-08 | 2023-05 | 3% | sufficient |
| peripheral_vascular | 2 | 2017-02 | 2020-10 | 2% | sufficient |
| respiratory | 2 | 2017-02 | 2017-08 | 2% | sufficient |
| neurovascular | 2 | 2018-12 | 2025-05 | 2% | sufficient |
| dialysis | 1 | 2017-01 | 2017-01 | 1% | single event |

## 3. Momentum

- no detectable change: 8 events in the last 24 months vs 10 before (ratio 0.80), p=0.815; minimum detectable ratio at 80% power is 3.78x
- Test: exact two-sided binomial p=0.815 (alpha=0.05), minimum detectable ratio at 80 % power 3.78x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (25 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- diversified: top track vascular_access holds 35% of 101 material events across 11 tracks (HHI 0.21)

## 5. Independent corroboration

- 1 of 11 technology tracks have independent device-trial support; 10 do not
- Tracks with **no** trial support: coronary, dental, dialysis, endoscopy, imaging_us, neurovascular, respiratory, surgical_energy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: dialysis — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: vascular_access: 0 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

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
