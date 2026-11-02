# Baxter — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Baxter: 10 resolved legal entities from 4 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 12 material events across 4 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 6 | 2016-11 | 2020-07 | 50% | sufficient |
| dialysis | 4 | 2017-01 | 2020-11 | 33% | sufficient |
| medical_ai | 1 | 2018-05 | 2018-05 | 8% | single event |
| endoscopy | 1 | 2020-01 | 2020-01 | 8% | single event |

## 3. Momentum

- no detectable change: 15 events in the last 24 months vs 9 before (ratio 1.67), p=0.307; minimum detectable ratio at 80% power is 3.26x
- Test: exact two-sided binomial p=0.307 (alpha=0.05), minimum detectable ratio at 80 % power 3.26x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 50% of 12 material events across 4 tracks (HHI 0.38)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: dialysis, endoscopy, medical_ai, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 22 of 50 months (56% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: endoscopy, medical_ai — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
- Hiring evidence: 69 archived postings across 21 months (posting-flow proxy, not headcount)
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
