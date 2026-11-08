# A00 — Commercial Medtech Intelligence Platforms: Cross-Platform Synthesis

**Program:** PHOENIX-001 · external methods audit
**Scope:** Seven commercial medtech competitive-intelligence platforms (M7–M13)
**Evidence date:** 2026-11-08 (Asia/Shanghai)
**Method:** public-web only. No account creation, no login, no paywall bypass, no volume scraping, no CAPTCHA solving, no purchases.
**Per-platform files:** `A07_clarivate_drg_medtech.md`, `A08_medvantage.md`, `A09_cmop.md`, `A10_nextdevice.md`, `A11_gbi_devint.md`, `A12_devicepro.md`, `A13_joinchain.md`

---

## 0. Executive summary — five findings

1. **All seven are closed.** Zero public code, zero open data, zero published schema, zero public API documentation. Every conclusion about internal design below is inferred from marketing copy, self-published product announcements, or datasheet-level statements. This is a hard ceiling on the evidence.
2. **Not one of the seven publishes any validation evidence for prediction.** No accuracy figure, no backtest, no holdout, no independent benchmark, no published evaluation — across all seven, zero. Only Clarivate explicitly claims forecasting ("Forecast pipeline movements, financial models and timelines **accurately**"); the other six either make no prediction claim or use only soft "forward-looking" language. **The industry's predictive claims are uniformly unsubstantiated.**
3. **Entity resolution is the shared unsolved problem — and it is solved better for *products* than for *companies*.** Every platform that does serious work anchors products on a hard regulatory key (注册证号 / 510(k) number / FDA product code). No platform publishes a company-hierarchy resolution method, and the two that lean hardest on company identity (CMOP via ticker, Clarivate via analyst labelling) are the weakest structurally.
4. **A dual taxonomy is the Chinese-market consensus.** NextDevice, DevicePro and Joinchain all maintain *two* orthogonal hierarchies: a **regulatory/product classification** (3 levels, class I/II/III-anchored) and a **market/track segmentation** (赛道, up to 4 levels). Western platforms maintain only the commercial one.
5. **Technology generation is almost absent from the industry.** Exactly one platform (NextDevice, 技术代际) names it as a standardised field, and publishes no semantics for it. Nobody publishes coverage start dates or per-record as-of versioning. These are the clearest open lanes.

---

## 1. Comparison matrix

| | M7 Clarivate DRG | M8 MedVantage | M9 CMOP | M10 NextDevice | M11 GBI DEVINT | M12 DevicePro | M13 Joinchain |
|---|---|---|---|---|---|---|---|
| Reachable | Yes (via browser only; 403 to HTTP) | Yes | Yes | Yes (**supplied URL dead**, found real one) | Yes | Yes | **No** — SPA, empty body, browser blocked, WeChat CAPTCHA |
| Vendor | Clarivate Plc (NYSE:CLVT) | Independent venture | RKPROD | 医药魔方 PharmCube | GB Group / 上海集博 | 药渡 Pharmacodia | 众成数科 |
| Delivery | Demo-gated enterprise | Pre-launch, free | **Self-serve, public pricing** | Trial + sales | Trial + sales | Trial + sales | Subscription + **data-exchange listings** |
| Pricing public | No | No | **Yes** (€0/€79/€199) | No (reports 3,889元) | No | No | No |
| Entity anchor | Analyst market segment | **Regulatory submission** | Company/ticker | **注册证号** | OneID (claimed) | **注册证号 / 产品** | **产品分类库** |
| Taxonomy published | Axis only, depth unknown | FDA product code (inherited) | **None** | Dimensions, depth unknown | **None** | Class + 4 labels | **3-level product + 4-level track** |
| ER documented | None | **Strongest claim** | Claim only | **Event dedup rules explicit** | "OneID" term only | Role-aware companies | Roles split, no hierarchy |
| Provenance | Brand-level | **Record-level (claimed)** | Answer-level citations | Curator-attested | "Traceable" (claimed) | Class-level + **as-of date** | **Exchange compliance review** |
| Tech generation | Absent | Absent | Absent | **技术代际 (named)** | Absent | Absent | Absent |
| Explicit forecast claim | **Yes** | No | No | Soft | Soft | No | No |
| Validation evidence | **None** | n/a | **None** | **None** | **None** | n/a | **None** |
| Public API | No | No | Yes (claimed, paid) | No | **Yes** (API+MCP+Skills) | No | Developer centre (opaque) |
| Decision | STUDY_ONLY | STUDY_ONLY | STUDY_ONLY | STUDY_ONLY | STUDY_ONLY | STUDY_ONLY | STUDY_ONLY (site BLOCKED) |

