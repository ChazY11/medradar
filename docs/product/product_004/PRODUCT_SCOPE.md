# PRODUCT-004 — Product Scope

**Release:** `feat/product-004-intelligence-workbench` (stacked on PR #52)
**Base:** `origin/feat/data-003-runtime-reliability` @ `c23429f`, which contains production commit
`7415382` (DATA-003 Correction-1). The PR stack #46 → #52 is still open; `main` does not contain
PRODUCT-001/002/003 or DATA-001/002/003, so branching from `main` would have removed the entire
product. This decision is recorded in `DESIGN_DECISIONS.md`.

## 1. Problem this release solves

The product can answer "show me records" but not "brief me on this competitor, and let me defend it".
It had no research object, no findings, no way to interrogate a comparison, and no deliverable. The
audit (`PRODUCT_AUDIT.md`) documents the evidence for each gap.

## 2. Primary persona and job

**Medical-device competitive-intelligence analyst.** Job: *before a strategy meeting, research one
competitor and its devices, and hand over a sourced brief that survives fact-checking.*

Secondary: the manager who receives the brief and asks "where does this number come from, and what
does it not mean?"

## 3. In scope (implemented)

| Capability | What ships |
|---|---|
| Research question | `/brief` workspace: Company / Compare / Device modes, organization or PMA identifier, window of 3/5/10 complete years or explicit dates, event-type selection. Full scope is encoded in the URL so a brief is reproducible and shareable. |
| Company Intelligence Brief | Scope and counting rule; executive tiles; pathway table with definitions; per-year chart; technology areas (FDA specialty **and** official product-code families); PMA families from the PRODUCT-003 device model; recent activity with the four time fields; findings; changes; evidence; limitations. |
| Competitor Comparison Brief | Same computation as `/api/compare`; explicit coverage assessment; comparability verdict; 21 explainable measures; pathway/specialty/product-code metrics; per-year charts; warnings; shared/exclusive product-code finding; verification asymmetry. |
| Explain this difference | Drawer per comparison metric: definition, numerator, denominator, window, event types, ownership/review filters, per-side record lists with official links, and a link to the identical event-browser filter. |
| Device brief | Official PMA hierarchy: original approval, every supplement, linked recalls (K-number only), confirmed vs candidate relations, findings and limitations. |
| Evidence-backed findings | Six deterministic rules: pathway concentration, recall-dominant window, year-on-year record shift, PMA family scale, specialty-not-stated, provisional attribution. Each carries the rule, inputs, cited records, a "what this does not mean" statement and a reproduce link. |
| Deliverables | Company brief Markdown, comparison brief Markdown, device brief Markdown, Evidence Appendix CSV (one row per supporting record, official URL, verification state, snapshot id), print stylesheet for browser PDF. |
| Experience | Task-first home, "Brief" in primary navigation, organization page CTA + product-code table, comparison CTA + explain link, product-code filter in the event browser, mobile language switch, bilingual brief workflow. |
| Data honesty | Every brief carries snapshot id, collection time, counting rule, source coverage, attribution verification, ownership-at-event-time limits, relationship confirmation states and "questions this cannot answer". Change ledger absence is stated, never rendered as "no news". |

## 4. Explicitly out of scope

No new data collection or sync changes; no database, queue, cache, cloud service, model or LLM; no
accounts, saved briefs or collaboration; no PDF library (browser print only); no company ranking, no
innovation score, no causal claim; no change to the PRODUCT-002 review service or DATA-003 runtime.
No production deployment or PR merge.

## 5. What "done" means

* **G1 User value:** a first-time analyst reaches a sourced company brief in one screen and one click
  after choosing the target; the acceptance run records the exact operation count.
* **G2 Workflow:** question → evidence → analysis → brief is one continuous route ending in files.
* **G3 Evidence:** every brief number equals the dataset/compare computation (tested), and every
  finding cites official records with URLs.
* **G4 Honesty:** pathway, time, identity, coverage, ownership and relationship limits are on the
  brief itself; findings state what they do not mean.
* **G5 Experience:** task-first home, consistent navigation, bilingual primary workflow, mobile
  layout with no overflow, print layout.
* **G6 Regression:** existing `tests/product` suite and the repository test suite stay green; no API
  removed; new fields are additive.
* **G7 Performance:** brief generation is a bounded read of already-loaded data; no new resident
  structure larger than the 7,098-row classification map (~2 MB) and no per-request index rebuild.
* **G8 Acceptance:** scenarios A–D executed in real Chromium with screenshots, downloads and a JSON
  report; no fabricated user research, retention or conversion numbers.

## 6. Non-goals that were considered and rejected

* A chat interface. The task requires clear structured interaction; a chat box would hide the scope.
* Auto-generated narrative. Every sentence about data is a template over computed values or an
  explicit methodological statement.
* A new Compare page. The existing comparison engine is reused; the brief adds explanation and
  output around it.
* More than six finding types. The chosen rules were selected for analytical usefulness and low
  false-claim risk; adding more would trade quality for feature count.
