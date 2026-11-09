# ATLAS Architecture

**Status:** implemented and running (ATLAS-001)
**Entry point:** `python -m medradar.atlas`
**Storage:** one SQLite file, no server, no ORM, runnable on a laptop.

---

## 1. Design constraints that shaped everything

1. **Traceability beats coverage.** A record that cannot be tied to raw bytes, a source
   record id and four clocks is not allowed into the store.
2. **No silent promotion.** A name similarity can create a *candidate*, never a confirmed
   relation. The schema rejects a candidate that carries confirmed-level confidence.
3. **Append-only.** Evidence versions and relation revocations are history, not edits.
4. **One write path.** Connectors return records; the store writes them. A connector cannot
   invent a second persistence mechanism.
5. **No new infrastructure for its own sake.** SQLite + Python standard library. No Neo4j, no
   message bus, no cloud dependency, no model training. The whole pilot runs offline after a
   bounded collection.
6. **Failures are data.** A failed request becomes a `quality_findings` row, never "0 events".

---

## 2. Module map

```
medradar/atlas/
├── config.py            paths, firm registry, source register
├── cli.py               every operation, JSON out
├── store.py             AtlasStore: evidence, entities, relations, findings
├── db/
│   └── migrations.py    versioned DDL, checksums, mandatory backup, rollback
├── evidence/
│   ├── schema.py        medradar.atlas.evidence.v1 (construct + validate)
│   ├── timeq.py         four clocks, quality, ordering checks
│   └── http.py          bounded, logged HTTP; streaming for whole-table endpoints
├── identity/
│   ├── normalize.py     scheme-scoped identifier + name folding
│   ├── companies.py     curated alias registry resolver
│   ├── models.py        Company / Manufacturer / Device / Identifier
│   ├── resolver.py      SAME_DEVICE_IDENTITY … UNKNOWN classification
│   └── pilot.py         the bounded, reproducible ATLAS-ID pilot
├── connectors/
│   ├── base.py          one six-operation contract + evidence construction
│   ├── openfda_udi.py   company-searchable GUDID projection + batch id resolver
│   ├── accessgudid.py   official DI lookup (same upstream as openFDA UDI)
│   ├── canada_mdall.py  streaming identifier table + id-keyed licence/company detail
│   └── openfda_510k.py  regulatory grouping (never device identity)
├── graph/
│   ├── build.py         source-declared relations only
│   └── query.py         seven evidence-bearing queries
├── quality/
│   └── checks.py        nine automated checks, aggregated findings
└── research/
    ├── asof.py          observed / public_inferred / unprovable
    └── prospective.py   timestamped candidate registry
```

Deliberate absences: no web frontend, no LLM dependency, no scheduler, no graph database.

---

## 3. Data flow

```
official source
     │  bounded HTTP (budget, retry, Retry-After, ledger)
     ▼
connector.fetch ──► normalize ──► identify ──► evidence record
     │                                   │
     │                                   ├─ raw_content_hash   (this record's bytes)
     │                                   ├─ normalized_content_hash (what we use)
     │                                   ├─ four clocks (event/public/first-observed/fetched)
     │                                   └─ identifiers + company tiers
     ▼
AtlasStore.append_evidence
     ├─ evidence(evidence_id, version, ...)        append-only
     ├─ evidence_head(evidence_id, latest_version) pointer only
     ├─ evidence_identifiers / evidence_entity_refs
     ├─ raw_objects (hash + provenance; body not committed)
     └─ request_log / collection_runs
     ▼
identity resolver (record pairs)
     ├─ CONFIRMED  → entity_relations(status=CONFIRMED)
     ├─ CANDIDATE  → entity_relations(status=CANDIDATE)
     ├─ REJECTED   → entity_relations(status=REJECTED, reason kept)
     └─ UNKNOWN    → no relation, counted as unknown
     ▼
graph queries / as-of / prospective registry / quality report / verifier
```

---

## 4. Storage model

