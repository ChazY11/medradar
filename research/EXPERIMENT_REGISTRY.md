# EXPERIMENT_REGISTRY — every experiment, its inputs, and its verdict

**Last updated:** 2026-11-03 · **Branch:** `research/full-history-v1`
This file registers the experiments of the current work unit (hist_v1 and the record-repair that accompanied it) in
the form the research directive requires: experiment ID, git commit, data version, target, train/test window, feature
set, model configuration, random seed, evaluation result, success status, conclusion/limits. The authoritative result
index for the whole programme remains `research/RESULTS/README.md` (R1–R167); prior experiments are indexed in §4.

**Commit note:** the IDs below were executed on branch `research/full-history-v1` from base `b2a14c0`; the commit that
contains each artifact is the commit that adds this file plus the artifact path (`experiments/hist_v1/manifest.json`
records the worktree head). Results are reproducible from the commands in each row.

---

## 1. Data versions

| alias | file | SHA-256 (first 12) | notes |
|---|---|---|---|
| `DS-MAIN` | `data/medradar.sqlite` | `445807cab60d` | openFDA device 510(k)/PMA full history + recalls/trials/8-K |
| `DS-ROSTER` | `data/research.sqlite` | `dd241bfec138` | 51-company roster, publication counts, frozen lane |
| `DS-TRIALS` | `data/b040_device_trials.sqlite` | `46e51490…` | device trials 2016+ (fusion only) |
| `TAX-CODETRACK` | `config/product_code_tracks.json` | `97c949963670` | 1,958 code→track entries |
| `TAX-TRACKS` | `config/tracks_device.json` | `074087461f5a` | 50 tracks; 38 observed |
| `ALIAS-5FIRM` | `config/hist_entity_aliases.json` | `94b53593f0dd` | Dräger/Mindray exact-string aliases |

Panel artifact: `out/hist_v1/panel.json` SHA-256 `10f8c00aff51ad061f6aa237449a7dfb571ccf57fe4ea6705623cda0fd350e20`
(474,686 B, 202 quarters, 53 companies, 38 tracks, 528 pairs, 14,704 material events). Git-ignored, regenerable.

## 2. hist_v1 experiment cells

