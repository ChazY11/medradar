# Teleflex — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Teleflex: 7 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 19 material events across 5 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 8 | 2016-12 | 2025-03 | 42% | sufficient |
| wound_care | 7 | 2017-10 | 2026-07 | 37% | sufficient |
| peripheral_vascular | 2 | 2019-02 | 2022-09 | 11% | sufficient |
| endoscopy | 1 | 2023-04 | 2023-04 | 5% | single event |
| coronary | 1 | 2024-09 | 2024-09 | 5% | single event |

## 3. Momentum

- no detectable change: 12 events in the last 24 months vs 6 before (ratio 2.00), p=0.238; minimum detectable ratio at 80% power is 4.06x
- Test: exact two-sided binomial p=0.238 (alpha=0.05), minimum detectable ratio at 80 % power 4.06x, detected=False

## 4. Concentration

- moderately concentrated: top track vascular_access holds 42% of 19 material events across 5 tracks (HHI 0.33)

## 5. Independent corroboration

- 2 of 5 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: endoscopy, peripheral_vascular, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 31 of 119 months (74% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: coronary, endoscopy — a single filing is an anecdote; treat these tracks as unconfirmed

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
