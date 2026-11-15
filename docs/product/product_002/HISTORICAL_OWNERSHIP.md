# HISTORICAL_OWNERSHIP

Phase B: a company belonging to a group **today** does not mean it belonged to that group when a
regulatory record was filed. This document defines how MedRadar separates the three questions and
what it verified.

## The three concepts

| Concept | Definition | What the product does with it |
|---|---|---|
| **Original applicant** | the exact applicant string FDA recorded on the record | always shown verbatim; never rewritten |
| **Historical owner at event time** | who controlled the filing entity when the event happened | stated only where an independent source with an effective date exists; otherwise UNKNOWN |
| **Current group** | the tracked organization the entity belongs to today | the default counting basis; always labelled as a *current-group* statement |

The product states this on the organization page, in the comparison, in the Markdown exports and in
`GET /api/ownership`. Where the historical owner is unknown, the API says `null` plus a caveat — it
never guesses.

## Verified relations

Evidence is recorded in `medradar/product/attribution/ownership.json` with the filing URL, accession,
access date and the exact quoted line (or the subsidiary name that matched).

| Relation | Organization | Entity | Effective from | Owner before | Status |
|---|---|---|---|---|---|
| REL-0001 | Medtronic | Covidien plc and subsidiaries (Covidien LP/LLC/AG, ...) | 2015-01-26 | Covidien plc (independent, NYSE: COV) | evidence-verified |
| REL-0002 | Medtronic | Medtronic MiniMed, Medtronic Vascular, Medtronic Sofamor Danek | not verified | UNKNOWN | evidence-verified (current ownership only) |
| REL-0003 | Medtronic | Tyco Healthcare (pre-2007 name) | not verified | UNKNOWN | **unresolved** |
| REL-0004 | GE HealthCare | GE Medical Systems / GE Healthcare entities | 2023-01-03 | General Electric Company (now GE Aerospace) | evidence-verified |
| REL-0005 | Philips | Philips North America LLC, Philips Medical Systems entities | not verified | UNKNOWN | evidence-verified (current ownership only) |
| REL-0006 | Philips | Philips Electronics North America | not verified | UNKNOWN | **unresolved** |
| REL-0007 | Draeger | Draeger US entities | not verified | UNKNOWN | **unresolved** (German registrant; no filing collected) |
| REL-0008 | Mindray | Mindray DS USA / Datascope | not verified | UNKNOWN | **unresolved** |

Evidence citations:

* Medtronic acquisition: Form 8-K filed 2015-01-27, Exhibit 99.1 "Medtronic Completes Acquisition of
  Covidien" — "DUBLIN, Ireland - January 26, 2015 ... successfully completed the previously announced
  acquisition of Covidien plc (NYSE: COV)".
* Medtronic subsidiaries: Form 10-K (fiscal 2026) Exhibit 21 lists "Covidien LP", "Covidien llc",
  "Medtronic MiniMed, Inc.", "Medtronic Vascular, Inc.", "Medtronic Sofamor Danek USA, Inc.".
* GE HealthCare spin-off: Form 10-K (fiscal 2025) — "On January 3, 2023, the General Electric Company,
  which now operates as GE Aerospace, completed the spin-off of GE HealthCare". Exhibit 21.1 lists the
  GE Medical Systems entities and Datex-Ohmeda, Inc.
* Philips: Form 20-F (fiscal 2025) group-company table lists "Philips Medical Systems (Cleveland),
  Inc." and "Philips North America LLC".

## What the product now shows

The organization page has an ownership block with:

* the counting-basis banner ("counts on this page use the CURRENT GROUP …");
* verified vs unresolved relation counts;
* per-relation historical split: records filed **before** the effective date (owned by a predecessor)
  vs **on or after** it;
* the caveat for each relation, and an explicit UNKNOWN statement for unverified ones.

Measured examples (snapshot, 5-year comparison window 2021-01-01 to 2025-12-31):

| Organization | Records in window | Records from predecessor entities | Curated Share |
|---|---|---|---|
| Medtronic | 3,426 | 196 (Covidien-family strings) | 20.7% |
| GE HealthCare | 493 | 493 (every record in the window predates the 2023 spin-off) | 100% |

GE HealthCare is the clearest case in the product: **under current-group attribution all 493 records
in the window are counted under GE HealthCare, even though every one of them was filed while the
business was part of General Electric.** Selecting the *original-registrant* basis returns **0
records** for that window — the honest answer, and a much better teaching moment than a hidden
aggregation rule.

## Comparison basis switch

`GET /api/compare?...&basis=original_registrant` (and the UI selector) excludes records whose
applicant string belongs to an acquired/predecessor entity. The basis is printed in the comparison
payload, the Markdown export and the CSV provenance header, so an exported report cannot be mistaken
for the other basis. For Medtronic in the same window the switch changes 3,426 -> 513 records; the
product does not pick one for the user.

## What is deliberately not claimed

* A complete historical group structure. Eight relations are recorded; four are unresolved.
* Legal succession for brands after acquisition (e.g. a brand sold to a third party is not tracked).
* Ownership at the *exact* event date for relations without a verified effective date: those stay
  UNKNOWN even when current-group attribution is shown.
* Any historical claim for Draeger, Mindray or the other 54 organizations: no jurisdiction filing was
  collected for them in this release.
