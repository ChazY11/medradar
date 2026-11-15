# MedRadar Data Contract

**Status:** binding for PRODUCT-001. Every API response, UI label and export must obey it.
**Owner:** product engineering. **Version:** 1.0 (2026-11-15).

This document defines what MedRadar is allowed to assert, where every fact comes from, and
which timestamps mean what. If a screen cannot satisfy this contract, it must show a gap
instead of a number.

---

## 1. Sources of record

| source_id | Name | Endpoint | Official record page |
|---|---|---|---|
| `openfda_510k` | FDA 510(k) premarket notifications | `/device/510k.json` | `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=<k_number>` |
| `openfda_pma` | FDA PMA approvals and supplements | `/device/pma.json` | `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=<pma_number>` |
| `openfda_recall` | FDA device recalls | `/device/recall.json` | `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=<res_event_number>` |
| `openfda_classification` | FDA device product-code classification | `/device/classification.json` | `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm` |

Every fact MedRadar displays is a projection of one of these four record sets. No fact is
invented, imputed or paraphrased into a conclusion. The only derived values are *counting*
and *grouping* operations that are re-expandable to the underlying records.

**Explicitly out of scope for PRODUCT-001** (must be shown as "not covered", never as zero):

* De Novo classification requests - openFDA exposes no De Novo endpoint. Not collected.
* NMPA / China registrations - source is behind a WAF (see `config/sources.json`). Not collected.
* EU MDR / CE marks, UDI, establishment registrations, clinical trials, financial filings,
  patents, hiring. Not collected in this release.
* Any record whose applicant could not be attributed to a tracked organization.

---

## 2. Snapshot, not a live feed

MedRadar v1 ships an **immutable collected snapshot** in `medradar/product/snapshot/`:

```
medradar/product/snapshot/snapshot.json           # manifest: ids, timestamps, counts, content hashes
medradar/product/snapshot/events.jsonl.gz         # one compact JSON object per regulatory record
medradar/product/snapshot/applicants.jsonl.gz     # applicant spellings discovered per search token
medradar/product/snapshot/classifications.jsonl.gz# FDA product-code dictionary
```

Rules:

1. The snapshot is **read-only** at request time. The API never mutates it.
2. Every response that shows data carries `snapshot.id` and `snapshot.collected_at`.
3. `snapshot.json` records the SHA-256 of every data file, the exact openFDA URLs queried,
   per-organization record counts and the collector version. Re-running the collector on the
   same date must produce a manifest that is diffable.
4. A snapshot is **stale** when its `collected_at` is older than the product's freshness
   threshold (30 days). The UI shows `data_freshness.state = "stale"` and the exact age.
   Staleness is never hidden.
5. The system never claims "real-time", "live" or "current" data. The correct phrase is
   "snapshot collected at <timestamp>".

---

## 3. Temporal semantics - four distinct times

These are different facts and must never be collapsed into one "date" column.

| field | meaning | provenance |
|---|---|---|
| `event_date` | When the regulatory **event happened**: FDA decision date for 510(k)/PMA, firm's recall **initiation** date for recalls. | source record |
| `published_at` | When the **source published** the record, if and only if the source states it. For recalls, `event_date_posted`. For 510(k)/PMA, **unknown** - openFDA publishes no record-publication timestamp. | source record or `null` |
| `first_observed_at` | When **MedRadar first ingested** the record (snapshot collection timestamp). Never earlier than the true public availability; it is the only time an observation is *proven* for our system. | our collector |
| `record_updated_at` | Source's own last-update marker when present (`openfda` meta `last_updated` for the dataset, else `null`). | source metadata |

Guarantees:

* `published_at` is **never** back-filled from `event_date`. If the source does not state a
  publication time, the API returns `null` and `published_at_status = "not_published_by_source"`.
* `first_observed_at` is **never** presented as the date an event became public.
* Ordering across snapshots must use `available_at` - the conservative lower bound of when we
  could first know about the record - where `available_at = published_at ?? first_observed_at`.
* UI copy: "event date" vs "first observed" are always labelled separately; the column header
  for `event_date` never says "publication date".

`time_quality` per record:

| value | meaning |
|---|---|
| `date_from_source` | event_date parsed from an explicit source date field |
| `date_derived_from_source` | event_date used a documented fallback (e.g. recall posted date when initiation date missing) |
| `unknown` | no usable date; the record is listed but excluded from time-series charts and counted as `undated` |

---

## 4. Identity model

### 4.1 Levels

