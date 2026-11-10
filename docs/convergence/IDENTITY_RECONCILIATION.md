# IDENTITY_RECONCILIATION — why ATLAS found 934 US↔Canada device identities and HORIZON found 0

**Task:** P0-B / shared task `task-2`.
**Question:** ATLAS reports 934 confirmed US–Canada `SAME_DEVICE_IDENTITY` pairs. HORIZON EXP-H2
reports 0 confirmed and all 726 pairs `UNKNOWN`. Is that a contradiction?

**Short answer: no.** The two experiments measured different things on different samples, and one
of them also typed the shared field differently. HORIZON's Canada slice contains 49 MDALL
`device_identifier` values, **none of which is a 14-digit GTIN**, so its official-identifier rule
(S4) was arithmetically unable to fire on any of its 726 pairs. ATLAS scanned the whole 1,673,926-row
MDALL active table, isolated the **5,512-row / 5,005-value GTIN-14 minority (0.329% of rows)**, queried
1,200 of those values against openFDA UDI, and found **934 exact GTIN-14 equalities**, every one of
which passes the GS1 Mod-10 check digit and every one of whose Canada side is re-derivable from the
raw frozen MDALL table. Both experiments are internally correct. HORIZON's `0` is a coverage and
field-typing result; ATLAS's `934` is real but thin, concentrated (81.4% from a single Canadian
licence and a single US labeler), and it does **not** establish corporate identity or global device
identity. The universal sentence HORIZON wrote into its own records — *"MDALL device_identifier …
is NOT a UDI-DI and shares no namespace with FDA GUDID"* — is false in its universal form and must
be narrowed to "for 99.67% of MDALL rows".
**No network call was made. Everything below is reproduced offline from frozen, SHA-256-bound inputs.**

---

## 1. What each experiment actually measured

| | ATLAS identity pilot (`research/atlas/reports/identity_pilot.json`, PR #28 `c636836`) | HORIZON EXP-H2 (`research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json`, PR #29 `2dcdc99`) |
|---|---|---|
| US records | openFDA Device UDI records: 500 by company-name search + **942 returned by identifier batch queries** + 12 AccessGUDID | 320 AccessGUDID records (October 2026 GUDID release), five pre-declared firms |
| Canada records | **full scan of the MDALL active `deviceidentifier` table, 1,673,926 rows → 5,512 GTIN-14-class rows (5,005 distinct values)** + 40 licence records → 5,552 `canada_mdall` evidence rows | **174 MDALL records (60 licences / 65 devices / 49 device identifiers)** selected by firm + keyword (`licence_name`/`device_name`/`deviceidentifier?id=`) |
| Pair construction | 1,200 of the 5,005 GTIN values (systematic 1-in-4.17 sample) queried against openFDA UDI; a pair is created only when the returned record's `di` equals an MDALL identifier | cross-product filtered to pairs where at least one of S1/S2/S3/S4/S5 fires |
| Pair table | **934 `SAME_DEVICE_IDENTITY` / `CONFIRMED`**, 0 candidate, 0 contradicted | **726 pairs, all `UNKNOWN`**; 700 candidate + 26 hard negatives |
| Confirmation rule | exact equality of a 14-digit identifier across the two records (`method=official_identifier`, `authority=source_declared`) | **S4 only**: "any official identifier value is equal on both sides **in the same scheme**" |
| Labelled evaluation set | 1,334 pairs = 934 positives + 400 sampled negatives; precision/recall 1.0 *on that sample only*, with an explicit "not a population estimate" caveat | no positives exist, so no metrics; the deliverable is a negative result with a signal-sufficiency table |

**The two Canada slices are not comparable samples.** ATLAS's Canada side is selected by *identifier
shape* (a full-table census of the GTIN-14 minority, plus 40 licences); HORIZON's is selected by
*company and keyword* among the five firms. They are complementary by construction: one is the
0.33% shape class, the other samples the 99.67% token class. 5,552 vs 174 evidence rows (≈32×) is
that difference, not a disagreement about facts.

---

## 2. What a "match" actually is (verification of the 934)

All checks below are reproduced by `tools/convergence/identity/extract_atlas_bridge.py` against the
frozen DB (`6f77822e…`), the raw MDALL cache (`55d2b641…`, identical to the `sha256` ATLAS recorded
in its own report), and HORIZON's frozen slices.

### 2.1 GTIN-14 validity — all 934 are real, check-digit-valid GTINs

| check | result |
|---|---|
| 934 pairs, distinct `basis_json.$.shared_identifier` | **934 distinct** values (`di:<14 digits>`), scheme `di` in all 934 |
| syntactically 14 digits | **934 / 934** |
| **GS1 Mod-10 check digit valid** | **934 / 934** |
| blank / missing / non-numeric | 0 |
| duplicate shared identifiers | 0 |
| canonical key equals the shared DI on both sides | 932 / 934 (the 2 exceptions are the package-DI anchors in §2.4) |

This is the strongest single falsification test in the reconciliation: a string coincidence
between MDALL's catalogue field and a GUDID DI would not be expected to satisfy the GS1 check
digit 934 times in a row. ATLAS's own `is_gtin_like()` only checks *shape* (14 digits, no check
digit); this report adds the check. For context, the MDALL GTIN-14 *class* is 5,512 rows /
5,005 values, of which 5,434 rows / 4,927 values pass Mod-10 and **78 distinct values do not**
(e.g. `02002262000040`, `02002264000000`) — those are numeric catalogue tokens, not GTINs. None of
the 78 invalid values appears among the 934.

