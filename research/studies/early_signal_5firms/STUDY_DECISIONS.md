# Study decision log — early_signal_5firms

Append-only. Entries are numbered `S-nnn` and record decisions made inside this study; the programme's main
`research/DECISIONS.md` is left untouched (it is prior record, not this study's scratchpad).

---

## S-001 — Study store is the main-clone store, not the curated research lane

**Date:** 2026-11-03 (system clock) · **Status:** accepted

The curated research lane holds 55,090 events (510(k)+PMA only, 51-firm roster). The main-clone store holds 375,378
events across 510(k) (176,466), **device recalls (59,646)**, PMA (57,372), **clinical trials (55,592)**, SEC 8-K
(20,976) and drug approvals (5,326), with event dates from 1966. Only the latter can speak to the directive's
cross-source questions. Both stores remain read-only for this study; no file under `data/` is committed.

## S-002 — No source reaches Tier A for historical availability

**Date:** 2026-11-03 · **Status:** accepted

`first_seen_at` in both stores is the collection date (2026-10-30/31), not the source's publication time. openFDA
bulk extracts and ctgov therefore reach **Tier B** at best: availability must be reconstructed as `event_date + lag`
with a declared assumption (30 days) and tested by sensitivity analysis. `procurement_awards` is Tier C
(`announcement_date`/`award_date` NULL, `data_quality = first_publication_unknown`) and may not enter lead-time
conclusions. `publication_counts` is annual and company-level only. **Patents are absent from every frozen store.**

## S-003 — Domain amendment is pre-registered, not smuggled

**Date:** 2026-11-03 · **Status:** accepted (human sign-off pending)

Coverage evidence supports cross-company validation on **two** tracks only (`imaging_us`, `respiratory`, three firms
each), not the directive's 12–18 combinations. `DOMAIN_AMENDMENT_001.md` fixes the confirmatory/secondary/exploratory
split **before** any outcome was examined, and does not touch the pre-declared floors or the window.

## S-004 — Dräger is descriptive only; Mindray's roster gap is a bookkeeping defect

**Date:** 2026-11-03 · **Status:** accepted

Dräger has 6 in-window observations in 4 quarters in respiratory and none elsewhere: it cannot enter any evaluation.
Dräger and Mindray have **no `company_key`** in the store's roster, so key-based counting reports zero events for both;
probing `applicant_raw` finds 48 and 244 events respectively. This is resolved by alias matching, which carries a
measured false-positive mode (`Surge Medical Sales` matching `GE MEDICAL`), now excluded.

## S-005 — The pilot's outcome is a declared non-result, and the pilot's own leak audit was defective

**Date:** 2026-11-03 · **Status:** accepted, recorded rather than hidden

The minimal replay produced **0 hits for both M0 and M1** over 9 rule-based positives in 164 events. The likely cause
is a specification mismatch (single-event entries versus a rate-anomaly detector) plus 0.85 events per cell-quarter.
Separately, the first leak audit asserted the wrong property and emitted 118 spurious violations; it was corrected to
test visibility-before-decision-cutoff, which passes with 0 violations. The defect is documented in
`PILOT_RESULTS.md` §2 rather than quietly fixed.

## S-006 — Phase 1 conditions (pre-committed)

**Date:** 2026-11-03 · **Status:** open

Phase 1 may only begin if: (a) the positive definition becomes a *sustained* change; (b) an earlier source survives
the tier audit so lead time is measurable at all; (c) per-cell results are reported separately and cross-firm pooling
is limited to the two confirmatory tracks; (d) 60 candidate cases are adjudicated by a named human reviewer with the
independence rule enforced. Until then Phase 1 is **CONDITIONAL-GO at best**.
