# Smith & Nephew — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Smith & Nephew: 5 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 116 material events across 6 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 54 | 2016-11 | 2026-09 | 47% | sufficient |
| wound_care | 27 | 2017-04 | 2026-09 | 23% | sufficient |
| trauma | 23 | 2016-11 | 2025-02 | 20% | sufficient |
| endoscopy | 10 | 2017-06 | 2022-10 | 9% | sufficient |
| medical_ai | 1 | 2022-08 | 2022-08 | 1% | single event |
| general_surgery | 1 | 2024-03 | 2024-03 | 1% | single event |

## 3. Momentum

- no detectable change: 22 events in the last 24 months vs 32 before (ratio 0.69), p=0.220; minimum detectable ratio at 80% power is 2.17x
- Test: exact two-sided binomial p=0.220 (alpha=0.05), minimum detectable ratio at 80 % power 2.17x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (31 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track ortho_joint holds 47% of 116 material events across 6 tracks (HHI 0.32)

## 5. Independent corroboration

- 5 of 6 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: endoscopy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: general_surgery, medical_ai — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: trauma: 2 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

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
