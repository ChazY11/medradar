# S-028-CORRECTION-1 — Correction of the "Yale paper does not exist" claim

**Correction ID:** S-028-CORRECTION-1
**Study:** S-028 *Relational Early Signals in Medical Technology Development: A Temporal Network Study*
**Branch:** `research/s028-temporal-graph-early-signal`（PR #15, draft）
**Author of correction:** `lit-verifier`（独立文献核验）
**Date:** 2026-11-04（Asia/Shanghai）
**Status:** the original conclusion is **withdrawn**. The paper exists. It also contains a **degree-distribution-preserving edge-shuffle ablation**. This note preserves the original wording (§2), explains the failure (§3), records the primary sources (§4–§6), separates bibliographic existence from method-level equivalence (§7–§8), and states the impact on S-028's argument (§9) and on the "44 references fully verified" claim (§10).

> This note is the single source of truth for the correction. `LITERATURE_REVIEW.md`, `artifacts/literature_refs.json` and `PHASE_REPORT_ZH.md` carry in-place corrections that cross-reference it. No code, no experimental artifact and no result number was changed. No git command was run.

---

## 1. Summary

| Question | Answer after primary-source check |
|---|---|
| Does the paper exist? | **Yes.** Christopher Clayton & Antonio Coppola, *The Optimal Use of AI in Financial Regulation*, NBER Working Paper **35227**, **May 2026**, DOI **10.3386/w35227**. |
| Is it Yale-affiliated? | **Yes** for Clayton: PDF title page lists "Yale University and NBER"; NBER author page lists Yale University; his personal site lists "Associate Professor of Finance, Yale School of Management"; the OpenAlex record's raw affiliation is "Yale School of Management, 165 Whitney Ave, New Haven, CT 06511". Coppola is *not* Yale (see §5.2 for the affiliation discrepancy across sources). |
| Does it build a graph model on institution–asset holdings? | **Yes.** Bipartite investor–asset graph, positions as edges, graph-transformer message passing (§6.1–§6.2). |
| Does it do out-of-sample validation? | **Yes.** Static random split **and** a walk-forward test retrained each year, 2015–2020, tested strictly on future quarters (§6.3). |
| Does it perform graph ablations? | **Yes.** Four architecture ablations, including "Shuffled edges" (§6.4). |
| **Is a degree-preserving swap/rewiring control present?** | **YES — stated.** The ablation is defined as "randomly permutes edge indices to destroy network topology while preserving node features and degree distributions" (Figure 6 notes, printed p.19). **The exact algorithm** (configuration-model stub matching vs. degree-preserving edge swaps) **is UNVERIFIED** — the paper does not specify it (§7). |
| Is it the same randomisation design as S-028? | **No.** It is a single retrained ablation variant per walk-forward window, reported as one R² number; **no repeated random draws, no null distribution, no quantiles/p-values, no block/time-stratified constraints, no seeds** (0 occurrences of "seed" in the extracted text of the 67-page PDF). S-028's *design intent* is R = 20 block-level degree-preserving swaps with per-track date pools and a paired ΔAP null distribution (§8); note that the Phase 0–3 **implementation** of that design is separately found defective in this same correction round (`RANDOMISATION_DEFECT_ANALYSIS.md` — not degree/weight/time preserving in 72/72 checks), and corrected N1/N2 null models replace it. |
| Was the original claim wrong? | **Yes**, and it was overstated epistemically: "not found in a targeted search" was written as "does not exist". The matching record had already appeared in the reviewer's own recorded search results and was dismissed at title level (§3). |
| Are S-028's empirical results affected? | **No, not by this literature correction.** Only a literature claim and the novelty framing that rested on it change. (Separately, a concurrent randomisation-implementation audit in this same correction round finds the Phase 0–3 randomisation defective and invalidates the H2 "random graphs beat the real graph" finding — `RANDOMISATION_DEFECT_ANALYSIS.md`; that is independent of this correction.) |

---

## 2. The erroneous claim, verbatim, with file and line

Line numbers are those of the **pre-correction** revision of each file.

**`LITERATURE_REVIEW.md`**

- L101: `## §8 金融关系网络的方法论启发（含对"耶鲁论文"的核验结论）`
- L103: `### 8.1 核验结论：找不到这样一篇论文`
- L107: `……**没有任何一篇同时满足"耶鲁 + 金融实体动态关系图 + 边置换或删结构对照"**。完整记录见 JSON 的 premise_checks.PC-01。三篇最接近的工作各只满足前提的一部分：`
- L113: `**正确表述**：用户描述的"打乱边 / 删结构"，正当来源是网络科学的零模型传统与约束随机化（保度、保活跃度、保时间分布的 rewiring），而非某篇耶鲁论文。S-028 若要引金融界先例，只能引其评估哲学（R43：图的有效性应与模型性能解耦检验），不能引一个并不存在的"方法先例"。`
- L16 and L191: the companion claim `44 条全部标识已核对到实抓记录：verified_primary 44 …` / `合计 44 条：verified_primary 44 / verified_secondary 0 / unverified 0`（audited in §10）.

**`PHASE_REPORT_ZH.md`**

- L128–L136: `1. **"耶鲁金融关系网络论文"经系统检索不存在。** …… **没有任何一篇同时满足"耶鲁 + 金融实体动态关系图 + 边置换/删结构对照"** …… **因此"打乱边/删结构"应归因于网络科学的零模型/约束随机化传统，不能引一个不存在的先例。**`

