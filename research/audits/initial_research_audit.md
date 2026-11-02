# Independent audit of the MedRadar research record

**Auditor:** repo-auditor (independent, adversarial verification) · **Date:** 2026-11-03
**Tree:** `D:\DEPPSKK\worktrees\hist-v1`, branch `research/full-history-v1`, HEAD `b2a14c0a92332c004445de686daee97754cf94cb`
**Method:** every claim below was checked against the artifact named in `research/RESULTS/README.md` at HEAD, not against the prose that repeats it. Artifacts were read from `git show HEAD:<path>` so that uncommitted working-tree edits cannot be mistaken for the record. Load-bearing scripts were re-run into a temporary directory and compared with the committed JSON. Four groups of numbers were re-derived with my own read-only SQL against the git-ignored stores. A clean-checkout tree (`git archive HEAD`) was used to test reproducibility without `data/`.

**Tree state at audit start:** 7 uncommitted paths (`M research/AUDIT.json`, `M research/AUDIT.md`, `M tools/round_end.json`, `M tools/round_end.log`, `?? config/hist_entity_aliases.json`, `?? out_gate_histv1.log`, `?? research/protocols/`). The four `M` files are outputs of the verification commands themselves; writing them is unavoidable when the gate runs (§6, defect 11).

---

## 1. The verification harness as advertised

Commands run in the worktree, exact final lines and exit codes:

| command | exact output (final lines) | exit |
|---|---|---|
| `python tools/round_end.py` | `PASS test suite: Ran 1074 tests in 38.545s`; `PASS paper claim map: claims checked: 88; failures: 0`; `PASS methods claim map: 25/0`; `PASS negative claim map: 24/0`; `PASS study tests:`; `PASS paper figures: 5/0`; `PASS methods figures: 5/0`; `PASS figure layout: layout checks: 5 figures; problems: 0`; `PASS profile self-check: checked 5 profiles; failures=0`; `PASS snapshot chain: leakage problems: 0`; `PASS objective audit: 11 PASS, 0 FAIL, 1 N/A of 12`; `N/A repository state: HEAD b2a14c0a9233, remote unknown, 7 uncommitted path(s)`; `{'passed': 11, 'failed': 0, 'skipped': 0, 'not_applicable': 1}` | **0** |
| `python -m medradar selftest` | `Ran 1074 tests in 36.225s` / `OK` | **0** |
| `python tools/final_audit.py` | 10 × `PASS`; `REPRODUCED seasonality`, `REPRODUCED density confirmation`, `REPRODUCED pipeline evaluation`, `REPRODUCED track-domain validation`; `summary: {'verifiers_passed': 10, 'verifiers_failed': 0, 'artifacts_reproduced': 4, 'artifacts_differing': 0}` | **0** |

`tools/final_audit.py` (155 lines) runs the 10 verifiers, then re-runs four scripts (`b074/seasonality.py`, `b026/density_confirm.py`, `b067/promotion_rolling_origin.py`, `b026/validate_track_domain.py`) with `--out <tempdir>`, parses the produced and committed JSON, and compares them as Python objects (`produced == reference`, not bytes). It writes `research/FINAL_AUDIT.json`. It passes here because `data/` is present; §4 shows it fails when `data/` is absent.

The gate's own trailing self-description is out of date in the record: R124 says "seven verifiers … 7 PASS", R143 says the gate "is now 9 steps", R146 says "10 steps". `tools/round_end.py` at HEAD defines **12** steps (11 PASS + 1 N/A, 0 FAIL).

## 2. Claim-by-claim audit (33 load-bearing rows)

Class: **V** = Verified (artifact exists at HEAD, contains the quoted value, and where noted the script re-runs identically); **PV** = Partially Verified; **U** = Unverified (could not check, reason given); **F** = Failed (named artifact does not support the statement at HEAD). "Re-run" means I ran the producing script with `--out` to a temp path and compared parsed JSON.

