# Completion report — MedRadar Foresight Lab as an autonomous, evidence-grounded research programme

**Date:** 2026-11-03 · **Branch:** `research/change-detection-v1` (`main` untouched at `7a639f7`) ·
**Audit:** `research/FINAL_AUDIT.json` · **Gate:** `python tools/round_end.py` → 10 steps, 0 failures

This report states, clause by clause, what the objective asked for, what exists, and how it was verified. It is
written so that a reader can check every line rather than trust it: each row names an artifact, and the audit re-runs
the verifiers and re-derives four load-bearing results from scratch.

---

## 1. The objective, clause by clause

| Required | What exists | Verification |
|---|---|---|
| Persistent research state (MISSION, ROADMAP, BACKLOG, STATE, HYPOTHESES, LITERATURE, EXPERIMENTS, DECISIONS, DATA_PROVENANCE, PREDICTION_PROTOCOL, RESULTS) | all 11 files under `research/`, each substantive | audit step 1 **PASS** — 11 files |
| Run the Observe→Question→Hypothesize→Implement→Experiment→Evaluate→Record→Improve loop with **real runs** | 157 commits on the branch; 43 cycle reports; 73 decisions; **152 result rows, 27 of them negative/null**; 2 retractions marked | audit step 4 **PASS** |
| **Honest negative results** | five retracted findings with the control that killed each (`PAPER_v1.md` §4.2–§4.6), four failed anticipations, two nulls that survived correction, one failed pre-registered bar, one unestablished pipeline component | results index rows R1–R152; `DECISIONS.md` D-007…D-073 |
| Verifiable **code** | stdlib-only `medradar` package; **913 tests**, `python -m medradar selftest` exit 0; every reported number re-derivable | gate steps 1, 7 |
| **Point-in-time datasets** | 6 auditable snapshots (3 backdated, 2 same-day-policy, 1 labelled), SHA-256 manifests, **0 leakage problems**, per-profile leakage audit | gate step 8 **PASS** |
| **Rolling-origin benchmarks** | 376 cells, 12 origins, 717 observations (`experiments/b050/`); plus a pipeline rolling-origin evaluation (68 alerts, 4,594 control cell-quarters) | audit step 7 **PASS**; `b067` |
| **Frozen forecasts** | 2 hash-verified sets; **25 genuinely prospective** forecasts maturing 2026-Q4…2028-Q1; scorer refuses a modified set | audit step 8 **PASS**; gate step 9 |
| **Papers** | 2 drafts, each with a machine-verified claim map: `PAPER_v1.md` (**88 claims**), `PAPER_METHODS_v1.md` (**25 claims**), 5 verified figures | gate steps 2, 3, 4, 5, 6 **PASS** |

**Deliverables: all satisfied.** The audit reports **11 PASS / 0 FAIL / 1 N/A** of 12 checks; the single N/A is the
legacy drug-lane artifact outside this programme's scope.

---

## 2. Reproducibility, not just validity

The round-end gate proves the artifacts *verify*. `tools/final_audit.py` additionally re-runs four deterministic
scripts into a temporary directory and compares the output with the committed JSON:

| script | result |
|---|---|
| `experiments/b074/seasonality.py` | **reproduced**, identical JSON |
| `experiments/b026/density_confirm.py` | **reproduced**, identical JSON |
| `experiments/b067/promotion_rolling_origin.py` | **reproduced**, identical JSON |
| `experiments/b026/validate_track_domain.py` | **reproduced**, identical JSON |

**4 of 4 reproduced; 10 of 10 verifiers pass** (`FINAL_AUDIT.json`).

---

## 3. What the science actually established

**One confirmed decision rule** — an alert followed by a sustained two-month confirmation window may be promoted, at
measured precision 0.914–0.917 against a base rate near 0.70 — replicated at the legal-entity unit, extended to a
second recording process (archived job postings) and to market-aggregate series, and shipped in a policy that
requires named human sign-off, refuses the ramp label below 1.0 event per series-month, and has no automated path.

**One confirmed measurement finding** — ramp recoverability is a function of series density: 0.117 at legal-entity
level, 0.142 at company level, 0.300 on hiring series, 0.396 at track level, and on a controlled thinning experiment
0.444 at 4.16 events per series-month against 0.204 at 0.22 (rank correlation 0.908, effect ratio 2.18×). This is
reported as a **post-failure confirmation** because its first pre-registered criterion failed.

**Everything else is negative, methodological, or scope-limited** — five retractions, four failed anticipations, a
rolling-origin null whose own outcome definition was biased before correction, and an end-to-end pipeline result where
the detector carries information (0.800 / 0.667 / 0.373 persistence) but the promotion filter's marginal value is not
established (+0.133, CI −0.074 … 0.344).

**The transferable output is the measurement discipline**: nine rules in `PAPER_METHODS_v1.md`, each tied to the
failure that motivated it, with two enforcement mechanisms — a schema that rejects a profile lacking contradictory
evidence, and a round-end command whose exit code is the completion claim.

---

## 4. What remains, and why it is not a defect of the work

These are recorded in `ROADMAP.md` §3. None can be discharged by another cycle of the same kind:

1. **Prospective maturation** — 25 forecast authorities mature 2026-Q4 … 2028-Q1; no prospective calibration claim is
   possible before then. Command: `python experiments/b068/maturate_forecasts.py`.
2. **Legacy registry** — 25 nowcasts mature 2027-10 (B-015).
3. **Human sign-off** — one promotion (`medtronic:insulin_delivery:2025-Q3`) is `PENDING_SIGNOFF`; the session cannot
   sign for a person.
4. **Access-blocked lanes** — patents (403) and broad hiring (504) are blocked on external services (D-029/D-031).
5. **Human-adjudicated labels** — B-014 needs a person; its own criterion forbids AI-created fixtures.
6. **Six scheduled analyses** — B-018, B-021, B-029, B-041 and the cohort re-run have **proven data present**
   (`experiments/b073/lane_inventory.json`); they are work, not blockers.

---

## 5. What is explicitly not claimed

- That filing rates predict technology. Every statement is about **public regulatory activity** and about the
  **resolution** of this data; nothing here sees intent, capability or internal R&D.
- That any forecast has skill over technology. **Zero** prospective forecasts have matured.
- That the density scaling generalises beyond binomial thinning of this taxonomy; it is a post-failure confirmation on
  one corpus.
- That the promotion filter improves decisions end to end; that test was underpowered by design and did not establish it.
- That the two papers are submission-ready: both are drafts, and a **rendered** figure review for contrast and
  text-on-text overlap is still outstanding.

---

## 6. How to check this report

```bash
python tools/round_end.py        # 10 verification steps; exit code is the claim
python tools/final_audit.py      # + re-derives four artifacts from scratch; writes research/FINAL_AUDIT.json
python -m medradar selftest      # 913 tests
git log --oneline research/change-detection-v1 | wc -l    # 157 commits
```

The decision log (`research/DECISIONS.md`, 73 entries) and the results index (`research/RESULTS/README.md`, R1–R152)
are the canonical record, including the five retractions and the reasons for each.
