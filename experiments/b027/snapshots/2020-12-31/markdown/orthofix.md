# Orthofix — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Orthofix: 4 resolved legal entities from 3 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 25 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| spine | 14 | 2016-12 | 2020-10 | 56% | sufficient |
| trauma | 8 | 2017-01 | 2020-05 | 32% | sufficient |
| ortho_joint | 2 | 2017-03 | 2018-03 | 8% | sufficient |
| imaging_mr_ct | 1 | 2020-10 | 2020-10 | 4% | single event |

## 3. Momentum

- no detectable change: 13 events in the last 24 months vs 18 before (ratio 0.72), p=0.473; minimum detectable ratio at 80% power is 2.77x
- Test: exact two-sided binomial p=0.473 (alpha=0.05), minimum detectable ratio at 80 % power 2.77x, detected=False

## 4. Concentration

- moderately concentrated: top track spine holds 56% of 25 material events across 4 tracks (HHI 0.42)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: imaging_mr_ct, ortho_joint, spine, trauma

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 23 of 50 months (54% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 1 track(s) rest on a single event: imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: trauma: 2 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading

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
