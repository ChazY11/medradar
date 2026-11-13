# A10 — NextDevice® (医药魔方 PharmCube)

## Metadata

| Field | Value |
|---|---|
| Name | NextDevice® 全球医疗器械数据库 |
| Official URL | **https://pharmcube.com/product/nextdevice/index** (see access note — the URL supplied to this audit, `medicube.cn`, is dead) |
| Vendor | 医药魔方 / PharmCube (PHARMCUBE). ICP 沪ICP备2024080838号-7; tel 010-64736966 |
| Product type | Commercial subscription database — "医疗器械全生命周期数据库" (full-lifecycle device database), with add-on analytic modules |
| Target customer | 器械决策者 — medical-device strategy, investment research, market access, tender/sales teams; also pharma-adjacent investors |
| Licence / terms | No public price list for the platform (subscription, 申请试用 / 预约演示 gated). Individual industry **reports are priced at 3,889 元/份** per the copyright notice on ByDrug. |
| Access barrier | **High.** Trial-request only; database login at a separate host; no public schema, no public API, no free tier. |
| Evidence date | 2026-11-08 (Asia/Shanghai) |
| Overall confidence | **High** — unusually explicit about its normalisation dimensions, including the only public "technology generation" field found in this audit. |

## 1) What it is and who buys it

NextDevice® is PharmCube's medical-device database, positioned as "一站式全球器械数据情报分析平台" (one-stop global device data-intelligence analysis platform). It covers four scenarios stated verbatim: **产品 (product), 销售 (sales), 研发 (R&D), 投资 (investment)**.

It is part of a large PharmCube product family (NextPharma®, PharmaGO®, TrialiCube®, InvestGO®, NextPat®, NextBioSeq®, PharmaBI® IPM/HCM/RCM/HPI), which is itself a structural finding: **patents live in NextPat®, not in NextDevice®**, and trials live in TrialiCube®. NextDevice is the device-domain vertical inside a pharma-first portfolio.

Buyers are Chinese medical-device decision-makers: strategy/investment analysts, market-access and tender teams, and RMB/VC investors doing 赛道 (track/sector) research.

## 2) Public evidence inventory

| # | URL | Quote (verbatim, translated faithfully) | Confidence |
|---|---|---|---|
| E1 | pharmcube.com/product/nextdevice/index | "NextDevice® 是医药魔方打造的医疗器械全生命周期数据库，覆盖器械领域'产品、销售、研发、投资'四大场景。" | VERIFIED |
| E2 | same | "魔方通过AI大数据监控收集+专业数据分析师审核清洗构筑了高精度的结构化数据" | VERIFIED |
| E3 | same | "深入清洗标准化了器械产品的**产品分类、技术代际、医疗服务项目、适应症、热门赛道、性能特色、挂网/中标**等信息" | VERIFIED |
| E4 | same | "进一步打通全球器械标签体系，同步化呈现全球器械竞争格局" | VERIFIED |
| E5 | same | 中国上市器械 module: "深度解析产品分类、技术代际、医疗服务项目、适应症、热门赛道、性能特色、**国产进口与管理类别**等特色数据，**实时追踪产品迭代动态**" | VERIFIED |
| E6 | same | Four solution modules: 中国上市器械 / 器械中标 / 耗材集采挂网 / 器械临床评价 | VERIFIED |
| E7 | 163.com product announcement (2025-11-20) | "该模块专注于整合全国各级公共招投标平台发布的医疗器械中标数据，涵盖设备与耗材的**品牌、型号、价格、采购量**等关键信息" | VERIFIED |
| E8 | same | "独家【产品分类(魔方)】字段，让检索更精准 … 器械名称复杂多样，仅靠切词检索易导致漏检。使用魔方独家产品分类字段，有效避免因产品名称不规范而导致的漏检问题。" | VERIFIED |
| E9 | same | "独家【AI+人工多轮去重】技术，彻底规避标讯重复统计" — dedup across: "同批次同当事人同产品、单平台多次发布"; "同批次同当事人同产品、多平台重复发布"; "同批次同当事人同产品、省市异编号发布" | VERIFIED |
| E10 | same | "中标器械信息中**关联上市器械注册证号**，支持一键跳转至产品详情页，查看完整技术参数与规格信息。" | VERIFIED |
| E11 | same | "检索式支持**AND与NOT**逻辑运算符组合使用" ; "数据库内置【热销产品】字段" ; 检索计算器; visualisation of "中标数量趋势、价格分布、市场份额及厂商排名" | VERIFIED |
| E12 | bydrug.pharmcube.com report page | "如需商业使用，需添加…获得授权并支付相应的授权费用（**3889元/份报告**）" | VERIFIED |
| E13 | product page | "实时追踪产品迭代动态" (real-time tracking of product iteration dynamics) | VERIFIED |
| E14 | product page | "为医疗器械决策者提供全球器械动态与竞争格局" (global device dynamics and competitive landscape) | CLAIMED_UNVERIFIED |

