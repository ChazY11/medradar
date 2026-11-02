# Biotronik — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Biotronik: 2 resolved legal entities from 2 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 9 material events across 3 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| coronary | 4 | 2017-01 | 2024-10 | 44% | sufficient |
| peripheral_vascular | 4 | 2022-07 | 2025-04 | 44% | sufficient |
| neurostimulation | 1 | 2023-03 | 2023-03 | 11% | single event |

## 3. Momentum

- no detectable change: 3 events in the last 24 months vs 5 before (ratio 0.60), p=0.727; minimum detectable ratio at 80% power is 7.74x
- Test: exact two-sided binomial p=0.727 (alpha=0.05), minimum detectable ratio at 80 % power 7.74x, detected=False

## 4. Concentration

- moderately concentrated: top track coronary holds 44% of 9 material events across 3 tracks (HHI 0.41)

## 5. Independent corroboration

- 1 of 3 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: neurostimulation, peripheral_vascular

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 22 of 119 months (82% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: neurostimulation — a single filing is an anecdote; treat these tracks as unconfirmed

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
