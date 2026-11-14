# Core User Journeys

These are the workflows the v1 workbench is built around. Each journey lists what the user does,
what the product shows, where the evidence comes from, and what the product refuses to claim.

---

## Journey 1 - Competitive scan of one company (primary)

**Persona:** competitive-intelligence analyst.
**Goal:** understand a competitor's recent FDA regulatory activity before a strategy meeting.

1. **Open the product.** Overview states what data is covered (59 organizations, 91,457 records,
   snapshot timestamp), what it cannot answer, and three starting actions.
2. **Search.** Type "medtronic" in the global search (`/` focuses it). Results are organizations,
   not raw FDA applicant strings; the match field and record count are shown.
3. **Organization page.** Identity block (legal name, ticker, country, registry review state),
   metric tiles (records, 510(k), PMA originals + supplements, recalls), coverage per source with
   date ranges, data-quality notes, records per year, specialty distribution, recent records.
4. **Regulatory events tab.** Full, filterable record list for that organization, including the
   attribution state of every row.
5. **Evidence.** Clicking a row opens a drawer with the official identifier, the official FDA URL,
   the four separate time fields, the attribution decision (verbatim applicant string + basis), the
   verbatim source fields, and the collection provenance.
6. **Export.** "Export CSV" downloads exactly the filtered set; "Export brief" downloads a Markdown
   organization brief with counts, coverage, attribution detail and official record links.

**What the product refuses to claim:** that a high record count means innovation, that a missing
source means no activity, or that an applicant-name match is a legal-entity fact. The organization
page states the attribution composition and flags provisional decisions.

---

## Journey 2 - Two-company comparison with sourced output (primary acceptance flow)

**Persona:** analyst asked "how does Medtronic compare with GE HealthCare in the last five years?"

1. **Open Compare** (or the "Compare Medtronic and GE HealthCare" action on the overview).
2. **Selection and window.** Two to four organizations; window of 3/5/10 complete calendar years;
   event types optionally narrowed. One window and one counting rule apply to every side.
3. **Warnings first.** Before any numbers, the page shows the comparability warnings raised by the
   API: coverage mismatch, pathway mix, recall share, unclassified records, provisional attribution,
   partial years, small base.
4. **Sides.** Each organization shows its identity, totals by event type, and per-source coverage
   with date ranges - so a reader can see whether a difference is activity or coverage.
5. **Matrices.** Records by event type (with share of all tracked organizations), by FDA medical
   specialty, by device class, and records per complete calendar year.
6. **Export.** "Export report (MD)" produces a Markdown comparison containing the snapshot, window,
   counting rule, disclaimer, warnings, coverage table, matrices, per-year table, source list and
   example official record links - ready to paste into a decision memo.

**What the product refuses to claim:** any ranking, any inference that one company is "more
innovative", or any comparison where the coverage and pathway differences are not stated first.

---

## Journey 3 - Verify a claim and take the evidence away

**Persona:** anyone about to cite MedRadar in an internal document.

1. **Filter the event browser** by organization, event type, date range, category, attribution
   review state or a text query. Filters live in the URL so the view is shareable.
2. **Open the evidence drawer** from any row (or deep-link `/events/<official id>`, e.g.
   `/events/K260306`).
3. **Check the four times.** Event date (what happened), published-at (only when the source states
   it - null for 510(k)/PMA by rule), first observed by MedRadar (snapshot time), available-at
   (conservative bound). The drawer says explicitly that openFDA publishes no publication time for
   510(k)/PMA.
4. **Check the attribution.** Verbatim applicant string, basis (legal name / brand / subsidiary /
   historical name), review state (curated or provisional).
5. **Open the official record.** The FDA accessdata URL is one click away and is printed in every
   export.
6. **Take the data.** CSV with one row per record including official URL, snapshot id and collection
   time; Markdown brief or comparison report with the same caveats as the screen.

---

## Journey 4 - Understand the limits and the coverage boundary

**Persona:** a new user, or a reviewer evaluating whether to trust the product.

1. **Open Sources & coverage.** Snapshot manifest (id, collection time, openFDA last-updated,
   request count, file hashes), sources of record with endpoints and date coverage, collection audit
   per organization, attribution review counters, the list of unattributed applicant strings,
   explicitly rejected look-alike names.
2. **Read the four time concepts** and the out-of-scope list (De Novo, NMPA, EU MDR, UDI,
   clinical trials, financial filings, patents, hiring).
3. **Reproduce.** The page prints the exact commands to re-collect, re-curate the registry, serve
   and test the product.

---

## Journeys intentionally deferred

| Journey | Why deferred |
|---|---|
| Continuous monitoring / alerts on new records | Requires a durable observation ledger and scheduling; the draft observatory branches are the starting point (see NEXT_STEPS). |
| "Find every company active in this specialty" across the full FDA registry | v1 tracks 59 organizations; the collection scope is explicit and the audit shows what is outside it. |
| Device-level product profiles and dedupe | Requires a product identity model (device lineage), which is a separate design problem. |
| AI-written analysis summaries | Deliberately excluded: the product refuses to make AI the source of a fact. |
| Accounts, saved watches, collaboration | Not needed to prove the core workflow; would add authentication and persistence cost. |
