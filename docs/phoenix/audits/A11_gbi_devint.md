# A11 — GBI DEVINT

## Metadata

| Field | Value |
|---|---|
| Name | GBI DEVINT (医疗器械数据库 / 器械注册查询平台) |
| Official URL | https://www.gbihealth.com.cn/products/gbi-devint (EN: /en/products/gbi-devint) |
| Vendor | 上海集博投资管理咨询有限公司 / GB Group Limited ("GBI Health"). 沪ICP备2023003595号-2. support@generalbiologic.com, +86 21 20681251 |
| Product type | Commercial subscription intelligence database for the medical-device life cycle, inside a pharma-first data platform; plus a published **API / MCP / Skills open platform** |
| Target customer | 医疗器械从业者及企业高管 (device industry practitioners and executives) — market strategy, product planning, registration, BD |
| Licence / terms | No public price list. 申请试用 (trial request) / 立即咨询 gated. **The /terms page contains no actual terms text** — only a shell. Terms are therefore UNKNOWN. |
| Access barrier | **High** for DEVINT (account required); **notably lower** for the open-platform catalogue, which publishes data-asset counts and API/MCP product descriptions publicly. |
| Evidence date | 2026-11-08 (Asia/Shanghai) |
| Overall confidence | **Medium.** Product framing VERIFIED; data model partly inferable from the open-platform asset list; schema, taxonomy and ER all UNKNOWN. |

## 1) What it is and who buys it

GBI DEVINT is described as "独树一帜的医疗器械数据库" (a distinctive medical-device database) and "覆盖医疗器械全生命周期的一站式竞争情报平台" (a one-stop competitive-intelligence platform covering the full device life cycle).

Critically, it is **not a device-first company**. GBI Health is a **pharma-first** data business; DEVINT is the device vertical, and the open-platform data-asset list (E7) is overwhelmingly pharmaceutical (学术论文 4000万+, 全球上市药品 45万+, 药品说明书 19万+, 靶点数据 4.7万+). Device coverage is one line item: 全球上市器械 180万+.

So DevINT's buyer is a device executive inside an organisation that may also buy GBI's pharma products, and whose real differentiator is **breadth of the adjacent pharma/clinical/regulatory universe**, not device depth.

## 2) Public evidence inventory

| # | URL | Quote (verbatim, translated faithfully) | Confidence |
|---|---|---|---|
| E1 | /products/gbi-devint | "GBI DEVINT 是覆盖医疗器械全生命周期的一站式竞争情报平台。" | VERIFIED |
| E2 | same | "依托标准化数据体系，打通全域异构数据源，聚合全球行业新闻、监管政策、产品注册申报、招投标、上市产品、临床试验等多维度数据" | VERIFIED |
| E3 | same | "依托 AI 技术驱动的数据治理与关联分析能力" (AI-driven data governance and correlation analysis) | VERIFIED (adjective-level; no mechanism) |
| E4 | EN page | "delivers timely, **traceable** competitive intelligence" | VERIFIED (a traceability claim, unexamined) |
| E5 | EN page | "Linked data—including product registrations, clinical studies, company portfolios, and market developments—provides a complete view of the competitive landscape" | VERIFIED |
| E6 | zh page | Four pain points: 市场机会难判断 / 无法及时掌握竞品动态 / 立项决策缺乏支撑 / 市场策略制定缺少依据 | VERIFIED |
| E7 | https://www.gbihealth.com.cn/open-platform | "**全球上市器械：180万+**"; "集采招标：600万+"; "全球临床试验：110万+"; "学术论文：4000万+"; "全球上市药品：45万+" | VERIFIED |
| E8 | /open-platform | "**OneID 连接内外部数据**" (OneID connects internal and external data) | VERIFIED (the only ER-adjacent term published) |
| E9 | /open-platform | "提供标准与定制两类接口 … 标准接口自动更新" (standard + custom API tiers; standard interfaces auto-update) | VERIFIED |
| E10 | /open-platform | "基于 Model Context Protocol（MCP），让各类 AI 助手与 Agent 实时调用 GBI 医药数据，即插即用" | VERIFIED |
| E11 | /open-platform | "GBISkills 技能库 — 面向医药业务场景预置的 AI 技能包 … 覆盖立项、研发、准入、医学运营等多维场景" | VERIFIED |
| E12 | /products/gbi-devint | "持续监测全球医疗器械监管政策、注册法规、行业新闻及市场热点，结合专业分析与专题解读" | VERIFIED |
| E13 | /terms | (no terms text rendered — page shell only) | VERIFIED (absence) |
| E14 | /open-platform | "提升市场预判能力和战略响应速度" (improve market **forecast/judgement** capability) | CLAIMED_UNVERIFIED |

