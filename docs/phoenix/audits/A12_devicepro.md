# A12 — DevicePro (药渡 / Pharmacodia)

## Metadata

| Field | Value |
|---|---|
| Name | DevicePro 医疗器械情报 (药渡 DevicePro) |
| Official URL | https://pharmacodia.com/devicepro.html (database host: https://data.pharmacodia.com/) |
| Vendor | 药渡经纬信息科技（北京）有限公司 (Pharmacodia). 京ICP备14047345号-1. data@pharmacodia.com, 400-851-9921 |
| Product type | Commercial subscription data platform — "全球一站式器械数据互联互通平台" (one-stop global device data interoperability platform), 5 大板块 / 20+ 数据子库 |
| Target customer | Device R&D and registration teams, industry investment/due-diligence, corporate strategy; also pharma-adjacent users of the same vendor's PharmaPro |
| Licence / terms | No public price list. 申请试用 (trial) at https://data.pharmacodia.com/freeTrial/step1; 服务协议/隐私声明 linked from footer (not read). Enterprise subscription. |
| Access barrier | **High.** Trial application + account; no public API, no open sample, no schema browser. Marketing site is fully public and unusually quantitative. |
| Evidence date | 2026-11-08 (Asia/Shanghai) |
| Overall confidence | **Medium-high for structure and scale claims** (the page is numerically specific); **low for taxonomy/ER mechanics** (no node lists, no rules published). |

## 1) What it is and who buys it

DevicePro is Pharmacodia's medical-device vertical: "覆盖产品、企业、注册、标准、临床、政策多维度的一体化器械数据互联互通平台" — an integrated, interoperable device-data platform spanning **product, company, registration, standards, clinical, policy**.

It is one of seven sibling products from the same vendor (PharmaPro, CyberAIDD, InvestPro, DevicePro, MarketPro, **PatentPro**, TrialPro) — and that sibling list is itself a structural finding: **patents belong to PatentPro, not DevicePro**, and clinical trials arguably to TrialPro. DevicePro's stated 5 板块 do **not** include patents. It is a registration/standards/commercial product, not an IP product.

Buyers: Chinese device R&D and registration affairs teams (注册 progress tracking), plus investment/due-diligence (立项评估、产业尽调) and competitive benchmarking (竞品对标).

## 2) Public evidence inventory

| # | URL | Quote (verbatim, translated faithfully) | Confidence |
|---|---|---|---|
| E1 | devicepro.html | "DevicePro 是面向医疗器械领域的全球一站式器械数据互联互通平台，共包含 **5 大板块、20+ 数据子库**，打通产品、企业、注册、标准、临床、政策等多维度数据壁垒。" | VERIFIED |
| E2 | same | "平台标准化聚类国内外一、二、三类医疗器械 **12W+ 款**，汇总注册、代理、备案相关企业 **7.8 万家**。" | VERIFIED (internally inconsistent — see §3) |
| E3 | same | "通过 **AI + 人工**实现器械**同名同物归一整合**、标准化处理，支持多维度检索" | VERIFIED (claim) |
| E4 | same | "纳入美国 510(k)/PMA 审批信息，累计 **130W+ 条注册备案记录**，一站式获取中美两地器械审批数据" | VERIFIED |
| E5 | same | 核心数据指标 table: 产品 **285W+** 标准化聚类器械产品规模 / 公司机构 **11W+** / 批准注册 **143W+** / 标准政策 **6.8W+** / 临床研究 **7.6W+** | VERIFIED (inconsistent with E2 — see §3) |
| E6 | same | "按**创新器械、设备、诊断试剂、高低值耗材**等维度标签化处理 … 便于快速筛选、统计与对比分析" | VERIFIED |
| E7 | same | "数据截至 **2026-08** · AI + 人工双重审核" | VERIFIED |
| E8 | same | "支持赛道格局、企业聚类、省市获批统计、注册进度追踪、竞品布局" | VERIFIED |
| E9 | same | "打通批件、备案、历史、代理产品数据链路 … 实现企业与产品信息联动" | VERIFIED |
| E10 | same | "持续汇集国内外官方公示信息，保持数据时效与完整" | VERIFIED |
| E11 | devicepro.html | Sibling products listed: PharmaPro, CyberAIDD, InvestPro, DevicePro, MarketPro, **PatentPro**, TrialPro | VERIFIED |
| E12 | devicepro.html | "对产品、企业、地域信息做标准化清洗" (standardised cleaning of product, company and geography information) | VERIFIED |

## 3) Data structure & standardisation principles

**Entity coverage (E1, E5):** product, company/institution, registration/approval (批准/注册/备案), standards & policy, clinical research, and geography (地域). Note the explicit absence of patents and of tender/price data as named entities — tenders appear only as an analysis input ("招标、注册与产品数据联动", E8), not as a first-class dataset.

