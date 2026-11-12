# EVIDENCE_STORE_COMPARISON — Phase 0 decision preparation

- **Task:** REFOUNDATION-002 / `task-8` (evidence-store architecture comparison)
- **Author:** `evidence-architect`
- **Branch:** `research/evidence-architecture-002` @ `b2a14c0` (`origin/main` = `b2a14c0`, fetched 2026-11-12)
- **Scope:** comparison and decision preparation only. No data is migrated, no schema on `main` is touched, no branch other than this one is written. This document does **not** execute REFOUNDATION-001's "TKG is the single canon" recommendation.
- **Status labels used throughout:**
  - `[FACT]` — read from code/commit at the pinned SHA, or printed by the committed probe. Every row cites `file:line`, a probe key, or a command.
  - `[INFERENCE]` — a conclusion drawn from facts; labelled with what it rests on.
  - `[UNVERIFIED]` — cannot be settled from this worktree (missing data snapshot, branch not merged, external consumer).
  - `[RECOMMENDATION]` — a conditional decision proposal, explicitly reversible by evidence.
- **Evidence artefacts (committed next to this file):**
  - `_evidence/evidence/probe_store_structure.py` — runnable, stdlib-only, offline structural probe.
  - `_evidence/evidence/store_structure.json` — full machine-readable probe output.
  - `_evidence/evidence/store_structure.txt` — human-readable probe output.
  - Reproduce: `python docs/refoundation/phase0/_evidence/evidence/probe_store_structure.py --json-out docs/refoundation/phase0/_evidence/evidence/store_structure.json --text-out docs/refoundation/phase0/_evidence/evidence/store_structure.txt`
  - Probe environment printed by the run: Python `3.12.10`, SQLite `3.49.1`, exit code `0`, `errors: 0`.

> **Reading rule.** Structural facts below come from the probe where it is possible to probe (main-branch classes are instantiated; branch-only stores are built from their DDL constant extracted with `ast` from `git show <ref>:<path>` and executed in `:memory:` — branch Python is never imported). A claim that the probe does not certify is not written as `[FACT]`.

---

## 0. One-paragraph answer

There are **seven modules on `main` that own SQLite DDL** and assemble three databases: `data/medradar.sqlite` (17 tables from `db.py` + 7 from `intelligence/storage.py` + one each from three `intelligence/sources/*` modules), `data/tkg.sqlite` (6 tables), and the forecast registry file (5 tables). Three branch-only stores add versioned evidence models: ATLAS (21 tables, `schema_migrations`), the DATA-EXPANSION-001 staging store (7 tables), and the Observatory ledger (13 tables, 17 triggers). Only TKG, the forecast registry and the Observatory ledger enforce append-only **physically** (probe: 7 / 10 / 17 triggers); the central `events` table is overwritten in place (`db.py:537`, probe `replaced_in_place=True`), has no revision table, no schema version and no foreign keys. The decisive measured failure of the "TKG canon" option is already in the repository: a real 55,090-row import into TKG dropped **55,090 / 55,090** `public_time` values because legacy `events.available_at` is stored naive (`2024-03-05T00:00:00`) and TKG rejects naive timestamps. The honest recommendation is therefore **not** one canon now: harden the `events` lane as the immediate, reversible canon (C) and promote ATLAS-style evidence records (B) only if the identity bridge experiment passes; TKG stays a derived index.

---

## 1. Definitions (so the counts in §2 are not rhetorical)

| Term | Definition used here | Why it matters |
|---|---|---|
| **Store** | A durable place where records asserted as observed external facts are written and read by research code. A module that only reformats in memory is not a store. | Prevents counting `analyze.py`/`stats.py` as "evidence implementations". |
| **Evidence record** | One row/document that says "source S said fact F about entity E at time T, and here is the provenance". | The unit that a canon must version. |
| **Canon** | The store that a future research claim is allowed to cite without cross-checking another store. | The Phase-0 question is *which store*, not *whether*. |
| **Ledger** | An append-only record of *decisions/attempts* (idempotency keys, resolutions, skips, runs) rather than of source facts. | Distinguishes TKG's `idempotency` table from TKG's `nodes`. |
| **Registry** | A curated map from an external string/identifier to an internal key that gates ingestion or attribution. | §2.3 shows the prior audit's "8 source registries" depends on this definition. |
| **Resolver** | Code that turns a raw source string/identifier into a canonical key, with an explicit confidence and failure mode. | §2.2. |
| **Mutation** | Any write that changes the content of an already-recorded row (UPDATE / DELETE / `INSERT OR REPLACE` / `DELETE`+`INSERT`). | What "immutability" must mean. |

---

## 2. Verification of the prior audit claims (not assumed)

The Phase-0 brief listed six numeric claims. Each was re-derived from code and the probe at `b2a14c0`; the verdict is the reproducible answer, not a confirmation.

| # | Prior claim | Verdict at `b2a14c0` | Evidence |
|---|---|---|---|
| C1 | `main` has **6 evidence implementations** | **`[FACT]` 7 DDL-owning modules; 8 external-fact record families.** The count 6 is reproducible only if `db.py`'s `live_alerts` lane is merged into `events` and the three source-private tables are merged into one. So 6 is a *defensible grouping*, not a unique count. | probe `main_ddl_collisions.per_module` keys: `medradar.db`, `...intelligence.storage`, `...sources.market_data`, `...sources.patents`, `...sources.publications`, `...tkg.store`, `...forecast_registry`; §3.1 inventory |
| C2 | `main` has **6 identity resolvers** | **`[FACT]` exactly 6 on `main` under the §1 definition** (plus 2 branch-only). Record-id derivation (`db.make_event_id`) is *not* an entity resolver and is excluded. | `config.py:209`, `config.py:285-304`, `corpus.py:407`, `universe.py:197-235`, `universe.py:364-401`, `studies/crosswalk.py:26-77`; branch: `atlas/identity/resolver.py:1-38`, `external_sources/identity.py:1-15` |
| C3 | `main` has **8 source registries** | **`[FACT]` 9 curated JSON registries + 3 code-embedded registries = 12 candidates; "8" is a subset, not a count.** | `config/*.json` list: `companies_device.json`, `companies_drug.json`, `tracks_device.json`, `tracks_drug.json`, `product_code_tracks.json`, `product_catalog_zh.json`, `product_families.json`, `sources.json`, `universe_v1.json`; code-embedded: `db.py:25-55` (companies/tracks/product_codes tables), `audit.py:19-27` (`EXPECTED_SOURCES`), `intelligence/taxonomy.py:22-25` (versioned taxonomy regime) |
| C4 | `main` has **4 ledgers** | **`[FACT]` 4 on `main`, 3 more on branches.** `main`: TKG `idempotency` (`tkg/store.py:136-141`), forecast `forecast_idempotency` (`forecast_registry.py:172-175`), run log `runs` (`db.py:140-146`), skip ledger `live_skips` (`db.py:216-222`, writer `live.py:540`). Branch: ATLAS `request_log`/`relation_events`, staging `request_log`, Observatory `sync_run`/`source_failure`. | probe table lists; writers cited |
| C5 | `main` has **6 query engines** | **`[FACT]` 6 distinct as-of/attribution query surfaces on `main`.** (1) `tkg/query.py` bitemporal snapshot; (2) `tkg/export.py` deterministic export; (3) `intelligence/graph_context.py` read-only graph context; (4) `replay.py` availability-window engine; (5) `research_agent.py` read-only as-of adapter; (6) `db.py:325`/`universe.py` raw SQL + universe rebuild. | each cited in §3.2 |
| C6 | `main` has **3 forecast records** | **`[FACT]` 3 distinct forecast *record formats*:** (a) JSON document schema `forecast_set_v1` (`intelligence/forecasts.py:22-28`); (b) mutable table `horizon_forecasts` (`intelligence/storage.py:113-132`); (c) append-only `forecasts`+`resolutions` (`forecast_registry.py:112-169`). `forecast_examples` (`storage.py:98-111`) is a training-example table, not a forecast record. | cited |
| C7 | `db.py:537` uses `INSERT OR REPLACE` on `event_id` | **`[FACT]` confirmed at `b2a14c0:537`.** Note line drift: the audit that said `db.py:519` was reading `7a639f7` (verified: `git show 7a639f7:medradar/db.py` has the statement at 519). | `db.py:536-543`; probe `behavioural.events_upsert_same_id.replaced_in_place=True` |
| C8 | `main` has **no schema version / migration table** | **`[FACT]` confirmed.** `db.py` creates `meta` (`db.py:20-23`) but never writes `schema_version`; `_migrate` only adds columns (`db.py:287-316`); `git grep schema_version origin/main -- medradar` finds only TKG, forecast registry, export/evaluation artifacts and `universe/replay` *document* versions. `onboarding.py:292` executes SQLite's internal `PRAGMA schema_version`, which is a schema cookie, not an application migration ledger. | command + cited lines |
| C9 | ATLAS declares a `schema_migrations` table | **`[FACT]` confirmed on `origin/foundation/atlas-001`** (not on `main`): version, name, checksum, applied_at, backup-before-migrate, checksum verification. | `atlas/db/migrations.py:28,44-49,324,373-434`; probe ATLAS table `schema_migrations` |
| C10 | ATLAS `identity/normalize.py:8-11` says "Ported from medradar.external_sources.identity" | **`[FACT]` confirmed, but the exact lines are `9-10`** ("Ported from … (DATA-EXPANSION-001, `origin/research/data-expansion-001`)"). | `atlas/identity/normalize.py:9-10`; source exists at `origin/research/data-expansion-001:medradar/external_sources/identity.py` |
| C11 | `tkg/` is append-only with **6 tables / 7 triggers** | **`[FACT]` both exact.** Probe: `tables=6 indexes=7 triggers=7 foreign_keys=6`. | probe TKG store; `tkg/store.py:69-188` |