All seven: `code_public = false`, `decision ∈ {STUDY_ONLY}`, no ADOPT/ADAPT possible.

---

## 2. Seven recurring patterns

### P1 — The "unjoinable public data" thesis
MedVantage states it best: *"Nine systems · no joins."* CMOP, GBI, DevicePro and Joinchain all make a version of the same argument (CFDA/NMPA filings scattered, tenders duplicated, patents separate). **The product is the join, not the data.** Every incumbent's moat is the normalisation layer, not source access — because the sources are public. This validates MedRadar's premise.

### P2 — Products have hard keys; companies do not
The asymmetry is stark:
- Products anchor on immutable regulatory identifiers: 注册证号 (NextDevice explicitly joins tender→注册证号, E10), FDA submission numbers and product codes (MedVantage), 产品分类库 (Joinchain).
- Companies have only *names*: applicant, owner-operator, brand (MedVantage); 注册人/代理/备案 roles (DevicePro); no hierarchy statement at all (Clarivate, Joinchain).

Consequence: **product-level identity is largely a solved engineering problem; company-level identity is an unsolved editorial problem** across the entire industry. DevicePro's role typing (registrant ≠ agent ≠ filer) and NextDevice's event dedup rules are the only two partial mechanisms found.

### P3 — Two incompatible information architectures
- **Document-first** (MedVantage, CMOP): the atom is a filing/patent/paper attached to a company. Good for search and monitoring; **structurally cannot express product generations, product matching, or share** because no product master exists.
- **Product-master-first** (NextDevice, DevicePro, Joinchain): the atom is a normalised product keyed to a registration. Supports generations, comparison, share — but requires the expensive unification layer.
- **Segment-first** (Clarivate): the atom is an analyst-authored market-segment record. Fast to sell, unauditable.

MedRadar must be product-master-first, or it inherits the document-first ceiling.

### P4 — Normalisation is always "AI + human", never "AI alone", and never measured
NextDevice: "AI大数据监控收集 + 专业数据分析师审核清洗". DevicePro: "AI + 人工双重审核". Joinchain: "智能清洗与人工二次复核". CMOP alone is fully automated (LLM enrichment, content-hash dedup) — and has the weakest stated data-model.

**Nobody publishes an inter-annotator agreement, a precision/recall for their NER or ER, or an error rate.** The human review is invoked as a quality warranty precisely because it is unmeasurable.

### P5 — Provenance is advertised as an adjective, never exhibited as a field
- GBI: "traceable" / 可追溯 — no field shown.
- Clarivate: analyst insight — no citation.
- Joinchain: "可追溯" via exchange compliance — institutional, not per-record.
- DevicePro: corpus as-of date (2026-08) — best temporal disclosure, still no per-record citation.
- MedVantage: record-level citation + verbatim source text — the only genuine record-level contract, and it is **pre-launch**.

**No platform exposes per-record as-of dating or version history.** This is the universal gap and MedRadar's clearest differentiator.

### P6 — Coverage is claimed in volume, not in fitness
"500余万条" (Joinchain), "2M+ documents" (CMOP), "180万+ devices" (GBI), "285W+ products" (DevicePro). DevicePro's own page contradicts itself (12W+ vs 285W+ products; 7.8万 vs 11W+ companies) — **direct evidence that vendor counts are not reliable measurements.** Counts describe inventory, not answerability.

### P7 — Prediction is either absent or unvalidated; restrained vendors avoid the claim
Ranked by restraint:
1. **MedVantage** — no prediction claim at all; monitors, doesn't forecast; openly labels illustrative UI.
2. **DevicePro / Joinchain** — no prediction claim; "AI" scoped explicitly to *cleaning* and *lead mining*.
3. **CMOP** — no forecast claim; AI is summarisation with citations (but "not hallucinations" is itself unvalidated).
4. **GBI / NextDevice** — soft "forward-looking" language, no product.
5. **Clarivate** — explicit "forecast...accurately", zero validation.

