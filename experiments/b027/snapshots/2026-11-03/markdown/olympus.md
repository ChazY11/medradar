# Olympus — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Olympus: 4 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 102 material events across 7 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 56 | 2016-11 | 2026-09 | 55% | sufficient |
| surgical_energy | 25 | 2017-09 | 2026-07 | 25% | sufficient |
| urology | 8 | 2018-03 | 2026-05 | 8% | sufficient |
| imaging_us | 6 | 2020-11 | 2026-07 | 6% | sufficient |
| dental | 4 | 2019-08 | 2026-09 | 4% | sufficient |
| general_surgery | 2 | 2017-10 | 2021-08 | 2% | sufficient |
| imaging_mr_ct | 1 | 2019-10 | 2019-10 | 1% | single event |

## 3. Momentum

- activity increasing: 50 events in the last 24 months vs 12 before (ratio 4.17), exact two-sided p=0.000
- Test: exact two-sided binomial p=0.000 (alpha=0.05), minimum detectable ratio at 80 % power 2.46x, detected=True
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 4 calibrated alert(s) in the last 8 quarters across 4 track(s) (33 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `surgical_energy` 2025-Q4: 4 events against a baseline of 0.12 (z=10.96)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `endoscopy` 2025-Q2: 6 events against a baseline of 0.88 (z=5.48)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `dental` 2026-Q3: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **reject** — shape unknown (no confirmation quarters available); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - `imaging_us` 2025-Q3: 2 events against a baseline of 0.12 (z=5.3)
    - promotion: **promote_pending_signoff** — shape level (post-alert rate is elevated and flat); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track endoscopy holds 55% of 102 material events across 7 tracks (HHI 0.37)

## 5. Independent corroboration

- 1 of 7 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: dental, endoscopy, general_surgery, imaging_mr_ct, imaging_us, surgical_energy

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed

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
