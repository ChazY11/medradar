# RESEARCH_VALIDATION — identity association, baselines and negative controls

**Study question:** before MedRadar can study technology emergence, it must know whether two
registry records describe the same device, the same model, the same family, or merely the same
words. This round measures that, and bounds what a simple name-matching system would do.

---

## 1. What is being evaluated

| Item | Definition |
|---|---|
| Unit | a pair of device records, one from the U.S. GUDID projection (openFDA UDI) and one from Health Canada MDALL |
| Positive label | the MDALL 14-digit identifier equals the GUDID UDI-DI — an **official identifier** both registries publish |
| Negative label | different DI, plus a deliberately hard subset (identical brand strings across different firms, same model strings across firms) |
| Method under test | ATLAS resolver: DI equality → `SAME_DEVICE_IDENTITY`; no name similarity may confirm |
| Baseline | label similarity ≥ 0.85 on brand/model (`baseline_name_match`) |

The label does not require a human: DI equality is an official assertion. That is also the
limit — this evaluation says nothing about devices that lack a shared UDI.

---

## 2. Data actually used

| Source | Sample |
|---|---|
| openFDA UDI | 500 records, 100 per target firm, from 5 company-name searches |
| AccessGUDID | 12 re-reads (all 12 were duplicates of the openFDA records — same GUDID upstream) |
| openFDA 510(k) | 250 clearances, 50 per firm |
| MDALL | the full active identifier table streamed once (219,970,233 bytes, 1,673,926 rows); 5,512 rows with a 14-digit-shaped identifier retained; 5,005 unique DIs |
| MDALL licences | 40 licence records + 40 company records |

Bridge: 1,200 deterministically sampled GTIN candidates → 942 resolved GUDID records → 934
device pairs.

---

## 3. Results (sampled labelled pairs)

| Method | TP | FP | FN | TN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| ATLAS identity (official DI) | 934 | 0 | 0 | 400 | 1.000 | 1.000 |
| Name-similarity baseline (≥0.85) | 0 | 33 | 934 | 367 | 0.000 | 0.000 |

**Reading this honestly**

1. The identity method recovers every official-identifier pair in the sample and produces no
   false positive against the sampled negatives. This is expected — the method *is* the label —
   and is therefore a **consistency check, not a discovery**.
2. The baseline fails in two distinct ways:
   - it recovers **none** of the 934 true pairs, because Canadian MDALL publishes a *number*,
     not a brand/model, for those records: there is no label to compare;
   - it produces **33 false positives** on the hard-negative set, where the same brand string is
     used by different firms.
3. These are **sampled** pairs, not a prevalence-weighted population. No overall F1 is claimed
   for "medical device identity"; `docs/atlas/QUALITY_REPORT.md` records the coverage gaps.

The methodological conclusion is the one the project needs: **name matching is not a weaker
version of identity matching here; for the cross-market bridge it is structurally
uninformative, and where labels do exist it is actively wrong.** The correct response is the
identity infrastructure, not a better fuzzy threshold.

---

## 4. Relation census from the full run

| Relation | Count | Meaning |
|---|---:|---|
| `SAME_DEVICE_IDENTITY` (CONFIRMED) | 934 | exact DI equality across U.S. and Canadian registries |
| `SAME_PRODUCT_FAMILY` (CONFIRMED) | 185 | shared 510(k)/licence grouping or same firm + product code |
| `SAME_MODEL` (CONFIRMED) | 1 | same firm + same model string, different DI (explicitly *not* identity) |
| `POSSIBLE_MATCH` (CANDIDATE) | 44 | label similarity only; never promoted |
| `RELATED_TECHNOLOGY` (CANDIDATE) | 7 | shared FDA product code, different firms |
| `UNRELATED` (REJECTED) | 1,146 | includes 33 hard negatives (identical brand, different firm) and same-firm/disjoint-code cases |
| `UNKNOWN` | 0 | every sampled pair had enough fields to decide |

---

## 5. Negative controls and leakage checks

| Control | Implementation | Result |
|---|---|---|
| Keyword/name baseline | `baseline_name_match` on the same pairs | 0 TP, 33 FP, 934 FN |
| Wrong product match | same firm, disjoint FDA product codes → `UNRELATED` | included in the 1,146 rejections, reasons stored |
| Same-company different product | `SAME_MODEL`/`SAME_PRODUCT_FAMILY` instead of identity | 1 + 185 relations, none called identity |
| Identical-brand hard negatives | same normalised brand, different firms → `UNRELATED` | 33 pairs, reasons recorded |
| Duplicate/independence control | `canonical_key` + `is_independent`; AccessGUDID re-reads counted as duplicates | 12/12 duplicates detected, not 12 corroborations |
| Time leakage | `first_observed_at` is a fetch clock; `as_of` separates observed vs public-inferred vs unprovable | 7,254 observed; 1,452 public-inferred; 5,802 unprovable (derived/unknown) |
| Future company attribution | company validity dates are stored; legacy manufacturer names link to a group but are not treated as current filings | modelled in `Manufacturer` role/relationship, not asserted as current ownership |

---

## 6. Independent re-check

- `tools/verify_atlas.py` recomputes every confirmed pair shares exactly one DI, every payload
  hash, report-vs-database counts and the baseline arithmetic. **14/14 pass.**
- One real evidence path was opened end-to-end and is committed as
  `research/atlas/reports/examples/query_relation_confirmed.json`: two evidence records, their
  source URLs, clocks, hashes, identifiers and the shared DI.
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

---

## 8. Reproduction

```bash
python tools/run_atlas_pipeline.py          # bounded live collection + reports + verifier
python -m pytest tests/test_atlas_identity.py tests/test_atlas_evidence.py \
  tests/test_atlas_db.py tests/test_atlas_research.py tests/test_atlas_connectors.py -q
python tools/verify_atlas.py
```

Expected: 14/14 verifier checks pass; the numbers above are read directly from
`research/atlas/reports/identity_pilot.json`.