The pattern worth noticing: **the vendors closest to the primary data (MedVantage, DevicePro) are the ones who don't claim to predict.** The vendors furthest from the raw record (analyst-curated, segment-level) claim the most.

---

## 3. The industry consensus data model

Reconstructed from the union of all seven platforms' documented entities and joins. This is what the industry converges on, and it is a reasonable starting schema for MedRadar:

```
Company ──(role)──► Registration ──► Product ──► Classification (regulatory)
   │                     │              │              │
   │                     │              ├──────────────┴──► Market Track (commercial)
   │                     │              ├──► Tender line (price, volume, buyer)
   │                     │              ├──► Clinical study
   │                     │              ├──► Patent family
   │                     │              ├──► Adverse event / recall
   │                     │              └──► Generation / model iteration  ◄── mostly MISSING
   │                     └──► Document (approval certificate, summary, filing)
   └──► Geography (province/city/park)
```

**Entity inventory evidenced across the set:**

| Entity | Evidenced in | Key insight |
|---|---|---|
| **Product** | all product-first platforms | must be normalised; `同名同物归一` (DevicePro), 产品分类 (NextDevice), 产品分类库 (Joinchain) |
| **Registration / approval** | all | the hard key: 注册证号, 510(k) no., PMA no., 备案号 |
| **Company** | all | **needs role typing**: manufacturer / registrant (注册人) / agent (代理) / filer (备案) / buyer |
| **Classification** | MedVantage, DevicePro, NextDevice, Joinchain | regulator-inherited (FDA product code, CN class I/II/III) |
| **Market track (赛道)** | NextDevice, Joinchain, Clarivate ("device series") | commercial; up to 4 levels (Joinchain) |
| **Tender / award** | NextDevice, Joinchain, GBI, DevicePro | brand + model + price + volume + procurement unit |
| **Clinical study** | all except Clarivate (indirect) | — |
| **Patent** | CMOP, Joinchain; **siloed** in NextDevice (NextPat) and DevicePro (PatentPro) | integration is a differentiator |
| **AE / recall** | MedVantage, Joinchain, NextDevice | post-market signal |
| **Geography** | DevicePro (explicit normalisation), Joinchain (park/集聚区) | China-specific, undervalued |
| **Document** | MedVantage, DevicePro, Joinchain | the provenance anchor |
| **Technology generation** | **NextDevice only** (技术代际) | the open lane |

