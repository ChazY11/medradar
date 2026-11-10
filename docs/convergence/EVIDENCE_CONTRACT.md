# EVIDENCE CONTRACT — `medradar.convergence.evidence.v1`

The contract that binds HORIZON's `horizon.evidence.v1` records into ATLAS's
`medradar.atlas.evidence.v1` substrate. It is implemented in
`medradar/integration/contract.py` (semantics, no I/O), `clock.py` (time),
`licence.py` (rights) and `adapter.py` (conversion), and it is enforced by the
tests in `tests/convergence/` and by `.github/workflows/convergence.yml`.

The contract exists because the two schemas look compatible and are not. Three
differences would silently corrupt the science if handled by renaming fields.

## 1. "Confirmed" means three different things

| schema | field | what it actually asserts |
|---|---|---|
| HORIZON | `evidence_status=CONFIRMED` | the official source really publishes this record |
| HORIZON | `identity_status=CONFIRMED` | this record's own identifier resolved at its own source |
| ATLAS | `identity_resolution_status=confirmed` | this record describes the **same real-world entity** as another record, via an authoritative identifier |

In the export, 941 records carry `evidence_status=CONFIRMED` and 889 carry
`identity_status=CONFIRMED`. Mapping either onto ATLAS identity would manufacture
889–941 false identity confirmations.

**Contract rule.** Record-level source status is preserved verbatim in
`normalized.convergence.source_record_status` and is never used to set
`identity_resolution_status`. Every imported record enters ATLAS as
`identity_resolution_status = "not_attempted"`. Identity is established later, by
the graph layer, from an authoritative identifier match — or not at all.

Verified: 5,884 imported evidence versions, all `not_attempted`.

## 2. The identity grade ladder

Six grades, ordered weakest to strongest. Only one may ever produce a confirmed
identity.

| grade | ATLAS identity | relation status | may confirm identity |
|---|---|---|---|
| `REJECTED_RELATION` | — | `none` | no |
| `CONTRADICTED_RELATION` | — | `contradicted` | no |
| `UNVERIFIED_RELATION` | `none` | `unknown` | no |
| `CANDIDATE_RELATION` | `candidate` | `candidate` | no |
| `SOURCE_ASSERTED_RELATION` | `candidate` | `asserted_by_source` | no |
| **`AUTHORITATIVE_ID_MATCH`** | `confirmed` | `asserted_by_source` | **yes, and only with an official identifier** |

`AUTHORITATIVE_ID_MATCH` additionally *requires* an official identifier in the
same namespace (see §3). A relation can never reach it on names, model tokens,
firm agreement or classification overlap.

HORIZON's own relation vocabulary maps as follows — note the deliberate demotion
of the one HORIZON already calls a candidate:

| HORIZON `relation_type` | grade | rationale |
|---|---|---|
| `applicant_group_candidate` | `CANDIDATE_RELATION` | HORIZON itself calls it a hypothesis about corporate grouping |
| `priority_claim` | `SOURCE_ASSERTED_RELATION` | asserted by the patent office for its own document |
| `application_to_publication` | `SOURCE_ASSERTED_RELATION` | official bibliographic link; not a device-identity claim |

`applicant_group_candidate` is in `NON_PROMOTABLE_RELATION_TYPES`, and the adapter
re-checks that guard even if the mapping table changes.

## 3. Identifiers: scheme is decided by value where the source mixes namespaces

The single most consequential identifier decision in this integration:

- `udi_di` (FDA GUDID) **is** a UDI-DI: a 14-digit GTIN-14.
- `hc_mdall_device_identifier` (Health Canada) is **usually a catalogue token**
  (`6102F-PA00017`, `ACCUTORR 3`) and **occasionally a genuine GTIN-14**.

A field-level rename (`hc_mdall_device_identifier → di`) would either destroy the
real bridge or fabricate thousands of fake ones. Therefore:

1. the value is promoted to `di` **only** when it is 14 digits with a valid GS1
   Mod-10 check digit;
2. the derivation is recorded per identifier in
   `normalized.convergence.identifier_decisions`;
3. a 14-digit value with a **bad** check digit is reported as malformed and is
   **not** promoted;
4. classification schemes (`hs_code`, `fda_product_code`, `cfr_regulation`,
   `eurostat_comext_cell`, `hmrc_ots_series`) are carried as identifiers but carry
   `role: classification` and can never form a canonical key or an identity claim.