### 2.2 Both sides are official records

* **US side**: each left record is an `openFDA - Device UDI` `device_registration` evidence row with
  official `public_device_record_key`, `company_name`, `labeler_duns_number`, `product_codes`,
  `publish_date`, and the DI in `identifiers[]`. It is **not** re-fetched offline; it is verified at
  record level against ATLAS's stored copy of the official openFDA payload (no network).
* **Canada side**: each right record is an MDALL `device_registration` evidence row carrying the
  official `device_identifier`, `original_licence_no` and `device_id`. **This side is fully
  re-derived from the raw frozen table**, not trusted from the DB: 934/934 identifiers are present
  in `mdall_active_deviceidentifier.json`, 934/934 licence numbers match, 934/934 `device_id`s match.

**Independence ledger** (from `ATLAS_BRIDGE_934.json`):

| check | result | independent of ATLAS's stored claim? |
|---|---|---|
| 934 relations are `SAME_DEVICE_IDENTITY`/`CONFIRMED`, single run | 934 | no — re-read of ATLAS's relation table |
| Canada identifier present in the **raw** MDALL table | **934 / 934** | **yes** — full re-derivation |
| Canada licence and `device_id` match the raw row | **934 / 934** | **yes** |
| US record payload is self-consistent (DI present, scheme/issuer set) | 934 / 934 | no — record-level check of stored payload |
| US-side cross-check against HORIZON's independently pulled GUDID slice | 0 / 934 overlap | yes, but different 320-record slice → weak by construction |
| Canada-side cross-check against HORIZON's independently pulled licence slice | 0 licences overlap | yes, but different 60-licence firm-targeted slice |
| bridge subsample reproducible (sorted 5,005 keys, 1,200 evenly spaced) | **934 / 934 confirmed DIs inside the reproduced query set** | **yes** — deterministic recomputation |
| request ledger shows the queries | **934 / 934 DIs appear in the 48 logged bridge batch URLs (1,200 tokens, 42×200, 6×404)** | **yes** — separate file from the evidence payloads |

The bridge batch accounting (48 batches, 6 no-match, 0 failed) is reproduced exactly from
`atlas_requests.jsonl`, and the 1,200-token subsample is reproduced exactly from the raw cache.

### 2.3 DI scope: 932 primary DI, 2 package DI

Health Canada's MDALL has **no primary/package DI concept** — the identifier table publishes one
`device_identifier` string per device row. ATLAS *asserts* `scheme=di`, `scope=global`,
`is_primary=1` for any 14-digit value; that is ATLAS's interpretation, not a Health Canada
declaration, and must be labelled as such. The primary/package distinction exists only on the GUDID
side (`identifiers[].type`).

Measured on the 934: **932 pairs are anchored on the US record's primary DI; 2 are anchored on a
GUDID package DI** (`00856825003203`, `44710810093560`, both from GALEMED CORPORATION under MDALL
licence 114223). A package-DI match is a *weaker* claim than a primary-DI match: it identifies a
packaging configuration of the device, not the base device. ATLAS's own connector docstring says
"only the **primary** DI is used for device identity"; the code path violates that for 2/934.