| level | example | how it is used |
|---|---|---|
| **Tracked organization** | `medtronic` -> "Medtronic" | the unit a user searches for, views and compares. Holds a curated registry entry. |
| **Applicant name** (verbatim) | `MEDTRONIC VASCULAR`, `Medtronic MiniMed, Inc.` | exactly the string FDA stores in the record. Never normalised for display of provenance. |
| **Attribution** | applicant name -> organization | a *reviewed decision*, not a guess. Carries basis, confidence and evidence. |
| **Ownership relation** | "Covidien LP was acquired by Medtronic in 2015" | optional, explicitly declared, with a status. Never inferred from name similarity. |

### 4.2 Attribution rules

1. Matching is **exact string equality** on the applicant name, against a curated
   `accept_exact` list. No fuzzy, no substring, no normalisation beyond Unicode NFC and
   case-insensitive comparison (both strings are compared after `casefold()` and whitespace
   collapse; the verbatim string is always preserved for evidence).
2. Every acceptance records:
   `{applicant_name, organization_key, basis, confidence, review_status, evidence}` where
   `basis` is one of `legal_name | brand | subsidiary | historical_name | division`.
3. `review_status` is one of `curated | pending_review | rejected`. `pending_review` means an
   agent proposed the mapping and a human has not signed it off. **The UI must render it as
   provisional** ("attribution pending human review").
4. A `reject_exact` list exists for strings that look similar but are a different business
   (e.g. "Drager Safety"). Rejected strings are shown in the attribution audit, not counted.
5. Records whose applicant is not in any `accept_exact` list are **unattributed**. They are
   never silently dropped: they are counted in `coverage.unattributed_records` and listed in
   the attribution audit with their applicant string.
6. Similar names are **never** merged automatically. Two organizations that could plausibly
   share a name produce two search results with an explicit "distinct legal entities" warning.

### 4.3 Ownership and parent/subgroup

`ownership` entries are `{child_key, parent_key, relation, status, note, evidence}`.
`status` is one of `declared | pending_review | unknown`. Only `declared` relations are used in
aggregation, and the UI always shows which relations were used. When the relation is unknown
the UI shows "unknown / to be verified", never a guess.

### 4.4 Search

Search matches, in this order, and returns which field matched:

1. exact legal name (case-insensitive),
2. exact brand / display name,
3. exact ticker,
4. curated alias prefix,
5. substring of display name or alias,
6. substring of any *tracked-organization* applicant name.

Results are **organizations**, not applicant strings. A query that only matches unattributed
applicant strings returns those strings in `applicant_matches` with a clear
"not attributed to a tracked organization" label, never as a company result.
No result is a first-class state: it reports the tracked-coverage size and how to request
coverage.

---

## 5. Record identity

`event_id = "<source_id>:<official_id>"`:

* `openfda_510k:K231234`
* `openfda_pma:P970003` (original) / `openfda_pma:P970003:S001` (supplement)
* `openfda_recall:Z-1234-2024` (FDA `res_event_number`)

The official identifier is printed everywhere alongside the event. It is the join key back to
the FDA public record and is stable across snapshots.

Event type vocabulary (never merged):

| event_type | display | notes |
|---|---|---|
| `510k` | 510(k) premarket notification | original clearances |
| `pma` | PMA original approval | original approvals |
| `pma_supplement` | PMA supplement | changes to an approved device; **not** a new device |
| `recall` | recall | safety action, not a product-technology signal |

Aggregations must state which event types they sum. A count that mixes them is forbidden.
PMA supplements are never counted as new technologies.

---

## 6. Categories

Category = the FDA **medical specialty / advisory committee** (`advisory_committee_description`)
joined through the product code. Secondary labels: `product_code`, `device_name` (from the
classification dictionary), `device_class` (1/2/3).

Rules:

* Category comes only from the FDA classification dictionary; MedRadar invents no taxonomy.
* A record whose product code is not in the dictionary is `category: null` and counted as
  `unmapped_category`. The UI shows the untitled bucket; it is never silently dropped.
* Device class is shown where present. Class 3 does not mean "more innovative".

---

## 7. Counts, comparison and honest inference

1. A count is a count of **records**, labelled "records", never "products", "devices",
   "innovations" or "breakthroughs".
2. Every aggregate returns `basis`: `{event_types, window, org_keys, snapshot_id}` so it can be
   reproduced.
3. Comparison always reports, per organization and per source: attributed record count, date
   coverage (min/max `event_date`), unmapped-category count, pending-review attribution count,
   and the applicant country mix. If coverage differs, the payload contains `warnings[]` that
   the UI must display above the comparison.
4. The product never converts record counts into an innovation ranking. An explicit disclaimer
   is part of every comparison payload and export.
5. Rates are per-year over the **complete calendar years** inside the window. Partial years at
   the window edges are excluded from rates and flagged.

---

## 8. Export contract

Exports reproduce exactly the filtered set and the same basis as the screen.

