# Cycle 2 design — Coverage, power, and the reality of the entry signal

Written **before** running the cycle-2 experiment. Frozen at commit time. Any change
must be recorded in `DECISIONS.md` and invalidates prior cycle-2 numbers.

## Observe — what we actually know after cycle 1

1. The entry target (dormant ≥36 months → active within 12 months) has a 1.23% base
   rate: 503 positives out of 41,003 rows across 24 quarterly origins.
2. Its AP is 0.107 (R&D-only) / 0.115 (+financial), against 0.0515 for the per-pair
   persistence baseline and 0.0151 for constant prevalence.
3. Only **one of three** holdout windows excludes zero for ΔAP; per-window positives
   are 25–27. Per-origin AP ranges 0.018 to 0.237.
4. 51 curated companies; **322 observed company-track pairs** out of a 51×38 = 1,938
   cross product. So 84% of the candidate universe has never been observed in a
   decade — a left-censoring artefact, not necessarily a fact about technology entry.
5. 510(k) links to a curated company only 16.9% of the time; 284 unlinked rows do name
   a curated company; **Mindray and Dräger (two of five mandated focus companies) are
   not in the roster at all**.
6. No added data source produced a detectable ranking gain; the two candidate
   explanations are "the sources are uninformative" and "the test is underpowered".

## Question

> Is the entry-signal estimate limited by *measurement coverage* (too few firms, too
> few positives) or by *the world* (technology entry genuinely hard to predict from
> public pre-cutoff evidence)?

These imply opposite next moves: fix the panel vs accept the null. Answering it is
therefore worth a cycle.

## Hypotheses (details in `HYPOTHESES.md`)

- **H2.1 (coverage → power).** Rebuilding the panel on a deterministic applicant
  universe (instead of 51 curated parents) materially increases positives per origin.
  *Prediction:* positives per origin rise from ~25 to ≥60 while base rate stays
  within roughly 0.5–3%.
- **H2.2 (signal resolution).** With the larger positive count, the entry model's
  ΔAP versus per-pair persistence either becomes resolvable (cluster CI excludes zero
  in a majority of pre-declared windows) or stays null with a now-small MDE. *Both
  outcomes are decisive* — the first establishes skill, the second converts "not yet
  validated" into a well-powered negative.
- **H2.3 (entity granularity).** The estimate is sensitive to entity definition
  (legal applicant entity vs corporate parent). *Prediction:* the legal-entity panel
  yields more positives but a lower per-entity event density; AP changes by more than
  its window dispersion, which would mean prior numbers were an artefact of the
  hand-curated roster.
- **H2.4 (heterogeneity).** Predictability concentrates in identifiable strata
  (large firms, data-mature origins, high-activity tracks) rather than being uniform.
- **H2.5 (lead time).** At an identical false-alarm rate, the learned model precedes
  the persistence baseline on the events it does detect. If the two have
  indistinguishable detection curves, the model adds nothing operationally no matter
  its AP.
- **H2.6 (null is underpowered).** The cycle-1 source nulls are consistent with a true
  effect smaller than the minimum detectable effect at n≈500 positives.

## Protocol (frozen; identical to cycle 1 except the entity universe)

- Material-event rule, dormancy rule, 36-month window, 12-month label, quarterly
  origins, purge rule `cutoff + 12m <= origin`: **unchanged** from E2, to keep the
  original-vs-expanded comparison attributable to one variable.
- Primary metric: average precision. Secondary: Precision@10%, Brier, ECE-10,
  matched-FAR lead time, per-origin stability.
- Inference: cluster-aware bootstrap (company and pair clusters) and MDE at 80% power.
- Holdout windows: pre-declared, the last three evaluable origins. All are reported;
  no window is selected after the fact.
- Two panels compared on identical protocol: **P1 curated-parent panel** (reproduces
  cycle 1) and **P2 deterministic legal-entity panel** (new). The delta between them
  is the result.

## Analysis plan (pre-declared)

1. Descriptive: entities, events, positives, candidates per origin under P1 vs P2;
   focus-company coverage; explicit remainder bucket.
2. Re-run T-cont and T-entry under P1 to confirm reproduction of the frozen numbers
   (a mismatch is a defect and must be reported before anything else).
3. Re-run both targets under P2. Report per-window and window-mean metrics for model
   and all persistence baselines.
4. ΔAP(model − persistence) with cluster-aware CIs, per window and pooled; MDE at the
   observed positive count.
5. Matched-FAR lead time with censored units counted.
6. Heterogeneity by pre-declared strata with multiplicity noted.
7. Decision rule (pre-registered): if the CI on ΔAP excludes zero in the majority of
   pre-declared windows under P2, record a supported signal; if it does not but the
   MDE is smaller than the cycle-1 point estimate, record a well-powered negative; if
   neither, record "still underpowered" and specify the positive count needed next.

## What would falsify our own design

- If P2's base rate collapses (e.g. <0.1%) the panel is dominated by never-active
  micro-entities and the comparison is invalid — then re-scope the cohort by minimum
  history rather than widening blindly.
- If P1 fails to reproduce cycle 1's frozen numbers, the harness is wrong and no P2
  result may be reported.
- If the deterministic universe's "entities" are mostly formatting variants of the
  same firm, the panel is inflated and H2.1 is rejected.

## Cost and stopping rule

Single workstation, deterministic CPU pipelines, no sweeps. The driver must complete
within one overnight-scale run; if it cannot, reduce origins (reported) rather than
silently sampling. Stop the cycle when the decision rule fires, and record the
outcome — including a negative one — regardless of direction.
