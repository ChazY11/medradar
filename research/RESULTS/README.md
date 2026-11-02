# Results

Each result is a committed artifact plus a plain-language statement of what it does
and does not show. Results are never edited to look better; a superseded result gets
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
