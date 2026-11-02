# Zimmer Biomet — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Zimmer Biomet: 20 resolved legal entities from 8 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 81 material events across 8 technology tracks (2 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 49 | 2016-11 | 2020-12 | 60% | sufficient |
| trauma | 13 | 2016-11 | 2020-04 | 16% | sufficient |
| spine | 8 | 2017-02 | 2020-10 | 10% | sufficient |
| dental | 5 | 2017-05 | 2019-12 | 6% | sufficient |
| wound_care | 2 | 2016-12 | 2017-02 | 2% | sufficient |
| rehab_exo | 2 | 2019-06 | 2019-11 | 2% | sufficient |
| imaging_mr_ct | 1 | 2017-03 | 2017-03 | 1% | single event |
| endoscopy | 1 | 2019-06 | 2019-06 | 1% | single event |

## 3. Momentum

- activity increasing: 62 events in the last 24 months vs 33 before (ratio 1.88), exact two-sided p=0.004
- Test: exact two-sided binomial p=0.004 (alpha=0.05), minimum detectable ratio at 80 % power 1.83x, detected=True

## 4. Concentration

- moderately concentrated: top track ortho_joint holds 60% of 81 material events across 8 tracks (HHI 0.41)

## 5. Independent corroboration

- 1 of 8 technology tracks have independent device-trial support; 7 do not
- Tracks with **no** trial support: dental, endoscopy, imaging_mr_ct, rehab_exo, spine, trauma, wound_care

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 2 track(s) rest on a single event: endoscopy, imaging_mr_ct — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
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