**`artifacts/literature_refs.json`（PC-01）**

- `premise_checks[0].finding`: `No single paper matching the description could be found. Three separate real works get conflated by the description.`
- `premise_checks[0].conclusion`: `The premise should not be accepted as stated: I could not verify the existence of a Yale paper with this design. The specific methodological device (rewiring links while preserving degree/activity/time as a null) is standard network-science practice (configuration-model-style randomisation), not a Yale finance contribution. …`

**Downstream, not edited in this pass（listed in §12）**

- `GRAPH_RESULTS.md` L121: `文献综述（LITERATURE_REVIEW.md §8）已核实：不存在"耶鲁 + 金融实体动态关系图 + 边置换对照"`

Two distinct errors are entangled here and are separated from now on:

1. **A false negative about existence** — "no such paper exists"（error of fact）.
2. **An over-broad inference about method** — "therefore the degree-preserving rewiring device has no financial precedent"（error of inference; the paper does have a degree-preserving shuffle, but not S-028's randomisation protocol）.

---

## 3. How the error arose

The failure was **not** a missing database record, and it was not a timing problem. It was a two-stage screening failure aggravated by metadata-only verification.

1. **The record was already in the reviewer's own result set.** `premise_checks.PC-01.searches_performed[1]` records, verbatim:
   > `OpenAlex works filter institutions.ror:03v76x132 AND 'financial' AND 'graph' - 11 hits: Mamba/stock …, two AI-in-financial-regulation papers (Clayton/Coppola), smart-contract security, telemedicine-in-ICU, haematology - no match.`
   
   The correctly matching work was surfaced by the Yale-ROR × `financial` × `graph` query and was then excluded. The `- no match` in the same sentence is the exact point where the false negative was created. The `finding`/`conclusion` fields were written as if the candidate had never appeared.
2. **Every hit was screened at title level.** The title *The Optimal Use of AI in Financial Regulation* contains none of `graph`, `network`, `relational` or `GNN`; the graph is in the abstract ("a graph-based deep learning model") and body. A title-level screen classifies the item as "AI-in-financial-regulation", not as a relational-network paper.
3. **The search vocabulary could not match the paper's own wording.** The queries used `shuffled graph`, `degree-preserving rewiring`, `placebo edges`. The paper writes **"shuffled edges" / "preserving … degree distributions"** and never uses "rewiring", "configuration model" or "edge swap" (0 hits for each in the full text). Only the exact phrase `shuffled graph` was queried.
4. **The earlier circulated title is also non-graph.** PDF p.1 footnote: *"This paper was previously circulated under the title 'Financial Regulation and AI: A Faustian Bargain?'"* — a title search on the current title does not reach a graph vocabulary either.
5. **The shuffle is described in a figure note and two sentences, not in the abstract.** The only descriptions are Figure 6 notes (printed p.19) and §3.2 "Ablation Analysis" (printed p.20), plus Appendix B contains no further specification. Any discovery method that does not read beyond the abstract/title cannot find it — so the earlier conclusion "contains no edge-shuffling control" (`PC-01.closest_matches[R42].why`) was **not supportable at the evidence level actually used**.
6. **No full text was ever read for any of the 44 original references** (0/44 marked full-text; see §10). Yet the review made method-level negative claims ("no edge-shuffling or structure-deletion control", "the Yale paper does not exist") that only full text can support.
7. **Timing excludes the innocent explanation.** The NBER issue date is **May 2026**; the OpenAlex record (W7162290176) was created **2026-05-26** and last updated **2026-10-28**; the review date is **2026-11-04**. The record was indexed and live for about five months.
8. **Epistemic overreach.** "Not found in targeted searches over OpenAlex/arXiv/Crossref/web" was converted into "does not exist" / "没有任何一篇" and then used as a premise for the novelty argument. This is the same class of error as the six wrong remembered DOIs already recorded in `LITERATURE_REVIEW.md` §0 — a fluent, plausible claim that was never read at source.

---

## 4. Primary sources checked (all accessed 2026-11-04, Asia/Shanghai)