**Joins that matter (each evidenced on at least one platform):**
1. `tender line → 注册证号 → product detail` (NextDevice, E10) — the commercial-to-regulatory bridge. **Most valuable single join found.**
2. `registration → product` 1:N (DevicePro 批件/备案/历史/代理 chains).
3. `product → classification` (all taxonomy-bearing platforms).
4. `product → track` many-to-many (Joinchain's dual taxonomy, NextDevice's 产品分类/赛道).
5. `company → product` via role (DevicePro's three roles).
6. `product → clinical study` (GBI's linked-data claim; NextDevice's 器械临床评价 module).
7. `product → customs HS code` (Joinchain) — unique trade dimension.
8. `submission → predicate → submission` (MedVantage's explicit predicate lineage graph) — the only genuinely novel graph structure found.

---

## 4. The single most valuable cross-platform design lesson

> **The product — anchored to an immutable regulatory identifier — must be the atomic unit of MedRadar's model; the company must be a *resolved attribution* over that anchor, never the primary key.**

**Evidence:**
- The five platforms that do serious structural work all recognise this: NextDevice joins commercial tender records to 注册证号 before anything else; DevicePro builds "企业与产品信息联动" outward *from* the product side and unifies by `同名同物`; Joinchain makes 产品分类库 the hub every other database links through; MedVantage anchors on the submission/product-code; even Clarivate, which lacks the anchor, has to invent a proxy ("device series") to navigate.
- The two that anchor elsewhere fail structurally: **CMOP** anchors on company (and even ticker) and consequently has *no product entity at all* — it therefore cannot express product generations, product-level matching, or share. **Clarivate** anchors on analyst market segments, so its records are prose and cannot be re-derived.
- Company-level ER is where **all seven** are weakest, precisely because company names have no stable key: subsidiaries, M&A, rebrands, and CN↔EN pairs defeat every vendor. Betting MedRadar's architecture on company resolution would inherit the industry's unsolved problem. Betting it on registration identity solves a solved problem first, then lets company attribution be a *derived, scored, correctable* layer on top.

**Corollary (the second lesson):** publish the normalisation rules and the taxonomy. NextDevice writes down its dedup rules (same batch / same party / same product, across single platform, multiple platforms, and different provincial numbering) — and that is the single most reusable artefact in this audit. The rules are free; the execution is the moat. MedRadar can publish its rules, its ER merges with confidence, and its coverage start dates — and lose nothing commercially while gaining the auditability no incumbent has.

---

## 5. What MedRadar should copy conceptually (design ideas, NOT code)

| # | Idea | Source | Why |
|---|---|---|---|
| 1 | Product-master anchored on registration ID; company as resolved view | NextDevice, Joinchain, DevicePro | turns an unsolved problem into a solved one |
| 2 | **Tender line → 注册证号 → product** join | NextDevice | bridges commercial fact to legal identity; enables price/volume history per product family |
| 3 | **Dual taxonomy**: 3-level product classification × 4-level market track, kept orthogonal | Joinchain | separates "what it is" from "what market it competes in" |
| 4 | **技术代际 as a named, standardised field** — but *publish the semantics* | NextDevice | validates the generation concept as market-real; nobody has documented the semantics |
| 5 | Event-level dedup with **written rules** (same event, multiple publications, multiple platforms, different administrative numbering) | NextDevice | the spec, freely reusable, prevents double-counting |
| 6 | **Role-typed companies**: manufacturer / registrant / agent / filer / buyer | DevicePro, Joinchain | China-specific and frequently confused; a classic silent-error source |
| 7 | **Geography normalisation** with approvals-by-province as first-class analytic | DevicePro, Joinchain | no Western competitor does it; cheap and differentiating |
| 8 | **Predicate lineage as a queryable graph** | MedVantage | novel; a genuine precursor to technology-generation ancestry |
| 9 | **Verbatim source text + deep link** instead of paraphrase | MedVantage | the correct provenance contract |
| 10 | **Record-level provenance + per-record as-of date** (beyond anyone) | gap in all seven | MedRadar's differentiator |
| 11 | **Four-dimension data-card compliance** (entity, source, tradability, circulation risk) | Joinchain / Shanghai Data Exchange | externally-reviewed provenance template |
| 12 | **Public price ladder** + free tier | CMOP | lowers evaluation cost, signals confidence |
| 13 | **API + MCP + Skills** delivery triad with standard/custom API tiers | GBI | modern distribution; agent-consumable data is the near-term channel |
| 14 | **Export to PNG/XLSX/PDF** as a first-class feature | Clarivate | enterprise reality: data must move into decks and models |
| 15 | **Openly labelling illustrative UI vs real figures** | MedVantage | trust practice worth institutionalising |

---

## 6. What is simply marketing (and must not be repeated)

| Claim | Platform | Status | Why it is not evidence |
|---|---|---|---|
| "Forecast pipeline movements, financial models and timelines **accurately**" | Clarivate | **CLAIMED_UNVERIFIED** | no accuracy metric, no backtest, no methodology, no benchmark |
| "Predict granular device pipeline shifts" | Clarivate | **CLAIMED_UNVERIFIED** | same; "predict" used as product adjective |
| "AI-driven data governance and correlation" | GBI | **CLAIMED_UNVERIFIED** | no mechanism, no evaluation |
| "timely, **traceable** competitive intelligence" / 可追溯 | GBI | **CLAIMED_UNVERIFIED** | no citation field exhibited publicly |
| "finds subsidiaries, brand names, and products automatically" | CMOP | **CLAIMED_UNVERIFIED** | no ER mechanism; hash-dedup ≠ ER; no accuracy |
| "returns cited, accurate intelligence — **not hallucinations**" | CMOP | **CLAIMED_UNVERIFIED** | no eval set, no error rate |
| "99.9% Uptime", "SOC 2 Type II", "HIPAA Ready", "200+ teams" | CMOP | **CLAIMED_UNVERIFIED** | no certificate, auditor, or status page cited |
| "Applicant, owner-operator, and brand names reconciled into a single company" | MedVantage | **CLAIMED_UNVERIFIED** | no accuracy, no merge log, no correction path; pre-launch |
| "打通**全球器械标签体系**" (global device tag system) | NextDevice | **CLAIMED_UNVERIFIED** | no node list, no crosswalk published |
| "标准化聚类 12W+ 款 … 285W+ 标准化聚类器械产品" | DevicePro | **CONTRADICTED** | same page gives 12W+ and 285W+ products, 7.8万 and 11W+ companies |
| "国内首个…" (first in China) ×3 | Joinchain | **CLAIMED_UNVERIFIED** | self-attributed priority claim, no independent source |
| "AI + 人工" quality warranty | NextDevice, DevicePro, Joinchain | **CLAIMED_UNVERIFIED** | no inter-annotator agreement, precision/recall, or error rate |
| "500余万条 / 2M+ / 180万+" volume counts | Joinchain, CMOP, GBI | **CLAIMED_UNVERIFIED** | inventory size ≠ answerability; DevicePro shows counts can be internally inconsistent |

**Positive control:** MedVantage makes **no** prediction claim and labels its own mock UI as illustrative — the only platform in the set whose public claims are calibrated to what it has built.

---

## 7. The open lanes (what nobody does)

Ranked by strength of evidence that the gap is universal:

1. **Published validation for any predictive claim** — 0/7. Every forecast claim in the industry is unsubstantiated. MedRadar can differentiate by publishing backtests, rolling-origin evaluation, and negative results.
2. **Per-record as-of dating and point-in-time versioning** — 0/7. DevicePro is closest with a single corpus-wide cut-off date. Critical for reproducibility and for avoiding look-ahead bias.
3. **Coverage start dates** — 0/7 publish them.
4. **Published company-resolution methodology with merge audit trail and confidence** — 0/7. Two publish a *claim*, none publish a *method*.
5. **Technology-generation semantics** — NextDevice names the field (1/7) but publishes no definition, boundary rule, or example.
6. **Inspectable schema / public sample records / field names** — 0/7. Not one platform lets a prospective user see a record before buying.
7. **Machine-readable public web presence** — Joinchain fails completely (empty body to HTTP, browser blocked); Clarivate returns 403 to non-browser clients. The industry is hostile to automated audit.
8. **Published Terms / data licence** — GBI's /terms page renders no terms; Clarivate, NextDevice, DevicePro publish none publicly. Only CMOP (and Joinchain, via exchange filings) have inspectable commercial terms.

---

## 8. Confidence and caveats

- **Confidence tiers used:** VERIFIED (their public docs state it) · CLAIMED_UNVERIFIED (marketing) · INFERRED (from product description/help/screenshots) · UNKNOWN.
- **Ceiling:** all seven are closed. Nothing here describes internal schemas, actual record counts, algorithm behaviour, or data quality as measured. Every "data structure" section is a reconstruction from marketing copy.
- **Joinchain (M13) is materially weaker evidence** than the rest: its primary site could not be read at all, and the audit rests on the vendor's own syndicated articles plus data-exchange coverage. Two key taxonomy facts (3-level classification, 4-level track) are title/statement-level only.
- **Two dead/changed URLs found:** `medicube.cn` (supplied for M10) does not resolve — NextDevice lives at `pharmcube.com/product/nextdevice/index`. `cmoinyourpocket.com` timed out on first attempt and only succeeded on retry.
- **No Chinese/English name-pair evidence exists anywhere in the corpus** — despite this being a stated MedRadar pain point, *not one* of the seven platforms documents how it handles CN↔EN company or product names. This is both a gap in the industry and a gap in this audit's evidence: it may be handled internally but is nowhere published.
- **Date discipline:** all access on 2026-11-08; product marketing pages change frequently and numbers/claims should be re-verified before citation.

## 9. Files in this audit

| File | Platform | Decision |
|---|---|---|
| `A07_clarivate_drg_medtech.md` | Clarivate DRG Medtech CI | STUDY_ONLY |
| `A08_medvantage.md` | MedVantage | STUDY_ONLY |
| `A09_cmop.md` | CMOP | STUDY_ONLY |
| `A10_nextdevice.md` | NextDevice (医药魔方) | STUDY_ONLY |
| `A11_gbi_devint.md` | GBI DEVINT | STUDY_ONLY |
| `A12_devicepro.md` | DevicePro (药渡) | STUDY_ONLY |
| `A13_joinchain.md` | 众成医械 Joinchain | STUDY_ONLY (site BLOCKED) |
| `A00_commercial_synthesis.md` | this file | — |
| `experiments/phoenix/external/commercial_audit_summary.json` | machine-readable summary | — |