On the HORIZON sample this promotes **zero** identifiers (the sample contains no
GTIN-form MDALL value), which is exactly why EXP-H2's official-identifier signal
never fired. On the full MDALL table it would promote thousands — that is the
subject of `IDENTITY_RECONCILIATION.md`, not of this contract.

## 4. Four clocks, and what may not be done to them

`event_at` · `source_public_at` · `first_observed_at` · `fetched_at` are kept
separately and none may stand in for another.

Strict rules enforced in `clock.py`:

- A missing `first_observed_at` stays **empty** with
  `observation_basis = "unknown_no_observation_log"`. It is never back-filled from
  `event_at`, from `source_public_at`, or from the import time. (ATLAS's own
  `build_time` defaults it to `fetched_at`, which is correct for ATLAS's own
  connectors and wrong here, because HORIZON observed these records on
  2026-11-09, not at integration time.)
- `source_public_at_quality` is derived from the precision the source actually
  published (`exact` / `day` / `coarse` / `derived` / `unknown`), never inflated.
- A source `temporal_note` saying a field is "not a publication date" or a
  "refresh stamp" causes the publication clock to be **refused** (recorded with
  basis `rejected_derivation_attempted`) rather than accepted because the column
  was named like a date.
- `public_before_event` is flagged per record, because publication before the event
  it should precede is the one ordering pattern that is almost always a
  misassigned clock.
- `clock_relation` is stored (`event_before_public`, `event_equals_public`,
  `public_before_event`, `event_only`, `public_only`, `no_dates`) so downstream
  analysis can decide what a record can support instead of the adapter guessing.

Measured effect: 1,394 records carry no observation clock and stay unknown; 90
records have publication before event and are flagged; 370 records have
`event_at == source_public_at`, which makes them unusable for lead-time claims.

## 5. Licence: three separate rights

| right | meaning |
|---|---|
`may_query` | may we call the endpoint |
`may_analyse_locally` | may we compute over the records |
`may_redistribute` | may the records or derived values be published |

`open_no_explicit_licence` is treated as **ingest-and-analyse yes, redistribute
only with attribution and a rights caveat**; `terms_restricted` and
`requires_licence` are never ingested; `unknown` fails closed. Quarantine
overrides every per-source grant. The authoritative policy is
`config/convergence/licence_policy.json` (51 sources).

A record that may be analysed but not redistributed still enters staging, and
carries the ATLAS quality flag `licence_restricted` so no downstream artefact can
mistake it for publishable. Count on this run: 1,104 such records.

## 6. Lossless conversion

Every source field ends in exactly one of two places:

- **consumed** into a real ATLAS field (10 fields), or
- **preserved verbatim** under `normalized.horizon` (12 fields).

Nothing is dropped silently (`fields_dropped_silently = 0`). Fields the adapter has
never seen are reported as `extension_fields` rather than discarded. The whole
source record is stored inside the ATLAS record, so a future contract version can
re-derive any mapping without re-fetching.

## 7. Record, entity, event and relation identity are separate

Four layers, measured but never conflated (`dedupe.py`, EXP-C3):

| layer | question | collapse is safe because |
|---|---|---|
`record_identity` | same source publication of the same record? | same bytes, same source |
`entity_identity` | same real-world object? | only via an authoritative identifier |
`event_identity` | same official event? | **includes the party**, so co-awarded suppliers are never deleted |
`relation_identity` | same asserted link? | `(from, to, type, method)` |

A notice naming several suppliers is one event with several awards. Keying only on
the notice id would delete every supplier but one — a defect HORIZON had already
observed. The contract makes the party part of the key by construction.

Patent families are a fifth, orthogonal grouping: publications of one PCT family
are neither merged into one record nor counted as independent inventions.

## 8. What the contract refuses

| input | outcome |
|---|---|
unknown `schema_version` | rejected, reason recorded, payload retained |
unmappable `entity_type` | rejected, reason recorded |
restricted / licensed / unknown source | rejected by the licence gate before parsing |
record with no `source_id` or `source_record_id` | rejected |
contract violation after construction | rejected with the validator's messages |

Rejected records are stored in `conv_rejections` **with their payload**, so a
rejection is auditable rather than invisible. On this run: **0 rejections**, and
the paths above are exercised by tests against synthetic restricted and
schema-mismatched inputs so the refusal logic is proven, not merely present.