### 2.4 The 942-vs-934 accounting, and an identifier-order defect

ATLAS reports `bridge_fda_records_resolved: 942` and `bridge_pairs: 934`. The 8-record gap is now
explained on the 942 records actually returned:

* `resolver.view_from_evidence()` takes the **first** `identifiers[]` entry with scheme `di` in the
  stored openFDA payload, **not the primary DI**.
* On exactly those 942 records: first-di anchoring gives **934** pairs (the published number);
  primary-DI anchoring gives **941**; 9 records list a non-primary DI first.
* Of the 8 unpaired records, **7 are primary-DI matches that were dropped only because a package DI
  was listed first**, and 1 is available only through a package DI (correctly dropped by ATLAS's
  intent). The 2 published package-DI pairs are the symmetric error.

So: `934` is reproducible and every pair is a genuine exact GTIN-14 equality, but it is **an
order-dependent subset of the 941 primary-DI equalities available in the returned records**. This is
a bounded code defect, not a data problem; it is documented here so the number is not over-trusted.

### 2.5 Duplicates and the "one GTIN, many MDALL rows" pattern

| property | value |
|---|---|
| pairs / distinct relation ids / distinct (from,to) / distinct shared DI | 934 / 934 / 934 / 934 |
| distinct US evidence rows / distinct US `public_device_record_key` | 934 / 934 |
| distinct CA evidence rows | 934 |
| any DI in more than one pair; any US record in more than one pair | **0; 0** |
| distinct MDALL licences behind the 934 | 66 |
| distinct MDALL `device_id`s behind the 934 | 127 |
| **GTIN values appearing in more than one MDALL row (whole table)** | **235 of 5,005** (211 under >1 licence, 233 with >1 `device_id`; max 5 rows; 507 surplus rows) |
| confirmed DIs with >1 MDALL row / >1 licence / >1 `device_id` | **47 / 43 / 46** |
| normalisation collisions (two raw strings → one 14-digit value) | 0 |

**No product is double-counted and no DI maps to two pairs.** However the ambiguity is real in the
source: 43 of the 934 GTINs are listed under more than one Canadian licence (e.g. `00816847021043`
under licences 89753 and 89835). ATLAS keys its MDALL view by DI and keeps the **last** cache row, so
the licence reported for those 43 pairs is arbitrary (a dict-overwrite artefact). The identity claim
survives; the **licence attribution** for those 43 pairs does not.

---

## 3. Verifying HORIZON's 0

### 3.1 Its sample contains no GTIN-14 at all

From the frozen `DATASETS/regulatory/canada_mdall/records.jsonl` (`b00c4565…`):

| scheme | values | 14-digit values |
|---|---|---|
| `hc_device_licence` | 174 (one per record) | 0 |
| `hc_mdall_device_id` | 114 | 0 |
| `hc_mdall_device_identifier` | **49** | **0** — not one value is all-digit; examples `6102F-PA00017`, `ACCUTORR 3`, `115-031807-00` |

US side: 320 records, all `udi_di`, all 14-digit. Intersection of the 49 MDALL identifier values with
the 320 GUDID DIs = **0**. Even a value-blind string comparison across all schemes would fire zero
times on HORIZON's own 726 pairs — its `S4 = 0` is **forced by the sample**.

Its 726 pairs are also a narrower slice than the 320×174 frame suggests: they are built from **46
distinct GUDID records (of 320) and 86 distinct MDALL records (of 174)**, expanded many-to-many:
700 candidate pairs + 14 `HN3_same_family_different_device` + 12 `HN4_subsidiary_vs_parent`
(HN1/HN2 = 0), all 726 verdicts `UNKNOWN`, `S4` fired 0.

### 3.2 Its rule is scheme-label-literal, so it would not fire even if the value were present

`research/horizon/experiments/regulatory/exp_h2_identity.py::ids_overlap` compares identifiers **only
when the declared scheme strings are identical**:

```python
for sch in set(a) & set(b):
    if a[sch] & b[sch]:
        return True, f"{sch}={sorted(...)[0]}"
```