| ID | target / risk set | horizon | train | test | features | model | seed | result | status | conclusion |
|---|---|---|---|---|---|---|---|---|---|---|
| `HIST-01` | first-ever track entry, `R_adj` | h=8 | candidate cells with `t'+8 ≤ t`, purged, weighted case-control cap 12,000 | 30 origins 1995-Q1…2024-Q1; 8,415 cells, 181 positives | 15 PIT features (groups A+B+C) | B0/B1/B2/B3 + L2 logistic (λ=1, lr 0.1, 120 epochs) | 20261103 | M1C mean AP **0.1137**; B1 0.0553, B2 0.0468, B3 0.0699; Δ(M1C−B1) **+0.0584**, CI **[+0.0020, +0.1213]**, p 0.045, MDE 0.0896; bootstrap OK; permutation p 0.0299 | **SUPPORTED (marginal)** | pre-registered primary criterion met; lower bound 0.002; not against B3 |
| `HIST-02` | M1C − B3 (two-way baseline) | h=8 | as HIST-01 | as HIST-01 | C | same | 20261103 | +0.0438, CI [−0.0184, +0.0957], p 0.198 | **not established** | incremental value over firm×track exposure not shown |
| `HIST-03` | first-ever track entry, `R_adj` | h=4 | as above | 31 origins 1995-Q1…2025-Q1 | C | same | 20261103 | Δ +0.0565, bootstrap **UNRELIABLE** (6/31 origins with zero positives), descriptive interval [−0.0020, +0.1143] | not quotable | 12-month horizon not confirmatory |
| `HIST-04` | first-ever track entry, `R_full` | h=8 | as above | 30 origins; 41,892 cells, 459 positives | C | same | 20261103 | M1C 0.0607 vs B1 0.0307, B3 0.0397; point Δ +0.0300, CI [+0.0128, +0.0699]; vs B3 +0.0210, CI [−0.0087, +0.0565] | **supported (secondary estimand)** | same pattern: persistence beaten, B3 not |
| `HIST-05` | `R_full` | h=4 | as above | 31 origins | C | same | 20261103 | point Δ +0.0204, CI [+0.0099, +0.0516] | supported (secondary) | consistent |
| `HIST-06` | ablation, feature groups A / B / C | h=8 | as HIST-01 | as HIST-01 | A firm only / B +industry / C +adjacency | same | 20261103 | A 0.0489 (Δ −0.0064 vs B1), B 0.0905 (+0.0352), C 0.1137 (+0.0584) | **mechanism result** | track tempo + adjacency carry the signal; firm momentum alone is below persistence |
| `HIST-07` | fusion, C vs D | h=8 | as above | 9 origins 2016+; 2,902 cells | +trial (track/adjacent) + publication (annual) | same | 20261103 | C 0.0401 vs D 0.0348; Δ −0.0053; bootstrap UNRELIABLE; join rates 0.786 / 0.910 | **NOT SUPPORTED (H2)** | no cross-source gain; consistent with earlier annual-publication ablation |
| `HIST-08` | label-permutation null | h=8 | permuted training labels | as HIST-01 | C | M1C + B1 refit per permutation | 20261103 | observed +0.0584 vs null mean +0.0239 (sd 0.0129, max 0.0667); **p = 0.0299** (6/200; floor 0.005) | **positive robustness** | ranking advantage not a scramble artefact |
| `HIST-09` | H5 lead-time frontier | h=8 | — | 94 entries in `R_adj` (of 255 in window) | M1C scores, per-origin 90th-pct training threshold | budgets 1/5/10/20 % | 20261103 | 1 %: 9/94, precision 0.206, median lead 5 q, 5.9 FA/1,000; 5 %: 19/94, 0.137, 6 q; 10 %: 24/94, 0.094, 6 q, 50.6; 20 %: 38/94, 0.073, 98.3 | **descriptive** | earlier warning trades against reliability; 56–85 misses per budget |
| `HIST-10` | five-firm descriptive timelines | — | — | 1976-Q2…2026-Q2 | none (counts) | none | — | Medtronic 32 tracks (last new 2012-Q4), GEHC 11 (2000-Q4), Philips 15 (2025-Q2), Dräger 4 (2014-Q4), Mindray 3 (2011-Q1) | **descriptive** | portfolios saturated; 161/255 entries are new-category |
| `HIST-11` | leakage controls | — | — | seeded 300-cell replay | all 15 | independent linear-scan replay | 20261103 | label purge 0 violations; replay mismatches **0/300** (and 0/102,441 in the exhaustive check) | **verification** | features PIT-consistent after the fix |
| `HIST-12` | first full run (VOID) | h=8 | as HIST-01 | as HIST-01 | C | same | 20261103 | pre-fix: 7,556 candidates / 110 positives; replay **184/300** mismatches; bootstrap UNRELIABLE; H1 UNRELIABLE | **VOID — not published** | unsorted company-category index corrupted risk set and features (D-077, R167) |
| `REPAIR-01` | prospective forecast set | — | — | lane through 2026-Q3 | — | `register_forecasts.py` window-start filter | — | 25 → **13** prospective (19 excluded); hash `8ac0b8df…`; maturities 2027-Q3…2028-Q1 | **CORRECTED** | D-075; supersedes R130 |
| `HIST2-A` | domain-level entry, `R_dom`, h=8 (primary) | 2026-11-03 | frozen hist_v1 panel → 22-domain panel (`out/hist_v2/domain_panel.json`, SHA `44c115c2…`) | 21 origins 1995-Q1…2015-Q1; 15,233 cells / 252 positives | 15 domain-level PIT features | B0–B3 + L2 logistic (λ=1, lr 0.1, 120 epochs); boot 2,000 / perm 200, seed 20261103 | M1C 0.0775 vs B1 0.0435; Δ +0.0340 CI [+0.0215,+0.0661] MDE 0.0316; permutation p 0.004975; criterion met, POWERED | **SUPPORTED (powered)** | D-083, R181; `experiments/hist_v2/` |
| `HIST2-B` | decisive secondary M1C − B3 | h=8 | as HIST2-A | as HIST2-A | as HIST2-A | paired bootstrap | Δ +0.0156, CI [−0.0107,+0.0445], p 0.212, MDE 0.0389 | **not significant** | incremental value over firm×domain exposure not established (R182) |
| `HIST2-C` | feature ablation A/B/C; era split; h=4; holdout | h=8/h=4 | as HIST2-A | as HIST2-A | A firm-only, B +domain tempo, C +adjacency | as HIST2-A | A 0.0515 (+0.0080), B 0.0812 (+0.0377), C 0.0775 (+0.0340); eras +0.0464 / +0.0227; h=4 Δ +0.0432 [+0.0214,+0.0692]; holdout descriptive +0.0095 | **mechanism (unit-dependent)** | domain tempo carries the signal; adjacency does not (R183) |
| `HIST2-D` | lead-time frontier + leakage | h=8 | as HIST2-A | 133 entries in `R_dom` (of 148) | M1C scores, per-origin 90th-pct threshold | budgets 1/5/10 % | 14/133 (precision 0.106, 5 q), 41/133 (0.079, 7 q), 58/133 (0.058, 6 q); purge 0, replay 0/300 | **descriptive (H5)** | R184 |
| `BACKLOG-029` | CIK-based deterministic 8-K linking (B-029) | 2026-11-03 | data/medradar.sqlite 8-K lane + SEC_CIK registry (57 unambiguous CIKs) | all 20,976 8-K events | — (linking) | exact integer CIK equality; ambiguous CIKs refused; names never used | — | 826 events equal exactly one curated CIK and all 826 are already linked → **0 new links**; 19,616 unlinked are 1,530 non-roster registrants; precision sample 60/60 PASS; 0 contradicted existing links | **closed as measurement (premise falsified)** | D-080, R178; `experiments/b101_cik_link/` |
| `BACKLOG-021` | cross-source lead/lag (B-021, frozen b103) | 2026-11-03 | frozen hist_v1 panel + financial_facts + market_bars + publication_counts, 2017-Q1…2025-Q4 | 36 quarters, lags −8…+8 | per-company z-scores; pooled r(k); k*=argmax over k=1..8 | company-clustered bootstrap 2,000; circular-shift permutation 1,000; Holm across 3 sources; seed 20261103 | financial k*=1 r −0.0441 p 0.683 MDE 0.072; market return k*=5 r −0.0278 p 0.967 MDE 0.051; publication k*=1 r −0.0387 p 0.614 MDE 0.057; Holm 1.000 all; procurement NOT_EVALUABLE | **well-powered negatives (no lead)** | D-081, R179; `experiments/b103_leadlag/` |
| `BACKLOG-041` | publication-lag sensitivity of the hist_v1 fusion result (B-041, frozen b104) | 2026-11-03 | frozen hist_v1 panel + research.sqlite publication_counts + b040 trials; hist_v1 C-vs-D evaluation reused | 9 origins 2016-Q1…2024-Q1; lags 0/14/30/90 days | hist_v1 C and D feature sets with the publication knowledge date shifted | frozen hist_v1 evaluator re-used; no new sampling | 0/14/30 d: join 0.786, AP(C) 0.0401, AP(D) 0.0348, Δ −0.0053 (exactly hist_v1); 90 d: join 0.200, Δ −0.0017; verdict unchanged | **negative robustness (conclusion survives)** | D-082, R180; `experiments/b104_publag/` |
| `PRE-01` | hist_v2 feasibility + pre-registration (no model) | 2026-11-03 | frozen hist_v1 panel (SHA `10f8c00a…`), 22-domain mapping | 21 origins 1995-Q1…2015-Q1, h=8 | — (feasibility only) | none fitted | — | domain unit: **12.0 positives/origin, 725.4 candidates/origin, base rate 1.7 %** (252 total) vs hist_v1 primary 6.0 positives; includes the 161 new-category entries | **frozen pre-registration** | R176/R177, `research/protocols/hist_v2_preregistration.md`, `experiments/hist_v2/feasibility.json`; run next round |
| `FINAL-01` | final Target B adjudication under owner authorisation | 2026-11-03 | owner-authorised external AI review (69 packets) + frozen worksheet | all 69 packets | — (adjudication, not modelling) | `experiments/b100/finalise_ai_adjudication.py` (validating; refuses without dated authorisation / fabricated Confirmed Shift / label overwrite) | — | **0/69 Confirmed Shift** (0.0 %, Wilson-upper 95 % **5.3 %**), 8 False Signal, 52 Routine, 9 Uncertain; H1/H2 NOT_EVALUABLE, H3 descriptive, H4 untestable | **final negative result** | D-079, S-035, R172–R175; human sign-off waived for this study only; labels `human_truth=false` |
| `INGEST-01` | external AI review of the 69 five-firm packets | — | human worksheet (frozen, 69 rows) + review worksheet/json | all 69 packets | — (labelling task, not modelling) | `experiments/b099/ingest_external_ai_review.py` (validating ingester) | — | labels Routine 52 / Uncertain 9 / False Signal 8 / Confirmed Shift 0; halt rule triggered; 8/9 small-sample pairs false signals; 13 left-censored novel entries; 5 manufacturing notices; 44/69 changed from the earlier agent rubric (descriptive only; not blind) | **non-human tier ingested; Target B stays unlabelled** | D-078, S-034, R168–R171; the nine-event lead-time description is withdrawn |
| `REPAIR-02` | rolling-origin reproducibility | — | — | 12 origins 2019-12…2025-06 | — | `b050/rolling_origin.py` date-type fix | 7 | re-run == committed JSON (`identical: True`) | **FIXED** | D-076; closes audit defect 2 |

