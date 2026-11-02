# Results

Each result is a committed artifact plus a plain-language statement of what it does
and does not show.

**Promotions are not results.** A promoted alert is an operational decision, not a finding, and is recorded
only in PROMOTIONS.md (append-only, signer-named). Nothing in this table may cite a promotion as evidence.
 Results are never edited to look better; a superseded result gets
a new entry and a pointer, not a rewrite.

| # | Result | Direction | Evidence |
|---|---|---|---|
| R1 | Continuation of active pairs is predictable but not beyond persistence | null on model advantage | `experiments/reverse_rd_v2/continuation_metrics.json` |
| R2 | First entry into a dormant track is weakly predictable at best | weak / not validated | `experiments/reverse_rd_v2/entry_metrics.json` |
| R3 | Consolidated SEC financials add no detectable continuation ranking skill | negative | `ablation_metrics.json` |
| R4 | Point-in-time market features add no detectable ranking skill | negative | `market_metrics.json` |
| R5 | OpenAlex publication counts add no detectable ranking skill | negative | `publication_metrics.json` |
| R6 | Financial features show a small positive entry ranking delta (+0.008 AP) | hypothesis only | `ablation_metrics.json` |
| R7 | Stored features are reproducible from as-of SQL (0 mismatches, 1.1M values) | consistency pass, not semantic proof | `run_v2.py` leakage replay |
| R8 | A bitemporal graph over real history supports deterministic as-of snapshots | infrastructure | `tkg_import_report.json` |
| R9 | 25 genuine prospective forecasts registered, none matured | pending | `data/registry.sqlite`, `forecast_cycle_report.json` |
| R10 | A deterministic applicant-entity universe doubles the observable firm panel without fuzzy matching | infrastructure | `config/universe_v1.json`, `docs/research/UNIVERSE.md` |
| R11 | On the entity cohort the entry model's ΔAP over per-pair persistence excludes zero in 3/3 windows under both entity and pair clustering | **supported (modest)** | `experiments/cycle2_coverage/` |
| R12 | The cycle-1 configuration is underpowered: its ΔAP sits below its own MDE and its pair-cluster interval includes zero | negative about cycle 1 | `experiments/cycle2_coverage/REPORT.md` §4 |
| R13 | The model's advantage at matched false-alarm rate is detection, not earlier warning | mixed / negative on lead time | `experiments/cycle2_coverage/REPORT.md` §5 |

## Cycle 1 (2026-11-02) — the honest headline

**The system, as of v0.5.0, has not demonstrated predictive skill for corporate
technological entry.** It has demonstrated: a rigorous, reproducible protocol; a
leakage-audited feature store; a persistence baseline that explains most of what
looked like skill; and a set of well-documented negative results about additional
data sources.

That is the correct baseline. Any future claim must beat it, not replace it.

See `cycle1_frozen_2026-11-02.md` for the numbers and their provenance.

## Cycle 2 (2026-11-02) — coverage, power, and whether the entry signal is real

Pre-registered question: *does widening the entity universe change the measured
predictability of first entry, and is the remaining estimate distinguishable from
zero?*

**Answer: yes to both, modestly.** On a 200-entity deterministic legal-entity cohort the
entry model beats per-pair persistence with ΔAP +0.0973, excluding zero in 3/3
pre-declared windows under both entity and pair clustering and exceeding its own MDE
(0.0877). On the original 51-parent panel the same protocol yields ΔAP +0.0564, below
its own MDE (0.0708), with the pair-cluster interval including zero — i.e. **the
cycle-1 negative was partly a coverage artefact**.

