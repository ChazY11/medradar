# Siemens Healthineers — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Siemens Healthineers: 17 resolved legal entities from 6 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 277 material events across 8 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 194 | 2016-11 | 2024-11 | 70% | sufficient |
| imaging_us | 41 | 2017-01 | 2024-11 | 15% | sufficient |
| medical_ai | 19 | 2018-10 | 2024-08 | 7% | sufficient |
| ivd_immuno | 14 | 2017-04 | 2024-07 | 5% | sufficient |
| surgical_energy | 5 | 2020-08 | 2024-07 | 2% | sufficient |
| urology | 2 | 2017-08 | 2024-02 | 1% | sufficient |
| ivd_poct | 1 | 2020-03 | 2020-03 | 0% | single event |
| respiratory | 1 | 2022-08 | 2022-08 | 0% | single event |

## 3. Momentum

- no detectable change: 110 events in the last 24 months vs 91 before (ratio 1.21), p=0.204; minimum detectable ratio at 80% power is 1.49x
- Test: exact two-sided binomial p=0.204 (alpha=0.05), minimum detectable ratio at 80 % power 1.49x, detected=False

## 4. Concentration

- highly concentrated: top track imaging_mr_ct holds 70% of 277 material events across 8 tracks (HHI 0.52)

## 5. Independent corroboration

- 2 of 8 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: imaging_mr_ct, imaging_us, ivd_immuno, ivd_poct, respiratory, surgical_energy

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: ivd_poct, respiratory — a single filing is an anecdote; treat these tracks as unconfirmed

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
