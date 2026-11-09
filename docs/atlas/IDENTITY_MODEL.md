# IDENTITY_MODEL — companies, manufacturers, devices and identifiers

**Scope:** ATLAS-ID, the identity layer used by the pilot and by the graph.
**Guiding rule:** a string is not an identity. An identity is a claim with a scheme, an issuer,
a source, a time and an evidence record.

---

## 1. Why four entity types

| Entity | Represents | Must not be confused with |
|---|---|---|
| **Company** | the legal/business group (parent) | the manufacturer named on a record |
| **Manufacturer** | the entity that legally manufactured / holds the registration | the brand owner, which may differ |
| **Device** | one regulatory product record (a model/DI as a registry knows it) | a brand family or a marketing product |
| **Identifier** | an official registry identifier with scheme + issuer + scope | a model number, a product code, a licence category |

A single brand can be many `Device` rows (one per model/DI). A single `Device` row can carry
several identifiers of different schemes. `Company` and `Manufacturer` are related but not
collapsed: "Medtronic Sofamor Danek, Inc." is a manufacturer/legacy legal name linked to the
Medtronic company, and a record filed under it is not automatically a current Medtronic filing.

---

## 2. Field contracts

### Company
`company_id`, `canonical_name`, `country`, `legal_form`, `valid_from`, `valid_to`,
`former_names`, `subsidiaries`, `external_ids`, `parent_company_id`.
Validity dates matter because groups rename and spin out (GE HealthCare from GE in 2023).

### Manufacturer
`manufacturer_id`, `name`, `company_id`, `role ∈ {legal_manufacturer, brand_owner,
registration_holder}`, `country`, `site`, `relationship ∈ {subsidiary, parent, contract,
legacy_name, unknown}`, `valid_from`, `valid_to`.

### Device
`device_id`, `canonical_name`, `brand_name`, `model_number`, `catalog_number`,
`product_family`, `device_class`, `product_codes[]`, `markets[]`, `manufacturer_id`,
`company_id`, `identifiers[]`.
`model_number` and `catalog_number` are **manufacturer attributes**, not identifiers.

### Identifier
`scheme`, `value`, `issuer`, `scope`, `is_primary`. Supported schemes and their issuers:

| Scheme | Meaning | Issuer | Scope |
|---|---|---|---|
| `di` | UDI Device Identifier | GS1 / HIBCC / ICCBBA | global |
| `basic_udi_di` | Basic UDI-DI | EUDAMED | EU |
| `510k` | 510(k) clearance number | FDA | US |
| `pma` | PMA number | FDA | US |
| `denovo` | De Novo number | FDA | US |
| `product_code` | FDA product code | FDA | US category |
| `licence_no` | MDALL licence number | Health Canada | CA |
| `mdall_device_id` | MDALL internal device id | Health Canada | CA |
| `mdall_company_id` | MDALL internal company id | Health Canada | CA |
| `duns` | labeler DUNS | Dun & Bradstreet / FDA | US |
| `nct`, `doi`, `pmid`, `patent_no`, `ocid` | research / IP / procurement | various | various |

**Non-interchangeability is enforced in code:** `canonical_key()` prefers a DI over a licence
number over a clearance number, and comparisons only match a scheme against itself. A DI and a
510(k) number are never compared as strings.

---

## 3. Relation types and what each one licenses

| Relation | Meaning | Minimum basis | May be called identity? |
|---|---|---|---|
| `SAME_DEVICE_IDENTITY` | same regulatory device record | equal official DI (same scheme) | **yes** |
| `SAME_MODEL` | same manufacturer model string | confirmed firm + equal normalised model | no — model-level only |
| `SAME_PRODUCT_FAMILY` | same family/clearance/licence grouping | equal 510(k)/PMA/licence, or firm + product code | no — grouping only |
| `RELATED_TECHNOLOGY` | same technology category | shared FDA product code, different firms | no |
| `POSSIBLE_MATCH` | unresolved candidate | labels only (similarity / shared token) | no |
| `UNRELATED` | positive evidence of non-identity | different firms with identical brand; same firm with disjoint codes | no (it is a rejection) |
| `UNKNOWN` | insufficient fields | neither record has an anchor | no |

A candidate may never be counted in a confirmed denominator. The evidence schema rejects a
`candidate` entity link with confidence ≥ 0.9.

### Contradiction handling
If two records carry the same DI but disagree on model or brand, the resolver returns
`SAME_DEVICE_IDENTITY` with status `CANDIDATE`, records the contradictions, and the quality
check raises an `identity_contradiction` error. It does not pick a winner.

---

## 4. Company resolution tiers

`config/atlas_firms.json` is the only alias registry. A source string resolves to:

1. `official_id` — an authoritative company id came from the source (not used in this pilot);
2. `exact_alias` — folded string contains a curated alias as consecutive tokens and no
   negative guard fired;
3. `multi_field` — reserved for alias + independent field agreement (the pilot does not claim
   it, because the sources do not expose a second independent company field);
4. `candidate` — fuzzy overlap (kept, counted separately, never confirmed);
5. `none`.

Negative guards are part of the rule, e.g. `PHILIPS LIGHTING`/`SIGNIFY`, `GE AVIATION`,
`DRAEGER SAFETY AG`. A guard demotes the match to `candidate`; it is not dropped silently.

German umlauts transliterate to two letters (`Dräger` → `DRAEGER`) so curated ASCII aliases work.

---

## 5. Cross-market realities encoded in the pilot

1. **A UDI-DI is the only strong global key** available in the public data used here.
   GUDID/openFDA publish it; Health Canada MDALL *sometimes* publishes it.
2. **MDALL usually publishes a model/catalogue string**, not a UDI-DI. Measured on
   2026-11-10: 5,512 GTIN-14-shaped rows out of 1,673,926 active identifier rows (0.33 %).
   A Canadian licence therefore cannot be assumed to identify a UDI device.
3. **A 510(k) number groups products.** Many models can sit under one clearance; it cannot
   confirm device identity and is modelled as `SAME_PRODUCT_FAMILY`.
4. **A licence number groups a family.** MDALL "Device Family" licences contain many devices.
5. **Same string ≠ same device.** Brand collisions across firms are modelled as `UNRELATED`
   rejections with a stated reason; they are the hard-negative test set.

---

## 6. Company vs market identity

- A device can be registered in several markets under different national records. Cross-market
  identity is only confirmed when an official global identifier (DI / Basic UDI-DI) matches.
- Without a shared official identifier, the relation stays at `SAME_MODEL`/`POSSIBLE_MATCH`
  even when brand and model strings agree.
- Market-specific fields (`markets[]`) are recorded per device, never inferred from a company's
  headquarters.

---

## 7. Identity status vocabulary in evidence rows

Each evidence record carries `identity_resolution_status ∈ {confirmed, candidate, none,
not_attempted, ambiguous}`. That status is computed from the entity refs, not asserted by the
connector:

- any confirmed-tier ref → `confirmed`;
- only candidate-tier refs → `candidate`;
- a ref with a negative guard or conflicting fields → `ambiguous`;
- no refs attempted → `none`/`not_attempted`.

This lets a downstream query filter "records about the five firms" from "records that merely
mention a similar name" without re-reading the payload.
