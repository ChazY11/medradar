# RESEARCH_VALIDATION — identity association, baselines and negative controls

**Study question:** before MedRadar can study technology emergence, it must know whether two
registry records describe the same device, the same model, the same family, or merely the same
words. This round measures that and bounds what a simple name-matching system would do.

---

## 1. What is being evaluated

| Item | Definition |
|---|---|
| Unit | a pair of device records: one from the U.S. GUDID projection (openFDA UDI), one from Health Canada MDALL |
| Positive label | the MDALL 14-digit identifier equals the GUDID UDI-DI — an **official identifier** both registries publish |
| Negative label | a different DI (random cross-registry pairs), after registry placeholders were removed |
| Method under test | ATLAS resolver: DI equality → `SAME_DEVICE_IDENTITY`; no name similarity may confirm |
| Baseline | label similarity ≥ 0.85 on brand/model (`baseline_name_match`) |

The label does not require a human: DI equality is an official assertion. That is also the
limit — this evaluation says nothing about devices that lack a shared UDI.

---

## 2. Data actually used

| Source | Sample |
|---|---|
| openFDA UDI | 500 company-page records (100 per target firm) + 8 additional records resolved during the bridge = 508 unique U.S. records |
| AccessGUDID | 12 re-reads; all 12 were duplicates of the openFDA records (same GUDID upstream) |
| openFDA 510(k) | 250 clearances, 50 per firm |
| MDALL | active identifier table downloaded once (219,970,233 bytes, 1,673,926 rows); 5,512 rows normalise to a 14-digit DI; 5,005 unique DI values; 40 licences + 40 companies detailed |
| Bridge | 1,200 deterministically sampled GTIN candidates → 942 resolved GUDID records → 934 paired device records |

---

## 3. Results (sampled labelled pairs)

| Method | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| ATLAS identity (official DI) | 934 | 0 | 0 | 400 | 1.000 | 1.000 |
| Name-similarity baseline (≥0.85) | 0 | 0 | 934 | 400 | undefined (0/0) | 0.000 |

**Reading this honestly**

1. The identity method recovers every official-identifier pair in the sample and produces no
   false positive against the sampled negatives. This is expected — the method *is* the label —
   and is therefore a **consistency check, not a discovery**.
2. The baseline recovers **none** of the 934 true pairs. Canadian MDALL publishes a *number*, not
   a brand/model, for those rows: there is no label to compare. On this bridge the name baseline
   is **uninformative**, not proven "actively wrong".
3. An earlier draft reported 33 baseline false positives. Independent audit showed all 33 were
   registry placeholders (`brand_name = "NA"`) colliding with each other. Those are not brand
   collisions; the resolver now erases placeholder labels and a regression test pins it. The
   honest hard-negative count in this sample is **0**.
4. These are **sampled** pairs, not a prevalence-weighted population. No overall F1 is claimed
   for "medical device identity".

The methodological conclusion remains: **for the cross-market bridge, name matching is not a
weaker identity method — it has nothing to compare.** The correct response is identity
infrastructure, not a better fuzzy threshold. Testing name matching *within* a registry requires
richer labels (e.g. MDALL licence names) and is listed in the roadmap.

---

## 4. Relation census from the full run

| Relation | Count | Meaning |
|---|---:|---|
| `SAME_DEVICE_IDENTITY` (CONFIRMED) | 934 | exact DI equality across U.S. and Canadian registries |
| `SAME_PRODUCT_FAMILY` (CONFIRMED) | 192 | shared 510(k)/licence grouping or same firm + product code |
| `SAME_MODEL` (CONFIRMED) | 2 | same firm + same model string, different DI (explicitly *not* identity) |
| `POSSIBLE_MATCH` (CANDIDATE) | 59 | label similarity only; never promoted |
| `RELATED_TECHNOLOGY` (CANDIDATE) | 10 | shared FDA product code, different firms |
| `UNRELATED` (REJECTED) | 1,087 | same-firm disjoint codes and other positive non-identities, reasons stored |
| `UNKNOWN` | 0 | every sampled pair had enough fields to decide |

The graph layer additionally stores 782 `MANUFACTURED_BY` and 5,544 `REGISTERED_AS`
source-declared relations; these are kept out of the identity census above.

---

## 5. Negative controls and leakage checks

| Control | Implementation | Result |
|---|---|---|
| Keyword/name baseline | `baseline_name_match` on the same pairs | 0 TP, 0 FP, 934 FN |
| Wrong product match | same firm, disjoint FDA product codes → `UNRELATED` | included in the 1,087 rejections, reasons stored |
| Same-company different product | `SAME_MODEL`/`SAME_PRODUCT_FAMILY` instead of identity | 2 + 192 relations, none called identity |
| Identical-brand hard negatives | same real normalised brand, different firms → `UNRELATED` | **0 found** in this sample; placeholder labels excluded; reported as a gap, not padded |
| Duplicate/independence control | `canonical_key` + `is_independent`; AccessGUDID re-reads counted as duplicates | 12/12 duplicates detected, not 12 corroborations |
| Primary-DI control | canonical key prefers the primary DI over package DIs | package-DI mis-dedupe fixed; regression test |
| Time leakage | `first_observed_at` is a fetch clock; `as_of` separates bases | observed 7,254; **of those**, 1,452 have a public date ≤ the query time; 5,802 have no usable date. The bases overlap and are not additive. |
| Future company attribution | company validity dates stored; legacy manufacturer names link to a group but are not treated as current filings | modelled in `Manufacturer` role/relationship |

---

## 6. Independent re-check

- `tools/verify_atlas.py` recomputes every confirmed pair shares at least one DI, every payload
  hash, request-log coverage, revocation history, report-vs-database counts and the baseline
  arithmetic. **16/16 pass.**
- One real evidence path is committed as
  `research/atlas/reports/examples/query_relation_confirmed.json`: both evidence records, source
  URLs, clocks, **source and normalized content hashes**, identifiers and the shared DI.
- 20 complete company → device → DI → regulatory-record chains are in
  `research/atlas/reports/examples/query_path_medtronic.json`.

---

## 7. What this study does **not** establish

1. It does not estimate precision/recall for global device identity.
2. It does not establish that 934 is the true number of U.S.–Canada shared devices; it is the
   number recoverable from the UDI-adopting subset of MDALL.
3. It does not validate `POSSIBLE_MATCH` or `RELATED_TECHNOLOGY` candidates — they have no
   gold standard in this round by construction.
4. It does not test prediction of future regulatory events. PHOENIX's negative results remain
   the record on that question; ATLAS provides the substrate to test it prospectively later.
5. It does not demonstrate that name matching produces false positives at scale; the sample had
   no real cross-firm label collisions once placeholders were removed.

---

## 8. Reproduction

```bash
python tools/run_atlas_pipeline.py          # bounded live collection + reports + verifier
python -m pytest tests/test_atlas_identity.py tests/test_atlas_evidence.py \
  tests/test_atlas_db.py tests/test_atlas_research.py tests/test_atlas_connectors.py -q
python tools/verify_atlas.py
```

Expected: 16/16 verifier checks pass; the numbers above are read directly from
`research/atlas/reports/identity_pilot.json`.