## 3) Data structure & standardisation principles

Entity coverage is broad and enumerated at the *dataset* level (E2, E5, E7): industry news, regulatory policy, **product registration filings (产品注册申报)**, **tenders (招投标)**, **marketed products (上市产品)**, **clinical trials (临床试验)**, plus company portfolios and market developments.

The stated standardisation principle is "**标准化数据体系**" (a standardised data system) that "打通全域异构数据源" (connects heterogeneous data sources across domains) — E2. Combined with E5's "linked data," the architectural intent is a **linked-entity graph across regulatory, clinical and commercial domains**, with the device record joined to trials and to companies.

However, unlike NextDevice or DevicePro, **no individual normalised field is ever named**. There is no published list of product attributes, no classification scheme, no registration-number anchor statement. The granularity of the public claim is "we standardise and link"; the method is UNKNOWN.

**Assessment:** the honest reading is that GBI's differentiator is *cross-domain linkage breadth* (drug + device + trial + academic + tender in one graph), while its device-specific schema depth is undocumented and probably shallower than NextDevice's.

## 4) Company identity resolution

The single relevant artefact is the term **"OneID"** in the API description (E8): "OneID 连接内外部数据" — OneID connects internal and external data.

This is meaningful in context: OneID implies a **master-entity identifier** scheme, i.e. one canonical ID per real-world entity (company, and possibly researcher/institution), used to join heterogeneous sources *and* to join a customer's internal data to GBI's. That is a more architectural ER commitment than any other platform in this set publishes.

What remains UNKNOWN:
- Whether OneID applies to companies, products, or both.
- How subsidiaries, M&A, rebrands, or Chinese/English name pairs are handled.
- Whether OneID is stable/versioned, and whether an ID-to-ID crosswalk is exposed to customers.

**Verdict: a published master-ID concept (VERIFIED as a term), with no published semantics (UNKNOWN).** This is a lead worth pursuing for MedRadar if GBI API docs are ever accessible, but nothing can be concluded about its behaviour.

## 5) Technology / product taxonomy

**UNKNOWN.** No device classification is published — no I/II/III class handling statement, no product hierarchy, no 赛道 model, no technology-generation concept. The only structured catalogue on public view is the *data-asset* list (E7), which is a product inventory, not a taxonomy.

This is a notable contrast with DevicePro (explicit class-based clustering) and Joinchain (explicit 3-level product classification, 4-level tracks). GBI publishes the *volume* of its assets but not their *shape*.

## 6) Data provenance & evidence presentation

GBI uses the word "**traceable**" (可追溯) twice — E4 ("timely, traceable competitive intelligence") and the Chinese solution statement ("全面、及时、可追溯的竞争情报支持"). Traceability is thus an explicit, repeated product promise.

But no public evidence shows **how** traceability surfaces: no source URL, no document link, no as-of date, no citation field is exhibited anywhere on the public pages. Combined with E12 ("结合专业分析与专题解读" — combined with professional analysis and topic interpretation), the model appears to be **curated analysis over sourced data**, with citation visible only inside the paid product.

**Verdict:** "traceable" is a CLAIMED_UNVERIFIED promise; provenance presentation is UNKNOWN.

## 7) Competitor comparison features

Documented at the level of *task*, not *dimension*. The solution pillars are:
1. End-to-end device intelligence across life cycle (E5);
2. Market competition insight — "Analyze tenders, procurement awards, marketed products, company portfolios, and market activity" (E5);
3. Real-time industry monitoring (E12).

So the inputs to comparison are tenders, procurement awards, marketed products, and company portfolios — implying share/volume comparison is possible. But no specific comparison dimension (price, share, rank, timeline) is published, and no screenshot of a comparison view is public.

## 8) Technology-generation expression

**Absent.** No mention of generations, iterations, 技术代际, or model lineage anywhere on the DEVINT or open-platform pages. This is a clear differentiator *against* NextDevice, which makes 技术代际 a headline field.

## 9) Historical technology activity display

