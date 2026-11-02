# Envista — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Envista: 4 resolved legal entities from 4 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 33 material events across 4 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| dental | 24 | 2016-11 | 2024-01 | 73% | sufficient |
| imaging_mr_ct | 7 | 2016-11 | 2023-12 | 21% | sufficient |
| medical_ai | 1 | 2019-03 | 2019-03 | 3% | single event |
| rehab_exo | 1 | 2019-08 | 2019-08 | 3% | single event |

## 3. Momentum

- no detectable change: 6 events in the last 24 months vs 7 before (ratio 0.86), p=1.000; minimum detectable ratio at 80% power is 4.75x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 4.75x, detected=False

## 4. Concentration

- highly concentrated: top track dental holds 73% of 33 material events across 4 tracks (HHI 0.58)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: dental, imaging_mr_ct, medical_ai, rehab_exo

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 32 of 98 months (67% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 2 track(s) rest on a single event: medical_ai, rehab_exo — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: dental: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

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
