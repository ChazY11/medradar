# Next Steps - Product Roadmap

Priorities are ordered by user value per unit of engineering effort, given that this repository is
maintained by a small team. Everything below builds on the delivered product; none of it re-opens the
research programme.

---

## P0 - Make the attribution trustworthy (the highest-value gap)

The product's biggest weakness is that 82% of attributed records rely on machine-proposed applicant
spellings. The data layer is right; the review workflow is missing.

1. **Attribution review tool** (`/api/attribution` already returns the full list). Add a reviewer
   screen: accept / reject / reclassify a proposed spelling, record the reviewer, timestamp and note,
   write to the registry with `review=curated`.
2. **Promotion rules with evidence**: strings that differ from a curated alias only by a legal-form
   suffix (`, Inc.`, `GmbH`, `LLC`, `B.V.` ...) can be auto-promoted with the rule recorded, cutting
   the provisional share without weakening the exact-match guarantee.
3. **Publish the provisional share** as a first-class metric on the overview, so the honest number is
   visible without opening the sources page.
4. Target: below 10% provisional records, with every remaining proposal reviewed or explicitly
   rejected.

## P1 - Product-level identity (devices, not records)

Users ask "what product is this?" and the product can currently only answer "these records".

1. Define a device identity model: 510(k) clearance → device family → PMA/supplement lineage →
   recall linkage (the recall payload already carries `k_numbers` for some records).
2. Cluster records into device families with a reviewable, deterministic rule; keep every underlying
   record and expose the membership.
3. Add a device timeline view (clearance → supplements → recalls) and product-code/specialty views
   built on device families rather than raw record counts.

## P2 - Sustained collection with the same auditability

The snapshot is manual today. The draft observatory branches (#13/#14) already solved the hard part
(append-only observation ledger), but they belong to a different product claim.

1. Keep the snapshot as the product's read model; add a **collection ledger** that records each run's
   query, response counts and hashes (the manifest already does this per run).
2. Schedule collection (weekly) with retry/backoff and an alert on anomalies (record count drops,
   schema changes, openFDA errors).
3. Publish a "changes since last snapshot" view: new records, changed records, disappeared records -
   the foundation of MONITORING (capability E).
4. Only after that, add alerts/subscriptions.

## P3 - Broaden the data source set (in order of expected value)

| Source | Value | Effort / risk |
|---|---|---|
| FDA De Novo + device classification updates | Closes a real gap in the pathway mix | Medium: no direct openFDA endpoint; needs scraping or the full download files |
| FDA UDI / GUDID | Device identity, manufacturer linkage | High volume; needs the product identity model first |
| ClinicalTrials.gov | Product pipeline evidence | Already collected by the research pipeline; adapter exists in draft branches |
| SEC filings (10-K/8-K) | Company-level context and M&A events | Out of the current data contract; stronger for ownership graph than for devices |
| NMPA / EU MDR | Non-US coverage, critical for the stated users | Currently blocked (WAF) or licence-restricted; must not be half-done |

## P4 - Analyst workflow depth

1. **PDF export** of the comparison report (the Markdown is already structured for it).
2. **Saved views and annotations** (needs a small persistence layer; keep it local-first).
3. **Full bilingual product copy** (finish the Chinese translation of methodology and warnings).
4. **Glossary and inline help** for FDA concepts (510(k) vs PMA vs supplement vs recall, device class,
   advisory committee).

## P5 - Engineering hardening

1. Move the dataset behind a small read-only index (SQLite or Parquet + DuckDB) if the corpus grows
   beyond ~1M records; the API contract should not change.
2. Add API response caching and an ETag on snapshot id.
3. Add lint/format gates (ruff/eslint) and a CI job that runs the product tests plus the browser
   acceptance walkthrough headlessly.
4. Add a snapshot-diff test: re-collect a small set and assert the manifest changes are explainable.

## Explicitly not next

* Any generative-AI narrative in the product. If AI is added, it must cite record ids and be visibly
  labelled as generated, never as the source of a fact.
* Predictive or "early signal" features sold as product capability. The research programme found no
  validated out-of-sample signal; shipping one would contradict the repository's own evidence.
* A hosted SaaS with accounts and billing: no paying user, no infrastructure budget, and it would
  distract from the data-quality work above.

---

## PRODUCT-004 follow-ups (recommended next phase)

1. **Saved briefs / workspace** — persist a brief (question, scope, snapshot, generated files) so a
   team can return to it after the snapshot changes. This needs storage and accounts; deliberately
   out of scope here.
2. **Change-aware briefs** — when DATA-001 is configured, diff two snapshots inside the same brief
   scope and add a "what changed since the last brief" section (records added, updated, retained),
   with the same evidence and limitation treatment. The current changes section already reads the
   ledger; this is a UI and diff-policy extension.
3. **More finding rules only after user testing** — e.g. family-level supplement cadence, recall
   clustering by product code, or window-normalised comparisons. Add a rule only when its threshold
   can be defended and its "does not mean" clause is written.
4. **A second data source with the same contract** — e.g. EU MDR or NMPA once a legal, stable access
   path exists, so "regulatory activity" is not US-only. Do not fake coverage in the meantime.
5. **Per-metric custom denominators** in Explain (e.g. share within a specialty rather than within
   the side) after confirming analysts need it.
6. **Translation completion** for the inherited Compare/Sources pages, replacing the explicit
   "English source text" labels.
7. **PDF generation** only if browser print proves insufficient in real distribution.