**Consequence of C1/C3/C4/C5/C6:** the audit's counts are true under a grouping that the audit did not state. All downstream Phase-0 work should quote the reproducible count (`7 DDL-owning modules on main`, `9 curated JSON registries`, `7 ledger tables on main`, etc.) rather than the bare numbers.

---

## 3. Inventory

### 3.1 The stores (probe-certified structure; `[FACT]` unless marked)

| ID | Store | Module / branch | Backing file | Record unit | PK / dedupe rule | Mutability | Declared schema version | Probe (tables / indexes / triggers / FKs) |
|---|---|---|---|---|---|---|---|---|
| **S1** | `events` | `medradar/db.py` (`main`) | `data/medradar.sqlite` (17 tables) | one source event row | `events.event_id` (content hash, `db.py:268-272`); `INSERT OR REPLACE` (`db.py:537`) | **mutable in place**; no revision log | **none** (C8) | 17 / 23 / **0** / **0** |
| **S2** | `live_alerts` | `medradar/db.py` (`main`) | same DB file | one fast-lane alert | `alert_id`; `INSERT OR REPLACE` (`live.py:769`) | mutable in place | none | part of S1's 17 |
| **S3** | TKG assertion store | `medradar/tkg/store.py` (`main`) | `data/tkg.sqlite` | one **assertion revision** about one node/edge | `(node_type,node_id,recorded_at,seq)` / edge identity + `recorded_at,seq`; `idempotency_key` ledger | **append-only, trigger-enforced** (UPDATE/DELETE/`INSERT OR REPLACE` all rejected) | `tkg-schema-2` (`store.py:44`, stamped `store.py:341-344`, hard-fails on mismatch `store.py:346-362`) | 6 / 7 / **7** / 6 |
| **S4** | Forecast registry | `medradar/forecast_registry.py` (`main`) | caller-chosen `registry.sqlite` (`cycle.py:189`) | one registered forecast + one resolution version | `prediction_id` (content hash) + `idempotency_key` UNIQUE (`:137`); `resolutions(prediction_id, resolution_version)` | **append-only, trigger-enforced** for `forecasts`, `resolutions`, `forecast_idempotency` | `forecast-registry-2` (`:60`) | 5 / 7 / **10** / 1 |
| **S5** | Intelligence core | `medradar/intelligence/storage.py` (`main`) | same DB file as S1 (shares the `DB` connection, `storage.py:154-158`) | per-source normalised rows: `financial_facts`, `procurement_awards`, `company_identifiers`, `temporal_edges`, `horizon_forecasts`, `forecast_examples` | per-table natural keys; all writers use `INSERT OR REPLACE` (`:175,:186,:202,:223,:245`) except `replace_examples` (`:228-241`, DELETE+INSERT by `dataset_version`) | **mutable in place**; no triggers | none | 7 tables of the assembled 26 |
| **S6** | Source-private tables | `intelligence/sources/{patents,publications,market_data}.py` (`main`) | same DB file as S1 | `patent_applications`, `publication_counts`, `market_bars` | natural keys; `INSERT OR REPLACE` / DELETE+INSERT (`market_data.py:285-295`) | **mutable in place** | none | 1+1+1 = 3 of the assembled 26 |
| **S7** | ATLAS evidence store | `medradar/atlas/**` (`origin/foundation/atlas-001`, **not on main**) | own SQLite file (`atlas/config.DEFAULT_DB`) | one documented external fact, **versioned** `(evidence_id, version)` | `evidence_id` = deterministic hash of `(source_id, evidence_type, source_record_id)` (`evidence/schema.py:111-113`); changed content → new version; unchanged re-fetch = no-op | **append-only by application code**; `evidence_head` pointer updated on purpose (`store.py:155-202`); **no DB triggers** | `schema_migrations` v1 (checksummed, backup-before-migrate) | 21 / 30 / **0** / **0** |
| **S8** | DATA-EXPANSION-001 staging | `medradar/external_sources/store.py` (`origin/research/data-expansion-001`, not on main) | `research/data_expansion/staging/*` (git-ignored, rebuilt per run) | one documented external fact, versioned by `(evidence_id, content_hash)` | deterministic `evidence_id`; `evidence_head.duplicate_of` for cross-source duplicates | append-only by code; **0 triggers**; explicitly disposable | none (staging, recreated) | 7 / 10 / **0** / **0** |
| **S9** | Observatory observation ledger | `medradar/observatory/ledger.py` (`origin/feat/observatory-reliability-v1`, not on main) | `data/observatory/observatory.sqlite` (`ledger.py:15,68-75`) | one observed source record (+ payload versions, change rows, mapping decisions) | `observation_id` + UNIQUE `(source, source_record_id)`; versions `version_id` | **mixed**: identity + `first_seen_at` immutable by trigger, no DELETE on history tables; bookkeeping columns update (`ledger.py:1-17`) | `meta.schema_version` (`ledger.py:465-466`) | 13 / 27 / **17** / 0 |
| **S10** | Non-DB evidence artefacts | `intelligence/forecasts.py` JSON schema; `research/studies/*/CLAIMS_EVIDENCE.json` | JSON in git | frozen forecast set / claim-evidence bundle | `schema` field + id strings | immutable by being committed to git | schema id in the document | n/a (not a DB) |

`[FACT]` The intelligence database, as assembled by `IntelligenceStore` + the three `ensure_*` calls, is **26 tables / 38 indexes / 0 triggers / 0 foreign keys** (probe `stores[3]`). That single number is the honest answer to "how big is the central store": 17 tables from `db.py`, 7 from `storage.py`, 3 from source modules — all in one file, with **no constraint-level join between them**.

Inventory attributes not shown in the table above are tabulated separately, per store: temporal fields §4.3, identity/join keys §4.4, query API §3.2, tests §3.5, licence/quality §4.5, schema evolution §4.6, operational cost §4.7.

### 3.2 Query surfaces (the "6 query engines", `[FACT]`)

| Engine | Entry point | Time semantics | Read-only? |
|---|---|---|---|
| Q1 TKG bitemporal query | `tkg/query.py:65-168` | `known_at` gates `recorded_at` **first**, then `valid_at` gates `[valid_from, valid_to)` (`query.py:1-16`) | yes |
| Q2 TKG deterministic export | `tkg/export.py:34-70` (snapshot), `:86-105` (renderings) | same two cutoffs; `snapshot_sha256` over canonical JSON, no wall clock in manifest (`export.py:1-14`) | yes |
| Q3 Graph context | `intelligence/graph_context.py:275-391` | reuses Q1 primitives (`graph_context.py:38-43,269-272`); endpoint-visibility contract | yes — `mode=ro` + `PRAGMA query_only` (`:55-83`) |
| Q4 Replay availability engine | `replay.py:270-312` | `available_at → published_at → payload`; **expands day precision to 23:59:59.999999** (`:306-310`); no `event_date` fallback | yes (read path) |
| Q5 Research-agent as-of adapter | `research_agent.py:185-241` | `_visible_at` compares `created_at` to `as_of` at day or instant resolution (`:197-229`) | yes — `mode=ro` (`:232-241`) |
| Q6 Raw SQL + universe rebuild | `db.py:325-330`, `intelligence/universe.py:329-401,740-775` | caller-defined; `universe` re-derives entity identity from `applicant_raw` | mixed |

