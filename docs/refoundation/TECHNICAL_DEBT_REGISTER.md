# MedRadar — Technical Debt Register (REFOUNDATION-001)

> **Deliverable:** `TECHNICAL_DEBT_REGISTER.md` · **Auditor:** architecture-auditor (task-2)
> **Companion:** [`ARCHITECTURE_AS_IS.md`](ARCHITECTURE_AS_IS.md)
> **Labels:** **[FACT]** verified from bytes/commands · **[INFERENCE]** reasoned, chain stated · **[RECOMMENDATION]** proposed action · **[UNVERIFIED]** not checkable here.

---

## 0. Scope / Method / Evidence base / Limits

| Item | Statement |
|---|---|
| **Scope** | Duplicated/overlapping infrastructure across `main` and the 20 open branches; module incompatibilities; legacy/exploratory surface; dependency & build reproducibility; git data volume; CI gaps; secret/credential exposure (paths and kinds only — **no values**); automation opportunities. |
| **Method** | Each duplicate claim rests on **read code**, not filenames: blob SHAs from `git ls-tree` for identity, `git merge-base --is-ancestor` for inheritance vs copy, schema extraction for structural comparison, `difflib` similarity for near-duplicate detection (`_evidence/arch/{probe,cmp,tables}.py`). Line numbers are `blob:line` at the named ref. |
| **Evidence base** | [`_evidence/arch/`](_evidence/arch/) (probe scripts + `pytest_collect.txt`), [`../_evidence/ancestry.json`](_evidence/ancestry.json), [`../_evidence/blob_identity.json`](_evidence/blob_identity.json), [`../_evidence/copy_volume.json`](_evidence/copy_volume.json), [`../_evidence/collisions.json`](_evidence/collisions.json), [`../_evidence/repo_facts.json`](_evidence/repo_facts.json), [`../_FACTS.md`](_FACTS.md). |
| **Independently re-verified** | Blob identities for `medradar/product/{store,catalog,analyst}.py`, `medradar/observatory/ledger.py`, `medradar/atlas/{store,evidence/schema,identity/resolver,db/migrations,graph/build,quality/checks}.py`, `medradar/tkg/store.py`; ancestry for the #12/#13/#14 stack, ATLAS→CONVERGENCE, and HORIZON↛CONVERGENCE; 1,074 collected tests on `main`. |
| **Not verified** | GitHub-side state (PR mergeability, Actions run logs). Whether any operator's `data/*.sqlite` violates a schema. Runtime cost of the duplicated work (no execution on real data permitted). |
| **Doctrine** | `main` is the only shipped state; `#N` denotes the PR whose head branch carries the code. Inheritance is **not** reported as duplication: if base is an ancestor, the identical files are stack inheritance. |

### Severity scale

| Severity | Meaning |
|---|---|
| **Critical** | Blocks safe merge/refoundation, or creates data-integrity / legal risk today. Must be decided before any consolidation. |
| **High** | Guarantees rework or divergence if left; fix in the first refoundation wave. |
| **Medium** | Cost grows linearly with features; fix in wave 2. |
| **Low** | Hygiene; batch with adjacent work. |

### Summary counts

| Severity | Items |
|---|---|
| Critical | 6 |
| High | 13 |
| Medium | 15 |
| Low | 6 |
| **Total** | **40** |

---

## Part A — Nine duplicated infrastructures

**[FACT] Method note.** For each infrastructure I list *every* implementation found, then compare the six facets that decide mergeability: **schema shape**, **primary key**, **time fields**, **source identifiers**, **dedup rule**, **identity rule**. The verdict is `UNIFY` (one implementation, migrate data), `ADAPT` (keep one, convert others mechanically), or `KEEP-SEPARATE` (legitimately different purpose). "Branch" means the code is not on `main`.

---

### A1. Evidence Store — **6 implementations, mutually incompatible models** · **Critical**

| # | Implementation | Where | Tables / shape | PK | Time fields | Source id | Dedup rule |
|---|---|---|---|---|---|---|---|
| 1 | **`events` table (shipped)** | `main` `medradar/db.py:57-80` | 1 flat table, `payload TEXT` untyped | `event_id = sha1(source\|kind\|parts)[:32]` (`db.py:268-272`) | `event_date`, `as_of`, `published_at`, `first_seen_at`, `available_at`, `timestamp_quality`, `fetched_at` | `source` string + `kind` | `INSERT OR REPLACE` on `event_id` (`db.py:537`) → **mutable** |
| 2 | **TKG inline evidence** | `main` `medradar/tkg/store.py:88-133` | `nodes`/`edges`, evidence *columns* not a table | `(type,id,recorded_at,seq)`; `assertion_id = "sha256:"+hash` | `valid_from/valid_to`, store-assigned `recorded_at`, optional `public_time(+basis)` | `source_locator` + `evidence_sha256` | append-only + `idempotency_key`; triggers reject UPDATE/DELETE/REPLACE (`store.py:146-187`) |
| 3 | **`temporal_edges`-style relational facts** | `main` `medradar/intelligence/storage.py:82-96` (also 18-52, 55-79) | `temporal_edges`, `financial_facts`, `procurement_awards`, `company_identifiers` — all in the **same DB file** as `events` | `edge_id = sha1(subject\|relation\|object\|source\|evidence_id)[:32]` | `valid_time`, `available_at`, `created_at` (+ `pit_usable` flag for procurement) | `evidence_source` + `evidence_id` | `INSERT OR REPLACE` (`:222`) → **mutable** |
| 4 | **Observatory ledger** | **#13/#14** `medradar/observatory/ledger.py:78-368` | 13 tables incl. `observation`, `observation_version` (`payload_hash`), `observation_change` | `observation_id`; version PK `version_id` | `first_seen_at` (immutable trigger), `ingested_at`, `event_at(+precision)`, `published_at(+precision)`, `source_updated_at(+precision)` | `source` + `source_record_id` + `record_type` | version-on-change; 17 immutability triggers |
| 5 | **ATLAS evidence** | **#28/#30** `medradar/atlas/db/migrations.py` + `evidence/schema.py:148-227` | `evidence` (20 cols) + `evidence_head` + `evidence_identifiers` + `evidence_entity_refs` + `raw_objects` | `(evidence_id, version)`; `evidence_id = ev_<sha256(source_id\|evidence_type\|source_record_id)[:32]>` (`schema.py:111-114`) | `event_at`, `source_public_at`, `first_observed_at`, `fetched_at`, `time_quality` | `source_id` + `source_record_id` + `source_url` | append-only versions; `first_observed_at` is earliest; `content_hash` = normalized hash |
| 6 | **DATA-EXPANSION evidence** | **#27** `medradar/external_sources/store.py` + `schema.py:166-227` | 7 tables: `evidence` (13 cols), `evidence_head`, `entity_refs`, `identifiers`, `raw_objects`, `collection_runs`, `request_log` | `(evidence_id, content_hash)` | `first_observed_at`, `fetched_at`, `event_at`, `source_public_at`, `time_quality` | `source_id` + `source_record_id` + `source_url` | append-only; `duplicate_of` pointer on `evidence_head` |

