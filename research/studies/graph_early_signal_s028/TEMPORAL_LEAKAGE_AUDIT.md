# S-028 时间泄漏审计 / Temporal Leakage Audit

**Audit date:** 2026-11-04
**Auditor role:** independent of the modelling code path where possible; every claim below is
tied to a code location or a computed artifact.
**Scope:** the S-028 historical-simulation experiment on the frozen research database.
**Verdict summary:** **the historical simulation is free of *within-experiment* future leakage**,
but it is **not** a strict point-in-time study: the knowledge clock is an *estimated*
`decision_date + 14 days` proxy and the historical database has **no** measured first-observation
time. Every claim must therefore be labelled `historical_proxy_asof`, never `observed_asof`.

---

## 0. Two clocks that must never be conflated

| clock | definition | where it exists | permitted use |
|---|---|---|---|
| `historical_proxy_asof` | `available_at = event_date/decision_date + 14 days` for 100% of the bulk lane; `first_seen_at` is a single bulk-fetch date **2026-11-01** for every historical row | frozen `research.sqlite` | **historical simulation only**, with the 14-day assumption stated |
| `observed_asof` | a genuine first-observation timestamp recorded by a running collector (`observation.first_seen_at`, `observation_origin`, `backfill_reason`) **with a short lag between publication and first capture** | `observatory.sqlite` | strict prospective evaluation |

**Correction from the independent data audit (`RELATION_AND_TIME_EVIDENCE_AUDIT.md` §2).** The Live
Observatory is **not** a clean prospective source either: only **6 of 400** observations were
captured within 1 day of publication. `observation_origin = LIVE` is a *collection-mode label*
(online collection vs backfill script), not evidence of prospective capture:
all 400 observations entered the ledger on the same day (2026-11-03), 365 of 400 (91.25%) have
`first_seen_at − published_at > 7 days`, the median lag is 65 days and the maximum is 7,613 days.
**Therefore S-028 uses no `observed_asof` data at all.** The 6 genuine prospective records are far
too few for any evaluation and are reserved for a future prospective study.

Measured evidence (from `artifacts/feasibility.json` and `entity_time_audit.json`):

- `available_at − event_date = 14 days` for **31,802 / 31,802** material events. It is a
  documented *estimate* of the bulk-lane publication lag, not a measurement.
- `first_seen_at` has exactly **1 distinct value** (2026-11-01) across the whole historical lane,
  and `as_of` likewise. They carry **zero** point-in-time information.
- The Live Observatory ledger is *separate* and materially better, but its 400 observations are
  **not** mixed into this experiment. Mixing them would silently upgrade a historical proxy to a
  prospective claim — the exact error the S-028 brief forbids.

**Consequence.** S-028 is a **historical simulation study**. This is stated in
`PRE_REGISTRATION.md` §3, in `LIMITATIONS.md`, and in every results document. No result may be
described as "validated in real time".

---

## 1. 未来事件泄漏 / Future-event leakage

**Rule enforced in code.** Every model input for an origin `t` is computed only from events
satisfying `event_date <= t` **and** `available_at <= t`:

- Panel features: `build_entry_panel` filters `history = [e for e in usable if e["day"] <= cutoff
  and e["available"] <= cutoff]` (`code/s028_lib.py`).
- Graph snapshots: `SnapshotSeries._history(t)` applies the same two-sided filter, and the
  12-month window is `(t − 12m, t]` (`code/s028_lib.py`).
- First-touch dates used by peer-entry features come from `all_history` with the identical filter.

Labels use the disjoint interval `(t, t + H]`. Because `available_at = day + 14d`, an event with
`t − 14d < day <= t` is neither a feature (not yet "available") nor a label (not after `t`). That
is a **conservative 14-day blind spot**, not a leak: information is hidden from the model, never
granted to it.

**Verification.** `code/s028_experiment.py --mode validate` reproduces the frozen cycle-2 P1
benchmark exactly (41,003 rows / 503 positives / 24 origins; per-window AP 0.137085, 0.095027,
0.100476; pooled 0.101060; persistence 0.044614). A pipeline with future leakage could not
reproduce a published, purged benchmark to <3e-7. Artifact: `artifacts/frozen_validation.json`.

## 2. 分类映射泄漏 / Taxonomy-mapping leakage

The 38 device tracks are defined by a product-code→track mapping built **with current knowledge**.
A product code that only exists after 2022 is assigned to a track as if that track category had
always existed. So:

- **This is a real structural limitation of the historical replay.** It cannot be repaired with
  the present data because no effective-dated taxonomy is committed for the whole period.
  (`research/STATE.json` records the same defect: "technology taxonomy is not versioned by
  effective date".)
- It is **not** a future-information leak into a feature *given the label rule*, because both the
  label and the features are defined through the same mapping. It *is* a historical-replay
  distortion: the measured "entry" may be an artefact of a late-created code.
- **Mitigation applied:** the label is restricted to Traditional 510(k) and original PMA, and
  `DATA_FEASIBILITY.md` quantifies how much of the lane sits on late-created codes if the mapping
  exposes that. The audit does **not** claim the mapping is historically correct.
- **Required disclosure:** any claim about "technology entry" in a specific track inherits this
  uncertainty. Per-track results are therefore reported as descriptive, never as established.

## 3. 实体映射泄漏 / Entity-mapping leakage

`companies.aliases` contains acquired subsidiaries and former names (e.g. `medtronic` includes
`COVIDIEN`/`TYCO`; `abbott` includes `ST JUDE MEDICAL`; `bd` includes `C R BARD`/`CAREFUSION`;
`stryker` includes `WRIGHT MEDICAL`/`MAKO`). Attributing a 2010 filing by "Covidien" to
"Medtronic" uses **today's** ownership knowledge.

**Quantified by the independent audit** (`RELATION_AND_TIME_EVIDENCE_AUDIT.md` §D): **84 events are
dated before the relevant acquisition completed but attributed to the parent**, and for some firms
the effect is large — **`bd`: 131 of 297 attributed events (44.11%) come from acquired aliases**;
`siemens_healthineers` 12.80%, `stryker` 5.43%, `abbott` 4.53%. For those firms, the year of
"first entry into a track" is partly determined by an **acquisition timetable**, not by a technical
entry. This is now a first-class limitation, not a footnote.

An analyst standing in 2020 could not have merged those entities. So:

- **Leak type present:** entity-identity look-ahead (a form of future knowledge about corporate
  structure), **not** label leakage.
- The direction of the bias is ambiguous: it makes the historical graph *denser and more stable*
  than it truly was, which if anything **favours** the relational hypothesis. A positive G1 result
  must therefore be read conservatively; a negative one is not rescued by this bias.
- **What is not done:** no fuzzy matching, no name-similarity inference, no inferred partnerships.
  Entity assignment is the curated `company_key` only.
- The independent quantification of this effect (alias-level first/last dates, per-acquisition
  counts) is in `RELATION_AND_TIME_EVIDENCE_AUDIT.md` §D, produced by the evidence auditor.

## 4. 关系图泄漏 / Graph leakage — the highest-risk path

The classic error is: compute centrality/degree on the **full-period** graph, then use it to
predict the past.

**Rule enforced.** There is no full-period graph object in the experiment. `SnapshotSeries`
constructs one snapshot per origin, and `features_for(cutoff, …)` can only return a snapshot
computed from `≤ cutoff` events. Every graph feature (peer entry, similarity, two-hop,
co-occurrence, centrality) is computed inside that snapshot's cache. The randomised control
(`G2`) rebuilds snapshots the same way.

**Verification.** (a) The panel builder's history filter is the same two-sided filter as §1;
(b) `SnapshotSeries._decorate` is called only from `_build(t)` / `_build_randomised` with that
snapshot's own `t`; (c) the frozen-benchmark reproduction (§1) validates the panel path end to end.
A code-level search for any full-period aggregation was performed: the only global objects are
the per-origin caches keyed by `cutoff`.

## 5. 标签同源泄漏 / Label-source leakage

The label is derived from FDA decision events (`event_date`, `available_at`, `company_key`,
`track_id`, payload `clearance_type`/`supplement_number`). The risk is using a field that is
*itself* the label, or its future derivative, as an input.

- No feature reads `payload` fields from the **label window**; the payload is parsed at load time
  only to classify an event as qualifying vs maintenance, and that classification defines the
  label — it is never a feature.
- The pair's own "first target event date" (`first_target_event_date`) is stored for lead-time
  analysis only and is **not** in any feature vector.
- `rd_company_track_novelty_share` counts novelty among events in `(t−24m, t]` only.

**Residual risk:** `event_date` is the decision date. A filing is *received* up to ~180 days
earlier (`date_received` exists in the payload but is not used). Using the decision date as both
the knowledge clock (+14d) and the event ordering is internally consistent, but a real analyst
could have seen the submission earlier. This makes the measured lead time a **lower bound** on
achievable lead time, not an upper bound — a conservative direction, disclosed here.

## 6. 训练集泄漏 / Train–test leakage (purge/embargo)

Company–track pairs are strongly autocorrelated across time, so random row splits would be
catastrophic.

**Split design enforced:**
- Expanding-window rolling origin on **calendar quarters**. Never a random split.
- **Purge:** a training example may be used at origin `t` only when
  `cutoff + H <= t`, i.e. the whole label window closed before the test window opened.
  Implemented in `eligible_training_rows` and validated by the frozen reproduction.
- **Embargo:** implicit in the purge — any row whose label window overlaps `(t, t+H]` is excluded.
- Test rows at different holdout origins are disjoint by construction; their **label windows
  overlap**, which is documented rather than hidden, and is why inference uses a
  company-clustered bootstrap rather than a row-level test.

## 7. 泄漏审计结论

| # | leak class | status in S-028 | evidence |
|---|---|---|---|
| 1 | future events in features | **controlled** | two-sided `day <= t and available <= t` filter; frozen reproduction PASS |
| 2 | taxonomy/mapping look-ahead | **present, disclosed, not repairable here** | no effective-dated taxonomy for whole period |
| 3 | entity-identity look-ahead | **present, disclosed, direction favours the hypothesis** | aliases include acquired firms |
| 4 | full-period graph statistics | **absent by construction** | per-origin snapshots only |
| 5 | label-source reuse | **controlled**; lead time is a lower bound | payload unused in features |
| 6 | random-split/purge leakage | **controlled** | quarterly rolling origin + purge, validated |
| 7 | proxy clock treated as point-in-time | **prohibited by naming and by §0** | `historical_proxy_asof` only |

**Bottom line.** The experiment can support statements of the form
"*in a historical simulation whose knowledge clock is decision-date + 14 days and whose taxonomy
and entity map are modern, the relational features did/did not add out-of-sample ranking value
under a purged rolling-origin protocol*". It **cannot** support point-in-time or causal claims.

Any future S-028 phase that reports genuine prospective evidence must use the Live Observatory
ledger's `observed_asof` records and must not be pooled with these historical results.