`[INFERENCE]` Six engines × four time conventions (§5.3) is the structural cause of the phase-0 complaint "no single canon": two engines can disagree about the same row by ~24 h (probe `timestamp_rendering.same_instant=False`). Fixing the engine count without fixing the convention would not change that.

### 3.3 Identity resolvers (the "6", `[FACT]`)

| R1 | `CompanyRegistry.resolve(applicant)` — exact alias → all-alias-token containment (score 0.95+) → token Jaccard ≥ 0.82; returns `(key, confidence, matched_alias)` or `(None, score, alias)` | `config.py:209-234` |
| R2 | `TrackRegistry.for_product_code/match_text/match_frontier_text` — code map, then longest-keyword containment | `config.py:285-304` |
| R3 | `corpus.normalize_company_name` — SEC display-name folding | `corpus.py:407-411` |
| R4 | `universe.normalise_applicant` + `entity_key` — deterministic, table-driven, "no fuzzy matching"; entity key = slug+sha1[:8] | `universe.py:197-235` |
| R5 | `universe.resolve_normalised` / `resolve_entities` — maps a normalised applicant to the curated/universe entity | `universe.py:364-401` |
| R6 | `studies.crosswalk.normalise` + `assign_device_track` — study-level keyword→track assignment | `studies/crosswalk.py:26-77` |

Branch-only additions (not on `main`): `atlas/identity/resolver.py:1-38` (three authorities: `source_declared` / `derived` / `inferred`; seven relation types; negative rule "a matching name is never identity") and `external_sources/identity.py:1-15` (identical rule, `official_id` → `exact_alias` → `multi_field`, everything weaker is `candidate` with confidence < 0.9).

`[FACT]` The two branch resolvers are **the same policy in two implementations** (`atlas/identity/normalize.py:9-10` says so; `external_sources/identity.py:1-15` and `atlas/identity/resolver.py:1-38` describe the same tier order). This is the strongest argument that a resolver — not a store — is the missing canon piece: identity policy was already stabilised twice and then duplicated.

### 3.4 Registries (the "8", `[FACT]` enumeration)

Curated JSON (9): `companies_device.json`, `companies_drug.json`, `tracks_device.json`, `tracks_drug.json`, `product_code_tracks.json`, `product_catalog_zh.json`, `product_families.json`, `sources.json`, `universe_v1.json` (1.7 MB, the derived universe document, `universe.py:776-808`).
Code-embedded (3): SQLite `companies`/`tracks`/`product_codes` (`db.py:25-55`), `audit.EXPECTED_SOURCES` (`audit.py:19-27`), `intelligence/taxonomy.py` versioned taxonomy regime (`taxonomy.py:22-25`, `TAXONOMY_VERSION="tracks_device_2026-11"`).
Branch-only (2): `config/atlas_firms.json` + `config/atlas_sources.json` (ATLAS source register with `access_basis`, `licence_status`, `time_semantics`, `verified_status`), DATA-EXPANSION-001 `research/data_expansion/registry/sources/<source_id>.json` (`external_sources/registry.py:1-15`).

`[INFERENCE]` "8" was likely the count of curated JSON files at the audit's SHA. It is now 9 + 3 code-embedded. Any canon option must decide whether registries are content or code — today `sources.json` has no DB representation, so licence/access metadata never reaches a stored record (§4.5).

### 3.5 Tests and verification surface (`[FACT]`)

| Store | Unit tests | Integration / acceptance |
|---|---|---|
| TKG | `tests/test_tkg.py` (1,032 lines) | `tests/test_tkg_integration.py` (381 lines); `docs/research/TKG_ACCEPTANCE.md` |
| Forecast registry | `tests/test_forecast_registry.py` (1,060 lines) | `tests/test_forecast_cycle.py`, `tests/test_registry_adapter.py` |
| Intelligence / market-to-R&D | `tests/test_intelligence.py`, `tests/test_market_intelligence.py`, `tests/test_forecast_cycle.py`, `tests/test_registry_adapter.py` | — |
| ATLAS (branch) | `tests/test_atlas_evidence.py` (165), `test_atlas_db.py` (156), `test_atlas_identity.py` (182), `test_atlas_connectors.py` (162), `test_atlas_research.py` (106) | `tools/verify_atlas.py` (342 lines), `.github/workflows/atlas.yml` |
| Observatory (branch) | 10 files `tests/test_observatory_*.py` (`core`, `audit`, `backup`, `reliability`, …) | `docs/observatory/evidence/16_acceptance_report_full.json` |
| `events` (S1) | `tests/test_audit.py`, `test_device.py`, `test_drug.py`, `test_replay.py`, `test_research_agent.py` | `python -m medradar selftest` |

`[UNVERIFIED]` The branch stores' tests were not executed here (different branches, and this task is read-only outside its own branch). Their presence is `[FACT]`; their current pass state is not.

---

## 4. Comparison matrix

### 4.1 Semantics — what is one record? (`[FACT]` from schema/probe)

| Store | One row means | Granularity risk |
|---|---|---|
| S1 `events` | "a source published an event of `kind` about `company_key`/`track_id` on `event_date`" | loses the source document; re-ingestion replaces content (probe) |
| S3 TKG | "the system recorded, at `recorded_at`, that a node/edge had these attrs over `[valid_from, valid_to)`" | source identity is reduced to `source_locator` + `evidence_sha256` (`store.py:99-102`); no licence/quality field |
| S4 forecast registry | "a forecast was registered with this content at `generated_at`; later resolutions are separate versions" | one record per prediction, not per evidence item; `target_attrs` is free JSON (`:121`) |
| S5 intelligence | "a source-normalised fact row (financial fact / award / edge / forecast)" | four different time conventions across its six tables (§4.3) |
| S7 ATLAS | "one documented external fact, bound to immutable raw bytes, versioned" | the cleanest unit in the repository (`evidence/schema.py:1-21,148-223`) |
| S8 staging | same as S7, disposable | duplicates S7's model with no triggers |
| S9 ledger | "one observed source record + its payload version history + mapping decision history" | trading/ops ledger, not research evidence |

`[INFERENCE]` S1 and S3 disagree about what a record *is* (source row vs assertion revision). That is the deepest incompatibility and it is not fixable by adapters alone: an `events` row that is replaced in place cannot be projected into a history that never existed.

### 4.2 Immutability (`[FACT]` probe `behavioural` + schema)

| Store | UPDATE | DELETE | `INSERT OR REPLACE` | Revision history available? | Enforcement |
|---|---|---|---|---|---|
| S1/S2/S5/S6 | allowed | allowed | **allowed — replaces content** | **no** (probe: `revision_history_table=0`) | none |
| S3 TKG | **rejected** (`TKG history is append-only: UPDATE rejected`) | **rejected** | **rejected** (`revision already recorded`) | yes (`nodes`/`edges` + `idempotency`) | **7 SQLite triggers** |
| S4 forecast | **rejected** | **rejected** | **rejected** (`forecast already registered`) | yes (`resolutions` versions) | **10 triggers** |
| S7 ATLAS | code never issues it for `evidence` | code never issues it | not used for `evidence`; `evidence_head` is updated by design (`store.py:196-202`) | yes (`(evidence_id, version)`) | **application only — 0 triggers** |
| S8 staging | application only | application only | application only | yes (`(evidence_id, content_hash)`) | **0 triggers** |
| S9 ledger | rejected for history tables / allowed for bookkeeping columns | rejected for history tables | n/a | yes | **17 triggers** (partial by design) |

`[FACT]` The probe proves the S1 defect behaviourally: two `upsert_events` calls with the same `event_id` and different `title` leave **1 row** whose title is the **second** version (`behavioural.events_upsert_same_id = {rows_after_two_writes: 1, title_after_second_write: "second version", replaced_in_place: true}`).

