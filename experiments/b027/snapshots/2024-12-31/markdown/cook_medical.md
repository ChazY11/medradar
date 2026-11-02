# Cook Medical — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Cook Medical: 11 resolved legal entities from 5 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 95 material events across 11 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 35 | 2017-05 | 2024-06 | 37% | sufficient |
| endoscopy | 22 | 2017-04 | 2022-04 | 23% | sufficient |
| coronary | 16 | 2016-12 | 2022-02 | 17% | sufficient |
| urology | 5 | 2018-02 | 2018-06 | 5% | sufficient |
| dental | 4 | 2017-01 | 2018-07 | 4% | sufficient |
| surgical_energy | 4 | 2017-08 | 2020-01 | 4% | sufficient |
| imaging_us | 3 | 2017-08 | 2023-05 | 3% | sufficient |
| peripheral_vascular | 2 | 2017-02 | 2020-10 | 2% | sufficient |
| respiratory | 2 | 2017-02 | 2017-08 | 2% | sufficient |
| dialysis | 1 | 2017-01 | 2017-01 | 1% | single event |
| neurovascular | 1 | 2018-12 | 2018-12 | 1% | single event |

## 3. Momentum

- no detectable change: 9 events in the last 24 months vs 11 before (ratio 0.82), p=0.824; minimum detectable ratio at 80% power is 3.52x
- Test: exact two-sided binomial p=0.824 (alpha=0.05), minimum detectable ratio at 80 % power 3.52x, detected=False

## 4. Concentration

- diversified: top track vascular_access holds 37% of 95 material events across 11 tracks (HHI 0.23)

## 5. Independent corroboration

- 1 of 11 technology tracks have independent device-trial support; 10 do not
- Tracks with **no** trial support: coronary, dental, dialysis, endoscopy, imaging_us, neurovascular, respiratory, surgical_energy

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: dialysis, neurovascular — a single filing is an anecdote; treat these tracks as unconfirmed

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