**Near-duplicate proof [FACT]:** implementation 6 is a **fork of implementation 5**. ATLAS `identity/normalize.py:8-11` states verbatim: *"Ported from `medradar.external_sources.identity` (DATA-EXPANSION-001, `origin/research/data-expansion-001`)"*. Measured with `difflib` (`cmp.py`): `evidence/schema.py` 42.4 % similar / 139 identical lines; `store.py` 19.8 % / 101 identical lines; `identity/normalize.py` vs `identity.py` 24.0 % / 81 identical lines.

**Incompatibility [FACT]** — the six disagree on *all* merge-critical axes:
- identity: hash-of-source-record (1,5,6) vs hash-of-assertion-content (2) vs hash-of-label-triple (3) vs opaque uuid-ish (4);
- mutability: (1,3) replace; (2,4,5,6) append-only;
- evidence-as-row (5,6) vs evidence-as-column (2) vs evidence-as-JSON-payload (1,3,4).

**Verdict: UNIFY** on one append-only evidence record with versioning and content hashes (ATLAS model is the most complete: content hash + normalized hash + identifiers + entity refs + `raw_objects`). `events` becomes a *projection* or is migrated; TKG assertions reference `evidence_id` instead of embedding `evidence_sha256`. Severity **Critical** — this is the root cause of TD-001/TD-004/TD-033.

---

### A2. Entity / Identity Resolver — **6 implementations (+1 study ontology)** · **Critical**

| # | Implementation | Where | Identity input | Rule | Persistence |
|---|---|---|---|---|---|
| 1 | `CompanyRegistry.resolve` | `main` `config.py:209-234` | free-text applicant | exact alias 1.0; token-containment 0.95–0.99; else token Jaccard; threshold **0.82** | none (in-memory, rebuilt per process) |
| 2 | `company_identifiers` table | `main` `intelligence/storage.py:18-29` | `scheme`+`identifier`+`source` | composite PK; `valid_from/valid_to/available_at/confidence` | SQLite (same DB) |
| 3 | product alias registry | **#12** `product/entities.py:29-39,133` + `entity_aliases.json` + `entity_map` (`product/store.py:138-155`) | applicant / `company_key` | `exact_alias_map`, `resolve_applicant`, `alias_review_pending` | SQLite `entity_map` + JSON |
| 4 | Observatory mapping | **#13/#14** `observatory/mapping.py:36-62` + `observation_mapping` table | source-specific (`sec_filing`, `ctgov_study`, `europepmc_publication`) | `MAPPING_VERSION = "obs-mapping-v1"`, `_MAPPED_CONFIDENCE = 0.95`, ambiguity candidates | SQLite (`observation_id, mapped_at`) |
| 5 | ATLAS identity | **#28/#30** `atlas/identity/{normalize,resolver,models,companies}.py` | 15 schemes (`di`,`basic_udi_di`,`510k`,`pma`,`denovo`,`product_code`,`licence_no`,`mdall_*`,`duns`,`nct`,`doi`,`pmid`,`patent_no`,`ocid`) + device views | `SAME_DEVICE_IDENTITY`…`UNKNOWN`; `CONFIRMED/CANDIDATE/REJECTED`; `source_declared/derived/inferred` | SQLite (`companies`,`company_names`,`device_identifiers`,`entity_relations`) + `config/atlas_firms.json` |
| 6 | DATA-EXPANSION identity | **#27** `external_sources/identity.py` (431 L) + `entity_refs` | scheme normalisers + `resolved_key`/`method`/`confidence` | per-scheme canonicalisation, method-tagged | SQLite |
| (7) | S-029 ontology (study) | **#16** `research/studies/relation_network_s029/RELATION_ONTOLOGY.md` | `ent:<type>:<slug>`, exact-string aliases + `identity_evidence` | deterministic identity confidence, 4 clocks | JSON artefacts only |

**Incompatibility [FACT]** — five different company keys can exist for the same firm: `company_key` (config), `entity_id` (observatory), `company_id` (ATLAS), `resolved_key` (DATA-EXPANSION), `ent:company_legal:<slug>` (S-029). No crosswalk table exists in any branch. `collisions.json` shows 7 branches modifying the same product files, i.e. the pressure to add *more* resolvers continues.

