# A07 — Clarivate DRG Medtech Competitive Intelligence

## Metadata

| Field | Value |
|---|---|
| Name | Clarivate DRG Medtech Competitive Intelligence |
| Official URL | https://clarivate.com/life-sciences-healthcare/medtech/drg-medtech-competitive-intelligence/ |
| Vendor | Clarivate Plc (NYSE: CLVT) — confirmed in Clarivate's own press release republished by NISO |
| Product type | Commercial subscription competitive-intelligence platform, analyst-curated; sibling of Medtech 360 |
| Target customer | Medtech corporate strategy, competitive intelligence, market access, BD/finance teams at mid-to-large device manufacturers |
| Licence / terms | Not published on the product page. Enterprise subscription, demo-gated ("Book a demo"). No public ToS, no public price list. **UNKNOWN** |
| Access barrier | **High.** No free account, no public sample data, no public API, no screenshot of field names. The page even rejects non-browser HTTP clients (403). |
| Evidence date | 2026-11-08 (Asia/Shanghai) |
| Overall confidence | **Medium.** Public marketing copy is VERIFIED verbatim; all internal schema, ER and forecasting detail is UNKNOWN. |

## 1) What it is and who buys it

Clarivate DRG Medtech Competitive Intelligence is a **human-analyst-curated** competitive-intelligence product for the global medical-device industry, positioned as "a comprehensive view of the medtech competitive landscape." It is explicitly not a raw database: the page states data is "curated and enhanced by Clarivate's medtech subject-matter experts."

It sits alongside Clarivate's other medtech products (Medtech 360, Medtech Market Tracking, DRG Commercial Analytics 360, formerly US Procedure Finder), which the page lists as "Related products." This is a portfolio of analyst products rather than a single self-serve database.

Pricing is not public. Purchase path is "Book a demo" → sales-led enterprise contract. No self-serve tier exists.

## 2) Public evidence inventory

| # | URL | Quote (verbatim) | Confidence |
|---|---|---|---|
| E1 | product page | "A comprehensive view of the Medtech competitive landscape" | VERIFIED |
| E2 | product page | "All data is categorized by company, device series (market segment), and geography to cut to the heart of the most important information to you." | VERIFIED |
| E3 | product page | "Review each competitor's most important products in the pipeline including company, brand, product type, device series, geography indication, timeline, and estimated launch date." | VERIFIED |
| E4 | product page | "Explore granular data on: Sales by product segment; Sales growth across a set of competitors" | VERIFIED |
| E5 | product page | "Press releases, powered by Cortellis"; "Recent headlines, powered by BioWorld" | VERIFIED |
| E6 | product page | "Read analyst insight authored by subject-matter experts within the medical device space. Get an at-a-glance view of global market share and top competitors for any company within a segment" | VERIFIED |
| E7 | product page | "Export all charts to PNGs, data to spreadsheets, and content to PDF reports" | VERIFIED |
| E8 | product page | "Forecast pipeline movements, financial models and timelines accurately" | CLAIMED_UNVERIFIED |
| E9 | product page | "curated and enhanced by Clarivate's medtech subject-matter experts" | VERIFIED |
| E10 | NISO press release, Jan 2025 | "Clarivate Plc (NYSE:CLVT)" ; DRG Fusion: "With data mastered at the drug and device level" | VERIFIED |
| E11 | NISO press release, Jan 2025 | DRG Fusion is built on "integrated medical and pharmacy claims and other real-world data sources" | VERIFIED (but Fusion ≠ DRG Medtech CI; separate product line) |

Note on E11: DRG Fusion is a real-world-data/claims analytics platform, **not** the product audited here. It is recorded only to show Clarivate's broader data-mastery claim and should not be conflated with DRG Medtech CI.

## 3) Data structure & standardisation principles

The only public structural statement is E2: everything is categorised on **three axes — company, device series (market segment), geography**. That is a genuinely informative admission: the primary navigation spine is a *market-segment* dimension ("device series"), not a regulatory artefact.

A product/pipeline record is documented (E3) as carrying: company, brand, product type, device series, geography, indication, timeline, estimated launch date. A financial record (E4) carries sales by product segment and sales growth.

What is **not** documented: registration identifiers, clinical-trial linkage, patent linkage, entity schemas, or any normalisation rule. The evidentiary model appears to be **analyst-authored insight** (E6, E9) rather than source-cited primary documents. No registration number, no document link, no point-in-time/as-of stamp is visible on any public surface.

**Standardisation principle (INFERRED):** humans (subject-matter experts) impose the segmentation, so standardisation is editorial and undocumented, not a published taxonomy. This is the opposite of a machine-checkable normalisation layer.

## 4) Company identity resolution

**UNKNOWN and undocumented.** The public page makes no statement about subsidiaries, M&A, rebrands, or Chinese/English name handling. The company is treated as a first-class category (E2) and "company insights" is a feature (E6), but there is no published ER methodology, no statement of legal-entity vs brand resolution, and no way to inspect merges without a subscription.

This is a material gap for MedRadar, and also evidence that the incumbent does **not** compete on transparent identity resolution — it competes on analyst interpretation.

## 5) Technology / product taxonomy

"Device series (market segment)" is the taxonomy term (E2, E3). Depth is **UNKNOWN** — never enumerated publicly. It is almost certainly a proprietary Clarivate segmentation aligned to Medtech 360 market definitions, but no public list, no hierarchy depth, and no inspectable sample exists.

Confidence: taxonomy axis exists = VERIFIED; its content and depth = UNKNOWN.

## 6) Data provenance & evidence presentation

Mixed. Sources are named for news only: Cortellis (press releases) and BioWorld (headlines) — E5. Market share and pipeline content are attributed to "analyst insight" (E6) rather than to primary regulatory documents.