| # | Source | What it establishes |
|---|---|---|
| 1 | **NBER official record** — https://www.nber.org/papers/w35227 (HTTP 200) | Title, both authors, "Working Paper 35227", "DOI 10.3386/w35227", "Issue Date May 2026", full abstract, NBER page categories. The HTML landing page does **not** display JEL codes. |
| 2 | **NBER full-text PDF** — https://www.nber.org/system/files/working_papers/w35227/w35227.pdf (HTTP 200, `application/pdf`, 2,295,917 bytes, **67 pages**, SHA-256 `E99446FD922B78C219F58DC89A63A3F40399407BF6F86FC996F64E1B91C74398`; internal `/CreationDate` 2026-05-12, `/ModDate` 2026-05-21, `/Title` "The Optimal Use of AI in Financial Regulation", `/Author` "Christopher Clayton and Antonio Coppola") | Title page (p.1), earlier-circulation title (p.1 footnote), JEL codes and author affiliations (p.2), and the **full text** used for every method claim below: §2 (pp.8–11), §3.1–§3.2 (pp.15–22), Tables 1–4, Figure 6, §3.5/Table 8, §3.6, Appendix B (PDF p.52, printed A.6), Online Appendix (pp.47–67). |
| 3 | **Crossref DOI registry** — https://api.crossref.org/works/10.3386/w35227 (HTTP 200) | DOI `10.3386/w35227` registered by NBER; title; two authors (Clayton first, Coppola additional); `type: report`; `issued`/`published-online` 2026-05; record created 2026-05-25; primary resource `http://www.nber.org/papers/w35227.pdf`. No affiliation fields. |
| 4 | **NBER author page** — https://www.nber.org/people/christopher__clayton (HTTP 200) | "Christopher Clayton — Faculty Research Fellow — **Yale University**"; programs IFM, ITI; contact `christopher.clayton@yale.edu`; personal site link. |
| 5 | **Author personal site** — https://www.christopherdclayton.com/ (HTTP 200) | "**Associate Professor of Finance, Yale School of Management**"; NBER Faculty Research Fellow (IFM, ITI). |
| 6 | **Yale SOM faculty directory** — https://som.yale.edu/faculty-research/faculty-directory/christopher-clayton (HTTP 200, redirected from `/faculty/christopher-clayton`) | Page title "Christopher Clayton \| Yale School of Management"; body was truncated by the fetcher, so only the existence of the Yale SOM faculty entry is claimed here, not its text. |
| 7 | **OpenAlex work record** — https://api.openalex.org/works?search=%22optimal%20use%20of%20ai%20in%20financial%20regulation%22 (HTTP 200) | Work **W7162290176**, `doi:10.3386/w35227`, `publication_date 2026-05-01`, OA green, fulltext available; Clayton raw affiliation "Yale School of Management, 165 Whitney Ave, New Haven, CT 06511" with institution **Yale University (ROR 03v76x132)**; keyword **"graph-based deep learning"**; second location `10.2139/ssrn.6824965` (SSRN). Used here as corroboration/indexing evidence, not as the authority for method claims. |

**Not used as evidence:** the NBER HTML abstract for method details (the abstract page does not mention ablations); any blog/summary; any secondary description of the paper's methods. No secondary source was needed: the full text was obtained from NBER and read.

**Extraction note.** PDF text was extracted with pypdf 6.18.1. Full-text searches (e.g. for "seed", "rewiring", "configuration model", "edge swap", "permutation") were run on the **extracted text layer**; text embedded only in figure images was not OCR'd, so "not found" here means "not present in the extractable text", not "absent from every pixel". Quotations below are verbatim wording; PDF superscripts and ligature-induced spacing were normalised (e.g. `R2` → `R²`, missing spaces restored). No wording was changed. Page citations give the **printed page** of the NBER PDF where visible, with the PDF page in parentheses.

---

## 5. Corrected bibliographic facts

### 5.1 Verified facts

| Field | Value | Evidence |
|---|---|---|
| Title | *The Optimal Use of AI in Financial Regulation* | NBER p.1/HTML; PDF p.1–2; Crossref |
| Authors | Christopher Clayton; Antonio Coppola (order as printed) | NBER; PDF p.1–2; Crossref |
| Series / number | NBER Working Paper Series, **Working Paper 35227** | NBER HTML; PDF p.1 |
| Issue date | **May 2026** | NBER HTML "Issue Date May 2026"; PDF p.1–2; Crossref `issued 2026-05` |
| DOI | **10.3386/w35227** | NBER HTML "DOI 10.3386/w35227"; Crossref; OpenAlex |
| JEL codes | **C4, G1, G2** | PDF p.2: "JEL No. C4, G1, G2" |
| Prior circulation title | *"Financial Regulation and AI: A Faustian Bargain?"* | PDF p.1 footnote |
| Publication status | NBER working paper, **not peer-reviewed** | PDF p.1 boilerplate: "NBER working papers are circulated for discussion and comment purposes. They have not been peer-reviewed…"; no published version is listed on the NBER page as of 2026-11-04 |
| Full text | 67-page PDF including main text, references and Online Appendix; SHA-256 as in §4 | PDF downloaded from NBER, 2026-11-04 |
| Abstract (substance) | Graph-based deep-learning model for security-level holdings of financial intermediaries; learns latent representations of assets and investors from the portfolio-positions network; applied to non-bank intermediaries (~$40tn); out-of-sample forecasts of trading behaviour including crises; >10× explanatory power for crisis-period cross-sectional asset returns vs traditional approaches; outperforms systemic-risk metrics; fully inductive with entire asset classes/investors withheld from training; embedded in a macroprudential optimal-policy framework addressing the Lucas critique | NBER HTML abstract = PDF p.2 abstract (identical text apart from the NBER "Institutional subscribers…" tail) |

### 5.2 Affiliations — exactly what each source says

| Source | Clayton | Coppola |
|---|---|---|
| Paper PDF p.2 | "Yale University and NBER" | "Stanford University" |
| NBER author pages | "Yale University" | "The University of Chicago" |
| OpenAlex authorship | Yale University (ROR 03v76x132), raw string "Yale School of Management, 165 Whitney Ave, New Haven, CT 06511" | University of Chicago (Booth) **and** NBER; ORCID listed as `0000-0003-2320-1625` |

