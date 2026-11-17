# Limitations and negative findings

This file is part of the deliverable. A system that only reports what it can do is not
auditable; what it cannot do, and what it got wrong, has to be as visible as what it got right.

## 1. What the live data actually supports

The first batch produced 8,592 observations across five enabled sources. The shape of that
evidence is itself a finding:

* **Regulatory evidence dominates.** Most (company, topic) cells are supported by FDA records,
  because an FDA clearance is a machine-readable record with an applicant and a product code.
* **Vendor capability statements are rare.** Of the 36 vendor documents fetched, only a handful
  name a launched product, and *none of them* states an ICU-monitoring capability. So the
  `PRODUCT_HAS_REPORTED_CAPABILITY` count is **0 for every company** in the current graph.
  That is not a bug: the model gets the number right by having nothing to say. It will become
  non-zero when a vendor publishes a release about a monitoring product, and the code path that
  produces it is covered by tests and by the isolated-fixture acceptance run.
* **Publications correlate weakly with companies.** A PubMed affiliation is enough for
  `DOCUMENT_MENTIONS_COMPANY` (research activity) and never enough for a product claim.
* **GE HealthCare has no vendor-press evidence** because its newsroom refuses automated access.
  Its technology branches are built from FDA and publication evidence only. The product says so
  rather than hiding it.

## 2. Query precision

* The PubMed queries are topical searches, not filters. Some returned records are only
  adjacent to ICU monitoring (a surgical case report, a dermatopathology case). They are
  classified `TOPIC_RELATED` or dropped by the scope gate, but they existed in the candidate
  set. Query sets are the weakest link in precision and are versioned configuration, not code.
* Crossref relevance ranking over a recent-deposit window is better than cursor-paging
  everything, but a query still returns *something*. Without the per-adapter scope gate the
  ledger would fill with unrelated papers; with it, roughly a third of the Crossref candidates
  were rejected as out of scope.
* FDA records are queried by 21 ICU-monitoring product codes. A device cleared under a code
  outside that list does not appear, even if it is a patient monitor. This is a scope decision,
  not a claim of completeness.

## 3. Identity and resolution

* Alias resolution is exact/prefix only. There is no fuzzy matching, on purpose: a false merge
  silently poisons the graph. The cost is that unusual applicant spellings stay unresolved.
* The two broad GE legal names ("General Electric Co.", "General Electric Company") are held at
  candidate confidence (0.6) because that name also files non-medical devices. Records under
  those names produce `CANDIDATE_PRODUCT_RELATION`, never `COMPANY_HAS_PRODUCT`.
* PubMed publishes a PMID and Crossref publishes a DOI, so the same paper seen through both
  APIs usually has **no shared identifier string**. Cross-source correlation therefore runs
  through the topic relation. `OFFICIAL_IDENTIFIER_MATCH` is implemented and tested, but on the
  current corpus it is empty. Storing the DOI as a secondary identifier is the obvious next
  step and is not done yet.

## 4. Time semantics

* Detection latency is only exact when the source states a timestamp with a time of day. Only
  Philips press releases do (JSON-LD `datePublished`). Every other source yields date-precision
  or no publication time, so the exact-latency figure rests on a small sample and the
  approximate figure is reported separately.
* A record whose publication date is a year or a year-month is anchored to the first day of
  that period **for ordering only**, in the graph. The record itself keeps the period.
* openFDA publishes no per-record publication timestamp for 510(k)/PMA rows. `source_published_at`
  is therefore absent for those records by design; the decision date is `event_date`.
* The knowledge-time view is honest but unflattering: because everything in this first load was
  discovered on one day, a knowledge-time view before that day is empty. The product says so
  instead of backdating.

## 5. The AI layer

Measured topic F1 on the 0.6B model is 0.18 (see [`AI.md`](AI.md)). It is not usable as a
classifier, and the system does not use it as one. It is kept as an optional candidate
generator because the harness — not the model — is the deliverable, and because a future
larger or fine-tuned model drops into the same gate.

## 6. Operational limits that are known and accepted

* One scheduler process per radar directory (a cross-platform file lock enforces it). There is
  no distributed coordination.
* `advance` re-materialises the graph per observation; a full first load of ~8.6k observations
  takes minutes, not seconds. Incremental cycles are fast because only new versions are pending.
* The graph is derived. Deleting `graph.db` is supported and safe; it requires `advance` to run
  again before the pages have data.
* The read-only API opens a connection per request. That is fine at this scale and keeps the
  serving process incapable of writing, but it is not a pooling design.
* The production deployment is **not** part of this change. No systemd unit, no timer and no
  production data path was modified; see [`CHANGE_REQUEST.md`](CHANGE_REQUEST.md).

## 7. Preserved negative findings from earlier work

The repository's earlier research is not overwritten by this delivery:

* the temporal company-technology graph study (S-028) did **not** establish that public
  evidence gives reliable early warning at the resolution tested — this system does not claim
  that it now does; it claims only that it can collect, version, relate and show the evidence;
* the local-LLM research (PR #19/#20) found that small models underperform rule layers on this
  domain — the measured F1 of 0.18 above is consistent with that finding, not a contradiction;
* the observatory work found that a "no change" cycle must be a first-class result — that
  requirement is preserved here as an explicit outcome and as a test.
