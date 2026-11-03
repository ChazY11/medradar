# S-028 复现指南 / Reproduce

All S-028 results are regenerable from a **SHA-256-verified frozen input database** and a fixed
set of seeds. No network access is required after setup.

## 0. 环境

| item | value |
|---|---|
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.10 |
| CPU-only | no GPU used anywhere in this study |
| numpy | 2.5.1 |
| pandas | 3.0.3 |
| scikit-learn | 1.9.1 |
| scipy | 1.18.1 |
| networkx | 3.6.1 (not required by the pipeline; listed for inspection) |

The repository itself has no mandatory third-party dependency for this study
(`pyproject.toml` `dependencies = []`); only `numpy` + `scikit-learn` were added for the
vectorised learner and the gradient-boosting robustness check.

## 1. 冻结输入（必须先校验）

```
D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite
size   289,443,840 bytes
sha256 dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d
```

`code/s028_lib.py::verify_frozen_db` refuses to run if size or hash differ. The database is opened
**read-only** (`file:...?mode=ro`) everywhere; nothing in this study writes to it.

## 2. 一键复现顺序

```powershell
cd D:\DEPPSKK\medradar
$env:PYTHONIOENCODING="utf-8"
$C = "research/studies/graph_early_signal_s028/code"

# 0. protocol hashes (original freeze + Amendment 1)
python $C/s028_freeze.py
python $C/s028_freeze.py --suffix _amendment1

# 1. data feasibility + label census + fidelity self-check (no model)
python $C/s028_feasibility.py

# 2. mandatory harness validation: must print "OVERALL: PASS"
python $C/s028_experiment.py --mode validate

# 3. main pre-registered experiment (H=4q primary, H=2q secondary, R=40 randomisations)
python $C/s028_experiment.py --mode main --horizons 4,2 --randomisations 40

# 4. statistics, CIs, MDE, BH, stability, decision rules
python $C/s028_stats.py --horizons 4,2

# 5. verify every number quoted in the reports against the artifacts
#    must end with "checks run: 71, failures: 0"
python $C/s028_verify.py

# 6. re-print the result tables
python $C/s028_show.py
python $C/s028_show_stats.py
```

Determinism: every model run is seeded (`FastLogisticRegression` has no randomness;
`HistGradientBoostingClassifier(random_state=20261104)`; randomisation seeds `20261104 + r`;
bootstrap seed 7; MCMC-free). Re-running must reproduce the artifacts byte-identically except for
timestamps.

## 3. 独立数据审计的复现

The evidence auditor's scripts are separate and also read-only:

```powershell
python research/studies/graph_early_signal_s028/code/audit_10_provenance.py
python research/studies/graph_early_signal_s028/code/audit_11_time_clocks.py
python research/studies/graph_early_signal_s028/code/audit_12_relations.py
python research/studies/graph_early_signal_s028/code/audit_13_entity_mapping.py
python research/studies/graph_early_signal_s028/code/audit_14_track_coverage.py
python research/studies/graph_early_signal_s028/code/audit_15_research_coverage.py
python research/studies/graph_early_signal_s028/code/audit_16_positive_sample.py
python research/studies/graph_early_signal_s028/code/audit_17_crosschecks.py
python research/studies/graph_early_signal_s028/code/audit_18_assemble.py
python research/studies/graph_early_signal_s028/code/audit_19_verify_report.py
```

`audit_19_verify_report.py` re-checks every numeric token in
`RELATION_AND_TIME_EVIDENCE_AUDIT.md` against `artifacts/entity_time_audit.json`.

## 4. 产物清单

| artifact | produced by | contains |
|---|---|---|
| `artifacts/prereg_freeze.json` | `s028_freeze.py` | SHA-256 of the frozen protocol, before any model |
| `artifacts/prereg_freeze_amendment1.json` | `s028_freeze.py --suffix` | hash chain after Amendment 1 |
| `artifacts/feasibility.json` | `s028_feasibility.py` | every number in `DATA_FEASIBILITY.md`, plus the fidelity self-check |
| `artifacts/frozen_validation.json` | `s028_experiment.py --mode validate` | reproduction of the frozen cycle-2 benchmark (AP to <3e-7) |
| `artifacts/experiment_H4q.json`, `experiment_H2q.json` | `s028_experiment.py` | metrics per window and pooled, all specs, comparisons, G2 distribution |
| `artifacts/predictions_H4q.json.gz`, `predictions_H2q.json.gz` | same | per-row holdout predictions (gzip), enough to re-derive every statistic without refitting |
| `artifacts/statistical_validation.json` | `s028_stats.py` | bootstrap CIs (both clusterings), MDE, BH, stability, verdicts |
| `artifacts/entity_time_audit.json` | `code/audit_*.py` | independent provenance audit |
| `artifacts/literature_refs.json` | literature verifier | 44 references with verification status and fetched URLs |

## 5. 计算预算（实测）

Recorded automatically by `s028_experiment.py` in `times` of each experiment artifact:
`n_rows`, `n_features`, fit count, wall-clock seconds per spec, total seconds. The study is
laptop-scale by design: no GPU, no cluster, no paid data.

## 6. 常见复现失败与原因

| symptom | cause |
|---|---|
| `RuntimeError: frozen input mismatch` | the database was modified or replaced, or the worktree moved |
| `OVERALL: FAIL` in step 2 | the panel or leaner code was changed; do not interpret any S-028 result until it passes |
| different AP in the 4th decimal | a different numpy/sklearn version changed float summation; check the environment table |
| `ModuleNotFoundError: medradar` | run from the repository root, or set `PYTHONPATH` to the repo root |


