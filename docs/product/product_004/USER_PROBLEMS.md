# PRODUCT-004 — User Problems and Prioritisation

Primary persona for this release: **Medical Device Competitive Intelligence Analyst**. Job to be
done: *"Before a strategy meeting, research one competitor (and its devices) and hand over a defensible
brief."* Secondary persona: the manager who receives the brief and asks "where does this number come
from?".

## 1. Ranked problems

| # | Problem | User cost | Evidence in the product | Priority |
|---|---|---|---|---|
| P1 | No research object: no question, no scope, no output | Every analysis is re-assembled by hand; nothing can be shared or re-run | Window exists only on Compare; org page is all-time | P0 |
| P2 | No findings: the analyst must eyeball 91k records | Hours of reading to reach three defensible facts | No findings anywhere; org page ends with distributions | P0 |
| P3 | Technology areas collapse to "Unknown" | Cannot answer "where is this company active technically?" | Medtronic specialty chart: 11,522 / 17,473 Unknown | P0 |
| P4 | Comparison cannot be interrogated | "Why is this different?" needs manual filter reconstruction | Compare cells are static; no definition / records route | P0 |
| P5 | Exports are not deliverables | Re-editing before it can be sent | `organization.md` lacks scope, date, findings, limits | P1 |
| P6 | Provenance precedes analysis on the company page | Two screens of scrolling before any activity view | 7,310 px mobile page; counts repeated | P1 |
| P7 | Homepage is a data-governance dashboard | First-time user cannot see what to do | Eyebrow "Product 001"; QA metrics first | P1 |
| P8 | Device intelligence not reachable from company analysis | Analyst has to know device ids exist | Org page has no PMA-family section | P1 |
| P9 | Partial Chinese; no mobile language switch | Chinese analysts get mixed-language output | English callouts on zh org page; toggle hidden < 768 px | P2 |
| P10 | Internal tools share top-level navigation | Slower orientation | "Identity review" beside "Compare" | P2 |
| P11 | Cold start ~11 s | First-load distrust | `/api/meta` cold 10.8 s | keep (do not regress) |

## 2. Explicit non-problems (keep as-is)

* Evidence drawer, four-time semantics, official URLs, snapshot provenance.
* Attribution verification vocabulary and the refusal to rank companies.
* Compare warnings; device confirmed/candidate distinction; data-status honesty.
* CSV of the filtered set.

## 3. PRODUCT-004 MVP (scope selected)

1. **Intelligence Brief workspace** (`/brief`) for three modes: Company, Compare, Device. Structured
   inputs (organization, comparison set, window of 3/5/10 complete calendar years or explicit dates,
   event types), URL-state so a brief is reproducible and shareable.
2. **Server-computed brief** with: scope and counting rule, executive snapshot, regulatory activity by
   pathway with definitions, technology areas (FDA specialty *and* official product-code families),
   device intelligence (PMA families, confirmed/candidate distinction), recent activity with the four
   times, **evidence-backed findings**, changes since the previous snapshot (or an explicit
   "not configured / no changes observed"), and evidence + limitations.
3. **Findings** from a small, transparent rule set (6 rules maximum, each with the records that
   produced it, a "what this does not mean" statement, and a route to the records). No prediction, no
   generated narrative, no claims of causality.
4. **Explain this difference** for every comparison metric: definition, numerator, denominator,
   window, filters, and the records behind it — data from the same computation as the brief.
5. **Exports**: Company Intelligence Brief (Markdown), Competitor Comparison Brief (Markdown),
   Evidence Appendix (CSV, one row per supporting record). Print stylesheet so the on-screen brief can
   be saved as PDF by the browser (no new dependency).
6. **Experience**: task-first home, "Intelligence brief" in primary navigation, company page CTA +
   product-code technology table, compare page route into the brief and per-row explanation, mobile
   language toggle. Existing screens keep their data semantics.

## 4. Out of scope for this round

New data collection, sync changes, new databases/services, AI-generated narrative, accounts,
real-time feeds, PDF library, new design system, company ranking, causal claims. No change to
production deployment.

## 5. Success criteria

* An analyst can go from an empty screen to a downloaded Company Brief for Medtronic, 2021–2025,
  without visiting another page.
* Every number in that brief reproduces from `/api/brief` and from `/api/events` with the same filters.
* At least three findings are produced for the acceptance cases, each with records and a
  "cannot conclude" statement.
* GE HealthCare vs Philips comparison states its coverage asymmetry and can explain at least one
  difference down to official records.
* A PMA family investigation distinguishes the official application hierarchy from candidate
  relationships and from unlinked recalls.
* 100% of existing `tests/product` tests still pass; new brief tests cover the invariants.