**Document types (E9):** 批件 (approval certificate), 备案 (filing/record), 历史 (history), 代理产品 (distributor products) — with the stated achievement that the data links across these chains and links company↔product.

**Standardisation principles — the most explicit mechanism statement in this audit:**

1. **器械同名同物归一整合** (E3) — literally "same-name-same-thing unification/integration." This is a *product identity resolution* principle stated as a named process, delivered by "AI + 人工" (AI plus human).
2. **标准化清洗** of product, company and **geography** (E12) — geography normalisation is called out explicitly, which no other platform does.
3. **标签化 (labelling)** by dimension: 创新器械 (innovative device), 设备 (equipment), 诊断试剂 (IVD reagent), 高低值耗材 (high/low-value consumables) — E6.
4. **AI + 人工双重审核** (dual review) with a stated data cut-off **数据截至 2026-08** (E7).

**⚠ Internal inconsistency (a real finding about marketing reliability):** the same page gives **12W+ products** (E2) and **285W+ products** (E5); and **7.8万家 companies** (E2) vs **11W+ companies** (E5). These differ by ~24× and ~1.4× respectively. Both cannot be right. The most plausible reconciliation is that E2 counts *normalised device models in the China NMPA universe* while E5 counts *all product-level rows including overseas and historical* — but the page never says so. **This is direct evidence that a leading Chinese vendor's own headline numbers are not internally reconciled**, and it should be cited as a caution against treating vendor counts as measurements.

## 4) Company identity resolution

The vendor states two things relevant to ER:

- **Product**-level: 同名同物归一整合 (same-name-same-thing unification, E3) — an explicit product-master claim.
- **Company**-level: 标准化清洗 of company information (E12), plus "汇总注册、代理、备案相关企业" (E2) — i.e. the company universe explicitly includes **registrants, agents/distributors (代理), and filers (备案)**, not just manufacturers.
- **Linkage**: "实现企业与产品信息联动" (E9) — company↔product linkage is a stated capability.

That three-way company role distinction (注册人 / 代理 / 备案) is important and is a genuine domain insight: in the Chinese market the legal registrant, the domestic agent for an imported device, and the filing entity are frequently **different legal persons for the same commercial product**. Any ER model that collapses them into "the company" will be wrong.

What is **not** stated: how subsidiaries are consolidated, how M&A/rebrands are handled, whether Chinese and English names are cross-linked, or whether a merge audit trail exists. **Company-hierarchy ER: UNKNOWN.**

**Verdict:** strong on product-name unification and on *role-aware* company typing (VERIFIED as claims); silent on corporate hierarchy (UNKNOWN).

## 5) Technology / product taxonomy

Published dimensions (E6, E8):
- **Regulatory class**: 一、二、三类 (Class I/II/III) for domestic and imported devices — explicit.
- **Business/technology label layer**: 创新器械 / 设备 / 诊断试剂 / 高低值耗材 — a coarse 4-way functional split.
- **赛道 (track/sector)** used as an analysis dimension (E8) but not defined.
- **Geography**: province/city normalised, with "省市获批统计" (approvals-by-province statistics) as a feature.

Depth: the class axis is shallow (3 levels, regulator-defined). The 赛道 axis depth is UNKNOWN. No node list, no published hierarchy, no sample records. There is **no technology-generation concept**.

## 6) Data provenance & evidence presentation

Evidence of sourcing practice:
- "持续汇集国内外官方公示信息" (E10) — sources described as *official public notices*, at home and abroad, by class rather than by name.
- **A published as-of date**: "数据截至 2026-08" (E7) — the only platform of the seven that publishes a data cut-off date on its marketing page. That is a meaningful, if minimal, point-in-time commitment.
- "AI + 人工双重审核" (E7) — dual review as the quality gate.

Not evidenced: source URL per record, document deep-links, per-record dates, version history, or whether the as-of date applies to all datasets or only headline counts.

**Verdict:** better-than-average on **temporal disclosure** (a dated cut-off), average-to-weak on **record-level citation**. Provenance is class-level plus a single corpus-wide date.

## 7) Competitor comparison features

Named comparison/analysis scenarios (E8):
1. **赛道格局分析** — track/sector landscape, with "企业聚类 · 省市获批统计" (company clustering, province-city approval counts).
2. **注册进度追踪** — registration progress tracking, approval query, compliance-path reference.
3. **竞品对标分析** — "招标、注册与产品数据联动" (tender, registration and product data linkage) for benchmarking and differentiation strategy.
4. **立项评估与产业尽调** — project evaluation and industry due diligence.