| row | claim (abridged) | named artifact | class | evidence |
|---|---|---|---|---|
| R7 | leakage replay 0 mismatches over 1.1M values | `experiments/reverse_rd_v2/data_provenance.json` | **V** | `.leakage_audit.entry.checked_feature_values=1107081`, `.mismatch_count=0` |
| R9 | 25 genuine prospective forecasts registered, none matured | `data/registry.sqlite`, `experiments/reverse_rd_v2/forecast_cycle_report.json` | **PV** | own SQL: 25 rows, all `record_kind='nowcast'`, `window_end` all `2027-10-01`, `resolutions` 0 → none matured ✓; but they are nowcasts (DATA_PROVENANCE defect 9) and are not the 25 records in the frozen prospective set (different ids), so "genuine prospective" is not supported |
| R11 | entity-cohort ΔAP +0.0973, MDE 0.0877, 3/3 windows exclude 0 | `experiments/cycle2_coverage/analysis.json` | **V** | `.panels.p2.inference.clustered_bootstrap.entity.delta=0.0973206`; `…mde.observed_from_entity_cluster_se.mde_delta_ap=0.0876886`; `per_window_inference` 3/3 `excludes_zero_entity=true` and `…pair=true` |
| R12 | 51-parent ΔAP +0.0564 < MDE 0.0708; pair interval includes 0 | same | **V** | `.panels.p1` pooled delta 0.0564465, MDE 0.0707605; pair CI `[-0.01824, 0.14558]` |
| R14 | ~94 % deterministic track assignment, 6 % keyword fallback | `experiments/detect_v1/track_assignment_audit.json` | **V** | 35,693/37,782 = 94.47 %; `.fraction_keyword=0.055291`. The "every multi-track code is in the fallback" half is supported by the 30 listed `multi_track_examples` (30/30 `how=keyword`, 0 explicit mappings), not by enumerating all 72 `codes_multi_track` |
| R15 | 2 % FAR: naive 0.223 vs CUSUM 0.181, Bayes 0.122, z 0.112 | `experiments/detect_v1/benchmark.json` | **V** | `.levels.track.frontier_readout.0.02`: 0.222701 / 0.181034 / 0.122126 / 0.112069 |
| R19 | quarterly reversal: Bayes 0.129 vs naive 0.025, paired +0.104 [+0.068,+0.140] | `benchmark.json` §track_quarterly | **F** | at HEAD `.levels.track_quarterly.frontier_readout.0.02` = Bayes 0.072917, naive 0.025298; paired `poisson_bayes_factor` = +0.047619 [0.019006, 0.074713]. The value `0.104` and the interval `[0.068,0.140]` appear nowhere in the file; `0.129227` exists only on the unrelated `levels.domain` Bayes frontier. Superseded by R25 (verified: `rolling_zscore` 0.147321 leads) |
| R23 | crossover at 2 months, ~0.42 expected events/bin | `experiments/detect_v1/bin_sweep.json` | **V** | `.crossover.bin_months=2`, `median_expected_events_per_bin=0.423729`; re-run identical |
| R27 | 0 of 104 detection cells matchable to an independent source | `experiments/detect_v1/probe_trials_source.py` | **U** | the row names a script, not an output; no committed artifact contains the 104-cell count; not re-run (probe needs the research lane). Unverified, not refuted |
| R31 | 16 cells; max r=0.036 at +7 m; null band [−0.046, 0.048] | `experiments/b040/lag_analysis.json` | **V** | `.coverage.cells_eligible=16`; `.lag_profile.7` observed 0.035951, null `[-0.045736, 0.047740]` |
| R37 | 79 % of entry events are new legal entities; ivd_immuno p 0.0010 → 1.0 | `experiments/detect_v1/entries_priorfiler.json` | **V** | `counts.new_entity_entries_excluded=3804` of 4,814 (79.02 %); churn `.pvalue_one_sided=0.0009995` → prior-filer `=1.0` |
| R41 | 3 nominated, 0 confirmed under clean split sample | `experiments/detect_v1/aesthetics_holdout.json` | **V** | `.clean_nomination_design.fdr.rejected=3`; every confirmation window `[0,…]` |
| R49 | 11/16 firms; BS 4,999/123 m, Stryker 8,839/90 m, Medtronic 5,107/60 m, BD 4,709/68 m | `experiments/b030/hiring_panel_v2.json` | **V** | `.companies.*.distinct_postings` and `.months` exactly as quoted |
| R56 | Medtronic 299 events/24 tracks; GE 274/5; Philips 224/11; Mindray 82/3; Dräger 16/2 | `experiments/b027/profiles/*.md` | **U** | per-company totals are in `profiles.json`; I did not compare them one by one in this audit (time-boxed), so the row is unverified here, not contradicted |
| R59 | Medtronic 90 vs 66 p=0.065 MDE 1.57×; Philips 73 vs 36 p=0.001 | `experiments/b027/momentum_calibration.json` | **V** | `.rows[33]`: 90/66, p=0.065207, mde=1.574626; `.rows[41]`: 73/36, p=0.000505 (renders as 0.001) |
| R63 | 35 of 53 naive flags vs 4 calibrated; iRhythm 4v1 p=0.375 MDE 22.9× | same | **V** | `.naive_flags=35`, `.companies=53`, `.calibrated_detections=4`; `.rows[28]` p=0.375, mde=22.926 |
| R65/R67 | 376 cells, 12 origins, 717 obs; lift 0.49→1.22, CI 0.95–1.53, no interval excludes 1 | `experiments/b050/rolling_origin.json` | **PV** | values present (`.counts.cells=376`, `len(origins)=12`, `.counts.observations=717`; `naive_increase_vs_recent.lift=0.485709` CI [0.318662,0.657290]; `…_vs_baseline.lift=1.221551` CI [0.953128,1.531532]), but the producing script **crashes at HEAD** (see §2.1) — not re-derivable |
| R82 | confirmed rule: BA 0.584 (0.556–0.607), precision 0.914 (0.892–0.934) vs base 0.696 | `experiments/b026/confirm_window.json` | **V** | `.metrics.balanced_accuracy=0.583845`, `.metrics.sustained_precision=0.914209`, `.metrics.sustained_base_rate=0.696356`; CIs as quoted |
| R93 | entity-unit replication: BA 0.594 (0.583–0.616), precision 0.917 (0.909–0.941) vs base 0.705 | `experiments/b026/confirm_entity_cells.json` | **V** | values as quoted; re-run identical |
| R100 | best ramp recall anywhere 0.229 (6 months) | `experiments/b026/window_tradeoff.json` | **V** | `.units.company.6.recall.ramp=0.228571`; re-run identical |
| R103 | hiring domain BA 0.593 (0.503–0.806), precision 0.929 (0.872–1.000) vs base 0.794 | `experiments/b026/validate_hiring_domain.json` | **V** | values as quoted; re-run identical |
| R112 | track domain BA 0.559 (0.514–0.605), precision 0.889 (0.851–0.925) vs base 0.690 | `experiments/b026/validate_track_domain.json` | **V** | values as quoted; re-run identical |
| R115 | thinning 0.440→0.222, rho 0.882; monotonicity gap 0.018, interval overlap 0.023 | `experiments/b026/density_experiment.json` | **PV** | `.decision.ramp_recalls_by_factor` 0.439560→0.222222, `.spearman_rho=0.881770`, `monotone_in_density=false`; gap 0.0182 derivable (0.318182→0.300000). The 0.023 overlap is **not in this JSON** — only in `research/RESULTS/cycle30_density_2026-11-03.md:32` |
| R118 | density confirmation: 0.444 at 4.16 vs 0.204 at 0.22, rho 0.908, ratio 2.18 | `experiments/b026/density_confirm.json` | **V** | `.decision.dense_recall=0.444444`, `.sparse_recall=0.204082`, `.rho=0.907804`, `.effect_ratio=2.177778`; `.factors.1.density.mean_events_per_series_month=4.157231` |
| R127 | promoted 0.800 (0.652–0.917), unpromoted 0.667, control 0.373 | `experiments/b067/promotion_rolling_origin.json` | **V** | `.rates.promoted=0.8`, `.bootstrap.promoted_ci=[0.652174,0.916667]`, `.rates.unpromoted=0.666667`, `.rates.control=0.373313`; re-run identical |
| R130 | 32 forecasts, 7 matured at registration, **25 genuinely prospective** | `research/forecasts/FORECAST_SET_2026-11-03{,_prospective}.json` | **F** | counts correct (32/7/25), but of the 25 "genuinely prospective" records **12 have outcome windows that begin at or before the registration lane cutoff 2026-Q3** (4 start 2026-Q1, i.e. 3 of their 4 outcome quarters were already in the lane; 4 start 2026-Q2; 4 start 2026-Q3). Only 13 are entirely future. See §6 defect 1 |
| R131 | backfilled forecasts Brier 0.337, accuracy 0.429 | `experiments/b068/maturation.json` | **V** | `.scoring.brier=0.337238`, `.scoring.accuracy=0.428571` |
| R148 | taxonomy carries version, effective date, SHA-256 fingerprints, stamped into `profiles.json` | `medradar/intelligence/taxonomy.py`, D-071 | **PV** | `taxonomy.py` exists (`TAXONOMY_VERSION="tracks_device_2026-11"`, `EFFECTIVE_FROM="2026-11-03"`); the **live** `experiments/b027/profiles.json` has a `taxonomy` block, but all three frozen snapshot `profiles.json` files (`2026-11-02`, `2026-11-03`, `2026-11-03-policy-v2`) have **no** taxonomy block, and every profile's own limitations still state "product-code taxonomy is not versioned by effective date" |
| R150 | Jan/Feb factor 0.891, annual spread 1.255×, permutation p=0.0005 (0/2,000); quarter-boundary months 1.058/1.054 | `experiments/b074/seasonality.json` | **V** | `.month_factors.factors[0]=0.8907`, `.spread_max_over_min=1.255102`, `.permutation.p_value=0.00049975`, `.boundary_artifact.quarter_start_vs_interior=1.0579`, `…quarter_end=1.0542`; re-run identical and stdout prints exactly these |
| R151 | adjustment changes 9 of 39,151 cell-months (91.8 % zeros); alert rate identical 0.0090, 89/9,870 | same | **PV** | `.quarterly_raw/.quarterly_adjusted` = 89/9,870, rate 0.009017, `.difference=0.0`; 39,151 = 329 cells × 119 months, confirmed by re-run stdout `cells: 329 … months: 119`. But "9 changed" and "91.8 % zeros" are **not stored in `seasonality.json`**; they appear only as literals in `experiments/b074/update_state_cycle41.py` |
| R153 | four scripts re-run and compared, 4/4 identical; 10/10 verifiers pass | `research/FINAL_AUDIT.json` | **PV** | true in this worktree (exit 0, 4/4, 10/10); **false in a clean checkout** (§4): `final_audit.py` exits 1 with 9/10 verifiers and 0/4 reproduced |
| R155 | closure: 152 result rows (27 negative), 74 decisions, 6 snapshots, 113 verified claims, 157 commits | `DECISIONS.md`, `STATE.json` | **PV** | 74 decisions ✓, 6 snapshots ✓, 113 = 88+25 paper claims ✓ (but three maps now total 137); 152 rows ✗ (155 at HEAD, 29 negative/null by the audit's own counter), 157 commits ✗ (184) |
| R74/R85/R124/R143/R146 | apparatus counts: 45 of 45 → 51 of 51 claims; gate 7 → 9 → 10 steps | `CLAIMS.json`, `tools/round_end.py` | **PV** | each was true when written; at HEAD `CLAIMS.json` holds 88 claims, the gate has 12 steps, and no row marks these as superseded (R85/R135 supersede the claim counts only) |

Tally: **21 Verified, 8 Partially Verified, 2 Failed, 2 Unverified.**

### 2.1 Independent script re-runs (six)

Re-run into `%TEMP%\histaudit\repro\`, compared as parsed JSON with the committed file:

| script | result | comparison |
|---|---|---|
| `experiments/b026/validate_hiring_domain.py` | exit 0 | `identical: True` |
| `experiments/b026/confirm_entity_cells.py` | exit 0 | `identical: True` |
| `experiments/b026/window_tradeoff.py` | exit 0 | `identical: True` |
| `experiments/detect_v1/bin_sweep.py` | exit 0 | `identical: True` |
| `experiments/b074/seasonality.py` | exit 0 | `identical: True`; stdout `cells: 329; lane events: 3928; months: 119`, `quarterly raw … 0.0090` |
| `experiments/b050/rolling_origin.py` | **exit 1** | crashes before writing: `AttributeError: 'str' object has no attribute 'year'` at `experiments/detect_v1/streams.py:49` (`month_index`), called from `rolling_origin.py:60` with `row["date"]`, which `experiments/b027/build_profiles.py:83` emits as `str(event["day"])[:10]`. That line was introduced in commit `5dffaab` (cycle 16), after `8eab223` (cycle 15, the only commit touching `rolling_origin.py`), and the benchmark was never re-run. **R65/R67 cannot be regenerated from the committed tree.** |

## 3. Claim maps, figures, layout — run directly

| verifier | command | output | exit |
|---|---|---|---|
| main claim map | `python papers/verify_claims.py` | `claims checked: 88; failures: 0` | 0 |
| methods claim map | `python papers/verify_claims.py --paper papers/PAPER_METHODS_v1.md --claims papers/CLAIMS_METHODS.json` | `claims checked: 25; failures: 0` | 0 |
| negative claim map | `python papers/verify_claims.py --paper papers/PAPER_NEGATIVE_v1.md --claims papers/CLAIMS_NEGATIVE.json` | `claims checked: 24; failures: 0` | 0 |
| figures | `python papers/verify_figures.py` | 16 + 50 + 12 + 53 points re-derived; `figures checked: 5; failures: 0` | 0 |
| methods figures | `python papers/verify_figures.py --paper papers/PAPER_METHODS_v1.md` | 5 figures incl. fig5 = 10 points; failures 0 | 0 |
| negative figures | `python papers/verify_figures.py --paper papers/PAPER_NEGATIVE_v1.md` | 5 figures; failures 0 | 0 |
| layout | `python papers/check_layout.py` | `layout checks: 5 figures; problems: 0` | 0 |

Total re-derived plotted points across the five figures: 16+50+12+53+10 = **141**; R77's "131" is the first paper's four figures (16+50+12+53) and is correct for what it claims.

**What the claim maps actually prove.** `papers/verify_claims.py` checks two substrings per claim: the needle is present in the named source file, and the value string is present in the paper. It does not re-run anything and does not compare numbers. Of the 88 main-paper claims, **61 name `research/DECISIONS.md` as their source**, and **49 have needles shorter than 6 characters** (e.g. `0.223`, `31802`). All 24 negative-paper claims name a single aggregate, `research/studies/early_signal_5firms/CLAIMS_EVIDENCE.json`. So "88/88 verified" is a text-consistency check between the paper and the prose record; it cannot detect the R19 and R130 defects above, because both papers' claims are consistent with the prose they cite.

## 4. Reproducibility from a clean clone, and `data/` provenance

`git ls-files data` → **0 files**. `.gitignore` excludes `data/` and `out/`. Committed stores are absent; sizes here: `data/medradar.sqlite` 1,368,469,504 B, `data/research.sqlite` 289,443,840 B, `data/b040_device_trials.sqlite` 7,323,648 B, `data/registry.sqlite` 81,920 B (≈1.65 GB, none committed). Snapshot manifests **pin** the input hashes (`data\research.sqlite` `dd241bfe…`, `data\b040_device_trials.sqlite` `46e51490…`, window end 2026-09) but ship no way to obtain files with those hashes.

I materialised the committed tree with `git archive --format=zip HEAD` → 1,135 files, **no `data/`, no `out/`**. In that tree:

* `python -m medradar selftest` → `Ran 1074 tests in 22.257s` / `OK (skipped=3)`, exit **0**. The suite is clean-clone-robust; data-dependent tests skip.
* `python tools/round_end.py` → `{'passed': 11, 'failed': 0, 'skipped': 0, 'not_applicable': 1}`, exit **0**; its `objective audit` reported `12 PASS, 0 FAIL, 0 N/A` because `git status` returns nothing outside a repository, so the "working tree committed" check cannot fail. The gate cannot distinguish a clean checkout from a directory that is not a repository at all (`repository state: HEAD , remote unknown`).
* `python tools/final_audit.py` → **exit 1**: `FAIL forecast scorer: sqlite3.OperationalError: unable to open database file`; all four reproducibility targets `DIFFERS` with the same error; `{'verifiers_passed': 9, 'verifiers_failed': 1, 'artifacts_reproduced': 0, 'artifacts_differing': 4}`.

Committed artifacts whose **regeneration** (not inspection) depends on the git-ignored stores — grouped by producing script; all fail from a clean clone with the same `unable to open database file` unless they also read committed intermediates:

| evidence group (rows) | committed artifact(s) | needs | documented regeneration command? | runnable offline here? |
|---|---|---|---|---|
| R150–R152 | `experiments/b074/seasonality.json` | `data/research.sqlite` | no dedicated doc; script only | yes with `data/` present (re-run identical); **no** from clean clone |
| R118/R120 | `experiments/b026/density_confirm.json` | `data/research.sqlite` | script only | same |
| R127/R128 | `experiments/b067/promotion_rolling_origin.json` | `data/research.sqlite` (lane outcomes) | script only | same |
| R112–R114 | `experiments/b026/validate_track_domain.json` | `data/research.sqlite` | script only | same |
| R131 | `experiments/b068/maturation.json` | `data/research.sqlite` | `python experiments/b068/maturate_forecasts.py` (ROADMAP §3) | fails clean |
| R65–R68 | `experiments/b050/rolling_origin.json` | `data/research.sqlite` | script only | **fails even with `data/`** (code drift) |
| R11–R13 | `experiments/cycle2_coverage/analysis.json` | `data/research.sqlite` | `python experiments/cycle2_coverage/run_cycle2.py` (in-file) | not tested (long); needs `data/` |
| R14–R29, R33–R42 | `detect_v1/{benchmark,bin_sweep,streams,streams_ext,widths,entries*,comovement,track_assignment_audit,reassignment_audit,aesthetics_holdout,realdetect}.json` | `data/research.sqlite` | per-script only | not tested; needs `data/` |
| R1–R9 | `reverse_rd_v2/{continuation,entry,ablation,market,publication}_metrics.json`, `data_provenance.json` | `data/research.sqlite` + `data/registry.sqlite` | README `python -m medradar.intelligence.pipeline collect --source fda\|sec\|procurement\|market`; `scripts/forecast_cycle.py` | not attempted: collection needs network and would produce a **newer** store, not the pinned snapshot |
| R44–R54 | `b030/{hiring_panel_v2,host_depth,lag_analysis_v2}.json` | Wayback network archive (not `data/*.sqlite`) | `experiments/b030/*.py` | not attempted (network-dependent) |
| R30–R32 | `b040/{collection_manifest,lag_analysis}.json` | ClinicalTrials.gov network + `data/b040_device_trials.sqlite` | `experiments/b040/collect_device_trials.py`, `write_manifest.py` | not attempted (network) |
| R147 | `b073/lane_inventory.json` | `data/*.sqlite` | script only | not tested |
| negative paper's 24 claims | `research/studies/early_signal_5firms/CLAIMS_EVIDENCE.json` | `data/medradar.sqlite` (its own `store` field points at `D:/DEPPSKK/medradar/data/medradar.sqlite`, a sibling checkout) | `experiments/b090/paper_evidence.py` | not tested from clean clone; recomputable here with my own SQL (§5.3) |
| B-027 profiles/snapshots (R56–R72, R98–R123) | `experiments/b027/profiles.json`, `snapshots/*/profiles.json` | `data/research.sqlite` + `b040.sqlite` (hashes pinned in manifests) | `experiments/b027/build_profiles.py`, `freeze_snapshot.py` | snapshot **verification** passes clean (committed hashes); regeneration needs `data/` |

Net: **no committed artifact's *verification* (hash/claim/figure checks) depends on `data/` — every verifier passes in the clean tree — but every event-lane artifact's *regeneration* does, and `final_audit.py`'s own reproducibility claim collapses without it.** The record's repeated claim that "every reported number is re-derivable" (ROADMAP §2; COMPLETION_REPORT §1) is therefore true only for a tree that has the uncommitted 1.65 GB of stores; the stores' hashes are pinned but the stores are not distributable and no checksum-verifiable download path is documented.

## 5. Four independent re-derivations with my own read-only SQL

I did not use the repo's scripts. Queries were against `data/medradar.sqlite` and `data/research.sqlite` opened `mode=ro`.

**5.1 `DATA_PROVENANCE.md` §3 (legacy store) — exact agreement.** `375,378` events; range `1966-12-14 … 2026-10-30`; `89` companies; `60` tracks; per-source counts `176,466 / 59,646 / 57,372 / 55,592 / 20,976 / 5,326`; linkage `company_key 132,293/375,378 = 35.243 %` (record 35.2 %), `track_id 52.358 %` (52.4 %), both `23.530 %` (23.5 %), `88,327` rows, `1,192` distinct company×track pairs. Record correct.

**5.2 `DATA_PROVENANCE.md` §2 and defects 1–2 (research lane) — exact agreement.** `55,090` events = `31,219` 510(k) + `23,871` PMA; 510(k) linked `5,287/31,219 = 16.93 %` (record 16.9 %); `43,420` financial facts / `32` companies; `95,725` market bars; `616` publication rows; `3,453` procurement awards; **Shenzhen Mindray 90 rows, 0 linked**; **Dräger-family 25 rows, 0 linked** (12 + 1 + 7 + 3 "Draeger…" spellings + 2 "Dragerwerk"), matching the record's "all 90" and "all 25". The defect statements are accurate.

**5.3 Negative paper's `CLAIMS_EVIDENCE.json` — exact agreement.** `eightk_total 20,976` ✓; `eightk_with_company_key 1,360` ✓; `trials_total 55,592` ✓; `trials_on_device_tracks 0` ✓ — 31,619 trial rows carry only `t_*` therapy-area ids (`t_oncology`, `t_respiratory`, …), none a device track. This independently confirms the study's central negative: the trial lane cannot be cross-walked to device tracks.

**5.4 `registry.sqlite` (R9) — agreement with the count, disagreement with the adjective.** 25 forecast rows, all `record_kind='nowcast'`, `window_end` uniformly `2027-10-01`, `resolutions 0` → "none matured" ✓. R9's "25 genuine prospective forecasts registered" is not supported: the frozen prospective set's ids (`abbott|medical_ai|2025-Q3`) are not the registry's `sha256:…` prediction ids, and DATA_PROVENANCE defect 9 itself calls the registry records nowcasts.

## 6. Defects not recorded in `research/DECISIONS.md`

1. **The "genuinely prospective" forecast set is partly backfilled.** In `research/forecasts/FORECAST_SET_2026-11-03_prospective.json` (`lane_through_at_registration: 2026-Q3`), **12 of 25** forecasts have outcome windows that begin at or before 2026-Q3 (4 start 2026-Q1, 4 start 2026-Q2, 4 start 2026-Q3), so between one and three of their four outcome quarters were already in the lane at registration; only 13 are entirely future. `experiments/b068/register_forecasts.py:65–70` filters only on `matures_when_data_through` (window end), not on window start, while D-066:2603–2614 claims the rule "outcome window is entirely in the future" was "applied immediately". It was not. This contaminates the programme's only forward-looking evidence asset and the "25 genuinely prospective" line in MISSION §10, ROADMAP §3, AUDIT.md and COMPLETION_REPORT §1.
2. **`experiments/b050/rolling_origin.py` cannot run at HEAD** (`AttributeError: 'str' object has no attribute 'year'`), so R65/R67 — the rolling-origin null that the papers rely on — are inspectable but not regenerable. No gate step runs it; `final_audit.py` chose four other scripts.
3. **Reproducibility collapses without `data/` while the gate still passes.** Clean `git archive HEAD`: selftest OK (1,074, 3 skipped) and `round_end.py` exit 0, but `final_audit.py` exit 1 (0/4 reproduced). `round_end`'s repository-state step reports HEAD `""`, 0 dirty paths and cannot fail outside a git repository. The four "REPRODUCED" claims in R153/FINAL_AUDIT.json are data-dependent and were never tested against absence of `data/`.
4. **The record's summary numbers disagree with its own artifacts.** `COMPLETION_REPORT.md:3–4,17,19,101,104,107` = 157 commits, 913 tests, 10 gate steps, 152 rows, 73 decisions, R1–R152, main `7a639f7`, branch `research/change-detection-v1`; HEAD has 184 commits, 1,074 tests, 12 steps, 155 rows, 74 decisions, R1–R155, main/`HEAD` `b2a14c0` on `research/full-history-v1`. `STATE.json.completion_position` says 67 decisions, 136 rows, 910 tests, "82 + 22 claims", phase `complete_verified` cycle 44. ROADMAP §2 says "currently 910" tests. MISSION §10 says "82 and 22 claims" and "five auditable frozen snapshots" (six exist). R155 itself says 152 rows / 27 negative / 157 commits.
5. **Two leakage-replay values for one audit.** MISSION §9:202 and STATE.json:89 say "0 mismatches over **656,048** values"; the artifact (`data_provenance.json .leakage_audit.entry`) says **1,107,081** values (R7's "1.1M"). 656,048 is the older `docs/research/AUDIT_CYCLE2.md:276` figure; the prose was never updated.
6. **R19's evidence pointer is dead.** The row says the quarterly reversal was "Bayes 0.129 vs naive 0.025, paired +0.104 [+0.068,+0.140]" and cites `benchmark.json` §track_quarterly; the artifact now contains 0.0729 / 0.0253 / +0.0476 [0.0190,0.0747] after the memory-parameterisation correction recorded as R25. Keeping the row is legitimate as history, but it is not marked superseded in place and no re-verification can reach it.
7. **R151's secondary numbers are not in its named artifact.** `9 of 39,151` and `91.8 % zeros` are absent from `experiments/b074/seasonality.json`; 39,151 is confirmed as 329 cells × 119 months by re-running the script, but the "9 changed" and 91.8 % are literals in `experiments/b074/update_state_cycle41.py:49`.
8. **Taxonomy versioning does not reach the frozen artifacts.** R148 says the taxonomy is "stamped into `profiles.json`". The live `experiments/b027/profiles.json` has the block; none of the three frozen snapshot `profiles.json` files has it, and every profile's own limitations list still says "product-code taxonomy is not versioned by effective date". MISSION §10 and DATA_PROVENANCE defect 6 also still describe the taxonomy as unversioned, so the record simultaneously claims and denies versioning.
9. **Momentum calibration has no multiplicity control.** `momentum_calibration.json` applies a two-sided exact binomial at α=0.05 to 53 companies; 4 detections are expected to include ≈2.65 false positives. Only Philips (p=0.000505) survives Bonferroni at 0.05/53=0.000943. D-033 and R63 do not state this; R63's "the exact binomial test supports 4" is presented as a calibration count without the correction.
10. **Verification mutates the repository it verifies.** `round_end.py` writes `tools/round_end.json/.log`, `research/AUDIT.json/.md`; `final_audit.py` writes `research/FINAL_AUDIT.json`. A run therefore guarantees the 4–5 modified paths that make the gate's own repository-state step N/A, and `round_end` still exits 0. "The exit code is the completion claim" while the tree is dirty on every run.
11. **Claim maps verify prose, not data.** 61/88 main claims cite `DECISIONS.md`; 49/88 needles are < 6 characters; all 24 negative claims cite one aggregate. The tool is a drift detector for text, and the record's "machine-verified" language (R74, R85, R135) reads stronger than it is.
12. **Minor**: R59 reports Philips p=0.001 where the artifact has 0.000505 (3-dp rounding); `negative` counts are 29 by the audit's own counter against 27 in R155/COMPLETION_REPORT; `COMPLETION_REPORT` still says "main untouched at 7a639f7" while this worktree's main is `b2a14c0`.

Checked and **not** defective: the Dräger/Mindray counts (25/0, 90/0 linked — DATA_PROVENANCE defect 2 correct); the 510(k) linkage 16.9 %; the five-firm study's "no agent labels" claim (§7); the 6/6 snapshot verification and 0 leakage problems; the seasonality and figure numbers.

## 7. The five-company study: are its stated blockers honest?

Yes, on the evidence I could check. The study says it is blocked on three things and all three are documented and externally checkable: (a) the positive class must become a sustained change (pilot's rate detector cannot see a single-event entry: "0.85 events per cell-quarter, z ≈ 1.8 for a 0→1 move against a 3.5 threshold", `PILOT_RESULTS`/PHASE0 §6.4); (b) no earlier source survives the availability audit, so lead time is not measurable (S-007, S-021, S-022, S-028/29); (c) **the 69 packets need a named human reviewer**. `HUMAN_REVIEW_WORKSHEET.csv` has exactly 69 rows and every human column (`human_label`, `human_reason`, `independent_confirmation`, `reviewer`, `reviewed_at`) is empty; `ADJUDICATION_HUMAN_V1.json` does not exist; `CASE_PACKETS` are all `PENDING_HUMAN_REVIEW` with `final_label=null`. The agent adjudication is quarantined in a separate tier (`AGENT_PRE_ADJUDICATION`, 0 `Confirmed Shift`, 0 `False Signal`, 45 Uncertain, 18 Routine, 6 Not Assessable) with the explicit note that it "may not be used as ground truth, may not score the study's detectors" (S-030/S-031), and no downstream artifact uses it to score anything. The study's own defects are recorded, not hidden: a wrong first leak audit (S-005, S-011), a wrong first rubric field (S-031), a truncated lead-time sample described as "descriptive only; n=9, below the floor of 10" (S-024), and a fragile agent-built crosswalk that formally flips G1 (S-020). Two residual points: the 3.3-quarter median lead rests entirely on that agent-constructed crosswalk and cannot be treated as a finding (the study says so); and the negative paper's per-claim sources all resolve to one aggregate `CLAIMS_EVIDENCE.json`, so its 24/24 claim map is a one-artifact check.

## 8. Overall verdict and ranked threats

The record is unusually candid about its negatives, and its central quantitative claims mostly check out: of 33 load-bearing rows, 21 are exactly supported by artifacts at HEAD, including the one confirmed decision rule, the five retractions' control numbers, and the seasonality result, which I re-ran identically. The weaknesses are not invention; they are **staleness, over-claiming of reproducibility, and a verification stack that proves text agreement rather than data correctness**. Its single forward-looking asset is partly retrospective, and its flagship rolling-origin benchmark cannot be re-run. A clean clone verifies the prose but cannot regenerate a single event-lane result, and the gate cannot tell a present repository from an absent one. Treat the established findings as real at 2026-11-03, but do not treat "verified" as "reproduced", and do not treat the 25 prospective forecasts as clean out-of-sample evidence until the window-start bug is fixed and those 12 records are re-registered from a lane cutoff that precedes their outcome windows.

Ranked by threat to the record:

1. **12 of 25 "genuinely prospective" forecasts are partially backfilled** (outcome windows start at or before the registration lane cutoff); the filter in `register_forecasts.py` checks window end only, contradicting D-066's stated rule and the "25 genuinely prospective" line in four documents.
2. **`rolling_origin.py` is broken at HEAD** — R65/R67 are not regenerable, and no gate step would catch it; "every reported number is re-derivable" is false.
3. **Clean-clone reproducibility fails where it is claimed**: `final_audit.py` exit 1, 0/4 reproduced, because all event-lane artifacts need the uncommitted 1.65 GB of stores pinned only by SHA-256; meanwhile `round_end.py` exits 0 in a git-less tree, so the gate cannot prove "committed".
4. **The summary layer contradicts the artifact layer**: COMPLETION_REPORT, STATE.json completion_position, ROADMAP and MISSION §10 quote 913/910 tests, 157 commits, 152 rows, 73/67 decisions, 82+22 claims, five snapshots, and 656,048 replay values, against 1,074 / 184 / 155 / 74 / 88+25 / six / 1,107,081 at HEAD.
5. **The verification stack is a text matcher**: 61/88 claims cite the decision log, 49/88 needles are under six characters, all 24 negative claims trace to one aggregate, and the gate passes outside a repository — so "88/88 verified" does not imply the numbers are right, as R19 and R130 demonstrate.

Localised defects worth fixing next: R19's dead evidence pointer, R151's absent secondary numbers, R148's taxonomy stamp missing from all frozen snapshots, and no multiplicity control on the 53-company momentum tests.

## 9. Not checked (Unverified, explicitly)

* **R56** per-company profile totals (Medtronic 299/24, GE 274/5, Philips 224/11, Mindray 82/3, Dräger 16/2): the artifact exists and `selfcheck` passes, but I did not compare each of the five counts to `profiles.json`. Not contradicted.
* **R72** verdict stability (40 stable / 13 changed / 2 reversed): artifact `verdict_stability.json` exists and `verify_figures` re-derives 53 points from it, but I did not re-run `verdict_stability.py`.
* **R27** "0 of 104 cells": no committed output contains the 104-cell computation; the row cites a probe script, which I did not execute.
* **R8, R10, R30, R44–R54, R103–R105**: hiring/trial-lane infrastructure rows were checked only where they intersected the claims above; network-dependent collection and Wayback numbers were not re-collected.
* **Heavy historical re-runs** (`reverse_rd_v2`, `cycle2_coverage/run_cycle2.py`, `detect_v1/benchmark.py`, `entries*.py`) were not re-executed: they read the 1.3 GB store and run for minutes; their artifacts were inspected, not regenerated. This is why "not re-derivable in this audit" appears against some rows — it is not evidence they are wrong.
* **`data/*.sqlite` content provenance** (whether the local stores are the ones pinned by the snapshot manifests): I did not hash the 1.65 GB of stores against the manifest hashes. The manifests record `dd241bfe…` (research) and `46e51490…` (b040); verifying that the local files match is a one-line SHA-256 job I did not run.

---

### Commands actually run (all from `D:\DEPPSKK\worktrees\hist-v1`)

```
python tools/round_end.py                         # exit 0, 11 PASS / 0 FAIL / 1 N/A
python -m medradar selftest                       # exit 0, Ran 1074 tests in 36.225s / OK
python tools/final_audit.py                       # exit 0, 10/10 verifiers, 4/4 reproduced
python papers/verify_claims.py                    # exit 0, 88 claims / 0 failures
python papers/verify_claims.py --paper papers/PAPER_METHODS_v1.md --claims papers/CLAIMS_METHODS.json   # 25/0
python papers/verify_claims.py --paper papers/PAPER_NEGATIVE_v1.md --claims papers/CLAIMS_NEGATIVE.json # 24/0
python papers/verify_figures.py                   # exit 0, 5 figures / 0 failures
python papers/verify_figures.py --paper papers/PAPER_METHODS_v1.md                                      # 5/0
python papers/verify_figures.py --paper papers/PAPER_NEGATIVE_v1.md                                     # 5/0
python papers/check_layout.py                     # exit 0, 5 figures / 0 problems
python experiments/b026/validate_hiring_domain.py --out %TEMP%\histaudit\repro\validate_hiring_domain.json   # identical
python experiments/b026/confirm_entity_cells.py  --out %TEMP%\histaudit\repro\confirm_entity_cells.json      # identical
python experiments/b026/window_tradeoff.py       --out %TEMP%\histaudit\repro\window_tradeoff.json           # identical
python experiments/detect_v1/bin_sweep.py        --out %TEMP%\histaudit\repro\bin_sweep.json                 # identical
python experiments/b074/seasonality.py           --out %TEMP%\histaudit\repro\seasonality.json               # identical
python experiments/b050/rolling_origin.py        --out %TEMP%\histaudit\repro\rolling_origin.json            # EXIT 1, AttributeError
git show HEAD:<artifact> / git cat-file -e HEAD:<artifact>   # every audited value read from HEAD, not the worktree
python <own read-only SQL> data/medradar.sqlite  # 375,378 events, source/linkage counts (§5.1)
python <own read-only SQL> data/research.sqlite  # 55,090 events, 5,287/31,219 510(k) linked, 25/25 Draeger rows unlinked (§5.2)
python <own read-only SQL> data/medradar.sqlite  # 20,976 8-K, 1,360 linked; 31,619 trial rows all t_* tracks (§5.3)
python <own read-only SQL> data/registry.sqlite  # 25 nowcasts, 0 resolutions, all windows 2027-10-01 (§5.4)
git archive --format=zip HEAD -o %TEMP%\histaudit\clean.zip   # 1135 files, no data/, no out/
cd %TEMP%\histaudit\clean && python -m medradar selftest      # exit 0, OK (skipped=3)
cd %TEMP%\histaudit\clean && python tools/round_end.py        # exit 0, 11 PASS / 1 N/A (objective audit 12 PASS)
cd %TEMP%\histaudit\clean && python tools/final_audit.py      # EXIT 1, 9/10 verifiers, 0/4 reproduced
```
