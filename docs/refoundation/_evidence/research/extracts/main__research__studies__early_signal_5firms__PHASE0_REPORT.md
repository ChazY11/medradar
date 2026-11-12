# PHASE 0 REPORT — Early detection of corporate technology shifts in medical devices

**Study:** `early_signal_5firms` · **Directive:** RESEARCH DIRECTIVE 001 · **Branch:**
`research/early-signal-5firms` · **Commits:** `42a923d`, `9627947`, `b957440` (+ this report)

> **Phase 0 verdict: CONDITIONAL-GO.** The measurement pipeline exists, the data are real, and the conditions under
> which Phase 1 could produce a valid answer are now explicit. Two of those conditions are currently unmet and are
> not in the agent's gift to meet: an earlier signal source must survive the availability audit, and the 60 candidate
> cases must be adjudicated by a named human reviewer.

---

## 1. What the directive asked for, and what exists

| deliverable | artifact | state |
|---|---|---|
| **A. COVERAGE_MATRIX** | `COVERAGE_MATRIX.{json,md}` | 5 firms × 5 domains × window, machine-readable + readable |
| **B. EVIDENCE_TIME_AUDIT** | `EVIDENCE_TIME_AUDIT.json` | per-source tier with reasons; clock audit included |
| **C. LABELING_PROTOCOL** | `LABELING_PROTOCOL.md` | Target A/B, five labels, independence rule, human-only adjudication |
| **D. EXPERIMENT_PROTOCOL** | `PROTOCOL.md` | RQ1–RQ5, H1–H4, frozen windows, metrics, false-alarm budget |
| **E. CASE_CANDIDATES** | `CASE_CANDIDATES.{json,md}` | 60 packets, all `PENDING_HUMAN_REVIEW`, no labels |
| **F. PILOT_RESULTS** | `PILOT_RESULTS.{json,md}` | real replay, leak audit, honest null |
| **G. PHASE0_REPORT** | this file | capability, data, experiments run vs not run, verdict |
| **H. REPRODUCIBILITY** | `REPRODUCIBILITY.md` | commands, seeds, versions, verification |

Supporting: `ENTITY_AND_DOMAIN_AUDIT.json`, `DOMAIN_AMENDMENT_001.md`, `STUDY_DECISIONS.md` (S-001…S-006).

## 2. Existing capability reused (nothing rewritten)

`medradar.intelligence.{profile,promotion,snapshot,changepoint,evalstats,forecasts,taxonomy}`,
`medradar.studies.coverage` (new, 18 tests), the frozen snapshot manifest machinery, and the programme's validated
quarterly detector (rolling z ≥ 3.5). The study added one module, four analysis programs and its own decision log; it
modified no existing module, no frozen forecast and no prior research record.

## 3. Data that exist (measured, not assumed)

| source | records | span | tier |
|---|---:|---|---|
| 510(k) | 176,466 | 1977–2026 | **B** |
| device recalls | 59,646 | 2002–2026 | **B** |
| PMA | 57,372 | 1979–2026 | **B** |
| clinical trials (ctgov) | 55,592 | 2004–2026 | **B** |
| SEC 8-K | 20,976 | 2019–2026 | **B** |
| product codes → tracks | 7,097 | — | mapping, unversioned until `taxonomy.py` |
| procurement awards | 3,453 | — | **C** (dates NULL) |
| publications | 616 annual rows | — | **C** for lead time |
| patents | **0** | — | **D** (access blocked) |

**No source reaches Tier A**: `first_seen_at` is the collection date, not a publication date.

## 4. Coverage and its consequence

- 42 tracks are touched by the five firms in 2018–2025.
- Only **2 tracks** are shared by ≥3 firms at the pre-declared floors: `imaging_us` (GE HealthCare, Mindray, Philips)
  and `respiratory` (GE HealthCare, Medtronic, Philips) → **6 firm × track cells**, not the 12–18 the directive hoped
  for. Recorded in `DOMAIN_AMENDMENT_001.md` before any outcome was examined.
