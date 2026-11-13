# A09 — CMOP (CMO In Your Pocket)

## Metadata

| Field | Value |
|---|---|
| Name | CMOP — CMO In Your Pocket |
| Official URL | https://www.cmoinyourpocket.com/ |
| Vendor | RKPROD ("© 2026 RKPROD — CMO In Your Pocket") |
| Product type | Self-serve SaaS competitive-intelligence platform: patent / clinical-trial / regulatory / publication monitoring with an LLM analyst layer; horizontal across pharma, MedTech and IVD |
| Target customer | Life-sciences teams: regulatory affairs, strategy/market entry, R&D/IP monitoring, marketing. Explicitly "Pharma, MedTech & IVD" |
| Licence / terms | **Public pricing published.** Free €0; Pro €79/mo (€69/mo annual); Ultra €199/mo (€179/mo annual). Separate /privacy, /terms, /security pages exist. |
| Access barrier | **Lowest of the seven.** Transparent tiers, free tier exists, public technology page, free signup without credit card. (Not used for this audit — no account created.) |
| Evidence date | 2026-11-08 (Asia/Shanghai) |
| Overall confidence | **High for packaging and architecture** (unusually candid public tech page); **low for data-model quality** (no schema, no taxonomy, no ER detail). |

## 1) What it is and who buys it

CMOP is a **self-serve, low-price, horizontal** competitive-intelligence tool for life sciences. Its pitch: "CMOP gives Life Sciences teams a unified view of patents, clinical trials, FDA filings, and publications — with AI that connects the dots across 15+ sources in real time."

It is the clear **price disruptor** in this set: while Clarivate, NextDevice, GBI and Joinchain are demo-gated enterprise contracts, CMOP publishes a €0 / €79 / €199 ladder and a free tier limited to "1 competitor tracked, 1,000 enrichment tokens/month." It is aimed at small teams and startups, not at large-market-access departments.

Its centre of gravity is **patents and publications**, with FDA clearances as one tracked event type — i.e. it is an IP/regulatory monitoring tool that also covers devices, rather than a device-native analytics platform.

## 2) Public evidence inventory

| # | URL | Quote (verbatim) | Confidence |
|---|---|---|---|
| E1 | https://www.cmoinyourpocket.com/ | "CMOP — Competitive Intelligence for Pharma, MedTech & IVD" | VERIFIED |
| E2 | homepage | "a unified view of patents, clinical trials, FDA filings, and publications — with AI that connects the dots across 15+ sources in real time" | VERIFIED |
| E3 | homepage | "Enter a company name, domain, or ticker. CMOP finds subsidiaries, brand names, and products automatically." | CLAIMED_UNVERIFIED |
| E4 | homepage | "Our 24/7 pipeline collects from 15+ sources — patents, trials, FDA, publications. Everything normalized, enriched, and indexed." | VERIFIED (design statement) |
| E5 | homepage | Free "€0 forever" / Pro "€79/mo" or "€69/mo billed annually" / Ultra "€199/mo" or "€179/mo billed annually" | VERIFIED |
| E6 | homepage | Free tier: "1 competitor tracked", "1,000 enrichment tokens/month", "AI chat: 50 tokens per query" | VERIFIED |
| E7 | homepage | "USPTO, EPO OPS, ClinicalTrials.gov, FDA 510(k), PubMed, SEC EDGAR, CMS Medicare, NICE, HAS" | VERIFIED |
| E8 | https://www.cmoinyourpocket.com/technology | "Automated connectors to 15+ authoritative data sources including PubMed, ClinicalTrials.gov, FDA, EUDAMED, USPTO, EPO, Google Patents, Google News, SEC EDGAR, and national HTA agencies (NICE, HAS, IQWiG, CMS)." | VERIFIED |
| E9 | /technology | "Content-hash based deduplication prevents duplicates across collection runs. Conflict resolution via upsert strategies ensures data is always up to date without loss." | VERIFIED |
| E10 | /technology | "Large language models (Claude, GPT-4o) provide contextual summaries, competitive insights, and natural-language Q&A over your intelligence data. Multi-model routing optimizes for quality and cost." | VERIFIED |
| E11 | /technology | "RESTful API with OpenAPI documentation. All platform features are accessible programmatically" | VERIFIED (claim of existence; docs not public) |
| E12 | /technology | "PostgreSQL for structured relational data with full-text search capabilities. Redis for task queuing, caching, and real-time job orchestration" | VERIFIED |
| E13 | homepage | "15+Data Sources / 2M+Documents / < 24hUpdate Cycle / 99.9%Uptime" | CLAIMED_UNVERIFIED |
| E14 | homepage | "Join 200+ Life Sciences teams" | CLAIMED_UNVERIFIED |
| E15 | homepage | Testimonials attributed only by role — "VP Regulatory Affairs · IVD Manufacturer", "Head of Strategy · MedTech Scale-Up", "Patent Analyst · Top 10 Pharma" | CLAIMED_UNVERIFIED (anonymous, unverifiable) |
| E16 | homepage | "SOC 2 Type II", "GDPR Compliant", "HIPAA Ready" | CLAIMED_UNVERIFIED (no certificate/auditor named) |