**Do not resolve this discrepancy by assertion.** The only affiliation relevant to the correction — Clayton's Yale affiliation — is attested by the paper itself (primary), the NBER author page, the personal site and OpenAlex. Coppola's current affiliation differs between the PDF (Stanford), NBER (Chicago) and OpenAlex (Chicago Booth + NBER); this is recorded here as **UNVERIFIED / conflicting**, and nothing in S-028 depends on it. The non-Yale author does not weaken the "Yale" identification of the paper: the premise concerned a Yale-affiliated paper, and one of its two authors is Yale faculty.

---

## 6. What the paper actually does — method facts with quotations

### 6.1 Graph model structure (nodes, edges, what is a "network")

- **Bipartite graph, per quarterly cross-section.** §2 (printed p.9, PDF p.11):
  > "The holdings graph G_t is bipartite: it has two distinct types of nodes, and edges only connect nodes of different types, with investors connecting to assets via position edges."
  > "Whenever investor i holds asset a at time t, then (i, a, w_ia,t, q_ia,t) ∈ E_t."
- **Nodes:** investors (non-bank financial intermediaries: mutual funds, ETFs, separate accounts, pensions, insurers) and assets (securities). Node features x_v,t are numerical (e.g. amount outstanding, coupon, years to maturity, AUM, number of positions, position-size mean/sd) and categorical (investor type, manager style, asset class, currency) — §3.1 (printed p.14, PDF p.16), Table 1 (printed p.12).
- **Edges:** observed positions at time t, with market value w and notional quantity q. The model predicts the position-quantity change y_ia,t+1 = log(q_ia,t+1 / q_ia,t) for continuing positions; **new entries (q_ia,t = 0) are excluded from training and evaluation** (footnote 4, printed p.8, PDF p.10).
- **Model:** a "graph transformer", i.e. an attention-augmented GNN with L = 3 message-passing layers and SA = 4 heads, hidden dim 256, embedding dim 128, economic-prior attention bias from normalised position weights, a masked-autoencoder pretraining phase (35% edge masking) then supervised fine-tuning with a hurdle head (extensive + intensive margin); ~1.3M parameters (Table 2, printed p.13; §2 and Appendix B, PDF p.52).
- **Aggregate conditioning:** the scalar ζ_t+1 is the St. Louis Fed Financial Stress Index (first PC of 18 stress indicators) — §2 (printed p.7, PDF p.9).
- **"Dynamic" means a panel of quarterly graphs, not a timestamped temporal graph.** The unit is the quarterly cross-section G_t plus year-by-year retraining; no continuous-time event graph, no temporal edge encoding (contrast with the temporal-GNN literature in `LITERATURE_REVIEW.md` §1).

### 6.2 How the institution–asset holdings network is constructed

- §3.1 (printed p.13, PDF p.15): "We train our deep learning model on quarterly institutional holdings from **Factset and Morningstar**, starting in **2004Q1**, which cover a broad range of non-bank intermediaries including mutual funds, ETFs, separate accounts, pensions, and insurance companies."
- Sample size: "roughly **37,000 unique non-bank financial intermediaries in 85,000 unique assets**" (printed p.14); **72 quarters 2004Q1–2021Q4**; mean per quarter **17,751 investors**, **33,302 assets**, **2,310,818 holdings edges**, graph density **0.406%**; ~122.8 positions per investor, ~65.6 holders per asset (Table 1, printed p.12).
- Node features: Factset, Morningstar and the GCAP security master file (printed p.14).
- Bond returns for §3.3 use TRACE with Dick-Nielsen (2014) cleaning (footnote 9, printed p.21).
- **What is not documented:** the paper's main text does not state the universe screening rules (e.g. minimum position size, entity filters, deduplication) beyond "non-bank intermediaries" and the exclusion of new positions. This is a **gap**, not a contradiction; it limits how far the construction can be cited as a template — §7 marks it UNVERIFIED.

### 6.3 Out-of-sample validation design

§3.1 (printed p.14, PDF p.16), verbatim:

> "We evaluate the model using two complementary out-of-sample strategies… The first is a **static split**, in which quarters are randomly partitioned into training and validation sets; this approach maximizes the available training data and provides a pooled measure of predictive accuracy. The second is a **walk-forward evaluation**, in which the model is retrained from scratch each year on an expanding window of past data and tested strictly on the subsequent year's quarters, mimicking real-time regulatory deployment. The walk-forward evaluation spans **six annual windows from 2015 to 2020**, with the final window providing a particularly salient test during a crisis event: the model is trained only on pre-crisis data and then evaluated on the Covid-19 stress episode (2020q1)."

- The paper itself flags that the static random split "creates potential information leakage through the persistence of the holdings graph" (printed p.15, PDF p.17) and relies on walk-forward as the conservative measure.
- Reported performance: static split AUC 0.860, R² 11.0% (Figure 2); walk-forward average AUC 0.823, R² 6.6% over six windows (Table 3, printed p.16); 2020 window R² 7.0%, 2020Q1 per-quarter R² 6.8%; benchmark table (Table 4) includes persistence, ridge, gradient boosting, matrix-factorisation, two-tower recommender and the graph transformer; the graph transformer is best in both the pooled and walk-forward columns.
- Also reported: cold-start inductive holdouts — entire corporate-bond asset class withheld, random 20% of investors, random 20% of assets — retrained from scratch and evaluated on complete graphs (Table 8, §3.5).

### 6.4 Which graph ablations / randomisation experiments are actually performed

**Figure 6 "Architecture ablation study"** (printed p.19, PDF p.21) reports walk-forward R² for the baseline and **four** variants, each retrained from scratch in every expansion window:

