# RADAR-001 — Live Intelligence Engine & Company Technology Graph

Status: **implemented, running against real public sources, acceptance evidence recorded**
(branch `feat/radar-001-live-intelligence-graph`, Draft PR, not merged).

This document is the design contract. It states what the system does, what it refuses to do,
and why each rule exists. The numbers cited here come from the acceptance run recorded in
[`docs/radar/evidence/acceptance_report.md`](evidence/acceptance_report.md).

---

## 1. The product claim

MedRadar's first users are product-line R&D leads at Chinese medical-device companies who need
to follow what international vendors are actually publishing about ICU patient monitoring, and
to understand those publications in relation to each other and over time.

The system therefore has to do three things, and it has to keep doing them without a human
starting it:

1. **Discover** new public information from multiple sources, and record who said it, when they
   said it, and when MedRadar first saw it — as four different facts.
2. **Relate** companies, products, publications, regulatory records and technologies with
   evidence and a stated confidence.
3. **Map** each company's technology tree from that evidence, with a time dimension and a
   citation for every branch.

What it must *not* do is equally explicit:

* an FDA clearance is not evidence that a company implements a specific algorithm;
* a paper's author affiliation is not evidence that the company makes the product;
* "no evidence found" is not "the company does not have this technology";
* a model's answer is not a fact until an independent rule agrees with it;
* a source that refuses automated access is not a source that returned nothing.

---

## 2. Architecture

```
                ┌──────────────────────────────────────────────────────────────┐
 real sources   │  adapters/  openfda · pubmed · crossref · philips · draeger   │
 ──────────────▶│  (each: plan → fetch_page → map_record; one module per source)│
                └───────────────┬──────────────────────────────────────────────┘
                                │ RawRecord + MappingResult
                ┌───────────────▼──────────────────────────────────────────────┐
                │ adapter.py — the incremental run engine                      │
                │ cursors · checkpoints · resume · retry accounting · watermarks│
                └───────────────┬──────────────────────────────────────────────┘
                                │
                ┌───────────────▼──────────────────────────────────────────────┐
                │ ledger.py — append-only observation ledger (radar.db)        │
                │ observation · version · change · status · mapping · source    │
                │ state · runs · checkpoints · queue · failures                 │
                └───────────────┬──────────────────────────────────────────────┘
                                │
   engine.advance()  ───────────┤  classify (rules) → resolve → link → publish
                                │
                ┌───────────────▼──────────────────────────────────────────────┐
                │ graph.py over medradar.tkg (graph.db)                        │
                │ bitemporal assertions, evidence on every edge, as-of queries  │
                └───────────────┬──────────────────────────────────────────────┘
                                │
        ai/worker.py  ──────────┤  optional, one-shot, low-priority, candidate-only
                                │
                ┌───────────────▼──────────────────────────────────────────────┐
                │ api.py  (/api/radar/*, read-only)  →  React pages            │
                └──────────────────────────────────────────────────────────────┘
```

Two databases, on purpose:

| File | Role | Mutability |
| --- | --- | --- |
| `radar.db` | observation ledger + cursor/health/work state | history tables are append-only (SQL triggers); heads and queue are mutable projections |
| `graph.db` | company technology graph (`tkg-schema-2`) | append-only assertion store; derived, rebuildable |

The graph is a **projection**. Deleting `graph.db` and re-running `advance` rebuilds it without
touching a single observation. That separation is what makes a rules change safe.

---

## 3. Reuse audit (what came from where)

The brief required auditing the earlier PRs and migrating only what still fits the current
contract. Nothing was merged wholesale.

| Component | Origin | What was reused | What changed |
| --- | --- | --- | --- |
| Observation ledger schema and `record_observation` state machine | PR #13/#14 `medradar/observatory/ledger.py` | the append-only tables, the NEW/UPDATED/UNCHANGED/REMOVED/FETCH_FAILED machine, "UNCHANGED is not a change row", the identity/hash split | re-implemented for the RADAR record shape; `first_observed_at` immutability moved into SQL triggers; a surrogate status-history key replaced the second-precision composite key that collided |
| Record vocabulary and time semantics | PR #13/#14 `medradar/observatory/records.py` | change states, precision vocabulary, discovery phases (`INITIAL_DISCOVERY` / `INCREMENTAL_DISCOVERY` / `HISTORICAL_BACKFILL`), `payload_hash`, `changed_fields` | extended with the intelligence-event fields (org/product/topic candidates, processing state, evidence references) |
| Run engine (scopes, cursors, resume, failure classification) | PR #13/#14 `medradar/observatory/adapter.py` | the scope → page → cursor loop, checkpoint-after-durable-write, retryable/terminal classification | watermarks merge only from scopes that completed; a per-adapter scope gate was added; the engine now also persists adapter-owned state (e.g. an official endpoint version) |
| Single-writer lock | PR #52 DATA-003 `medradar/data_pipeline/lock.py` | the cross-platform `PipelineLock`, imported directly | none |
| Bitemporal assertion store and as-of query | PR #35 evidence-core / `medradar/tkg` | `TKGStore`, `TKGQuery`, idempotency keys, append-only triggers, `snapshot(known_at, valid_at)` | added an optional `read_only` handle so the web process cannot write the graph |
| Source catalogue for FDA endpoints / official URLs | PR #50 DATA-001 `medradar/data_pipeline/{model,openfda}.py` | `SOURCES`, `build_url`, `SourceSpec.official_url` | queried by monitoring product code instead of the whole applicant sweep |
| Source-access verification | PR #29 HORIZON `DATASETS/*/PROVENANCE.json` and robots captures | the *practice* of capturing robots.txt and licence evidence before enabling a source | re-run from this host with this project's user agent; the result is `evidence/source_probe.json` |
| Licence policy | PR #30 CONVERGENCE `config/convergence/licence_policy.json` | the requirement that every source carries a licence and a redistribution statement | expressed per source in `config/radar/sources.json` |

