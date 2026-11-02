# Zimmer Biomet — technology profile

*As of 2026-11-03. Evidence window 2016-11 to 2026-09 (119 months). Schema profile_v1.*

> A profile states what public evidence supports and what would change the answer. It is not a score, and it is only as good as the coverage below.

## 1. Identity

- Zimmer Biomet: 20 resolved legal entities from 8 aliases, observed 2016-11 to 2026-09
- Sources: data/research.sqlite (510(k)+PMA lane), data/b040_device_trials.sqlite, config/companies_device.json, config/universe_v1.json

## 2. Technology footprint

- 154 material events across 10 technology tracks (3 tracks rest on a single event)

| track | events | first | last | share | evidence |
|---|---:|---|---|---:|---|
| ortho_joint | 87 | 2016-11 | 2026-09 | 56% | sufficient |
| trauma | 30 | 2016-11 | 2026-06 | 19% | sufficient |
| spine | 12 | 2017-02 | 2024-03 | 8% | sufficient |
| dental | 12 | 2017-05 | 2025-06 | 8% | sufficient |
| rehab_exo | 6 | 2019-06 | 2026-01 | 4% | sufficient |
| wound_care | 2 | 2016-12 | 2017-02 | 1% | sufficient |
| imaging_mr_ct | 2 | 2017-03 | 2023-07 | 1% | sufficient |
| endoscopy | 1 | 2019-06 | 2019-06 | 1% | single event |
| urology | 1 | 2023-10 | 2023-10 | 1% | single event |
| surgical_energy | 1 | 2024-05 | 2024-05 | 1% | single event |

## 3. Momentum

- no detectable change: 36 events in the last 24 months vs 27 before (ratio 1.33), p=0.314; minimum detectable ratio at 80% power is 2.04x
- Test: exact two-sided binomial p=0.314 (alpha=0.05), minimum detectable ratio at 80 % power 2.04x, detected=False
- Deployment detector: rolling_zscore at 3-month resolution, threshold z>=3.5, no calibrated alert in the last 8 quarters (54 track-quarters examined at 3-month resolution, threshold z>=3.5, measured FAR 0.018)
  - these alerts are calibrated at the measured false-alarm rate 0.018 and sensitivity 0.147; they are statements about filing rate, not about technology

## 4. Concentration

- moderately concentrated: top track ortho_joint holds 56% of 154 material events across 10 tracks (HHI 0.37)

## 5. Independent corroboration

- 1 of 10 technology tracks have independent device-trial support; 9 do not
- Tracks with **no** trial support: dental, endoscopy, imaging_mr_ct, rehab_exo, spine, surgical_energy, trauma, urology

## 6. Contradictory evidence

- 1 contradictory observation(s) out of 4 checks
- `single_event_tracks`: 3 track(s) rest on a single event: endoscopy, surgical_energy, urology — a single filing is an anecdote; treat these tracks as unconfirmed

## 7. Limits and provenance

- As of 2026-11-03; window 2016-11 to 2026-09
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