| Variant | What is changed | Walk-forward R² |
|---|---|---|
| Baseline graph transformer | — | **6.6%** |
| No FSI conditioning | removes aggregate stress index ζ_t+1 from the prediction head | 4.3% |
| No attention | replaces attention aggregation with symmetric mean pooling | 3.2% |
| Single GNN layer | restricts message passing to one hop | 2.5% |
| **Shuffled edges (topology destroyed)** | "randomly permutes edge indices to destroy network topology while preserving node features and degree distributions" (Figure 6 notes) | **2.3%** |

§3.2 "Ablation Analysis" (printed p.20, PDF p.22) interprets them; the key sentence is quoted in §6.5.

Other experiments that are **not** graph randomisations and are not described as ablations: (i) the benchmark-comparison table (Table 4); (ii) the cold-start entity-holdout tests (Table 8); (iii) a placebo test using **random embedding directions** for the fire-sale-vulnerability direction (§3.6, printed p.27: "A placebo test using random embedding directions yields near-zero R²"), which is a placebo on the interpretation of embeddings, **not** on graph edges; (iv) conformal prediction-interval coverage (§3.7). No permutation test, no randomisation distribution, no p-value for the shuffle, and **no seed count is reported anywhere in the 67-page PDF** (the string "seed" does not occur in the extracted text).

### 6.5 The degree-preserving edge-shuffle — exact quotes

**Figure 6 notes** (printed p.19, PDF p.21):
> "'Shuffled edges' randomly permutes edge indices to destroy network topology while preserving node features and degree distributions."

**§3.2 Ablation Analysis** (printed p.20, PDF p.22):
> "The ablations show that the network information (the topology of the network) is indispensable: randomly shuffling edges, while preserving node features and degree distributions, reduces walk-forward R² from 6.6% to 2.3%, eliminating nearly two-thirds of the model's explanatory power and bringing the performance in line with models based only on characteristics."

**Appendix B** (PDF p.52, printed A.6, "Architecture and Training Details") documents the attention computation, losses, MAE masking and parameters, but contains **no further specification of the edge-shuffle procedure**.

### 6.6 What is demonstrably *not* in the paper (searching the full text)

Absent: "degree-preserving rewiring", "configuration model", "edge swap", "permutation test", "randomisation distribution", "null model", "quantile", "seed", "placebo edges". Present once: "placebo test" (embedding directions). The paper's word is **"shuffled edges"** with an explicit **degree-distribution-preservation** claim. "Independent/edge-swap implementation" is therefore **not** established by the text.

---

## 7. What is VERIFIED vs. what remains UNVERIFIED

### 7.1 Verified (primary source opened)