Deliberately **not** migrated: ATLAS's separate identity/graph stack (the in-tree TKG already
provides bitemporal assertions), HORIZON's bulk-download connectors (they solve archive
acquisition, not continuous incremental monitoring), and the old observatory's SEC/ctgov
adapters (out of the ICU monitoring scope).

Negative findings from the earlier research are preserved rather than overwritten — see
[`LIMITATIONS.md`](LIMITATIONS.md).

---

## 4. The intelligence event

Every observation exposes the same fields, whatever the source (RADAR-001 §6):

```
observation_id · source · official_identifier · title · source_url · record_type
event_date (+precision) · source_published_at (+precision) · first_observed_at
last_checked_at · source_updated_at (+precision) · content_hash · version
organization_candidates · product_candidates · technology_topics
evidence_references · processing_state · change_state · discovery_phase
```

The four times are **different facts with different owners**:

| Field | Means | Written by | Never used for |
| --- | --- | --- | --- |
| `event_date` | when the world event happened, as the source states | adapter | freshness |
| `source_published_at` | when the source made the record public, if it states a timestamp | adapter | freshness |
| `source_updated_at` | when the source says the record changed (e.g. a sitemap `lastmod`) | adapter | publication date |
| `first_observed_at` | when MedRadar first saw it — a real clock reading, immutable | ledger | anything the source claims |

`last_checked_at` is the check, not the record. A source that answers "no change" every day has
a fresh `last_checked_at` and an old `last_observed_update_at`. That difference is the product.

### Change states

| State | Meaning |
| --- | --- |
| `NEW` | first time this `(source, source_record_id)` was observed |
| `UPDATED` | the content hash changed; a new payload version was appended |
| `UNCHANGED` | re-observed byte-identical — **not** written as a change row, only as a check |
| `REMOVED_OR_UNAVAILABLE` | the source no longer serves it; the record and its history are kept |
| `FETCH_FAILED` | the re-check failed; this is a state, not evidence of no change |

A `NEW` row whose `discovery_phase` is `INITIAL_DISCOVERY` was already public when the source
was first enabled. The UI labels it. It is not "news".

---

## 5. The technology graph

### Nodes

`company` · `organization` · `product` · `technology_topic` · `regulatory_record` ·
`publication` · `document` · `evidence`

### Relations

`COMPANY_HAS_PRODUCT` · `PRODUCT_HAS_REPORTED_CAPABILITY` ·
`REGULATORY_RECORD_REFERENCES_PRODUCT` · `PUBLICATION_DISCLOSES_TOPIC` ·
`DOCUMENT_MENTIONS_COMPANY` · `OFFICIAL_IDENTIFIER_MATCH` · `CANDIDATE_PRODUCT_RELATION` ·
`RELATED_TECHNOLOGY_TOPIC` · `ORGANIZATION_PART_OF_COMPANY` · `DOCUMENT_REFERENCES_TOPIC`

### Every edge stores

`edge_type`, source locator, **evidence id** (payload-version id), observation id, content hash,
`confirmation`, `method`, `valid_from`, `public_time` (+basis), `recorded_at`, rule/taxonomy
version, confidence, and the matched terms or basis. The store rejects an assertion without a
source locator, so an edge with no evidence cannot exist.

### Confirmation levels — and what each may not conclude

| Level | Produced when | May not be read as |
| --- | --- | --- |
| `CONFIRMED` | a source states it directly: an FDA applicant + device; a vendor naming its own launched product and capability; two sources publishing the same official identifier | proof of internal implementation, strategy or superiority |
| `CANDIDATE` | a rule supports the link but identity/intent is not established (a broad legal name such as "General Electric Co." at 0.6 confidence) | a product or a capability |
| `TOPIC_RELATED` | the record is *about* the topic (keyword hit, or an FDA product code) | that a product *has* that capability |
| `UNKNOWN` | recorded explicitly with a reason | absence |

Two rules are enforced in code and tested:

