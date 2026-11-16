# PRODUCT-004 — Evidence Contract

This document is the contract between the brief and the record. It applies to the JSON API, the
on-screen brief and both exports. A violation is a product defect, not a documentation issue.

## 1. Chain of custody

```
openFDA source record
  → immutable snapshot 2026-11-14T22:09:22Z-openfda (sha256 per file in snapshot.json)
  → attributed Event (exact applicant spelling → reviewed registry decision)
  → filter + count (one row = one record)
  → brief section / finding / comparison metric
  → official_url back to accessdata.fda.gov
```

Every brief carries:

* `scope.snapshot.id`, `collected_at`, `openfda_last_updated`, per-file sha256;
* `scope.counting_rule` (bilingual) and `scope.event_types`;
* `scope.ownership_basis` and `scope.review_filter`;
* `generated_at` (UTC) and `rules_version` (`brief-findings-v1`);
* `evidence.sources` (per-source records and date range);
* `evidence.appendix.rows` and the CSV itself.

No brief is computed from a paginated page, a cached screen or a previous export. `/api/brief`
recomputes from the loaded dataset on every request.

## 2. Record-level evidence

Each cited or recent record exposes at least:

| Field | Meaning |
|---|---|
| `official_id` | the FDA identifier as printed on the official page (K number, PMA plus supplement) |
| `official_url` | the accessdata.fda.gov URL for that record |
| `event_type` | 510(k), PMA original, PMA supplement or recall — never merged |
| `event_date` | FDA decision date (510(k)/PMA) or firm recall-initiation date |
| `published_at` | only when the source states it (recalls); `null` for 510(k)/PMA by rule |
| `first_observed_at` | snapshot collection time; not a publication time |
| `available_at` | `published_at` if known, otherwise `first_observed_at` |
| `attribution_verification` | evidence-verified / rule-verified / proposed / rejected / unattributed |
| `attribution_verified` | true only for evidence-verified or human-reviewed mappings |
| `record_state` | ACTIVE or a retained lifecycle state such as MISSING_ON_RECHECK |

The evidence drawer displays all four time fields separately. The brief never describes a record as
"new" because MedRadar collected it today; the first-observed time is labelled as collection time.

## 3. Counting rules (binding)

1. One record is one row in the FDA source dataset.
2. Only attributed records count as an organization's activity. Unattributed and rejected records are
   reported in the audit and are not added to a company.
3. Event types are never merged. A PMA supplement is a change to an approved device; a recall is a
   safety action.
4. Per-year calculations use complete calendar years only. Partial years at the edges of an explicit
   window are shown, marked and excluded from the year-change rule.
5. Shares of nothing are `null`, never `0%`.
6. Counts use the current group by default. The owner at the event date is reported separately;
   `UNKNOWN` is reported, never counted as zero.
7. Comparison sides share one window, one event-type set, one ownership basis and one review filter.
   Shares use all tracked organizations in the same window as the denominator only where the compare
   engine does so.
8. A count is not a measure of innovation, quality, market share or R&D intensity.

## 4. Finding contract

A finding may be displayed only if all of the following are present:

* a stable `id` and a `category` (`finding` or `caution`);
* a bilingual `title`, `statement` and `cannot_conclude`;
* `basis.rule` (the threshold, in words), `basis.inputs` (the exact values used) and
  `basis.rules_version`;
* `evidence.record_count` and, where records exist, up to five cited records with official URLs;
* a `drilldown` that reproduces the set (event browser URL or device page);
* deterministic computation: the same snapshot and scope produce the same finding set and inputs.

Rules in this release (`brief-findings-v1`):

| Rule | Fires when | Category |
|---|---|---|
| `pathway_concentration` | top event type ≥ 75% and records ≥ 40 | finding |
| `recall_dominant_window` | recall share ≥ 50% and recalls ≥ 10 | caution |
| `activity_shift_<type>` | latest complete year vs mean of previous two changes ≥ ±40%, both ≥ 10, records ≥ 20; at most two | finding |
| `pma_family_scale` | top PMA family in the window has ≥ 20 supplement decisions | finding |
| `product_family_overlap` | comparison: product-code set overlap | finding |
| `coverage_asymmetry` | a source has records on one side only, or first event year differs ≥ 3 years | caution |
| `pathway_mix_divergence` | comparison: a pathway's share differs ≥ 25 pp, both sides ≥ 20 records | finding |
| `specialty_not_stated` | official `Unknown` + not-in-dictionary ≥ 25% and records ≥ 50 | caution |
| `verification_asymmetry` | comparison: curated-share difference ≥ 10 pp | caution |
| `provisional_attribution` | provisional share ≥ 25% and records ≥ 50 | caution |

The rule set is deliberately small. If a rule does not fire, the brief states that no finding rule
fired; it does not invent one.

## 5. Comparison / Explain contract

For every comparison metric (`records_total`, `type.<event_type>`, `specialty.<id>`,
`product_code.<CODE>`):

* the value is computed by the same filter as the brief and the event browser;
* the definition states the unit and the denominator;
* the explain response returns the numerator, denominator, event types, window, ownership basis,
  review filter, up to 20 recent records per side and a URL that applies identical filters;
* a difference is never described as advantage, innovation or quality;
* the brief states whether source coverage is symmetric even when it is.

## 6. Device contract

* A device identity comes from its own FDA application; a MedRadar identifier is internal and is shown
  beside the official identifier.
* A PMA family is the official PMA number plus every supplement that carries it; it is not proof of a
  commercial product line.
* A supplement is a version of an approved device, never a new device.
* A recall is linked only via its official K-number field. No link is not evidence that no recall
  occurred; unlinked recalls remain in the unlinked browser.
* Candidate relations are deterministic suggestions. They are never presented as established and are
  never counted with confirmed relations.

## 7. Change ledger contract

* `not_configured` — no ledger exists: the brief says it cannot report changes and makes no claim.
* `no_changes` — the ledger is configured and records zero changes: the brief says it observed no
  published changes. It never converts an old record into an update.
* `available` — items come from DATA-001 with their own observed time; an item is not an FDA decision
  date.
* `unavailable` — reading failed; the error is stated.
* Device briefs state that the ledger is organisation-scoped and not reported there.

## 8. Export contract

Markdown exports contain: title, question, window, event types, snapshot id and collection time,
counting rule, executive measures, pathway table with definitions, per-year table, technology tables,
device table (company), comparability and explainable measures (comparison), findings with cited
records and rules, changes, sources, official links, limitations, appendix note. Device exports carry
the official application history and linked recalls.

Evidence Appendix CSV columns:

`section, metric, organization, official_id, event_type, event_date, published_at, first_observed_at,
available_at, official_url, product_code, fda_specialty, device_name, applicant_name,
attribution_review, attribution_verification, record_state, snapshot_id`

`section` is `window_records`, `side:<key>`, `device_history` or `finding:<id>`. The appendix includes
every window record and the records cited by findings; device appendices include the application and
every supplement.

## 9. Prohibited claims

The brief must never state or imply:

* that more records mean more innovation, quality or market strength;
* that a PMA supplement is a new device or a commercial launch;
* that recall counts are a failure rate or a ranking of safety;
* that an applicant string is the current legal manufacturer;
* that a candidate relation is established;
* that a missing record means no activity;
* that a change in records identifies a cause;
* that MedRadar is real-time or that discovery time is publication time;
* any number that is not reproducible from the snapshot and the stated filters.
