# Ambu — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Ambu: 2 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 2 material events across 2 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 1 | 2018-03 | 2018-03 | 50% | single event |
| urology | 1 | 2020-04 | 2020-04 | 50% | single event |

## 3. Momentum

- no detectable change: 4 events in the last 24 months vs 2 before (ratio 2.00), p=0.688; minimum detectable ratio at 80% power is 11.32x
- Test: exact two-sided binomial p=0.688 (alpha=0.05), minimum detectable ratio at 80 % power 11.32x, detected=False

## 4. Concentration

- highly concentrated: top track endoscopy holds 50% of 2 material events across 2 tracks (HHI 0.50)

## 5. Independent corroboration

- 2 of 2 technology tracks have independent device-trial support; 0 do not

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 6 of 50 months (88% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: endoscopy, urology — a single filing is an anecdote; treat these tracks as unconfirmed

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