## 3) Data structure & standardisation principles

The site does not publish a schema. What is inferable:

- The **primary entity is the competitor/company**, entered by "company name, domain, or ticker" (E3). This is a *company-first* model, unlike NextDevice/DevicePro (product-first) or MedVantage (submission-first).
- **Document types are the second axis**: patents, clinical trials, FDA filings, publications, HTA decisions, news (E7, E8). So records are heterogeneous "documents" attached to a company.
- Normalisation is described as "Everything normalized, enriched, and indexed" (E4) and, mechanically, as **content-hash deduplication + upsert conflict resolution** (E9).

Critical distinction: E9 describes **de-duplication**, not **entity resolution**. Content-hash dedup removes byte-identical or near-identical copies across collection runs; it does not decide that "Roche Diagnostics" and "F. Hoffmann-La Roche AG" are one firm. CMOP's ER is claimed only in marketing prose (E3) and nowhere mechanistically described.

There is **no product entity**: no product master, no registration record as a first-class object, no product-code taxonomy. "FDA 510(k)" appears as a *document/event source*, not as a normalised device record.

## 4) Company identity resolution

Claim (E3): "Enter a company name, domain, or ticker. CMOP finds subsidiaries, brand names, and products automatically."

This is the full extent of the public documentation. Specifically absent:

- No statement of legal-entity graph construction, no parent/subsidiary hierarchy, no M&A/rebrand handling.
- No mention of Chinese/English name pairs or transliteration — despite claiming MedTech/IVD coverage, the source list is entirely US/EU (USPTO, EPO, ClinicalTrials.gov, FDA, EUDAMED, NICE, HAS, IQWiG, CMS) with **no NMPA/China regulatory source**.
- No merge/split audit trail, no confidence score, no correction workflow.

**Verdict: marketing-only claim. CLAIMED_UNVERIFIED with no supporting mechanism published.** The presence of a ticker-based entry point and SEC EDGAR implies the operative identity anchor is the **listed-company ticker**, which works for public companies and degrades badly for private device firms and Chinese subsidiaries — precisely the segment MedRadar cares about.

## 5) Technology / product taxonomy

**No taxonomy is published.** No device classification, no product hierarchy, no 赛道/segment model. Searches are semantic ("Search by concept, not keywords") and the AI layer does concept matching (E10), which is a *retrieval* strategy, not a *classification* strategy.

For MedRadar this means CMOP offers **no taxonometric precedent at all** — it is a text-retrieval product over regulatory documents. That is a fundamentally different information architecture.

## 6) Data provenance & evidence presentation

Better than average on source naming, weaker on record-level traceability:

- Sources are named individually and specifically (E7, E8) — including EUDAMED, IQWiG, Google Patents. This is genuine specificity, not hand-waving.
- The AI is positioned as returning **"cited answers"** ("Ask strategic questions... Get cited answers in seconds"; "returns cited, accurate intelligence — not hallucinations"). Citation-on-answer is the stated contract.
- No statement about as-of/point-in-time versioning, record versioning, or retrieval date display.
- No statement of what happens when a source changes or is withdrawn.
- "Not hallucinations" is a **claim**, and no evaluation/benchmark of citation accuracy is published anywhere.

Provenance is therefore **answer-level (citations attached to LLM output)**, not **record-level (a structured record with a source document and date)**.

## 7) Competitor comparison features

Evidence is thin. The site shows:
- A "Competitors 24 / Patents 1,847 / Trials 312 / FDA Clearances 89" dashboard counter (illustrative).
- Semantic search across concept with facet counts ("rapid sepsis diagnostics | Patents (14) FDA (3) Trials (8)").
- Real-time alerts on patent granted / trial update / FDA clearance.
- "Interactive Dashboards — Real-time digest, trend visualization, and drill-down views across publications, clinical trials, patents, regulatory events, and reimbursement decisions" (E-page /technology).
- Weekly executive digest email; AI-assisted PPTX export.

So comparison dimensions are **document counts and event streams per competitor** — volume and recency, not share, price, or performance. There is no competitive benchmarking of product capability.

## 8) Technology-generation expression

