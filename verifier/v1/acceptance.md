# Acceptance criteria v1

1. `clinical_hold`, `refuse_to_file`, `crl`, `pre_submission`, and designations are distinct event categories; a De Novo pre-submission is never counted as an approval.
2. Historical records without a real public timestamp cannot become tradeable through an `event_date` fallback; unknown timing is excluded and visible in metrics.
3. Extreme raw returns are explicitly flagged for audit, and robust event-study output exposes exclusion/flag counts rather than hiding them behind winsorisation.
4. An official FDA advisory-committee source can be collected into the unified event model with deterministic parsing and tests; pending 510(k)/PMA surveillance is not fabricated.
5. Device intelligence covers hierarchical domains including life support, IVD, neuromodulation/BCI, cardiovascular, imaging, robotics, SaMD, renal/diabetes, and other major clinical areas, with machine-readable frontier keywords and tests.
6. New capabilities are reachable through CLI and documented in both READMEs, CHANGELOG, ROADMAP, METHODS/SCHEMA as appropriate; version references are consistent.
7. All original and new offline tests pass; offline demo, calibration replay, compileall, and install checks pass.
8. The change is delivered as a reviewable branch and pull request, with verification evidence and no credentials or generated bulk data committed.