GUDID records are typed `udi_di`; HORIZON's MDALL connector types every `device_identifier` as
`hc_mdall_device_identifier` (`CONNECTORS/regulatory/canada_mdall.py:206`), with **no GTIN special
case**. The scheme sets are disjoint, so S4 is structurally false for *every possible MDALL record*,
not just for the 49 sampled. ATLAS instead promotes a 14-digit MDALL value to `di`. **The two
experiments disagree about how to type the same Health Canada field**; that is the second, formal
layer of the 934-vs-0 gap.

### 3.3 HORIZON's universal semantic claim is over-general — and is written into 49/49 records

`DATASETS/regulatory/canada_mdall/records.jsonl`, field `attributes.identifier_semantics`, on every
`product_identifier` record; also in `exports/horizon-2026-11-10/canada_mdall.jsonl` (49/49 records);
source: `CONNECTORS/regulatory/canada_mdall.py:221-224`:

> "MDALL device_identifier is Health Canada's own model/catalogue token for the licensed device line
> (e.g. 'P02-14030'). It is NOT a UDI-DI and shares no namespace with FDA GUDID."

This is true for **99.6707%** of the table (1,668,414 / 1,673,926 rows) and true for HORIZON's own 49
values — and false in the universal form it asserts. The exact counts that refute it:

