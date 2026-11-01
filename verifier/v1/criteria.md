# MedRadar Market-to-R&D acceptance criteria v1

Created: 2026-11-01.

1. The original FDA, clinical-trial, SEC-event, analytics and trading tests remain green.
2. SEC Company Facts parsing keeps consolidated facts distinct from segment/product revenue, preserves `filed` as knowledge time, and reconstructs amendments point-in-time.
3. USAspending collection stores award identifiers, buyer, supplier, value, award/performance dates, source, raw provenance and an explicit snapshot-quality warning. Award value is never called revenue.
4. Cross-domain company links require deterministic CIK/ticker or normalized-alias evidence; ambiguous names stay unmatched.
5. Every feature row has an information cutoff. Automated tests prove that facts first filed after the cutoff cannot change features or labels.
6. The baseline predicts a defined future FDA milestone with rolling-origin training and an untouched final time holdout. Random temporal splitting is not used.
7. Reports include PR-AUC, Brier score, ECE, FPR, Precision@K, lead time and horizon stability. Empty or immature evaluations produce `null`, not invented metrics.
8. Procurement snapshots that cannot reconstruct first-publication time are excluded from historical predictive-gain claims.
9. Horizon forecasts contain model version, cutoff, horizon, probability, uncertainty, evidence, counter-evidence and a machine-checkable verification condition.
10. Real-data runs save source counts, retrieval timestamps, configuration, quality warnings and results without committing raw bulk data or model weights.
11. Delivery is on a non-main branch with reproducible commands and an honest account of negative or unavailable results.

Verification command: `python3 verifier/v1/verify.py`.
