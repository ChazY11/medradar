# Competitive audit: what the commercial platforms actually sell

Produced 2026-11-21 by 43 parallel research agents; 39 returned evidence-backed findings
(1,037 facts, 579 distinct open sources, 39 with hand-verified endpoints). Raw output:
[`evidence/competitive_audit_2026-11-21.txt`](evidence/competitive_audit_2026-11-21.txt).

Every claim below was checked against a live page or endpoint. **Prices are marked
unverified** wherever the vendor publishes none — which is every vendor except Obsidian,
PatSnap and one Citeline product.

## The one-sentence finding

**Not one of the audited platforms structures the FDA engineering document corpus, and
almost all of them resell data that is already public.** The differentiation in this market
is not access to data; it is the mapping layer that turns identifiers into one entity graph.

## What each platform actually holds

| Platform | What it really sells | Device-level engineering data? | Public-source dependence |
|---|---|---|---|
| Clarivate DRG Medtech CI / Medtech 360 | market size and 10-year forecasts, hospital purchase-order SKU pricing, competitor pipeline, analyst notes | no | high — its report catalogue (11,799 items, 2,034 medtech) is readable through a WordPress REST endpoint with no key |
| Clarivate Cortellis (CRI) | regulatory documents plus human summaries, per-jurisdiction | **no** — its own numbers: 310K+ documents / 81 jurisdictions, but device side only 79K documents / 75 jurisdictions, approval packages back to **2013** only (drugs 1997) | high — 293,906 of the 375,378 events MedRadar already has |
| GlobalData Medical Devices | 250+ market models, 235,002 procedure codes, US hospital SKU panels | no | **it labels its own Clinical Trials / Marketed Products / Patents datasets "Proprietary Data: No"** |
| Evaluate MedTech | broker-consensus forecasts, deal comparables, segment sales | no | market shell is rebuildable; the forecasts are human consensus, not a model |
| Citeline Meddevicetracker / Medtech Insight | structured product/company/event/catalyst records plus journalism | no | **its own Data Trackers page states "Data derived from FDA.gov. Updated weekly"** — and its 510(k) tracker was **archived in 2026-05, De Novo in 2026-09** |
| IQVIA MedTech | claims, procedure volume (950 procedures × 45 countries), RWE services | no | claims and procedure volume are contract-licensed; that layer is genuinely uncopyable |
| Definitive / AcuityMD / MedScout | provider targeting, procedure volume, payer mix, affiliations | **no — zero hits for 510(k)/PMA/recall/MAUDE** in their exposed schemas | Medicare-derived volumes are public via data.cms.gov; Open Payments is public |
| PatSnap | patents; **"Synapse" is biopharma, not devices** | no — 60 `/synapse/*` endpoints, zero device ones; one Beta MCP has a device search with company-level patents only | Google Patents JSON returns 123,797 US catheter results with no key |
| GreyB / Dolcera | claim charts, FTO, landscape reports as deliverables | claim-element level, per matter | **Google Patents `/xhr/query` returns landscape aggregates free** — the aggregation layer is commodity |
| Obsidian | regulatory change monitoring with an audit-traceable chain | no | 850–6,700 official sources, all public originals |
| RegDesk / RAPS / Emergo / NAMSA | RIM platform / trade media / consultancy tools | no | — |
| NavaX / SyneticX / Intuceo | AI engines and consulting wrapped around other data | no | none holds a device event layer |

## What they charge, where a number exists

| Vendor | Published price | Note |
|---|---|---|
| Obsidian | $3,000/yr single jurisdiction; $6,000/yr database; $16,000 regulatory mapping; **$2,900/month managed monitoring** | the only medtech-adjacent vendor with a real price list; priced per *jurisdiction × industry* |
| PatSnap | Starter free 10,000 credits/90 days; **Pro from $100**, 1 credit = $0.01 | credit-metered, no subscription |
| Dolcera IP Author | $4,800/yr drafting, $9,590/yr bundle | the tooling half only; the judgement half is per matter |
| Evaluate | one disease report at **$16,275** | a report, not platform access |
| GlobalData | £1,000 is a site-wide placeholder (447M rows priced the same as 10K rows) | treat as no price |
| everything else | **unverified** | no public price page; sales-gated |

## Where the actual moat is

Four layers, and only the last two are worth building:

1. **Raw public records** — commodity. openFDA alone: MAUDE 26,849,547; UDI 5,182,695;
   registrationlisting 337,446; 510(k) 176,683; PMA 57,518; recall 59,705; enforcement 40,535;
   classification 7,103. All keyless.
2. **Aggregation and search over those records** — already commoditised; a free third-party
   front end serves the same corpus with an MCP endpoint.
3. **Human judgement sold by the matter** — claim charts, forecasts, analyst notes. Real, but
   it is labour, not a data asset, and it does not scale with code.
4. **The identity join** — device → predicate → clearance → UDI-DI → MAUDE failure → patent
   family → grant → payer. **Nobody assembles this.** Every segment is public; the map is not.

MedRadar's defensible position is layer 4, and this pass built two of its edges: the UDI/DUNS
spine (5,258,157 devices, 12,536 labeler DUNS, measured) and the MAUDE narrative corpus.

## Three findings that change our own plan

1. **Our snapshot is 1.4 % of one endpoint.** MAUDE alone is 26,849,547 reports; the committed
   snapshot holds 375,378 events in total. "Our data is public so it is not a moat" was the
   wrong framing — the problem is depth, not exclusivity, and depth is obtainable.
2. **Citeline archived its 510(k) tracker.** A structured, English-language 510(k) tracker is
   being vacated by a paid vendor while we hold the URL rule that resolves 176,683 filings to
   their summaries. That is a product-shaped hole.
3. **Compliance is a differentiator here, not a cost.** WHO ICTRP's terms forbid commercial use
   of its data; the market's default is to ignore that. A platform that states which sources it
   may not commercially use is more defensible than one that quietly uses them.
