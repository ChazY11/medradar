# `artifacts/correction_round_1/` — S-028-CORRECTION-1 machine-readable record

Everything in this directory was produced **after** the Phase 0-3 negative-result
commit (`51c7fce`) and is additive. No original artifact in `artifacts/` was
modified; see `ORIGINAL_EVIDENCE_MANIFEST.json` and `provenance_verification.json`.

| File | Producer | What it is |
|---|---|---|
| `ORIGINAL_EVIDENCE_MANIFEST.json` | `audit_24_provenance_and_freeze.py` (created first) | git blob SHA-1 + worktree SHA-256 of all 50 HEAD-tracked S-028 files at the start of the correction round |
| `randomisation_invariants.json` | `audit_20_randomisation_invariants.py` | minimal counterexample for the shipped swap, invariant audit of the shipped implementation (FAIL 72/72) and of the corrected nulls N1/N2 (PASS) |
| `audit_20_console.log` | same | console transcript of the above |
| `g2_corrected_H4q_N1.json` | `s028_g2_corrected.py --label H4q --model N1 --randomisations 40` | 40 corrected-null draws for the primary horizon, per-draw AP, deltas, per-origin invariants, frozen-control reproduction |
| `g2_corrected_H4q_N2.json` | same, `--model N2` | idem, activity- and time-constrained null |
| `g2_corrected_H2q_N1.json`, `g2_corrected_H2q_N2.json` | same, `--label H2q` | secondary horizon |
| `run_H4q_N1.log`, `run_H4q_N2.log`, `run_H2q_N1.log`, `run_H2q_N2.log` | same | console transcripts (every draw printed, nothing dropped) |
| `comparison_table.json`, `comparison_table.md` | `s028_correction_compare.py` | original vs corrected arms on identical test labels: B2, G1, G2-original, G2-N1, G2-N2 |
| `stats_audit_original.json` | `audit_21_statistics.py` | 143 numeric findings on the original artifacts with PASS/DISCREPANT/BUG verdicts and 13 documented code bugs |
| `stats_corrected_original.json` | `s028_stats_corrected.py` | corrected statistics on the original predictions (MDE, bootstrap, dedupe sensitivity, BH step-up) |
| `stats_corrected_g2.json` | `s028_stats_corrected.py --g2-model both` | corrected-G2 H2 re-derivation for N1 and N2, per window, with the 1/41 resolution statement |
| `leakage_audit.json` | `audit_23_leakage_correction.py` | 21 temporal-validity items (knowledge clock, truncation invariance, purge matrix, left truncation, shared variance, mapping reproducibility) |
| `false_positive_cases.json` | `audit_22_false_positives.py` | 90 per-case top-false-positive records with raw event IDs and failure classification |
| `provenance_verification.json` | `audit_24_provenance_and_freeze.py` (run last) | re-hash of all original files, pre-registration freeze-chain verification, frozen-DB check |

Reading order for a reviewer: `randomisation_invariants.json` →
`comparison_table.md` → `stats_corrected_g2.json` → `leakage_audit.json` →
`false_positive_cases.json` → `provenance_verification.json`.

Human-readable companions live one level up:
`RANDOMISATION_DEFECT_ANALYSIS.md`, `G2_CORRECTION_RESULTS.md`,
`STATISTICAL_REVIEW_CORRECTION.md`, `TEMPORAL_LEAKAGE_AUDIT_CORRECTION.md`,
`FALSE_POSITIVE_CASE_REVIEW.md`, `LITERATURE_CORRECTION_NOTE.md`,
`CORRECTION_REPORT_ZH.md`.
