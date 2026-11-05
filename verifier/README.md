# Verifier index

- 2026-11-01 — `v1`: initial acceptance criteria for legacy regressions, real SEC/procurement ingestion, point-in-time features, rolling-origin evaluation, forecast registry and reproducible delivery. Verify with `python3 verifier/v1/verify.py`; append every result under `verifier/runs/`.
- 2026-11-05 — `v2`: S-031 hiring-capability audit. Adds deterministic 100-job stratified sampling, four-axis ontology, verbatim prelabel quotes, 994/992/983 count reconciliation, ≥15 disagreement cases, H1–H3 falsifiability and delivery completeness. Does not replace v1. Verify with `python3 verifier/v2/verify.py`; append every result under `verifier/runs/`.