## 3) Data structure & standardisation principles

The most explicitly enumerated standardisation set of the seven (E3/E4/E5). Eight named standardised dimensions, all Chinese-native:

| Dimension | Meaning | MedRadar relevance |
|---|---|---|
| 产品分类 | product classification (proprietary "魔方" classification) | taxonomy — high |
| **技术代际** | **technology generation** | **directly the MedRadar generation problem — unique** |
| 医疗服务项目 | medical service/procedure item (billing/procedure linkage) | pricing/utilisation linkage — high |
| 适应症 | indication | clinical linkage — high |
| 热门赛道 | "hot track"/sector | market segmentation — medium |
| 性能特色 | performance characteristics | product differentiation — high |
| 挂网/中标 | listing price / tender award | commercial — high |
| 国产进口 + 管理类别 | domestic-vs-import + regulatory management class (I/II/III) | regulatory anchoring — high |

Entities evidenced: **product** (with 注册证号 as identity anchor, E10), **company/manufacturer**, **tender award record** (brand, model, price, volume — E7), **procurement unit**, **medical service item**, **indication**, **sector**.

The **tender record is the commercial atom**; it carries brand + model + price + quantity and is **joined to the product master via 注册证号** (E10). That join — regulatory certificate number to commercial tender line — is the platform's central structural trick and the most transferable idea in this audit.

Search supports **AND / NOT boolean composition** (E11), which implies the underlying store is a faceted structured index, not a text search.

Within-device families: **"全球器械标签体系"** (global device tag system, E4) — a cross-border tag layer, claimed, content UNKNOWN.

## 4) Company identity resolution

**Partially documented, and instructive.** The public evidence shows:

- Strong **record-level de-duplication** with explicitly stated *business rules* (E9): they detect the same procurement event republished on one platform, across multiple platforms, and under **different province/city numbering schemes**. That third rule — reconciling the same award across regional numbering systems — is a genuinely hard ER problem solved at the *event* level.
- Manufacturing company appears as an attribute of the product/tender record, but **no public statement about subsidiary consolidation, M&A, rebranding, or Chinese/English name pairing.** ER at the *organisation* level is UNKNOWN.
- The `(魔方)` product-classification field (E8) is explicitly justified as a fix for **unstable product naming** — i.e. they normalise the *product name* problem rather than the *company name* problem.

**Verdict:** strong on product-name and tender-event normalisation (VERIFIED rules); silent on corporate-hierarchy resolution (UNKNOWN). This is the inverse of MedVantage's emphasis — and the two are complementary.

## 5) Technology / product taxonomy

Two layers, both proprietary:

1. **产品分类 (魔方 classification)** — a proprietary product classification field, explicitly the fix for non-standard device names (E8). Depth and node count are **UNKNOWN**; it is not published or browsable without a subscription.
2. **赛道 (track/sector)** — 热门赛道 is a standardised dimension (E3, E5). Depth UNKNOWN.

Plus regulatory class (管理类别, I/II/III) and 国产/进口 origin flags (E5).

None of these are published, and no sample tree is visible publicly. However the *dimension list* itself is a valuable specification of what a Chinese device taxonomy must cover.