### 4.3 The four time axes (`[FACT]` columns from probe; semantics from cited code)

Axes: **E** = event/valid time (when the fact was true), **P** = public time (when a third party could know), **O** = first-observed/ingestion time, **F** = fetch/evaluation time (when this copy was retrieved / when the result is computed).

| Store | E | P | O | F | Separation enforced? |
|---|---|---|---|---|---|
| S1 `events` | `event_date` | `published_at` (+`timestamp_quality`) | `first_seen_at` | `fetched_at`, `as_of` | **No.** Batch collectors collapse P=O=E (`audit.py:29-49`); `_migrate` backfills P/O from `event_date` (`db.py:309`); `estimated` lag modelled as +14 days (`openfda_bulk.py:105-107`) |
| S3 TKG | `valid_from`/`valid_to` (+`valid_precision`) | `public_time` + `public_time_basis` (optional) | **`recorded_at`** (store clock, store-assigned, monotonic) | — | partially: O is first-class and trustworthy; P is optional metadata and **was empty for 100% of the real import** (§6.3) |
| S4 forecast | `window_start`,`window_end` | `information_cutoff` | `generated_at` (store clock) | `resolved_at`,`event_time` | yes for the forecast problem (5 clocks, validated `:523-608`) |
| S5 intelligence | `period_end`,`valid_time`,`award_date`,... | `available_at` | `retrieved_at` | — | per-table, not consistent; `company_identifiers.valid_from/valid_to` vs `financial_facts.valid_time` |
| S7 ATLAS | `event_at` | `source_public_at` (+quality) | `first_observed_at` | `fetched_at` | **yes** — all four required keys (`evidence/schema.py:261-268`), `observation_basis` mandatory when P exists |
| S8 staging | `event_at` | `source_public_at` | `first_observed_at` | `fetched_at` | yes, same contract (`external_sources/schema.py:251-258`) |
| S9 ledger | `event_at`(+precision) | `published_at`(+precision) | `first_seen_at`/`ingested_at` | `last_checked_at`,`captured_at` | yes, with per-axis precision columns |

`[FACT]` Renderers disagree on the same calendar day: `util.iso_moment("2024-03-05")` → `2024-03-05T00:00:00` (naive), TKG → `2024-03-05T00:00:00.000000Z`, replay → `2024-03-05T23:59:59+00:00` (probe `timestamp_rendering`, `same_instant=False`). There are **three canonical forms across four implementations**: `util.iso_moment` (`util.py:62-81`), `tkg/_time.render_moment` (`_time.py:53-55`, also used by `forecast_registry` via its import at `forecast_registry.py:58`), the replay end-of-day expansion (`replay.py:306-310`), and `research_agent._as_of_moment` (`:197-209`) which re-implements the TKG form rather than importing it. `[INFERENCE]` A "day" in `events` therefore means a 24-hour window per consumer, not a time.

### 4.4 Identity and join keys (`[FACT]`)

| Store | Record identity | Entity identity | Cross-store join key | FK declared? |
|---|---|---|---|---|
| S1 | `event_id = sha1(source|kind|parts)[:32]` (`db.py:268-272`) | `company_key` from R1, `track_id` from R2, `product_code` raw | `company_key`, `track_id`, `product_code` (text) | **none** (probe fk=0) |
| S3 | `(node_type,node_id)` + `recorded_at,seq`; `entities` is an FK target (`store.py:82-86,106`) | ids copied from source, no resolver | same text ids; `event` nodes keep `event_id` | 6 (inside TKG only) |
| S4 | `prediction_id = sha256(canonical content)` (`:512`) | `target_type`+`target_id`+`target_attrs` JSON — **not validated against any registry** | `prediction_id`; verification joins `target_attrs.company/track` to `events` (`registry_adapter.py:verify_registered_forecasts`) | 1 (`resolutions → forecasts`), enforced (`PRAGMA foreign_keys=ON`, `:422`) |
| S5 | per-table natural keys | `company_key` text; `company_identifiers(company_key,scheme,identifier,source)` — **write-only, no reader on main** (`git grep company_identifiers`: 2 hits, both in `storage.py`) | `company_key`; `temporal_edges.evidence_id` text | **none** (probe fk=0) |
| S7 | `evidence_id = hash(source_id, type, source_record_id)` (`schema.py:111-113`) | `canonical_key` from authoritative identifiers priority list (`schema.py:116-146`); `entity_refs` with `method`+`confidence`; `canonical_entity_id`; companies/devices registry | `canonical_key`, `evidence_identifiers(scheme,value)`, `source_id`+`source_record_id` | **0 declared** (probe) though `PRAGMA foreign_keys=ON` is set — nothing to enforce |
| S8 | same as S7 minus the priority logic details | same tiers (`identity.py:1-15`) | `canonical_key` | **0** |
| S9 | `(source, source_record_id)` UNIQUE | mapping decisions append-only | `(source, source_record_id)` | 0 |

`[FACT]` **No store can join to another by constraint.** The only cross-store joins in shipped code are text equality: (a) forecast verification parses JSON and matches `events.company_key/track_id`; (b) `graph_context` matches TKG node ids to `company`/`track` strings that came from `events`; (c) `temporal_edges.evidence_id` is an unenforced pointer. Silence on mismatch is the failure mode (C8/D10).

### 4.5 Licence / quality tagging (`[FACT]`)

| Store | Licence on record | Quality flags | Confidence | Redistribution gate |
|---|---|---|---|---|
| S1/S2 | none | `timestamp_quality` only | none | none |
| S3 | none | `evidence_kind ∈ {source_observed,inferred,reconstructed}` (`store.py:46`) | `confidence ∈ [0,1]` CHECK | none |
| S4 | none | `evidence_kind` | p only | none |
| S5 | **none columns**; `data_quality` strings on `financial_facts`/`procurement_awards` | free-text `data_quality` | `match_confidence` on awards | `procurement_awards.pit_usable` (0/1) |
| S7 | `licence_status ∈ {public_domain, open_licence, open_no_explicit_licence, restricted, unknown}` (`schema.py:54-61`) | 13-value `quality_flags` taxonomy (`schema.py:63-78`) | per entity ref | **licence gate is first-class**; `config/atlas_sources.json` carries `redistribution` per source |
| S8 | `licence_status` on record (`external_sources/schema.py:85-88`) | quality flags | per entity ref | yes |
| S9 | none | change state / status enums | none | none |

`[INFERENCE]` Only S7/S8 can answer "may we redistribute this row and how good is its publication clock?" from the store alone. Any canon that keeps S1 as the record of truth must add both columns and backfill them from registries, or accept that licence/quality live only in git.

### 4.6 Schema evolution (`[FACT]`)

| Store | Mechanism | Failure mode |
|---|---|---|
| S1/S2/S5/S6 | `CREATE TABLE IF NOT EXISTS` + `_migrate()` adding 4 columns (`db.py:287-316`) | silent heterogeneous DBs; no checksum, no backup, no downgrade detection; `IF NOT EXISTS` also **hides** the contradictory index in §7/D3 |
| S3 | fixed `SCHEMA_VERSION`, stamped in `meta`; missing/mismatched → **hard error with "rebuild from source"** (`store.py:322-362`) | no migration path by design: changing schema means rebuild + re-import (which loses nothing only if the source still exists) |
| S4 | fixed `SCHEMA_VERSION`; no migration path | same as S3 |
| S7 | versioned migrations with checksum + **backup before migrate** + transaction (`migrations.py:373-434`) | requires the branch; `Migration` dataclass is the only real migration system in the repo |
| S8 | none (rebuilt per run) | not applicable |
| S9 | `meta.schema_version` + `created_schema` flag (`ledger.py:465-466`) | no migration chain found |

### 4.7 Operational cost (`[FACT]` where measured; `[INFERENCE]` where projected)

Measured by the committed import report `experiments/reverse_rd_v2/tkg_import_report.json` (real 55,090-row source, not synthetic):

| Metric | Value |
|---|---|
| Source DB | 289,443,840 B, SHA-256 unchanged before/after (adapter is read-only) |
| TKG store produced | 194,723,840 B |
| Rows imported | 55,090 → **171,800 assertions** (57,381 nodes, 114,419 edges, 57,381 entities, 171,800 idempotency keys) |
| Import time | **32.593 s** *with* two ad-hoc operational indexes (`--no-index` path is O(n²) because `idempotency_key` is unindexed in `nodes`/`edges`; source note `scripts/tkg_import_research.py:23-28`) |
| Re-import time | 13.661 s, `assertions_created=0`, store did not grow (idempotency works) |
| Export time | 6.514 s (+5.695 s to write `snapshot.json`) |
| **Public time survived** | **0 of 55,090 rows** (`counters.invalid_public_time_dropped = 55090`) |

