# PRODUCT-004 — Known Limitations

Limitations are part of the product. These are the ones this release does **not** solve; they are
also stated inside the brief where they affect a reading.

## Data and measurement

1. **Snapshot, not a feed.** The brief describes one immutable snapshot
   (`2026-11-14T22:09:22Z-openfda`). It cannot answer "what changed since this morning". The changes
   section reflects whatever the DATA-001 ledger knows; on this deployment the ledger is not
   configured.
2. **Scope is the tracked registry.** 59 organizations are tracked; an untracked company is not
   searchable as a company, and its records are not counted. Search results say so.
3. **FDA specialty is often `Unknown`.** 2,520 of Medtronic's 3,426 window records (73.6%) carry the
   official specialty `Unknown`. The product-code table is the interpretable alternative, but it is
   a classification unit, not a market segment.
4. **Applicant is not manufacturer.** Attribution is exact applicant-string matching against a
   reviewed registry. 36.4% of Medtronic's window records rest on provisional mappings. The owner at
   the event date is unknown for 16,429 of the all-time 17,473 records (94%) because no verified
   ownership relation with an effective date exists.
5. **No publication time for 510(k)/PMA.** openFDA exposes none; `published_at` is null and the UI
   says so. First-observed time is collection time, not publication time.
6. **Media and duplicates.** Event types are counted as records; the snapshot does not deduplicate
   media, and a record may be revised by FDA. Removed-on-recheck records are retained and marked, but
   the brief's counts still count the retained row.
7. **Only FDA device sources.** De Novo, UDI, establishment registrations, EU MDR/CE, NMPA, clinical
   trials, patents, hiring, financial filings and market share are out of scope.
8. **No prediction.** Findings are deterministic descriptions of the snapshot. No forecast, score,
   ranking or causal claim is produced.

## Findings

9. **Rule thresholds are heuristics.** A 75% pathway concentration or a ±40% year change is a
   reading aid, not a statistical test. A different threshold would produce a different finding set;
   the rule and its inputs are printed so the reader can judge.
10. **Small bases produce no finding.** The rules require minimum counts. A company with few records
    gets fewer findings, not weaker claims.
11. **Year shifts use complete years only.** An explicit window with partial edge years excludes them
    from the year-change rule; the table marks them.
12. **At most two year-shift findings.** More simultaneous movements are not shown individually; the
    per-year table still contains them.

## Comparison

13. **Two to four organizations.** The comparison brief inherits the Compare engine's bounds.
14. **Shares and denominators** follow the compare engine (all tracked organizations in the same
    window for share-of-all-tracked; side totals for pathway shares). The brief states the definition
    per metric but does not provide a custom denominator UI.
15. **Coverage symmetry is binary.** It compares the set of sources that have records, not source
    completeness or FDA backfill. The per-source date table is the finer-grained view.
16. **Product-code overlap is classification overlap.** Eight shared codes for GE HealthCare and
    Philips do not establish competing products.

## Device

17. **PMA hierarchy only.** The family is the official PMA number and its supplements. 510(k)
    predicate relationships are not modelled because openFDA exposes no predicate identifier.
18. **Recall links require the official K-number field.** A recall without that field is unlinked; the
    absence of a link is not evidence that no recall occurred.
19. **Device history is all-time** and only as complete as the snapshot. A missing supplement is not
    proof that it does not exist.
20. **Candidate relations are suggestions.** They are counted separately and never promoted by this
    release.

## Product experience

21. **Bilingual coverage is complete for the new brief workflow, not for the inherited pages.** The
    organization/compare/sources pages still contain English explanatory copy in Chinese mode. The
    brief labels server warning text as the English source when it is not translated.
22. **No saved briefs, accounts or collaboration.** The URL is the record. Sharing means sharing the
    URL or exporting the files.
23. **PDF is browser print, not a generated file.** The print stylesheet is tested visually; no PDF
    library is included.
24. **Chrome/Chromium is the acceptance browser.** Firefox and Safari were not exercised.
25. **Cold start.** The first request after process start loads 91,457 events (~11 s on this host).
    The first company brief that needs the device index adds ~4 s. Later requests are fast. This is
    unchanged DATA-003 behaviour, not a new per-request cost.
26. **One new resident map.** The classification map (7,098 rows) is kept for the life of the
    process; the brief does not cache other derived structures.

## Process / governance

27. **Stacked Draft PR.** This release is based on PR #52's branch, not `main`. Merging it requires
    the upstream stack to be merged first or the PR to be rebased after the stack lands.
28. **No production deployment.** The release is verified against a local loopback server; no
    production web process, sync job or cloud configuration was touched.

## Not limitations (deliberate refusals)

* The product does not rank companies.
* It does not turn a PMA supplement into a new device or a recall into a quality rate.
* It does not state a cause for a record-count change.
* It does not generate narrative conclusions from an LLM.