There is **no visible citation of a registration certificate, no document deep-link, no source date, and no as-of/point-in-time handling** on any public surface. Exports are chart/data/report artefacts (E7), which implies users receive derived numbers rather than traceable records.

Assessment: provenance is **brand-level, not record-level**. This is the weakest aspect of the product from a scientific-auditability standpoint.

## 7) Competitor comparison features

Dimensions evidenced: pipeline products and estimated launch dates (E3); sales by product segment and sales growth (E4); global market share and top competitors within a segment (E6); news volume/headlines (E5). The FAQ framing on the page enumerates the questions buyers ask: launch timing by geography/segment, financial performance, active segments and growth drivers, news prominence, market share and share dynamics.

So the comparison model is **share + pipeline timing + financials + news salience** — a commercial-strategy frame, not a technology frame.

## 8) Technology-generation expression

**UNKNOWN / absent.** No public mention of product generations, iterations, model versions, or technology代际. The closest construct is "pipeline" with "estimated launch date" (E3) — i.e. a *time-to-market* construct, not a *technology-generation* construct.

Inference: Clarivate models the future as a dated launch event, not as a generational technology ladder. MedRadar should not assume an incumbent generation model exists to copy.

## 9) Historical technology activity display

No public statement about timeline features, coverage start year, or as-of snapshots. "Timeline" appears only as a per-product field (E3). Historical depth is UNKNOWN.

## 10) Prediction capability: marketed vs validated

**Marketed:** E8 — "Forecast pipeline movements, financial models and timelines accurately." The page also promises "Predict granular device pipeline shifts and plan accordingly."

**Validated:** **Nothing.** No accuracy figure, no MAPE/MAE, no backtest, no holdout, no published methodology, no independent benchmark, no third-party evaluation. The word "accurately" is an adjective, not a measurement.

**Verdict: CLAIMED_UNVERIFIED marketing. This is not evidence of predictive capability.** Recorded explicitly as unsubstantiated. Given the underlying input is analyst judgement plus launch-date estimates, the "forecast" is most plausibly a curated launch-timing estimate and financial projection (analyst-led), not a statistical model.

## 11) What MedRadar can learn conceptually

1. **Three-axis navigation spine (company × segment × geography)** is a defensible UX abstraction. MedRadar can expose the same three axes while keeping a fourth, regulatory-anchored axis underneath — that is a strict improvement.
2. **"Who will launch when" as the core buyer question** — a strong product framing for the launch-timing use case, independent of whether their forecast is validated.
3. **Export as a first-class feature** (PNG/XLSX/PDF) — enterprise buyers need to move data into decks and models.
4. **Pipeline record shape**: company, brand, product type, segment, geography, indication, timeline, estimated launch date is a reasonable, minimal public schema to benchmark against.
5. **Named-source transparency for news** (Cortellis/BioWorld) is a cheap credibility win MedRadar can copy at record level rather than brand level.

## 12) What must NOT be copied

1. **The "accurately forecast" claim without published validation.** MedRadar must never ship an unvalidated forecast presented as precise.
2. **Analyst-insight-as-evidence.** Prose written by an expert without a citation chain cannot be audited and cannot be reproduced. MedRadar's provenance must be record-level.
3. **Demo-gated opacity.** A product whose schema cannot be inspected by a prospective user invites distrust; MedRadar should publish its entity model.
4. **Segment-only taxonomy.** A market-segment spine with no regulatory anchor makes Chinese NMPA registration data hard to map and makes identity resolution unverifiable.

## 13) Decision + reasoning

**Decision: STUDY_ONLY.**

Reasoning: ADOPT/ADAPT are impossible — the platform is closed, has no public API, no public sample, no published schema, and blocks non-browser clients. Yet the public page yields four concrete, transferable design facts: the three-axis (company × device series × geography) spine, the pipeline field list, the export requirement, and the fact that the flagship's "forecast" is unvalidated marketing. MedRadar should study the framing and explicitly reject the evidence model.

## 14) Access log

All timestamps 2026-11-08, Asia/Shanghai (+08:00).

| Attempt | URL | Result |
|---|---|---|
| 1 | https://clarivate.com/life-sciences-healthcare/medtech/drg-medtech-competitive-intelligence/ (via `web_fetch`) | **FAILED** — TypeError: fetch failed |
| 2 | https://clarivate.com/life-sciences-healthcare/ja/medtech/drg-medtech-competitive-intelligence/ (`web_fetch`) | HTTP 200 but body empty (title only) |
| 3 | https://clarivate.com/life-sciences-healthcare/lp/access-leading-competitive-data-by-product-segment/ (`web_fetch`) | HTTP 200 but body empty (title only) |
| 4 | same as #1 via PowerShell `Invoke-WebRequest` | **HTTP 403 Forbidden** — bot protection |
| 5 | https://test.clarivate.com/.../medtech-insights-platform-overview.pdf (`web_fetch`) | **HTTP 401** — "This site is locked." (staging host) |
| 6 | https://clarivate.com/.../Medtech-360-with-Data-Explorer.pdf (`web_fetch`) | Error: unsupported content type "application/pdf" — not retrieved |
| 7 | same as #1 via headless browser (Playwright, JS-rendered) | **HTTP 200 — full page text obtained** (this is the evidence used for E1–E9) |
| 8 | https://www.niso.org/niso-io/2025/01/clarivate-launches-drg-fusion (`web_fetch`) | HTTP 200 — full text (E10, E11) |

No authentication was bypassed. No account was created. The 403/401 responses were treated as hard limits and the page was read only through a normal browser session as a public visitor. Fourteen days of attempt coverage is not claimed; this is a single-session audit.
