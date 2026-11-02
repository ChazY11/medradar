# Integra LifeSciences — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Integra LifeSciences: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 20 material events across 7 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| general_surgery | 8 | 2017-09 | 2024-07 | 40% | sufficient |
| ortho_joint | 3 | 2018-06 | 2019-12 | 15% | sufficient |
| neurovascular | 3 | 2019-01 | 2024-02 | 15% | sufficient |
| trauma | 2 | 2018-11 | 2021-07 | 10% | sufficient |
| surgical_energy | 2 | 2018-11 | 2021-05 | 10% | sufficient |
| wound_care | 1 | 2021-10 | 2021-10 | 5% | single event |
| endoscopy | 1 | 2024-01 | 2024-01 | 5% | single event |

## 3. Momentum

- no detectable change: 6 events in the last 24 months vs 7 before (ratio 0.86), p=1.000; minimum detectable ratio at 80% power is 4.75x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 4.75x, detected=False

## 4. Concentration

- diversified: top track general_surgery holds 40% of 20 material events across 7 tracks (HHI 0.23)

## 5. Independent corroboration

- 2 of 7 technology tracks have independent device-trial support; 5 do not
- Tracks with **no** trial support: endoscopy, general_surgery, ortho_joint, surgical_energy, trauma

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 27 of 98 months (72% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: endoscopy, wound_care — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
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