| measured fact (whole frozen table) | count |
|---|---|
| MDALL active identifier rows | 1,673,926 |
| rows whose `device_identifier` is 14 digits (after ATLAS's separator normalisation) | **5,512** (0.3293%) |
| distinct 14-digit values | **5,005** (of 1,546,415 distinct normalised values) |
| 14-digit rows with a **valid GS1 Mod-10 check digit** | **5,434** rows / **4,927** distinct |
| 14-digit values that are **not** check-digit-valid (numeric catalogue tokens) | 78 distinct |
| … of which equal a GUDID UDI-DI (ATLAS's confirmed bridge) | **934** |
| licences with at least one GTIN-14-class row | 227 of 36,056 (0.630%) |
| MDALL `device_id`s with at least one GTIN-14-class row | 679 of 146,183 (0.464%) |

**Recommended correction** (for HORIZON, one sentence): *"MDALL device_identifier is usually a
model/catalogue token; a measured minority of 5,512 of 1,673,926 active rows (0.329%, 5,005 distinct
values) are GTIN-14-shaped, 4,927 of which pass the GS1 check digit and can be joined to GUDID UDI.
The field therefore does share a UDI namespace, thinly."*

---

## 4. The unified sample: both methods on one frozen pair table

`tools/convergence/identity/unified_sample.py` writes
`research/convergence/identity/UNIFIED_SAMPLE.jsonl` (`09109c67…`): **1,660 rows = 934 ATLAS pairs +
726 HORIZON pairs**, each carrying both records and both identifier typings. No resampling.

**Structural disjointness — the samples never met:**

| overlap | count |
|---|---|
| shared pair ids | 0 |
| shared US record ids / shared US DIs | 0 / 0 |
| shared Canada identifier values | 0 |
| shared Canada licences | 0 |

Methods applied to all 1,660 rows:

* **A — ATLAS bridge**: `CONFIRMED` iff both records carry the same 14-digit, Mod-10-valid GTIN-14.
* **H2 native** — the pre-registered H2 rule as implemented: `CONFIRMED` only if S4 fires, i.e. the
  same value under the **same source-declared scheme**.
* **H2 namespace** — a charitable reading in which a Mod-10-valid 14-digit Canada identifier is
  promoted into the UDI-DI namespace before S4 is applied.

### 2×2 confusion, native field typing (the two experiments as they were actually run)

|  | H2 native CONFIRMED | H2 native not confirmed | total |
|---|---|---|---|
| **ATLAS bridge CONFIRMED** | **0** | **934** | 934 |
| **ATLAS bridge not confirmed** | **0** | **726** | 726 |
| total | 0 | 1,660 | 1,660 |

Rejected: ATLAS 0, H2 0. Unknown: ATLAS 726, H2 1,660.
**Disagreement = 934 pairs: every confirmed pair is one that HORIZON's sample never contained.**

### 2×2 confusion, namespace field typing (same sample, same facts, H2's S4 semantics repaired)

|  | H2 namespace CONFIRMED | H2 namespace not confirmed | total |
|---|---|---|---|
| **ATLAS bridge CONFIRMED** | **934** | **0** | 934 |
| **ATLAS bridge not confirmed** | **0** | **726** | 726 |
| total | 934 | 726 | 1,660 |

**The 934-vs-0 gap is fully decomposed:** 934 pairs of sample difference (ATLAS's positive set is
disjoint from HORIZON's pair space) and, independently, a field-typing difference that suppresses S4
on any MDALL data. **No pair in the unified sample is confirmed by one method and refuted by the
other**, and neither method rejects any pair it was given (name-level evidence cannot refute identity
either — HORIZON's own point).

*Caveat:* the union of the two pair tables contains no ATLAS hard negatives (the 400 negatives were
sampled inside the pilot and were never exported), so the "neither" cell is pure HORIZON-candidate
space. This does not affect the disagreement count, which is about positives.

---

## 5. How far does the conclusion generalise? The explicit bound

* **Joinable ceiling (before matching):** at most **5,512 / 1,673,926 = 0.3293% of MDALL active
  identifier rows** can ever be joined by official UDI; **227 / 36,056 = 0.630% of Canadian
  licences**; **679 / 146,183 = 0.464% of MDALL device lines**; **5,005 / 1,546,415 = 0.3236% of
  distinct MDALL identifier values**. Everything else — 1,668,414 rows (99.6707%) — publishes no
  UDI to join on.
* **Confirmed fraction of that ceiling:** 934 / 5,512 = **16.94%** of class rows and 934 / 5,005 =
  **18.66%** of class values; against the whole table, 934 / 1,673,926 = **0.0558%** of MDALL rows.
* **Of the query sample:** 1200 of 5005 GTIN values were queried (23.98%, a *systematic* 1-in-4.17
  sample of the sorted keys, reproduced exactly); **934 / 1,200 = 77.83%** of queried values found a
  US counterpart. **3,805 GTIN values were never queried**, so 934 is a *lower bound* on what this
  method could confirm — and no extrapolation is made here.

**Bound to state explicitly in any downstream claim:** *at most ~0.33% of the MDALL table is even
joinable by official UDI, and only 934 pairs (0.056% of MDALL rows) are confirmed. This is a thin
official bridge, not a solution to global device identity.*

---

## 6. Corporate attribution: the bridge is not a five-firm story

This corrects the working assumption that the bridge is "concentrated in Medtronic/GE".

| fact | value |
|---|---|
| distinct US labeler companies behind the 934 | **37** |
| pairs whose US labeler is **any of the five target firms** | **10 (1.07%)** strict alias / **12 (1.28%)** by ATLAS's stored `firm_key` |
| pairs whose US labeler is **outside** the five-firm register | **924 (98.93%)** |
| largest labeler | **Bloomden Bioceramics (Hunan) Co., Ltd. — 760 pairs (81.37%)** |
| next: Sbo Hearing A/S / Steris Mexico / 3D Systems | 50 / 42 / 15 pairs |
| top 4 labelers | 867 / 934 = **92.83%** |
| distinct MDALL licences | 66; largest **licence 113873 = 760 pairs (81.37%)** |
| Canada-side company known (any tier) | **9 / 934 (0.96%)**, all GE HealthCare name-alias links (7 exact-alias tier, 2 candidate tier) |
| Canada-side company unknown | **925 / 934 (99.04%)** |
| same firm group on both sides (confirmed tier) | **6 pairs (0.64%)** |

Why Canada-side attribution is almost impossible offline: MDALL's identifier table publishes no
company column; ATLAS fetched only 40 licences (13 exact-alias and 8 candidate company links, all
GE); HORIZON's independent 60-licence slice has **zero** overlap with the 66 licences behind the 934.
`missing_firms_in_bridge: [draeger, mindray, philips]` in ATLAS's report is literally true but
misleading as a summary: the two "present" firms account for only ~1% of the pairs, and the bridge's
mass sits with manufacturers that are not in the five-firm frame at all.

Consequences: the 934 do **not** demonstrate corporate coherence across the border (subsidiary-vs-
parent, HN4, cannot be adjudicated for 99% of pairs). They demonstrate *identifier* equality; any
corporate reading needs the licence holder's official identity, which the frozen data does not carry
for the dominant licence.

---

## 7. What should happen to records the bridge cannot connect

| class | size | recommendation |
|---|---|---|
| MDALL rows with no GTIN-14 identifier | 1,668,414 rows (99.67%) | Keep as Canada-market records with `identity_resolution_status=none/unknown`. Do **not** promote via name/model to `SAME_DEVICE_IDENTITY`; at most `SAME_MODEL`/`SAME_PRODUCT_FAMILY` where an official 510(k)/licence grouping supports it. Absence of a UDI is not evidence of non-identity. |
| GTIN-class values never queried | 3,805 (of 5,005) | `unknown`, not `negative`. If coverage is needed, query them; do not extrapolate the 77.83% hit rate. |
| Pairs where the US record is not the primary DI | 2 published (+7 recoverable) | Re-anchor on the primary DI before calling it device identity; keep package-DI matches at a weaker relation. |
| US records no longer in commercial distribution | 2 / 934 | Keep the identity, but do not describe the pair as a currently marketed device without checking the Canadian licence status against the US distribution end date. |
| GTIN-14 values that fail the check digit | 78 distinct | Treat as numeric catalogue tokens, **not** UDI; never bridge them. |
| Cross-border identity in general | — | Only an official shared identifier can confirm. Where none exists the correct verdict is `UNKNOWN`, never a name-based `CONFIRMED` and never a name-based `REJECTED`. |

---

## 8. Defensible scope

**Supported by this work**
1. HORIZON's `0` is correct *for its sample* and arithmetically forced: 0/49 GTIN-14 identifiers and
   disjoint scheme namespaces; a value-blind comparison also yields 0 on its 726 pairs.
2. ATLAS's `934` are 934 distinct, exact, Mod-10-valid GTIN-14 equalities between MDALL active
   `device_identifier` rows and openFDA UDI records; the Canada side is fully re-derivable from the
   raw frozen table (934/934), and the query set and batch accounting are independently reproducible.
3. The two experiments are not in conflict: their pair spaces are disjoint (0 shared US DIs, 0 shared
   Canada identifiers, 0 shared Canada licences).
4. The MDALL `device_identifier` field is heterogeneous: 99.67% model/catalogue tokens and 0.33%
   GTIN-14-shaped values (4,927 distinct check-digit-valid).
5. The official bridge is real but thin and concentrated: at most 0.329% of MDALL rows are joinable;
   81.4% of confirmed pairs come from one licence/one US labeler.

**NOT supported (do not claim)**
1. Population precision/recall, F1, or a US–Canada identity *rate*. ATLAS's 1.0 is on 1,334 sampled
   pairs only; 934/5,005 or 934/1,673,926 must not be presented as a rate of true identities.
2. That the five target firms have a US–Canada identity bridge: only 10–12 of 934 pairs are theirs.
3. That the pairs are corporately verified: 925/934 have no Canada-side company identity in the
   frozen data, and "same DI" is not "same legal entity".
4. That a package-DI match is a primary-device identity (2/934 are package-anchored).
5. That "MDALL shares no UDI namespace" as a universal statement — it is false for 5,512 rows.
6. That 934 is the complete set — 3,805 GTIN values were never queried.

---

## 9. Known limitations / what would falsify this

**Limitations**
* The US side was **not re-acquired** (offline rule). It is verified at record level against ATLAS's
  stored openFDA payloads; the 48 batch URLs and their statuses are corroborated from the request
  ledger, but response bodies are only available as ATLAS stored them.
* ATLAS's US sample itself is bounded: 942 records returned for 1,200 queried identifiers; openFDA's
  company-search samples are first pages, not random.
* The 1,200-of-5,005 subsample is **systematic**, not random; no population inference is valid.
* MDALL licence↔identifier semantics are not fully resolved: one licence `113873` lists 760 of the
  matched DIs, and 43 confirmed GTINs sit under more than one licence. "Licence family" vs "device"
  granularity remains market-specific.
* No human adjudication was performed by either experiment, and none is added here.
* The unified-sample "neither" cell contains only HORIZON candidate space; ATLAS's 400 sampled
  negatives were never exported.
* The HORIZON `identifier_semantics` claim is a documentation defect, not a data defect: its 174
  records are correctly collected for what they are.

**Falsifiers (and current status)** — full machine-readable list in
`COVERAGE_AND_ATTRIBUTION.json::falsifiers`
1. Any of the 934 failing a 14-digit or Mod-10 check → **not fired (934/934 pass)**.
2. Any Canada side absent from the raw frozen table or mismatched on licence/device_id → **not fired**.
3. HORIZON's Canada slice containing a GTIN-14, or a shared DI with ATLAS → **not fired (0 and 0)**.
4. Either method confirming something the other refutes on the unified sample → **not fired
   (native: 934 ATLAS-only; namespace: 934 both)**.
5. The bridge reaching a large share of MDALL or spreading evenly across manufacturers →
   **refuted already: 0.33% ceiling, 81.4% single-licence concentration; this is why the claim is
   bounded rather than general.**
6. Canada-side corporate identity contradicting the US side → **cannot be tested for 925/934 pairs**.

---

## 10. Frozen inputs (SHA-256, size, mtime UTC)

`research/convergence/identity/FROZEN_INPUTS.json`, generated by
`tools/convergence/identity/freeze_inputs.py`. Worktrees: `convergence-001` at `3c3a295…`,
`atlas-001` at `c63683631a1b…` (PR #28 head).

| role | path | bytes | SHA-256 | mtime UTC |
|---|---|---|---|---|
| atlas_db | `…/atlas-001/research/atlas/staging/atlas.sqlite` | 52,060,160 | `6f77822e57edf5a2c8d86423e22c30399d21bf97c56ac6dcd86ecb9384d8bffb` | 2026-11-10T17:43:27Z |
| mdall_cache | `…/atlas-001/research/atlas/cache/mdall_active_deviceidentifier.json` | 219,970,233 | `55d2b64189a2b8b6d3d7431462930196aebe5503addeeb6a4a6f0d65f5c2973f` | 2026-11-09T23:02:07Z |
| atlas_identity_report | `research/atlas/reports/identity_pilot.json` | 8,377 | `12702ae0a89650786b3777a29801b59b684e36913125ca34daf096a3ac7cc6a8` | 2026-11-10T18:18:36Z |
| horizon_mdall_records | `research/horizon/DATASETS/regulatory/canada_mdall/records.jsonl` | 288,641 | `b00c4565ba24346877954124dceecebcbf844dd5cbce1792749bb404479e0dc7` | 2026-11-10T18:22:36Z |
| horizon_gudid_records | `research/horizon/DATASETS/regulatory/accessgudid/records.jsonl` | 733,815 | `233274cb66d4a75552b6d4be52af89c1ae10fec46ce22c0d1052ff1b1c089c54` | 2026-11-10T18:22:36Z |
| horizon_h2_pairs | `research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl` | 679,872 | `e7ad98e1d6b45636d1e1ea4159ce1780e22ec3c2d977cd1b5fa98ab1046390d9` | 2026-11-10T18:22:37Z |

The MDALL cache digest equals the `sha256` ATLAS recorded in
`identity_pilot.json::stages.canada_mdall.table.sha256` — the table analysed here is byte-identical to
the one ATLAS scanned. Supporting inputs (HORIZON counts/summary/selection rule, ATLAS pairs sample,
request log, `docs/atlas/IDENTITY_MODEL.md`, `config/atlas_firms.json`) and method-source hashes are
in `FROZEN_INPUTS.json`.

---

## 11. Reproduction (offline; from `D:\DEPPSKK\worktrees\convergence-001`)

```powershell
python tools/convergence/identity/freeze_inputs.py          # FROZEN_INPUTS.json
python tools/convergence/identity/analyse_mdall_cache.py    # MDALL_CACHE_ANALYSIS.json  (~60 s, 220 MB scan)
python tools/convergence/identity/extract_atlas_bridge.py   # ATLAS_BRIDGE_934.json     (~60 s, 220 MB scan)
python tools/convergence/identity/unified_sample.py         # UNIFIED_SAMPLE.jsonl + UNIFIED_SAMPLE_RESULTS.json
python tools/convergence/identity/coverage_bounds.py        # COVERAGE_AND_ATTRIBUTION.json
python -m pytest tests/convergence/test_identity_reconciliation.py -q
```

Artefacts under `research/convergence/identity/`:
`FROZEN_INPUTS.json`, `MDALL_CACHE_ANALYSIS.json` (`55d2b641…` table),
`ATLAS_BRIDGE_934.json` (934 pairs + per-pair fields + verification ledger),
`UNIFIED_SAMPLE.jsonl` (1,660 rows, `09109c67…`) and `UNIFIED_SAMPLE_RESULTS.json`,
`COVERAGE_AND_ATTRIBUTION.json` (ceilings, concentration, falsifier ledger).
