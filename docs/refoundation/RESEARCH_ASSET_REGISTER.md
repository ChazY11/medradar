# RESEARCH ASSET REGISTER — REFOUNDATION-001

> **Owner:** `research-registrar` (scientific-integrity auditor) · **Task:** `task-3`
> **Collected:** 2026-11-12 (Asia/Shanghai), read-only from the local git object store.
> **Companion machine artifacts:** `_evidence/research/frozen_artifact_hashes.json`,
> `_evidence/research/extracts/` (verbatim extracts used for line citations).
> **This document is evidence, not a plan.** It records what exists, what was measured, what was
> concluded — and, above all, what may **not** be said in public.

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** Every research asset reachable from any ref of `ChazY11/medradar` at audit time: the ten
merged PRs (#2–#11), the nineteen open draft research PRs (#15, #16, #18–#30), and one branch
(`research/full-history-v1`) with no PR. Product/engineering PRs are covered only where they carry a
scientific claim. Total: **24 studies/lanes** (some merged PRs are one lane, e.g. #6–#11 are the same
early-signal study published in five steps).

**Method.**

1. Every statement is labelled **[FACT]**, **[INFERENCE]**, **[RECOMMENDATION]** or **[UNVERIFIED]**.
2. A verdict is quoted **verbatim** from the study's own frozen verdict artifact; the locator is given.
   Where a study did not issue a GO/NO-GO, that is stated rather than invented.
3. Negative results are reproduced in the study's own wording. A NO-GO is never restated as
   "inconclusive", and an underpowered result is never restated as "no effect".
4. Numbers are copied from committed artifacts, never recomputed or rounded up.
5. Line locators are `main:<path>:<line>` for `origin/main`, and `<branch>:<path>:<line>` for a branch.
6. `.sha256` sidecars and committed manifests are treated as freeze evidence; hashes were recomputed
   only for the small set in `_evidence/research/frozen_artifact_hashes.json`.

**Evidence base (primary, all read).** `docs/refoundation/_FACTS.md`; `_evidence/repo_facts.json`;
`research/STATE.json` and `research/AUDIT.json` on `main`; `research/RESULTS/README.md` (R1–R155);
`papers/PAPER_v1.md`, `PAPER_NEGATIVE_v1.md`, `CLAIMS_NEGATIVE.json`; the early-signal study directory;
`experiments/reverse_rd_v1/REPORT.md`, `reverse_rd_v2/REPORT.md`, `detect_v1/REPORT.md`,
`cycle2_coverage/REPORT.md`; and, per branch, the frozen protocol + result + verdict files named in
each section. Commands used: `git show`, `git ls-tree`, `git log`, `git cat-file`, `git grep`.
No file was modified except this deliverable and `_evidence/research/`.

**What this register can and cannot claim.** It can claim that a verdict artifact exists, that it says
what is quoted, and where it lives. It **cannot** claim the underlying science is correct, that an
independent human verified it, or that a number reproduces on this machine: no test suite, model,
database or live API was run during this audit (per `_FACTS.md` §0 rules 3–5 and this task's read-only
constraint). Reproduction commands are recorded exactly so an owner can run them.

**Structural limits that shape every reading below.**

- **`main` is v0.5.0 and contains only PRs #2–#11.** Everything named "PHOENIX", "ATLAS", "HORIZON",
  "CONVERGENCE", "S-028", "S-029", "S-030", "S-031", "QLoRA", "Live Observatory" exists **only on a
  branch** [FACT: `main:research/STATE.json:11-12` says `phase=complete_verified`, `cycle=44`, but
  `_FACTS.md:68-74` establishes the branch-only reality].
- **No research database is in the repository.** `data/medradar.sqlite` is absent from every branch;
  the PHOENIX protocol records the frozen DB by size and SHA-256 but the file itself is not committed
  [FACT: `research/phoenix-001-round2:docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md:16-29`, and
  `research/phoenix-001-round2:docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md:28` says `research.sqlite`
  "不存在"]. Therefore every "reproduce" command below requires a locally provisioned store;
  **until that store exists, no number in this register is reproducible from a clean clone** [FACT].
- **A committed state file describes a working tree, not the commit that ships it.** `research/STATE.json`
  on `main` hardcodes `<REDACTED_LOCAL_PATH> and `main_untouched_at: 7a639f7`
  [FACT: `main:research/STATE.json:21-25`], which is not `main`'s HEAD `b2a14c0` [FACT:
  `_FACTS.md:61`]. This is a provenance defect, not a cosmetic one: it makes the state file
  unverifiable against the tree it is committed in.
- **Test-count claims disagree across records**: `STATE.json` says 795 tests
  [FACT: `main:research/STATE.json:29`]; `PAPER_v1.md` says 854 [FACT: `main:papers/PAPER_v1.md:469`];
  `README.md` claims 678 [FACT per `_FACTS.md:252`]; a branch report says 1,074 [FACT per Lead message,
  not re-run here — **[UNVERIFIED] by this registrar**]. Treat any test count as **[UNVERIFIED]** until
  the owner runs one command and records it once.

---

## 1. Master table of all studies

Verdict class legend: **NEG-NO-GO** = a study-level NO-GO was issued; **NEG-NULL** = pre-registered
test returned a null/negative without a GO/NO-GO vocabulary; **MIXED** = some gates pass, some fail;
**INCONC** = explicitly underpowered/unblocked/not evaluable; **INFRA** = methodology/infrastructure
deliverable with no predictive claim; **POS-NARROW** = one narrow, caveated positive.

| # | Study ID (PR) | Branch / location | Tier | Head commit | Core result (one line) | Verdict class | Public claim? |
|---|---|---|---|---|---|---|---|
| 1 | TKG + Forecast Registry (#2) | `main:medradar/tkg`, `main:medradar/forecast_registry.py` | merged infra | `b2a14c0` (tree) | Bitemporal store + immutable forecast registry; **no real forecast, no model, no out-of-sample return** | INFRA | no |
| 2 | Market-to-R&D v1/v2 (#3, #4) | `main:experiments/reverse_rd_v1`, `reverse_rd_v2` | merged study | `b2a14c0` (tree) | Entry target weak and window-dependent; added sources add no stable ranking; R11 = modest cycle-2 gain | MIXED | not yet |
| 3 | Change detection / Foresight Lab (#5) | `main:experiments/detect_v1`, `cycle2_coverage`, `research/RESULTS` | merged study | `b2a14c0` (tree) | Best detector recovers 0.223 of injected shifts at 2% FAR; detector not identifiable across resolutions | MIXED / NEG-NULL | no |
| 4 | Early-signal five firms S-026/S-027 (#6, #7) | `main:research/studies/early_signal_5firms` | merged study | `b2a14c0` (tree) | G1 lead-time **NO-GO** (3 pairs vs floor 10); O1 **underpowered** (1 then 0 onsets); 1D unit **not supported** | NEG-NO-GO | no |
| 5 | Third-source cross-check (#8) | `main:research/studies/early_signal_5firms/THIRD_SOURCE_*` | merged sub-study | `b2a14c0` (tree) | 4 SUPPORTED_BEFORE / 5 AFTER; only **one** near-term hit (LT-07, 76 d); 3 are decades old | NEG-NULL | no |
| 6 | Agent pre-adjudication (#9) | `main:.../ADJUDICATION_AGENT_V1.*`, `ADJUDICATION_AMENDMENT_002.md` | merged sub-study | `b2a14c0` (tree) | Non-human tier; **0 Confirmed Shift**, 45 Uncertain; unusable as ground truth | INFRA / NEG-NULL | no |
| 7 | Human review workbench (#10, #11) | `main:.../HUMAN_REVIEW_WORKSHEET.*`, `REVIEW_GUIDE.md` | merged tooling | `b2a14c0` (tree) | 69 rows, drop-down validator, refusal paths verified; **no human label exists** | INFRA | no |
| 8 | Papers & claim maps (PAPER_v1 / NEGATIVE / METHODS) | `main:papers/*` | merged publication record | `b2a14c0` (tree) | 5 retractions; 1 confirmed decision rule (precision 0.914–0.917 vs ~0.70 base); momentum rule flags 35/53 but the test supports 4/53 | POS-NARROW | yes (strictly scoped) |
| 9 | AI evidence review (#18) | `research/ai-evidence-review` | branch sub-study | `b68af12` | AI review of 69 packets: **0 Confirmed Shift**, 48 Routine; 6 packets are PMA process supplements; 8/9 lead pairs join different devices | NEG-NULL / triage | no |
| 10 | Local LLM foundation Phase 2 (#19) | `research/local-llm-foundation` | branch study | `d4c4e43` | Rules vs Qwen3-4B on 19 docs; **`RESEARCH_TRAINING_BLOCKED`** | INCONC / blocked | no |
| 11 | S-030 overnight QLoRA (#20) | `research/overnight-qlora-s030` | branch study | `5954d7d` | 60-step QLoRA; silver-label agreement 1.000 but negative-control false positives **0 → 0.667**; P/R/F1 `NOT_EVALUABLE` | INCONC / blocked | no |
| 12 | Innovation Signals Observatory / Phase 4 hiring (#21) | `research/innovation-signals-observatory` | branch study | `c4327ce` | 5/5 firms observable; track coverage 6.1%; hiring is an **observation layer, not a signal layer** | INFRA + NEG-NULL | no |
| 13 | S-031 hiring capability study (#22) | `research/s031-hiring-capability-study` | branch study | `e3e39d5` | 100 stratified postings, AI preliminary labels only; **no accuracy/P/R/F1**; H1–H3 evidence insufficient | INCONC | no |
| 14 | PHOENIX-001 round 1 (#23) | `research/phoenix-001-external-methods` | branch study | `bd2f839` (remote; local +33 commits) | H1 supported; H9 refuted; H5/H6 blocked; H2/H3/H4/H7/H8/H10 inconclusive | MIXED | no |
| 15 | PHOENIX-001 round 2 (#24) | `research/phoenix-001-round2` | branch study | `cd63c72` | Frozen protocol; H3/H6/H9 NOT SUPPORTED; **H7 SUPPORTED** (method only); **H8 SUPPORTED (modest, +0.0379)** then refuted by #25 | MIXED | no |
| 16 | PHOENIX-002 H8 re-validation (#25) | `research/phoenix-002-h8-validation` | branch study | `c826703` | **NO-GO**: ΔAP +0.0294 < τ=0.03; cross-construct +0.0123; placebo p=0.0846; dedup collapses to +0.0048 | NEG-NO-GO | no |
| 17 | PHOENIX-003 early evidence (#26) | `research/phoenix-003-early-evidence` | branch study | `91495bc` | **NO-GO**: specificity 1.37 vs 3–5; placebo p=0.881; 92.3% of links are follow-up of already-regulated products | NEG-NO-GO | no |
| 18 | DATA-EXPANSION-001 (#27) | `research/data-expansion-001` | branch study | `192085e` | 59 sources, 31 verified; EXP-B: **no association strategy usable**; EXP-C: **`NO_DETECTABLE_LEAD`** (p=0.569) | NEG-NO-GO (lead) | no |
| 19 | ATLAS-001 (#28) | `foundation/atlas-001` | branch infra | `c636836` | Identity pilot: 934 DI-confirmed cross-registry pairs; precision 1.000 is a **consistency check, not a discovery** | INFRA | no |
| 20 | HORIZON-001 (#29) | `research/horizon-001` | branch study | `2dcdc99` | Patent gap filled keylessly (EPO sitemap; CIPO); **EXP-H2: 0 CONFIRMED of 726**; 60% publication-date disagreement | MIXED / NEG-NULL | no |
| 21 | CONVERGENCE-001 (#30) | `integration/convergence-001` | branch integration | `c6606c3` | 5,884 records end-to-end, 0 rejected; independent verifier **81 PASS / 10 FAIL / 4 UNVERIFIABLE** | INFRA (with defects) | no |
| 22 | S-028 graph early-signal (#15) | `research/s028-temporal-graph-early-signal` | branch study | `4c6686f` | H1 no improvement; sealed as **credible exploratory negative result**; "well-powered" claim invalidated | NEG-NULL (sealed) | no |
| 23 | S-029 evidence-based relations (#16) | `research/s029-evidence-based-relations` | branch study | `10f25d1` | **`NO-GO FOR PREDICTION`**: T4 zero point-in-time claims, T6 no human adjudication | NEG-NO-GO | no |
| 24 | full-history-v1 (no PR) | `research/full-history-v1` | branch study | `969fd0c` | H1 **SUPPORTED marginally** (ΔAP +0.0584, CI [+0.0020,+0.1213]); not established vs two-way baseline | POS-NARROW | not yet |

**Counts.** 4 explicit study-level NO-GOs (early-signal G1, S-029, PHOENIX-002, PHOENIX-003); 1
lead-level NO-GO in DATA-EXPANSION (EXP-C); 4 explicit "not evaluable / blocked / underpowered"
(early-signal O1, S-030, local-LLM, S-031); 2 narrow positives (papers' confirmed decision rule,
full-history H1); the remainder are infrastructure, mixed or null. **Zero studies in this repository
currently support a validated, externally generalisable predictive or early-warning claim.**

---

## 2. Per-study detail

### 2.1 TKG + Forecast Registry (PR #2, merged)

- **Goal / question.** Can the system reconstruct "what was knowable when" and store forecasts
  immutably so that prospective scoring becomes possible? This is infrastructure, not a study of the
  world.
- **Design.** SQLite bitemporal store with separate `known_at`/`valid_at`, late facts, retractions,
  visible-endpoint constraints; forecast registry for 3/6/12/24-month horizons with Brier, log loss,
  calibration bins, ECE.
- **Data / scale.** No real data is generated by the PR; it ships an offline CLI demo and tests.
  [FACT: `main:docs/research/TKG_ACCEPTANCE.md`, `FORECAST_REGISTRY_ADR.md` exist; `main` tree].
- **Preregistration.** ADR + acceptance document, not a scientific pre-registration
  [FACT: `main:docs/research/TKG_ADR.md`, `FORECAST_REGISTRY_ADR.md`].
- **Core result.** Infrastructure delivered; adversarial review fixes recorded (SQL REPLACE history
  overwrite, microsecond comparison leak, early settlement of future events, backfilled-sample
  contamination). The PR body explicitly states: "本 PR 交付研究基础设施，未生成真实预测、训练模型或
  证明样本外收益" [FACT: `_evidence/repo_facts.json` PR #2 body].
- **Verdict.** No GO/NO-GO. **No forecast has matured; calibration evidence is zero**
  [FACT: `main:research/STATE.json:51`, `main:research/STATE.json:94`].
- **Limitations.** Single writer; old schemas rejected, not migrated; source revision numbers unknown;
  content digest ≠ source version. **No point-in-time data exists to populate it** — the parent
  programme's own state file says `available_at == event_date` and `fetched_at` covers two days
  [FACT: `research/phoenix-001-round2:docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md:30-46`].
- **Reproduce.** `python -m medradar selftest`; `PYTHONPATH=. python docs/research/foundation_probe.py`
  [FACT: `_evidence/repo_facts.json` PR #2 body].
- **Independent verification.** Review by a different model context per PR body; not human, not
  external [FACT: PR #2 body: "开发与复核由 Kimi Code 的不同上下文执行… 尚未完成 DeepSeek 代码交叉验证"].
- **Public claim?** **No.** It is a container with no validated contents; claiming "we can forecast
  with calibrated probabilities" would be unsupported.

### 2.2 Market-to-R&D v1 / v2 (PR #3, #4, merged)

- **Goal / question.** Does public market/regulatory/financial evidence predict a firm's **first entry**
  into a technology track, and does continuing activity persist?
- **Design.** Expanding-window rolling origin, purged training (12-month label window closed before
  origin), independent final-origin holdout, leakage replay via independent as-of SQL, logistic
  baselines vs per-pair persistence; multi-window (3 sequential holdouts) in v2; source ablation
  (financial, market, publication).
- **Data / scale.** openFDA 55,090 bulk events (31,219 510(k) + 23,871 PMA), coverage to 2026-10-15;
  SEC 43,420 facts / 32 companies; USAspending 3,453 awards with **0 point-in-time usable**;
  continuation 6,701 examples / 25 origins; entry 41,003 examples / 24 origins, 503 positives
  (base rate 1.23%); final holdout 2025-10-01, 307 rows / 129 positives (continuation), 1,716 / 26
  (entry) [FACT: `main:experiments/reverse_rd_v2/REPORT.md:17-25`, `:29`].
- **Preregistration.** Protocol documented, but v2 is a new target (`first_entry_v1`) defined in
  `docs/REVERSE_RD.md`; three holdouts are **overlapping, not independent replications**
  [FACT: `main:experiments/reverse_rd_v2/REPORT.md:29`, `:123`].
- **Core result.**
  - Continuation: mean AP 0.7737 vs pair persistence 0.7555; model−pair Δ +0.0022 CI
    [−0.0316, +0.0368] → **no detectable ranking advantage** [FACT:
    `main:experiments/reverse_rd_v2/REPORT.md:38-62`].
  - Entry: mean AP 0.1068; point estimate beats pair persistence in all three windows but only the
    last excludes zero; with 25–27 positives per window this is **not evidence of a stable effect**
    [FACT: `main:experiments/reverse_rd_v2/REPORT.md:88-97`].
  - Added sources: financial, market, publication — "the only replicating effect is a small
    calibration/FPR shift… no source adds a statistically detectable ranking improvement"
    [FACT: `main:experiments/reverse_rd_v2/REPORT.md:146`, `:164`].
  - R11/R12 (cycle 2): entity cohort entry ΔAP +0.0973 excluding zero in 3/3 windows; original 51-parent
    panel +0.0564 below its MDE → **"the cycle-1 negative was partly a coverage artefact"**
    [FACT: `main:research/RESULTS/README.md:45-56`].
- **Verdict.** No single GO/NO-GO. The canonical ledger entry is:
  **"R11 … supported (modest)"**, **"R12 … negative about cycle 1"**, and the Cycle-1 headline:
  **"The system, as of v0.5.0, has not demonstrated predictive skill for corporate technological
  entry."** [FACT: `main:research/RESULTS/README.md:23-33`].
- **Limitations.** 51 curated companies, not a random industry sample; two IFRS filers lack US-GAAP
  facts; entry label is *first observed public milestone*, not a project; unversioned taxonomy; 55.1%
  of material events have no track; as-of replay cannot detect semantic leakage
  [FACT: `main:experiments/reverse_rd_v2/REPORT.md:117-124`].
- **Reproduce.** `python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite --holdouts 3`
  [FACT: `main:experiments/reverse_rd_v2/REPORT.md:6`].
- **Independent verification.** Leakage replay independently recomputes 27 features: 1,107,081 values,
  0 mismatches [FACT: `main:experiments/reverse_rd_v2/REPORT.md:23-24`]. Holdouts are not independent.
- **Public claim?** **No** for a stable predictor; **not yet** for R11's modest entry signal (requires
  genuinely non-overlapping prospective validation).

### 2.3 Change detection / Foresight Lab (PR #5, merged)

- **Goal / question.** Is corporate technological evolution detectable — and, later, predictable —
  from public regulatory filings at a controlled false-alarm budget?
- **Design.** Controlled-truth benchmark: real quarterly/monthly series, known shifts injected,
  four detectors calibrated to a target FAR; multi-resolution sweep; calibration tests (exact binomial);
  rolling-origin benchmark (376 cells, 12 origins, 717 observations); point-in-time snapshot chain.
- **Data / scale.** 31,802 premarket submissions 2016-11…2026-09 (119 months); 9,412 deterministic
  entities; 2,663 device trials (43 tracks, 46 companies); archived hiring for 13 firms
  [FACT: `main:papers/PAPER_v1.md:9-13`]. 67,084 company-track-quarter rows in later PHOENIX panel.
- **Preregistration.** Public decision log `research/DECISIONS.md` (74 decisions) names statistic,
  null, lags, split point, decision rule and expected failure mode before each run
  [FACT: `main:papers/PAPER_v1.md:147-153`].
- **Core result.**
  - Best detector at 2% FAR: sensitivity **0.223** (naive), 0.181 CUSUM, 0.122 Bayes, 0.112 z
    [FACT: `main:papers/PAPER_v1.md:168-171`].
  - Detector identity **not identifiable across resolutions**; quarterly winner z-score 0.147; Kendall
    τ vs monthly = **−1.0** [FACT: `main:papers/PAPER_v1.md:173-193`].
  - Calibration: naive ratio flags **35 of 53** companies; exact binomial supports **4**; MDE range
    1.77×–22.93× [FACT: `main:papers/PAPER_v1.md:220-230`].
  - Rolling origin: pre-registered outcome produced a spurious "anti-prediction" lift 0.49; corrected
    future-vs-long-run lift **1.22** and **no predictor's interval excludes 1**; signal fires 5/717
    [FACT: `main:papers/PAPER_v1.md:232-244`].
  - Verdict instability: 40 stable / 13 changed / **2 reversed** of 53 across four as-of dates
    [FACT: `main:papers/PAPER_v1.md:246-252`].
- **Verdict.** No GO/NO-GO vocabulary; the programme's own state file states the OBSERVE layer is
  "data spine + entity universe + a working change detector with measured operating characteristics"
  and that **"2x shifts remain undetectable at any honest budget; data density is the binding
  constraint"** [FACT: `main:research/STATE.json:33-43`]. The papers paper is explicit:
  **"We conclude that this data supports narrow, budget-explicit statements about public filing rates
  and nothing about intent, capability or internal R&D"** [FACT: `main:papers/PAPER_v1.md:40-43`].
- **Limitations.** 0.21 events/cell-month; unversioned taxonomy can manufacture waves; Special 510(k)s
  (15.01%) not separated; no independent confirmation source in the shipped spine
  [FACT: `main:research/STATE.json:36-43`, `main:papers/PAPER_v1.md:421-455`].
- **Reproduce.** `python experiments/detect_v1/benchmark.py`;
  `python experiments/b050/rolling_origin.py`; `python papers/verify_claims.py`
  [FACT: `main:papers/PAPER_v1.md:468-477`].
- **Independent verification.** `papers/verify_claims.py` checks 88 claims both directions; figures
  re-derived by `verify_figures.py`; rendered-layout checker `check_layout.py` found 3 defects missed
  by structural checks [FACT: `main:research/AUDIT.json:85-92`; `main:papers/PAPER_v1.md:376-398`].
  This is **artifact consistency, not peer review**.
- **Public claim?** **No** for prediction. The **only** defensible positive is the narrow promotion
  rule in §2.8.

### 2.4 Early-signal five firms — S-026/S-027 (PR #6, #7, merged)

- **Goal / question.** Can public evidence identify a medical-device firm's technology shift **earlier**
  than conventional regulatory monitoring, at a fixed false-alarm budget?
- **Hypotheses.** H1 fusion improves detection; H2 non-regulatory signals precede milestones; H3
  heterogeneity; H4 density bounds inference [FACT:
  `main:research/studies/early_signal_5firms/PROTOCOL.md:21-31`].
- **Design.** Pre-registered Phase 0 coverage/evidence-time audit; four frozen gates: G1 lead-time
  (≥10 eligible trial→clearance pairs, ≥2 firms), O1 two-track fusion (≥10 onsets), expanded O1
  (≥10 onsets), 1D event-level earlier detection at equal FAR. Target A = observable milestone;
  Target B = human-adjudicated shift, forbidden to the agent
  [FACT: `main:research/studies/early_signal_5firms/PROTOCOL.md:44-53`, `:97-107`].
- **Data / scale.** 5 firms (Medtronic, GE HealthCare, Philips, Dräger, Mindray); window
  2018-01-01…2025-12-31 (extended to 2017 in crosswalk); store holds 375,378 events, of which 510(k)
  176,466, recalls 59,646, PMA 57,372, trials 55,592, 8-K 20,976. Coverage audit found only **2 tracks**
  shared by ≥3 firms → **6 firm-track cells**, not 12–18 [FACT:
  `main:research/studies/early_signal_5firms/PHASE0_REPORT.md:37-60`].
- **Preregistration / freeze.** `PROTOCOL.md` is DRAFT pending human sign-off; four Phase-1 protocols
  written before their experiments; owner sign-off recorded in S-019 with an explicit boundary: the
  **69 case labels remain pending** [FACT: `main:research/studies/early_signal_5firms/STUDY_DECISIONS.md:238-265`].
- **Core result.**
  - G1: `0` pairs on device tracks; `3` pairs across 2 firms on the assumed crosswalk → below floor 10
    → **NO-GO** [FACT: `main:research/studies/early_signal_5firms/LEAD_LAG_PROBE_CROSSWALK.md:3-5`;
    S-007 at `STUDY_DECISIONS.md:65-73`].
  - Authorised keyword crosswalk: `17` pairs / 3 firms → formal **GO**, but only **9 distinct later
    clearances** → **"GO (frozen count) / FRAGILE (independence check)"**; under distinct-event
    counting it is below floor [FACT: `main:research/studies/early_signal_5firms/LEAD_LAG_PROBE_CROSSWALK.md:5`;
    S-020 at `STUDY_DECISIONS.md:269-291`].
  - O1 two-track: **1 onset** in 24 company-years → underpowered; descriptive recalls 1.0 on 1 positive
    [FACT: `main:research/studies/early_signal_5firms/STUDY_DECISIONS.md:101-113`].
  - Expanded O1: **0 onsets** in 5 cells / 2022–2025; sign test all p=1.0; verdict **UNDERPOWERED**
    [FACT: `main:research/studies/early_signal_5firms/CONCURRENT_DETECTION_EXPANDED.md:5-7`, `:18-24`].
  - 1D event-level unit: coarser quarterly detector fires **earlier**, differences +133.9 d and +32.7 d
    → "the finer unit buys power, not latency" → **not supported**
    [FACT: `main:research/studies/early_signal_5firms/STUDY_DECISIONS.md:180-217`;
    `main:papers/PAPER_NEGATIVE_v1.md:115-136`].
- **Verdict (quote).** Gate table: **"G1 lead time … 3 pairs, 2 firms — NO-GO"**; **"O1 two-track
  fusion … 1 onset — underpowered"**; **"O1 expanded fusion … 0 onsets — underpowered"**; **"1D
  event-level unit … coarser detector earlier by 32.7–133.9 days — not supported"**
  [FACT: `main:papers/PAPER_NEGATIVE_v1.md:144-149`]. Phase 0 itself is **CONDITIONAL-GO**
  [FACT: `main:research/studies/early_signal_5firms/PHASE0_REPORT.md:6-9`].
- **Limitations / biases.** Definitional as well as empirical: a different operationalisation of
  "change" could behave differently; recalls share the regulator (partial independence); two firms
  resolved by applicant-string matching with a confirmed false-positive mode (`Surge Medical Sales` ↔
  `GE MEDICAL`); Dräger not evaluable; **no human label exists, so no Target B analysis**
  [FACT: `main:papers/PAPER_NEGATIVE_v1.md:157-167`].
- **Reproduce.** `python experiments/b080/coverage_audit.py` … `b089/onset_ladder.py`
  [FACT: `main:papers/PAPER_NEGATIVE_v1.md:169-180`].
- **Independent verification.** Agent self-review S-026 against the exact published head (0 data files,
  0 secrets, 88/88 + 25/25 + 24/24 claims, 69 packets still pending); **explicitly not peer review**
  [FACT: `main:research/studies/early_signal_5firms/STUDY_DECISIONS.md:382-410`].
- **Public claim?** **No** — only the negative result may be quoted; even "17 pairs → GO" must travel
  with "FRAGILE / n_effective = 9".

### 2.5 Third-source cross-check (PR #8, merged)

- **Goal.** Does an independent publication source place a programme **before** the clearance?
- **Design.** Protocol frozen before queries: deterministic `(AFF:"company") AND ("keyword")` strings;
  independence rule excludes trial reports; availability = first publication date
  [FACT: `main:research/studies/early_signal_5firms/THIRD_SOURCE_PROTOCOL.md`; S-028 at
  `STUDY_DECISIONS.md:442-468`].
- **Data / scale.** Nine small-sample events; Europe PMC; one recorded query per event; hit counts
  32–1,934 [FACT: `main:research/studies/early_signal_5firms/THIRD_SOURCE_CROSSWALK.md:5-15`].
- **Core result.** 4 `SUPPORTED_BEFORE` / 5 `AFTER_CLEARANCE`; distance classes: **only one NEAR hit**
  (LT-07, Philips respiratory, 76 days before, *PLoS ONE* low-cost ventilator); **three DISTANT**
  matches at 6.7 / 14.5 / 23.3 years; five only after clearance
  [FACT: `main:research/studies/early_signal_5firms/THIRD_SOURCE_CROSSWALK.md:3-15`;
  `STUDY_DECISIONS.md:459-464`].
- **Verdict.** No GO/NO-GO; the frozen summary is: **"the third-source check does not corroborate a
  programme-level early signal; it produces one plausible near-term prior publication and three
  decade-old matches"** [FACT: PR #8 body; `STUDY_DECISIONS.md:477-485`].
- **Limitations.** `NO_RECORD` is a null search, not absence; keyword+affiliation matches work from any
  era; disclosed deviation (keywords from track list, not packet crosswalk)
  [FACT: `STUDY_DECISIONS.md:466-485`].
- **Reproduce.** `python experiments/b095/europepmc_crosscheck.py`
  [FACT: PR #8 body].
- **Independent verification.** 15 unit tests + frozen protocol; no external verification
  [FACT: PR #8 body].
- **Public claim?** **No** — one near-term hit in n=9 is not corroboration.

### 2.6 Agent pre-adjudication (PR #9, merged)

- **Goal.** Owner-instructed adjudication of all 69 packets **without** breaking the human-only labelling
  rule.
- **Design.** Third tier `AGENT_PRE_ADJUDICATION` with deterministic `agent_rubric_v1`; separate field
  `agent_preliminary_label`; `human_review_status` and `final_label` untouched
  [FACT: `main:research/studies/early_signal_5firms/ADJUDICATION_AMENDMENT_002.md`; S-030 at
  `STUDY_DECISIONS.md:489-504`].
- **Core result (corrected run).** `Uncertain 45`, `Routine Iteration 18`, `Not Assessable 6`,
  `False Signal 0`, **`Confirmed Shift 0`**. The **first run was wrong** (scored regulatory packets by
  searching trial text) and is recorded, not hidden [FACT: `STUDY_DECISIONS.md:506-536`].
- **Verdict.** No GO/NO-GO; the artifact states the labels are **"not usable as ground truth"** and
  **"not usable to score the study's detectors"**
  [FACT: `main:research/studies/early_signal_5firms/ADJUDICATION_AGENT_V1.md`; `STUDY_DECISIONS.md:497-501`].
- **Limitations.** Circularity risk; deterministic rubric ≠ human judgement; `Confirmed Shift = 0`
  means exactly that.
- **Reproduce.** `python experiments/b096/adjudicate_packets.py` [FACT: `STUDY_DECISIONS.md:492`].
- **Independent verification.** 19 tests; no independent review.
- **Public claim?** **No.** Must never be cited as validation of the study's detectors.

### 2.7 Human review workbench (PR #10, #11, merged)

- **Goal.** Make human adjudication cheap and un-fakeable, without producing labels.
- **Design.** 69-row CSV/XLSX with evidence pre-filled; five empty human columns; drop-down restricted to
  the five frozen labels; ingester refuses incomplete/invalid submissions; dry-run writes nothing
  [FACT: `main:research/studies/early_signal_5firms/REVIEW_GUIDE.md`; S-032/S-033 at
  `STUDY_DECISIONS.md:540-589`].
- **Core result.** Guard rails verified: full worksheet exit 0; missing reviewer exit 2; `Confirmed
  Shift` without independent confirmation exit 2 (14 problems); out-of-vocabulary label exit 2; no
  output file on dry run [FACT: `STUDY_DECISIONS.md:578-589`].
- **Verdict.** No scientific verdict; **no label exists**. "Target B still requires a named human"
  [FACT: `STUDY_DECISIONS.md:536`].
- **Limitations.** Tooling only. A validator cannot make a reviewer correct.
- **Reproduce.** `python experiments/b098/verify_review_path.py`
  [FACT: `STUDY_DECISIONS.md:570`].
- **Independent verification.** Five refusal cases verified end-to-end; nothing else.
- **Public claim?** **No** — and note the AI review (#18) explicitly did **not** run the ingester, so
  the worksheet remains empty [FACT: `research/ai-evidence-review:research/studies/early_signal_5firms/ai_review/AI_REVIEW_SUMMARY.md:9-14`].

### 2.8 Papers and claim maps (merged, on `main`)

- **Goal.** Publish the programme's retractions, measurement rules and the one confirmed decision rule
  with machine-checked claims.
- **Design.** `PAPER_v1` (results), `PAPER_METHODS_v1` (nine rules tied to failures), `PAPER_NEGATIVE_v1`
  (the five-firm negative); `CLAIMS.json` / `CLAIMS_METHODS.json` / `CLAIMS_NEGATIVE.json` with
  exact-substring verification both directions.
- **Core result.**
  - Five retractions documented, each with the control that destroyed it
    [FACT: `main:papers/PAPER_v1.md:195-218`].
  - **One confirmed decision rule**: a two-month post-alert window promotes an alert at balanced
    accuracy **0.584** (95% CI 0.556–0.607) and sustained-change precision **0.914** (0.892–0.934) vs a
    **0.696** base rate; replicated at legal-entity unit (**0.594 / 0.917** vs 0.705) and a hiring
    domain (**0.593 / 0.929** vs 0.794); ramp class **not** recovered (recall 0.142)
    [FACT: `main:papers/PAPER_v1.md:291-334`].
  - Density scaling: first controlled test **failed its pre-registered bar** (monotonicity broke by
    0.018); revised criterion confirmed on fresh draws (0.444 vs 0.204, ratio 2.18×) —
    **post-failure confirmation** [FACT: `main:papers/PAPER_v1.md:344-356`].
- **Verdict.** No GO/NO-GO; the paper's own closing ratio is **"five retractions to one confirmed
  rule"** [FACT: `main:papers/PAPER_v1.md:431-434`]. Claims verified 88/88
  (`main:research/AUDIT.json:86`), methods 22/22, negative 24/24.
- **Limitations.** Post-discovery confirmation (cell reuse); only one independent non-registry domain;
  not transferable to other countries/taxonomies/resolutions.
- **Reproduce.** `python papers/verify_claims.py`, `python papers/verify_figures.py`,
  `python papers/check_layout.py` [FACT: `main:papers/PAPER_v1.md:468-477`].
- **Independent verification.** Machine claim maps, not peer review. **No external scientist has signed
  any paper** [FACT: absence of any such record; `papers/README.md` indexes drafts].
- **Public claim?** **Partially yes, strictly scoped:** the promotion rule's measured precision may be
  quoted **with** its caveats (post-discovery, one corpus, no ramp distinction, requires human sign-off).
  Nothing else.

### 2.9 AI evidence review (PR #18, branch)

- **Goal.** First-pass, source-checked review of the 69 packets without pretending to be human truth.
- **Design.** Live re-query of all 60 candidate FDA records + 9 later clearances + 9 trials + 9
  third-source PMIDs; two model reviewers (Lead `deepseek-flash` + separate `kimi` session) and one
  adjudicator; frozen five-label vocabulary; `AI_ADJUDICATED`/`AI_UNRESOLVED`.
- **Data / scale.** 69 packets; 69/69 verified record references; 60/60 FDA records matched live;
  9/9 trials verified [FACT: `research/ai-evidence-review:.../AI_REVIEW_SUMMARY.md:51-54`].
- **Core result.** Labels: `Routine Iteration 48`, `False Signal 14`, `Uncertain 4`,
  `Insufficient Observation 3`, **`Confirmed Shift 0`**; 62 adjudicated, 7 unresolved
  [FACT: `.../AI_REVIEW_SUMMARY.md:75-92`]. Five findings: 6/60 "events" are PMA process supplements;
  **8/9 lead pairs join different devices**; one "first use" is an entity-resolution artefact
  (Given Imaging); the interesting technologies are one-off clearances; the candidate rule selects
  timing, not substance [FACT: `.../AI_REVIEW_SUMMARY.md:94-148`].
- **Verdict.** No GO/NO-GO. The document's own boundary: **"It is not human adjudication, not expert
  truth, and not a gold-standard label set. It may not be used as ground truth or to score the study's
  own detectors"** [FACT: `.../AI_REVIEW_SUMMARY.md:9-14`].
- **Limitations.** Two models, **not two experts**; Reviewer A and adjudicator are the same session;
  identity checked by the study's own alias rule; only 14/60 packets got independent source search
  [FACT: `.../AI_REVIEW_SUMMARY.md:185-203`].
- **Reproduce.** `python research/studies/early_signal_5firms/ai_review/verify_ai_review.py`
  [FACT: `.../AI_REVIEW_SUMMARY.md:206-208`].
- **Independent verification.** Structural validator only; reviewer B is a different model family but not
  an independent expert.
- **Public claim?** **No.** Usable only as a triage document; must not be called "AI-confirmed evidence".

### 2.10 Local LLM foundation — Phase 2 (PR #19, branch)

- **Goal.** First real local GPU run of event extraction on real documents; can a 4B model beat rules,
  and is formal training possible?
- **Design.** Arm A rules vs arm B Qwen3-4B-Instruct (NF4) on the **same 19 real documents**, same
  validator, same closed roster; frozen corpus with content hashes; QLoRA pipeline technical smoke only.
- **Data / scale.** 19 documents (510(k)/PMA/recall/trial) covering five firms; model revision pinned and
  13/13 files re-hashed [FACT: `research/local-llm-foundation:.../docs/PHASE2_SUMMARY.zh-CN.md:14-38`].
- **Core result.** JSON valid 19/19 both; verbatim quote located **5/19 rules vs 19/19 model**; events
  5 vs 20; abstentions 14 vs 0; validation accepted 18/1 vs 12/7; median latency 0.010 s vs 25.90 s;
  peak VRAM 5,020 MiB. Silver-label agreement is **exploratory, not accuracy**: company 5/19 vs 19/19,
  category 2/19 vs 17/19, date 1/19 vs 17/19
  [FACT: `research/local-llm-foundation:.../docs/PHASE2_SUMMARY.zh-CN.md:26-58`].
- **Verdict (quote).** **"`RESEARCH_TRAINING_BLOCKED`：正式 QLoRA 科研微调没有启动"**; prediction /
  early-signal evaluation **`NOT_RUN`**
  [FACT: `research/local-llm-foundation:.../docs/PHASE2_SUMMARY.zh-CN.md:91-97`, `:21-22`].
- **Limitations.** No human labels (0); validation splits cannot exist without labels; 89.5% is
  agreement with a source-derived silver label, measuring read fidelity not extraction accuracy;
  2,000× latency [FACT: `.../PHASE2_SUMMARY.zh-CN.md:55-59`, `:93-99`].
- **Reproduce.** `run_real_document_experiment.py --weights-path … --max-new-tokens 512`; GPU
  verification via real tensor computation [FACT: `.../PHASE2_SUMMARY.zh-CN.md:126-145`].
- **Independent verification.** Independent audit of Phase-1 code found 26 issues / 2 blockers; 12 were
  fixed [FACT: `.../PHASE2_SUMMARY.zh-CN.md:14`]. The Phase-2 numbers themselves are self-reported.
- **Public claim?** **No.** "The model extracts better than rules" is not supported; the correct
  statement is about format compliance and quote locatability on 19 structured documents.

### 2.11 S-030 overnight QLoRA (PR #20, branch)

- **Goal.** Complete overnight exploratory run: fix Phase-2 defects → frozen corpus → silver dataset →
  real QLoRA → four-arm evaluation → ablation.
- **Design.** 104 public regulatory documents (openFDA 510(k)/PMA/recall + ClinicalTrials.gov), 12
  companies, 3 negative controls; split 70/14/20 by **near-duplicate connected components**; QLoRA
  r=16, 60 optimisation steps / 1200 s.
- **Core result.** Arm A0 rules, A1 rules+locale date, B base Qwen3-4B, C exploratory QLoRA:
  schema 1.000 / 1.000 / 0.650 / 0.850; category agreement 0.471 / 0.471 / 0.706 / **1.000**;
  negative-control false-positive rate 0.000 / 0.000 / 0.000 / **0.667**
  [FACT: `research/overnight-qlora-s030:OVERNIGHT_RESEARCH_REPORT.zh-CN.md:115-120`].
- **Verdict (quote).** Grading block: labels `SOURCE_DERIVED_SILVER`; training
  **`EXPLORATORY_WEAK_SUPERVISION`**; formal research training **`RESEARCH_TRAINING_BLOCKED`（本次未解除）**;
  Precision/Recall/F1 **`NOT_EVALUABLE`** [FACT: `.../OVERNIGHT_RESEARCH_REPORT.zh-CN.md:7-18`].
- **Limitations.** 60 steps ≈ 0.86 epoch; 100% agreement is template-to-JSON mapping; negative-control
  false positives rose from 0 to 0.667 because the training set had no abstention examples; prompt
  v1→v2 **did not improve** the un-tuned model (0.765 vs 0.706) — recorded as a negative result;
  adapter and training record were lost to a crash and **reconstructed** (fields marked
  measured/derived/unrecoverable) [FACT: `.../OVERNIGHT_RESEARCH_REPORT.zh-CN.md:83-91`, `:126-152`].
- **Reproduce.** `run_overnight_experiment.py --adapter-path … --run-id replay --splits test`
  [FACT: `.../OVERNIGHT_RESEARCH_REPORT.zh-CN.md:310-315`].
- **Independent verification.** None external. The run found and fixed 5 of its own defects.
- **Public claim?** **No.** Any "fine-tuning works" claim is contradicted by the negative-control
  regression in the same table.

### 2.12 Innovation Signals Observatory / Phase 4 hiring (PR #21, branch)

- **Goal.** Can publicly observable technical hiring provide credible, traceable early evidence of an
  emerging R&D direction?
- **Design.** Five firms' official careers sites; append-only observation store with identity/version
  semantics; deterministic function+track classifier (arm A) and local 4B extraction (arm B);
  independent-evidence linking with explicit failure.
- **Data / scale.** Medtronic full population 994 postings; GE HealthCare / Philips / Dräger / Mindray
  bounded 80-posting samples; site denominators 1,035 / 805 / 171 / 141; single snapshot T0
  (source dates 2025-11-07…2026-11-04) [FACT:
  `research/innovation-signals-observatory:PHASE4_RESEARCH_REPORT.zh-CN.md:50-63`, `:101-103`].
- **Core result.** 5/5 firms `VERIFIED`; 61/994 postings (6.1%) classified into an existing track;
  8 candidate signals; 7 independently supported, 1 no support, 2 unknown — **but** Medtronic has
  events in 23/38 tracks, so same-firm+same-track verification is nearly automatic; **0**
  `NEW_DIRECTION_CANDIDATE`; **no unit recommended for escalation**
  [FACT: `.../PHASE4_RESEARCH_REPORT.zh-CN.md:78-93`].
- **Verdict.** No GO/NO-GO. The report's own sentence: **"能作为「观察层」的数据源…但现在还不能作为
  「信号层」的数据源"** and **"「招聘信号是否领先技术突破」这个问题今天仍然无法回答"**
  [FACT: `.../PHASE4_RESEARCH_REPORT.zh-CN.md:12-16`, `:97-98`].
- **Limitations.** Single snapshot (stock, not flow); classifier non-transfer (surgical_robotics: 80
  mentions, 0 classified); no human gold standard → no P/R/F1; evidence library window only
  2024-10…2026-10 [FACT: `.../PHASE4_RESEARCH_REPORT.zh-CN.md:99-110`, `:195-210`].
- **Reproduce.** Offline tests and `scripts/collect_recruitment*.py`; not a single command in the
  report [FACT: `.../PHASE4_RESEARCH_REPORT.zh-CN.md:140-149`; **[UNVERIFIED]** exact command list].
- **Independent verification.** Offline tests only; no independent replication.
- **Public claim?** **No** — "we observe hiring" is supportable; "hiring is an early signal" is not.

### 2.13 S-031 hiring capability study (PR #22, branch)

- **Goal.** How far can a public job ad be read as evidence of a technical capability requirement,
  without turning sales/product context into an R&D claim?
- **Design.** Audit-first: 100 difficult stratified postings (20/company) from the PR #21 corpus;
  four independent dimensions (Role Function, Technical Capability, Product/Business Context, R&D
  Evidence Strength); per-quote verbatim evidence; old-rule comparison; 34 rows flagged for human review.
- **Data / scale.** 100 postings from five firms; seed 31031; 3 `DETAIL_FAILED` retained unclassified;
  31 delivery files pinned by sha256 [FACT:
  `research/s031-hiring-capability-study:research/s031/deliverables/S031_RESEARCH_REPORT.zh-CN.md:19-36`;
  `S031_DELIVERY_MANIFEST.json`].
- **Core result.** AI preliminary distribution: direct R&D evidence 23, indirect 48, product-context
  only 23, non-R&D 3, insufficient 3. Old rule: 39 `UNCLASSIFIED`, 36 `SALES_ADMIN_OTHER`, **3
  `MAPPED`** — so the sample does **not** show the old rule mass-mapping sales to R&D
  [FACT: `.../S031_RESEARCH_REPORT.zh-CN.md:50-64`].
- **Verdict.** No GO/NO-GO. H1/H2/H3 are each labelled **"当前证据不足"**; the report states it
  **cannot** give H1 an effect size and **cannot** claim the four-dimension scheme is better
  [FACT: `.../S031_RESEARCH_REPORT.zh-CN.md:154-178`]. `S031_DISAGREEMENT_AUDIT.md` exists; no
  accuracy/P/R/F1 was computed anywhere [FACT: `.../S031_RESEARCH_REPORT.zh-CN.md:36`].
- **Limitations.** Stratified by function **by design**, not representative; one snapshot; no blind
  human reference standard; AI labels are preliminary, not truth
  [FACT: `.../S031_RESEARCH_REPORT.zh-CN.md:34-36`, `:212-220`].
- **Reproduce.** `python -m unittest discover -s research/s031/tests -v`; `python verifier/v2/verify.py`
  [FACT: PR #22 body; `research/s031/tests/test_s031.py` exists].
- **Independent verification.** Verifier v2 12/12 PASS; no independent scientist.
- **Public claim?** **No.** May describe the method and the 100-case audit; may not quote accuracy.

### 2.14 PHOENIX-001 round 1 (PR #23, branch)

- **Goal.** Audit 13 external projects, reproduce transferable methods, compare 20 methods on the same
  three holdout origins.
- **Design.** Read-only comparison over frozen artifacts; unified origins 2025-04-01 / 07-01 / 10-01;
  AP, P@K, R@K, false alarms, lead time, paired bootstrap, company/track stability; six source files
  SHA-256-pinned.
- **Core result.** H1 supported (pair persistence AP 0.7913 > base rates); **H9 refuted** (fusion
  0.7867 vs regulatory 0.7935; entry fusion 0.0979 vs 0.1163); H5/H6 blocked; H2/H3/H4/H7/H8/H10
  inconclusive [FACT: `research/phoenix-001-external-methods:docs/PHOENIX_SUMMARY.md:7-14`;
  `docs/PHOENIX_METHOD_COMPARISON.md:62-67`].
- **Verdict.** Explicit hypothesis verdict list: **"Supported：H1。Refuted（当前协议范围）：H9。
  Blocked：H5、H6。Inconclusive：H2、H3、H4、H7、H8、H10。"**
  [FACT: `research/phoenix-001-external-methods:docs/PHOENIX_METHOD_COMPARISON.md:62-67`].
- **Limitations.** No `data/medradar.sqlite` in the environment at run time; no re-fetch; 3,833
  material event rows are **not** independent devices; all results are **evidence class 3 (historical
  simulated prediction)**, not independent prospective validation
  [FACT: `.../PHOENIX_SUMMARY.md:27-31`, `:13`].
- **Reproduce.** `python3 experiments/phoenix_001/build_method_comparison.py`;
  `python3 experiments/phoenix_001/audit_assets.py`
  [FACT: `.../PHOENIX_METHOD_COMPARISON.md:69-73`].
- **Independent verification.** `verifier/v1` and `verifier/run_v2.py`; v2 appends every acceptance run
  [FACT: `.../PHOENIX_SUMMARY.md:51-64`]. **[UNVERIFIED]** whether those runs are green at the remote
  head; the PR body claims final acceptance.
- **Public claim?** **No.**

### 2.15 PHOENIX-001 round 2 (PR #24, branch)

- **Goal.** Add what round 1 lacked: a **frozen protocol written before any experiment ran**, a shared
  harness with a verified no-future-information test, ten pre-registered hypotheses with thresholds,
  and explicit negative results.
- **Design.** `phoenix-001/v1` frozen 2026-11-08; tasks T-CELL (67,084 rows) and T-TRACK (4,904 rows);
  three injected lag scenarios L000/L090/L180 (headline L090); walk-forward 2014–2025; baselines B0–B7;
  full metric set + cluster bootstrap + Holm; audits L1–L8.
- **Data / scale.** `data/medradar.sqlite`, 1,368,469,504 bytes, SHA-256
  `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92`, 375,378 events; 89 companies;
  59 tracks; 1,116 company×track units [FACT:
  `research/phoenix-001-round2:docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md:14-29`].
- **Core result.** Track-level: H3 **NOT SUPPORTED** (+0.0177 < 0.02, p=0.246); H6 **NOT SUPPORTED**
  (+0.0133, p=0.082; test-1 negative mean reversion); **H7 SUPPORTED** method-only (PELT +0.126
  [+0.052,+0.202], p=0.002 at matched FAR); **H8 SUPPORTED** modest (+0.0379 [+0.0115,+0.0618],
  p=0.004 — later refuted by #25); H9 **NOT SUPPORTED** (Δ −0.0050, p=0.628; fusion/single ratio
  0.966) [FACT: `research/phoenix-001-round2:docs/phoenix/EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md:393-401`].
- **Verdict (quote).** Same table: **"H3 … NOT SUPPORTED"**, **"H6 … NOT SUPPORTED"**, **"H7 …
  SUPPORTED (conditional on matched FA budget)"**, **"H8 … SUPPORTED (modest)"**, **"H9 … NOT
  SUPPORTED (no material gain)"** [FACT: `.../EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md:397-401`].
- **Limitations.** Walk-forward evaluable subset only 2,443 rows / 155 positives; 11 of 12 folds
  evaluable; no result is class **P** (prospective); single snapshot; no patents; class S maximum
  [FACT: `.../EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md:21-42`, `:411-427`].
- **Reproduce.** Six commands under `experiments/phoenix/hypotheses/track/`, ~268 s, fixed seed
  20261108 [FACT: `.../EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md:45-65`].
- **Independent verification.** 17/17 self-tests; leakage audit L1–L8; no external replication.
- **Public claim?** **No** — and H8 must never be quoted from this PR without #25's NO-GO.

### 2.16 PHOENIX-002 H8 re-validation (PR #25, branch)

- **Goal.** Try as hard as possible to **disprove** PHOENIX-001's only surviving predictive finding (H8).
- **Design.** `phoenix-002/v1` frozen before results; three independent methodological audits (label
  maturity, risk set, target-definition/mathematical coupling); corrected main configuration `attr38`
  (drop 21 structurally impossible `t_*` tracks) + Y1 target + L090 + 6-quarter purge; 8 arms on
  identical rows; pre-registered gates G1–G7.
- **Data / scale.** 1,723 evaluable rows / 176 positives / 10.21% / 38 tracks; sample reconciliation
  against v1's 2,443 / 155 / 6.34% documented
  [FACT: `research/phoenix-002-h8-validation:docs/phoenix/PHOENIX_002_H8_RESULTS.md:24-44`].
- **Core result.** ΔAP **+0.0294** [+0.0082,+0.0573] **< τ = 0.03**; cross-construct **+0.0123**
  [−0.0788,+0.1107]; within-track time-shuffle placebo **p = 0.0846**; after de-duplication **+0.0048**
  [−0.0221,+0.0347], p=0.508; simple trend model M3 AP 0.1766 **>** H8 0.1589; pure-noise control gives
  mean ΔAP +0.0373 (negative binomial), 40/40 universes positive; independent verifier's own null
  +0.0469 sd 0.0240 places observed +0.0294 at the 25th percentile (upper-tail p=0.76)
  [FACT: `.../PHOENIX_002_H8_RESULTS.md:13-17`, `:160-227`].
- **Verdict (quote, from `verdict.json`).** `"verdict": "NO-GO"`, reason
  **"point estimate is positive but below the pre-registered practical threshold tau=0.03"**; gates
  `G1_primary_dap_ge_tau:false`, `G3_placebo_p_lt_0.05:false`
  [FACT: `research/phoenix-002-h8-validation:experiments/phoenix/h8_validation_v2/results/verdict.json:2-13`;
  prose at `.../PHOENIX_002_CONCLUSION_AND_NEXT_STEPS.md:11-32`].
- **Limitations.** CI both excludes 0 and straddles τ → cannot claim "no association"; cannot claim
  "effect at τ"; single snapshot; taxonomy back-projected; 38 clusters / 176 positives still thin;
  Q1-only non-overlapping sensitivity +0.0160 [−0.0167,+0.0551], p=0.356
  [FACT: `.../PHOENIX_002_H8_RESULTS.md:240-263`].
- **Reproduce.** `python experiments/phoenix/h8_validation_v2/run_phoenix002.py`
  [FACT: `.../PHOENIX_002_H8_RESULTS.md:5`, `:281-291`].
- **Independent verification.** Separate verifier under `verify/` re-used only OOF CSVs; 40 self-tests;
  audit C's null simulation independently implemented [FACT: `.../PHOENIX_002_H8_RESULTS.md:220-227`,
  `:290`].
- **Public claim?** **No.** The only public sentence allowed is the NO-GO wording itself.

### 2.17 PHOENIX-003 early evidence (PR #26, branch)

- **Goal.** Before a device firm reaches an important regulatory milestone, does an independent public
  source already describe the related technical activity — how early, how reliably, and could an
  observer have identified it without knowing the future?
- **Design.** Frozen protocol + reusable **anchor-and-control battery**: canonical milestone identity
  (177,948 from 233,838 raw rows; 0 repeated official identifiers), brand-lineage attribution
  (12,230 milestones / 13 firms; 93.1% of applicants left `UNKNOWN` rather than imputed), first-in-code
  sampling frame (269 anchors), keyword baseline, matched decoy, time placebo, pre-regulatory split,
  literature-rarity filter.
- **Data / scale.** 269 anchors (59 core + 210 extension), 2015–2024, 249 product codes; 177,948
  canonical milestones; 5,760 verified rows; 28 strict cases
  [FACT: `research/phoenix-003-early-evidence:docs/phoenix003/SCIENTIFIC_CONCLUSION.md:12-55`].
- **Core result.** C1 naive keyword baseline links **99.2%** with median apparent lead **1,821 d**;
  C2 anchored **69.9%**, median **1,620 d**; C3 matched decoy **51.4%** → specificity **1.37**; C4 time
  placebo **p = 0.51 / 0.53** and **0.72 / 0.88**; **92.3%** of verified links are follow-up study of
  already-regulated products; only **28** milestones are simultaneously product-specific,
  literature-rare, verifiable and pre-regulatory [FACT:
  `.../SCIENTIFIC_CONCLUSION.md:32-55`].
- **Verdict (quote).** **`NO-GO`**; gate values: `specificity 1.3672` vs threshold 5.0 (GO) / 3.0
  (LIMITED_GO), `placebo_p 0.881059` vs 0.05 / 0.10 — both fail, "not close on either gate"
  [FACT: `research/phoenix-003-early-evidence:experiments/phoenix003/results/verdict.json:17-129`;
  PR #26 body; `docs/phoenix003/SCIENTIFIC_CONCLUSION.md:121-131`].
- **Limitations.** Single 2026-10-30 snapshot; token identity ≠ semantic identity; non-US pathways
  absent; 93% of firms `UNKNOWN`; no human adjudication of the 28 cases
  [FACT: `.../SCIENTIFIC_CONCLUSION.md:83-104`].
- **Reproduce.** `python experiments/phoenix003/code/run_pipeline.py`
  [FACT: `.../SCIENTIFIC_CONCLUSION.md:7`; `experiments/phoenix003/README.md`].
- **Independent verification.** `docs/phoenix003/INDEPENDENT_VERIFICATION.md` exists (38,626 bytes);
  **its content was not audited by this registrar — [UNVERIFIED] whether it is independent-in-fact**.
- **Public claim?** **No** — except the methodological instrument and the bounded 28-case library,
  both explicitly labelled non-statistical.

### 2.18 DATA-EXPANSION-001 (PR #27, branch)

- **Goal.** Discover, verify and measure the scientific increment of new global data sources.
- **Design.** 59-source registry; live access verification; External Evidence Schema; pre-registered
  EXP-A (coverage), EXP-B (association accuracy with decoys/irrelevant controls), EXP-C (lead time with
  date-shift placebo), plus C3 (non-FDA regulatory footprint).
- **Data / scale.** 59 sources investigated / 31 verified without registration or payment; 349 requests,
  **105 failures all retained**; 688 deduplicated evidence records; 38 frozen regulatory anchors
  (2017–2024), 16 requests [FACT:
  `research/data-expansion-001:research/data_expansion/SOURCE_INCREMENT_EXPERIMENT.md:22-46`.
- **Core result.**
  - EXP-A: Crossref 81.6%, OpenAlex 76.3%, USAspending 36.8%, Europe PMC 34.2%, CT.gov 26.3%;
    NIH RePORTER 0% (real finding), Semantic Scholar 2.6% (rate-limited). Cross-source duplicate rate
    for one DOI **75%** [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:51-78`].
  - EXP-B: **no association strategy usable** for confirmation-grade linking. `name_only` covers 84.2%
    with 0.3% false-link rate but **cannot confirm the firm**; requiring firm confirmation drops
    coverage to 18.4% and rejects 78.1% — "they are exact because they link almost nothing"
    [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:86-117`].
  - EXP-C: T1 median lead **2,508 d** vs date-shift placebo **2,593.5 d**, **p = 0.569** →
    **`NO_DETECTABLE_LEAD`** [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:121-143`].
  - C3: 11/30 Canadian earlier licences but only **2 strict matches**; 9 are brand-word collisions
    [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:147-179`].
- **Verdict (quote).** **`NO_DETECTABLE_LEAD`**; **"可用于确认级关联的策略：无。"**
  [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:17`, `:98`]. No overall GO/NO-GO is issued; the
  executive summary's own conclusion is **"提前量信号仍未出现"**
  [FACT: `research/data-expansion-001:research/data_expansion/EXECUTIVE_SUMMARY_ZH.md:63-67`].
- **Limitations.** No human labels → no overall P/R/F1; anchor set is survivor-biased (all products
  eventually approved); T1 n=29 below floor; MDALL is a current snapshot, not proof of past public
  visibility [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:134-143`, `:175-179`].
- **Reproduce.** `python research/data_expansion/experiments/run_experiments.py`
  [FACT: `.../SOURCE_INCREMENT_EXPERIMENT.md:5`].
- **Independent verification.** 174 offline tests; registry "0 validation problems"; **no independent
  replication** of EXP-A/B/C [FACT: PR #27 body].
- **Public claim?** **No** for lead time; the **source-access facts** (31 verified sources, licence
  matrix) are publishable as engineering, not science.

### 2.19 ATLAS-001 (PR #28, branch)

- **Goal.** Build the identity/evidence/graph substrate without which "cross-source signal" cannot be
  distinguished from a name collision.
- **Design.** ATLAS-ID (company/manufacturer/device/identifier; name similarity may only create
  candidates), ATLAS-EVIDENCE (four clocks, source + normalised hashes, append-only versions),
  ATLAS-DB (versioned migrations, backups), ATLAS-GRAPH (7 queries), ATLAS-RESEARCH (`as_of()` with
  observed / public-inferred / unprovable), 9 quality checks.
- **Data / scale.** openFDA UDI 508 unique US records; MDALL full table 1,673,926 rows (219,970,233 B),
  5,512 normalise to 14-digit DI, 5,005 unique; bridge 1,200 GTIN candidates → 942 resolved → **934
  paired devices**; relation census 934 identity + 192 family + 2 model + 59 possible + 10 related +
  1,087 unrelated [FACT: `foundation/atlas-001:docs/atlas/RESEARCH_VALIDATION.md:24-32`, `:65-80`].
- **Core result.** ATLAS identity precision **1.000**, recall **1.000** on the sampled pairs — but the
  method **is** the label (DI equality) → **"a consistency check, not a discovery"**; name-similarity
  baseline recovers **0/934** because MDALL publishes a number, not a label
  [FACT: `.../RESEARCH_VALIDATION.md:38-61`].
- **Verdict.** No GO/NO-GO. Explicit non-establishment list: no global precision/recall, 934 is a lower
  bound, candidates unvalidated, **no future-event prediction** — "PHOENIX's negative results remain the
  record on that question" [FACT: `.../RESEARCH_VALIDATION.md:110-121`].
- **Limitations.** Sampled pairs, not prevalence-weighted; placeholders previously produced 33 false
  positives (all were `brand_name="NA"`); time leakage separated but bases overlap
  [FACT: `.../RESEARCH_VALIDATION.md:84-93`].
- **Reproduce.** `python tools/run_atlas_pipeline.py`; `python tools/verify_atlas.py`
  [FACT: `.../RESEARCH_VALIDATION.md:124-134`].
- **Independent verification.** `tools/verify_atlas.py` 16/16 self-checks; **CONVERGENCE's independent
  verifier re-derived the 934 from raw SQLite and it survived every test** (V3, 19/22 PASS, 1 FAIL on a
  documentation count, 2 UNVERIFIABLE) [FACT:
  `integration/convergence-001:docs/convergence/INDEPENDENT_VERIFICATION.md:185-232`].
- **Public claim?** **No** predictive claim; the 934-pair bridge is publishable as an **identity
  measurement** with its 0.329% coverage limit.

### 2.20 HORIZON-001 (PR #29, branch)

- **Goal.** Global data frontier: find keyless patent channels, export real evidence, and run three
  pre-registered experiments on increment, identity and time quality.
- **Design.** EXP-H1 (independent coverage / dedup), EXP-H2 (cross-national product identity, selection
  rule frozen before pairs examined), EXP-H3 (fitness for historical time research), EXP-H4 (industry).
- **Data / scale.** 10 weekly EPO sitemaps → 37,989 publications, 3,093 medtech (8.14%), 228 front
  pages fetched, 197 independent technical disclosures; CIPO 337 MB, 13.21M party rows, 19,702 target
  patents; 60 DOIs × 6 databases = 308 rows → **60 distinct works (dedup ratio 0.195)**; GUDID 320 ×
  MDALL 174; 24-source export 6,492 records / 20,335,003 bytes
  [FACT: `research/horizon-001:research/horizon/EXPERIMENT_RESULTS.md:17-98`;
  `integration/convergence-001:docs/convergence/INDEPENDENT_VERIFICATION.md:74-90`].
- **Core result.**
  - H1: patent gap filled with no key; naive union across six scholarly databases over-counts ≈**5.1×**
    [FACT: `.../EXPERIMENT_RESULTS.md:74-98`].
  - H2: HORIZON's **prose** reports 712 pairs / 387 REJECTED / 325 UNKNOWN; the independent verifier
    recomputed **726 pairs, UNKNOWN 726, REJECTED 0, CONFIRMED 0**, and found the prose wrong in 8 of
    9 numbers (the machine artifact agrees with the verifier, not with the prose)
    [FACT: `.../EXPERIMENT_RESULTS.md:104-137`;
    `integration/convergence-001:docs/convergence/INDEPENDENT_VERIFICATION.md:135-181`].
  - H3: **60.0%** of anchors have ≥2 databases disagreeing on publication date; **36.7%** differ by
    >30 days; PubMed/Semantic Scholar/OpenAIRE expose no creation timestamp
    [FACT: `.../EXPERIMENT_RESULTS.md:189-245`].
- **Verdict.** No GO/NO-GO. HORIZON's own text says patent "gap filled", identity **0 CONFIRMED**, and
  time quality mixed [FACT: `research/horizon-001:research/horizon/EXPERIMENT_RESULTS.md`]. The
  CONVERGENCE verifier's V2 verdict is **"FAIL — prose contradicts the pair file"** and V5
  **"FAIL — two of the four clocks are not clocks"**
  [FACT: `integration/convergence-001:docs/convergence/INDEPENDENT_VERIFICATION.md:41-46`].
- **Limitations.** Single snapshot; no historical versions; patent records `SNAPSHOT_ONLY`; EXP-H2
  cannot speak to identity beyond the sampled pairs; no predictive claim is made anywhere.
- **Reproduce.** Offline from committed samples: `measure_patents.py`, `analyze_exp_h1.py`,
  `analyze_exp_h3.py` [FACT: `.../EXPERIMENT_RESULTS.md:286-292`].
- **Independent verification.** CONVERGENCE V1–V5: export bytes/hashes PASS 17/18; EXP-H2 counts FAIL;
  time semantics FAIL. **The machine artifacts pass; the HORIZON prose does not.**
- **Public claim?** **No** for identity or time; the **keyless patent-access method** and the
  **date-disagreement measurement** are publishable as data-engineering/findings with caveats.

### 2.21 CONVERGENCE-001 (PR #30, branch)

- **Goal.** Connect ATLAS and HORIZON into one runnable, reproducible, auditable pipeline; reconcile
  P0 contradictions; enforce a licence gate.
- **Design.** Selective import (ATLAS 70/70 files; HORIZON 661/691, excluding 30 UN Comtrade paths);
  export verification → licence gate → conversion → isolated ATLAS evidence DB → cross-source relations
  → six research queries; independent verifier importing none of the application code.
- **Data / scale.** 23 sources / 5,884 records / 20,335,003 bytes; integration DB 60.98 MB; 672 official
  identifier relations + 2,101 firm attributions; 134 cited query items, 0 uncited
  [FACT: `integration/convergence-001:docs/convergence/EXECUTIVE_SUMMARY_ZH.md:23-48`;
  `.../INDEPENDENT_VERIFICATION.md:74-90`].
- **Core result.** End-to-end flow works: 5,884 converted, **0 rejected, 0 fields silently dropped**;
  23 sources SHA-256 verified, 1 quarantined by licence, 0 mismatches. P0 fixes: EXP-H2 prose corrected
  (official 726/0/0/726; 712/387/325 was an earlier unrecoverable run); **934 vs 0 reconciled as a
  sampling-coverage issue, not a conflict**; restricted data payloads and derived figures removed;
  62 duplicate rows retained as versions
  [FACT: `.../EXECUTIVE_SUMMARY_ZH.md:52-117`].
- **Verdict.** No scientific GO/NO-GO. The independent verifier's verdict is
  **`PASS 81  FAIL 10  UNVERIFIABLE 4`**, with 8 distinct defects: V2 HORIZON prose numbers, V5 time
  semantics, V1 non-unique `source_record_id` (62 extra rows), V3 one documentation count, V7 record
  identity [FACT: `.../INDEPENDENT_VERIFICATION.md:14-49`].
- **Limitations.** Only 5,884 records; no prediction; historical observation clock starts 2026-11-09, so
  **"observable as of 2020-01-01 = 0"** — any "we predicted in 2020" claim is fabrication
  [FACT: `.../EXECUTIVE_SUMMARY_ZH.md:153`].
- **Reproduce.** `tools/convergence/verify/verify.py` (stdlib, `--json`, exit 1 on FAIL); two runs
  byte-identical [FACT: `.../INDEPENDENT_VERIFICATION.md:7-13`].
- **Independent verification.** Genuinely independent: no application imports, re-implemented hashes and
  identifiers, no network, read-only originals. **This is the strongest verification artifact in the
  repository** — and it still reports 10 FAILs.
- **Public claim?** **No.** "End-to-end integration works" is an engineering statement with defects
  attached; nothing predictive.

### 2.22 S-028 temporal graph early-signal (PR #15, branch)

- **Goal.** After controlling for a firm's own filing history, the track's history and common time
  trends, does the historical structure of a company–technology network add out-of-sample information
  about a firm's first observed qualifying regulatory activity in the next 2 / 4 quarters?
- **Design.** Pre-registered `HYPOTHESIS_REGISTRY` + freeze hashes; 51 companies × 38 tracks bipartite
  graph; 12 graph features added to a strong 16-feature non-graph baseline B2; paired AP differences
  with company- and pair-clustered bootstrap; degree-preserving randomisation control; ablations;
  HistGB robustness; stopping rule that forbids GNN if H1 fails.
- **Data / scale.** 3,833 material events with both company and track = **12.1%** of the 31,802-event
  lane; 303–322 observed pairs; 12-month snapshots only 135–148 edges; H=4q holdout 67 positives;
  pooled rows 5,159 (but only 1,729 distinct pairs) [FACT:
  `research/s028-temporal-graph-early-signal:research/studies/graph_early_signal_s028/LIMITATIONS.md:19-38`,
  `:88-103`; `.../GRAPH_RESULTS.md:36-54`].
- **Preregistration / freeze.** `PRE_REGISTRATION.md` + `prereg_freeze.json`
  (sha256 `d2f543cd…`) + Amendment 1 (`prereg_freeze_amendment1.json`, sha256 `29a8c1c6…`). Freeze
  chain verifies for `PRE_REGISTRATION.md`, but **`HYPOTHESIS_REGISTRY.md` matches neither freeze hash**
  — the results table was filled in after the freeze; reported as an unresolved provenance limitation
  [FACT: tip commit `4c6686f` body].
- **Core result.** H1: ΔAP **−0.00609** [−0.02219,+0.00450] company / [−0.03347,+0.01043] pair;
  0/3 windows exclude zero; all 6 ablations below B2; HistGB worse; graph features are largely
  restatements of history (two-hop reach / eigenvector R² 0.727 / 0.623 on non-graph features,
  Spearman 0.891 / 0.870) [FACT: `.../GRAPH_RESULTS.md:27-54`; tip-commit body].
- **Correction.** Independent methodological review found (a) the randomised null did **not** preserve
  degrees/weights/timing — **72/72 invariant failures**; (b) the **"well-powered" label was wrong** —
  the pre-registered conjunction's 80%-power MDE is **0.0374 AP**, power at 0.0194 is **16.3%**;
  (c) the **"Yale paper does not exist" claim was false** (Clayton & Coppola, NBER WP 35227);
  (d) the three holdout windows **overlap** (37 physical positives counted 75 times). Corrected nulls
  N1/N2 re-run 40 draws: H4q still 40/40 above real graph (**p=1/41**) but **only in the 2025-04-01
  window** (other windows 23/40, 31/40); H2q shows **no reversal** (16/40, 20/40) — the original 30/40
  was a defect artefact [FACT: tip-commit body; `.../GRAPH_RESULTS.md:109-121`;
  `.../CORRECTION_REPORT_ZH.md:13-19`].
- **Verdict (quote, seal decision).** **"S-028 可以正式封存为一项可信的探索性负结果——但前提是按本报告
  改写的措辞封存，而不是按原始措辞。"** and **"不能封存为「确证性结论」"**
  [FACT: `research/s028-temporal-graph-early-signal:research/studies/graph_early_signal_s028/CORRECTION_REPORT_ZH.md:15`,
  `:340`]. Status table: H1 `UNCHANGED_FINDING`; the "40/40 random graphs beat real" H2 method claim
  `INVALIDATED_FINDING`; corrected H4q tail `CORRECTED_RESULT`, **exploratory only**
  [FACT: `.../CORRECTION_REPORT_ZH.md:284-295`].
- **Limitations (selected, all measured).** Not point-in-time (`available_at = event_date + 14 d` for
  55,090/55,090 rows; `first_seen_at` has one value); graph on 12.1% of events; 84 events attributed to
  parents before acquisition; `bd` 44.11% of events from acquired aliases; left truncation 71.4% /
  9.90%; taxonomy back-projected; no company↔company edges; calibration uninformative at 1.0% base
  rate; no GNN run by stop rule; per-case review originally incomplete (later completed: 90 top false
  positives, all traceable) [FACT: `.../LIMITATIONS.md:9-135`; tip-commit body].
- **Reproduce.** `python research/studies/graph_early_signal_s028/code/run_all.py` (or per-step scripts;
  see `REPRODUCE.md`); seeds frozen [FACT: `.../REPRODUCE.md`].
- **Independent verification.** Correction round performed by an independent reviewer, re-hashing all
  50 HEAD-tracked S-028 files; **0 experimental artifacts changed**; 9 documents carry `CORRECTED`
  blocks preserving original wording [FACT: tip-commit body; `.../RANDOMISATION_DEFECT_ANALYSIS.md`].
  This is the **best self-correction record in the repository** — and it is not external peer review.
- **Public claim?** **No** — except the exploratory-negative wording itself. The "well-powered", "40/40
  randomisation", "disjoint holdout" and "Yale paper absent" statements are **forbidden**.

### 2.23 S-029 evidence-based temporal relations (PR #16, branch)

- **Goal.** Reconstruct evidence-based temporal relations of medical-technology development and decide
  whether the relation layer is good enough to feed a time-ordered prediction experiment.
- **Design.** Frozen `GO_NO_GO_CRITERIA.md` (sha256 `d1bb8339…`); six conditions T1–T6 with explicit
  thresholds and an **anti-relaxation clause**; Phase 0 search recall/source audit/ontology/entity
  history; Phase 1 real collection; Phase 2 quality metrics + network feasibility + human worksheet;
  independent verification script (12/12).
- **Data / scale.** **20,563 claims**, 3,418 record-level evidence rows, 158 kept rejects; 15,796
  deduplicated edges; 7,059 entities; 5,220 with verified stable identifiers; 5 firms; 45 references;
  102-row human worksheet with human fields empty [FACT:
  `research/s029-evidence-based-relations:research/studies/relation_network_s029/NETWORK_FEASIBILITY.md:23-39`;
  `.../NEGATIVE_FINDINGS.md:178-186`].
- **Core result.** T1 PASS, T2 PASS, T5 PASS (after documented amendment); **T3 FAIL** (fuzzy-only
  10.08% vs 10.0%), **T4 FAIL** (**0 of 20,563 claims has genuine point-in-time observation**; 60
  mislabelled `ACTUAL_OBSERVATION` claims were corrected), **T6 FAIL** (no human adjudication)
  [FACT: `.../artifacts/prereg_decision.json:2-15`; `.../NEGATIVE_FINDINGS.md:68-122`].
- **Verdict (quote).** **`"verdict": "NO-GO FOR PREDICTION"`**
  [FACT: `research/s029-evidence-based-relations:research/studies/relation_network_s029/artifacts/prereg_decision.json:14`;
  prose `.../NETWORK_FEASIBILITY.md:87-92`].
- **Limitations.** No cooperation claims at all (`COOPERATES_WITH` = 0 admissible rows); 32.56% of
  company relations are co-authorship stored with an explicit interpretation limit; Dräger ASCII query
  65.26% name collisions; Europe PMC affiliation retrievability breaks in 2014 (28%→97.1%); 38/770
  records are patents; 67.68% of evidence lost under canonical-name-only search
  [FACT: `.../NEGATIVE_FINDINGS.md:13-143`].
- **Reproduce.** `python research/studies/relation_network_s029/code/s029_12_verify_report.py`
  [FACT: `.../REPRODUCE.md`].
- **Independent verification.** An independent adversarial reviewer recomputed 24 numbers and found
  **9 unreproducible numbers and 5 ontology divergences**, all corrected before delivery; verdict
  unchanged. `artifacts/verification.json` records 12/12 checks.
- **Public claim?** **No.** The dataset may be described as reconstructable/traceable; it may **not** be
  called point-in-time, validated, or a collaboration network.

### 2.24 full-history-v1 (branch, no PR)

- **Goal.** Rebuild the entry panel over the full openFDA history (1976–2026) and test whether publicly
  observable regulatory-sequence signals rank future first clearances better than firm persistence.
- **Design.** Frozen pre-registration (`research/protocols/hist_v1_preregistration.md`, amendments
  A1–A5 logged before any fit); discrete-time entry-hazard target Y8/Y4; 15 point-in-time features;
  expanding-window origins 1995–2024; B0–B3 baselines; permutation null (200 draws); MDE.
- **Data / scale.** 53 companies × 38 tracks × 202 quarters; 528 observed pairs; **14,704 panel material
  events = 8.2% of 178,417**; 510(k) company linkage 13.4%; primary risk set `R_adj` 8,415 cells / 181
  positives; 30 origins [FACT: `research/full-history-v1:experiments/hist_v1/REPORT.md:32-80`].
- **Core result.** **H1 SUPPORTED marginally**: mean per-origin AP **0.1137 vs 0.0553** company base
  rate, Δ **+0.0584** [+0.0020,+0.1213], permutation **p = 0.030**; MDE 0.090 > observed 0.058; **not**
  better than the two-way exposure baseline B3 (Δ +0.0438 [−0.0184,+0.0957]); no added source helps
  (fusion −0.0053); 56–85 of 94 in-scope entries missed at every alert budget
  [FACT: `.../REPORT.md:11-18`, `:78-180`].
- **Verdict (quote).** **"H1 is supported, marginally"** and **"a candidate early-warning signal whose
  existence is now supported and whose practical value is not yet established"**
  [FACT: `research/full-history-v1:experiments/hist_v1/REPORT.md:3-18`, `:100-105`].
- **Limitations.** Curated roster, not industry; 55.1% of material events have no track; 86.1% no
  company; taxonomy back-projected; `R_adj` selected post hoc as primary risk set (pre-registered but
  narrow); h=4 bootstrap unreliable; no point-in-time data
  [FACT: `.../REPORT.md:44-63`, `:106-114`, `:117-124`].
- **Reproduce.** `python experiments/hist_v1/build_panel.py`; `python experiments/hist_v1/eval.py`;
  `python experiments/hist_v1/verify_report_numbers.py`
  [FACT: `.../REPORT.md:6`, `:32`].
- **Independent verification.** `verify_report_numbers.py` re-checks report numbers against artifacts;
  branch commit message claims an independent audit and two record repairs **[UNVERIFIED] by this
  registrar** (no independent artifact located and read).
- **Public claim?** **Not yet.** A marginal, curated-roster, single-corpus rank improvement is a
  candidate, not a validated early-warning system; it has no prospective test.

### 2.25 Repository consolidation (PR #17, branch) — governance, not a study

- **What it is.** README rewrite and research index; it documents the discrepancies (678 vs actual
  tests, AdCom parser returning zero meetings, 25 unmatured forecasts, single-annotator calibration)
  [FACT: `_evidence/repo_facts.json` PR #17 body]. It is **not** a research result and adds no evidence;
  it is relevant because it is the only merged-or-proposed document that states the programme's negative
  record on the front page. Not counted in the verdict tally.

---

## 3. Verdict summary

### 3.1 Explicit NO-GO / negative verdicts (never to be upgraded)

| Study | Verdict text (verbatim) | Locator |
|---|---|---|
| Early-signal five firms | gate table: **G1 … NO-GO**; O1 ×2 **underpowered**; 1D **not supported** | `main:papers/PAPER_NEGATIVE_v1.md:144-149` |
| S-029 relations | **`NO-GO FOR PREDICTION`** | `research/s029-evidence-based-relations:.../artifacts/prereg_decision.json:14` |
| PHOENIX-002 H8 | **`NO-GO`** — *"point estimate is positive but below the pre-registered practical threshold tau=0.03"* | `research/phoenix-002-h8-validation:.../results/verdict.json:2-3` |
| PHOENIX-003 early evidence | **`NO-GO`** (specificity 1.37 < 3.0–5.0; placebo p 0.881 > 0.10) | `research/phoenix-003-early-evidence:.../results/verdict.json:129` |
| DATA-EXPANSION lead | **`NO_DETECTABLE_LEAD`** (p = 0.569) | `research/data-expansion-001:.../SOURCE_INCREMENT_EXPERIMENT.md:17` |
| S-028 graph | **sealed as credible exploratory negative result; cannot be sealed as confirmatory** | `research/s028-...:.../CORRECTION_REPORT_ZH.md:15`, `:340` |

### 3.2 Explicit "blocked / not evaluable / underpowered"

| Study | Status text (verbatim) | Locator |
|---|---|---|
| Local LLM Phase 2 | **`RESEARCH_TRAINING_BLOCKED`** | `research/local-llm-foundation:.../docs/PHASE2_SUMMARY.zh-CN.md:91` |
| S-030 QLoRA | **`RESEARCH_TRAINING_BLOCKED`（本次未解除）**; P/R/F1 **`NOT_EVALUABLE`** | `research/overnight-qlora-s030:OVERNIGHT_RESEARCH_REPORT.zh-CN.md:13-14` |
| Early-signal O1 | **UNDERPOWERED — 0 onset(s) … H1 is neither supported nor refuted** | `main:.../CONCURRENT_DETECTION_EXPANDED.md:5-7` |
| S-031 hiring | H1/H2/H3 **当前证据不足**; no accuracy computed | `research/s031-hiring-capability-study:.../S031_RESEARCH_REPORT.zh-CN.md:154-178` |
| Innovation observatory | hiring = observation layer, **not** signal layer | `research/innovation-signals-observatory:PHASE4_RESEARCH_REPORT.zh-CN.md:97-98` |
| AI evidence review | not human adjudication / not ground truth | `research/ai-evidence-review:.../AI_REVIEW_SUMMARY.md:9-14` |

### 3.3 Narrow positives (quote with full caveats, or not at all)

| Study | Result | Caveat that must travel with it |
|---|---|---|
| Foresight confirmed rule | sustained-change precision **0.914** (0.892–0.934) vs **0.696** base; 78.7% spike recall; entity unit 0.917 vs 0.705; hiring domain 0.929 vs 0.794 | post-discovery confirmation; cell reuse; **no ramp distinction** (recall 0.142); needs human sign-off; one corpus/taxonomy/resolution |
| full-history-v1 | ΔAP **+0.0584** [+0.0020,+0.1213], p=0.030 | marginal; MDE 0.090 > effect; **not** better than two-way baseline; curated roster; no prospective test |
| Market-to-R&D cycle 2 (R11) | entity-cohort entry ΔAP **+0.0973**, 3/3 windows exclude zero | 200-entity deterministic cohort; part of the gain is the baseline weakening; detection not earlier warning; cycle-1 panel +0.0564 below MDE |

### 3.4 What the tally means for the project

- **The negative record is intact and unusually well documented.** Six independent negative assets
  (early-signal, S-028, S-029, PHOENIX-002, PHOENIX-003, DATA-EXPANSION) converge on the same
  diagnosis from different designs: **the binding constraint is data (identity, point-in-time clocks,
  density), not modelling**. That convergence is the programme's most credible scientific output.
- **No study currently has a validated prospective signal.** Every predictive number is evidence class
  **S** ("historical simulated prediction with an injected lag") at best; class **P** (true prospective
  validation) is **not produced anywhere** [FACT:
  `research/phoenix-001-round2:docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md:264-273`; `main:research/STATE.json:51`].
- **The one confirmed rule is a decision rule about alerts, not a discovery about firms.** It classifies
  transient spikes vs sustained activity; it does not predict a technological shift.
- **The programme's own state says the Understand layer is "prototypes only; no validated
  research-quality output" and Anticipate Level A is "not built"**
  [FACT: `main:research/STATE.json:45-52`]. Any external narrative contradicting this is unsupported.

---

## 4. Frozen-artifact index

Checksums below were recomputed with `git cat-file blob | Get-FileHash -Algorithm SHA256`; full machine
list in `_evidence/research/frozen_artifact_hashes.json`. `—` means not recomputed (large or already
covered by a committed sidecar). Frozen **snapshots** are additionally listed after the table.

| # | Branch | Path | Bytes | SHA-256 (first 16) | Freeze evidence |
|---|---|---|---:|---|---|
| 1 | main | `research/STATE.json` | 66,700 | `ac482d804a7509fb…` | committed state file (see provenance defect) |
| 2 | main | `research/AUDIT.json` | 2,931 | `a30be5ca7b919bee…` | objective audit, 11 PASS / 0 FAIL / 1 N/A |
| 3 | main | `papers/PAPER_NEGATIVE_v1.md` | 11,802 | `ebb7385a0ab28e95…` | claim map `CLAIMS_NEGATIVE.json` |
| 4 | main | `papers/CLAIMS_NEGATIVE.json` | 5,848 | `64a97de288b899c0…` | 24 verified claims |
| 5 | main | `.../THIRD_SOURCE_CROSSWALK.json` | 12,226 | `646e7b0e9d91da27…` | protocol frozen before queries |
| 6 | main | `.../ADJUDICATION_AGENT_V1.json` | 44,643 | `aade704a8cf2f5a6…` | amendment 002 |
| 7 | main | `.../CASE_PACKETS_SMALL_SAMPLE_V2.json` | 16,462 | `ae5ea459b9880816…` | original packets preserved |
| 8 | main | `experiments/detect_v1/benchmark.json` | 386,963 | `49688dce6e1aa191…` | controlled-truth benchmark |
| 9 | main | `experiments/reverse_rd_v2/ablation_metrics.json` | 38,190 | `d27c864bfcbe10e0…` | ablation cells |
| 10 | s028 | `.../artifacts/prereg_freeze.json` | 756 | `d2f543cd2a965d08…` | freeze hash chain |
| 11 | s028 | `.../artifacts/prereg_freeze_amendment1.json` | 756 | `29a8c1c63e6d5993…` | Amendment 1 |
| 12 | s028 | `.../CORRECTION_REPORT_ZH.md` | 32,785 | `40473eaa73bdfcbc…` | seal/not-seal verdict |
| 13 | s028 | `.../correction_round_1/stats_corrected_g2.json` | 75,946 | `d0b9dc24b2a97089…` | corrected N1/N2 re-run |
| 14 | s029 | `.../GO_NO_GO_CRITERIA.md` | 9,431 | `832ff3007d6c358a…` | prereg sha256 `d1bb8339…` recorded in #15 |
| 15 | s029 | `.../artifacts/prereg_decision.json` | 614 | `0f77787d5c66f2e7…` | verdict + prereg sha256 |
| 16 | s029 | `.../artifacts/verification.json` | 5,875 | `6691814928b2e5ce…` | 12/12 checks |
| 17 | phoenix-002 | `experiments/phoenix/h8_validation_v2/results/verdict.json` | 1,429 | `4649e4d800b8f4c0…` | mechanical NO-GO |
| 18 | phoenix-002 | `docs/phoenix/PHOENIX_002_PROTOCOL.md` | 17,664 | `14e47665549bb1e0…` | frozen before results |
| 19 | phoenix-003 | `experiments/phoenix003/results/verdict.json` | 2,429 | `c5a4547a887fe646…` | mechanical NO-GO |
| 20 | phoenix-003 | `experiments/phoenix003/FROZEN_RULES.json` | 7,787 | `147778583943c47b…` | frozen thresholds |
| 21 | data-expansion | `research/data_expansion/experiments/pre_registration.json` | 1,316 | `4e11e98b1b980fe5…` | design frozen 2026-11-09T05:40Z |
| 22 | data-expansion | `.../exp_a/EXP_A.json` | 8,567 | `9d01fdc453e6a116…` | EXP-A |
| 23 | data-expansion | `.../exp_b/EXP_B.json` | 3,617 | `be66fe88a4053ba1…` | EXP-B |
| 24 | data-expansion | `.../exp_c/EXP_C.json` | 4,101 | `d345e657d6d8ec71…` | EXP-C |
| 25 | atlas | `research/atlas/reports/identity_pilot.json` | 8,377 | `8ec9f30d54da245a…` | pilot results + verifier |
| 26 | horizon | `research/horizon/exports/horizon-2026-11-10/MANIFEST.json` | 25,860 | `b9e8653d53b1d1a2…` | manifest; **24 `*.sha256` sidecars** present |
| 27 | convergence | `research/convergence/verification/verification_summary.json` | 127,823 | `a0e913ef0140e2d5…` | independent verifier, deterministic |
| 28 | s031 | `S031_DELIVERY_MANIFEST.json` | 5,962 | `05072724f3b014e4…` | pins 31 delivery files |
| 29 | s030 | `.../results/overnight-2026-11-04/index/ARTIFACT_INDEX.json` | 62,099 | `10a8b19a48f9613a…` | 146 files / 128.14 MiB hashed |

**Frozen snapshots / manifests (not individually re-hashed here).**

- `main`: profile snapshots `experiments/b027/snapshots/{2020-12-31, 2022-12-31, 2024-12-31,
  2026-11-02, 2026-11-03, 2026-11-03-policy-v2}` each with `manifest.json` and SHA-256 per artifact
  [FACT: `main:research/RESULTS/README.md:117-128`, `:154`]. `research/FINAL_AUDIT.json` reports
  4/4 deterministic scripts identical.
- `main`: forecast sets `research/forecasts/FORECAST_SET_2026-11-03.json` and
  `..._prospective.json` (25 genuinely prospective forecasts, none matured)
  [FACT: `main:research/RESULTS/README.md:186-189`].
- `main`: `HUMAN_REVIEW_WORKSHEET.xlsx` (69 rows, 5-label drop-down) and `.csv`
  [FACT: `main:research/studies/early_signal_5firms/STUDY_DECISIONS.md:570-589`].
- `s031`: `S031_AI_PRELABELS.jsonl` (192,812 B) and `audit/legacy_rule_comparison.jsonl` (282,888 B)
  pinned by manifest [FACT: PR #22 body].
- `s030`: model adapter (132 MB safetensors) deliberately **not committed**; only the hash index is
  [FACT: `research/overnight-qlora-s030:OVERNIGHT_RESEARCH_REPORT.zh-CN.md:297-307`].
- `horizon`: `research/horizon/exports/horizon-2026-11-10/` — 23 present + 1 quarantined
  (`un_comtrade.jsonl`), 24 sidecars; all 23 byte lengths and SHA-256 equal the manifest
  [FACT: `integration/convergence-001:docs/convergence/INDEPENDENT_VERIFICATION.md:57-60`].
- `convergence`: two staging snapshots retained (60,928,000 B and 26,984,448 B) so both states stay
  auditable [FACT: `.../INDEPENDENT_VERIFICATION.md:62-68`].

**Freeze-status anomalies (must be disclosed with the artifacts).**

1. S-028 `HYPOTHESIS_REGISTRY.md` **matches neither freeze hash**; the results table was filled after
   the freeze [FACT: tip commit `4c6686f` body].
2. S-029's pre-registration, metrics and hash **first entered git in one commit**; ordering is evidenced
   by timestamps and the amendment log, **not** by an earlier commit — the study says so itself
   [FACT: `research/s029-evidence-based-relations:.../GO_NO_GO_CRITERIA.md:3-8`].
3. PHOENIX-002's `verdict.json` path differs from PHOENIX-003's (nested under `experiments/phoenix/`);
   there is no repository-wide freeze convention.
4. Horizon's 24 `.sha256` sidecars cover payloads; the **HORIZON prose** that summarises them was later
   shown wrong in 8/9 numbers [FACT: `.../INDEPENDENT_VERIFICATION.md:149-163`]. A hash proves bytes,
   not sentences.

---

## 5. Claims that must NOT be made publicly

Ordered by severity. Each item names the artifact that forbids it.

1. **"MedRadar predicts medical-technology change / early signals."** Forbidden by every predictive
   study: full-history H1 is marginal and non-prospective; PHOENIX-002/003 are NO-GO; S-028/S-029 are
   negative; `STATE.json` says `no validated research-quality output` and Anticipate Level A `not built`
   [`main:research/STATE.json:45-52`].
2. **"The system has demonstrated predictive skill for corporate technological entry."** Directly
   contradicted by the programme's own headline
   [`main:research/RESULTS/README.md:29-33`].
3. **"H8 is supported / growth features predict track growth."** Refuted: ΔAP 0.0294 < τ, placebo
   p=0.0846, dedup +0.0048, simple trend better; the pure-noise null reproduces the effect
   [`research/phoenix-002-h8-validation:.../PHOENIX_002_H8_RESULTS.md:13-17`, `:199-227`].
4. **"We detect technical activity ~4.4 years before regulatory milestones."** PHOENIX-003 measured
   specificity 1.37 and placebo p=0.88; 92.3% of links are follow-up of already-regulated products
   [`research/phoenix-003-early-evidence:.../SCIENTIFIC_CONCLUSION.md:32-55`].
5. **"S-028 is well-powered / the randomisation control proves real graphs are worse."** Both are
   `INVALIDATED_FINDING`; the corrected H4q tail is single-window and exploratory; H2q shows no reversal
   [`research/s028-...:.../CORRECTION_REPORT_ZH.md:284-295`; `.../GRAPH_RESULTS.md:109-121`].
6. **"S-028's holdouts are disjoint."** They overlap; 37 physical positives counted 75 times
   [FACT: tip commit `4c6686f`; `.../CORRECTION_REPORT_ZH.md`].
7. **"S-028's literature review found no such Yale paper."** False; Clayton & Coppola NBER WP 35227
   exists and contains a degree-preserving edge-shuffle ablation
   [FACT: `research/s028-...:.../LITERATURE_CORRECTION_NOTE.md`; `.../GRAPH_RESULTS.md:145-161`].
8. **"S-029 reconstructs point-in-time evidence / a collaboration network."** 0 of 20,563 claims has
   genuine point-in-time observation; `COOPERATES_WITH` has 0 admissible rows; co-authorship is not
   collaboration [`research/s029-...:.../NEGATIVE_FINDINGS.md:13-29`, `:68-79`].
9. **"Early-signal G1 is a GO."** Only "GO (frozen count) / FRAGILE"; 17 pairs collapse to 9 distinct
   clearances, below the floor of 10 [`main:.../LEAD_LAG_PROBE_CROSSWALK.md:5`;
   `STUDY_DECISIONS.md:288-291`].
10. **"The nine-event median lead of 3.3 quarters is a lead-time estimate."** It is truncated at
    2 quarters by the eligibility rule; shares ≥1q/≥2q are tautologies
    [`main:.../LEAD_TIME_SMALL_SAMPLE.md:3`, `:9-13`].
11. **"The 69 packets have been adjudicated / human truth exists."** `final_label = null` and
    `PENDING_HUMAN_REVIEW` on all 69; the AI review and agent rubric are non-human tiers
    [`main:.../ADJUDICATION_AGENT_V1.md`; `research/ai-evidence-review:.../AI_REVIEW_SUMMARY.md:9-14`].
12. **"AI-confirmed evidence / AI adjudication is ground truth."** Forbidden by the AI review's own
    header and by `LABELING_PROTOCOL.md` §1.
13. **"QLoRA fine-tuning improved extraction."** True only for schema compliance and abstention; false
    for negative controls (0 → 0.667 false positives); P/R/F1 `NOT_EVALUABLE`
    [`research/overnight-qlora-s030:OVERNIGHT_RESEARCH_REPORT.zh-CN.md:115-152`].
14. **"Hiring is an early signal of R&D direction."** The hiring study says it is an observation layer,
    not a signal layer; 0 new-direction candidates; classifier covers 6.1%
    [`research/innovation-signals-observatory:PHASE4_RESEARCH_REPORT.zh-CN.md:78-110`].
15. **"The four-dimension hiring ontology is validated."** S-031 explicitly says H1/H2/H3 are
    insufficient and no accuracy was computed
    [`research/s031-hiring-capability-study:.../S031_RESEARCH_REPORT.zh-CN.md:154-178`].
16. **"New sources add predictive lead time."** DATA-EXPANSION EXP-C is `NO_DETECTABLE_LEAD`
    (p=0.569); EXP-B finds no usable association strategy
    [`research/data-expansion-001:.../SOURCE_INCREMENT_EXPERIMENT.md:86-143`].
17. **"Cross-national device identity is solved / the 934 bridge covers the five firms."** The bridge
    covers 0.329% of MDALL rows; 98.9% of pairs are outside the five firms; 925/934 Canadian rows have
    no company field [`integration/convergence-001:docs/convergence/EXECUTIVE_SUMMARY_ZH.md:99-115`].
18. **"ATLAS identity precision 1.000 means we solved device identity."** It is a consistency check
    where the method *is* the label; no global P/R is claimed
    [`foundation/atlas-001:docs/atlas/RESEARCH_VALIDATION.md:38-61`].
19. **"HORIZON's EXP-H2 found 712 pairs / 387 rejected."** Official result is **726 / 0 / 0 / 726**; the
    prose was wrong in 8/9 numbers. Quote the machine artifact, never the prose
    [`integration/convergence-001:docs/convergence/INDEPENDENT_VERIFICATION.md:135-181`].
20. **"CONVERGENCE is fully verified."** The independent verifier reports **81 PASS / 10 FAIL /
    4 UNVERIFIABLE**; defect list must travel with the claim
    [`.../INDEPENDENT_VERIFICATION.md:14-49`].
21. **"The repository has an external, independent peer review."** No such record exists; all
    "independent" reviews are model sessions, separate scripts, or internal correction rounds.
22. **"The state file proves main's state."** `STATE.json` names a working tree and an old commit
    (`7a639f7`) that is not main's HEAD (`b2a14c0`) — it cannot verify the tree it ships in
    [`main:research/STATE.json:21-25`].
23. **"678 / 795 / 854 / 1,074 tests all pass and the count is settled."** The records disagree; one
    command by the owner must settle it. **[UNVERIFIED]**
24. **"The programme has five retractions and three marked retractions."** `AUDIT.json` says
    `retractions marked: 3`, while `PAPER_v1` and `D-074` say five retracted findings; the difference is
    almost certainly a counting-definition difference, but it is **unexplained** and must be resolved
    before either number is quoted [`main:research/AUDIT.json:32` vs `main:papers/PAPER_v1.md:195-218`].

---

## 6. Implemented feature ≠ validated method ≠ demonstrated predictive power

This is the register's central distinction. A feature can be excellent engineering and still support
**no** scientific claim.

| Level | What it means | Examples in this repository | What may be said |
|---|---|---|---|
| **Implemented** | Code exists, runs offline, has tests, may be product-grade | TKG + forecast registry; append-only observation ledger; ATLAS identity/evidence DB; HORIZON connectors; CONVERGENCE adapter; human-review workbench; XLSX validator; claim verifier | "We built X." Nothing about the world. |
| **Measured / validated method** | A specific measurement instrument has measured properties under stated conditions | Change detector with measured FAR/sensitivity **at one resolution**; promotion classifier at measured precision **0.914**; identity bridge at 0.329% coverage; control battery that destroys naive early-signal claims; publication-date disagreement 60% | "Under conditions C, instrument M has property P (with CI and limits)." |
| **Demonstrated predictive power** | Out-of-sample, ideally prospective, replicated, on an independent sample | **None.** full-history is marginal and non-prospective; Market-to-R&D R11 is modest/overlapping; PHOENIX-002/003 NO-GO; S-028/S-029 negative; no forecast matured | Nothing. **This cell is empty.** |

Concrete traps already recorded in the repository:

- **Passing tests ≠ validated method.** 1,074-ish offline tests coexist with a NO-GO verdict on the same
  branch; tests check code, not the world.
- **Format compliance ≠ extraction accuracy.** S-030's arm C reached schema 0.85 / agreement 1.000 while
  negative-control false positives rose to 0.667
  [`research/overnight-qlora-s030:OVERNIGHT_RESEARCH_REPORT.zh-CN.md:128-152`].
- **A ratio ≠ evidence.** 35/53 vs 4/53 under an exact binomial test
  [`main:papers/PAPER_v1.md:220-230`].
- **A promoted alert ≠ a finding.** The results ledger explicitly forbids citing a promotion as
  evidence [`main:research/RESULTS/README.md:6-9`, R107].
- **A verified identifier ≠ a true claim.** 66 CT.gov "RESULT" references → 35 corroborated; one grant
  number match is very likely a publisher metadata error
  [`research/horizon-001:research/horizon/EXPERIMENT_RESULTS.md:257-270`].
- **A reproduced number ≠ a real effect.** H8's +0.0379 reproduced bit-for-bit and was still a
  data-geometry artefact [`research/phoenix-002-...:.../PHOENIX_002_H8_RESULTS.md:48-65`, `:216-227`].
- **A hash proves bytes, not sentences.** HORIZON's exported bytes verified while its prose was wrong in
  8/9 numbers.

---

## 7. Programme-level integrity risks (ranked)

1. **No prospective evidence exists anywhere; every "prediction" is a backtest with an injected lag.**
   This is stated in the protocols but easily lost in PR titles. Risk: a reader treats class-S results
   as class-P. Mitigation: always print the evidence class next to the number.
2. **A committed state file is not bound to its commit.** `STATE.json` names
   `<REDACTED_LOCAL_PATH> `main_untouched_at: 7a639f7`; main HEAD is `b2a14c0`. Any
   automated reader of `STATE.json` is reading an unverifiable working-tree snapshot
   [`main:research/STATE.json:21-25`].
3. **The one positive result has been retracted/fragmented repeatedly across rounds** (H8: supported in
   #24 → NO-GO in #25; S-028 "well-powered" → 16.3% power; S-028 randomisation → 72/72 invalid). Risk:
   stale positive headlines survive in PR descriptions and READMEs. Mitigation: quote only the latest
   frozen verdict artifact.
4. **Identity is the universal blocker and is measured as much worse than assumed.** 93.1% of applicants
   `UNKNOWN` (PHOENIX-003); 67.68% of evidence lost under canonical-name search (S-029); 86.1% of
   material events have no roster company (full-history); 0.329% UDI bridge coverage (CONVERGENCE).
   Any "firm-level" claim is therefore a claim about a **small, non-random, curated subset**.
5. **Time semantics are fabricated in the store, not observed.** `available_at == published_at ==
   event_date` for all rows; `fetched_at` spans two days; S-028's `first_seen_at` has one value;
   PHOENIX records a synthetic +14-day clock for 55,090/55,090 rows. Risk: any "as-of" claim is
   unverifiable. This is a **data-infrastructure** defect, not a modelling one.
6. **Cluster/ID collisions between study numbering schemes.** `STUDY_DECISIONS.md` uses S-030 for agent
   pre-adjudication and S-031 for the rubric defect
   [`main:research/studies/early_signal_5firms/STUDY_DECISIONS.md:489`, `:506`], while the programme's
   branches use **S-030 = QLoRA** and **S-031 = hiring study**. Risk: citing "S-031" without a branch
   context is ambiguous. Mitigation: always cite `S-031 (hiring)` vs `S-031 (rubric defect)`.
7. **Verdict vocabulary is not standardised.** Some studies issue GO/NO-GO; others issue
   SUPPORTED/NOT SUPPORTED/INCONCLUSIVE; others only a seal/no-seal narrative; several issue none.
   Risk: an honest "underpowered" is later summarised as "no effect". Mitigation: this register's
   verdict class column.
8. **Overlapping holdouts are repeatedly described as independent.** Market-to-R&D v2 (3 overlapping
   windows), S-028 (3 overlapping windows, 99.5% pair repeat), PHOENIX-002 (Q1-only sensitivity
   +0.0160, n.s.). Risk: overstated significance. Mitigation: report the non-overlapping sensitivity.
9. **Prose has drifted from machine artifacts at least twice at high stakes** (HORIZON EXP-H2: 8/9
   numbers wrong; STATE/AUDIT retraction count). Risk: reports are read, artifacts are not. Mitigation:
   the `check_h2_consistency.py` gate invented by CONVERGENCE should be generalised to every study.
10. **Data-licence and personal-data exposure existed and is partially irreversible.** 6,234,301 bytes of
    UN Comtrade payload remain in PR #29 history; 248 named buyers' emails were in three raw packs
    (deleted on the branch). Risk: redistribution violation. This is recorded by CONVERGENCE and
    requires an owner decision [`integration/convergence-001:docs/convergence/EXECUTIVE_SUMMARY_ZH.md:72-79`,
    `:169-177`].
11. **Test/claim counts drift across records** (678 / 795 / 854 / 1,074; 3 vs 5 retractions; 45 vs 51 vs
    88 claims). Risk: low, but it erodes trust in every count. Mitigation: one canonical generated
    `COUNTS.json` per commit.
12. **The PHOENIX-001 PR #23 remote branch is stale by 33 local commits.** The PR shows older content
    than the local branch (`_FACTS.md:189`); the scientific record for round 1 may depend on content a
    reviewer cannot see. **[UNVERIFIED]** whether those 33 commits change any published number.

---

## 8. Open questions for the owner

1. **Which single document is allowed to define "the programme's result" in public?** Today the answer
   is ambiguous: `STATE.json`, `PAPER_v1`, `README.md`, and PR bodies disagree. Recommendation: make one
   generated `RESEARCH_STATUS.md` on `main`, signed by you, and forbid public claims not traceable to it.
2. **Do you want the 69 early-signal packets adjudicated or the lane closed?** No human label exists;
   without one, Target B cannot exist and the AI/agent tiers must never be cited as truth.
3. **Will you provision and hash-pin `data/medradar.sqlite` (or an extract) so any result is
   reproducible from a clean clone?** At present every "reproduce" command here is unexecutable without
   it, which is the largest single integrity gap.
4. **What is the canonical test count and the canonical claim count?** 678 / 795 / 854 / 1,074 and
   45 / 51 / 88 cannot all be right. One command, one recorded number.
5. **Can S-031 (hiring) and S-030 (QLoRA) be renamed to avoid collision with the early-signal study's
   internal S-030/S-031?** Cross-study citation is currently error-prone.
6. **For the one narrow positive (promotion rule): is it allowed in public at all before an external
   statistician reviews it?** If yes, which exact sentence and which caveats are mandatory?
7. **Will full-history-v1 get a PR and an independent review, or stay an unreviewed branch?** It contains
   the strongest remaining positive-*candidate* result; it is currently invisible to a `main` reader.
8. **Who owns the 33 unpushed PHOENIX-001 commits, and do they change any published number?** The PR
   content is stale; the scientific record may be too.
9. **What is the disposition of the licence-restricted UN Comtrade history and the 248 personal
   emails?** CONVERGENCE lists five owner decisions (A–E); none is taken.
10. **Should every study be required to emit a machine-readable `verdict.json` with a closed verdict
    vocabulary (GO / NO-GO / INCONCLUSIVE / BLOCKED / INFRA), plus a claim map?** Today only PHOENIX-002,
    PHOENIX-003 and S-029 do this cleanly.
11. **Will the `STATE.json` working-tree provenance defect be fixed, and will the file be regenerated
    from the commit it ships in?** Until then it cannot be used as evidence.
12. **What is the retirement policy for superseded positive claims (e.g. H8 "SUPPORTED")?** The
    repository preserves originals correctly, but readers encounter the old positive before the new
    NO-GO; a "superseded by" header in every affected file would remove that trap.

---

## 9. Appendix — evidence extraction and verification log

- Commands: `git ls-tree -r --name-only origin/<branch>`; `git show origin/<branch>:<path>`;
  `git log -1 --format='%H|%ci|%s' origin/<branch>`; `git cat-file -s`; `git cat-file blob`;
  `Get-FileHash -Algorithm SHA256`.
- Extracts retained verbatim under `_evidence/research/extracts/` (86 files) so every `path:line`
  citation is re-checkable without re-reading git objects. Extract filenames encode
  `<branch>__<path>`.
- Hash table: `_evidence/research/frozen_artifact_hashes.json` (29 entries).
- No repository file outside `docs/refoundation/` was written. No branch, PR, database or frozen
  artifact was modified.
- **Audit limitation to state plainly:** this register is a *documentary* audit. It did not execute any
  test, model, pipeline or data collection. Where a study's own verification is the only evidence, that
  is labelled as such. Absence of an external review is recorded as absence, not as failure.
