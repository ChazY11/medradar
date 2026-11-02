# Hologic — technology profile

*As of 2022-12-31. Evidence window 2016-11 to 2022-12 (74 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Hologic: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2022-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 21 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ivd_molecular | 14 | 2017-02 | 2022-06 | 67% | sufficient |
| imaging_mr_ct | 4 | 2017-10 | 2020-10 | 19% | sufficient |
| medical_ai | 2 | 2020-11 | 2022-10 | 10% | sufficient |
| womens_health | 1 | 2018-04 | 2018-04 | 5% | single event |

## 3. Momentum

- activity decreasing: 3 events in the last 24 months vs 12 before (ratio 0.25), exact two-sided p=0.035
- Test: exact two-sided binomial p=0.035 (alpha=0.05), minimum detectable ratio at 80 % power 6.10x, detected=True

## 4. Concentration

- moderately concentrated: top track ivd_molecular holds 67% of 21 material events across 4 tracks (HHI 0.49)

## 5. Independent corroboration

- 2 of 4 technology tracks have independent device-trial support; 2 do not
- Tracks with **no** trial support: ivd_molecular, medical_ai

## 6. Contradictory evidence

- 4 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 24 of 74 months (68% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: womens_health — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: ivd_molecular: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: imaging_mr_ct: 0 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2022-12-31; window 2016-11 to 2022-12
- Hiring evidence: 87 archived postings across 22 months (posting-flow proxy, not headcount)
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
