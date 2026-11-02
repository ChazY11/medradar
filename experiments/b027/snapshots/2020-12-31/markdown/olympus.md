# Olympus — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Olympus: 4 resolved legal entities from 4 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 47 material events across 7 technology tracks (4 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 27 | 2016-11 | 2020-12 | 57% | sufficient |
| surgical_energy | 12 | 2017-09 | 2020-05 | 26% | sufficient |
| urology | 4 | 2018-03 | 2020-08 | 9% | sufficient |
| general_surgery | 1 | 2017-10 | 2017-10 | 2% | single event |
| dental | 1 | 2019-08 | 2019-08 | 2% | single event |
| imaging_mr_ct | 1 | 2019-10 | 2019-10 | 2% | single event |
| imaging_us | 1 | 2020-11 | 2020-11 | 2% | single event |

## 3. Momentum

- no detectable change: 33 events in the last 24 months vs 27 before (ratio 1.22), p=0.519; minimum detectable ratio at 80% power is 2.07x
- Test: exact two-sided binomial p=0.519 (alpha=0.05), minimum detectable ratio at 80 % power 2.07x, detected=False

## 4. Concentration

- moderately concentrated: top track endoscopy holds 57% of 47 material events across 7 tracks (HHI 0.40)

## 5. Independent corroboration

- 1 of 7 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: dental, endoscopy, general_surgery, imaging_mr_ct, imaging_us, surgical_energy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 4 track(s) rest on a single event: dental, general_surgery, imaging_mr_ct, imaging_us — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: surgical_energy: 3 events in the last 24 months vs 9 before — this track is retreating, which cuts against a growth reading

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
