# KNOWN_LIMITATIONS

Everything below is a statement about this release, not a plan. Where the product reports UNKNOWN,
this file explains why.

## Data and attribution

1. **Attributed Share is not accuracy.** 99.92% of collected records are attributed; only 9.79% rest
   on independent evidence or a human decision. 46.07% rest on no rule and no evidence at all.
2. **No human review has happened.** `human_reviewed` count is 0. The review workspace and the ledger
   exist and are tested, but a named human has not yet recorded a decision in this release.
3. **Attribution precision is not reliably estimated.** The pre-registered sample is 66% undecidable
   with the evidence collected so far; the interval over decidable cases is 0.772-1.000 with an AI
   reviewer. A human sample review is required before any precision claim.
4. **Retrieval coverage is UNKNOWN.** There is no independent denominator for "every FDA record that
   should have been retrieved for this organization". Attributed share of the collected sample is not
   coverage.
5. **59 organizations only.** This is a tracked roster, not the FDA universe. A missing company is
   not evidence that it has no FDA activity.
6. **Historical ownership is mostly UNKNOWN.** Four of eight recorded relations are unresolved;
   current-group counting is the default and is labelled as such. Draeger, Mindray and 54 other
   organizations have no collected corporate filing.
7. **Recalls count records, not recall events.** A recall affecting several products produces several
   records; the product counts records and says so.
8. **PMA originals and supplements are separate event types.** They are never summed into "PMA
   approvals" without showing the split.
9. **510(k)/PMA records have no publication timestamp in openFDA.** `published_at` is null there by
   rule; availability is the collection time.
10. **16 implausible event dates are quarantined** in the snapshot (manifest `data_quality`).

## Coverage

11. Snapshot-based, not live: data is as collected on 2026-11-14 (openFDA last updated 2026-11-02).
12. Out of scope: De Novo, NMPA/China, EU MDR/CE, UDI, establishment registrations, clinical trials,
    financial filings, patents.
13. OpenFDA endpoints were queried per organization; a record filed under a name nobody queried is
    not in the sample.

## Engineering and product

14. **No external user testing.** Alpha evidence is internal simulation + browser automation. Do not
    present it as user validation.
15. Chromium-only browser matrix; no visual regression baseline; no dedicated accessibility audit.
16. The alpha is a local installation. There is no hosted deployment, no Docker image verified in CI
    (the guide documents the pip flow that was actually executed), no public cloud.
17. The identity-review workspace requires a local token file; there is no multi-user identity
    provider, no role model beyond "has the token", and no per-organization authorisation.
18. Review decisions are stored in a gitignored SQLite ledger; the committed export
    (`identity_review_decisions.json`) is a snapshot for audit, not the live store.
19. Exports are CSV and Markdown only; no Excel-native or PDF report.
20. Chinese and English are the only interface languages, and the professional glossary covers the
    terms used on the screens listed in `/sources`, not every page.

## Governance

21. `DATA_LICENSES.yaml` and the licence gate are repository consistency controls, **not a legal
    opinion**. A human still owns the redistribution judgement.
22. The narrowed derived-binary exception (GOV-0005) applies only to `openfda_device` files under
    `medradar/product/snapshot/*.gz`, gzip only, <= 32 MiB, SHA-256 bound. It is not a licence
    expansion, and it does not cover any future data source.
23. No branch protection is enforced on `main` in this repository (unchanged from before this work).

## What this release does not claim

* That the data is complete, correct or up to date beyond what is stated per screen.
* That records are comparable across event types or that more records mean more innovation.
* That the product is production-ready, hosted, or validated by external users.
