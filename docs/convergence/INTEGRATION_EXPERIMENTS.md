# INTEGRATION_EXPERIMENTS — EXP-C1 … EXP-C5

Measured results of the integrated pipeline. Every figure below is produced by
`tools/convergence/run_experiments.py` from the staging database and the frozen
export; the machine output is `research/convergence/reports/integration_experiments.json`.
The numbers in the fenced block are checked against that file by
`tools/convergence/check_report_consistency.py` in CI, so this page cannot drift
from the data.

```bash
python tools/convergence/run_integration.py --fresh --run-id <id>
python tools/convergence/run_experiments.py
python tools/convergence/check_report_consistency.py
```

## Headline figures

<!-- convergence:numbers
c1_input_records=5884
c1_converted=966
c1_degraded=4918
c1_rejected=0
c1_declared_source_fields=22
c1_fields_with_atlas_home=10
c1_fields_preserved_losslessly=12
c1_fields_dropped_silently=0
c2_mdall_identifiers=49
c2_mdall_gtin14_valid=0
c2_gudid_udi_di=320
c2_overlap=0
c2_confirmed_cross_border=0
c3_distinct_evidence=5822
c3_evidence_versions=5884
c3_repeat_observations=62
c4_records=5822
c4_usable_for_lead_time=1989
c4_not_usable=3833
c4_without_first_observation=1332
c4_public_before_event=90
c4_date_conflicts=51
c5_cited_items=134
c5_uncited_items=0
-->

---

## EXP-C1 — Schema-conversion fidelity

**Question.** Does every input record have an explainable conversion outcome, with
nothing silently lost?

| outcome | records |
|---|---|
| converted cleanly | 966 |
| converted with recorded warnings | 4,918 |
| **rejected** | **0** |
| **total read** | **5,884** |

| field accounting | count |
|---|---|
| declared source fields | 22 |
| mapped to a real ATLAS field | 10 |
| preserved losslessly under `normalized.horizon` | 12 |
| **dropped silently** | **0** |

**Date changes.** No record's dates were altered. Two intentional refusals:

- 1,394 records have no `first_observed_at`; it stays empty
  (`observation_basis = unknown_no_observation_log`) instead of being filled with
  an event date or the import time.
- 90 records have `source_public_at` **before** `event_at`, which is surfaced as a
  warning rather than "fixed", because guessing which clock is wrong would be
  fabricating data.

**Identifier changes.** 38 distinct source schemes were mapped; only one changes
meaning by value (`hc_mdall_device_identifier`). On this sample **0** identifiers
were promoted to `di` and **0** GTIN-shaped values were rejected for a bad check
digit — because the sample contains no GTIN-form MDALL value at all (see EXP-C2).

**Licence status changes.** None widened: 827 `public_domain`, 3,891
`open_licence`, 1,104 `open_no_explicit_licence` survived unchanged. 1,104 records
carry `licence_restricted` so they cannot be mistaken for publishable.

