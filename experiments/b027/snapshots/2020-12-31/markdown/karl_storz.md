# Karl Storz — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Karl Storz: 3 resolved legal entities from 2 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 21 material events across 6 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 11 | 2017-03 | 2020-11 | 52% | sufficient |
| urology | 4 | 2017-07 | 2020-10 | 19% | sufficient |
| ent | 3 | 2019-03 | 2020-08 | 14% | sufficient |
| surgical_energy | 1 | 2017-08 | 2017-08 | 5% | single event |
| medical_ai | 1 | 2020-07 | 2020-07 | 5% | single event |
| imaging_mr_ct | 1 | 2020-12 | 2020-12 | 5% | single event |

## 3. Momentum

- no detectable change: 17 events in the last 24 months vs 13 before (ratio 1.31), p=0.585; minimum detectable ratio at 80% power is 2.81x
- Test: exact two-sided binomial p=0.585 (alpha=0.05), minimum detectable ratio at 80 % power 2.81x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 52% of 21 material events across 6 tracks (HHI 0.34)

## 5. Independent corroboration

- 0 of 6 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: endoscopy, ent, imaging_mr_ct, medical_ai, surgical_energy, urology

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 23 of 50 months (54% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 3 track(s) rest on a single event: imaging_mr_ct, medical_ai, surgical_energy — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
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