Boundaries that matter: the effect is small in absolute terms (AP 0.129 at a 0.68% base
rate), part of the gain is the persistence baseline getting weaker, the advantage is
**detection rather than earlier warning**, and the pre-declared firm-scale heterogeneity
split was degenerate. Details and all numbers: `cycle2_2026-11-02.md` and
`experiments/cycle2_coverage/REPORT.md`.
| R14 | Track assignment is deterministic for ~94% of material events; 6% rests on text keywords and every multi-track product code sits in that fallback | measurement | `experiments/detect_v1/track_assignment_audit.json` |
| R15 | At a matched 2% false-alarm budget the naive rate-multiplier detects 0.223 of injected shifts versus 0.181 (CUSUM), 0.122 (Bayes factor), 0.112 (z-score): the simple baseline is not beaten | **negative for complexity** | `experiments/detect_v1/REPORT.md` §0/§5 |
| R16 | The Bayes factor wins on the deterministic-track-only panel (+0.039 [+0.003,+0.071]) but loses on the other two panels: no stable preference | mixed / not robust | `experiments/detect_v1/benchmark.json` |
| R17 | Absolute detection is low: ~22% of shifts overall, ~50% of 5× shifts; a 2× change is undetectable at an honest budget. Data density, not the algorithm, is binding | finding | `experiments/detect_v1/REPORT.md` §6 |
| R18 | Real-data independence/confirmation is **blocked** on the current spine; the only available "independent" pathway shares the filing system | blocked | `docs/research/DETECTION_DESIGN_REVIEW.md` |
| R19 | Pre-declared sensitivity: quarterly aggregation **reverses** the detector ranking — Bayes factor 0.129 vs naive 0.025, paired +0.104 [+0.068,+0.140] | **correction to R15** | `experiments/detect_v1/benchmark.json` §track_quarterly |
| R20 | Removing 15.01% Special 510(k)s leaves the naive detector best and makes likelihood detectors worse: the monthly comparison is not maintenance noise | confirms R15 locally | `benchmark.json` §track_no_special |
| R21 | Masking product codes first seen 2022+ changes nothing material: taxonomy churn is concentrated, not global | confirms R15 locally | `benchmark.json` §track_stable_codes |
| R22 | Detector ranking is resolution-dependent on this lane; the mechanism (expected count per bin) is a hypothesis awaiting a bin-width sweep | finding | `research/RESULTS/cycle3b_correction_2026-11-02.md` |
| R23 | Bin-width sweep (1/2/3/4/6 months) puts the resolution crossover at 2 months (~0.42 expected events/bin) | finding | `experiments/detect_v1/bin_sweep.json` |
| R24 | Above the crossover the winning detector is NOT stable (alternates z-score / CUSUM): the best detector is not identifiable at this sample size | **negative / identifiability limit** | `bin_sweep.json` §crossover |
| R25 | Detector memory was parameterised in bins, so cycle 3b's quarterly winner was confounded: with calendar-matched memory the naive detector still collapses but the winner is the rolling z-score, not the Bayes factor | **correction to R19** | `research/RESULTS/cycle3c_sweep_2026-11-02.md` |
| R26 | The matched rate-ratio test is resolution-fragile: it wins only at the finest resolution and collapses at the next width | finding | `bin_sweep.json` |
| R27 | No independent confirmation source exists in the shipped spine: the only different registry (ClinicalTrials.gov) is mapped to drug tracks disjoint from device tracks, so 0 of 104 detection cells can be matched | **blocked (measured)** | `experiments/detect_v1/probe_trials_source.py` |
| R28 | Cross-firm co-movement: 3 of 32 tracks look synchronised under a lane-volume null, but **0 of 32** under a null conditioning on the track's own volume — the effect was track growth admitting firms | **negative** | `experiments/detect_v1/COMOVEMENT.md` |
| R29 | Technology activity in this lane is firm-specific plus track-level growth; month-level "the industry moved together" is not supported | finding | `comovement.json` |
| R30 | A device-track-mapped ClinicalTrials.gov lane now exists (2,663 events, 43 device tracks, 46 companies) with a committed collection manifest | infrastructure | `experiments/b040/collection_manifest.json` |
| R31 | The two independent lanes show **no detectable aligned time structure** at cell level: 16 eligible cells, whole lag profile −6…+12 inside the null band (max r=0.036 at +7 m vs [−0.046,0.048]) | **negative** | `experiments/b040/REPORT.md` |
| R32 | Evidence-fusion claims between trials and clearances are unsupported at this granularity; the limits are coverage (55%/48%), sparsity and company-vs-subsidiary granularity | limitation | `experiments/b040/REPORT.md` §What this licenses |
| R33 | Entry-cohort unit removes the density ceiling: 4,814 technology-entry events vs ~0.2 events per cell-month | infrastructure / method | `experiments/detect_v1/entries.json` |
| R34 | **ivd_immuno shows FDR-controlled industry-wide entry clustering that strengthens under product-code churn control** (p 0.0055 → 0.0010, z=4.73) — the first positive finding to survive its own controls | **positive (suggestive)** | `entries_churn.json` |
| R35 | `medical_ai`'s apparent entry wave was partly taxonomy churn: p 0.0040 → 0.0365 once late-created product codes are removed | correction of a tempting signal | `entries_churn.json` |
| R36 | No firm shows multi-track entry bursts (0 of 60): simultaneous entry is not a detectable signature of strategic redirection at this granularity | **negative** | `entries.json` §firm_clustering |
| R37 | **RETRACTION of R34**: 79% of raw entry events were first-ever appearances of a legal entity, not established firms entering; the ivd_immuno wave collapses under the prior-filer control (p 0.0010 → 1.0) | **retracted** | `entries_priorfiler.json`, `research/RESULTS/cycle7_retraction_2026-11-02.md` |
| R38 | No device track has a specification-stable industry entry wave: the surviving track changes identity across specifications and the one rejection under the strictest control rests on 5 entries | **negative** | `compare_entry_specs.py` output |
| R39 | Measurement rule: entry studies in this lane must state whether they measure firm-level technology entry or legal-entity appearance — mixing them manufactures waves | method rule | `research/STATE.json` `measurement_rule` |
| R40 | Pre-registered split-sample test of the aesthetics candidate: estimation p=0.0215, holdout p=0.0360 — but **not confirmatory**, because the candidate was nominated using the holdout window | **methodological correction** | `research/RESULTS/cycle8_holdout_2026-11-02.md` |
| R41 | Clean split-sample design (nominate on estimation window only, BH over 30 tracks; test on untouched holdout): **3 nominated, 0 confirmed** — no device track's entry clustering replicates | **negative** | `aesthetics_holdout.json` §clean_nomination_design |
| R42 | Holdout power for entry clustering is 0.25/0.52/0.95 at 30/50/70 % wave concentration: the null excludes strong clustering only, so the claim is "no evidence of replication", not "no clustering" | limitation | `aesthetics_holdout.json` §power |
| R43 | **Entry-clustering thread closed as a null**; programme shifts to data acquisition (hiring, patents) rather than further specification search | decision | `research/DECISIONS.md` D-027 |
| R44 | A lawful, keyless, genuinely **historical** hiring proxy exists: Wayback Machine CDX archives real job-posting URLs (Medtronic index spans 15 pages back to 2010) | infrastructure | `experiments/b030/hiring_panel.json` |
| R45 | Hiring coverage is thin: 6 of 16 probed device firms yield posting URLs and only **2** pass the pre-declared usability floor (bd, boston_scientific) | **feasibility limit** | `experiments/b030/REPORT.md` |
| R46 | The hiring↔regulatory lag question is **UNRUN, not answered**: the pre-registered test rests on 2 companies and the proxy's negative sign is uninterpretable (capture gaps ≠ hiring gaps) | **no result** | `experiments/b030/lag_analysis.json` |
| R47 | Access facts: PatentsView bulk = 403 (key required); Common Crawl index = persistent 504; the usability floor was deliberately not loosened to raise the sample | recorded constraint | `research/DECISIONS.md` D-029 |
| R48 | **Correction of R45**: cycle-9's "hiring coverage too thin" was a collector bug (`collapse=urlkey` + `limit`/`page` does not page here); the same hosts hold thousands of posting URLs | **retracted / corrected** | `experiments/b030/host_depth.json`, D-030 |
| R49 | Corrected hiring coverage: 11 of 16 probed firms have posting URLs, 6 have ≥24 months (Boston Scientific 4,999/123 months; Stryker 8,839/90; Medtronic 5,107/60; BD 4,709/68) | infrastructure | `hiring_panel_v2.json` |
| R50 | The pre-registered hiring/regulatory lag test is still **UNRUN, not null**: 3 usable companies, every value inside its null band, negative sign uninterpretable (capture-gap confound) | **no result** | `lag_analysis_v2.json` |
| R51 | Remaining hiring blockers are specific: power (3 companies) + board discovery for Philips, Dräger, Mindray, Zimmer Biomet, Masimo (two are mandated focus companies) | constraint | `research/STATE.json` `hiring_lane.remaining_blockers` |
| R52 | Board discovery (B-048) added a real Philips hiring board (669 postings/38 months) but it fails the silence criterion; Dräger, Mindray, Masimo have **no archived job-level URLs** | coverage result | `experiments/b030/depth_b048.json` |
| R53 | **The hiring lane covers 1 of the 5 mandated deep-case companies** (Medtronic): GE HealthCare only independent since 2023, Philips archived too sparsely, Dräger/Mindray on unarchived systems | **structural limit** | `research/DECISIONS.md` D-031 |
| R54 | Hiring lag test remains **UNRUN** (3 usable companies, unchanged floor); probing stopped because the marginal firm is unreachable, not because the floor was met | **no result** | `experiments/b030/lag_analysis_v2.json` |
| R55 | **Understand layer shipped**: a pure, unit-tested profile engine with seven required fields; contradictory evidence is a schema requirement (`validate_profile` rejects profiles without it) | infrastructure / method | `medradar/intelligence/profile.py`, `tests/test_profile.py` (34 tests) |
| R56 | Profiles generated for **all five mandated deep cases** from existing holdings: Medtronic 299 events/24 tracks (momentum 90 vs 66, 14/24 tracks trial-supported, 2 declining tracks), GE HealthCare 274/5, Philips 224/11, Mindray 82/3, Dräger 16/2 (thin, and says so) | deliverable | `experiments/b027/profiles/*.md` |
| R57 | Self-check re-derives every number in the Markdown from the JSON, verifies all seven fields and determinism: **5/5 pass**; full suite 829 tests OK | verification | `experiments/b027/selfcheck.py` |
| R58 | **Momentum is now a calibrated test** (two-sided exact binomial, α=0.05) with a mandatory minimum detectable ratio; a non-detection can no longer be reported as stability | method | `medradar/intelligence/profile.py`, D-033 |
| R59 | **Three of five cycle-12 momentum readings were noise**: Medtronic 90v66 p=0.065 (MDE 1.57×), Mindray 18v12 p=0.362, GE HealthCare 57v48 p=0.435 — only **Philips** survives (73v36, p=0.001) | **retracted readings** | `experiments/b027/profiles.json` |
| R60 | Calibration happened **inside the product**: D-032's structural contradiction rule forced the test to exist, so the correction did not depend on a reviewer noticing | design result | `research/RESULTS/cycle13_momentum_2026-11-02.md` |

  - id: B-049
    layer: understand
    priority: P1
    title: Full-roster profiles and a frozen dated snapshot set
    status: todo
    owner: lead
    depends_on: [B-027]
    acceptance: >
      Extend the seven-field profile engine beyond the five mandated deep cases to the full curated
      roster, then freeze a dated snapshot (profiles + source hashes + as-of date) so later cycles can
      compare against it. The snapshot is the point-in-time artifact any rolling-origin evaluation
      needs; without it, "what did we believe on date X" cannot be audited.