## 6) Data provenance & evidence presentation

Weakest dimension. What is evidenced:

- Data is sourced from "全国各级公共招投标平台" (public tender platforms, E7) and regulatory listings — sources are described **generically by class**, never enumerated by URL.
- The product detail page (reached from a tender record via 注册证号) shows "完整技术参数与规格信息" (full technical parameters and specifications, E10).
- **No document deep-link, no source URL, no as-of date, and no citation of the original announcement** appears in any public material.
- The human analyst layer ("专业数据分析师审核清洗", E2) is the stated quality mechanism — editorial, undocumented.

So provenance is **curator-attested**, not source-attested. There is no public evidence of point-in-time handling, although the existence of 挂网/中标 prices implies effective-dated commercial data internally.

## 7) Competitor comparison features

Explicitly evidenced (E11) for the tender module: visualisation of
- **中标数量趋势** — award-volume trend
- **价格分布** — price distribution
- **市场份额** — market share
- **厂商排名** — manufacturer ranking

Plus a **检索计算器** that computes award count and award value for a product class (monthly/quarterly reporting), and the 【热销产品】 (best-selling product) one-click field.

Dimensions therefore: **volume, price, share, rank — per brand/model, per region, per period.** This is the richest commercial comparison model of the seven for the Chinese market, and it is genuinely price-and-volume based rather than mere document counts.

## 8) Technology-generation expression

**This is the only platform of the seven that publicly names technology generation as a standardised field.** 技术代际 appears twice, as a first-class cleaned dimension of the product master (E3) and as a featured field in the listed-product module (E5), alongside "实时追踪产品迭代动态" (real-time tracking of product iteration dynamics, E5/E13).

What is **not** published: the generation scheme's definition, how many generations exist per product family, what constitutes a generational boundary, or any worked example. So:

- Existence of a standardised generation field: **VERIFIED**.
- Its semantics/derivation: **UNKNOWN**.
- Whether it is analyst-assigned or inferred from specs/dates: **UNKNOWN**.

This is the strongest single signal in the commercial audit that "technology generation" is a real, sellable dimension in the Chinese device market — and that a defensible, *published* generation model would be differentiating rather than redundant.

## 9) Historical technology activity display

- "实时追踪产品迭代动态" (real-time product iteration tracking) is promised (E5, E13).
- Tender module supports trend analysis over time with period aggregation (E11), and 2025-dated analyses (e.g. ECMO market review) show multi-year retrospective capability.
- **Coverage start date is not published.** No as-of/versioning model is described. No timeline UI is documented publicly beyond trend charts.

Evidence of real historical output exists (published market reviews built on the database, e.g. 2025 ECMO report), which is indirect confirmation of retrospective depth — INFERRED, not stated.

## 10) Prediction capability: marketed vs validated

**Marketed:** no explicit quantitative forecast claim on the NextDevice product page. The nearest language is "助力…投资研判" (support investment judgement) and "市场预判能力" used in the sibling GBI-style framing; on the 163 announcement the claim is "了解市场规模、份额竞争格局、趋势边际变化，前瞻布局潜在赛道" ("forward-looking layout of potential tracks") — directional "forward-looking" language, not a numeric forecast.

**Validated: nothing.** No accuracy metric, no backtest, no published evaluation, no third-party benchmark anywhere in the public corpus examined. The published reports are descriptive market reviews ("回顾与展望"), not validated predictions. The "展望" (outlook) sections are analyst opinion.

**Verdict:** **no substantive prediction claim, therefore no unsubstantiated prediction marketing to flag — but equally no validation evidence exists.** Any "NextDevice predicts X" statement would be unsupported. Recorded as: prediction capability **UNKNOWN/unclaimed**, marketed as *forward-looking analysis*, not as a model.

## 11) What MedRadar can learn conceptually

