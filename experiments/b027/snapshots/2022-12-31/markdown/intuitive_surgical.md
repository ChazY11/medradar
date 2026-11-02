# Intuitive Surgical — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Intuitive Surgical: 2 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 64 material events across 4 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| surgical_robotics | 51 | 2017-01 | 2022-11 | 80% | sufficient |
| endoscopy | 11 | 2017-09 | 2022-06 | 17% | sufficient |
| imaging_mr_ct | 1 | 2019-02 | 2019-02 | 2% | single event |
| surgical_energy | 1 | 2022-11 | 2022-11 | 2% | single event |

## 3. Momentum

- no detectable change: 16 events in the last 24 months vs 19 before (ratio 0.84), p=0.736; minimum detectable ratio at 80% power is 2.59x
- Test: exact two-sided binomial p=0.736 (alpha=0.05), minimum detectable ratio at 80 % power 2.59x, detected=False

## 4. Concentration

- highly concentrated: top track surgical_robotics holds 80% of 64 material events across 4 tracks (HHI 0.67)

## 5. Independent corroboration

- 2 of 4 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: imaging_mr_ct, surgical_energy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: imaging_mr_ct, surgical_energy — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: endoscopy: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
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
