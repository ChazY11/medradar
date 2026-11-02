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

---

## S-007 — G1 = NO-GO for lead-time measurement (pre-registered gate, run as specified)

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `EARLIER_SOURCE_AUDIT.json`, `LEAD_LAG_PROBE.json`,
`PHASE1_SHRINKAGE.md`

The frozen G1 criteria (≥10 eligible pairs with lead ≥2 quarters across ≥2 firms) were applied to three scopes:
S1 primary (trials on the device tracks) produced **0** pairs; S2 (assumed crosswalk `t_respiratory → respiratory`)
produced **3** pairs across 2 firms; S3 firm-level produced 0 eligible pairs because every trial is followed by a
clearance within the 2-quarter floor. The best scope reaches 3 pairs, below the floor of 10, so **G1 = NO-GO**.

Cause is structural, not statistical: the trial lane assigns therapy-area tracks (`t_*`), only four of which have an
id-identical device counterpart, and only one of those touches a confirmatory track. A crosswalk would have to be
built and reviewed, and building it after seeing outcomes would violate pre-registration. SEC 8-K is unusable at cell
level: 1,360 of 20,976 records carry a company_key (~5 per firm in the window) and none carries a track.

## S-008 — Firm-level pairing is recorded as invalid for inference, with the number that shows why

**Date:** 2026-11-03 · **Status:** accepted

At firm level, Medtronic's 113 in-window trials pair to the next clearance with **303,942** skipped follow-on events,
and **112 of 113** pairs fall below the 2-quarter floor. With thousands of clearances any trial will be followed by
one almost immediately, so the pairing carries almost no information about whether a technology change exists. This
is recorded so that no later analysis revives firm-level lead times as if they were evidence.

## S-009 — Next question is concurrent detection (O1), not lead time

**Date:** 2026-11-03 · **Status:** open, awaiting human decision

The corpus can support a question about *as-it-happens* multi-source detection (H1) but not about lead time (H2). The
recommendation in `PHASE1_SHRINKAGE.md` §6 is to run O1 next, after the positive definition is changed to a sustained
change, and to state the lead-time question as unanswerable on this corpus rather than replace it with a proxy.
O2 (a reviewed trial crosswalk) would need a human-adjudicated mapping before it can be used; O3 (patents/procurement)
remains blocked by access and by Tier C timestamps.

---

## S-010 — O1 is underpowered: the confirmatory cells contain almost no sustained changes

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `CONCURRENT_DETECTION.{json,md}`, `PHASE1B_PROTOCOL.md`

The amended positive definition (≥2 regulatory events within 4 quarters after ≥12 months of silence) yields
**1 onset** across the six confirmatory firm-track cells in the evaluation window 2022-Q1…2025-Q4 (24 company-years).
Under the frozen underpowered clause (<10 onsets), no comparison between M0, M1, M2 and M5 may be reported as support
or refutation of H1. The descriptive numbers are: M0 recall 1.0 (3 alerts), M1 1.0 (5 alerts), M2 0.0 (10 alerts),
M5 1.0 (10 alerts) — all with intervals spanning nearly the whole unit range ([0.207, 1.0] or wider), which is what a
single positive case produces.

The binding constraint is now clear and is **not** observation count: the cells carry enough quarter-observations
(164 events, 6 cells) but almost no *sustained changes*. A change-detection study cannot be powered on two tracks.

## S-011 — Second defect in my own leak audit, recorded rather than hidden

**Date:** 2026-11-03 · **Status:** accepted

The O1 leak audit initially aborted with 7 violations. Cause: the quarterly cutoff was computed as the 28th of the
quarter's final month instead of the real last day, so events published in the final days of a quarter were flagged.
Fixed with `calendar.monthrange`; the audit then reports **0 violations**. This is the second time an availability
audit of mine tested a slightly wrong property (the first is in `PILOT_RESULTS.md` §2), and the pattern is now
explicit in the study log: **audit cutoffs are code and must carry the same test discipline as models.**

## S-012 — The honest state of the study, and the decision that is not mine

**Date:** 2026-11-03 · **Status:** open, awaiting human decision

Three findings now bound this study:
1. lead time is unmeasurable here (G1 NO-GO, S-007): the trial lane cannot be joined to the device tracks;
2. the confirmatory cell set is too thin for change detection (S-010): 1 sustained onset in 4 years;
3. the only defensible multi-source pairing available is partial independence (recalls share the regulator).

Therefore the choice is between (a) **expanding** the cell set to the exploratory tracks (pre-registering a
multiplicity control, since per-firm exploratory cells invite cherry-picking), (b) **changing the unit** from
quarter-counts to event-level sequences, or (c) **closing** the programme at this scope and publishing the negative
result. Each is a scientific judgement about what the question is worth, and none is the agent's to make silently.