Synthetic bench (`docs/research/tkg_bench_synthetic.json`, explicitly labelled synthetic): 2,000 nodes / 1,999 edges → write 0.1219 s, export 0.071 s, deterministic re-export hash.

`[UNVERIFIED]` The shipped `data/medradar.sqlite` is **not in the worktree** (`data/` is gitignored, `.gitignore:2`). `audit.py:47` claims "the shipped 375,378-row snapshot", but that number cannot be checked here.

`[INFERENCE]` Projection: if the 375k-row claim is true, S3 size scales ~3.5× (≈680 MB) and a from-scratch import at the measured 1,690 rows/s is ≈3.7 min (plus O(n²) risk without the ad-hoc indexes). Neither store currently prunes history, and TKG's export materialises the full snapshot in memory (`export.py:53-69`), so export time at 375k rows is a real unknown (E5).

### 4.8 Compatibility with existing consumers (`[FACT]` census via `git grep -l "<table>" origin/main -- medradar`)

| Store | Direct consumers on `main` | Count | Consequence for a migration |
|---|---|---|---|
| S1 `events` | `__main__.py`, `analyze.py`, `audit.py`, `families.py`, `frontier.py`, `intelligence/entities/technology_mapping.py`, `intelligence/evaluation/leakage_audit.py`, `intelligence/features/research_features.py`, `intelligence/forecasting/{cycle,horizon,registry_adapter}.py`, `intelligence/universe.py`, `products.py`, `replay.py`, `research_agent.py`, `stats_cmd.py`, `tkg/adapter.py` | **17 modules** | any canon that moves `events` rewrites 17 read paths; any canon that keeps it (C) is free |
| S3 TKG | `intelligence/graph_context.py` (via `research_agent.py`), `tkg/__main__.py`, `scripts/tkg_import_research.py`; forecast registry reads a TKG **file** only | 3–4 | A's compatibility cost is not the adapter, it is the 17 `events` consumers that would not move |
| S4 forecast registry | `intelligence/forecasting/cycle.py`, `.../registry_adapter.py`, CLI | 3 | already the canonical forecast lane; `horizon_forecasts` is its shadow (D9) |
| S5 intelligence core | `intelligence/features/research_features.py` (`financial_facts`), `forecasting/{horizon,calibration,cycle}.py` (`horizon_forecasts`/`forecast_examples`), `research_agent.py` | 5 modules | a canon must either adopt or retire these tables; they are read by the frozen-model lane |
| S6 source-private tables | `features/market_features.py` + `research_agent.py` (`market_bars`), `features/publication_features.py` (`publication_counts`, patents via `sources/patents.load_publications`) | 3 modules | the only consumers are feature builders — the cheapest group to port |
| S7/S8/S9 (branch) | **0** (`git grep -l "medradar.atlas\|medradar.external_sources\|medradar.observatory" origin/main` → 0 files) | 0 | adopting B or the ledger means **adding** a consumer, not replacing one — the compatibility score of 1 in §8 is literal |

---

## 5. What a canon must answer (derived requirements)

`[INFERENCE]` from §4; each requirement is used as a decision criterion in §8.

| Req | Requirement | Worst offender today |
|---|---|---|
| RQ1 | one record = one documented external fact, with source identity | S1 loses the document on replace |
| RQ2 | recorded history cannot be rewritten (constraint, not convention) | S1/S5/S6/S7/S8 |
| RQ3 | E/P/O/F separated, each with explicit precision and "unknown" | S1 collapses P/O/E |
| RQ4 | identity resolution is explicit, tiered, and auditable | S1 resolves at ingest and never records the evidence for the match (`CompanyRegistry.resolve` returns confidence/alias but `upsert_events` stores neither) |
| RQ5 | licence + quality survive with the record | S1/S3/S5 |
| RQ6 | schema changes are planned, checksummed and backed up | S1 |
| RQ7 | joins between evidence, entities, forecasts and studies are typed | none |
| RQ8 | the 17 `events`-reading modules keep working during migration (`studies/` are pure functions and are not a constraint) | A/B both break this |

`[FACT]` RQ4's gap is concrete: `upsert_events` (`db.py:490-545`) stores `company_key`, `track_id`, `product_code` but **not** the resolver's `(confidence, matched_alias)`; only `procurement_awards` keeps `match_confidence`/`matched_alias` (`storage.py:76-77`, `procurement_us.py:53-54`).

---

## 6. Explicit defects (with file:line; severity is `[INFERENCE]`)

| ID | Defect | Evidence | Severity | Blocking which option |
|---|---|---|---|---|
| **D1** | `events` is overwritten in place; no revision history; `first_seen_at` reset on re-collection | `db.py:537`; probe `replaced_in_place=True`, `revision_history_table=0`; `db.py:502` assigns `first_seen_at=stamp` on every upsert | **critical** | A, B, C all need a fix; blocks "history" claims of any canon |
| **D2** | no application schema version / migration ledger on the central DB | `db.py:20-23,287-316`; `git grep schema_version origin/main -- medradar` (only TKG/forecast/artefacts); `onboarding.py:292` is SQLite's cookie | high | C (cheap to add), A/B (must decide coexistence) |
| **D3** | duplicate, **contradictory** index definition for `idx_market_bars_date`; import order decides the index | `storage.py:146` `ON market_bars(date,ticker)` vs `market_data.py:83` `ON market_bars(date)`; probe `main_ddl_collisions.contradictory_index_names` | high (silent performance/semantic drift) | all |
| **D4** | `market_bars` table is owned by two modules; `meta`/`clock_guard` names are reused by three DB modules | probe `duplicate_table_names=['clock_guard','market_bars','meta']`; `storage.py:133-146`, `market_data.py:69-85` | medium | all |
| **D5** | timestamp dialect split: `db.upsert_events` stores naive `…T00:00:00`; TKG rejects naive → **100 % public-time loss** on the only real import | probe `legacy_available_at_to_tkg`; `tkg/store.py:217-218,232-233`; `experiments/reverse_rd_v2/tkg_import_report.json` `invalid_public_time_dropped=55090` | **critical** | **A (measured)** |
| **D6** | **three canonical-moment forms** (four implementations) disagree on day precision: naive midnight (`util.iso_moment`, used by `db.upsert_events`), fixed-microsecond 00:00:00 UTC (`tkg/_time.render_moment`, reused by `forecast_registry`), 23:59:59 UTC (replay end-of-day), plus `research_agent._as_of_moment` re-implementing the TKG form | probe `timestamp_rendering.same_instant=False`; `util.py:62-81`; `tkg/_time.py:53-55`; `replay.py:306-310`; `research_agent.py:197-209` | high | all (must normalise before any bitemporal claim) |
| **D7** | identity table with no consumer: `company_identifiers` written, never read | `git grep company_identifiers origin/main -- medradar` → only `storage.py:18,175` | medium | B (its `evidence_identifiers` solves this) |
| **D8** | two market series with different provenance (`prices` has no source/retrieved_at; `market_bars` does) and `prices` is overwritten; Yahoo restates adj_close | `db.py:86-96,562-566`; `storage.py:133-145`; `prices.py:1-20`; KIMI audit §0.2 (v0.2.2) | high for backtests | all |
| **D9** | three forecast record formats; `horizon_forecasts` is mutable while the same prediction is append-only in the registry; the bridge is an adapter, not a key | `storage.py:113-132,243-257`; `forecast_registry.py:112-169`; `intelligence/forecasts.py:22-28`; `cycle.py:1-23,189-226`; `registry_adapter.py:1-24` | medium | A/B/C must name one canon and demote the others |
| **D10** | cross-store joins are untyped text; no FK anywhere in the central DB; `temporal_edges.evidence_id` unenforced | probe fk=0 on S1/S5/S7/S8; `storage.py:93`; `registry_adapter.py` joins via `attrs` JSON | high | A/B/C |
| **D11** | ATLAS/staging immutability is application-level (0 triggers); `evidence_head` is updated by design | probe S7/S8 `trigger_count=0`; `atlas/store.py:3-15,155-202` | medium | B (must add triggers or state the boundary) |
| **D12** | documented contract contradicts migration code: `docs/SCHEMA.md:196` says "no `event_date` fallback", while `db._migrate:309` backfills `available_at` from `event_date`, and `audit.py:29-49` documents legacy P=O=E promotion that the trading gate cannot detect (`db.py:259-265` only checks quality ∈ {datetime,date}) | cited lines | **critical for research integrity** | all |
| **D13** | run log `runs` uses `INSERT OR REPLACE` (a run record is history) | `db.py:614-624` | low | C |
| **D14** | `forecast_registry`'s FK to `forecasts` is the repo's only enforced FK; everything else has none, so "referential integrity exists somewhere" is misleading | probe S4 fk=1 vs S1/S5/S7 fk=0 | low | all |

