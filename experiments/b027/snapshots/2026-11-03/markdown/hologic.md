# Hologic — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Hologic: 1 resolved legal entities from 3 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 39 material events across 6 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ivd_molecular | 26 | 2017-02 | 2025-09 | 67% | sufficient |
| imaging_mr_ct | 5 | 2017-10 | 2026-09 | 13% | sufficient |
| medical_ai | 5 | 2020-11 | 2025-07 | 13% | sufficient |
| womens_health | 1 | 2018-04 | 2018-04 | 3% | single event |
| general_surgery | 1 | 2024-07 | 2024-07 | 3% | single event |
| surgical_energy | 1 | 2026-06 | 2026-06 | 3% | single event |

## 3. Momentum

- no detectable change: 10 events in the last 24 months vs 11 before (ratio 0.91), p=1.000; minimum detectable ratio at 80% power is 3.40x
- Test: exact two-sided binomial p=1.000 (alpha=0.05), minimum detectable ratio at 80 % power 3.40x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (25 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track ivd_molecular holds 67% of 39 material events across 6 tracks (HHI 0.48)

## 5. Independent corroboration

- 2 of 6 technology tracks have independent device-trial support; 4 do not
- Tracks with **no** trial support: general_surgery, ivd_molecular, medical_ai, surgical_energy

## 6. Contradictory evidence

- 3 contradictory observation(s) out of 4 checks
- `sparse_months`: the company has material events in 36 of 119 months (70% silent) — monthly series are mostly zeros; rate estimates are unstable
- `single_event_tracks`: 3 track(s) rest on a single event: general_surgery, surgical_energy, womens_health — a single filing is an anecdote; treat these tracks as unconfirmed
- `activity_decline_by_track`: medical_ai: 1 events in the last 24 months vs 3 before — this track is retreating, which cuts against a growth reading

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
- Hiring evidence: 87 archived postings across 22 months (posting-flow proxy, not headcount)
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
