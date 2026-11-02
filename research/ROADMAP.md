# Roadmap

Living plan. Phase gates are evidence-based: a phase is "done" only when its
acceptance criterion is met by a committed artifact.

## Phase 0 — Audit and foundation (DONE, 2026-11-01/02)

Independently audited the existing repo, then built the temporal/causal foundation
that every later claim depends on.

- Forensic audit of three divergent branches; defects fixed (AdCom empty-feed silent
  `ok`, 8-K pre-submission mislabel, raw-open/adjusted-close price basis, purge in
  rolling validation, verifier-by-grep).
- Bitemporal knowledge store (`medradar/tkg`): append-only assertions, separate
  valid time and knowledge time, as-of snapshot queries, deterministic PIT export.
- Immutable forecast registry (`medradar/forecast_registry.py`): append-only
  forecasts and resolutions, as-of scoring, idempotency keys, nowcast record kind.
- Integrations consolidated on `integration/market-to-rd-v2` (v0.5.0).
- **Gate met:** 679 offline tests `OK (skipped=3)` on CPython 3.12.10 (re-run by the
  Lead 2026-11-02), independent verifier exit 0, real-data TKG import 171,800
  assertions / 57,381 nodes / 114,419 edges.

## Phase 1 — Real-data reverse-R&D benchmark v1/v2 (DONE, 2026-11-02)

- Bulk openFDA lane, SEC Company Facts, market bars, OpenAlex publications.
- Two targets: continuation (`reverse_rd_v1`) and first-entry (`first_entry_v1`).
- Purged expanding-window rolling origin, persistence baselines, paired bootstrap,
  independent as-of leakage replay.
- **Gate met, with a negative headline:** frozen artifacts reproducible; the model
  does not beat per-pair persistence detectably on continuation, and the entry
  signal is weak/window-dependent. No added source yields a detectable ranking gain.

## Phase 2 — Coverage, power and the reality of the entry signal (CURRENT)

The v2 negative results may be underpowered artifacts of a 51-firm, 322-pair panel
rather than facts about predictability. Phase 2 tests that explanation.

Deliverables:
1. Deterministic applicant-entity universe from the industry lane, replacing the
   hand-curated 51-parent roster as the primary panel definition, with an explicit
   *entity-granularity ablation* (legal applicant entity vs corporate parent).
2. Focus-company gap closed: Dräger and Mindray enter the roster with evidence.
3. Inference upgrade: cluster-aware bootstrap CIs and minimum detectable effects, so
   a null is reported as "no effect" or "underpowered" — never conflated.
4. Lead time at matched false-alarm rate (a benchmark metric the project requires
   but has not implemented).
5. Heterogeneity: predictability by track, firm activity scale and data maturity
   (mission question 6).
6. Re-run the frozen targets on the expanded panel under the identical protocol and
   report the delta honestly, including the possibility that the entry signal
   disappears with more entities rather than getting stronger.

**Gate:** a committed, re-runnable experiment answering one question: *does widening
the entity universe change the measured predictability of first entry, and is the
remaining estimate distinguishable from zero?* Either answer is publishable.

## Phase 3 — Signal-timing program (NEXT)

- Lead/lag measurement between source classes (regulatory, trial, publication,
  financial, procurement, market, hiring) and technology milestones, with
  clustering-aware inference and explicit multiple-comparison control.
- Public hiring data (the one mandated source class still genuinely missing):
  lawful, reproducible job-posting collection with point-in-time snapshots.
- Procurement: only after a snapshot with genuine historical publication times
  exists; the current USAspending pull is `pit_usable=0` and must not be smuggled
  into a retrospective claim.
- Patents: requires either an API key or bulk-file ingestion; until then it stays an
  unimplemented, explicitly declared gap.

## Phase 4 — Evidence-aware method (AFTER BASELINES)

Only if Phase 2/3 produce a real baseline gap to explain:
- discrete-time survival formulation for entry timing (time-to-event, not just
  binary horizon labels);
- evidence-aware fusion with per-source reliability/lag weighting;
- temporal knowledge-graph representation;
- calibration-first probabilistic output.
Explicit non-goal: adopting a Transformer/GNN because it is modern. Adoption
requires a purged, multi-window, baseline-beating, reproducible result.

## Phase 5 — Prospective track record and open benchmark

- Continuous forecast cycle registering genuine future-window forecasts.
- Matured-forecast calibration report (including "worse than base rate" outcomes).
- Open benchmark release: dataset cards, provenance, licence, reproduction scripts.
- Publication draft with negative results in the main text.

## Standing constraints

- Compute: one workstation; overnight-scale jobs only. Prefer deterministic,
  resumable pipelines over large hyperparameter sweeps.
- Every phase must keep `python -m medradar selftest` green.
- No merge to `main` without an independent verification pass on the exact commit.