`[FACT]` D5 and D12 together mean the current central evidence store **cannot** be described as bitemporal: the public clock is partially fabricated and then destroyed on import to the store that models clocks properly. This is not a documentation nit; it is the empirical basis for calling the TKG-canon proposal premature (§7 Option A).

---

## 7. Three candidate architectures

All effort ranges are `[INFERENCE]` from the measured facts (`§4.7`) and the file counts in the probe; they assume one competent engineer familiar with the codebase. "Effort" is engineering time, excluding institutional review. No option is executed in Phase 0.

### Option A — TKG canon + typed evidence projection (the REFOUNDATION-001 proposal)

**Shape.** `events` remains an ingestion cache; the canon is `nodes`/`edges`; research reads `TKGQuery`/`export_snapshot`; evidence records are node attrs + `source_locator`/`evidence_sha256`; studies consume exported snapshots.

**What wins**
- `[FACT]` Only main-branch store with physical append-only (7 triggers) + store-assigned monotonic knowledge clock (`store.py:365-383`) + idempotent retry semantics (probe: re-import created 0 assertions).
- `[FACT]` Already integrated read-only into research code (`graph_context.py`) and into forecast provenance (registry can verify a TKG `snapshot.json`, `registry_adapter.py:_snapshot_block`).
- `[FACT]` Deterministic, byte-reproducible export with no wall-clock in the manifest (`export.py:1-14`; `reexport_sha256 == snapshot_sha256` in the real import report).

**What is lost / what breaks**
- `[FACT]` **Public time:** 0/55,090 real rows carried `public_time` into TKG (D5). The canon would be built on a store that cannot see when information became public unless a normalisation pass repairs `available_at` first.
- `[FACT]` No licence/quality fields (§4.5), no entity resolution inside (ids are copied strings), no schema migration path (rebuild by design, `store.py:322-362`).
- `[FACT]` Cost: 194.7 MB / 55k rows; O(n²) duplicate lookups without ad-hoc indexes (measured 32.6 s with, projected ~27 min without per `scripts/tkg_import_research.py:23-28`); full-snapshot export materialised in memory.
- `[INFERENCE]` Compatibility: the 17 `events`-reading modules (scanner in §4.8) do their own SQL, so moving the read path is a rewrite of `analyze/replay/research_agent/intelligence features`, not an adapter. `medradar/studies/*` are pure record functions with **no DB access** (`git grep -n "sqlite\|DB(" origin/main -- medradar/studies` → no hits), so studies are unaffected either way.

**Migration steps (evidence: adapter exists, nothing else does)**
1. Repair `events` first (normalise timestamps to aware UTC; preserve day precision; demote legacy promotions per D12). Without this, step 2 re-imports the same 100 % loss.
2. Re-run `tkg.adapter.import_events` against the repaired DB; verify `invalid_public_time_dropped == 0` and count `public_time` non-null.
3. Add the operational indexes (`idempotency_key`) or fix the duplicate-path query; measure at target row count.
4. Port one consumer end-to-end (`graph_context` already exists) and diff its output against the SQL result on the same cutoffs.
5. Port `studies/` one study at a time, each with a frozen expected-output fixture.
6. Freeze `events` writes to the adapter only; publish the cutoffs (`known_at`, `valid_at`) used by each study.

**Effort:** 4–8 weeks to make TKG *sufficient* (public-time repair + identity + licence + migration story + one consumer port); 3–6 months to move all studies. `[INFERENCE]`
**Risk:** high — it changes the research read path for every study while the measured public-time gap remains open. **Reversibility:** medium — export is reproducible and the source DB is untouched (adapter opens `mode=ro`, `adapter.py:51-61`), so abandoning A costs only the ported code, not data.
**Falsifier (what would prove A wrong):** after repairing `available_at`, a re-import still drops/rejects a material fraction of public times, or a ported study cannot reproduce its SQL result from an as-of snapshot. Either one kills the "TKG is sufficient canon" claim.

### Option B — ATLAS versioned evidence canon + TKG as temporal index

**Shape.** Evidence records live in the 21-table ATLAS store: `(evidence_id, version)` append-only by code, four required clocks, `canonical_key`, identifier and entity-ref tables, licence/quality, `schema_migrations` with checksums + backup. TKG is fed *from* evidence and used only for graph/as-of traversal. Studies read evidence/entities.

**What wins**
- `[FACT]` The only model with all four clocks **required and validated**, with publication quality and `observation_basis` (`evidence/schema.py:228-296`); the only one with licence + quality taxonomy on the record (`:54-78`).
- `[FACT]` The only schema-evolution system with checksums, backup-before-migrate and transaction rollback (`migrations.py:1-15,373-434`).
- `[FACT]` The only cross-source de-duplication key built from authoritative identifiers (`canonical_key`, `schema.py:116-146`) and an explicit independence predicate (`is_independent`, `:304-315`).
- `[FACT]` Identity policy is explicit and tiered (three authorities; seven relation types; REJECTED relations preserved as negative evidence) — this is exactly RQ4, and it already exists twice (`atlas/identity/resolver.py:1-38`, `external_sources/identity.py:1-15`).

**What is lost / what breaks**
- `[FACT]` Not on `main`; adopting it means merging a large branch (21 tables, connectors, tools, CI) or porting the schema. `[UNVERIFIED]` merge feasibility and divergence size — E2.
- `[FACT]` Immutability is convention, not constraint (0 triggers, D11); `evidence_head` is updated by design; `revoke_relation` uses UPDATE. The "versioned canon" claim would need triggers to match TKG's guarantee.
- `[INFERENCE]` Compatibility: near-zero on `main` — nothing consumes ATLAS; `events` rows are *source rows*, not documented facts, so a lossless `events → evidence` mapping must be designed (one source row may yield several facts: registration + identifiers + company refs). This is the largest hidden cost.
- `[INFERENCE]` Operationally it is a second database next to `events`, `tkg`, `registry`, `observatory` — until the migration ends, the store count goes up, not down.

**Migration steps**
1. Decide the evidence-record projection for each `events.source/kind` (which facts does one 510(k) row assert?).
2. Backfill: `events` → `make_evidence` → `append_evidence`, carrying `first_observed_at` honestly as *today* (never back-dated; the ATLAS contract forbids it, `timeq.py:17-21`).
3. Add enforcement to match the promise: triggers for `evidence`/`evidence_identifiers`/`evidence_entity_refs`, and a documented immutability boundary for `evidence_head`.
4. Attach TKG as an index fed from evidence (`graph/build.py` on branch), not as a source of truth.
5. Rewrite the forecast verification join to use `evidence_id`/`canonical_key` instead of `target_attrs` JSON.
6. Retire or demote `horizon_forecasts` and the staging store.

**Effort:** 6–12 weeks minimum for schema + merge + a backfill design for every `events.source` family (`audit.EXPECTED_SOURCES` alone lists 7, `audit.py:19-27`) + one research consumer; 4–9 months to become the default read path. `[INFERENCE]`
**Risk:** high — largest semantic jump, new canon on an unmerged branch. **Reversibility:** medium-low — `evidence_id` is derivable again from source identity, so data can be rebuilt, but downstream code written against evidence ids is not free to revert.
**Falsifier:** a source family in `events` cannot be projected into `make_evidence` without inventing fields (e.g. no `source_public_at` at all), or the merge/port cost exceeds the measured migration budget. Also: if the licence gate proves unnecessary for the research questions actually asked, B's main differentiator loses weight.

