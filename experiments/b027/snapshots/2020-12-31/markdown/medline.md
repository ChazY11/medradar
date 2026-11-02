# Medline Industries — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Medline Industries: 3 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 16 material events across 5 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| trauma | 4 | 2016-12 | 2020-06 | 25% | sufficient |
| vascular_access | 4 | 2017-01 | 2019-09 | 25% | sufficient |
| surgical_energy | 4 | 2018-04 | 2020-10 | 25% | sufficient |
| wound_care | 3 | 2018-07 | 2019-03 | 19% | sufficient |
| infection_control | 1 | 2017-01 | 2017-01 | 6% | single event |

## 3. Momentum

- no detectable change: 31 events in the last 24 months vs 19 before (ratio 1.63), p=0.119; minimum detectable ratio at 80% power is 2.26x
- Test: exact two-sided binomial p=0.119 (alpha=0.05), minimum detectable ratio at 80 % power 2.26x, detected=False

## 4. Concentration

- diversified: top track trauma holds 25% of 16 material events across 5 tracks (HHI 0.23)

## 5. Independent corroboration

- 1 of 5 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: infection_control, surgical_energy, trauma, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: infection_control — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: vascular_access: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

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
