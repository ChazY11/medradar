# Boston Scientific — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Boston Scientific: 7 resolved legal entities from 6 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 65 material events across 12 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| endoscopy | 12 | 2017-02 | 2020-09 | 18% | sufficient |
| coronary | 10 | 2016-12 | 2020-08 | 15% | sufficient |
| peripheral_vascular | 7 | 2016-11 | 2020-10 | 11% | sufficient |
| medical_ai | 7 | 2017-03 | 2020-07 | 11% | sufficient |
| neurostimulation | 7 | 2017-08 | 2020-12 | 11% | sufficient |
| urology | 7 | 2017-12 | 2020-08 | 11% | sufficient |
| vascular_access | 4 | 2018-06 | 2020-10 | 6% | sufficient |
| imaging_us | 3 | 2017-11 | 2020-04 | 5% | sufficient |
| surgical_energy | 3 | 2019-03 | 2020-12 | 5% | sufficient |
| cardiac_rhythm | 2 | 2017-07 | 2019-03 | 3% | sufficient |
| ep_pfa | 2 | 2017-12 | 2019-10 | 3% | sufficient |
| structural_heart | 1 | 2019-04 | 2019-04 | 2% | single event |

## 3. Momentum

- no detectable change: 54 events in the last 24 months vs 46 before (ratio 1.17), p=0.484; minimum detectable ratio at 80% power is 1.75x
- Test: exact two-sided binomial p=0.484 (alpha=0.05), minimum detectable ratio at 80 % power 1.75x, detected=False

## 4. Concentration

- diversified: top track endoscopy holds 18% of 65 material events across 12 tracks (HHI 0.11)

## 5. Independent corroboration

- 5 of 12 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: cardiac_rhythm, coronary, medical_ai, structural_heart, surgical_energy, urology, vascular_access

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: structural_heart — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: coronary: 1 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading
- `activity_decline_by_track`: endoscopy: 4 events in the last 24 months vs 8 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
- Hiring evidence: 4999 archived postings across 123 months (posting-flow proxy, not headcount)
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
