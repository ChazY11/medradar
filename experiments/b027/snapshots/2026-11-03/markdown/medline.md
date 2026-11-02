# Medline Industries — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Medline Industries: 3 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 43 material events across 8 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| trauma | 11 | 2016-12 | 2024-08 | 26% | sufficient |
| respiratory | 10 | 2023-06 | 2026-03 | 23% | sufficient |
| surgical_energy | 7 | 2018-04 | 2024-12 | 16% | sufficient |
| vascular_access | 5 | 2017-01 | 2026-07 | 12% | sufficient |
| wound_care | 4 | 2018-07 | 2024-03 | 9% | sufficient |
| general_surgery | 3 | 2021-12 | 2024-03 | 7% | sufficient |
| infection_control | 2 | 2017-01 | 2024-03 | 5% | sufficient |
| patient_monitoring | 1 | 2026-06 | 2026-06 | 2% | single event |

## 3. Momentum

- activity decreasing: 11 events in the last 24 months vs 25 before (ratio 0.44), exact two-sided p=0.029
- Test: exact two-sided binomial p=0.029 (alpha=0.05), minimum detectable ratio at 80 % power 2.76x, detected=True
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (42 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- diversified: top track trauma holds 26% of 43 material events across 8 tracks (HHI 0.18)

## 5. Independent corroboration

- 2 of 8 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: general_surgery, infection_control, respiratory, surgical_energy, trauma, vascular_access

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: patient_monitoring — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: trauma: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: respiratory: 3 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

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
