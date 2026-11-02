# Canon Medical Systems — technology profile

*As of 2026-11-02. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Canon Medical Systems: 6 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 107 material events across 4 technology tracks (1 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| imaging_mr_ct | 87 | 2017-06 | 2026-05 | 81% | sufficient |
| imaging_us | 17 | 2018-10 | 2026-01 | 16% | sufficient |
| medical_ai | 2 | 2025-04 | 2026-05 | 2% | sufficient |
| ophthalmology | 1 | 2018-02 | 2018-02 | 1% | single event |

## 3. Momentum

- no detectable change: 18 events in the last 24 months vs 20 before (ratio 0.90), p=0.871; minimum detectable ratio at 80% power is 2.48x
- Test: exact two-sided binomial p=0.871 (alpha=0.05), minimum detectable ratio at 80 % power 2.48x, detected=False

## 4. Concentration

- highly concentrated: top track imaging_mr_ct holds 81% of 107 material events across 4 tracks (HHI 0.69)

## 5. Independent corroboration

- 0 of 4 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: imaging_mr_ct, imaging_us, medical_ai, ophthalmology

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 1 track(s) rest on a single event: ophthalmology — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-02; window 2016-11 to 2026-09
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
