# PHASE 1 PROTOCOL — frozen decision rules for the lead-time feasibility gate (G1)

**Status:** FROZEN before the pairing probe (`LEAD_LAG_PROBE.json`) was produced · **Study:**
`early_signal_5firms` · **Branch:** `research/early-signal-5firms`

> Written after the *source audit* (`EARLIER_SOURCE_AUDIT.json`: record counts, taxonomy, tiers) and **before** any
> trial→clearance pairing or lead-time number was computed. If any number here contradicts the later probe, the
> protocol wins and the discrepancy is reported.

---

## 1. What is being decided

Whether a **lead-time study** is scientifically possible on this corpus: can an earlier public source (clinical
trials, SEC 8-K) be paired to a later regulatory event (510(k)/PMA) on the study's tracks, with point-in-time
availability, in enough quantity to estimate how early a change is visible?

This is a **feasibility gate**, not a test of H1–H4. No detection model is involved.

## 2. Definitions, fixed now

- **Earlier evidence:** a `ctgov` trial record or an SEC `8-K` record, dated by its **posting/filing date**
  (`event_date`), which is the PIT-safe availability boundary (Tier B).
- **Later event:** a `510k` or `pma` event for the same firm and track.
- **Pair:** an earlier-evidence record and the **first** later event of the same firm in the defined scope, with the
  later event's date strictly after the earlier record's date.
- **Lead time:** `later_event_date − earlier_evidence_date`, reported in **quarters** and as a distribution
  (median, quartiles, min, max). Positive means the earlier source led.
- **Eligible lead:** an absolute lead of **≥ 2 quarters** (the directive's "3–6 months" band, rounded to the study's
  quarterly unit).
- **Independent confirmation:** for a pair to count as evidence of *early visibility*, the two records must come from
  **different source families** (trial vs regulatory; 8-K vs regulatory). A trial confirmed by another trial does not
  count.

## 3. Three scopes, in pre-declared priority order

| scope | definition | role |
|---|---|---|
| **S1 (primary)** | firm × **device track** (`imaging_us`, `respiratory`), pairing only within the same device track | the only scope that could answer RQ4 |
| **S2 (sensitivity)** | firm × **assumed crosswalk** `t_respiratory` → `respiratory` (id-identical after the `t_` prefix; a candidate mapping, not an established one) | declared in advance as an **assumption-labelled** analysis |
| **S3 (descriptive)** | firm level: any earlier record → next regulatory event for the same firm (any track) | describes ordering; cannot support RQ4, and cannot be pooled with S1/S2 |

S2 exists because the trial lane's therapy-area taxonomy has exactly four id-identical counterparts
(`t_respiratory`, `t_ophthalmology`, `t_urology`, `t_womens_health`); only `t_respiratory` touches a confirmatory
device track. Any S2 result must be reported with the words "assumed crosswalk".

## 4. Gate criteria (frozen)

**G1 = GO for a lead-time study** iff, in S1 or in S2 (either one suffices, reported separately):

- **≥ 10 independent eligible pairs** (lead ≥ 2 quarters), AND
- pairs span **≥ 2 firms**, AND
- the availability audit reports **0 violations** under the declared lag.

**G1 = NO-GO** for lead-time measurement otherwise. A NO-GO must be reported as a **negative finding about public
data**, not as a failure of the study: the coverage and audit documentation still stands, and the shrinkage report
(`PHASE1_SHRINKAGE.md`) must state which question public data cannot answer.

**G1 = NOT_EVALUABLE** (distinct from NO-GO) if the pairing cannot even be constructed — e.g. zero records in scope.
A zero count is NOT_EVALUABLE only when it is caused by a structural mapping gap rather than by the world.

## 5. Lag sensitivity (declared, not fitted)

Availability is reconstructed as `event_date`, with the trial/8-K date treated as the publication date. The probe is
re-run with **+30, +60, +90 days** added to the earlier record's availability, and the pair count and median lead
must be reported at each setting. If the GO decision flips across those settings, the result is **fragile** and G1
becomes NO-GO regardless of the base count.

## 6. What would invalidate the probe

- Any pair whose later event precedes or equals the earlier record's date (negative lead) is dropped from the lead
  distribution but **counted and reported** as a "late/coincident" record.
- A single trial paired to multiple clearances: only the first later event counts, and the multiplicity is reported.
- Records resolved only by alias matching keep their `resolved_by` field in the artifact; a pair built entirely on
  alias-resolved records is flagged.

## 7. What Phase 1 may do if G1 passes

Only then: baselines M0–M5, rolling-origin evaluation, leave-one-company-out on the ≥2 firms present, false-alarm
budget of 2 per company-year, and the metric set frozen in `PROTOCOL.md` §8. Nothing in Phase 1 may be reported
before its leak audit passes.

## 8. Human sign-off

| item | status |
|---|---|
| G1 criteria, scopes S1/S2/S3, lag sensitivity | **PENDING_HUMAN_REVIEW** |
| Use of the `t_respiratory → respiratory` crosswalk as an assumption-labelled sensitivity | **PENDING_HUMAN_REVIEW** |
| Any eventual `Confirmed Shift` label | **PENDING_HUMAN_REVIEW** (human only) |
