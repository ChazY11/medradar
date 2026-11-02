# Roadmap

Living plan, realigned 2026-11-02 to the Observe → Understand → Anticipate architecture
(`DECISIONS.md` D-011). Phase gates are evidence-based: a phase is done only when its acceptance
criterion is met by a committed artifact. Module-to-layer mapping: `LAYERS.md`.

## Where the program actually stands (2026-11-02)

| Layer | Capability | State |
|---|---|---|
| Foundation | bitemporal store, PIT export, immutable forecast registry, leakage audit | **done and independently audited** |
| Observe | data lanes (FDA, trials, SEC, market, publications), entity universe, taxonomy | **partly done** — entity universe is new and solid; detection is absent |
| Observe | **technology-change detection with false-alarm control** | **not started → current phase** |
| Understand | knowledge graph, evidence fusion, research agent with citations | **prototype exists, not validated for research-quality claims** |
| Anticipate (Level A) | emerging-trend identification | **not built** (depends on Observe detections) |
| Anticipate (Level B) | probabilistic milestone forecasting + calibration | **frozen benchmark exists; no matured calibration** |

## Phase A — Reliability floor (P0) — largely done, continuous

Acceptance: a third party can re-run every reported number; no claim without provenance.

- Done: audit of three divergent branches and defect fixes; bitemporal store; forecast registry;
  deterministic applicant-entity universe (9,412 entities, no fuzzy matching); independent audit of
  the five frozen cycle-1 claims (5/5 PASS, full leakage replay 0/656,048); 751 offline tests green;
  verifier exit 0.
- Continuous obligations: every new module ships with tests; every claim carries a DB/artifact hash
  (audit finding O5); nulls carry MDEs.

## Phase B — OBSERVE: change detection (P1) — **CURRENT**

Question: **can we detect a real change in a company's technology activity, early, without drowning
the analyst in false alarms?**

Deliverables:
1. A detector suite for sparse monthly company×technology activity streams: naive rate-multiplier
   baseline, rolling z-score, Poisson CUSUM, Poisson Bayes factor (`medradar/intelligence/changepoint.py`).
2. **Controlled-truth evaluation**: semi-synthetic injection of known step-changes into real monthly
   stream shapes → detection probability, detection delay (months), false alarms per stream-year;
   leave-company-out to test cross-company generalisation.
3. **Real-data application with FDR control**: Benjamini–Hochberg across tested cells, and a
   confirmation test against an *independent* source to separate genuine change from single-source
   artefacts.
4. **Noise controls**: minimum baseline/total events, seasonality check, product-code reassignment
   audit (the taxonomy is unversioned, so a code remap can manufacture a change point), and an
   explicit spike-vs-level-shift distinction.
5. A pre-registered decision: which detector, if any, beats the naive baseline on the
   delay/false-alarm frontier, and whether real detections confirm cross-source.

**Gate:** a committed, re-runnable benchmark plus a real-data alert set with a documented FDR and
confirmation rate — including the possibility that no detector beats the naive baseline.

## Phase C — OBSERVE: coverage completion (P1, after B)

- Focus-company roster fix: add Dräger and Mindray with evidence from the lane (B-010); re-run the
  universe build and record the new artifact hash.
- Hiring signals (the mandated source class still missing): lawful, point-in-time collection (B-013).
- Patents: key-free ingestion path or bulk files (B-014).
- 8-K/CIK deterministic linking (B-011) — 19,616 unlinked events that carry a CIK.
- Publication-lag sensitivity (B-012).

## Phase D — UNDERSTAND: explanation with traceable evidence (P2)

- Corporate technology knowledge graph over real history (prototype exists; needs a QA pass against
  the new entity universe).
- Company R&D profiles: which directions changed, related to capability, competitors, demand and
  resources.
- Evidence fusion and **contradictory-evidence discovery** as first-class outputs.
- Auditable research conclusions: every judgement carries the seven required evidence fields
  (`MISSION.md` §2, Layer 2).
- Evaluation must use verifiable evidence and labelled samples; LLM assistance is permitted for
  organisation and hypothesis generation only, never for facts or citations.

## Phase E — ANTICIPATE Level A: emerging-trend identification (P3)

Feeds directly on Phase B detections: a trend is "forming" when multiple independent evidence types
cross their own detection thresholds within a window. Requires the Phase B detector to work and the
Phase C sources to exist.

## Phase F — ANTICIPATE Level B: probabilistic forecasting and prospective validation (P3)

Continues the frozen cycle-1/2 work (see `RESULTS/`), re-tested on the entity panel:
- source-null re-test with MDEs (B-018), exogenous scale measure (B-019), acquisition chains (B-020),
  lead/lag program (B-021);
- 25 registered nowcasts mature through 2027-10 → the first real calibration report (B-015).

## Phase G — P4 advanced methods, only with cause

Temporal graph learning, dynamic knowledge graphs, multimodal temporal models, evidence-aware
forecasting, causal designs. Entry condition: a baseline gap that simpler methods demonstrably
cannot close.

## Standing constraints

- One workstation; deterministic, resumable pipelines; no hyperparameter sweeps for their own sake.
- Every phase keeps `python -m medradar selftest` green.
- No merge to `main` without independent verification of the exact commit.
- Scope discipline: no global-industry prediction, no cross-industry digital twin, no macro
  forecasting, no large LLM training, no unverifiable speculation about internal R&D.
