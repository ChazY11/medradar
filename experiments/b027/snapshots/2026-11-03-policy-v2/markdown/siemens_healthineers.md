# Siemens Healthineers — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Siemens Healthineers: 17 resolved legal entities from 6 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 327 material events across 8 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 220 | 2016-11 | 2026-09 | 67% | sufficient |
| imaging_us | 46 | 2017-01 | 2026-09 | 14% | sufficient |
| medical_ai | 35 | 2018-10 | 2026-09 | 11% | sufficient |
| ivd_immuno | 14 | 2017-04 | 2024-07 | 4% | sufficient |
| urology | 5 | 2017-08 | 2026-05 | 2% | sufficient |
| surgical_energy | 5 | 2020-08 | 2024-07 | 2% | sufficient |
| ivd_poct | 1 | 2020-03 | 2020-03 | 0% | single event |
| respiratory | 1 | 2022-08 | 2022-08 | 0% | single event |

## 3. Momentum

- no detectable change: 92 events in the last 24 months vs 105 before (ratio 0.88), p=0.393; minimum detectable ratio at 80% power is 1.49x
- Test: exact two-sided binomial p=0.393 (alpha=0.05), minimum detectable ratio at 80 % power 1.49x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, 1 calibrated alert(s) in the last 8 quarters across 1 track(s) (48 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - `medical_ai` 2026-Q2: 6 events against a baseline of 1.5 (z=3.67)
    - promotion: **reject** — shape spike (post-alert rate 1.33x baseline is below the 1.5x floor); sign-off required=true; promotion marks a change in public filing rate, not in technology
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track imaging_mr_ct holds 67% of 327 material events across 8 tracks (HHI 0.49)

## 5. Independent corroboration

- 2 of 8 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: imaging_mr_ct, imaging_us, ivd_immuno, ivd_poct, respiratory, surgical_energy

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: ivd_poct, respiratory — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: ivd_immuno: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: surgical_energy: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

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
