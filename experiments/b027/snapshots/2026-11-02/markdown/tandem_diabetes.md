# Tandem Diabetes Care — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Tandem Diabetes Care: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 14 material events across 3 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| insulin_delivery | 12 | 2018-06 | 2025-11 | 86% | sufficient |
| diabetes_cgm | 1 | 2017-08 | 2017-08 | 7% | single event |
| vascular_access | 1 | 2025-08 | 2025-08 | 7% | single event |

## 3. Momentum

- no detectable change: 6 events in the last 24 months vs 6 before (ratio 1.00), p=1.000; minimum detectable ratio at 80% power is 5.04x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 5.04x, detected=False

## 4. Concentration

- highly concentrated: top track insulin_delivery holds 86% of 14 material events across 3 tracks (HHI 0.74)

## 5. Independent corroboration

- 2 of 3 technology tracks have independent device-trial support; 1 do not
- Tracks with **no** trial support: vascular_access

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 18 of 119 months (85% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: diabetes_cgm, vascular_access — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: insulin_delivery: 2 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

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
