# Terumo — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Terumo: 11 resolved legal entities from 4 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 10 material events across 3 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| vascular_access | 7 | 2017-07 | 2020-01 | 70% | sufficient |
| coronary | 2 | 2017-01 | 2017-09 | 20% | sufficient |
| ivd_poct | 1 | 2018-11 | 2018-11 | 10% | single event |

## 3. Momentum

- activity decreasing: 5 events in the last 24 months vs 15 before (ratio 0.33), exact two-sided p=0.041
- Test: exact two-sided binomial p=0.041 (alpha=0.05), minimum detectable ratio at 80 % power 4.25x, detected=True

## 4. Concentration

- highly concentrated: top track vascular_access holds 70% of 10 material events across 3 tracks (HHI 0.54)

## 5. Independent corroboration

- 0 of 3 technology tracks have independent device-trial support; 3 do not
- Tracks with **no** trial support: coronary, ivd_poct, vascular_access

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 19 of 50 months (62% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: ivd_poct — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: vascular_access: 2 events in the last 24 months vs 5 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
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
