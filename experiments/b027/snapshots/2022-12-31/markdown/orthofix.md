# Orthofix — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Orthofix: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 34 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 20 | 2016-12 | 2022-02 | 59% | sufficient |
| trauma | 11 | 2017-01 | 2022-05 | 32% | sufficient |
| ortho_joint | 2 | 2017-03 | 2018-03 | 6% | sufficient |
| imaging_mr_ct | 1 | 2020-10 | 2020-10 | 3% | single event |

## 3. Momentum

- no detectable change: 11 events in the last 24 months vs 13 before (ratio 0.85), p=0.839; minimum detectable ratio at 80% power is 3.15x
- Test: exact two-sided binomial p=0.839 (alpha=0.05), minimum detectable ratio at 80 % power 3.15x, detected=False

## 4. Concentration

- moderately concentrated: top track spine holds 59% of 34 material events across 4 tracks (HHI 0.46)

## 5. Independent corroboration

- 1 of 4 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: imaging_mr_ct, ortho_joint, trauma

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 31 of 74 months (58% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
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
