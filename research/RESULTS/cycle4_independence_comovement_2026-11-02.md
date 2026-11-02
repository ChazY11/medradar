# Cycle 4 — independent-source audit and cross-company co-movement (2026-11-02)

**Status:** completed. Two negative results, both load-bearing. Evidence:
`experiments/detect_v1/probe_trials_source.py`, `comovement.json`, `COMOVEMENT.md`. Decisions: D-021.

## 1. Is there a genuinely independent confirmation source? (B-033)

The Observe layer detects a change in a firm's public regulatory activity rate. The obvious next
question — *is the change real?* — needs a signal from a different publication system. The backlog
had this as "blocked, assumed". It is now **measured**:

| candidate source | what exists | why it cannot confirm |
|---|---|---|
| ClinicalTrials.gov (legacy DB) | 55,592 trial events, 1999-2026 | its tracks are **drug** tracks (22 × `t_*`); the detection panel is device tracks. **0 of 104 detection cells** contain a single trial event; 12 of 94 entities appear only as pharma sponsors |
| OpenAlex publications | 616 company-year rows, 51 curated companies | annual granularity, curated-company coverage only, not the entity cohort |
| USAspending procurement | 3,453 awards | `award_date` NULL in all rows, `pit_usable=0` in all rows |
| PMA vs 510(k) split | same lane | same filing system — not independent |

So the confirmation question **cannot be answered with the current spine**, and the obstacle is
track-taxonomy disjointness rather than a missing file. The concrete fix is B-040: collect
ClinicalTrials.gov **device** trials with device-track mapping (the device-intervention filter
already exists in `medradar/clinical.py`).

## 2. Do competitors enter a technology together? (B-025)

Presence panel (entity × track × month), statistic `sum_m C(active firms, 2)`, permutation null
preserving each firm's activity level and a monthly volume profile.

**The choice of volume profile decides the answer, and the intuitive choice is wrong:**

| null conditions on | tracks with excess co-movement (BH q = 0.10) |
|---|---|
| lane-wide monthly volume | 3 of 32 — `medical_ai` (z = +5.47), `spine` (+3.50), `ivd_molecular` (+3.27) |
| **the track's own monthly volume** | **0 of 32** (strongest positive z = +1.21) |

The three tracks that looked synchronised are the tracks that grew most over the decade: a growing
track admits firms over time, which manufactures co-occurrence. Once the track's own growth and
seasonality are conditioned out, **month-level cross-firm synchronisation is not detectable** in
this lane.

**What the data do contain:** firm-level activity changes, and track-level growth. **What they do
not contain (at this granularity):** firms visibly moving together.

### Limitations that must travel with this

- Most tracks sit *below* the track-volume null (down to z ≈ −3.9) because the null draws firm-months
  independently while real firms file in contiguous bursts. The test is conservative in the positive
  direction — this strengthens the null finding — but the **negative direction is an artefact and
  must not be read as anti-synchronisation**.
- Presence ignores magnitude; month is coarse; a cell's membership can change through product-code
  reassignment (documented in `track_assignment_audit.json`).
- No causal claim: this is the timing of public regulatory activity, not internal R&D portfolios.

## 3. Why these two results matter for the programme

Both close off tempting claims that the data cannot support:

- "We can confirm our detected changes against an independent source" — **not with this data**;
  device-trial collection (B-040) is the prerequisite.
- "The industry is moving into medical AI / molecular diagnostics / spine" — the co-movement is
  track growth, not competitors synchronising, and the naive statistic that produced it would have
  been published as a finding if the null had not been re-specified.

The pattern across cycles 1–4 is consistent: each tempting positive dissolves under a better null or
a corrected measurement, and what survives is a small set of narrow, budget-explicit claims. That is
the programme working as designed.
