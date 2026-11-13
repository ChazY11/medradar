# Verifier index

- 2026-11-01 — `v1`: initial acceptance criteria for legacy regressions, real SEC/procurement ingestion, point-in-time features, rolling-origin evaluation, forecast registry and reproducible delivery. Verify with `python3 verifier/v1/verify.py`; append every result under `verifier/runs/`.

- 2026-11-06 — `v2`: PHOENIX-001 acceptance gate covering read-only asset hashing, 13-project evidence audits, REA supply-chain/deployment honesty, frozen H1–H10 protocols, temporal/leakage controls, reproducible comparisons, candidate modules and Draft PR delivery. It supplements rather than replaces v1. Verify with `python3 verifier/run_v2.py`; every run appends JSON and stdout records under `verifier/runs/`.
