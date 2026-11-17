# ENGINEERING START HERE

This is the single entry point for a new engineer or a new agent working on MedRadar. Read it
before reading the code. It states what is authoritative, what is history, and where a change
belongs.

Updated: 2026-11-18 (REFOUNDATION-004).

## 1. What MedRadar is, in two sentences

MedRadar turns public medical-technology evidence (FDA regulatory records, papers, official
company statements) into traceable, explained intelligence about monitoring technology: who is
building what, what the evidence is, what it does not support, and when it became knowable.

## 2. Which branch is "the product"

- **origin/main** (86311b1) is the published research front page and the SCIENCE-001 study. It does
  **not** contain the product or the radar lane. Do not start from main if you are changing the
  product.
- **The product line is a draft stack** (all open, none merged at the time of writing):
  #46 PRODUCT-001 -> #47 PRODUCT-002 -> #48 PRODUCT-003 P0 -> #49 PRODUCT-003 -> #50 DATA-001 ->
  #51 DATA-002 -> #52 DATA-003 -> #53 PRODUCT-004 -> #54 RADAR-001. Each PR's base is the previous
  PR's head. Read the tip of the stack, not main.
- **REFOUNDATION-004** (this round) is one reviewable layer on top of #54 on branch
  `refoundation/004`. It does not rebase or merge the drafts.
- **Deployed vs draft** is tracked in the change documents under docs/ (for example
  docs/radar/LAUNCH_001_ACCEPTANCE.md records the deployed radar SHA and docs/data/data_003/
  records the data pipeline deployment). Do not assume a merged PR equals a deployment.

## 3. The three lanes, and which one you are in

| Lane | If your task is about... | Authority | Do not touch |
| --- | --- | --- | --- |
| Live intelligence (radar) | sources, observation ledger, relevance, technology graph, intelligence feed | `medradar/radar/*`, (data/radar/radar.db) | — |
| FDA evidence product | company/device dossiers, regulatory snapshots, briefs, exports, the product workbench | `medradar/data_pipeline/*` + `medradar/product/*` + `web/src` (snapshot store) | the radar ledger |
| Legacy research/market | historical studies, paper trading, dashboards, forecasts | `medradar/db.py` + the modules reachable from `python -m medradar collect/analyze/report/trade` | — (frozen: do not extend) |

If a requirement crosses lanes, it needs an explicit design note; the lanes do not share a data
contract yet (see docs/refoundation/004/ARCHITECTURE_DECISIONS.md ADR-007).

## 4. The core business flow (radar)

```
source adapter fetch -> RawRecord -> ledger.record_observation
   -> observation / observation_version / observation_change (append-only history)
   -> observation_mapping + observation_facet (rule layer: org/product/topic candidates)
   -> assessment (dimensions + decision) -> observation_admission (append-only) + admission_current
   -> graph assertions (evidence ids, known_at/valid_at)
   -> API feed / graph / detail -> web UI
```

Non-negotiable invariants (enforced in code and in SQL triggers, tests named after them):

1. An observation, its versions and its first_observed_at are never rewritten.
2. An admission decision is never rewritten; a re-judgement is a new row.
3. A rejected record is not deleted; it keeps its reason.
4. A coarse date is never rendered as an exact instant.
5. A topic match never becomes a capability claim.
6. Discovery stores what the source said; relevance is a decision, not a storage filter.

## 5. Where a change belongs

