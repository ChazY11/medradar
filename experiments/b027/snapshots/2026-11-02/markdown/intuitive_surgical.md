# Intuitive Surgical — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Intuitive Surgical: 2 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 116 material events across 6 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| surgical_robotics | 86 | 2017-01 | 2026-09 | 74% | sufficient |
| endoscopy | 22 | 2017-09 | 2026-07 | 19% | sufficient |
| surgical_energy | 4 | 2022-11 | 2024-08 | 3% | sufficient |
| medical_ai | 2 | 2024-12 | 2025-12 | 2% | sufficient |
| imaging_mr_ct | 1 | 2019-02 | 2019-02 | 1% | single event |
| wound_care | 1 | 2025-03 | 2025-03 | 1% | single event |

## 3. Momentum

- no detectable change: 34 events in the last 24 months vs 22 before (ratio 1.55), p=0.141; minimum detectable ratio at 80% power is 2.15x
- Test: exact two-sided binomial p=0.141 (alpha=0.05), minimum detectable ratio at 80 % power 2.15x, detected=False

## 4. Concentration

- highly concentrated: top track surgical_robotics holds 74% of 116 material events across 6 tracks (HHI 0.59)

## 5. Independent corroboration

- 3 of 6 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: medical_ai, surgical_energy, wound_care

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: imaging_mr_ct, wound_care — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: surgical_energy: 0 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
- Hiring evidence: 532 archived postings across 18 months (posting-flow proxy, not headcount)
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
