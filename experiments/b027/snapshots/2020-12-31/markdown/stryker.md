# Stryker — technology profile

*As of 2020-12-31. Evidence window 2016-11 to 2020-12 (50 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Stryker: 26 resolved legal entities from 11 aliases, observed 2016-11 to 2020-12
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 122 material events across 15 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 32 | 2017-02 | 2020-12 | 26% | sufficient |
| trauma | 29 | 2017-02 | 2020-07 | 24% | sufficient |
| endoscopy | 14 | 2016-11 | 2020-12 | 11% | sufficient |
| spine | 11 | 2016-11 | 2020-10 | 9% | sufficient |
| neurovascular | 11 | 2018-03 | 2020-12 | 9% | sufficient |
| surgical_energy | 7 | 2017-02 | 2018-04 | 6% | sufficient |
| general_surgery | 5 | 2019-04 | 2020-10 | 4% | sufficient |
| medical_ai | 2 | 2017-02 | 2020-11 | 2% | sufficient |
| imaging_mr_ct | 2 | 2018-12 | 2019-01 | 2% | sufficient |
| ep_pfa | 2 | 2019-01 | 2020-05 | 2% | sufficient |
| coronary | 2 | 2019-05 | 2020-09 | 2% | sufficient |
| vascular_access | 2 | 2019-11 | 2020-02 | 2% | sufficient |
| wound_care | 1 | 2016-11 | 2016-11 | 1% | single event |
| cmf | 1 | 2018-09 | 2018-09 | 1% | single event |
| imaging_us | 1 | 2019-05 | 2019-05 | 1% | single event |

## 3. Momentum

- no detectable change: 89 events in the last 24 months vs 75 before (ratio 1.19), p=0.310; minimum detectable ratio at 80% power is 1.55x
- Test: exact two-sided binomial p=0.310 (alpha=0.05), minimum detectable ratio at 80 % power 1.55x, detected=False

## 4. Concentration

- diversified: top track ortho_joint holds 26% of 122 material events across 15 tracks (HHI 0.16)

## 5. Independent corroboration

- 4 of 15 technology tracks have independent device-trial support; 11 do not
- Tracks with **no** trial support: cmf, coronary, ep_pfa, imaging_mr_ct, imaging_us, medical_ai, spine, surgical_energy

## 6. Contradictory evidence

- 2 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: cmf, imaging_us, wound_care — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: surgical_energy: 0 events in the last 24 months vs 7 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2020-12-31; window 2016-11 to 2020-12
- Hiring evidence: 8839 archived postings across 90 months (posting-flow proxy, not headcount)
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