No timeline feature, no coverage start date, and no as-of model is published. The most historical-looking evidence is the aggregate counts (E7) and the "life cycle" framing (E1) — the latter implies coverage from R&D through commercialisation, i.e. pre-market as well as post-market, which is a *coverage* claim rather than a *historical display* claim.

## 10) Prediction capability: marketed vs validated

**Marketed:** only soft, adjective-level language — E14 "提升市场预判能力" ("improve market forecast/judgement capability"), and E3 "AI 技术驱动的数据治理与关联分析能力". There is **no numeric forecast product, no accuracy claim, no prediction feature named**.

**Validated: nothing.** No accuracy figure, no backtest, no evaluation, no benchmark. And because no predictive *product* is even claimed, there is nothing to validate.

**Verdict:** prediction is **not claimed as a capability** — merely implied through the word 预判 in a benefit sentence. Recorded as CLAIMED_UNVERIFIED soft marketing. **No evidence of predictive capability exists.** The AI claims are about *data governance and correlation*, not forecasting, and should be read that way.

## 11) What MedRadar can learn conceptually

1. **"OneID" as a named master-entity concept** — naming the identity spine publicly, even before documenting it, is a positioning move MedRadar can make *and then actually document*.
2. **Publishing the data-asset inventory with counts** (E7) is a cheap, credible way to communicate coverage without exposing schema. MedRadar should publish an asset catalogue with counts and as-of dates.
3. **MCP + Skills + API as a delivery triad** — exposing data to agents (MCP), prebuilt analytical skills, and a standard API is a forward-looking distribution model, and notably more modern than any other platform here.
4. **Standard vs custom API tiering** with auto-updating standard endpoints (E9) — a sane commercial/technical split.
5. **Cross-domain linkage breadth as the moat** (device + trial + academic + tender + drug) — argues for MedRadar planning its entity graph to accept adjacent domains rather than only device records.
6. **"Traceable" as the marketed value word** for this segment — evidence the market rewards provenance messaging, which favours MedRadar's auditability strategy.

## 12) What must NOT be copied

1. **Traceability asserted without exhibited mechanism** — E4 says "traceable," but no source link, date or citation field is shown publicly. MedRadar must show the citation, not the adjective.
2. **"AI-driven data governance" as a differentiator** (E3) with no described mechanism, evaluation, or error rate.
3. **A Terms page with no terms** (E13) — an auditability anti-pattern; MedRadar should publish real terms and a data licence.
4. **Device coverage as a line item in a pharma catalogue** — 180万+ device records inside a drug-first platform implies device depth is secondary; MedRadar must not assume GBI is a device-native benchmark.
5. **Volume counts as a substitute for schema disclosure.**

## 13) Decision + reasoning

**Decision: STUDY_ONLY.**

Reasoning: ADOPT/ADAPT impossible — closed subscription, sales-gated, no public schema or data, ToS unpublished. Study value is **medium**: the most transferable assets are the *distribution architecture* (API + MCP + Skills, standard/custom tiers) and the *OneID master-entity naming*, both of which are packaging/architecture lessons rather than data-model lessons. For device data structure, GBI is the least informative of the four Chinese platforms and should not be used as a schema reference.

## 14) Access log

All timestamps 2026-11-08, Asia/Shanghai (+08:00).

| Attempt | URL | Result |
|---|---|---|
| 1 | https://www.gbihealth.com.cn/products/gbi-devint (`web_fetch`) | **HTTP 200 — full page text obtained** (E1–E3, E6, E12) |
| 2 | https://www.gbihealth.com.cn/open-platform (`web_fetch`) | **HTTP 200 — full text** (E7–E11, E14) |
| 3 | https://www.gbihealth.com.cn/en/products/gbi-devint (`web_fetch`) | **HTTP 200 — full text** (E4, E5) |
| 4 | https://www.gbihealth.com.cn/terms (`web_fetch`) | **HTTP 200 but no terms content** — page renders only navigation/footer (E13). No bypass attempted. |

No login (`accounts.gbihealth.pro`) was accessed. No trial requested. No API key obtained. Deeper URLs referenced by the open platform ( `/open-platform/gbi-api`, `/open-platform/gbi-mcp`, `/open-platform/gbi-skills` ) were **not** fetched — the audit stopped at the catalogue level because the questions asked (data structure, ER, taxonomy, provenance, prediction) are answered or explicitly unanswered there; fetching the sub-pages would not reveal schema without an account.