| Table group | Tables | Invariant |
|---|---|---|
| Bookkeeping | `schema_migrations` | checksum verified on every open |
| Collection | `collection_runs`, `request_log`, `raw_objects` | one row per run/request; counts are derived from rows |
| Evidence | `evidence`, `evidence_head`, `evidence_identifiers`, `evidence_entity_refs` | `(evidence_id, version)` immutable; head is a pointer |
| Entities | `companies`, `company_names`, `manufacturers`, `devices`, `device_identifiers`, `device_product_codes` | identifiers are scheme-scoped and never interchangeable |
| Relations | `entity_relations`, `relation_events` | never deleted; revocation appends an event |
| Quality | `quality_findings`, `source_status` | failures persisted, not swallowed |
| Time | `observations` | field-level observations for as-of queries |
| Prospective | `prospective_candidates`, `prospective_events` | registration timestamp fixed at creation |

`PRAGMA journal_mode=WAL`, `foreign_keys=ON`. A migration that changes an existing database
copies it to `backups/` first and reports the path.

---

## 5. Identity decision pipeline

```
record pair
   │
   ├─ same DI? ──────────────► SAME_DEVICE_IDENTITY (source_declared)
   │     └─ descriptive fields conflict? → CANDIDATE + contradiction flag
   ├─ same 510(k)/PMA/licence? ► SAME_PRODUCT_FAMILY (grouping, not one device)
   ├─ same firm + same model? ─► SAME_MODEL (confirmed, explicitly not identity)
   ├─ same firm + same product code? ► SAME_PRODUCT_FAMILY
   ├─ same firm + disjoint product codes? ► UNRELATED (rejected, reason kept)
   ├─ identical brand, different firms? ► UNRELATED (hard negative)
   ├─ shared product code, different firms? ► RELATED_TECHNOLOGY (candidate)
   ├─ shared distinctive brand token? ► POSSIBLE_MATCH (candidate)
   ├─ high label similarity? ► POSSIBLE_MATCH (candidate)
   ├─ no anchors at all? ► UNKNOWN
   └─ otherwise ► UNRELATED (rejected, reason kept)
```

The resolver is pure and deterministic; tests pin each branch.

---

## 6. Time model

Four clocks, never collapsed:

| Clock | Meaning | Failure mode prevented |
|---|---|---|
| `event_at` | when the underlying event happened | treating a decision date as publication |
| `source_public_at` | when the record first became public at the source | using a refresh/version stamp as publication |
| `first_observed_at` | when MedRadar first saw it | backfilled history masquerading as live knowledge |
| `fetched_at` | when this copy was retrieved | re-fetch date masquerading as publication |

`source_public_at_quality` is one of `exact / day / coarse / derived / unknown`. Derived and
coarse dates are excluded from lead-time claims by construction.

`as_of(T, basis)` answers two questions separately:
- `observed`: `first_observed_at <= T`;
- `public_inferred`: `source_public_at <= T` with exact/day quality;
- everything else is reported as `unprovable`.

---

## 7. Connector contract

Every connector implements the same six operations:

| Operation | Requirement |
|---|---|
| `fetch` | through `HttpClient`; budget, min interval, bounded retries, ledger |
| `normalize` | explicit field projection; unknown stays empty, never guessed |
| `validate` | `evidence.validate_evidence` must pass before storage |
| `identify` | official identifiers + company tier; candidates labelled |
| `version` | content hash + deterministic evidence id |
| `store` | returns records; the runner writes them |

Streaming (`HttpClient.stream_to_file`) exists only for endpoints that return whole tables
(MDALL) and enforces a byte cap and a ledger entry.

---

## 8. Reproducibility and verification

- The pilot writes one machine report (`research/atlas/reports/identity_pilot.json`) whose
  numbers come from SQL aggregates in the same process.
- `tools/verify_atlas.py` opens the database **read-only** and recomputes hashes, counts,
  relation invariants and baseline arithmetic with an independent implementation.
- The committed sample is bounded and redistributable; staging, cache and the database are
  git-ignored.

---

## 9. What the architecture deliberately does not claim

- It does not claim complete coverage of any registry.
- It does not claim that a candidate is a match.
- It does not claim that a shared product code means a shared technology programme.
- It does not claim point-in-time replay of source revisions that were never observed.
- It does not claim that two interfaces over the same upstream registry are independent
  evidence (AccessGUDID and openFDA UDI are one authority).
