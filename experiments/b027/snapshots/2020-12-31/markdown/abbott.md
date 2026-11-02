# Abbott — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Abbott: 26 resolved legal entities from 10 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 47 material events across 16 technology tracks (8 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| medical_ai | 12 | 2016-12 | 2020-11 | 26% | sufficient |
| ivd_molecular | 6 | 2017-05 | 2020-08 | 13% | sufficient |
| coronary | 6 | 2017-08 | 2020-07 | 13% | sufficient |
| diabetes_cgm | 4 | 2017-09 | 2020-06 | 9% | sufficient |
| ep_pfa | 3 | 2017-02 | 2019-09 | 6% | sufficient |
| heart_failure | 3 | 2017-08 | 2019-12 | 6% | sufficient |
| vascular_access | 3 | 2019-04 | 2019-12 | 6% | sufficient |
| cardiac_rhythm | 2 | 2016-11 | 2017-01 | 4% | sufficient |
| ophthalmology | 1 | 2017-05 | 2017-05 | 2% | single event |
| peripheral_vascular | 1 | 2018-02 | 2018-02 | 2% | single event |
| structural_heart | 1 | 2019-03 | 2019-03 | 2% | single event |
| imaging_us | 1 | 2019-04 | 2019-04 | 2% | single event |
| neurovascular | 1 | 2019-07 | 2019-07 | 2% | single event |
| ivd_immuno | 1 | 2019-09 | 2019-09 | 2% | single event |
| neurostimulation | 1 | 2020-01 | 2020-01 | 2% | single event |
| ivd_poct | 1 | 2020-04 | 2020-04 | 2% | single event |

## 3. Momentum

- no detectable change: 39 events in the last 24 months vs 36 before (ratio 1.08), p=0.818; minimum detectable ratio at 80% power is 1.91x
- Test: exact two-sided binomial p=0.818 (alpha=0.05), minimum detectable ratio at 80 % power 1.91x, detected=False

## 4. Concentration

- diversified: top track medical_ai holds 26% of 47 material events across 16 tracks (HHI 0.12)

## 5. Independent corroboration

- 1 of 16 technology tracks have independent device-trial support; 15 do not
- Tracks with **no** trial support: coronary, diabetes_cgm, ep_pfa, heart_failure, imaging_us, ivd_immuno, ivd_molecular, ivd_poct

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 8 track(s) rest on a single event: imaging_us, ivd_immuno, ivd_poct, neurostimulation, neurovascular — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: diabetes_cgm: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
- Hiring evidence: 566 archived postings across 34 months (posting-flow proxy, not headcount)
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
