# DEVICE_IDENTITY_MODEL

The data model PRODUCT-003 adds, and the distinctions it refuses to blur.

## Why the model exists

A row in an FDA dataset is not a device. The snapshot holds 91,457 records, but most of them are
events *about* applications, and a recall record does not even name a device. Before this module the
product could only say "this company has N records". The model below lets it say "this is device X,
identified by application Y, with versions V and these evidenced relations - and here is what is not
known".

## Entities

| Entity | Identifier (example) | What it is | What it is NOT |
|---|---|---|---|
| Regulatory record | `openfda_510k:K181234` (existing event id) | one row in an FDA dataset | not a device |
| Regulatory application | `app:openfda_510k:K181234`, `app:openfda_pma:P980016:S001` | an official FDA application identifier | not a commercial product |
| Device identity | `device:openfda_510k:K181234`, `device:openfda_pma:P980016` | the device an application cleared (510(k)) or approved (PMA) | not proof of a commercial SKU |
| Product family | `family:pma:P980016` | the official PMA application hierarchy (original + supplements) | not a brand family |
| Recall record | `openfda_recall:Z-0001-2009` | a safety action on a product description | not a device identity |
| Organization | `medtronic` (existing registry key) | the tracked company an applicant is attributed to | not the manufacturer of record |
| Evidence reference | `{kind, field, value, official_url}` | the official field that produced a relation | not a rule score |

Two identifier rules are enforced by construction:

1. **MedRadar identifiers never impersonate FDA identifiers.** They carry a type prefix
   (`app:`, `device:`, `family:`) and the official identifier is always stored separately and shown
   first in the UI. A test asserts the prefix and that a device page always links the official record.
2. **Identifiers are derived from official data** (source id + official number), so rebuilding the
   index produces identical identifiers and relation ids (`test_index_is_deterministic`).

## Identity rules

* **510(k)** - one clearance identifies one device model. The page states "identified by the FDA
  510(k) clearance that cleared this device model". Different K numbers are never merged, even when
  the applicant, product code and device name are identical; that case produces a *candidate* relation
  only.
* **PMA original** - one approval identifies one device. Its supplements are **versions** of that
  device, not new devices. The PMA number is the official hierarchy key.
* **PMA supplement** - creates an *application*, never a device identity. It appears as a version of
  the family and as a confirmed `application_has_supplement` relation with two official evidence
  references (PMA number on both sides + supplement number).
* **Recall** - creates no device identity. It links to an application only through the official
  `k_numbers` field. When the referenced K number is not in the snapshot the reference is counted
  (8,457 edges) but not drawn as an edge to a record that does not exist.
* **Unknown identity** - a recall with no reference stays in the unlinked browser. It is not guessed,
  not deleted and not attached to a device.

## What is deliberately not modelled

| Not modelled | Reason |
|---|---|
| Predicate relationships | openFDA exposes no predicate identifier for 510(k) submissions and the 510(k) summary documents were not collected. A predicate is not lineage anyway. |
| `record_mentions_device` relations | every application record names a device by definition; a relation for it would be tautological. The name is shown on the record and on the device page. |
| `manufacturer_of_device` relations | the applicant field is a record claim, not proof of current manufacture. It is shown as the applicant with its PRODUCT-002 attribution status. |
| UDI / GUDID linkage | not collected in this release; adding it would not change any identity above and would need its own governance review. |
| Cross-pathway device equivalence (510(k) <-> PMA) | no identifier or official document in the data establishes it; only candidates would be possible and a candidate is not an identity. |

## Model code

* `medradar/product/device/model.py` - entities, relation statuses, evidence refs.
* `medradar/product/device/build.py` - deterministic builder (applications -> devices -> families ->
  relations -> per-device stats), ~4.7 s for the committed snapshot, lazily built and cached per
  process; queries are 10-190 ms.
* `medradar/product/device/payloads.py` - API payloads and exports (the API is a thin projection).
* `medradar/product/device/quality.py` - relationship quality report.

## Counts in the committed snapshot

| | |
|---|---|
| Regulatory applications | 61,632 (510(k) 23,400 / PMA 574 / PMA supplements 37,658) |
| Device identities | 23,974 (510(k) 23,400 / PMA 574) |
| PMA product families | 630 (574 with the original in the snapshot, 56 supplement-only) |
| Recall records | 29,825 (15,022 linked by official K number, 6,227 external-only, 8,576 no reference) |
