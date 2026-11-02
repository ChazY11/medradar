# Fresenius Medical Care — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Fresenius Medical Care: 7 resolved legal entities from 4 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 19 material events across 4 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| dialysis | 16 | 2017-05 | 2022-10 | 84% | sufficient |
| respiratory | 1 | 2020-02 | 2020-02 | 5% | single event |
| medical_ai | 1 | 2022-03 | 2022-03 | 5% | single event |
| vascular_access | 1 | 2022-03 | 2022-03 | 5% | single event |

## 3. Momentum

- no detectable change: 11 events in the last 24 months vs 13 before (ratio 0.85), p=0.839; minimum detectable ratio at 80% power is 3.15x
- Test: exact two-sided binomial p=0.839 (alpha=0.05), minimum detectable ratio at 80 % power 3.15x, detected=False

## 4. Concentration

- highly concentrated: top track dialysis holds 84% of 19 material events across 4 tracks (HHI 0.72)

## 5. Independent corroboration

- 3 of 4 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: respiratory

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 27 of 74 months (64% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 3 track(s) rest on a single event: medical_ai, respiratory, vascular_access — a single filing is an anecdote; treat these tracks as unconfirmed

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