| # | Claim | Evidence |
|---|---|---|
| V1 | Paper exists; exact title; both authors and order | NBER HTML; PDF p.1; Crossref |
| V2 | NBER Working Paper number 35227 | NBER HTML; PDF p.1 |
| V3 | Issue date May 2026 | NBER HTML; PDF p.1–2; Crossref `issued` |
| V4 | DOI 10.3386/w35227 | NBER HTML; Crossref; OpenAlex |
| V5 | JEL codes C4, G1, G2 | PDF p.2 |
| V6 | Previously circulated under "Financial Regulation and AI: A Faustian Bargain?" | PDF p.1 |
| V7 | Clayton: Yale University / NBER (paper's own statement) + Yale SOM / NBER affiliation | PDF p.2; NBER author page; personal site; OpenAlex raw affiliation |
| V8 | Not peer-reviewed (NBER working paper, as of 2026-11-04) | PDF p.1 boilerplate; NBER page lists no published version |
| V9 | Bipartite investor–asset holdings graph; positions as edges | §2, printed p.9 |
| V10 | Data: Factset + Morningstar quarterly holdings, 2004Q1–2021Q4, 72 quarters, ~37k investors, ~85k assets, ~2.31M edges/quarter, density 0.406% | §3.1 printed pp.13–14; Table 1 printed p.12 |
| V11 | Graph transformer: L=3, 4 heads, 256/128 dims, MAE pretraining, hurdle head, ~1.3M params | Table 2 printed p.13; §2; Appendix B |
| V12 | Out-of-sample: static random split + walk-forward retrained yearly, 2015–2020, future-only test | §3.1 printed p.14; Table 3 printed p.16 |
| V13 | Four ablations incl. shuffled edges; values 6.6 / 4.3 / 3.2 / 2.5 / 2.3 | Figure 6 printed p.19; §3.2 printed p.20 |
| V14 | The shuffle is stated to preserve "node features and degree distributions" | Figure 6 notes + §3.2, exact quotes in §6.5 |
| V15 | No seed count / no randomisation distribution / no p-value for the shuffle | Full-text search: "seed" 0 hits; Figure 6 reports single values |
| V16 | OpenAlex indexed the work (W7162290176) with Yale affiliation and keyword "graph-based deep learning" | OpenAlex API record |

### 7.2 UNVERIFIED (cannot be established from the sources read)

| # | Open question | Why it is unverified |
|---|---|---|
| U1 | **Exact edge-shuffle algorithm** — configuration-model stub matching, Maslov–Sneppen degree-preserving edge swaps, or something else | Paper does not specify it; Appendix B silent; only the phrase "randomly permutes edge indices … preserving … degree distributions" exists, which is not an algorithm |
| U2 | Whether **both** degree sequences (investor side and asset side) are preserved, or only the marginal degree distribution | Statement says "degree distributions" (plural), but the mechanism is unspecified |
| U3 | Whether the shuffle **preserves time structure, block/sector structure, or position weights** | Not stated; node features are preserved by design; time and weight preservation are not mentioned |
| U4 | How many random draws / seeds; whether the reported R² is a mean over draws or one realisation | No seed or repetition count appears; a single variant is described as "retrained from scratch in every expanding window" |
| U5 | Whether any null distribution, quantile or p-value was computed for the shuffle | Not reported in the main text or appendix; no such statistic appears |
| U6 | Universe/data-cleaning filters for the holdings graph (position-size cutoffs, entity screens, deduplication) | Not documented in the text; only "non-bank intermediaries" and exclusion of new positions are stated |
| U7 | Any revision of the paper after the 2026-05 version, or acceptance at a journal | Only the NBER May 2026 PDF was read; NBER page lists no published version as of 2026-11-04 |
| U8 | Coppola's current affiliation | Conflicting across PDF (Stanford), NBER (Chicago), OpenAlex (Chicago Booth + NBER) — irrelevant to S-028's argument but not asserted |
| U9 | Meaning/description of the JEL codes (codes C4, G1, G2 are printed; their class labels are not printed on p.2) | Codes verified; interpretations not asserted |
| U10 | The original 44 references' substantive claims and 10 venue attributions | See §10 — metadata-level only |

**Headline verdict for the task's critical distinction:**
- **(a) Existence and bibliographic facts:** **verified** (§5).
- **(b) Degree-preserving swap control present:** **YES, stated** — an edge-shuffle ablation explicitly described as preserving degree distributions (V14). **Implementation-level equivalence to a configuration-model/edge-swap randomisation is UNVERIFIED (U1–U5).** A repeated-randomisation null distribution (the design S-028 uses) is **not present**.

---

## 8. Method-level distinction: w35227 vs. S-028

| Dimension | Clayton & Coppola (w35227) | S-028 |
|---|---|---|
| Purpose of the shuffled-edge variant | Architecture ablation: show that "the network information (the topology of the network) is indispensable" (printed p.20); reported as a descriptive R² drop 6.6 → 2.3 | Inference: is the observed ΔAP distinguishable from a degree/activity/time-preserving null? reports paired ΔAP(real − randomised) and its position in the randomisation distribution |
| Graph | Bipartite investor–asset holdings graph; 2.31M edges/quarter; bipartite density 0.406%; 72 quarterly snapshots | Bipartite company–technology event graph; 322 observed pairs of 1,938 (16.6%); 135–148 edges per 12-month snapshot; 51-node projected-graph density 0.093–0.101 (projected graph, not the bipartite density) |
| Randomisation | One retrained shuffled-edge model per walk-forward window; single value per window | **Design intent:** R = 20 block-level degree-preserving swaps with per-track date pools, preserving degree + activity + time. **Implementation status:** the Phase 0–3 implementation is audited separately in this same correction round (`RANDOMISATION_DEFECT_ANALYSIS.md`), which finds it did **not** in fact preserve the bipartite degree sequences, edge-weight semantics or entry-time distribution (72/72 invariant failures) and therefore invalidates the H2 "random graphs beat the real graph" finding; corrected null models N1 (degree-preserving) and N2 (degree + track-activity + within-track time distribution) replace it. `LITERATURE_REVIEW.md` states R=20 while `PHASE_REPORT_ZH.md` §9.3 says "40 种子" — the original Phase 0–3 run used 40 randomisations per `RANDOMISATION_DEFECT_ANALYSIS.md`, so the document counts need reconciling (outside this correction's scope). |
| Null distribution / quantiles | None reported | Reported (e.g. 97.5% quantile of the randomised distribution) |
| Decision statistic | Walk-forward R² (%) | Paired ΔAP with MDE; pre-registered stopping rules |
| Time structure | Quarterly panel; no time-preserving constraint stated for the shuffle | Explicit time/activity preservation as part of the null |
| Target event | Investor–asset quantity change (continuous, all positions) | Rare first regulatory event (base rate ~1.019%), right-censored 12-month window |
| Sample scale | 68.8M walk-forward observations; ~1.3M-parameter model | 41k–44k rows, 239–418 positives; 16–30 feature baselines |

**Consequence:** the existence of w35227 supports the *plausibility* of topology ablation in a financial network (and, read the other way, is now the strongest available finance-domain evidence that destroying topology while preserving degree distributions removes most of the model's explanatory power). It does **not** establish S-028's randomisation protocol, its null-distribution inference, its block/time constraints, or its ΔAP/MDE decision rule. S-028's design remains a **methodological extension**, not a copy, of w35227 — and the earlier claim that there is "no financial precedent" is now withdrawn.

---

## 9. Impact on S-028's argument

**What the original text used the alleged non-existence for.** §8.1 (and PHASE_REPORT item 1) used "the Yale paper does not exist" to support two claims: (a) the "shuffle edges / delete structure" device should be attributed to the network-science null-model tradition, not to a finance precedent; (b) S-028's design is therefore an import from network science. `LITERATURE_REVIEW.md` §9 B1 separately claimed the degree+activity+time-preserving null on a bipartite event graph has "no precedent" in the reviewed literature.

**Corrected position.**

1. **Withdraw** the existence claim entirely. w35227 exists, is by a Yale-affiliated author, and is NBER WP 35227 (May 2026).
2. **Withdraw** the claim that the shuffle/struct-deletion device has no finance precedent. w35227 is now the closest finance precedent, and it is closer than any of R42/R43/R44: it does build a relational network over financial entities and does run a topology-destroying, degree-distribution-preserving edge shuffle.
3. **Refine, do not discard, the provenance claim.** The *origin* of constrained randomisation is the network-science null-model tradition; w35227 is an *application* of that logic in finance, at ablation level. S-028 may cite w35227 for the application precedent while still citing the network-science literature for the null-model method.
4. **Novelty must be restated.** S-028 cannot claim "no one has tested whether relations carry information by destroying the graph" — w35227 has, in a financial network. What S-028 can claim, as a **search-scoped** statement, is: *in the literature reviewed here, no located study applies a repeated constrained randomisation (degree + activity + time preserved at block level) with a paired ΔAP/null-quantile/MDE decision rule to a sparse, rare-event, bipartite company–technology regulatory-event graph.* The phrase must be "not located in the reviewed literature", **not** "does not exist".
5. **The plausible inference is strengthened, not weakened.** w35227's result — degree-preserving shuffled edges collapse R² from 6.6% to 2.3% — is evidence that topology matters in holdings networks, which is directly relevant to S-028's own randomised-edge null: if S-028's observed graph were no better than a degree-preserving shuffle, that would be a substantive negative, not a modelling artefact. The correction therefore gives S-028 a better-grounded null-model rationale.
6. **This correction changes no empirical number by itself.** All S-028 numbers (ΔAP, MDE, null quantiles, baseline comparisons) are untouched by this literature correction; only the literature framing and the provenance sentence change. Separately, a concurrent randomisation-implementation audit in the same correction round (`RANDOMISATION_DEFECT_ANALYSIS.md`) invalidates the H2 randomisation-based reversal and introduces corrected N1/N2 null models. The two corrections are independent: this literature correction stands whether or not the H2 finding is reinstated.

**In-place edits made to reflect this:** `LITERATURE_REVIEW.md` §0 (method list + counts + correction block), §8.1 (rewritten on the corrected basis, original wording preserved in this note), §8.2 ①, §8.3 ① and ④, §9 B1, §10 (new [R45] and totals); `PHASE_REPORT_ZH.md` §3 item 1 and §9.3; `artifacts/literature_refs.json` (new R45, PC-01 correction, counts, gaps).

---

## 10. Audit of the "44 references were all fully verified" claim

**The claim as written.** There is no sentence literally saying "44 references were all fully verified"; the strongest forms are:

- `LITERATURE_REVIEW.md` L16: `**结果分布。** 44 条全部标识已核对到实抓记录：verified_primary 44、verified_secondary 0、unverified 0。`
- `LITERATURE_REVIEW.md` L191: `**合计 44 条：verified_primary 44 / verified_secondary 0 / unverified 0；含摘要 23 条、仅题录 21 条、会议归属未核验 10 条、出版年未核验 1 条。**`
- `PHASE_REPORT_ZH.md` L121/L124: `## 3. 文献（已核验，44 条）` / `（44 条全部 verified_primary；23 条读到摘要，21 条仅题录；10 条会议归属未核验，已标记）`
- `PHASE_REPORT_ZH.md` L361: `一份已验证的文献库（44 条，含核验 URL 与状态）`

**What was actually verified.** Recomputed from `artifacts/literature_refs.json` (pre-correction state):

| Level | Count | Notes |
|---|---|---|
| Record identity resolved against one fetched record | 44 / 44 | this is what `verified_primary: 44` actually means |
| Abstract read | 23 / 44 | `claim_scope = abstract` |
| Title/record metadata only | 21 / 44 | `claim_scope = title_record`; Crossref deposits for JSTOR/ACM/OUP/Wiley carry no abstract |
| **Full text read** | **0 / 44** | no reference had a `full_text` field or full-text check |
| Venue attribution verified | 34 / 44 | 10 explicitly `venue_verified: false` (R01, R02, R04, R06, R10, R12, R17, R18, R35, R44) |
| Year verified | 43 / 44 | R20 unverified |
| Affiliation field from a secondary source inside a primary entry | at least 1 | R43's "University College Dublin" is taken from an OpenAlex record (secondary) per its own `verification.notes` |

**Verdict.** The claim is **overstated if read as "the references were fully verified"**. Precisely: all 44 *identities* were resolved to a fetched record, but substantive claims were only abstract-level (23) or title-level (21), no full text was read, 10 venue attributions were left open, and at least one affiliation field came from secondary metadata. The limitation paragraph in `LITERATURE_REVIEW.md` L31 already admits much of this — the overstatement is the summary label "全部核验 / verified_primary 44", which a reader will take as substantive verification.

**Second, more serious scope failure.** The claim "44 条全部核验" was also implicitly a claim about the *search*: that a targeted search plus verified records supports the negative literature statement in §8.1. This audit shows it does not: (i) 0/44 full texts were read, so no method-level negative ("contains no edge-shuffling control") could be supported at that evidence level; (ii) the w35227 record was already inside the reviewer's own recorded result set and was dismissed at title level; (iii) "not found in targeted searches" was converted into "does not exist". The honest scope of the original verification is therefore: **bibliographic identity of 44 records, abstract-level claims for 23, title-level for 21, no full-text checks, no exhaustive database coverage** — and, additionally, one false negative in the coverage claim itself.

**Corrected wording adopted in the in-place edits:** "45 entries: 45/45 identity-level verified; 23 abstract-level; 21 title-level; 1 full-text (R45); 10 venue attributions unverified; 1 year unverified. 'Verified' means the record was fetched and its metadata checked, not that the substantive or method claims were read at source." (Counts after adding R45: 44 old = 23 `abstract` + 21 `title_record`; plus R45 at `full_text`; total 45.)

---

## 11. Remaining UNVERIFIED items (open list for the Lead)

1. w35227's exact edge-shuffle algorithm and whether both degree sequences are preserved (U1–U2).
2. Whether the shuffle preserves time/block structure or position weights (U3).
3. Number of random draws/seeds and whether any null distribution/p-value exists (U4–U5).
4. w35227's holdings-universe cleaning rules (U6).
5. Whether w35227 was revised/accepted after May 2026 (U7) — only the 2026-05 NBER version was read.
6. Coppola's affiliation conflict (U8); JEL class labels (U9).
7. Original 44 references: method/substantive claims unread (0/44 full texts), 10 venues unverified, R20 year unverified, R43 affiliation from OpenAlex (U10).
8. Whether any *other* paper in the 44 has a degree-preserving shuffle control — not re-checked here; only w35227 was read in full.
9. Whether the phrase "randomly permutes edge indices" in the Figure 6 note is a precise description or a loose gloss — cannot be determined without authors' code.

---

## 12. Files changed by this correction, and propagation items outside this write scope

**Changed in this pass (write scope of task-1):**

| File | Change |
|---|---|
| `research/studies/graph_early_signal_s028/LITERATURE_CORRECTION_NOTE.md` | **new**, this document |
| `research/studies/graph_early_signal_s028/LITERATURE_REVIEW.md` | §0 source list/counts/limitations + correction block; §8.1 rewritten with original wording marked corrected; §8.2 ①; §8.3 ①/④; §9 B1; §10 new [R45] + totals |
| `research/studies/graph_early_signal_s028/artifacts/literature_refs.json` | new `R45` entry (with method-level verified/unverified fields); `PC-01` correction block (original fields preserved); counts 44→45; `gaps_not_verified` updated |
| `research/studies/graph_early_signal_s028/PHASE_REPORT_ZH.md` | §3 heading/counts, item 1 rewritten, correction-note pointer, §9.3 asset line |

**Propagation items NOT edited (outside this write scope) — for the Lead:**

- `GRAPH_RESULTS.md` L121 still asserts `不存在"耶鲁 + 金融实体动态关系图 + 边置换对照"` and must be corrected to cite [R45] and the note.
- `REPRODUCE.md` L103 still says "44 references with verification status and fetched URLs" → 45 (or "44 + correction entry").
- `PAPER_DRAFT.md` L49 cites `[R42]–[R44]` for the financial-network literature; consider adding [R45] as the closest graph-structure precedent, and check whether any draft sentence repeats the non-existence claim (none found by grep as of this pass).
- The same "44" count appears in `PHASE_REPORT_ZH.md` §9.3 (edited here) and in `LITERATURE_REVIEW.md` (edited here); a final repository-wide grep for `44 条` / `44 references` is recommended.

**Evidence trail.** All URLs in §4 were fetched on 2026-11-04 (Asia/Shanghai). PDF parsed with pypdf 6.18.1, 67 pages; SHA-256 as recorded in §4. Quotations are from that file; the temporary PDF/text working copies used for extraction were deleted after the audit.

---

## Appendix — exact source snippets used for the headline claims

1. **NBER landing page** (`https://www.nber.org/papers/w35227`): page heading "The Optimal Use of AI in Financial Regulation"; byline "Christopher Clayton & Antonio Coppola"; "Working Paper 35227"; "DOI 10.3386/w35227"; "Issue Date May 2026".
2. **PDF p.1**: "NBER WORKING PAPER SERIES / THE OPTIMAL USE OF AI IN FINANCIAL REGULATION / Christopher Clayton / Antonio Coppola / Working Paper 35227 / http://www.nber.org/papers/w35227 / NATIONAL BUREAU OF ECONOMIC RESEARCH / … / May 2026".
3. **PDF p.1 footnote**: "This paper was previously circulated under the title 'Financial Regulation and AI: A Faustian Bargain?'"
4. **PDF p.2**: "JEL No. C4, G1, G2"; author blocks "Christopher Clayton / Yale University / and NBER" and "Antonio Coppola / Stanford University".
5. **Figure 6 notes (printed p.19)**: "'Shuffled edges' randomly permutes edge indices to destroy network topology while preserving node features and degree distributions."
6. **§3.2 (printed p.20)**: "randomly shuffling edges, while preserving node features and degree distributions, reduces walk-forward R² from 6.6% to 2.3%."
7. **§2 (printed p.9)**: "The holdings graph G_t is bipartite: it has two distinct types of nodes, and edges only connect nodes of different types, with investors connecting to assets via position edges."
8. **§3.1 (printed p.14)**: "the model is retrained from scratch each year on an expanding window of past data and tested strictly on the subsequent year's quarters"; "six annual windows from 2015 to 2020".
