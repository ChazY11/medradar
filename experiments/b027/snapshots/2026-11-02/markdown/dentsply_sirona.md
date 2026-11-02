# Dentsply Sirona — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Dentsply Sirona: 1 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 54 material events across 6 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| dental | 44 | 2017-03 | 2026-03 | 81% | sufficient |
| medical_ai | 4 | 2020-08 | 2026-08 | 7% | sufficient |
| imaging_mr_ct | 2 | 2017-07 | 2018-04 | 4% | sufficient |
| rehab_exo | 2 | 2022-05 | 2026-09 | 4% | sufficient |
| infection_control | 1 | 2019-11 | 2019-11 | 2% | single event |
| general_surgery | 1 | 2022-03 | 2022-03 | 2% | single event |

## 3. Momentum

- no detectable change: 23 events in the last 24 months vs 11 before (ratio 2.09), p=0.058; minimum detectable ratio at 80% power is 2.79x
- Test: exact two-sided binomial p=0.058 (alpha=0.05), minimum detectable ratio at 80 % power 2.79x, detected=False

## 4. Concentration

- highly concentrated: top track dental holds 81% of 54 material events across 6 tracks (HHI 0.67)

## 5. Independent corroboration

- 1 of 6 technology tracks have independent device-trial support; 5 do not
- Tracks with **no** trial support: general_surgery, imaging_mr_ct, infection_control, medical_ai, rehab_exo

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: general_surgery, infection_control — a single filing is an anecdote; treat these tracks as unconfirmed

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
