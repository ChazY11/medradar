# Biotronik — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Biotronik: 2 resolved legal entities from 2 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 8 material events across 3 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| coronary | 4 | 2017-01 | 2024-10 | 50% | sufficient |
| peripheral_vascular | 3 | 2022-07 | 2024-07 | 38% | sufficient |
| neurostimulation | 1 | 2023-03 | 2023-03 | 12% | single event |

## 3. Momentum

- no detectable change: 6 events in the last 24 months vs 4 before (ratio 1.50), p=0.754; minimum detectable ratio at 80% power is 6.10x
- Test: exact two-sided binomial p=0.754 (alpha=0.05), minimum detectable ratio at 80 % power 6.10x, detected=False

## 4. Concentration

- moderately concentrated: top track coronary holds 50% of 8 material events across 3 tracks (HHI 0.41)

## 5. Independent corroboration

- 1 of 3 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: neurostimulation, peripheral_vascular

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 20 of 98 months (80% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: neurostimulation — a single filing is an anecdote; treat these tracks as unconfirmed

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