**Verdict: UNIFY.** One resolver (ATLAS's, with scheme-scoped normalisation) + one alias registry + one persisted identifier table with `valid_from/valid_to`. Company aliases currently live in **two** shipped files (`config/companies_device.json`, and on #12 `product/entity_aliases.json`) — that alone is TD-019. Severity **Critical**.

---

### A3. Temporal Knowledge Graph — **5 implementations + 2 study models** · **High**

| # | Implementation | Where | Model | As-of semantics | Invariants |
|---|---|---|---|---|---|
| 1 | **TKG store** | `main` `tkg/store.py` (6 tables, 7 triggers), `tkg/query.py` | assertion revisions per node/edge; system-knowledge clock only | `known_at` gates `recorded_at` → latest revision per identity → then `valid_at` cut (`query.py:1-17`, `:75-167`) | append-only triggers, clock guard, idempotency ledger, schema stamp `tkg-schema-2` |
| 2 | **`temporal_edges`** | `main` `intelligence/storage.py:82-96` | one row per (subject,relation,object) with `assertion_status` | none (no as-of query; plain table scan) | none |
| 3 | **`graph_context`** | `main` `intelligence/graph_context.py:48-52,269-300` | derives `company_event`/`event_in_track`/`event_has_code` edges from `events` at query time | own `_cutoffs(known_at, valid_at)` | none; read-only |
| 4 | **ATLAS graph** | **#28/#30** `graph/build.py` (124 L, source-declared relations only), `entity_relations`/`relation_events` | versioned-relations-with-revocation (`revoked_at`), not assertion revisions | `research/asof.py:36` with `observed/public_inferred/unprovable` | append-only relations; relation events |
| 5 | **S-028 study model** | **#15** `research/studies/graph_early_signal_s028/GRAPH_SCHEMA.md` | bipartite `Company–TechnologyTrack`, single edge `ACTIVITY_IN`, 12-month rolling, per-cutoff snapshots | snapshot per forecast origin `t` with `available_at ≤ t` | research protocol |
| 6 | **S-029 study model** | **#16** `research/studies/relation_network_s029/RELATION_ONTOLOGY.md` | claims not edges; `entity_id`, 4 clocks, deterministic identity | frozen ontology | research protocol |
| (7) | CONVERGENCE graph | **#30** `integration/graph.py` (319 L) | builds links over `conv_*` staging | inherits contract clocks (`clock.py:36-41`) | none |

**[FACT]** `main` alone answers "what did we know about X at T" three different ways (1,2,3), with three different answers to "is a triple evidence" (no / yes-as-row / yes-if-derived).

**Verdict: ADAPT + UNIFY.** Keep **TKG storage invariants** (append-only + store clock + schema stamp) as the mechanism; take the **relational model** from ATLAS/S-029 (typed relations with evidence refs and status) because TKG-MVP's `edges.attrs` is unstructured. Explicitly retire (2) and fold (3) into a query API over the unified store. Severity **High**.

---

### A4. Data Source Registry — **8 implementations** · **High**

| # | Implementation | Where | Shape | Actually used? |
|---|---|---|---|---|
| 1 | `config/sources.json` | `main` `config/sources.json` | JSON: base URL, endpoints, rate limits, `public_domain`, blocked-source note | **No.** Only referenced as a filename in `onboarding.py:51` (a "required files" list). `git grep` finds no loader. **[FACT]** decorative |
| 2 | `audit.EXPECTED_SOURCES` | `main` `audit.py:19-28` | hard-coded dict of 7 source→kind pairs | yes (audit only) |
| 3 | `intelligence/sources/*.py` | `main` 6 modules | one hard-coded collector per source | yes (forecast lane) |
| 4 | `COLLECTORS` dict | `main` `__main__.py:39-45` | 5 module paths | yes (run lane) |
| 5 | Observatory `source_state` | **#13/#14** `observatory/ledger.py:174-197` | per-source operational state: cadence, watermark, status, failure counts | yes |
| 6 | `external_sources/registry.py` | **#27** | `SCHEMA_ID = "medradar.external.source_register.v1"`, `TRISTATE`, probe-merged records | yes (its branch) |
| 7 | ATLAS sources | **#28/#30** `config/atlas_sources.json`, `source_status`, `connectors/base.py:42-137` | JSON + provenance + run logs | yes |
| 8 | HORIZON registry | **#29** `research/horizon/registry/sources/*.json` (**51 files**) + `CONNECTORS/*/_util.py` | one JSON per source; per-family HTTP clients | yes (its branch) |

**[FACT]** That is **four different registry file formats** (`sources.json`, `atlas_sources.json`, `registry/sources/*.json`, `source_register.v1` records), plus three code-level registries and one operational table — and the *only* one on `main` that looks like a registry does not drive anything.

**Verdict: UNIFY.** One machine-readable registry (schema = DATA-EXPANSION's `source_register.v1`, which is the only one with validation + tri-state probe status), generated adapters, and `source_state` as the *operational* companion. Delete `config/sources.json` or make it the registry. Severity **High**.

---

### A5. Observation Ledger — **4 implementations** · **High**

| # | Implementation | Where | Granularity | Immutability |
|---|---|---|---|---|
| 1 | `events` + `runs` | `main` `db.py:57-146` | one row per source record (replaceable) | none (`INSERT OR REPLACE`) |
| 2 | `live_alerts` | `main` `db.py:148-163` | one row per detected catalyst | none |
| 3 | **Observatory ledger** | **#13/#14** `ledger.py:78-368` | observation + version + change + status history + mapping + phase + run/checkpoint/failure | **17 triggers**, `first_seen_at` and identity immutable (`:283-300`) |
| 4 | ATLAS `observations` | **#28/#30** `db/migrations.py` | one row per (entity_ref, field, value_json, observed_at, evidence_id, run_id) | append-only by design |
| (5) | DATA-EXPANSION `evidence_head.first_observed_at` | **#27** | earliest observation per evidence id, `duplicate_of` | append-only |

**[FACT]** The Observatory ledger is a **drop-in replacement** for `events` on the observation axis (it even names `source_record_id`, `first_seen_at`, `payload_hash`) but is not on `main` and is not compatible with `analyze.py`. It is also the best instrumented of the four (watermarks, resumable runs, per-source failure log, ops metrics).

**Verdict: UNIFY** with A1/A3: one append-only observation log (schema = Observatory's `observation`+`observation_version`, invariants = TKG's), with `events` as a derived view. Severity **High**.

---

### A6. Forecast Registry — **3 stores, 2 write paths** · **Medium-High**

| # | Implementation | Where | Tables | Mutability | Consumer |
|---|---|---|---|---|---|
| 1 | **`forecast_registry.py`** | `main` (5 tables, 10 triggers, `forecast-registry-2`) | `forecasts`, `resolutions`, `forecast_idempotency`, `meta`, `clock_guard` | append-only + idempotency; store clock | `scripts/forecast_cycle.py`, CLI `python -m medradar.forecast_registry` |
| 2 | **`forecast_examples` + `horizon_forecasts`** | `main` `intelligence/storage.py:98-132` | 2 tables in the *main* DB | `INSERT OR REPLACE` (`:244`); `replace_examples` deletes by `dataset_version` (`:231`) | `forecasting/horizon.py`, `cycle.py` |
| 3 | **`forecast_set_v1` JSON** | `main` `intelligence/forecasts.py:22-25` | none (in-memory document) | n/a | `score()` / `validate_forecast_set()` |

**[FACT]** Two independent implementations of the *same* domain object (a registered, resolvable forecast) with opposite durability rules; `registry_adapter.py:129` is the only bridge and it *copies* rows from (2) into (1), so the same forecast exists twice with two ids (`forecast_id` vs `prediction_id`).

**Verdict: KEEP-SEPARATE storage, ADAPT the API.** The registry (1) is correct as the audit-grade record. Table (2) should become either a *staging* area with a documented one-way promotion, or a view over (1). Drop (3) or make it a rendering of (1). Severity **Medium-High** (TD-013).

---

### A7. Research Query Engine — **6 implementations** · **High**

| # | Implementation | Where | Query semantics | Language |
|---|---|---|---|---|
| 1 | `tkg/query.py` | `main` (168 L) | `known_at` then `valid_at`, latest-revision-first | Python over `store.raw` |
| 2 | `intelligence/graph_context.py` | `main` (391 L) | own `_cutoffs`, chunked edge fetch (`_IN_CHUNK = 400`) | SQL fragments |
| 3 | `product/store.py` | **#12** (3,152 L) | window/granularity/period-completeness/radar queries over `events` | hand-assembled SQL (92 module-level functions, 65 inline `SELECT`s) |
| 4 | `atlas/graph/query.py` + `research/asof.py` | **#28/#30** (248 L + 167 L) | company→devices, tech→companies, evidence paths; as-of with 2 bases | Python + SQL |
| 5 | CONVERGENCE `integration/graph.py` | **#30** (319 L) | authoritative links over `conv_*` | Python |
| 6 | HORIZON ad-hoc | **#29** | per-source probe scripts | scripts |

**[FACT]** (1),(2),(4) implement **as-of** queries with three different cutoff rules; (3) is the only one with window-completeness semantics (`complete_window`, `window_completeness`, `is_period_partial` at `product/store.py:448-649`) — a genuinely valuable concept that exists nowhere on `main`.

**Verdict: UNIFY** into one query service with (a) as-of contract from (1)/(4), (b) completeness contract from (3). Severity **High**.

---

### A8. Data Quality Validator — **6 implementations** · **High**

| # | Implementation | Where | Checks | Output |
|---|---|---|---|---|
| 1 | `audit.run_audit` | `main` `audit.py:71-244` | expected sources, match rate, stale dates, prices, legacy timestamp promotions | JSON + Markdown |
| 2 | `leakage_audit.audit_examples` | `main` `intelligence/evaluation/leakage_audit.py:298-408` | temporal leakage (replay base/entry features, financial as-of) | JSON |
| 3 | `stats_cmd.data_stats` | `main` `stats_cmd.py:441-827` | dataset scale/distribution/consistency | JSON + Markdown blocks |
| 4 | Observatory audit/validation/health | **#14** `audit.py` (**2,683 L**, 3 verdicts), `validation.py` (427 L), `health.py` (352 L) | ledger integrity, slots, duplicate/latency stats, disk, deployment | JSON + evidence runs |
| 5 | ATLAS quality | **#28** `quality/checks.py:45-263` | 8 checks incl. `check_duplicate_records`, `check_time_anomalies`, `check_identity_contradictions`, `check_licence_restrictions` | `quality_findings` table |
| 6 | Study-level audits | **#15/#16** | `TEMPORAL_LEAKAGE_AUDIT(_CORRECTION).md`, `RANDOMISATION_DEFECT_ANALYSIS.md`, `DATA_QUALITY_REPORT.md` | Markdown only |

**[FACT]** The `_FACTS.md` contradiction C8 (competing state files) is the same phenomenon: `research/STATE.json` + `AUDIT.json` + `FINAL_AUDIT.json` + `BACKLOG.yaml` are four unversioned assertions about quality. **[FACT]** `#14`'s `audit.py` is **2,683 lines**, larger than any module on `main` except `report.py`/`replay.py` — a maintenance liability.

**Verdict: ADAPT.** One validator contract (`finding_id, severity, subject, detail, evidence_ids, run_id, status` — ATLAS's `quality_findings` is already that shape), pluggable checks per dataset, single result store. Retire doc-only audits as the *mechanism*. Severity **High**.

---

### A9. Licensing Engine — **4 implementations, none on `main`** · **High (legal risk)**

| # | Implementation | Where | Mechanism | Data |
|---|---|---|---|---|
| 1 | **ATLAS licence field + check** | **#28/#30** `evidence/schema.py` (`licence_status` in every record; `LICENCE_STATUSES`), `quality/checks.py:235` `check_licence_restrictions` | per-record status + quality finding | `evidence.licence_status` |
| 2 | **HORIZON licence evidence** | **#29** `research/horizon/CONNECTORS/industry/_licence.py` + `DATASETS/industry/LICENCE_EVIDENCE.json` | fetch the terms page, store bytes + sha256, extract quoted sentences; registry `licence_note` must quote one | raw HTML + extracted sentences |
| 3 | **CONVERGENCE policy engine** | **#30** `medradar/integration/licence.py:92-244` (`LicencePolicy`, `config/convergence/licence_policy.json`) | decisions: `may_ingest`, `may_redistribute`, `may_analyse_locally`, `attribution_required`, `quarantined_sources/paths` | policy JSON |
| 4 | PHOENIX licence audit | **#24** `docs/PHOENIX_LICENSE_AUDIT.md`, `docs/PHOENIX_EXTERNAL_PROJECT_REGISTER.md` | document-only audit of external projects | Markdown |
| 5 | `main` | — | **none** (grep for `licence` on `medradar/` finds only narrative strings: `publications.py:227`, `market_data.py:32`) | — |

**[FACT]** The three executable implementations are **complementary, not redundant**: (1) records status, (2) obtains evidence, (3) decides policy. But they use three vocabularies and no shared source-id namespace, so they cannot currently be composed.

**Verdict: UNIFY** — `licence_status` enum from (1) as the data contract, (2) as the evidence producer, (3) as the decision function. This is the only area where "unify" means *assemble* rather than *pick one*. Severity **High** because shipping branch data without a machine-readable licence decision is a redistribution risk.

---

### A10. Cross-infrastructure summary

| Infrastructure | Implementations | On `main` | Newest/best | Verdict | Severity |
|---|---|---|---|---|---|
| Evidence Store | 6 | 3 | ATLAS | UNIFY | Critical |
| Entity/Identity Resolver | 6 (+1 study) | 2 | ATLAS | UNIFY | Critical |
| Temporal Knowledge Graph | 4 (+2 studies) | 3 | TKG invariants + ATLAS model | ADAPT→UNIFY | High |
| Data Source Registry | 8 | 4 | DATA-EXPANSION `source_register.v1` | UNIFY | High |
| Observation Ledger | 4 | 2 | Observatory ledger | UNIFY | High |
| Forecast Registry | 3 | 3 | `forecast_registry.py` | KEEP/ADAPT | Medium-High |
| Research Query Engine | 6 | 2 | TKG `query.py` + `product/store.py` completeness | UNIFY | High |
| Data Quality Validator | 6 | 3 | ATLAS `quality/checks.py` | ADAPT | High |
| Licensing Engine | 4 | 0 | compose (1)+(2)+(3) | UNIFY | High |

**[INFERENCE]** The pattern is consistent: **the newest branch is almost always the best-specified implementation, and it is always unreachable from `main`.** Any refoundation that starts from `main` and "adds branches later" will re-create these nine splits within one release cycle.

---

## Part B — Ranked register (40 items)

Ranked by severity, then by blast radius. `#N` = PR/branch where the code lives.

| ID | Sev | Area | Finding | Evidence (locators) | Impact | Disposition |
|---|---|---|---|---|---|---|
| TD-001 | Critical | Evidence store | Six evidence implementations with incompatible identity/mutability rules (§A1) | `db.py:57-80,268-272,537`; `tkg/store.py:88-133`; `storage.py:82-96`; `#14 ledger.py:78-368`; `#28 migrations.py`; `#27 store.py`; port note `atlas/identity/normalize.py:8-11` | every downstream metric is computed over an evolving, half-auditable fact model | **UNIFY** on versioned evidence + content hash |
| TD-002 | Critical | TKG | `main` holds three graph/TKG answers (§A3): `tkg/`, `temporal_edges`, `graph_context` | `tkg/store.py:68-188`; `storage.py:82-96`; `graph_context.py:48-52,269-300` | no single as-of truth; divergence invisible until results differ | **ADAPT** to one store + one query API |
| TD-003 | Critical | Identity | Six resolvers; company has ≥5 incompatible keys; no crosswalk (§A2) | `config.py:209-234`; `storage.py:18-29`; `#12 product/entities.py:29-39`; `#14 mapping.py:36-62`; `#28 identity/*`; `#27 identity.py` | joins across stores are guesses; entity-level recall/precision unmeasurable | **UNIFY** resolver + identifier table |
| TD-004 | Critical | Integrity | The shipped event store is **mutable**: `INSERT OR REPLACE` on `event_id` (`db.py:537`), while every newer store is append-only | `db.py:490-545`; contrast `tkg/store.py:146-187`, `forecast_registry.py:190-224`, `#14 ledger.py:283-368` | a re-run can silently rewrite historical facts a backtest already consumed | **ADAPT**: append-only `events` (or `event_version` table) |
| TD-005 | Critical | Provenance | `#30` copied 651/813 files (80.1 %) from `#29` though `#29` is **not** an ancestor; committed `research/convergence/h2/_recovered/blob_*.py` show the mechanism | `merge-base --is-ancestor origin/research/horizon-001 origin/integration/convergence-001` → false; [`copy_volume.json`](_evidence/copy_volume.json) | two divergent copies of 690 k lines; fixes will not propagate; review impossible | **REBASE/MERGE** HORIZON into CONVERGENCE properly, or declare HORIZON the only source |
| TD-006 | Critical | Legal | No licence engine on `main`; 3 partial engines on branches; HORIZON committed third-party raw pages | §A9; `#30 integration/licence.py:92-244`; `#29 _licence.py`; `#28 quality/checks.py:235` | redistribution decisions undocumented at the data layer | **UNIFY** licence contract |
| TD-007 | High | Migrations | Primary store has **no schema version, no migration table**; `_migrate` does `ALTER`+blanket `UPDATE` (`db.py:287-316`); changed column definitions are silently ignored by `CREATE TABLE IF NOT EXISTS` | `db.py:19-231,287-316` vs `#28 db/migrations.py` (`schema_migrations`) | any refoundation of `events` cannot deploy safely | **ADOPT** ATLAS-style versioned migrations |
| TD-008 | High | Reviewability | PR base metadata contradicts ancestry: #22 declares `main` but contains #12→#14; #21 targets the PR-less `integration/phase4-base` | [`../_FACTS.md` §3](_FACTS.md); ancestry verified | #21/#22 diffs re-present the whole product stack as new; reviewers cannot see the actual delta | **RESTACK** PRs with truthful bases; open a PR for `phase4-base` |
| TD-009 | High | Source registry | 8 registries; `config/sources.json` is never loaded (`onboarding.py:51` only) | §A4; `git grep sources.json` → 1 hit | governance illusion; adding a source requires touching 3+ places | **UNIFY** + delete or wire `sources.json` |
| TD-010 | High | Observation | 4 ledgers with different immutability (§A5); best one (`#14`, 13 tables/17 triggers) is off-main | `#14 ledger.py:78-368`; `db.py:57-146`; `#28 migrations.py observations` | point-in-time claims cannot be proven from the shipped store | **UNIFY** |
| TD-011 | High | Build | **No dependency lockfile, no pinned install**: `pip install .` in CI resolves unpinned; only `pyproject.toml` exists (no requirements/tox/uv.lock/poetry.lock) | `pyproject.toml:13-18`; `ci.yml` install step; `git ls-tree` finds no lock file | CI is non-reproducible; a PyPI release can break `main` silently | **ADD** lock + hash-pinned install |
| TD-012 | High | CI | No lint, type-check, coverage, or security job anywhere | `ci.yml` (3 jobs: `test` matrix ×3 Python, `data-stats`, `windows-install`); `weekly.yml` | whole classes of defects (unused imports, type drift, leaked credentials) unblocked | **ADD** ruff/mypy/pip-audit gates |
| TD-013 | High | Forecast | Forecast is recorded in three places with two id names (`forecast_id` vs `prediction_id`) and two durability rules (§A6) | `forecast_registry.py:112-224`; `storage.py:98-132,243-257`; `forecasts.py:22-25`; `registry_adapter.py:129` | cohort evaluation can double-count or lose forecasts | **ADAPT** staging→promotion |
| TD-014 | High | Reproducibility | Forecast lane not reproducible from a clean clone: needs 276 MB gitignored `data/research.sqlite`; workflow header says it was never executed; registry DB gitignored | `forecast-cycle.yml` header + steps; `scripts/forecast_cycle.py` | the only continuous-ML claim in the repo cannot be reproduced or reviewed | **ADD** fixture-sized reproducible cycle + committed artefact |
| TD-015 | High | Git volume | All refs hold **476.46 MiB** unique blob bytes vs **29.06 MiB** on `main`; `research` alone 232.76 MiB / 2,515 blobs, `experiments` 188.21 MiB | `git rev-list --objects --all` + `cat-file --batch-check` (§Part G) | clone/fetch cost and review noise scale with abandoned drafts | **PRUNE** investigation artefacts; archive outside git |
| TD-016 | High | Data governance | Committed generated artefacts dominate churn: `docs/dashboard.html` 3.35 MB × 4 revisions, `docs/preview.png` 489 KB × 12, `docs/metrics.json` 474 KB × 11 | `git rev-list --count origin/main -- docs/dashboard.html` etc. (§Part G) | history is ~3× the working tree; diffs unreadable | **STOP** committing generated HTML; publish as Pages artifact only |
| TD-017 | High | Governance | Public Pages site is rebuilt weekly by a job that runs `--with-trade --with-replay`, deploying a simulated-trading narrative with no test gate | `weekly.yml` run step; `paper.py:51-67` (`ENGINE`, `DISCLAIMER_ZH`) | readers may read simulated results as advice | **SEPARATE** research site from trading demo; add test gate |
| TD-018 | High | Maintainability | Mega-modules with no seam: `report.py` 4,520 L, `replay.py` 3,088 L, `#14 audit.py` 2,683 L, `evalstats.py` 1,455 L, `families.py` 1,439 L | line counts via `probe.py ls` | every change is a merge-conflict magnet; review cost dominates | **SPLIT** by output/stage |
| TD-019 | High | Identity drift | Two shipped alias registries: `config/companies_device.json` (mutable by `watchlist`) and `#12 product/entity_aliases.json` | `onboarding.py:418-469`; `#12 product/entities.py:29-39` | the same firm can resolve differently depending on entrypoint | **UNIFY** alias source of truth |
| TD-020 | Medium | Runtime | `medradar run` calls `build_metrics` **twice** (lines 295-296 and 348-349) | `__main__.py:286-355` | 2× dominant CPU cost per weekly run; larger double-run windows for divergence | **REFACTOR** to build→enrich |
| TD-021 | Medium | Storage | `market_bars` declared twice with conflicting index definitions; same index name, different columns | `intelligence/storage.py:133-146` vs `intelligence/sources/market_data.py:69-84` | first module to run wins; second silently no-ops → index shape depends on import order | **DELETE** one definition |
| TD-022 | Medium | Consistency | `table_count()` whitelist omits 3 tables that exist in `SCHEMA` (`live_pending`, `live_skips`, `llm_verdicts`) | `db.py:333-347` vs `:204-230` | status/summaries under-report; operators cannot see retry backlog | **FIX** whitelist → derive from schema |
| TD-023 | Medium | Discoverability | `tkg` and `forecast_registry` entrypoints are invisible from `medradar --help` (separate `-m` parsers) | `__main__.py:761-956`; `tkg/__main__.py:216-247`; `forecast_registry.py:1227` | the best-engineered components are effectively unused | **ADD** delegating subcommands |
| TD-024 | Medium | Test/CI mismatch | CI runs `python -m medradar selftest` (`unittest` discover), not `pytest`; `pyproject` configures pytest | `__main__.py:751-757`; `ci.yml`; `pyproject.toml:45-47` | two runners can disagree; local green ≠ CI green | **PICK** one runner |
| TD-025 | Medium | Render contract | Renderers consume untyped `metrics.json`; missing keys degrade to `暂无数据` silently; `_audit_guess` guesses an input path | `report.py:35,4445`; `dashboard.py:87,114` | schema drift is invisible until visual inspection | **ADD** metrics schema + validation |
| TD-026 | Medium | Docs/state | `research/STATE.json` records a local Windows path (`<REDACTED_LOCAL_PATH>) and `main_untouched_at: 7a639f7`, but actual `main` is `b2a14c0`; claims "795 tests" vs 1,074 collected | `research/STATE.json` (`working_tree`, `last_verified`) | committed provenance is wrong; readers cannot tell which tree produced the results | **FIX** provenance or move to artefacts |
| TD-027 | Medium | Competing state | Four unversioned "current state" files: `research/{STATE.json,AUDIT.json,FINAL_AUDIT.json,BACKLOG.yaml}` | `_FACTS.md` C8; files present on `main` | no single source of truth for status | **DESIGNATE** one machine-readable state |
| TD-028 | Medium | Config | Config is untyped JSON; `config/universe_v1.json` is 1.71 MB; `watchlist_add` rewrites `companies_device.json` in place with no schema check | `config.py:157-169`; `onboarding.py:418-469` | a malformed edit surfaces deep in scoring, not at load | **ADD** JSON-schema validation |
| TD-029 | Medium | CLI growth | `__main__.py` collects 20 subcommands on `main` → 21 (#12) → 32 (#13) → 44 (#14); manual `sub.add_parser` accepted everywhere, nobody adds migrations later | subparser counts by ref (`probe.py`) | CLI is the only integration surface; every module added = new subcommand | **INTRODUCE** plugin/command registry |
| TD-030 | Medium | Query duplication | Six query engines (§A7); the only period-completeness logic lives in an unmerged 3,152-line module | `#12 product/store.py:448-649`; vs `tkg/query.py` | re-derivation risk; completeness semantics lost if #12 is dropped | **EXTRACT** completeness contract |
| TD-031 | Medium | Graph ontology | S-028 (`ACTIVITY_IN` bipartite) and S-029 ("a triple is not evidence") are **incompatible models**, both unmerged, both over the same data | `#15 GRAPH_SCHEMA.md`; `#16 RELATION_ONTOLOGY.md` | refoundation cannot adopt "a graph" without choosing one and voiding the other's results | **DECIDE** one model in the target architecture |
| TD-032 | Medium | Time handling | Three canonical-moment renderers: `tkg/_time.py`, `forecast_registry.normalize_moment:239-277`, `#28 evidence/timeq.py:62-119` | cited files | mixed precision breaks lexical=chronological ordering if ever crossed | **EXTRACT** one time library |
| TD-033 | Medium | Cross-store keys | No documented join key between `events.event_id`, `observations.observation_id`, `evidence.evidence_id`, `forecast.prediction_id` | §A1/A5/A6 | lineage queries need ad-hoc hash recomputation | **PUBLISH** a lineage map |
| TD-034 | Medium | Legacy surface | `live` lane (7 tables, 1,183-line `live.py`) performs *simulated trading* inside the shipped CLI and is exposed in `--help` | `db.py:148-230`; `live.py`; `__main__.py:858-877` | users can mistake simulation for capability; schema surface grows for one research feature | **SEPARATE** experiment package / flag |
| TD-035 | Low | Artefacts | 657 `experiments/` files (15.05 MiB) + 22 committed `verifier/` files (13 test transcripts + 6 `.meta` + README/criteria/verify) + `tools/*.log` are shipped in the package repo | `git ls-tree`; §Part G | clone noise; the *product* is 1.77 MiB of `medradar/` | **MOVE** to artefacts/archive |
| TD-036 | Low | Tooling | Ad-hoc state-mutation scripts commit: `tools/update_state_cycle33/37/38/39.py`, `round_end.py`, `final_audit.py` | `tools/` listing | provenance by regex-rewriting Markdown; brittle | **RETIRE** after TD-027 |
| TD-037 | Low | Credentials | No secret values committed; **but** `tools/github_api.py` shells out to `git credential fill` and holds a token in memory | `tools/github_api.py:1-45`; scan in §Part I | a repo tool that extracts the developer's GitHub token is a supply-chain foot-gun | **REMOVE** from repo or gate behind env-only |
| TD-038 | Low | Version claims | `pyproject.toml` version `0.5.0` vs README "stable core through v0.2.2" / "v0.3.0 consolidates"; `__init__.py:31` `0.5.0` | `pyproject.toml:3`; `medradar/__init__.py:31`; `_FACTS.md` C1 | users cannot tell what they have | **FIX** single version source |
| TD-039 | Low | Packaging | `pyproject.toml` has 3 divergent blobs across branches; `README.md` has 5 | `git ls-tree` across 10 branches (§Part G) | branch merges will collide on metadata | **REBASE** metadata to one canonical file |
| TD-040 | Low | Observability | No structured logging, no run metrics export, no error envelope; failures are `print()` to stderr | `__main__.py:964-968`; collectors' `except Exception` → string (`:75-76`) | an operator cannot answer "why did Sunday's run produce this" | **ADD** run log + stage timing to `runs.stats` |

---

## Part C — Module incompatibilities (not mere duplication)

| # | Incompatibility | Evidence | Consequence |
|---|---|---|---|
| C1 | **`__main__.py` is a 4-way fork point.** Blobs: `main`/ATLAS/CONVERGENCE identical `5beb830`, #12 `f629768`, #14 `b83f2cc`. #13/#14 already disagree with #12 on the same file | `git ls-tree` per branch | merging #12 and #14 in either order produces a conflict on the single integration file; no stable CLI contract |
| C2 | **Two modules named `config`** with different semantics: `medradar/config.py` (paths + registries) and `medradar/atlas/config.py` (ATLAS dirs + `load_sources`) | `config.py:1-20`; `#28 atlas/config.py:16-75` | import readers must know which "config" they mean; duplicate environment variables |
| C3 | **Three DB-open conventions**: `DB(path)` (writable, WAL), `TKGStore(path)` (foreign-keys on), `AtlasStore(path)` (migrations on open), `#14 ObservationLedger(path, create/read_only)` | each cited module | no shared connection policy; lock/retry behaviour differs per store |
| C4 | **`events` vs `observations` vs `evidence` row models cannot be joined** without recomputing hashes (TD-033) | §A1 | cross-store lineage is manual |
| C5 | **Dependency surface diverges**: `main` = no deps; #12 adds `web` (fastapi/uvicorn, under `#19/#22` `local-llm` adds torch/transformers family) | `pyproject.toml:13-18` vs branch blobs `e503ccc`, `7d46e02` | "install the product" is a different operation per branch; the GPU extra is ~3 GB and only for experiments |
| C6 | **ATLAS declares intentional non-integration**: "no knowledge of, and no write path into, the legacy MedRadar databases under `data/`" | `#28 atlas/store.py:20-23` | ATLAS cannot be adopted incrementally; it is a replacement decision |
| C7 | **`#21` base branch has no PR**; `integration/phase4-base` is 39 commits ahead of `main` and itself on the unmerged stack | `_FACTS.md` §4/§5 | review target invisible; merge order unspecified |

---

## Part D — Legacy / exploratory surface shipped in the repo

| Item | Size | Status | Note |
|---|---|---|---|
| `experiments/` | 657 files, 15.05 MiB | shipped on `main` | incl. `b027` (391 files), `detect_v1*`, `cycle2_coverage`, `reverse_rd_v1/v2`; **not imported by `medradar/`** |
| `papers/` | 32 files, 0.51 MiB | shipped | manuscripts |
| `research/` (main) | 116 files, 1.33 MiB | shipped | mixed: state files + study outputs |
| `verifier/` | 22 files (13 run transcripts, 6 `.meta`, README, `v1/criteria.md`, `v1/verify.py`) | shipped | historical test transcripts committed as text |
| `tools/*.log`, `tools/round_end.json` | 5 files | shipped | agent-run logs |
| `live` lane | `live.py` 1,183 L + 7 tables | shipped, `--help` visible | simulated trading; schedule commented out in CI |
| `nmpa` demo seed | `config/nmpa_demo_seed.csv` | shipped | real source WAF-blocked; the demo seed is honestly labelled in `config/sources.json` but that file is decorative (TD-009) |
| `scripts/nightly.ps1` | PowerShell | shipped | Windows-only automation, exercised by `windows-install` CI job with all stages skipped |
| Branch-only experiments (`#19/#20` local-LLM, `#22/#21` recruitment, `#23–#26` PHOENIX) | up to 303 k added lines each | **branch only** | PHOENIX adds **no product code** (`experiments/phoenix*` + docs only) — correct separation, but 4 PRs × ~160 k lines |

**[RECOMMENDATION]** The refoundation should define an explicit "shipped vs research" boundary. Today `main` ships 15 MiB of experiments in the same tree as a 1.77 MiB product package, and `pyproject` packages only `medradar*` — i.e. the repo *already* treats everything else as non-product, but the tree does not say so.

---

## Part E — Dependency and build reproducibility

| Aspect | `main` state | Risk |
|---|---|---|
| Runtime deps | **none** (`pyproject.toml:13`) | excellent; no dependency attack surface for the shipped CLI |
| Optional extras | `excel`, `pdf`, `dev`, `bulk` — all loose lower bounds (`>=`) | **[FACT]** `openpyxl>=3.1`, `pypdf>=4.0`, `pytest>=8.0`, `ijson>=3.3` unpinned |
| Lockfile | **none** (no `requirements*.txt`, `uv.lock`, `poetry.lock`, `tox.ini`, `Makefile`, `Dockerfile`) | **[FACT]** `git ls-tree` over `main` finds only `pyproject.toml` + `MANIFEST.in` |
| CI install | `pip install --upgrade pip; pip install .` | resolves latest setuptools/Python deps each run → non-reproducible |
| Build backend | `setuptools>=68` | unpinned build requirement |
| Data-files install | `share/medradar/config` + `share/medradar/docs` | config is installed **outside** the wheel; version drift between wheel and config is possible (CI does assert `CONFIG_ORIGIN == 'installed'`) |
| Python matrix | 3.10 / 3.11 / 3.12 in CI | good; `requires-python >=3.10` matches |
| Branch extras | #12 `web`; #19/#22/#20 `local-llm` (`torch>=2.7,<3`, `transformers>=4.51,<6`, …) | **[FACT]** the GPU lane is explicitly out-of-band; `#22` pyproject adds 23 lines incl. a CUDA-12.8 note |
| Reproducibility of results | `experiments/b027` etc. depend on runtime SQLite that is gitignored | **cannot re-run** from a clean clone |

**[RECOMMENDATION]** Pin with a lockfile, install `--require-hashes` in CI, and either vendor a tiny fixture DB or publish artefact hashes for each study.

---

## Part F — CI gaps (detail)

| Gap | Evidence | Effect |
|---|---|---|
| No lint | no `ruff`/`flake8` config or step in any workflow | style/dead-code drift unchecked |
| No type check | no `mypy`/`pyright` config or step; code base uses heavy `Any` | type errors surface only at runtime |
| No coverage | no coverage tool, no threshold | the 1,074 tests do not prove coverage of `report.py`/`replay.py` |
| No security scan | no `pip-audit`/`bandit`/CodeQL/secret scan | TD-037-style tools are unmonitored |
| Runner mismatch | CI `selftest` (unittest) vs local `pytest` | plugin/collection differences |
| Workflow truthfulness | `forecast-cycle.yml` header: "was **not executed**"; `live.yml` schedule commented out | two of four workflows are aspirational |
| Deploy without gate | `weekly.yml` builds **and deploys** Pages in one run; no test/validation step | a broken renderer is published |
| Branch CI divergence | `#28` adds `atlas.yml`, `#30` adds `atlas.yml`+`convergence.yml`, `#14` modifies `ci.yml` and adds `observatory.yml` | **[FACT]** `main` has 4 workflows; `#14` 5; `#30` 6 — no single CI contract |
| `_FACTS.md` correction | §7 claims `observatory.yml` is a `main` workflow; `main` has only `ci, forecast-cycle, live, weekly` | document/file contradiction; bytes win |

---

## Part G — Git data volume

**[FACT]** Measured with `git rev-list --objects --all` + `git cat-file --batch-check` (all refs, unique blobs):

| Top-level | Unique blob bytes | Blobs |
|---|---|---|
| `research/` | **232.76 MiB** | 2,515 |
| `experiments/` | **188.21 MiB** | 1,557 |
| `docs/` | 33.13 MiB | 365 |
| `medradar/` | 10.19 MiB | 388 |
| `tests/` | 3.70 MiB | 242 |
| `config/` | 2.89 MiB | 22 |
| `web/` (branch) | 0.81 MiB | 49 |
| **all refs total** | **476.46 MiB** | — |
| **`main` tracked tree** | **29.06 MiB** | 1,135 files |

Other measurements: pack size **88.57 MiB** across 3 packs, 8,192 in-pack objects; **184** commits on `main`, **369** across all refs.

**Generated-artefact churn [FACT]** (revision count of the same path on `main`):

| Path | Revisions | Current size | Approx bytes in history |
|---|---|---|---|
| `docs/dashboard.html` | 4 | 3,350,819 B | ~13 MB |
| `docs/report_zh.md` | 12 | 55,768 B | ~0.7 MB |
| `docs/preview.png` | 12 | 488,736 B | ~5.9 MB |
| `docs/metrics.json` | 11 | 468,561 B | ~5.2 MB |
| `docs/summary.csv` | 11 | 68,460 B | ~0.75 MB |

**[INFERENCE]** ~25 MB of the 88.57 MiB pack (≈28 %) is regenerable renderer output. Combined with 421 MiB of unreviewed branch data, the repository's growth is dominated by **artefacts, not code** (`medradar/` is 10.19 MiB across *all* refs).

**[RECOMMENDATION]** Stop committing `docs/dashboard.html`/`metrics.json` (publish via Pages artifact); move study artefacts to releases/LFS; prune abandoned experiment snapshots before the refoundation freeze.

---

## Part H — Secret / credential scan (paths and kinds only; **no values printed**)

**[FACT]** Method: `git grep -I -i -E` over `origin/main` for `BEGIN … PRIVATE KEY`, `api[_-]?key\s*[=:]`, `secret\s*[=:]`, `password\s*[=:]`, `token\s*[=:]`, `sk-…`, `ghp_…`, `AKIA…`, `xox[baprs]-`; plus a tracked-filename scan for `.env|.pem|.key|credential|secret|.p12|.pfx|id_rsa`.

| Result | Detail |
|---|---|
| Private keys committed | **none found** |
| `ghp_`/`AKIA`/`sk-`-style literal tokens | **none found** |
| `.env`/`.pem`/`.p12`/`id_rsa` files tracked | **none** |
| `api_key` / `token` / `secret` words | appear as **environment-variable names / CLI options**, e.g. `medradar/llm.py`, `medradar/intelligence/sources/patents.py`, `README*.md`, `docs/RESEARCH.md`; no literal values |
| `password` matches | only `tools/github_api.py:24-32`, which reads the value from `git credential fill` at runtime and never stores it — **kind: credential-plumbing tool, no embedded secret** |
| CI secrets referenced | `SEC_USER_AGENT` (`forecast-cycle.yml`), `MEDRADAR_SEC_UA` (`live.yml`) — referenced via `${{ secrets.* }}` / env, not inline |
| Tools committed that *handle* credentials | `tools/github_api.py` (git credential helper extraction) |

**[INFERENCE]** No secret leakage found in the shipped tree. Residual risk is **process**, not content: a repo-owned tool that pulls the developer's GitHub token into process memory invites accidental commit of its output (it currently prints only login/status — verified at `tools/github_api.py:9-12`). See TD-037.

**[RECOMMENDATION]** Add a pre-commit + CI secret scan (gitleaks/trufflehog) as part of TD-012; remove `tools/github_api.py` from the package repo.

---

## Part I — Automation opportunities (ranked by payoff/effort)

| # | Opportunity | Why it pays | Effort |
|---|---|---|---|
| A1 | **Derive `table_count`/status from `sqlite_master`** instead of a whitelist | kills TD-022 class permanently | S |
| A2 | **Fix `build_metrics` double-run** into build→enrich | halves weekly CPU (TD-020) | S |
| A3 | **One as-of test vector** (known_at/valid_at fixtures) applied to every query engine | proves TD-002/TD-030 equivalence or exposes divergence | M |
| A4 | **Schema-drift guard**: snapshot `PRAGMA table_info` for every store, diff in CI | makes silent `CREATE TABLE IF NOT EXISTS` drift impossible | M |
| A5 | **Registry-driven collectors**: one JSON schema + generated adapter skeleton | collapses 8 registries into 1 (TD-009) | M |
| A6 | **Licence gate in CI**: fail if a committed dataset lacks `licence_status` | turns TD-006 into an enforced invariant | M |
| A7 | **Page render golden files**: hash `report_zh.md`/`dashboard.html` for a fixture metrics snapshot | catches renderer contract drift (TD-025) | S |
| A8 | **Reproducible-cycle fixture**: 10 MB synthetic DB + committed expected artefacts | makes TD-014 reviewable | M |
| A9 | **Copy detector in CI**: `git ls-tree` blob-share across PR head vs its base + a warn threshold | prevents TD-005 recurring | S |
| A10 | **PR base validator**: assert declared base is an ancestor of head, and that `merge-base main..head` is not carrying another open PR | makes TD-008 impossible to repeat | S |
| A11 | **One time library + property tests** (lexical order == chronological order) | prevents TD-032 regressions | S |
| A12 | **Run log**: persist stage timings/counters to `runs.stats` and expose `medradar status --runs` | replaces `print()` debugging (TD-040) | S |

---

## Part J — What is *not* debt (explicitly excluded)

To prevent over-correction in the refoundation:

| Thing | Why it is fine |
|---|---|
| Identical `medradar/product/*` blobs on 7 branches | **stack inheritance** — `feat/medradar-2.0-mvp` is an ancestor of all of them (`merge-base` verified). Not copy-paste. |
| Identical `medradar/observatory/ledger.py` on 5 branches | inheritance from `#14` (ancestor of s028/s029/s031/innovation/phase4-base). Not copy-paste. |
| Identical `medradar/atlas/**` on #28 and #30 | ATLAS **is** an ancestor of CONVERGENCE. Legitimate. |
| `medradar/tkg/store.py` and `medradar/forecast_registry.py` identical on all 10 branches | inherited from `main` (single blob `e3b4288`). They are **not** cross-branch duplicates — their problem is overlap *with other stores on main* (§A3/A6), not duplication across branches. |
| `stats.py` (1,391 L) vs `stats_cmd.py` (827 L) | different roles: statistics library vs CLI report. **Not** a duplicate. |
| `config/sources.json` being byte-identical on 10 branches | not debt *by identity*; it is debt because it is **unused** (TD-009). |
| Zero runtime dependencies | a strength to preserve. |
| The `unittest`-based `selftest` | works offline in 3 OSes; the debt is the *runner mismatch*, not the runner. |

---

## Part K — Open questions for the owner

1. **Which evidence model is authoritative** for the refoundation — ATLAS's versioned `evidence` (best-specified), the Observatory ledger's observation history (best-instrumented), or the `events` table (the only shipped one)? This single decision cascades into TD-001/002/003/010.
2. **Is HORIZON a source or a sibling?** If `#30` may copy it, it will be copied again. Should `#29` be merged first, rebased onto, or archived as a data estate?
3. **What is the intended fate of the product stack (#12–#14)?** Is `main` allowed a FastAPI/uvicorn dependency and a web surface, and does the #12 product layer become the query engine (TD-030)?
4. **Is the trading lane (`live`, `paper`, `replay`) product or research?** It drives 7 tables, 4,200 lines, a public Pages narrative, and a weekly job — but `research/STATE.json` says the anticipate layer has "zero calibration evidence".
5. **May history be rewritten for artefacts?** Pruning `docs/dashboard.html`/`preview.png`/`metrics.json` revisions is the cheapest 25 MB; it needs a decision because it touches published Pages history.
6. **Who owns `research/STATE.json`?** Its recorded working tree and `main` SHA are already wrong (TD-026); four competing state files exist (TD-027).
7. **What is the minimum CI contract** the refoundation must not regress — is lint+types+coverage+secret-scan acceptable as a merge gate given the repo currently has none?
8. **Which identity schemes are in scope?** ATLAS defines 15 (`di`…`ocid`); the shipped `CompanyRegistry` uses none of them. Choosing the scheme list is a prerequisite for the unified resolver.