* CSV: one row per record, UTF-8 with BOM, includes `event_id`, `official_id`, `source_id`,
  `source_name`, `official_url`, `event_date`, `published_at`, `published_at_status`,
  `first_observed_at`, `event_type`, `organization_key`, `organization_name`, `applicant_name`,
  `attribution_basis`, `attribution_review`, `product_code`, `category`, `device_class`,
  `device_name`, `snapshot_id`, `collected_at`.
* Markdown report: comparison tables + warnings + the same caveats + a source list with links.
* Every export starts with a provenance header block naming the snapshot and collection time,
  and every row links its official record.

---

## 9. Data quality states exposed to the user

| state | meaning | UI behaviour |
|---|---|---|
| `ok` | attributed, dated, categorised | normal |
| `unattributed` | applicant not attributed | counted in audit, never shown as the org's activity |
| `undated` | no usable event date | listed, excluded from charts, labelled |
| `unmapped_category` | product code unknown | shown as "unclassified", never dropped |
| `pending_review` | attribution proposed, not signed off | labelled "attribution pending review" |
| `stale` (snapshot) | older than freshness threshold | banner with age |
| `partial_coverage` | org's sources have different start dates | shown in coverage panel |

**A number is only shown when its basis and coverage are shown with it.**

## PRODUCT-002 additions

### Attribution verification status

Every accepted applicant spelling carries one of `proposed`, `rule_verified`,
`evidence_verified`, `human_reviewed` (accepted) or `rejected`, `unresolved` (negative). Derivation
(inputs are explicit fields, never a judgement):

1. registry review flag `pending_review` -> `proposed` (provenance machine_proposal);
2. registry review flag `curated` with basis legal_name/brand -> `rule_verified` **iff** the
   deterministic name-identity rule holds, else `proposed`;
3. registry review flag `curated` with basis subsidiary/division/historical_name -> `proposed`
   (a corporate relation needs evidence);
4. lexical equivalence to a stronger sibling -> `rule_verified` (`lexical_equivalence_v1`);
5. a verified ownership relation covering the spelling -> `evidence_verified`;
6. a review-ledger decision -> its recorded status (highest precedence).

`curated` in product metrics means `evidence_verified` or `human_reviewed` **only**.

### Metric definitions (authoritative, also served at `/api/metrics`)

| Metric | Numerator / denominator | UNKNOWN when |
|---|---|---|
| Attributed Share | attributed records / collected records (also: attributed strings / observed strings; organizations with records / tracked) | never for a loaded snapshot |
| Rule-verified Share | attributed records with `rule_verified` / attributed records | no attributed records |
| Curated Share | attributed records with `evidence_verified` or `human_reviewed` / attributed records | no attributed records |
| Estimated Attribution Precision | supported cases / decidable cases in the pre-registered sample, Wilson 95% | no completed sample review |
| Retrieval Coverage | retrieved relevant records / independently known relevant population | no independent denominator (always UNKNOWN in this release) |

### Ownership data

`medradar/product/attribution/ownership.json` (`medradar.ownership.v1`): relations with
`applicant_token_patterns`, `effective_from`/`effective_to`, `historical_owner_before`, `status`
(`evidence_verified`/`unresolved`), `reviewer`, `reviewer_kind` and `evidence` records. An
`evidence_verified` relation requires at least one evidence entry with a URL. Unresolved relations
must carry no evidence.

### Owner at event time (PRODUCT-003 P0-B)

Each attributed record carries `historical_owner`: `{state: verified|unknown, reason,
organization_key, display, relation_id, effective_from}`. It is derived from a verified ownership
relation with an effective date compared against the record's event date:
`verified_current_group`, `verified_predecessor`, or `unknown` (`no_relation`,
`no_effective_date`, `no_event_date`). `basis=historical_owner_verified` keeps only
`verified_current_group` records and reports the excluded counts. The retired
`original_registrant` basis is refused.

### Identity review ledger

Append-only SQLite (`data/identity/review.db`, gitignored) with three tables: `review_decisions`
(one row per decision, `supersedes_uid` links corrections), `review_revocations` (withdrawn
decision uids) and `review_audit` (every append). SQLite triggers reject `UPDATE`/`DELETE` on the
decision and revocation tables. `effective()` folds the ledger: the latest non-withdrawn decision
per applicant key wins. The committed `docs/product/product_002/identity_review_decisions.json` is an
audit snapshot, not the live store.

### Validation artifacts

`docs/product/product_002/validation/` contains `sample.json` (pre-registered design + cases),
`sec_entity_lists.json` (derived entity names from public filings, with source URLs),
`review_records.json` (per-case verdict + evidence) and `precision.json` (estimate + interval +
caveats). Generated by `tools/validation/validate_attribution.py`.