### Option C — `events` canon + append-only revision log + adapters (minimal change)

**Shape.** Keep `events` as the canonical source-observation record, but make recording safe: add `event_revisions` (append-only, trigger-protected) or a content-addressed evidence table keyed on `(source, source_record_id, content_hash)`; add `schema_migrations`; normalise the four clocks; add licence/quality columns; make all joins go through one identity table; keep ADAPTERS to TKG/ATLAS for graph and evidence-model consumers.

**What wins**
- `[FACT]` Zero data movement: every existing **DB reader** (17 modules, §4.8) already reads `events`; `medradar/studies/*` are pure functions over records and are unaffected by the store choice. The migration is additive.
- `[FACT]` Cheapest fix for the two critical defects: D1 is solved by an append-only revisions table (`events` itself can stay as head), D2 by a `schema_migrations` table copied conceptually from `migrations.py`.
- `[FACT]` Reversibility is near-total: additive tables/columns can be stopped and dropped without touching rows; `events` keeps its content-hash `event_id` so replays remain comparable.
- `[INFERENCE]` It is the only option that keeps the measured acquisition pipeline (55k→375k rows, collectors, caches) valid during the change.

**What is lost / what breaks**
- `[INFERENCE]` It does **not** create a defensible evidence model: a source row still is not a documented fact; licence/quality/identity tiers must be added as columns or they stay in git.
- `[FACT]` It inherits the mutable-`events` semantics until the revision table is adopted by every writer; `upsert_events` has **9 call sites across 8 modules** (`git grep -n 'upsert_events(' origin/main -- medradar`: `__main__.py`, `adcom.py`, `clinical.py`, `collect_device.py`, `collect_drug.py`, `corpus.py`, `openfda_bulk.py` ×2, `nmpa.py`), so "all writers switched" is a real coordination task.
- `[INFERENCE]` A revision log without identity resolution reproduces B's problem with less structure; if the project later needs multi-source de-duplication (aggregator republishing), C has to grow the same tables B already has.
- `[FACT]` No edge/relation representation exists in S1 (probe: no relation table among the 17), so TKG/ATLAS graph work would live in adapters; C explicitly accepts a projection layer forever.

**Migration steps**
1. Freeze the semantics in a schema doc: one row = one source observation; head + revisions model.
2. Add `schema_migrations` + version stamp; make `_migrate` transactional and checksummed (pattern from `atlas/db/migrations.py`).
3. Add `event_revisions(event_id, content_hash, first_seen_at, payload_json, …)` with BEFORE UPDATE/DELETE/replace triggers; change `upsert_events` to insert-if-new + append revision-if-changed.
4. Normalise timestamps at write (`aware UTC`, fixed precision) and add a one-shot repair for legacy rows (D5/D6/D12); record `timestamp_basis` per axis.
5. Add `licence_status`, `quality_flags`, `match_confidence`, `matched_alias` columns; populate from registries.
6. Replace the dead `company_identifiers` write with a used identity table and one resolver; expose it to `studies/`.
7. Point TKG import at the revision table (now lossless) and keep graph_context as the graph reader.

**Effort:** 2–4 weeks for steps 1–4 (the critical defects), 4–8 weeks for 5–7. `[INFERENCE]`
**Risk:** medium — the data is not at risk, but a half-migrated revision log reintroduces ambiguity; requires discipline across **9 `upsert_events` call sites in 8 modules**.
**Reversibility:** high — additive; `events` content unchanged, new tables droppable.
**Falsifier:** if the Phase-0 question is specifically "which store may a paper cite", C fails: it makes `events` trustworthy but not sufficient as an evidence canon (no licence/quality/de-dup). Also if multi-source duplicate detection becomes a requirement in the next phase, C must be extended into B anyway.

---

## 8. Weighted decision matrix (`[INFERENCE]` scores; `[FACT]` evidence per criterion)

Scale 1 (bad) – 5 (good). Weights sum to 100 and were chosen before scoring; changing them is the sensitivity test in §8.1.

| Criterion | Weight | A TKG canon | B ATLAS canon | C events+revisions | Key evidence for the score |
|---|---|---|---|---|---|
| Semantic fidelity (one record = one documented fact) | 15 | 3 | **5** | 3 | §4.1; `evidence/schema.py:1-21` vs `db.py:57-84` |
| Immutability enforced by the store | 15 | **5** | 3 | 4 | probe trigger counts 7 / 0 / (addable 7) |
| Four time axes separated + precision | 15 | 2 | **5** | 3 | §4.3; measured 0/55,090 public times in A |
| Identity resolution + auditability | 12 | 3 | **5** | 3 | §3.3, §4.4; D7 |
| Schema evolution / migration safety | 8 | 4 | **5** | 3 | §4.6 (`schema_migrations` vs hard rebuild vs none) |
| Cross-store join integrity | 8 | 4 | 3 | **5** | §4.4; A has internal FKs, C keeps the existing keys |
| Licence / quality tagging | 7 | 2 | **5** | 1 | §4.5 |
| Operational cost at current scale | 6 | 3 | 4 | **5** | §4.7 (194.7 MB, O(n²), 32.6 s import) |
| Compatibility with `studies/` + `intelligence/` | 8 | 2 | 1 | **5** | consumer census §4.8 |
| Migration reversibility | 6 | 5 | 3 | **5** | adapter read-only / branch / additive |
| **Weighted total (÷5 = /100)** | **100** | **65.6** | **80.8** | **71.4** | arithmetic in §8.1 |

Raw weighted sums: A = 328, B = 404, C = 357.

### 8.1 Sensitivity (why the ranking is not a verdict)

All numbers below are recomputed from the same scores; only the weights change.

