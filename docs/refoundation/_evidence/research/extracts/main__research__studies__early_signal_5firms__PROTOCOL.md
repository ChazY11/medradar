# PROTOCOL — Early detection of corporate technology shifts in medical devices

**Study:** `early_signal_5firms` · **Directive:** RESEARCH DIRECTIVE 001, Phase 0 · **Status:** DRAFT, frozen on
human sign-off · **Branch:** `research/early-signal-5firms`

> **PENDING_HUMAN_REVIEW.** The scientific target definition (§4), the candidate case list (§7) and the Phase 0
> feasibility verdict (§9) require a named human scientist's adjudication. This document records what the machine
> can fix in advance; it does not sign for a person.

---

## 1. Research questions (fixed before any modelling)

- **RQ1** Which public sources carry a reliable early-warning signal for changes in a firm's technology positioning?
- **RQ2** At an equal false-alarm budget, does cross-source fusion detect more real changes than the best single
  source?
- **RQ3** Is there a stable ordering in time across sources (which signal tends to appear first)?
- **RQ4** Do any measured lead times replicate across firms and across technology domains?
- **RQ5** How do sparsity, classification error and timestamp uncertainty bound the conclusions?

## 2. Hypotheses (all *pending tests*, none treated as fact)

| id | hypothesis | direction of a working result |
|---|---|---|
| **H1** | Cross-source fusion improves early detection at a fixed false-alarm budget | fusion recall − best single-source recall > 0, interval excluding 0 |
| **H2** | Some non-regulatory signals precede verifiable regulatory/commercial milestones | median lead time > 0 for at least one source, with ≥2 firms |
| **H3** | Signal usefulness differs by firm and by domain | per-cell effects differ beyond sampling noise |
| **H4** | Sparse cells bound early detection and lead-time estimation | recall/lead time degrade as observation density falls |

**Not claimed before Phase 1:** that any signal precedes anything; that fusion helps; that a firm's filings proxy its
R&D. The programme has already retracted five findings in this area and will not re-package them.

## 3. Study unit and window

- **Unit:** `company × technology domain × quarter`.
- **Historical window:** 2018-01-01 … 2025-12-31, to be confirmed by the coverage audit; 2026+ is reserved for genuinely
  prospective registration only.
- **Domains (candidate, coverage-checked):** patient monitoring, ultrasound imaging, advanced imaging, respiratory &
  critical care, medical AI / SaMD. Domains may be dropped or split only with a recorded reason; sample size may not
  be inflated by inventing firm-domain activity.

## 4. Scientific target

**Target A — Observable technology milestone (primary).** A pre-specified, independently checkable event: a cleared
510(k) or PMA in a domain the firm had not been active in for a declared period, or a documented product
commercialisation with a public date. Recorded fields: definition, company, domain, event date, **first public
confirmation date**, evidence source, confidence, ambiguity, exclusion criteria.

**Target B — Expert-adjudicated technology shift (secondary, human only).** Labels: `Confirmed Shift`,
`Routine Iteration`, `False Signal / No Confirmed Shift`, `Uncertain`, `Insufficient Observation`. **The agent may
prepare candidate packets and the review form; it may not produce the labels.**

**Explicitly forbidden as a target:** a rise in filing counts treated as a strategic shift.

## 5. Point-in-time rules (binding)

1. A feature at decision time *t* may use only evidence whose `available_at` (or reconstructed availability) is
   ≤ *t*.
2. Event dates are **not** publication dates. Availability is reconstructed with a declared lag per source and must
   be shown to survive a lag sensitivity analysis (`EVIDENCE_TIME_AUDIT.json` fixes the assumed lags).
3. `first_seen_at` in these stores is the **collection** date, not a publication date, and may never be used as one.
4. Current entity mappings and taxonomies may not be applied to history without an audited check.
5. Samples may not be selected on knowledge of their outcome.
6. A backfilled prediction may never be described as prospective.
7. Date-only values may not be described as having hour precision.

## 6. Baselines (fixed now; `NOT_EVALUABLE` where data do not permit)

| id | model | data requirement |
|---|---|---|
| **M0** | historical persistence (activity intensity only) | always evaluable |
| **M1** | regulatory signal (510(k)/PMA) | present |
| **M2** | scientific signal (patents, publications) | **patents absent; publications annual only → likely NOT_EVALUABLE** |
| **M3** | clinical signal (trials) | present (55,592 ctgov events) |
| **M4** | corporate/market signal (SEC filings, hiring, procurement) | SEC 8-K sparse; procurement Tier C; hiring partial → **partial** |
| **M5** | cross-source fusion | only sources that survived audit |

Simple, interpretable methods only until a simple baseline demonstrably fails.

## 7. Candidate cases

Target: **60 candidate cases across the five firms**, stratified by the pre-declared rules (confirmation status,
domain, era), **not** selected by fame. Each case carries an *Evidence Packet* with the fields in
`CASE_CANDIDATES.json`. Every case starts as `PENDING_HUMAN_REVIEW`; no LLM judgement may be recorded as a human label.

## 8. Metrics (primary, fixed now)

- Event recall at a fixed false-alarm budget; **primary budget: 2 false alerts per company-year** (sensitivity at
  stricter and looser budgets reported alongside).
- Precision at a fixed alert budget; false alerts per company-year.
- Lead time = confirmation time − first valid alert time, reported as a **distribution** (median, quartiles, censoring),
  never as a mean of successes only.
- Recall at 3, 6 and 12 months before confirmation.
- Missed events, unresolved alerts, and censored cases reported explicitly.
- Confirmation must rest on evidence **independent of** the source that produced the alert.

## 9. Phase 0 completion and feasibility verdict

Phase 0 is complete when the coverage matrix, evidence-time audit, this protocol, the labelling protocol, the
evaluability decisions and at least one real historical replay exist as committed artifacts. The verdict is
**GO / CONDITIONAL-GO / NO-GO**, and must be supported by the numbers in `COVERAGE_MATRIX.json`, not by ambition.

## 10. What would make this study stop

- Fewer than six firm-domain cells reach the pre-declared floors → cross-company validation impossible (RQ4).
- No source reaches Tier A or B for availability time → lead time cannot be measured, only described.
- Confirmation evidence exists only in the same source as the alert → recall would be circular.