1. **技术代际 as a first-class standardised field** — direct validation that the generation model is a market-real requirement, not an academic invention. MedRadar should publish the semantics that NextDevice leaves opaque.
2. **Join the commercial record to the regulatory certificate number** (E10: 中标记录 → 注册证号 → product detail). This is the cleanest bridge between "what was sold at what price" and "what was legally registered" observed in this audit.
3. **Event-level de-duplication with explicit rules** (E9): same event, multiple publications, multiple platforms, **different administrative numbering**. Write the rules down; they are the spec for MedRadar's tender/approval dedup.
4. **Product-name normalisation as the primary ER fix**, with the stated motivation that tokenised search causes false negatives (E8).
5. **Standardised dimension list** (产品分类 / 技术代际 / 医疗服务项目 / 适应症 / 赛道 / 性能特色 / 挂网中标 / 国产进口 / 管理类别) — a ready-made checklist for a China-market device schema.
6. **Boolean AND/NOT retrieval over a faceted index** for precision-critical competitive questions.
7. **Monetising reports separately from data** (3,889 元/report) — a viable revenue shape.

## 12) What must NOT be copied

1. **Opaque proprietary taxonomy and opaque 技术代际 semantics.** The classification is a moat precisely because customers cannot audit it; MedRadar's credibility depends on the opposite.
2. **Curator-attested provenance** (E2 "analyst review") with no source URL and no as-of date.
3. **Generic source description** ("public tender platforms at all levels") instead of enumerated, linkable sources.
4. **Fragmented product family as integration.** Patents in NextPat, trials in TrialiCube, devices in NextDevice means no cross-domain join — a structural weakness MedRadar must not reproduce.
5. **Global tag-system claim without published evidence** ("打通全球器械标签体系", E4) — treat as marketing until a node list is visible.
6. **Revenue share of report sales as the primary model** — it incentivises withholding structured access.

## 13) Decision + reasoning

**Decision: STUDY_ONLY.**

Reasoning: ADOPT/ADAPT impossible — subscription-only, no public API, no data licence to MedRadar, no schema access, trial gated behind a Chinese sales process. Study value is nonetheless the **highest-priority of the seven** for three reasons: (a) it is the only documented precedent for a standardised **technology-generation** field; (b) it demonstrates the **tender→注册证号→product** join that MedRadar needs for commercial evidence; (c) its **explicit dedup rules** are a directly reusable specification (rules, not code). It must be studied as a *what to build* reference and explicitly not as a *how to be auditable* reference.

## 14) Access log

All timestamps 2026-11-08, Asia/Shanghai (+08:00).

| Attempt | URL | Result |
|---|---|---|
| 1 | https://www.medicube.cn/product/nextdevice/index (URL supplied to audit) | **FAILED** — TypeError: fetch failed (DNS/host unresolvable) |
| 2 | https://www.medicube.cn/ | **FAILED** — fetch failed (host dead) |
| 3 | https://www.medicube.cn/product/nextdevice/index.html | **FAILED** — fetch failed |
| 4 | https://pharmcube.com/product/nextdevice/index (`web_fetch`, found via search) | **HTTP 200 — full page text obtained** (E1–E6, E13–E14) |
| 5 | https://m.163.com/dy/article/KEQARI0S0534Q32Z.html (`web_fetch`) | **HTTP 200 — full text** (E7–E11) — PharmCube's own product announcement republished on NetEase |
| 6 | https://data.iyiou.com/intelligence/details/898049e83cb3d6564a9d58d00d508e0f (`web_fetch`) | **HTTP 202** with empty body — no content retrievable |
| 7 | https://bydrug.pharmcube.com/report/detail/30d576310f72403cb5114288dab831cf (`web_fetch`) | **HTTP 200** — confirmed report pricing 3889元 (E12) and that reports are built on NextDevice |
| 8 | http://mp.weixin.qq.com/s?__biz=MzE5ODEwOTIwNg==&mid=2247484580... (`web_fetch`) | Error: cross-origin redirect to mp.weixin.qq.com not followed — not retried (WeChat captcha seen on the Joinchain attempts) |

**Dead-URL finding (important for the program):** the URL given in the brief, `medicube.cn`, does not resolve — the product is published at `pharmcube.com`. Any future citation should use the PharmCube URL. No account was created; no trial was requested; the database login host was not accessed.
