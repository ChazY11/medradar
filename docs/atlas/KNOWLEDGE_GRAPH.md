# KNOWLEDGE_GRAPH — relations, queries and evidence paths

**Implementation:** `medradar/atlas/graph/` over the ATLAS SQLite store.
**No graph database.** Relations are rows; traversal is SQL. This is sufficient for the
current scale (≈5.5k devices, ≈16k identifiers, ≈2.2k relations) and keeps the system runnable
on a laptop.

---

## 1. Node types

| Node | Table | Notes |
|---|---|---|
| Company | `companies` | five target firms + any resolved company |
| Manufacturer | `manufacturers` | legal manufacturer / brand owner / registration holder |
| Device | `devices` | one regulatory product record |
| Product family | `devices.product_family` + `device_product_codes` | not a separate node yet; grouping is explicit |
| Identifier | `device_identifiers` | scheme-scoped; a DI is not a licence number |
| Regulatory record | `evidence` (`regulatory_clearance`, `device_registration`) | source record, not a summarised label |
| Publication / trial / patent / procurement | reserved in the evidence vocabulary | **not collected in ATLAS-001** |

A missing node type is represented as missing. It is never filled with a similar-looking record.

---

## 2. Relation types

### Source-declared (built from the record's own fields)
| Relation | From → To | Evidence |
|---|---|---|
| `MANUFACTURED_BY` | device → company | the record's company/manufacturer field |
| `REGISTERED_AS` | device → regulatory identifier | an official number the record carries |
| `BELONGS_TO_FAMILY` | device → licence/family | MDALL's own licence grouping (reserved; licence rows carry the family name) |

### Inferred identity (built by the resolver)
`SAME_DEVICE_IDENTITY`, `SAME_MODEL`, `SAME_PRODUCT_FAMILY`, `RELATED_TECHNOLOGY`,
`POSSIBLE_MATCH`, `UNRELATED`, `UNKNOWN` — each with `status`, `method`, `authority`,
`confidence`, `basis_json`, `contradictions_json`, `rejection_reason`.

### Explicitly **not** created in ATLAS-001
- `STUDIED_IN` (device → publication/trial): no publication/trial collection for devices.
- `FUNDED_BY`, `SUPPLIED_TO`, `ACQUIRED_BY`: no procurement/award/ownership data in this round.
- `RELATED_TO_TECHNOLOGY` from a shared name: only a shared **FDA product code** creates
  `RELATED_TECHNOLOGY`, and only as a candidate.

This is the difference between a graph and a rumour: the missing edges are missing.

---

## 3. Authority levels

Every relation carries one of:

| Authority | Meaning | Example |
|---|---|---|
| `source_declared` | the sources themselves assert the identifier relation | same DI in GUDID and MDALL |
| `derived` | deterministic field agreement | same firm + same model string |
| `inferred` | similarity only | shared brand token |

A query can filter on authority; the CLI prints it. No inferred relation is counted as
confirmed.

---

## 4. Queries (implemented, JSON)

| Query | Command | Returns |
|---|---|---|
| Company → devices | `query company --key medtronic` | devices with official identifiers + evidence record |
| Device → identity | `query device --key <device_ref>` | identifiers, relations, evidence |
| Company → device → identifier → regulatory record | `query path --key medtronic` | complete chains, `chain_complete` flag |
| Technology → companies | `query tech --key NIQ` | companies with devices in that FDA product code |
| Relation → evidence + history | `query relation --key <relation_id>` | both evidence records, basis, event history |
| Why a relation was rejected | `query rejections` | rejection reason + basis |
| Device → research candidates | `query research --key <device_ref>` | explicit empty `NOT_COLLECTED` response |

### Example: what "complete" means

```
company        Medtronic plc
  └─ device    UDI record (DI 00643169718425), brand/model from GUDID
       ├─ official identity: di:00643169718425
       ├─ REGISTERED_AS: 510k:<K-number>  (source-declared identifier, when present)
       └─ regulatory record: evidence row with source_url + hashes + clocks
```

`chain_complete` is true only when both a device evidence record and a regulatory record exist.
Otherwise it is false and the gap is reported, not filled.

---

## 5. Revocation

Relations are never deleted. Revocation:

1. sets `revoked_at` and `revoked_reason` on the relation;
2. appends a `relation_events` row with `action='revoked'`;
3. removes the relation from default query results;
4. keeps it visible with `include_revoked=True` and in `query relation`.

The test `test_revoked_relation_keeps_history` pins this behaviour.

---

## 6. Scale and traversal

Current pilot: 5,543 devices, 16,377 identifier rows, 2,217 relations. Queries are indexed on
`device_identifiers(scheme,value)`, `entity_relations(from_ref)`, `(to_ref)`, `(relation_type)`.
Bounded multi-hop traversal is done in application code (`evidence_path`), not recursive SQL,
so a missing edge produces a reported gap instead of a silently empty join.

For future scale, the migration path is: keep SQLite for identity/evidence, add a read-only
export to a graph engine only if traversal depth genuinely exceeds 3–4 hops. No such need was
demonstrated in this round.
