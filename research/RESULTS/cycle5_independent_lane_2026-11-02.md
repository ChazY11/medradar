# Cycle 5 — an independent device-trial lane, and what it says about confirmation (2026-11-02)

**Status:** completed. Closes B-033 (independent source) and B-040 (device-trial collection).
Evidence: `experiments/b040/` (collector, log, manifest, analysis, generated report).
Decisions: D-022 (pre-registration), D-023 (outcome).

## 1. What was built

Cycle 4 showed the shipped spine could not answer "is the detected change real?": the only other
registry present (ClinicalTrials.gov) was mapped to **drug** tracks, disjoint from the **device**
tracks used by the detector — 0 of 104 cells matchable. B-040 closed that by **collection**, reusing
the repository's audited device-trial collector against a new, disposable database:

| quantity | value |
|---|---:|
| studies returned | 4,130 |
| interventional studies in window | 2,663 |
| trial events stored (2016-09 … 2026-10) | **2,663** |
| attributable to a curated device company | 1,472 (55 %) |
| mapped to a **device** track | 1,278 (48 %) |
| device-intervention studies with a device track | 1,181 |
| distinct companies / device tracks | 46 / 43 |
| requests used (bounded run) | 107 (0 errors) |

The frozen research lane was never touched; the collected rows are not committed (the registry is
live), but `collection_manifest.json` pins exactly what was collected, when, and with which caps.

## 2. The pre-registered test, and its answer

Analysis declared in D-022 before computing any association: (company, device track) cells carrying
both lanes, floors of ≥6 regulatory and ≥3 trial events, cross-correlation at lags −6 … +12 months,
pooled by Fisher z, null from circularly shifting each cell's trial series.

**Result: 26 cells in both lanes, 16 eligible, and no detectable association at any lag.** The
largest observed value is r = 0.036 at lag +7 months against a null band of [−0.046, +0.048]; the
whole profile sits inside the null.

## 3. What this licenses and what it does not

**Licensed:** at cell level, device-trial activity and regulatory clearance activity show no
detectable aligned time structure in this sample. The evidence-fusion premise — that one lane
confirms the other — is unsupported and must be argued from a different design, not assumed.

**Not licensed:** that the two signals are unrelated. The limits are decisive:
- **coverage** — 55 % sponsor attribution, 48 % track mapping; a bounded sample, not a census;
- **sparsity** — floors of 3 and 6 events over 119 months mean the series are mostly zero, so a
  per-cell correlation is a co-occurrence pattern of rare months, not a rate relationship;
- **granularity** — a trial attaches to a company, a clearance to a legal sub-entity; a
  multi-subsidiary firm is pooled while its clearances sit in separate cells.

## 4. Why this matters for the programme

Mission question 3 (time relations between public signals) now has one honest, re-runnable answer at
device-track granularity: **none detectable** between the two independent lanes. The honest route
forward is not more lag windows on 16 sparse cells but the two declared data gaps (hiring, patents)
or a different unit of analysis (company entry cohorts rather than cell-month counts).

This is the third consecutive cycle in which a tempting positive dissolved under a better design
(coverage artefact → resolution dependence → track-growth co-movement → no cross-lane association).
The programme's accumulating value is the set of narrow, budget-explicit claims that survive, plus a
documented map of what this data cannot support.
