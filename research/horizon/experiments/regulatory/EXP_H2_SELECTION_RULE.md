# EXP-H2 — SELECTION RULE (written before any pair was inspected)

Status: **pre-registered**. This rule was fixed by the collection design (which
sources and which slices were pulled), before any FDA<->Canada pair was looked at.
Nothing below was tuned after seeing a verdict distribution.

## Question

Can a US GUDID device record and a Canadian MDALL record be shown to describe
**the same real product**, using only official identifiers or explicit official
fields?

## Boundary of the experiment

* FDA side: `accessgudid` records emitted by
  `CONNECTORS/regulatory/accessgudid.py` (320 records, October 2026 GUDID monthly
  release, selection rule recorded in `DATASETS/regulatory/accessgudid/COUNTS.json`).
* Canada side: `canada_mdall` records emitted by
  `CONNECTORS/regulatory/canada_mdall.py` (174 records: 60 licences,
  65 devices, 49 device identifiers; selection rule in
  `DATASETS/regulatory/canada_mdall/COUNTS.json`).
* Both sides are restricted to the same five pre-declared firms:
  **Medtronic, GE HealthCare, Philips, Dräger, Mindray**.

## Pair construction

A pair is (one GUDID record, one MDALL record). Pairs are only generated when
**at least one signal fires**; the empty-signal cross-product is not enumerated
(it carries no information about sufficiency).

Signals, each recorded independently per pair:

| id | signal | definition |
|---|---|---|
| S1 | exact name | normalised GUDID `brand_name` equals normalised MDALL `trade_name` or `licence_name` |
| S2 | model in both | a normalised model/catalogue token from GUDID also appears as an MDALL `device_identifier` or inside MDALL text |
| S3 | same firm | both records are attributed by their source to the same one of the five firms |
| S4 | official identifier | any official identifier value is equal on both sides **in the same scheme** |
| S5 | name tokens overlap >=2 | two or more non-stopword tokens shared and not covered by S1 |

## Verdict rule (fixed in advance)

* `CONFIRMED` — **only** if S4 fires: a shared official identifier in the same
  scheme. Name, model or firm agreement is never sufficient.
* `REJECTED` — when an explicit official field contradicts sameness: different
  firm attribution (S2 fires but S3 does not), or an official date range that
  makes the two records impossible to be the same marketed device.
* `UNKNOWN` — everything else. This includes the strongest non-identifier case
  (S1 ∧ S2 ∧ S3 all fire) and is the correct verdict for it.

An LLM opinion is not a gold standard and is not used anywhere in this experiment.

## Hard negatives (constructed deliberately, not sampled)

Each row carries `construction_rule` naming how it was built:

* `HN1_same_brand_different_device` — S5 or S1-token overlap with a differing
  head noun (e.g. "INFUSION PUMP" vs "INFUSION PUMP SET").
* `HN2_same_model_token_different_firm` — identical model token, S3 false.
* `HN3_same_family_different_device` — shared product-family keyword, different
  device noun.
* `HN4_subsidiary_vs_parent` — same corporate family, legally distinct
  manufacturer names on the two sides (e.g. "MEDTRONIC MINIMED" vs
  "MEDTRONIC OF CANADA").

## Expected outcome, stated before running

Given that GUDID identifies devices by UDI-DI and MDALL by Health Canada's own
licence/device/identifier numbers, S4 is expected to fire **zero** times. If that
holds, the deliverable is a *negative* identity result with a measured signal
table, not a matched corpus — and no pair may be promoted to CONFIRMED.