| You want to add... | Change these files | Test file |
| --- | --- | --- |
| A new data source | `medradar/radar/adapters/<name>.py` + one entry in `adapters/__init__.py` + `config/radar/sources.json` | `tests/test_radar_parsers.py`, `tests/test_radar_pipeline.py` |
| A new technology topic or product code | `config/radar/topics.json` (data, not code) | `tests/test_taxonomy.py` |
| A relevance rule | `medradar/radar/assessment.py` (single entry point). Bump ASSESSMENT_VERSION | `tests/test_radar_integrity.py` + regenerate the quality report |
| A new admission dimension | assessment.py vocabulary + `observation_admission.dimensions` (JSON) | integrity tests |
| An API endpoint (intelligence) | `medradar/radar/api.py` | `tests/test_radar_api.py` |
| An API endpoint (product) | `medradar/product/api.py` | `tests/test_device.py` / `tests/test_product*` |
| A UI page | `web/src/pages/*` + route in `web/src/App.tsx` + `web/src/api/*` types | build + browser check |
| A graph query | `medradar/radar/graph.py` | `tests/test_radar_graph.py` |
| A database change | `medradar/radar/ledger.py` SCHEMA + a migration path + SCHEMA_VERSION bump | `tests/test_radar_ledger.py`, integrity migration test |
| An evaluation label set | new frozen JSON under `docs/refoundation/.../quality/` with sha256 | `scripts/evaluate_relevance.py --check` |

## 6. Local start

```bash
python -m pip install -e '.[dev,product]'        # from the repository root
python -m pytest tests -q                        # full suite
python -m medradar radar --help                  # radar commands
python -m medradar radar run --source pubmed     # one source cycle (network)
python -m medradar radar status
python -m medradar web --port 8787               # product workbench (committed snapshot)
python -m medradar radar api --port 8788         # radar API
```

Data locations: radar ledger `data/radar/radar.db` (override with `MEDRADAR_RADAR_DIR`); product
snapshot `medradar/product/snapshot/` (override with `MEDRADAR_DATA_DIR`).

## 7. Data updates and relevance

1. `python -m medradar radar cycle` (or the systemd timer) runs adapters + advance + admissions.
2. A rule change means: edit assessment.py, bump `ASSESSMENT_VERSION`, run the cycle (or
   `radar reproject`). The old decisions stay in `observation_admission`; `admission_current`
   shows the newest. The rules digest difference triggers the re-judgement automatically.
3. Regenerate the quality artefacts: `python scripts/evaluate_relevance.py --data-dir <dir>
   --labels <sample> --json ... --markdown ...`, then `--check` in CI.
4. Never hand-edit a number in a quality report. It is generated.

## 8. Safe migration and rollback

- Backup first: `python -m medradar radar backup --destination <dir> --json` (verified copy).
- Schema version lives in `meta.schema_version`. Opening a read-write ledger migrates v1/v2 -> v3
  (status-history key, then admission append-only). A read-only open refuses to migrate and says so.
- The migration copies rows forward and drops the old table only after the copy; a failure leaves
  the old table in place.
- Rollback of code: redeploy the previous SHA; the new tables are additive/inert for older code
  except `observation_admission_latest`/`admission_current` which older code ignores.
- Rollback of data: restore the verified backup; never delete a ledger file in place.

## 9. Deploy (not performed by this round)

Follow docs/radar/LAUNCH_001_RUNBOOK.md and docs/data/data_003/DEPLOYMENT_CHANGE_REQUEST.md:
immutable release tree, `DEPLOYED_SHA` file, systemd units, backup timer, restore-check drill.
Record the deployed SHA and the backup digest in the change document.

## 10. Historical claims that must not be repeated

- **Do not claim the system predicts the future.** S-028, S-029 and SCIENCE-002 are negative
  results (no validated early-warning signal). The PHOENIX line returned NO-GO.
- **Do not claim a cleared product equals a capability.** A 510(k) is a regulatory event, not proof
  of an algorithm.
- **Do not claim the QA-002 71.2%/75.5% numbers are the current quality.** They measured the old
  rules. The current held-out numbers are in docs/refoundation/004/quality/QUALITY_HELDOUT.md.
- **Do not call the labels "independent human evaluation".** They are one reviewer's auditable
  adjudication against a frozen rule.
- **Do not claim live continuous discovery was re-verified this round.** The machinery is tested;
  a fresh live collection was not run.

## 11. Known open debt (short list)

See docs/refoundation/004/REPAIR_PLAN.md. The five that matter: no recall adapter in the radar,
Crossref watermark can jump into the future, Dräger records have no dates, two organization
registries, and product/api.py is one 949-line function.