**Warning classes** (a record can carry several): `classification_carried_as_identifier`
3,438; `quality_flags_preserved_without_atlas_equivalent` 2,178;
`first_observed_at_unknown` 1,394; `source_public_at_precedes_event_at` 90;
`clock_ordering` 1 (a genuine 1896 Canadian patent, flagged as implausibly old by
ATLAS's inherited check — real, not an error).

---

## EXP-C2 — Cross-source identity consistency (HORIZON side)

**Question.** Can the HORIZON US–Canada sample support an official cross-border
device identity, and why did EXP-H2 report zero?

| measurement | value |
|---|---|
| HORIZON MDALL `device_identifier` values | 49 |
| … that are 14-digit GTIN-shaped | **0** |
| … with a valid GS1 check digit | **0** |
| HORIZON GUDID distinct `udi_di` | 320 |
| intersection MDALL identifiers × GUDID UDI-DIs | **0** |
| identifiers promoted to `di` in staging | **0** |
| confirmed `SAME_DEVICE_IDENTITY` relations in staging | **0** |

**Conclusion.** EXP-H2's "zero confirmed" is arithmetically forced by its sample:
with no GTIN-form identifier on the Canadian side there is nothing for the official
identifier signal to fire on. It is a **coverage** result, not a refutation.

**Binding.** This experiment reports only what the integrated HORIZON sample can
support. ATLAS's 934 confirmed pairs were measured on the full 1.67-million-row
MDALL table and are reconciled in `IDENTITY_RECONCILIATION.md` from frozen inputs;
they are deliberately **not** reproduced here, because the integration artefact
does not carry that table.

---

## EXP-C3 — Evidence de-duplication

**Question.** Are duplicates separated by layer without deleting real records?

| layer | measurement |
|---|---|
| records read | 5,884 |
| distinct evidence ids | 5,822 |
| evidence versions appended | 5,884 |
| **repeat observations of the same record** | **62** |

**Layer 1 — record identity.** 62 records are emitted more than once by the export
(the same PMA/establishment record collected once per firm slice). ATLAS appends a
*version* rather than a second record, and the staging log keeps **every
occurrence** (`occurrence` 1…n), so neither the duplicate nor its provenance is
lost. This also means HORIZON's manifest record count is **62 higher** than the
number of distinct underlying records — a real data-quality finding, not a
conversion artefact.

**Layer 2 — entity identity.** 307 scholarly publication records collapse to
**60 distinct DOI keys**; all 60 are seen by more than one aggregator, one DOI by
**6** aggregators. Counting those 307 records as independent findings would
inflate the literature corpus roughly 5×. The identity layer collapses them before
any independence claim is made.

**Layer 3 — event identity.** 606 procurement records; **0** notices in this sample
name more than one supplier. The party is part of the event key by construction, so
co-awarded suppliers cannot be deleted — but with zero multi-party notices in this
sample the guard is **untested by this data**, and that is stated rather than
hidden. It is covered by a unit test instead.

**Layer 4 — relation identity.** 672 relations, 672 distinct
`(from, to, type, method)` keys: no relation was double-counted.

**Patent families.** 2,228 patent publications, 499 distinct PCT family keys,
**0** families containing more than one publication. Publications of one family are
neither merged nor double-counted; in this sample there simply are no multi-country
siblings, so family grouping is measured but not exercised.

---

## EXP-C4 — Historical-time observability

**Question.** Which records can support a historical claim, and with which clock?

| clock | present | share |
|---|---|---|
| `event_at` | 4,191 | 72.0% |
| `source_public_at` | 3,563 | 61.2% |
| `first_observed_at` | 4,490 | 77.1% |
| `fetched_at` | 5,822 | 100% |

| clock relation | records |
|---|---|
| event before public | 1,619 |
| **event equals public** | **370** |
| public before event | 90 |
| event only | 2,112 |
| public only | 1,484 |
| no dates | 147 |

- **Usable for a lead-time claim** (event clock *and* day-quality publication
  clock): **1,989** records (34.2%).
- **Not usable for historical analysis**: **3,833** (65.8%).
- **No observation clock at all**: **1,332** — these can never be counted as
  "observed by" any date, which is why `as_of` queries never use `event_at` as a
  substitute.
- **Cross-source publication-date conflicts**: **51** DOIs carry different
  `source_public_at` values from different aggregators (e.g. `2021-07-03` vs
  `2021-10-01`). Both assertions are preserved; the integration does **not** pick
  the earlier one, because picking the earliest date manufactures lead time.

**Interpretation.** Only about a third of this corpus can support a time-anchored
research claim at all, and the 370 records whose event and publication dates are
identical cannot support lead-time reasoning even though both clocks are present.
A study that reports lead time over the full corpus would be using clocks that do
not exist.

---

## EXP-C5 — Query and reproducibility

**Question.** Can the whole pipeline run from a clean checkout, offline, and
reproduce?

| requirement | result |
|---|---|
| runs from a clean working directory | yes |
| depends on agent scratch state | no |
| needs a GPU | no |
| needs a paid API | no (`network_used = false`) |
| needs credentials | no |
| staging database rebuilt from scratch | yes (`--fresh`, 60.98 MB) |
| all six demo queries render | yes, 0.684 s total |
| query results carrying a source citation | **134** cited items, **0** uncited |
| reproducible across runs | identical `integrity`/`import`/`dedupe`; stable result digest |
| database migration safe | new database only; ATLAS research DB never opened |
| key results have an independent recomputation program | yes — `tools/convergence/verify/` (see `INDEPENDENT_VERIFICATION.md`) |

**No performance optimisation was made at the expense of evidence correctness.**
The pipeline favours full-record preservation and validation over speed, which is
why the staging database is 61 MB for 5,884 records.

---

## What these experiments do **not** show

- They do not show that the corpus is representative: it is a 6,492-record declared
  sample across 24 sources, and 608 of those records are excluded on licence
  grounds.
- They do not show a cross-border device identity from HORIZON data alone (EXP-C2).
- They do not show that the multi-party procurement guard works on real
  multi-party data, because this sample has none.
- They do not show that patent family grouping works, because this sample has no
  multi-country family siblings.
- They do not evaluate performance or scale beyond 5,884 records.
