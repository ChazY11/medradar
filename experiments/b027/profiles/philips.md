# Philips — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Philips: 36 resolved legal entities from 7 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 224 material events across 11 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 127 | 2016-11 | 2026-08 | 57% | sufficient |
| imaging_us | 45 | 2016-11 | 2026-09 | 20% | sufficient |
| patient_monitoring | 23 | 2017-03 | 2026-02 | 10% | sufficient |
| medical_ai | 12 | 2018-10 | 2026-03 | 5% | sufficient |
| wearable_remote | 7 | 2019-03 | 2026-09 | 3% | sufficient |
| cardiac_rhythm | 3 | 2019-06 | 2021-01 | 1% | sufficient |
| peripheral_vascular | 2 | 2016-12 | 2023-12 | 1% | sufficient |
| aesthetics | 2 | 2025-02 | 2025-12 | 1% | sufficient |
| dental | 1 | 2017-07 | 2017-07 | 0% | single event |
| respiratory | 1 | 2024-07 | 2024-07 | 0% | single event |
| vascular_access | 1 | 2025-06 | 2025-06 | 0% | single event |

## 3. Momentum

- activity rising: 73 events in the last 24 months vs 36 in the prior 24 (ratio 2.03)

## 4. Concentration

- moderately concentrated: top track imaging_mr_ct holds 57% of 224 material events across 11 tracks (HHI 0.38)

## 5. Independent corroboration

- 9 of 11 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: aesthetics, cardiac_rhythm

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: dental, respiratory, vascular_access — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
- Hiring evidence: 669 archived postings across 38 months (posting-flow proxy, not headcount)
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
