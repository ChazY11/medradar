# PHOENIX-001 acceptance criteria v2

Created: 2026-11-06. This version adds PHOENIX-specific checks; v1 remains the legacy regression gate.

1. Work is delivered on `research/phoenix-001-external-methods`; `main` and all frozen databases/results are not modified.
2. `experiments/phoenix_001/asset_audit.json` records the actual runtime, expected database paths, existence, size, read-only access and SHA-256 when an asset exists. Missing assets remain explicitly missing; no substitute data are generated.
3. Exactly 13 named external projects have machine-readable audit records. Every record contains type, official URL, licence/use terms, methods, data dependencies, accessibility, local run result, resource needs, overlap, transferable methods, limitations/leakage risks, reproduction evidence and a justified final decision (`ADOPT`, `ADAPT`, `STUDY_ONLY`, `REJECT`, or `BLOCKED`). Commercial marketing is never labelled scientific validation.
4. REA documentation identifies the inspected upstream repository/package, stable version, licence, release evidence, supply-chain/resource review, proposed MCP changes, owner-approval state, actual tool list if connected, smoke-test evidence, timing/resource observations and honest failures. No unreviewed install script is executed.
5. The reproduction report distinguishes source execution, independent implementation, paper-only analysis, failure and access restriction. Each claimed run has a command, exit code, timestamp and saved log under `experiments/phoenix_001/logs/`.
6. H1–H10 are frozen before outcome interpretation with entity/event definitions, sample scope, information cutoff, prediction window, baselines and primary metrics. Each ends as supported, refuted, inconclusive, blocked or not testable, with a reason. Missing databases cannot be replaced by synthetic success claims.
7. Every completed predictive comparison uses identical temporal boundaries, reports sample and independent-event counts, prevalence, AP/PR-AUC, Precision@K, Recall@K, false-positive burden, lead time where measurable, uncertainty and year/company/track stability. Duplicate devices/applications/trials and derived copies cannot cross train/validation partitions. S-028/S-029 entity, left-censoring, time-proxy, duplication and cross-source risks are addressed.
8. Descriptive findings, retrospective temporal associations, conservative simulated prediction and independent prospective validation are labelled separately. Neither category 2 nor 3 is presented as category 4.
9. Any integration candidate has clear provenance/licensing, local reproduction, MedRadar-data reproducibility or an explicit data block, incremental value/defect repair, isolation from production, automated tests and reproduction instructions. Third-party projects are not wholesale copied into the repository.
10. Final documents cover the external map, reproduction report, fair method comparison, candidate modules, research gaps/opportunities and a 1–3 direction roadmap with cost and failure risk. A Draft PR exists and is not merged; its summary includes unresolved issues and next research questions.
11. `python3 verifier/v1/verify.py` remains green, and `python3 -m pytest tests/test_phoenix_001.py -q` passes. Every verifier invocation appends timestamped command, exit code and machine-readable results under `verifier/runs/`.

Verification commands:

```bash
python3 verifier/run_v2.py
python3 verifier/v1/verify.py
```