- **Dräger**: 6 observations in 4 quarters, one domain → descriptive only, excluded from every evaluation.
- **Mindray**: no `company_key` in the roster; 244 alias-resolved events make it evaluable in `imaging_us` only.
- **GE HealthCare**: the roster key spans 1969–2026 across `GE MEDICAL SYSTEMS` and current naming; legal-entity
  continuity is **not established** and no claim may assert it.

## 5. Experiments run vs not run

**Run:** schema and store characterisation; coverage matrix; evidence-time audit; clock audit; entity-resolution
audit; domain-sharing computation; 60-packet build with a prospective, outcome-blind rule; minimal historical replay
with an independent leak audit.

**Not run, and why:**

| not run | blocking reason |
|---|---|
| H1 fusion test | needs ≥2 audited independent sources at the same cells; only one family is usable so far |
| H2 temporal ordering / lead time | no measured lead time is possible while the positive is "the event itself" and no earlier source is included |
| H3 heterogeneity test | 9 rule-based positives across 6 cells |
| H4 density constraint | designable, but it would have been a test of a known arithmetic limit, not a discovery |
| Target B training/labels | requires a named human reviewer; the agent may not label |
| Leave-one-company-out | two confirmatory tracks × three firms only; meaningful only after a working model exists |
| M2 patent model | patents absent (`NOT_EVALUABLE`, not filled with proxies) |
| M4 corporate/market model | SEC 8-K too sparse at cell level; procurement Tier C; hiring partial |

## 6. Findings with evidence

1. **The frozen research lane is the wrong store for this study.** The main-clone store carries recalls, trials and
   8-K; the curated lane carries 510(k)+PMA only (55,090 vs 375,378 events).
2. **Cross-company validation is structurally limited to two tracks** at the declared floors. This bounds RQ4 before
   any modelling and is reported rather than engineered away.
3. **Availability can be enforced and audited**: 0 violations once the audit tested the right property; the pilot's
   first audit asserted the wrong one and produced 118 false alarms (documented).
4. **A rate-anomaly detector cannot detect a single-event entry** at this sparsity: 0.85 events per cell-quarter,
   z ≈ 1.8 for a 0→1 move against a 3.5 threshold. The null result is explained by design mismatch, not by a
   statistical accident, and the correction is pre-committed (sustained-change positive).
5. **Alias matching has a measured false-positive mode** (`Surge Medical Sales` ↔ `GE MEDICAL`), excluded and
   recorded; six further strings await human adjudication.

## 7. Honest verdict

**CONDITIONAL-GO.** Phase 0's ten gate conditions are met except the two that require either new source work or a
human:

- ✅ five firms' coverage audited (and their limits recorded);
- ✅ domain validity checked, with a frozen amendment;
- ✅ historical availability assessed source by source (no Tier A);
- ✅ RQs and primary metrics pre-registered;
- ✅ labelling protocol established;
- ✅ baseline evaluation design fixed;
- ✅ one real historical replay passed its engineering checks (leak audit 0);
- ✅ no known undisclosed leak;
- ✅ all non-evaluable parts explicitly marked;
- ✅ Phase 1 feasibility supported by specific evidence — **and it is limited**.

**Phase 1 is not GO until:** (a) the positive becomes a sustained change; (b) an earlier source (trials or 8-K)
survives the availability audit so lead time is measurable at all; (c) the 60 cases are adjudicated by a named human
with the independence rule enforced.

## 8. What would make this study stop

- If no earlier source survives the audit, the study can only measure **concurrent detection**, and the directive's
  core question (how early) becomes unanswerable — a NO-GO for lead time, while coverage documentation stands.
- If adjudication yields fewer than ~10 `Confirmed Shift` labels across the two confirmatory tracks, RQ4 replication
  cannot be tested and the study should be narrowed to a single-track descriptive design.

## 9. Reproduction

See `REPRODUCIBILITY.md`. All commands are stdlib-only, deterministic where sampling is involved (seed 8080), and
read the stores read-only.
