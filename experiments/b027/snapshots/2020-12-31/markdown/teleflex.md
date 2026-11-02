# Teleflex — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Teleflex: 7 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 9 material events across 3 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| wound_care | 5 | 2017-10 | 2020-03 | 56% | sufficient |
| vascular_access | 3 | 2016-12 | 2018-11 | 33% | sufficient |
| peripheral_vascular | 1 | 2019-02 | 2019-02 | 11% | single event |

## 3. Momentum

- no detectable change: 6 events in the last 24 months vs 8 before (ratio 0.75), p=0.791; minimum detectable ratio at 80% power is 4.54x
- Test: exact two-sided binomial p=0.791 (alpha=0.05), minimum detectable ratio at 80 % power 4.54x, detected=False

## 4. Concentration

- moderately concentrated: top track wound_care holds 56% of 9 material events across 3 tracks (HHI 0.43)

## 5. Independent corroboration

- 1 of 3 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: peripheral_vascular, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 12 of 50 months (76% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: peripheral_vascular — a single filing is an anecdote; treat these tracks as unconfirmed

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