* a regulatory record never produces `PRODUCT_HAS_REPORTED_CAPABILITY` — only
  `DOCUMENT_REFERENCES_TOPIC` (`TOPIC_RELATED`);
* a publication affiliation never produces `COMPANY_HAS_PRODUCT` or a capability — only
  `DOCUMENT_MENTIONS_COMPANY`.

### The two clocks

The store assigns `recorded_at` internally from the store clock; it cannot be backdated. That
gives two independent questions:

* **Knowledge time** (`mode=knowledge`, `known_at=T`): what MedRadar had actually recorded by
  T. Evidence discovered later is excluded, even if it describes an earlier event.
* **Public time** (`mode=public`, `valid_at=T`): what was publicly true on T, reconstructed from
  today's knowledge. The API returns `reconstructed: true` and the UI shows a persistent banner.

The retrospective view therefore never dresses up today's discovery as past knowledge. And when
MedRadar discovers a 1984 FDA clearance today, that is exactly what the knowledge-time view says.

---

## 6. Company comparison

For each (company, topic) cell the API returns four **separate** counts:
`reported_capability_evidence`, `regulatory_topic_evidence`, `publication_topic_evidence`,
`official_document_topic_evidence` — plus a `state` (`EVIDENCE_PRESENT` / `NO_EVIDENCE_FOUND`)
and the sentence that cell deserves.

The payload carries two mandatory statements:

* `no_evidence_means` — absence of evidence is not evidence of absence;
* `not_comparable_warning` — a publication count is affiliated research activity, a regulatory
  record is a clearance, and MedRadar does not rank companies by these numbers.

A blocked source is reported as `BLOCKED_BY_ACCESS_POLICY`, never as "no results". This matters
concretely: GE HealthCare's newsroom refuses anonymous automated access, so GE's branch has FDA
and publication evidence but no vendor-press evidence — and the product says exactly that.

---

## 7. The intelligence pipeline

`ingest → deduplicate → classify → resolve → link → publish`

| Stage | What it does | What it never does |
| --- | --- | --- |
| ingest | one adapter run per source; failures are contained per source | invent an empty result for a failed source |
| deduplicate | identity `(source, source_record_id)` + content hash | merge two sources into one row — cross-source identity is a *relation*, not a merge |
| classify | rules: product codes, organisation aliases, keyword regexes, each with a method and confidence | use fuzzy matching (a false merge poisons the graph) |
| resolve | organisation strings through the committed alias table | promote a below-threshold alias to confirmed |
| link | write assertions, each with its evidence id and rule version | assert above the level its evidence supports |
| publish | make it visible in the feed and the graph | delete anything (a removal is a state) |

`advance` is idempotent and restartable; running it twice changes nothing. A rule-version change
re-classifies affected observations and invalidates exactly their graph projection.

---

## 8. The AI layer (optional)

Qwen3-0.6B, CPU, one-shot process per batch, low priority, behind a resource guard. See
[`AI.md`](AI.md). The contract:

* output is a **candidate** (`ai_candidate`), never a confirmed fact;
* a topic claim is promoted only if the topic id is in the taxonomy **and** the quoted evidence
  appears verbatim in the source text;
* an organisation claim is promoted only if it resolves through the committed alias table **and**
  the quote is verbatim;
* the backlog survives a missing, slow or wrong model, and discovery never waits for it.

---

## 9. Operations

```
python -m medradar radar init                     # create the store, print the registry
python -m medradar radar run                      # one real incremental check of every due source
python -m medradar radar advance                  # classify → resolve → link → publish
python -m medradar radar status                   # source status, latency, backlog, integrity
python -m medradar radar feed --limit 20          # the latest intelligence events
python -m medradar radar map --company philips    # the technology tree
python -m medradar radar compare                  # the evidence-coverage matrix
python -m medradar radar watch --interval 300     # the scheduler loop
python -m medradar radar verify                   # integrity audit (exit 2 on a problem)
python -m medradar radar ai status|run|eval       # the optional enrichment worker
```

The web workbench mounts the read-only API at `/api/radar/*` when `--radar-dir` (or
`MEDRADAR_RADAR_DIR`) is set, and serves the two new pages at `/radar` and
`/radar/technology-map`.

Recovery is automatic: a run left `RUNNING` by a killed process becomes `INTERRUPTED` on the next
start, its checkpoints are reused, and stale AI claims return to the queue.

---

## 10. What would have to change to add a company, a topic or a source

* **A company**: append to `config/radar/organizations.json` (aliases + confidence). No code, no
  migration.
* **A technology topic**: append to `config/radar/topics.json` (family, verified FDA product
  codes, keyword regexes). The taxonomy fingerprint changes, which re-classifies on the next
  `advance`.
* **A source**: one module implementing `SourceAdapter` (`plan` / `fetch_page` / `map_record`),
  one entry in `adapters/__init__.py`, one entry in `config/radar/sources.json`, and a probe run
  recorded in `evidence/source_probe.json`.