- **Fold mergeability into compatibility** (B's compatibility 1 → 0.5, weight 8): B = 404 − 4 = **400 → 80.0**; C stays **71.4**, A **65.6**. Ordering unchanged.
- **Immutability up to 20 and licence down to 2** (weights sum preserved): A = 328 +25 −10 = **343 → 68.6**; B = 404 +15 −25 = **394 → 78.8**; C = 357 +20 −5 = **372 → 74.4**. Ordering unchanged (B > C > A), margin B–C narrows from 9.4 to 4.4.
- **Compatibility-dominated weighting** (compatibility 34, joins 10, semantic/immutability/temporal 10 each, identity 8, schema 5, cost 6, reversibility 6, licence 1; B's compatibility = 0 because nothing on `main` consumes it): C = **420 → 84.0**, A = **302 → 60.4**, B = **272 → 54.4**. **This is the one weighting under which the ordering flips** (C > A > B).
- **If the delivered data snapshot is much smaller than the 375k claim**, the operational-cost penalty on A shrinks; but the 0/55,090 public-time result is independent of volume and keeps A's temporal score at 2.

`[INFERENCE]` The flip requires compatibility to carry more than a third of the total weight *and* B to score zero on it. That is exactly the Phase-0 question — "does an unmerged branch count as available?" — so the recommendation in §9 is a gate on E2, not on the arithmetic.

`[INFERENCE]` A is never first under the three weightings tested. It is at or above both alternatives only on immutability (5), schema evolution (4) and licence/quality (2); it can therefore win only under a weighting that makes *history safety* the dominant goal and treats temporal fidelity, cost and research compatibility as minor. That is a legitimate goal, and it is the one condition under which A should be revisited.

---

## 9. Conditional recommendation (`[RECOMMENDATION]`, decision prep only)

**Do not adopt a single canon in Phase 0.** Sequence the decision:

1. **Now (Phase 0/1, reversible): C.** Add `schema_migrations`, an append-only revision log, aware-UTC normalisation, licence/quality columns, and one used identity table to `events`. This fixes D1/D2/D5/D6 and forces the D12 demotion decision, making the data trustworthy **without** choosing a canon. It is the precondition for A and B anyway: neither can be evaluated against a store whose timestamps are 100 % unreadable.
2. **Then (Phase 1): run E1–E4 (§10).** If events can be projected into ATLAS evidence records with ≥95 % of rows carrying a real `source_public_at` and a resolvable identity, **B becomes the target canon**, with TKG retained as a derived graph/as-of index (not canon). This is the recommended target if E1/E2 pass.
3. **If E1 fails** (no defensible `source_public_at` for a material share of sources, or the evidence projection needs invented fields), **stay on C** and treat ATLAS as a source-side cache for the subset of sources where it fits. Do not promote TKG.
4. **Never silently promote A.** TKG is excellent at what it does (append-only, monotonic knowledge clock, deterministic export) and is recommended to remain the **derived index** for graph traversal and snapshot provenance. Promoting it to canon requires D5 fixed *and* licence/identity/migration added *and* all 17 `events` readers ported — three conditions that Phase 0 cannot verify.

**Why this is conditional, not a verdict:** the ranking (B 80.8 > C 71.4 > A 65.6) is driven by criteria that Phase 0 could only partly observe (`[UNVERIFIED]` data snapshot, branch mergeability, consumer intent). The recommendation is therefore a *decision tree with gates*, not a selection.

**Anti-recommendations**
- Do not migrate 375k rows into TKG before the timestamp repair: the measured outcome is a canon with no public clock.
- Do not run two canons in parallel without naming which one a paper may cite; D9 is already that failure at small scale.
- Do not add a fifth store; the repo already has 7 DDL-owning modules and 3 branch stores.

---

## 10. What we do NOT know, and the experiments needed

| ID | Unknown | Why it blocks a verdict | Experiment | Cost |
|---|---|---|---|---|
| **E1** | Can every `events` row family be projected into an ATLAS-style evidence record with a real `source_public_at` and an identity? | Decides B vs C | Build a 1,000-row stratified sample (one per `source`×`kind`), hand-map to `make_evidence`; report fields that would be invented | 1–2 days |
| **E2** | Is `origin/foundation/atlas-001` mergeable/portable onto `main`? | B's availability | `git merge-tree`/`git diff --stat origin/main...origin/foundation/atlas-001`; count conflicting files and duplicated modules; run `tools/verify_atlas.py` | 0.5–1 day |
| **E3** | How much of `available_at` is genuinely observed vs promoted? | D12 severity; whether A can ever be temporal | Run `audit.legacy_timestamp_promotions` against the shipped DB; cross-tab `timestamp_quality` × source × `published_at==event_date` | 0.5 day |
| **E4** | Is `market_bars` redundant next to `prices`, and which one do features use? | D8/D3 cost of unification | `git grep market_bars` consumer census + coverage diff on the real DB | 0.5 day |
| **E5** | TKG cost/perf at real scale without ad-hoc indexes | A's operational score | Import the full snapshot with and without the operational indexes; record time/bytes/export memory | 1 day |
| **E6** | Do any external consumers depend on `forecast_registry` / observatory file names/APIs? | B/C compatibility | Search CI, `scripts/`, `docs/`, and (if available) issue/PR history; ask owners | 0.5 day |
| **E7** | What is the authoritative identity policy going forward: the two branch resolvers (same policy, two implementations) or the six `main` paths? | RQ4 | Side-by-side evaluation on a labelled sample (`research/atlas/reports/identity_baseline_eval.json` exists) | 1–2 days |
| **E8** | Does the shipped snapshot actually have 375,378 event rows (and how many distinct `event_id` after re-collection)? | All size/cost projections are `[UNVERIFIED]` | Obtain the DB; `SELECT COUNT(*)`, distinct ids, quality distribution | 0.5 day |
| **U1** | Semantic definitions of "analyst time"/"evaluation time" (none of the stores has this axis) | A 5th clock may be needed by the eventual canon | Ask research owners; inspect `studies/` usage | — |
| **U2** | Whether `data/observatory` from the branch is meant to replace or complement the research DB | Affects whether there are 4 or 5 canons | Branch owner interview | — |
| **U3** | SQLite single-writer contention across 4 DB files under the new lane | operational risk for any canon | Concurrency probe (two processes writing `events` and `tkg` while a study reads) | 1 day |

**Decision rules** `[RECOMMENDATION]`
- E1 pass (`≥95 %` rows projectable, no invented `source_public_at`) **and** E2 pass (portable) → target B; else target C.
- E3 shows `<10 %` of rows with genuine observed public time → any "public-time canon" is aspirational; C + explicit `estimated` labelling is the honest ceiling.
- E5 shows full-scale import `>2 h` or export `>5 min` → A's operational score 3 is already generous; A stays out.

---

## 11. Appendix — provenance of every number

| Number / claim | Source |
|---|---|
| 7 DDL-owning modules, 26/38/0/0 intelligence DB, 6/7/7/6 TKG, 5/7/10/1 registry, 17/23/0/0 events DB, 21/30/0/0 ATLAS, 7/10/0/0 staging, 13/27/17/0 ledger | `_evidence/evidence/store_structure.json` (`stores[*].schema_structure`), probe run 2026-11-12, Python 3.12.10 / SQLite 3.49.1 |
| `replaced_in_place=True`, `revision_history_table=0` | `store_structure.json` → `behavioural.events_upsert_same_id` |
| TKG/forecast append-only rejections and exact messages | `store_structure.json` → `behavioural.tkg_append_only`, `behavioural.forecast_registry_append_only` |
| Timestamp divergence (`same_instant=False`) | `store_structure.json` → `behavioural.timestamp_rendering` |
| Naive `available_at` rejected by TKG | `store_structure.json` → `behavioural.legacy_available_at_to_tkg` |
| Contradictory `idx_market_bars_date` DDL | `store_structure.json` → `main_ddl_collisions.contradictory_index_names` |
| 55,090 rows → 171,800 assertions; 32.593 s / 13.661 s / 6.514 s; 194,723,840 B; **55,090 dropped public times**; source SHA unchanged | `experiments/reverse_rd_v2/tkg_import_report.json` (committed on `main`) |
| 2,000-node synthetic bench 0.1219 s / 0.071 s | `docs/research/tkg_bench_synthetic.json` (explicitly synthetic) |
| `db.py:519` in the old audit vs `db.py:537` at `b2a14c0` | `git show 7a639f7:medradar/db.py` vs `git show origin/main:medradar/db.py` |
| Branch table/trigger counts for S7/S8/S9 | probe `stores[4..6]` (DDL extracted with `ast` from `git show`; branch code not imported) |
| 375,378-row snapshot claim | `audit.py:47` — `[UNVERIFIED]`, `data/` is gitignored (`.gitignore:2`) |
| Branch test file sizes | `(git show <ref>:<path>).Count` (recorded in §3.5) |

**Reproduce the probe output exactly:**

```bash
python docs/refoundation/phase0/_evidence/evidence/probe_store_structure.py \
  --json-out docs/refoundation/phase0/_evidence/evidence/store_structure.json \
  --text-out docs/refoundation/phase0/_evidence/evidence/store_structure.txt
```

**Boundaries of this document**
- Branch-only stores are read from their DDL constants; their Python behaviour is not executed here. Any statement about their *runtime* behaviour is marked `[UNVERIFIED]` or sourced from the branch's own tests/docs.
- No row counts, quality distributions or performance numbers were measured on the shipped database, because it is not present in this worktree. All such values are either taken from the committed import report or marked `[UNVERIFIED]`.
- This is decision preparation. It deliberately does not select a canon; §9 is a gated recommendation whose gates are the experiments in §10.

---

## 12. Owner questions (answer before Phase 1 starts)

These are the only open questions that change the recommendation; everything else is measured above.

1. **Research owner:** is the canon's job (a) reproducing a published claim, (b) prospectively registering predictions, or (c) both? A and C optimise (a)/(c) differently, B partly serves both.
2. **Research owner:** which clock does a claim cite — `source_public_at` (third-party availability) or `first_seen_at` (our observation)? The answer decides whether TKG's one-clock model is a feature or a gap.
3. **Data-governance owner:** is licence/redistribution a gate on storage or only on publication? If storage-only, B's licence field moves from "necessary" to "useful" and the matrix changes.
4. **Platform owner:** is a second database file acceptable during migration, or is "one file" a hard operational requirement? (Determines whether B can coexist with `events` for a phase.)
5. **CI owner:** what is the budget for a branch merge + full test matrix (E2) before the next milestone?
6. **Audit owner:** are the defect severities in §6 acceptable as the Phase-0 defect register, or should D1/D5/D12 block all canon work until fixed?
7. **REFOUNDATION-002 Lead:** is "TKG is the single canon" still a *constraint* on Phase 1, or a *hypothesis* that E1/E5 may reject? The document is written on the latter reading; if it is the former, Options B/C need a TKG-projection clause and the matrix must be recomputed.
