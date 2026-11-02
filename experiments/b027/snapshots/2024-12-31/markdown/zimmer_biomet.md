# Zimmer Biomet — technology profile

*As of 2024-12-31. Evidence window 2016-11 to 2024-12 (98 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Zimmer Biomet: 20 resolved legal entities from 8 aliases, observed 2016-11 to 2024-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 129 material events across 10 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 71 | 2016-11 | 2024-12 | 55% | sufficient |
| trauma | 24 | 2016-11 | 2024-09 | 19% | sufficient |
| spine | 12 | 2017-02 | 2024-03 | 9% | sufficient |
| dental | 11 | 2017-05 | 2024-10 | 9% | sufficient |
| rehab_exo | 4 | 2019-06 | 2024-07 | 3% | sufficient |
| wound_care | 2 | 2016-12 | 2017-02 | 2% | sufficient |
| imaging_mr_ct | 2 | 2017-03 | 2023-07 | 2% | sufficient |
| endoscopy | 1 | 2019-06 | 2019-06 | 1% | single event |
| urology | 1 | 2023-10 | 2023-10 | 1% | single event |
| surgical_energy | 1 | 2024-05 | 2024-05 | 1% | single event |

## 3. Momentum

- no detectable change: 29 events in the last 24 months vs 36 before (ratio 0.81), p=0.457; minimum detectable ratio at 80% power is 2.01x
- Test: exact two-sided binomial p=0.457 (alpha=0.05), minimum detectable ratio at 80 % power 2.01x, detected=False

## 4. Concentration

- moderately concentrated: top track ortho_joint holds 55% of 129 material events across 10 tracks (HHI 0.36)

## 5. Independent corroboration

- 1 of 10 technology tracks have independent device-trial support; 9 do not
- Tracks with **no** trial support: dental, endoscopy, imaging_mr_ct, rehab_exo, spine, surgical_energy, trauma, urology

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: endoscopy, surgical_energy, urology — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: dental: 2 events in the last 24 months vs 4 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2024-12-31; window 2016-11 to 2024-12
- Hiring evidence: 4 archived postings across 4 months (posting-flow proxy, not headcount)
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
