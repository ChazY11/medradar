# RELATIONSHIP_EVIDENCE

Every relation MedRadar draws, the rule that produced it, and the evidence it carries.

## Status vocabulary

| Status | Meaning | Can the product show it as established? |
|---|---|---|
| `confirmed` | an official identifier or an official record field establishes the relation | yes |
| `evidence_supported` | an official free-text field names the link (vocabulary exists; **no relation needed it in this release**, count = 0) | yes, with the field quoted |
| `candidate` | a deterministic similarity rule suggests the link | **no** - always labelled "candidate only / not established" |
| `unlinked` | no relation; the record stays visible and is counted | n/a |

## Relation types in this release

| Type | Status | Rule | Evidence recorded |
|---|---|---|---|
| `application_has_supplement` | confirmed | `same_official_pma_number_v1` | `pma_number` on the original and the supplement + `supplement_number`, each with the official URL |
| `device_has_version` | confirmed | derived from the same PMA number (only in the device detail) | the supplement's `pma_number` with its official URL |
| `recall_references_application` | confirmed | `official_k_numbers_field_v1` | the recall's `k_numbers` value with the recall's official URL |
| `candidate_same_device` | candidate | `same_applicant_product_code_normalised_device_name_v1` | applicant, product code and normalised name values (rule evidence, no URL) |
| `candidate_recall_application` | candidate | `same_registry_group_product_code_v1` (bounded to 3 candidates per recall) | organisation key, product code, device-name token overlap |

A test asserts that the status of every relation equals the status its type declares, so a candidate
type can never be emitted as confirmed.

## Measured counts (committed snapshot)

| | Count |
|---|---|
| Total relations | 77,751 |
| Confirmed | **55,870** (37,038 `application_has_supplement` + 18,832 `recall_references_application`) |
| Candidate | **21,881** (20,227 recall->application + 1,654 same-device clusters) |
| Confirmed relations with official evidence + URL | **55,870 / 55,870 (100%)** |
| Candidate relations with rule evidence | 21,881 (rule evidence, not documentary) |
| Relations missing any evidence reference | **0** |
| Devices with a confirmed relation | 4,496 |
| Devices with a candidate relation only | 4,736 |
| Devices with no relation at all | 14,742 |

## Verification levels (kept separate on purpose)

1. **Rule consistency** - every confirmed relation comes from one of two named rules over official
   fields (`same_official_pma_number_v1`, `official_k_numbers_field_v1`).
2. **Documentary evidence** - every confirmed relation cites the official field value and URL (100%).
3. **Human review** - **0**. No human has reviewed a device relation in this release.
4. **Accuracy estimate** - **UNKNOWN**. No independent sample of device relations has been reviewed,
   so the product claims no accuracy figure. Rule consistency is not accuracy.

The quality report is served at `GET /api/devices/quality` and its verification levels contain
exactly these four entries.

## Worked examples

* **PMA hierarchy:** `P980016` has 934 supplements. Each one yields a confirmed relation whose
  evidence is the PMA number on both records; the device page lists them as versions ordered by
  decision date.
* **Recall reference:** a recall whose `k_numbers` field contains `K000001` produces a confirmed
  relation to `app:openfda_510k:K000001` with the field value as evidence. The device page shows it
  under "Related recalls" and "Linked by K000001".
* **Candidate only:** two clearances with the same applicant, the same product code and the same
  normalised device name produce `candidate_same_device`. Both keep separate device identities and
  the page labels the relation "candidate only".
* **External reference:** a recall that names a K number absent from the snapshot is counted in
  `external_k_references` (8,457 edges) and shown on the recall; no edge is drawn to a missing record.

## Ambiguity the report surfaces instead of hiding

* 2,079 recall records reference an application whose product code differs from the recall's own
  product code.
* 2,291 recall records reference more than one application (many-to-many is supported, not merged).
* 446 normalised device names are shared by more than one applicant: they are never merged.