| R61 | **Full-roster profiles**: 53 companies (51-company roster + Dräger and Mindray) generated by the same seven-field engine | deliverable | `experiments/b027/snapshots/2026-11-02/` |
| R62 | **First frozen, hash-verified snapshot** (2026-11-02): per-artifact and per-source SHA-256, manifest hash, as-of date; freezer re-reads and verifies its own output; self-check verifies markdown reproduces exactly from JSON | point-in-time artifact | `experiments/b027/snapshots/2026-11-02/manifest.json`, `medradar/intelligence/snapshot.py` |
| R63 | **Calibration value measured**: a naive ratio rule flags **35 of 53** companies, the exact binomial test supports **4** — 31 would have been unsupported claims (e.g. iRhythm 4 vs 1, ratio 4.00, p=0.375, MDE 22.9×) | **method result** | `experiments/b027/momentum_calibration.json` |
| R64 | Per-company MDEs span 1.77×–22.9×, so detected counts cannot be compared as an innovation ranking | limitation | `experiments/b027/momentum_calibration.json` |
| R65 | **First rolling-origin benchmark shipped**: 376 (company, track) cells, 12 origins (2019-12..2025-06), 717 observations, signal uses only data up to each origin, company-clustered bootstrap | infra / evaluate | `experiments/b050/rolling_origin.json` |
| R66 | **Design flaw caught inside the benchmark**: the pre-registered outcome compared the future block with the *same recent block* that triggered the flag, so regression to the mean produced a spurious "anti-prediction" lift of 0.49 (CI 0.32–0.66) | **self-caught flaw** | `research/DECISIONS.md` D-036 |
| R67 | Corrected (future vs long-run baseline): the naive-increase lift **flips to 1.22 (CI 0.95–1.53)** and **no predictor's 95 % interval excludes 1** — no evidence of 12-month-ahead predictability above baseline | **null with intervals** | `rolling_origin.json` §_vs_baseline |
| R68 | The calibrated change signal is **too rare to predict with** (5 flags in 717 observations at ~0.2 events/cell-month): calibration made momentum honest and too sparse for triggering | limitation | `rolling_origin.json` §resolution |
| R69 | **Point-in-time rebuild**: `build_profiles.py --as-of` cuts the regulatory lane, the **trial lane** and the **code first-seen map** at the as-of date, and records a per-profile `leakage_audit` | method / reliability | `experiments/b027/build_profiles.py` |
| R70 | **A real leakage path was found and closed**: the trial lane and the code first-seen map had been read in full regardless of as-of, which would have silently invalidated any point-in-time claim | **defect fixed** | `research/DECISIONS.md` D-037 |
| R71 | Three backdated snapshots frozen and audited — **0 leakage problems**; lane events used 12,853 / 19,182 / 25,772 for 2020-12-31 / 2022-12-31 / 2024-12-31 | point-in-time artifact | `experiments/b027/snapshots/*`, `snapshot_diff.json` |
| R72 | **Verdict stability**: across four as-of dates, 40 of 53 momentum verdicts are stable, 13 change at least once and **2 reverse outright** (hologic, zimmer_biomet) — consistent with the calibrated test's measured low power | **stability result** | `experiments/b027/verdict_stability.json` |
| R73 | **Paper draft v1** (`papers/PAPER_v1.md`): five retractions with their control mechanisms, controlled-FAR frontier (0.223 best at 2 %), calibration 35→4, rolling-origin null (0.49→1.22 after correcting the bias), verdict instability (40 stable / 13 changed / 2 reversed), leakage-free point-in-time chain | **deliverable / publish** | `papers/PAPER_v1.md` |
| R74 | **Machine-verified claim map**: every quantitative claim declared in `papers/CLAIMS.json` with its artifact and exact substring; `papers/verify_claims.py` checks both directions — **45 of 45 verified** | verification | `papers/CLAIMS.json`, `papers/verify_claims.py` |
| R75 | Drafting failed the sourcing check three times before passing (two figures mis-transcribed from memory, one omitted) — the check caught the author, not a reader | process lesson | `research/DECISIONS.md` D-038 |
| R76 | **Four paper figures generated as dependency-free SVG** from the artifacts: detection frontier (16 points), calibration scatter (50), rolling-origin lifts (12), verdict-stability matrix (53) | deliverable | `papers/figures/*.svg` |
| R77 | **`verify_figures.py` re-derives all 131 plotted points** from source artifacts, parses each SVG, rejects numeric artefacts and requires paper links — 0 failures | verification | `papers/verify_figures.py` |
| R78 | **Headless rendering caught three layout defects** that structural checks missed (clipped labels, annotation off-frame, missing row labels) — validity is not readability | process lesson | `research/DECISIONS.md` D-039 |
| R79 | **Pre-registered alert-shape classifier FAILED** (balanced accuracy 0.394 vs 0.333 chance; sustained precision 0.764 vs 0.728 base rate): its confirmation window included the pulse | **negative** | `experiments/b026/spike_vs_shift.json` |
| R80 | Excluding the alert month from the window raises balanced accuracy to **0.608** (0.552–0.659) and sustained-change precision to **0.940** (0.903–0.978) — **post-hoc**, awaiting confirmation in B-054 | post-hoc result | `spike_vs_shift.json` §posthoc_variant |
| R81 | **Ramp-versus-level separation is not recoverable** from a two-month window (ramp recall 0.170) at ~0.2 events per cell-month | **negative** | `spike_vs_shift.json` §posthoc_variant |
| R82 | **First confirmed pre-registered prediction of the programme**: on fresh injection months the corrected promotion window reaches balanced accuracy **0.584** (0.556–0.607) and sustained-change precision **0.914** (0.892–0.934) vs a **0.696** base rate, clearing every pre-declared floor | **positive (narrow)** | `experiments/b026/confirm_window.json` |
| R83 | The confirmation is **binary only**: 78.7 % of spikes caught, but ramp recall 0.142, so ramp-vs-level remains unrecovered | limitation | `confirm_window.json` §confusion |
| R84 | **Caveat carried**: post-discovery confirmation — fresh injection months, same 65 cells; it does not rescue any earlier association finding | limitation | `research/DECISIONS.md` D-043 |
| R85 | Paper updated: title, abstract (labelled "after drafting") and new §4.9; **51 of 51** claims verified | deliverable | `papers/PAPER_v1.md` |
| R86 | **Deployment resolution fixed at 3 months (quarterly)**, justified by decision cadence and the measured sparsity ceiling; OBSERVE now names a detector only resolution-specifically | decision | `experiments/b039/deployment_resolution.json` |
| R87 | At quarterly resolution the **rolling z-score** leads: sensitivity **0.147** (CI 0.112–0.182), vs Bayes 0.073, CUSUM 0.065, naive 0.025 — no interval overlap within that resolution | measurement | `deployment_resolution.json` §per_width.3 |
| R88 | **No detector is identifiable across resolutions**: winner cycles naive→CUSUM→z→CUSUM→z and Kendall tau vs monthly is **−1.0** (complete reversal) | **negative** | `deployment_resolution.json` §conclusion |
| R89 | **The validated detector now runs inside every profile**: nested `deployment_alerts` applies the quarterly rolling z-score (threshold 3.5, measured FAR **0.018**, sensitivity **0.147**) and keeps the seven-field contract | deliverable | `medradar/intelligence/profile.py` |
| R90 | Alerts are printed with counts and baselines beside them: Medtronic shows **two live alerts**, each 2 events against a 0.25 baseline — calibrated is not substantial | honest reading | `experiments/b027/profiles/medtronic.md` |
| R91 | Self-check now fails a profile naming another detector/resolution, an alert failing its own threshold, or a markdown missing the detector line or FAR; profile tests **36 → 44** | verification | `experiments/b027/selfcheck.py` |
| R92 | The **promotion rule stays manual** by design: automating D-043 would turn a measured decision rule into an opaque default | design decision | `research/DECISIONS.md` D-046 |
| R93 | **Promotion rule confirmed at the legal-entity unit**: balanced accuracy **0.594** (0.583–0.616), sustained precision **0.917** (0.909–0.941) vs a **0.705** base rate — a difference of 0.010 and 0.003 from the company-level result | **positive (replicated)** | `experiments/b026/confirm_entity_cells.json` |
| R94 | Because entity cells **nest inside** company cells, this narrows the caveat rather than removing it: it tests aggregation level, not independence | limitation | `research/DECISIONS.md` D-048 |
| R95 | Three-way shape recovery still fails at both units: ramp recall **0.117** at entity level (0.142 at company level) | **negative** | `confirm_entity_cells.json` §confusion |
| R96 | **Promotion policy is code** (`promotion.py`, 18 tests): validated-detector provenance → confirmed two-quarter window → contradiction check → mandatory human sign-off; only `reject` or `promote_pending_signoff` exist, and a test forbids an automated path | deliverable | `medradar/intelligence/promotion.py`, `PREDICTION_PROTOCOL.md` §8 |
| R97 | On frozen data the gate diverges correctly: Medtronic `coronary` 2026-Q3 **rejected** (no confirmation quarters yet), `insulin_delivery` 2025-Q3 **promote_pending_signoff** (ramp) | behaviour | `experiments/b027/profiles/medtronic.md` |
| R98 | **Fifth auditable snapshot** (2026-11-03, manifest `5b7062d2…`) carries the deployment block; its diff against 2026-11-02 reports **identical data** — knowledge changed, not data | point-in-time artifact | `snapshots/2026-11-03/manifest.json` |
| R99 | `selfcheck` now enforces the verdict set, `requires_signoff`, the filing-rate statement and markdown presence; 5 profiles + 5 snapshots pass | verification | `experiments/b027/selfcheck.py` |
| R100 | **No confirmation window recovers the ramp class**: best ramp recall anywhere is **0.229** (6 months, company cells) and precision falls monotonically with window length; no window meets the pre-declared criterion on both units | **negative** | `experiments/b026/window_tradeoff.json` |
| R101 | **Metric trap named**: balanced accuracy is *highest* at the one-month window (0.588/0.616) because it can never see a ramp forming — reporting BA alone would recommend the window worst at the job | method lesson | `research/DECISIONS.md` D-051 |
| R102 | The blind spot now travels with every profile: `limits_and_provenance` carries the ramp limitation and the quarterly-only validation; two tests assert both appear in JSON and Markdown | product | `medradar/intelligence/profile.py` |
| R103 | **Second-domain validation CONSISTENT**: identical rule on archived job-posting series (8 of 13 series eligible, 43 alerts) gives balanced accuracy **0.593** (0.503–0.806) and sustained precision **0.929** (0.872–1.000) vs a **0.794** base rate | **positive (scoped)** | `experiments/b026/validate_hiring_domain.json` |
| R104 | Domain chosen by **measured feasibility**: the trial lane was inspected first and rejected (5 eligible cells) before the hiring lane (8 series) was used | method | `experiments/b026/inspect_{trial,hiring}_lane.py` |
| R105 | Not a second confirmation: 43 alerts vs 494/1,196 in the registry runs; no portability beyond this one domain; registry error rates remain the policy numbers | limitation | `research/DECISIONS.md` D-053 |
| R106 | **Promotions have their own append-only ledger** with enforced attribution: signer, timestamp, justification and policy version are required, and the logger refuses an unsigned promotion | deliverable | `research/RESULTS/PROMOTIONS.md`, `experiments/b027/log_promotion.py` |
| R107 | **A promotion is explicitly not a finding**: the findings ledger may not cite one as evidence; the promotion ledger is hashed into snapshot manifests so attribution is auditable | accounting rule | `research/RESULTS/README.md`, `research/DECISIONS.md` D-054 |
| R108 | The one candidate promotion (Medtronic `insulin_delivery` 2025-Q3) is left **PENDING_SIGNOFF** — the programme can prepare a promotion but cannot sign for a human | behaviour | `research/RESULTS/PROMOTIONS.md` |
| R109 | **The objective is audited mechanically**: `tools/audit_objectives.py` checks 12 requirements and writes `research/AUDIT.json`/`.md`; current result **11 PASS, 0 FAIL, 1 N/A** | infrastructure | `tools/audit_objectives.py`, `research/AUDIT.md` |
| R110 | The audit is a completeness/reproducibility check, **not a correctness proof** — it cannot show the science is right, only that artifacts exist, verify and are committed | scope | `research/DECISIONS.md` D-055 |
| R111 | Profiles now name the **governing promotion policy version** in their limits, and the promotion ledger carries a **reviewer checklist** (a promotion without independent corroboration is a rate change, not a technology change) | deliverable | `medradar/intelligence/profile.py`, `research/RESULTS/PROMOTIONS.md` |
| R112 | **Third-unit validation CONSISTENT at market-aggregate level** (38 tracks, median 270 events, 297 alerts): balanced accuracy **0.559** (0.514–0.605), sustained precision **0.889** (0.851–0.925) vs a **0.690** base rate | **positive (scoped)** | `experiments/b026/validate_track_domain.json` |
| R113 | **Ramp recall rises with series density** across units: 0.117 (entity) → 0.142 (company) → 0.300 (hiring) → **0.396** (track) — the first coherent scaling relationship found | **observational gradient** | `validate_track_domain.json`, D-057 |
| R114 | The gradient is observational: density and unit type vary together, so a controlled down-sampling test is needed before calling it a law; it does explain why a longer window could not rescue ramps | limitation | `research/DECISIONS.md` D-057 |
| R115 | **Controlled density experiment FAILED its pre-declared bar**: thinning dense track series 20× cut ramp recall **0.440 → 0.222** with rank correlation **0.882**, but strict monotonicity broke by 0.018 and dense/sparse intervals overlapped by 0.023 | **negative against its criterion** | `experiments/b026/density_experiment.json` |
| R116 | The **pre-registration was the weak part**, not the data: requiring strict monotonicity from five noisy point estimates voids a large consistent effect on a 0.018 wobble | method lesson | `research/DECISIONS.md` D-059 |
| R117 | The density scaling therefore stays **suggestive, not established**; no product or policy change is made on it; B-064 will confirm with a rank-correlation plus effect-size criterion on fresh draws | consequence | `research/BACKLOG.yaml` B-064 |
| R118 | **Density scaling CONFIRMED on fresh draws** under a disclosed post-failure revised criterion: ramp recall **0.444** at 4.16 events/series-month vs **0.204** at 0.22, rank correlation **0.908**, effect ratio **2.18×** | **positive (post-failure confirmation)** | `experiments/b026/density_confirm.json` |
| R119 | **Policy v2**: the ramp label is withdrawn below **1.0 event/month** and reported as `sustained_unresolved`; promotion itself is unaffected because the binary decision is what is confirmed | product | `medradar/intelligence/promotion.py`, D-061 |
| R120 | The measured ramp curve (0.204 at 0.22/month → 0.444 at 4.16) is what justifies the floor — not a fitted threshold but a conservative point on a measured curve | justification | `density_confirm.json` |
| R121 | **Labelled snapshots** allow a second freeze at the same as-of (2026-11-03-policy-v2) while keeping verification: manifest records the true as-of, selfcheck/diff accept the suffix, leakage audit uses the manifest value | infrastructure | `experiments/b027/freeze_snapshot.py`, D-062 |
| R122 | **Promotion-label diff**: between policy v1 and v2, **32 alert labels changed** and **8 changed shape** (ramp → sustained_unresolved), while the data-level diff reports **zero** change — only reporting one of the two would mislead | point-in-time / governance | `experiments/b027/snapshot_diff.json` |
| R123 | **6 of 6 snapshots verify**, 0 leakage problems, 5 consecutive diffs recorded | verification | `snapshot_diff.json` §leakage_audit |
| R124 | **Round-end routine is executable**: `tools/round_end.py` runs seven verifiers (test suite, claim map, figures, profile self-check, snapshot chain, objective audit, repository state) and its exit code is the completion claim — currently **7 PASS / 0 FAIL** in ~23 s | infrastructure | `tools/round_end.py`, `tools/round_end.json` |
| R125 | **Paper limitations now state the honest ratio**: exactly **one** decision rule confirmed against **five** retractions, plus the human sign-off requirement, the 1.0-event/month ramp floor and the post-failure status of the density confirmation | deliverable | `papers/PAPER_v1.md` §6 |
| R126 | Two implementation lessons recorded: unittest writes its summary to **stderr**, and per-step marker extraction beats a generic keyword heuristic (the first version reported the wrong line for the audit) | method | `research/DECISIONS.md` D-063 |
| R127 | **End-to-end pipeline evaluation**: alerts persist far more than non-alert cell-quarters — promoted **0.800** (0.652–0.917), unpromoted **0.667**, control **0.373** — so the detector carries real information about persistence | **positive (detector level)** | `experiments/b067/promotion_rolling_origin.json` |
| R128 | **The promotion filter's marginal value is NOT established**: difference **+0.133** with interval **−0.074 … 0.344** on 33 unpromoted alerts — recorded as a documentation discipline, not a measured predictive improvement | **negative (filter level)** | `promotion_rolling_origin.json` §decision |
| R129 | Underpowered by design: spikes are rare among alerts *because* the filter exists; testing it needs a longer history (unavailable) or a lower threshold (which changes the object under test) | limitation | `research/DECISIONS.md` D-065 |
| R130 | **Frozen prospective forecast sets** committed with content hashes: 32 forecasts registered from the policy-v2 snapshot, of which **7 matured at registration** (backfilled labels, excluded) and **25 genuinely prospective** ones mature 2026-Q4…2028-Q1 | deliverable | `research/forecasts/FORECAST_SET_2026-11-03_prospective.json` |
| R131 | The 7 backfilled forecasts score **Brier 0.337, accuracy 0.429** — no better than the majority class; reported as a sanity check that failed to reassure, not as evidence | **negative** | `experiments/b068/maturation.json` |
| R132 | **Registration rule recorded**: a forecast set may only be registered from alerts whose outcome window is entirely in the future; scripts must filter and report backfilled alerts separately | rule | `research/DECISIONS.md` D-066 |
| R133 | The objective audit now verifies committed forecast sets by structure **and content hash** rather than trusting the local registry: "2 hash-verified set(s); 25 prospective forecasts pending" | verification | `tools/audit_objectives.py` |
| R134 | **Second paper shipped** (`papers/PAPER_METHODS_v1.md`): nine measurement rules, each tied to the failure that motivated it, plus the two enforcement mechanisms and two results needing an intermediate category | **deliverable** | `papers/PAPER_METHODS_v1.md` |
| R135 | **Its own claim map**: `CLAIMS_METHODS.json` declares **22** quantitative claims with artifacts and exact substrings, verified in both directions (22/22); the round-end gate now runs **both** claim maps (8 steps) | verification | `papers/CLAIMS_METHODS.json`, `tools/round_end.py` |
| R136 | `papers/README.md` indexes the two papers and states how to read them together (results vs discipline) | deliverable | `papers/README.md` |
| R137 | **Roadmap rewritten as a plan of record** where every capability cites an evidence artifact, with section 3 naming what remains and why it cannot be simulated (maturation 2026-Q4…2028-Q1, human sign-off, access-blocked lanes) | **governance** | `research/ROADMAP.md`, D-068 |
| R138 | **Mission position updated** with history preserved: §9 keeps the 2026-11-02 record, §10 states today's established and unchanged facts | governance | `research/MISSION.md` |
| R139 | Every deliverable in the objective now has a named, machine-checked artifact; what remains is time- or access-dependent rather than open work | completion position | `research/STATE.json` §completion_position |
| R140 | **Figure 1 of the methods paper**: ten events mapped to nine rules (**21 filled cells**), generated from `papers/rules_map.py` and re-derived cell by cell by the verifier | **deliverable** | `papers/figures/fig5_retraction_rules.svg`, `papers/rules_map.py` |
| R141 | **Rule 7** (check the pipeline) is motivated by **four** events and **Rule 3** (benchmark independence) by **three** — the two most "boilerplate-looking" rules carry the most independent evidence | finding | `papers/rules_map.py`, D-069 |
| R142 | Three layout defects (legend covering columns 8–9, decision ids over event labels, legend off-canvas) were found **only by a rendered check**; fourth such case, now treated as a recurring class | method lesson | `research/DECISIONS.md` D-069 |
| R143 | `verify_figures.py` now scopes the paper-link check per paper; the gate runs both figure verifications and is now **9 steps** | verification | `tools/round_end.py` |
| R144 | **Render-only defect class now automated**: `papers/check_layout.py` detects text outside the canvas and text painted over by a later shape — the two classes that had escaped `verify_figures.py` four times — with rotated axis labels measured vertically | **infrastructure** | `papers/check_layout.py` |
| R145 | The checker was **proven against injected defects** (heading past the right edge; filled rect over two headings) and covered by 7 unit tests, one of which asserts the committed figures are clean | verification | `tests/test_check_layout.py` |
| R146 | Round-end gate is now **10 steps**, including `layout checks: 5 figures; problems: 0`; the checker does not replace a rendered review (contrast, text-on-text overlap remain manual) | governance | `tools/round_end.py`, D-070 |
| R147 | **Counted the store before calling anything blocked**: financial (43,420), market (95,725), publication (616), events (55,090) data are present, so five open backlog items are scheduled work, not blocked work; only **B-014** is newly blocked (needs a human adjudicator) | **governance** | `experiments/b073/lane_inventory.json` |
| R148 | **B-032 shipped**: taxonomy carries a version, effective date and SHA-256 fingerprints of both mapping files, stamped into `profiles.json`, with regime-change detection — a code remap is now visible as a regime change | **deliverable** | `medradar/intelligence/taxonomy.py`, D-071 |
| R149 | A process defect caught in-cycle: inserting `notes:` after section comments left the YAML unparseable; the audit failed, both were repaired, and the gate now runs the parser every round | method | `research/DECISIONS.md` D-071 |