So dimensions compared are **approval counts by geography, registration status/timeline, product portfolio composition, and (via tenders) commercial activity**. This is a **regulatory-and-portfolio** comparison model — closer to MedVantage's philosophy than to NextDevice's price/share model, but with China NMPA instead of US FDA.

## 8) Technology-generation expression

**Absent.** No 技术代际, no product-generation, no iteration-tracking language. Products are counted and clustered (12W+/285W+), not sequenced into generations.

This is a clear and citable gap versus NextDevice, and it is the sharpest differentiator MedRadar can claim against DevicePro specifically.

## 9) Historical technology activity display

Elements present: **历史 (history) is a named document type in the linkage chain** (E9), and "注册进度追踪" implies status-over-time tracking. The as-of date (E7) implies a maintained current state.

Absent: coverage start year, timeline visualisation, snapshot/version model. Historical depth is UNKNOWN — "历史" here appears to mean *historical registration records* (superseded certificates), which is genuinely useful but is not a technology-activity timeline.

## 10) Prediction capability: marketed vs validated

**Marketed: nothing quantitative.** The page offers 立项评估 (project evaluation) and 赛道格局分析 (landscape analysis) — decision *support*, not forecasting. No "predict", no "forecast", no accuracy language, no AI-prediction claim beyond "AI + 人工" used for *normalisation* (E3), not for prediction.

**Validated: not applicable** — no predictive product is claimed.

**Verdict:** DevicePro is the **least overclaiming** of the Chinese platforms. Its "AI" is explicitly a *data-cleaning* tool ("AI + 人工实现器械同名同物归一整合"), not an oracle. That is an honest and correct use of the term. Recorded as: **no prediction claim, no validation evidence, no inflated AI marketing.**

## 11) What MedRadar can learn conceptually

1. **"同名同物归一" (same-name-same-thing unification) as the named principle** — a sharper articulation than "entity resolution" for the product-master problem. MedRadar should state its own unification rule explicitly.
2. **Role-aware company typing** — registrant (注册人) vs agent (代理) vs filer (备案) as distinct roles over the same product. This is a real Chinese-market requirement and a likely MedRadar blind spot.
3. **Geography as a normalised dimension** with approvals-by-province as a first-class analytic. No Western competitor does this.
4. **Publishing a data cut-off date** ("数据截至 2026-08") — minimal but real temporal accountability. MedRadar should do better: per-record as-of plus corpus as-of.
5. **A coarse functional label layer** (innovative / equipment / IVD / consumables) on top of the regulatory class — cheap, useful faceting.
6. **Dual AI+human review as an explicitly stated pipeline stage** — honest about human involvement.
7. **Document-type chain linkage** (批件 / 备案 / 历史 / 代理) as an explicit data-linkage feature.

## 12) What must NOT be copied

1. **Unreconciled headline counts.** 12W+ vs 285W+ products and 7.8万 vs 11W+ companies on one page. MedRadar must publish one reconciled number with its definition.
2. **Class-level sourcing with no record citation** — "official public notices" is not a citation.
3. **Product clustering without a published taxonomy** — "标准化聚类" is un-auditable if the cluster scheme is invisible.
4. **Absence of patents from the device product** — splitting patents into a separate SKU (PatentPro) prevents IP-from-device joins; MedRadar should integrate rather than silo.
5. **Corpus-wide as-of date only** — it cannot support point-in-time correctness for a single record.
6. **Trial-gated schema.** Nothing about structure should be inferred from a marketing page alone.

## 13) Decision + reasoning

**Decision: STUDY_ONLY.**

Reasoning: ADOPT/ADAPT impossible — closed subscription, trial-gated, no public API or data licence. Study value is **medium-high and specific**: the *role-aware company model* (registrant/agent/filer) and *geography normalisation* are directly transferable design requirements that neither Western platform surfaces; the *same-name-same-thing* principle is the best-phrased statement of the product-master problem in the set. It simultaneously provides the audit's clearest example of **vendor metric inflation** (the 12W vs 285W inconsistency), which is why it must be studied and not trusted.

## 14) Access log

All timestamps 2026-11-08, Asia/Shanghai (+08:00).

| Attempt | URL | Result |
|---|---|---|
| 1 | https://pharmacodia.com/devicepro.html (`web_fetch`) | **HTTP 200 — full page text obtained** (E1–E12) |
| 2 | https://pharmacodia.com/about.html (`web_fetch`) | HTTP 200 but body effectively empty (title only) — not used |

Not attempted: `https://data.pharmacodia.com/` and `/freeTrial/step1` (require account/trial application — out of scope and would be an access attempt against a gated resource). No account created. No ToS accepted. `服务协议`/`隐私声明` footer links not read, so licence terms remain **UNKNOWN beyond "commercial subscription, trial-gated"**.
