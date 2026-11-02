# Integra LifeSciences — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Integra LifeSciences: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 16 material events across 6 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| general_surgery | 6 | 2017-09 | 2022-08 | 38% | sufficient |
| ortho_joint | 3 | 2018-06 | 2019-12 | 19% | sufficient |
| trauma | 2 | 2018-11 | 2021-07 | 12% | sufficient |
| surgical_energy | 2 | 2018-11 | 2021-05 | 12% | sufficient |
| neurovascular | 2 | 2019-01 | 2021-04 | 12% | sufficient |
| wound_care | 1 | 2021-10 | 2021-10 | 6% | single event |

## 3. Momentum

- no detectable change: 7 events in the last 24 months vs 8 before (ratio 0.88), p=1.000; minimum detectable ratio at 80% power is 4.26x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 4.26x, detected=False

## 4. Concentration

- diversified: top track general_surgery holds 38% of 16 material events across 6 tracks (HHI 0.23)

## 5. Independent corroboration

- 2 of 6 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: general_surgery, ortho_joint, surgical_energy, trauma

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 21 of 74 months (72% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: wound_care — a single filing is an anecdote; treat these tracks as unconfirmed

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
