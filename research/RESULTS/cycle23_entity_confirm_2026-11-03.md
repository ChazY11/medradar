# Cycle 23 — the promotion rule confirmed at a finer unit; the "same cells" caveat narrows (2026-11-03)

**Status:** completed. Closes B-055. Pre-registered in D-047, outcome in D-048.
Artifacts: `experiments/b026/confirm_entity_cells.py`, `confirm_entity_cells.json`, `confirm_entity_cells.log`.

## Why this test

The D-043 confirmation used fresh injection months but the **same 65 company-level cells**, and the paper
carries that caveat. The obvious next test is a **different unit of analysis**: the legal entity rather than
the curated company. Each company cell aggregates one to thirty entities, so entity cells are finer, more
numerous, and exercise a different aggregation.

## Result: CONFIRMED at entity level

6,841 entity-track cells → **191 eligible** (same floors) → three fresh origins per cell → **1,196 scored
alerts**.

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike | 277 | 39 | 37 | **0.785** |
| level | 0 | 373 | 50 | 0.882 |
| ramp | 3 | 368 | 49 | 0.117 |

- balanced accuracy **0.594** (95 % CI 0.583–0.616), floor 0.50 → pass
- sustained-change precision **0.917** (95 % CI 0.909–0.941), floor 0.85 → pass
- sustained base rate **0.705**; CI lower bound 0.909 exceeds it → pass

## What it means

The numbers are almost identical to the company-level confirmation (0.584 and 0.914): balanced accuracy
differs by **0.010**, precision by **0.003**. A rule that survives at a unit five times finer with essentially
the same accuracy is **not an aggregation artefact**.

## What it does not mean

Entity cells **nest inside** company cells, so this is not a second independent sample — it tests aggregation
level, not independence, and the pre-registration said so in advance. The scope limit also stands: **ramp
recall falls to 0.117**, so three-way shape recovery remains unrecovered at either unit.

## Effect on the programme's one positive result

`STATE.json` records the rule as confirmed at **both units**, and the paper's caveat narrows from "the same
cells were reused" to "a nested unit, not an independent sample". The product's alert machinery is unaffected:
it runs at the company level, which is the unit already confirmed.

## Verification

- `python experiments/b026/confirm_entity_cells.py` → exit 0, 2.4 s, deterministic (seed 4040).
- Bootstrap clustered by company (2,000 replications).
- `python -m medradar selftest` → 862 tests OK (skipped=3).
