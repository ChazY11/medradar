# Abbott — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Abbott: 26 resolved legal entities from 10 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 145 material events across 17 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| medical_ai | 26 | 2016-12 | 2026-09 | 18% | sufficient |
| ivd_molecular | 20 | 2017-05 | 2026-08 | 14% | sufficient |
| diabetes_cgm | 16 | 2017-09 | 2026-08 | 11% | sufficient |
| coronary | 11 | 2017-08 | 2025-10 | 8% | sufficient |
| imaging_us | 10 | 2019-04 | 2026-04 | 7% | sufficient |
| ivd_immuno | 10 | 2019-09 | 2026-09 | 7% | sufficient |
| ep_pfa | 9 | 2017-02 | 2026-09 | 6% | sufficient |
| vascular_access | 9 | 2019-04 | 2026-03 | 6% | sufficient |
| peripheral_vascular | 6 | 2018-02 | 2026-02 | 4% | sufficient |
| structural_heart | 6 | 2019-03 | 2025-10 | 4% | sufficient |
| ivd_poct | 6 | 2020-04 | 2025-06 | 4% | sufficient |
| cardiac_rhythm | 4 | 2016-11 | 2023-06 | 3% | sufficient |
| heart_failure | 4 | 2017-08 | 2022-02 | 3% | sufficient |
| neurostimulation | 3 | 2020-01 | 2023-05 | 2% | sufficient |
| neurovascular | 2 | 2019-07 | 2024-02 | 1% | sufficient |
| respiratory | 2 | 2022-12 | 2024-01 | 1% | sufficient |
| ophthalmology | 1 | 2017-05 | 2017-05 | 1% | single event |

## 3. Momentum

- no detectable change: 54 events in the last 24 months vs 60 before (ratio 0.90), p=0.640; minimum detectable ratio at 80% power is 1.69x
- Test: exact two-sided binomial p=0.640 (alpha=0.05), minimum detectable ratio at 80 % power 1.69x, detected=False

## 4. Concentration

- diversified: top track medical_ai holds 18% of 145 material events across 17 tracks (HHI 0.09)

## 5. Independent corroboration

- 11 of 17 technology tracks have independent device-trial support; 6 do not
- Tracks with **no** trial support: ivd_molecular, ivd_poct, medical_ai, neurovascular, ophthalmology, vascular_access

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: ophthalmology — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: diabetes_cgm: 1 events in the last 24 months vs 6 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
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
