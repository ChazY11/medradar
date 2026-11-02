# Globus Medical — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Globus Medical: 3 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 100 material events across 5 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 42 | 2017-01 | 2026-05 | 42% | sufficient |
| trauma | 34 | 2017-03 | 2026-06 | 34% | sufficient |
| ortho_joint | 21 | 2017-08 | 2026-08 | 21% | sufficient |
| endoscopy | 2 | 2018-03 | 2019-04 | 2% | sufficient |
| imaging_mr_ct | 1 | 2021-08 | 2021-08 | 1% | single event |

## 3. Momentum

- no detectable change: 15 events in the last 24 months vs 22 before (ratio 0.68), p=0.324; minimum detectable ratio at 80% power is 2.56x
- Test: exact two-sided binomial p=0.324 (alpha=0.05), minimum detectable ratio at 80 % power 2.56x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 2 calibrated alert(s) in the last 8 quarters across 2 track(s) (24 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `spine` 2026-Q2: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **reject** — shape spike (post-alert rate 0.00x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `trauma` 2026-Q2: 2 events against a baseline of 0.25 (z=3.5)
    - promotion: **reject** — shape spike (post-alert rate 0.00x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track spine holds 42% of 100 material events across 5 tracks (HHI 0.34)

## 5. Independent corroboration

- 0 of 5 technology tracks have independent device-trial support; 5 do not
- Tracks with **no** trial support: endoscopy, imaging_mr_ct, ortho_joint, spine, trauma

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: spine: 3 events in the last 24 months vs 10 before — this track is retreating, which cuts against a growth reading

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