**Absent, and arguably structurally impossible.** With no product entity, there is nothing to attach a generation to. Patent families and priority dates are the closest proxy but are not presented as generations.

## 9) Historical technology activity display

Patents, trials and publications are inherently historical, and "trend visualization" plus "real-time digest" are claimed. But **coverage start dates are not published**, and no timeline/snapshot model is described. Given the pipeline is "collected every 24 hours," the platform is plausibly **forward-collecting only** — meaning historical backfill depth is unknown and may be shallow for older records.

This is an important caution: a 24-hour cron collector is not a historical archive.

## 10) Prediction capability: marketed vs validated

**Marketed:** nothing explicit. The site says "AI-powered competitive analyst", "Ask strategic questions", "cited answers", "trend visualization". It does **not** claim to forecast markets or predict competitor launches.

**Validated: nothing.** Not even a claim to validate.

However, two adjacent claims deserve scrutiny because they are the kind that get repeated as if validated:
- **"not hallucinations"** (accuracy of LLM answers) — CLAIMED_UNVERIFIED, no benchmark, no eval set, no error rate.
- **"99.9% Uptime"** (E13) — CLAIMED_UNVERIFIED, no status page cited.

**Verdict:** no prediction claim to debunk; and no accuracy evidence for the AI layer either. The AI is a retrieval-and-summarise layer over documents, and should be described as such.

## 11) What MedRadar can learn conceptually

1. **Transparent public pricing** (€0/€79/€199) is a legitimate competitive weapon against demo-gated incumbents — it signals confidence and lowers evaluation cost. MedRadar should publish a price ladder.
2. **Explicit source enumeration** (naming EUDAMED, IQWiG, HAS, NICE individually) builds more credibility than "15+ sources" alone. Enumerate, don't tally.
3. **Citation-on-answer as the AI contract** — every LLM output must carry its sources. This is the right interface contract for MedRadar's analyst-facing features.
4. **API-first with OpenAPI docs** (E11) — treating the API as a first-class product, not an afterthought.
5. **Modular architecture discipline** (PostgreSQL relational + Redis queue + isolated AI workers with rate limiting/backoff) is a reasonable reference architecture for a small team.
6. **Content-hash dedup + upsert** as the cheap first line of data hygiene — necessary but not sufficient.

## 12) What must NOT be copied

1. **Calling de-duplication "entity resolution."** Hash dedup is not identity resolution; conflating them is the exact failure mode this program must avoid.
2. **Ticker-anchored company identity.** Anchoring on SEC tickers systematically fails for private companies, Chinese subsidiaries, and pre-IPO device firms — i.e. most of the medtech universe.
3. **Token-metered AI pricing** ("1,000 enrichment tokens/month", "AI chat: 50 tokens per query"). It makes cost unpredictable for the user and incentivises shallow queries; it also caps the analytical depth MedRadar needs.
4. **Anonymous role-only testimonials** and unverified SOC 2 / "HIPAA Ready" badges as trust signals.
5. **Absence of a product entity.** A document-centric model cannot support product generations, competitor product matching, or share analysis.
6. **No China/NMPA source** while claiming MedTech coverage — a coverage claim broader than the source list.

## 13) Decision + reasoning

**Decision: STUDY_ONLY.**

Reasoning: ADOPT/ADAPT impossible (closed SaaS, no data export rights, no public schema; the API exists but requires a paid account and the OpenAPI docs are not public). Study value is concentrated in **commercial packaging** (public price ladder, free tier, self-serve onboarding) and **AI-interface discipline** (cited answers, API-first). Its data model is the weakest of the seven for MedRadar's purpose and its ER claim is unsupported; it should not be treated as a design reference for structure or identity resolution.

## 14) Access log

All timestamps 2026-11-08, Asia/Shanghai (+08:00).

| Attempt | URL | Result |
|---|---|---|
| 1 | https://www.cmoinyourpocket.com/ (`web_fetch`) | **Timeout after 30 000 ms** (first attempt) |
| 2 | http://www.cmoinyourpocket.com/ (`web_fetch`) | Error: cross-origin redirect to https not followed automatically — retried against https |
| 3 | https://www.cmoinyourpocket.com/ (`web_fetch`, retry) | **HTTP 200 — full page text obtained** (evidence E1–E7, E13–E16) |
| 4 | https://www.cmoinyourpocket.com/technology (`web_fetch`) | **HTTP 200 — full page text obtained** (evidence E8–E12) |

No account was created. No `/register` or `/login` was accessed. No API call was made (no key). Named `/privacy`, `/terms`, `/security` pages exist and were **not** fetched (not needed for the questions asked); licence terms therefore recorded as "public pricing known, ToS text not read".