## 3. Why HIST-01 is "supported" but not "strong"

The pre-registered criterion was a 95 % CI excluding zero on the mean per-origin ΔAP, and it is met
([+0.0020, +0.1213]). The same result is *thin*: the lower bound is 0.002, the MDE (0.0896) exceeds the observed
effect (0.0584), the two-way exposure baseline B3 is not beaten, and 161 of 255 entry events are outside the primary
risk set by construction. The material is recorded as **supported, marginal**, and the report says so in its first
paragraph. Any stronger claim must come from a new pre-registration (§7 of `RESEARCH_STATE.md`), not from re-reading
this one. HIST-12 records the void run and its cause so that the corrected numbers cannot be confused with it.

## 4. Prior experiments (index only)

The programme's earlier experiments are registered in `research/EXPERIMENTS.md` and indexed with verdicts in
`research/RESULTS/README.md` (R1–R155). Load-bearing ones and their artifacts:
`experiments/detect_v1/` (detection frontier), `experiments/b026/` (alert-shape, density, promotion rule),
`experiments/b027/` (profiles, snapshots, momentum calibration), `experiments/b040/` (device trials, lag analysis),
`experiments/b050/` (rolling origin), `experiments/b067/` (pipeline evaluation), `experiments/b068/` (forecasts),
`experiments/b073/` (lane inventory), `experiments/b074/` (seasonality), `experiments/reverse_rd_v1|v2/`
(continuation/entry forecast targets), `research/studies/early_signal_5firms/` (five-firm study, blocked on human
labels). Their data versions are pinned in `experiments/*/data_provenance.json` and the snapshot manifests; their
reproduction status is audited in `research/audits/initial_research_audit.md` (21 verified, 8 partial, 2 unverified,
2 failed as of 2026-11-03).

## 5. Registering a new experiment

Append a row to §2 before running it: ID, target/risk set, horizon, train/test windows, features, model, seed. After
running, fill result/status/conclusion from the committed artifact only — never from memory. A result whose artifact
is not committed is not registered.




