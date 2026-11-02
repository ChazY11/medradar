# Fresenius Medical Care — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Fresenius Medical Care: 7 resolved legal entities from 4 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 32 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| dialysis | 26 | 2017-05 | 2026-01 | 81% | sufficient |
| vascular_access | 3 | 2022-03 | 2023-06 | 9% | sufficient |
| respiratory | 2 | 2020-02 | 2024-04 | 6% | sufficient |
| medical_ai | 1 | 2022-03 | 2022-03 | 3% | single event |

## 3. Momentum

- no detectable change: 17 events in the last 24 months vs 14 before (ratio 1.21), p=0.720; minimum detectable ratio at 80% power is 2.75x
- Test: exact two-sided binomial p=0.720 (alpha=0.05), minimum detectable ratio at 80 % power 2.75x, detected=False

## 4. Concentration

- highly concentrated: top track dialysis holds 81% of 32 material events across 4 tracks (HHI 0.67)

## 5. Independent corroboration

- 3 of 4 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: respiratory

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 47 of 119 months (61% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: medical_ai — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
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
