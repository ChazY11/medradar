# A02 — PubTrends (`JetBrains-Research/pubtrends`) external method audit

**Program:** PHOENIX-001 · **Lane:** external methods · **Auditor:** `oss-audit` · **Date:** 2026-11-08
**Scope:** licence, dependency, supply-chain and reproducibility audit of a third-party research
project, plus an isolated reproduction attempt of its algorithm. *Not* a feature review.

**Verdict in one line:** the licence is genuine **Apache-2.0** and the project is actively maintained,
but PubTrends is a **literature-exploration web service with no temporal model and no predictive
metric** — there is no forecasting method to adopt, and its Postgres/Redis/Faiss stack is both
forbidden to deploy here and disproportionate to the value → **STUDY_ONLY**.

---

## 0. Project metadata

| Field | Value |
|---|---|
| Name | PubTrends |
| Official URL | https://github.com/JetBrains-Research/pubtrends |
| Paper | Shpynov, O. & Kapralov, N. (2021). *PubTrends: a scientific literature explorer.* ACM BCB 2021, pp. 1–1, `doi:10.1145/3459930.3469501` |
| Type | production web service: Flask app + Celery worker + Kotlin PostgreSQL loader + embedding/semantic-search micro-services + Bokeh/HoloViews visualisation |
| Licence (code) | **Apache License 2.0** — `LICENSE.txt`, 11,316 B, canonical text |
| SPDX | **`Apache-2.0`** (confirmed from the file, not the README) |
| Copyright holder | `Copyright 2022 JetBrains Research.` (in the licence appendix) |
| Stars / forks / open issues | 50 / 5 / 20 |
| Commits | **2,027** |
| Releases | v0.21 (2022-01-25), v1.0 (2023-09-04), v1.1 (2025-03-14), v1.2 (2025-04-03), v1.3 (2025-06-01), v1.4 (2025-11-03), **v1.6 (2026-01-29)** — note there is no v1.5 tag |
| Last commit | 2026-10-27 (`pushed_at`); repo created 2018-10-04; not archived; **actively maintained** |
| Language | Python + Kotlin + JavaScript/templates. GitHub reports "Jupyter Notebook" because of `notebooks/` |
| LOC | **~10,115 Python + 2,640 Kotlin** ≈ 12.8k excl. templates/JS; 267 blobs; 23 `test_*.py` files; TeamCity CI badge |
| Declared dependencies | **52** in `pyproject.toml`; only three are version-constrained (`bokeh==3.8.2`, `werkzeug<3.1`, `setuptools<70`) plus one direct-URL wheel; the other 48 are entirely unpinned; `requires-python == "3.12.*"` |
| Install method | `uv sync` per `Dockerfile` (`python:3.10-slim`), then Flask/Celery; or 4 × `docker-compose/*.yml` |
| Data needs | PubMed XML baseline/update packs from NCBI FTP (~40M papers / 450M citations) **or** Semantic Scholar Open Corpus (170M papers / 600M citations); PostgreSQL 17 + pgvector; Redis 7.4.2 |
| GPU needed | no (CPU; optional GPU extra for sentence-transformers) |
| Network needed | yes for data load, model weights (Hugging Face / NCBI), and live PubMed/S2 search |
| Paid needed | no (datasets are free; huge) |
| Local accommodation | fetched to `D:\DEPPSKK\phoenix-external\pubtrends`; **full stack deliberately NOT deployed** (brief rule 5); no upstream code executed |

---

## 1. Provenance and maintenance

- Long-lived and genuinely maintained: created 2018-10-04, **2,027 commits**, seven tagged releases
  between 2022-01 and 2026-01, last push 2026-10-27, 20 open issues (normal for an active tool),
  Zenodo DOI `10.5281/zenodo.15131474`, TeamCity build badge in the README.
- Real engineering hygiene that the other audited project entirely lacks: a test suite (23 test
  modules, `testcontainers` for PostgreSQL, mocked loaders), a changelog (`docs/CHANGES.md`),
  `docs/DATABASE.md` and `docs/DEVELOPMENT.md`, flake8 config, and a versioned release process.
- Composition is honest and well-structured: `pysrc/papers/analysis/*` holds the algorithms as small
  pure functions, `pysrc/app` is the web layer, `src/main/kotlin` is the bulk data loader. The
  algorithm layer is unusually readable and is what §5 and §6 concern.
- One provenance caveat worth recording: **`pysrc/version.py` says `VERSION = 'development'` while
  `pyproject.toml` says `version = "1.0.0"`**, and the Docker base image is Python **3.10** while
  `pyproject.toml` requires **3.12.*** — the shipping metadata is internally inconsistent.
- No vendored third-party code and no second licence (see §2), so provenance of the source is clean.

---

## 2. Licence audit

**Finding: Apache-2.0 is genuinely present and unmodified.**

Evidence:

1. `LICENSE.txt` is 11,316 bytes — the canonical Apache License 2.0 text including the APPENDIX
   boilerplate, with the copyright line filled in: `Copyright 2022 JetBrains Research.`
2. In the **complete 267-blob inventory** there is exactly **one** licence file (`LICENSE.txt`). No
   `NOTICE`, no second licence, no dual-licensing.
3. GitHub's detector agrees: `license.spdx_id = "Apache-2.0"`.
4. **No per-file headers**: searching every `.py`/`.kt` for `SPDX-License-Identifier`,
   `Copyright` or `Licensed under` returns nothing. That is normal and compliant for Apache-2.0,
   which relies on the root licence, but it means a file lifted out of the repository must carry the
   licence and attribution explicitly.

**Obligations if any code is ever reused:** keep `LICENSE.txt` and the copyright notice in
redistribution; state modified files (Apache-2.0 §4b); honour the NOTICE convention; no trademark
grant — the "PubTrends"/"JetBrains" names may not be used to endorse a derivative.

**Vendoring:** none. No `vendor/` tree, no third-party copyright notices in source, and the only
binary artefact is `gradle/wrapper/gradle-wrapper.jar` (the Gradle wrapper bootstrap, not vendored
application code). Therefore no sublicensing conflict — the whole source is available under
Apache-2.0, which is the cleanest possible outcome for a licence audit.

This is the decisive contrast with A01: PubTrends is **legally reusable**, SciTrends is not.

---

## 3. Dependency and supply-chain audit

**52** Python dependencies in `pyproject.toml`. Only three carry a version constraint
(`bokeh==3.8.2`, `werkzeug<3.1`, `setuptools<70`) and one is a direct URL; the remaining **48 float
entirely** (`flask`, `celery`, `pandas`, `scikit-learn`, `gensim`, `spacy`, `transformers`,
`onnxruntime`, `faiss-cpu`, `networkx`, `umap-learn`, `psycopg2-binary`, ...). Hazards, most severe
first:

| # | Severity | Finding | Evidence |
|---|---|---|---|
| 1 | **high** | A dependency is installed **directly from a GitHub release URL with no hash**. | `pyproject.toml`: `"en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"` |
| 2 | **high** | The Docker build **executes a remote script**: `curl -LsSf https://astral.sh/uv/install.sh \| sh` — no pin, no checksum. | `Dockerfile` |
| 3 | medium | **Third-party package index** added for torch: `--extra-index-url https://download.pytorch.org/whl/cpu`; `[tool.uv.index]` in `pyproject.toml`. Classic dependency-confusion surface. | `pyproject.toml`, `Dockerfile` |
| 4 | medium | **Committed default credentials + hardcoded secret salt.** `postgres_password = mysecretpassword`, `admin_password = password`; `SECURITY_PASSWORD_SALT` default `"D82CWwxNDzdhB7mbeaAChVd2BjdM9VjR"`. `.env.example` is an **empty file**. | `config.properties`, `pysrc/config.py:62`, `docs/DATABASE.md`, `.env.example` (0 B) |
| 5 | medium | **Unsafe deserialisation** of a cache file with no integrity check → RCE if the cache path is attacker-writable. | `pysrc/papers/compute_or_load.py:136` `return pickle.load(f)` |
| 6 | medium | **Unpinned base images**, and the image's Python (3.10) contradicts `requires-python ==3.12.*`. | `Dockerfile` `FROM python:3.10-slim`; `Dockerfile-test` `FROM eclipse-temurin:21-jre` |
| 7 | low | Runtime model downloads with no digest pin: NCBI BioWordVec and Hugging Face `thenlper/gte-base`. | `pysrc/endpoints/embeddings/fasttext/fasttext.py:10`, `pysrc/endpoints/embeddings/sentence_transformer/sentence_transformer.py` (`AutoTokenizer.from_pretrained`) |
| 8 | low | `ast.literal_eval` on DB text columns — comparatively safe, noted for completeness. | `pysrc/preprocess/embeddings/embeddings_db_connector.py:105,122` |

**Not found:** no `eval()`, no `exec()`, no `os.system`, no `shell=True`, no telemetry/analytics
endpoints. `subprocess` appears only in two test modules that shell out to the Kotlin jar.

**Install-script review (brief rule 4):** I read `Dockerfile`, `Dockerfile-test`, all four
`docker-compose/*.yml`, `pyproject.toml`, `build.gradle`, `scripts/*.sh`, `config.properties` and
`.env.example` before deciding. **Nothing from this project was installed, built or executed** — the
`curl … | sh` line alone is sufficient reason, and the stack is forbidden anyway (rule 5).

**Supply-chain conclusion:** as a *service operated by someone else* the risk is containable; as
something MedRadar would vendor or build, hazards 1–5 would all need pinning, hashing, secret
externalisation and removal of the pickle cache before it could be trusted.

---

## 4. Data dependencies and availability

PubTrends is a **database-backed service**; the code is useless without a populated PostgreSQL.

| Dataset | Size | How obtained | Gated? | Accessible in this audit? |
|---|---|---|---|---|
| PubMed | ~40M papers, ~450M citations (README) | Kotlin `PubmedLoader` pulls NCBI FTP baseline + daily update packs (`pubmed20n*.xml`) into Postgres; `docs/DATABASE.md` documents a cron job | no | **No** — tens of GB, requires a Postgres instance; far beyond the 200 MB budget |
| Semantic Scholar Open Corpus | 170M papers, 600M citations (README) | S2 datasets API bulk release / shards | no (terms apply) | **No** — tens of GB |

Infrastructure demanded by `docs/DATABASE.md`: **PostgreSQL 17**, a **separate pgvector instance** for
semantic search (docs suggest `-m 32G`), **Redis 7.4.2**, a **Celery** worker, a **Faiss** index, and
optional sentence-transformer/fasttext embedding services. Recommended Postgres memory:
`effective_cache_size = 8GB`, `shared_buffers = 2GB`, `work_mem = 1GB`.

**Committed data:** only small test fixtures (`pysrc/test/test_data/*.csv` ≤ 58 KB;
`src/test/resources/articlesPubmed.xml` 119 KB). No derived corpus ships with the repo.

**Availability verdict — BLOCKED for any end-to-end run**, for two independent reasons: dataset scale
(terabyte-class) and the forbidden full stack. This is exactly the case the brief anticipates: *if the
algorithm needs Postgres/Neo4j, extract the algorithm and test its logic on synthetic data in pure
Python.* That is §6.

---

## 5. Method extraction

Entry points: `pysrc/app/pubtrends_app.py` (Flask), `pysrc/celery/tasks_main.py` (async),
`src/main/kotlin/.../Main.kt` (loader). The whole analysis is orchestrated by
**`pysrc/papers/analyzer.py` (`PapersAnalyzer.analyze_papers`, 314 lines)**.

### 5.1 Pipeline, with exact parameters from `pysrc/config.py`

1. **Load** publications, citations-by-year, citation edges, co-citations, bibliographic coupling from
   Postgres (`loader.*`).
2. **Bibliometric graph** (`analysis/graph.py:19-58`): nodes = papers; edge attributes
   `cocitation`, `bibcoupling`, `citation` stored separately.
3. **Text edges** (`graph.py:84-156`): hybrid text similarity
   `0.8·cos(embedding) + 0.2·cos(tfidf)`, each term zeroed when `< SIMILARITY_TEXT_MIN = 0.1`,
   keeping the top `GRAPH_TEXT_SIMILARITY_EDGES = 100` neighbours per node.
4. **Composite edge weight** (`graph.py:11-16`):
   \[
   \text{similarity} = 10\cdot\text{cocitation} + 3\cdot\text{bibcoupling}
   + 1\cdot\text{citation} + 20\cdot\text{textsimilarity}
   \]
5. **Sparsify** (`graph.py:61-81`): greedy k-NN graph, `NODE2VEC_GRAPH_EDGES = 50`, nodes processed by
   descending degree.
6. **Graph embedding** (`analysis/node2vec.py`): node2vec random walks with
   `p = 5.0`, `q = 2.0`, `walk_length = 30`, `walks_per_node = 50`, `seed = 42`, then
   `gensim Word2Vec(vector_size=64, window=5, sg=1, epochs=3)`.
7. **Project** (`analyzer.py:218-223`): `StandardScaler` → `PCA(n_components = PCA_VARIANCE = 0.9)`.
8. **Cluster** (`analysis/clustering.py`): `AgglomerativeClustering` when
   `n_papers ≤ MAX_AGGLOMERATIVE_CLUSTERING = 5000`, else `KMeans`; labels renumbered by descending
   cluster size.
9. **Describe clusters** (`analysis/topics.py:41-79`): for each cluster take summed token counts;
   normalise each token's cross-cluster frequency vector to unit length; score a token by
   `unit_c(token) · log1p(total_count(token))`; take the top `n_words`. Intuition: pick tokens whose
   frequency profile is closest to the cluster's **one-hot** vector, with a frequency prior.
10. **Citation analytics** (`analysis/citations.py`): top-cited papers; per-year **absolute max gain**;
    per-year **relative gain** = `citations_this_year / cumulative_citations_before`, denominator
    guarded `0 → 1`, reported when `≥ 0.01`.
11. Authors / journals (`analysis/metadata.py`); t-SNE only for the scatter plot.

### 5.2 What the method does **not** do (decisive for this audit)

Every module operates on **one current result set**. There is:

- **no train/test split**,
- **no lagged or future target**,
- **no accuracy metric of any kind**,
- **no cluster identity across time** (labels are recomputed per query).

`pysrc/prediction/predict_analyzer.py` is misleadingly named: it issues
`SELECT pmid … ORDER by random() LIMIT {limit}` and then runs the ordinary snapshot analysis. It is a
demo harness for sampling PubMed, **not a forecaster**.

Consequently the brief's questions — "topic change and emerging research areas", "temporal features" —
resolve to: PubTrends renders **per-cluster paper counts by publication year** for the current result
set. That is descriptive trend rendering, not forecasting, and it is not evaluated.

---

## 6. Reproduction attempt

**Status: METHOD_ONLY.** There is no published predictive number to reproduce, and the stack is
forbidden. I therefore reimplemented the distinctive algorithms independently and unit-checked them on
synthetic inputs — including two checks designed to *find* defects rather than confirm behaviour.

### 6.1 What I ran

`experiments/phoenix/external/pubtrends/pt_repro.py` — **my own implementation** written from the
published source semantics and the constants above; it imports nothing from upstream, executes
nothing upstream, opens no database, and deploys no service.

```
python pt_repro.py --out pt_results.json
exit code 0 · 0.04 s · numpy 2.5.1 · 9 checks passed / 0 failed
```

### 6.2 Checks and results

| ID | Check | Result |
|---|---|---|
| A | composite similarity weights reproduce `10·co + 3·bc + 1·cit + 20·txt` | **pass** |
| B1 | node2vec p/q transition probabilities equal the `1/p`, `1`, `1/q` rule — analytic vs 200,000 sampled walks | **pass**, max abs error < 0.005 |
| B2 | first hop is weight-proportional | **pass** (0.75 for a 3:1 weight) |
| B3 | heavier edge gets proportionally higher walk probability | **pass** (0.9 for 9:1) |
| C | k-NN sparsification: every kept edge is top-k for ≥1 endpoint, **but the degree cap is not strict** | **pass** (invariant recorded, see 6.3) |
| D | cluster topic description recovers cluster-specific tokens and **demotes a shared high-frequency token** | **pass** |
| E | clusters relabelled `0 = largest` by descending size | **pass** |
| F | absolute max-gain correct; **relative "hot paper" gain exceeds 1.0** in a paper's first citation year | **pass** (defect recorded, see 6.3) |
| G | no held-out predictive evaluation exists in the repository | **pass** (structural finding) |

### 6.3 Two upstream defects the checks exposed (not my bugs)

1. **`sparse_graph` does not honour its degree cap.** On a synthetic 120-node / 1,051-edge weighted
   graph with `k = 5`, **18 nodes ended with degree 6–7** (max 7). Cause: the greedy loop gates
   insertion on the **peer's** degree (`len(result.neighbors(x)) < k`) but never checks the **current
   node's own** degree before adding its own `k` edges — so a node that already received edges as
   someone else's peer can overshoot up to ~`2k−1`. In production this runs with `k = 50`. The
   *quality* invariant does hold: with consistent tie-breaking, **zero** edges were outside the top-k
   of both endpoints. Impact is bounded (a denser-than-intended walk graph), but the name and the
   constant overstate the guarantee.
2. **The "hot paper" relative-gain metric can exceed 1.0 and is biased to first-citation-year
   papers.** The denominator is cumulative citations *before* the year, guarded `0 → 1`, so in a
   paper's first citation year the metric collapses to the raw citation count (I measured
   `rel_gain = 10.0` for a paper with 10 first-year citations). Since the reporting threshold is only
   `≥ 0.01`, such papers are always admitted — so "hot paper per year" preferentially reports works
   that just started being cited, not works that are accelerating relative to their own history.

Both are recorded as measured facts in `pt_results.json` (checks C and F) and in §9 of this audit.

### 6.4 What was not attempted, and why (honest scope)

- **Full stack** (PostgreSQL + pgvector + Redis + Celery + Flask + Faiss): forbidden by brief rule 5.
- **End-to-end analysis on real data**: terabyte-class corpora, outside budget and forbidden.
- **gensim Word2Vec itself**: I verified the *walk-transition mathematics* that feeds it, which is the
  project-specific part; the Word2Vec implementation is a stock library call.
- Therefore this is explicitly **not** a reproduction of any PubTrends output or screenshot.

---

## 7. Capability overlap with MedRadar

MedRadar already ingests publications via OpenAlex (`medradar/intelligence/sources/publications.py`)
and holds a temporal knowledge graph (`medradar/tkg/`: bitemporal `known_at`/`valid_at` store,
deterministic point-in-time export) plus `graph_context.py`. PubTrends is a different animal.

| Capability | MedRadar | PubTrends | Overlap |
|---|---|---|---|
| publication intake | OpenAlex annual counts, point-in-time knowledge dates | full PubMed/S2 text + citation graph | **weak** — MedRadar deliberately takes counts, not corpora |
| paper–paper graph | `graph_context.py`, `tkg` (entities/relations) | co-citation + bibliographic coupling + citation + text | **conceptual only** |
| literature topic clustering | **none** | core competence | **genuine gap, but not needed by the forecasting lane** |
| temporal discipline | bitemporal store, `available_at`, purged splits, forecast registry | none | **MedRadar far stricter** |
| forecasting | horizon lane 3/6/12/24 months, registry | **none** | **no overlap — nothing to import** |
| regulatory/company intelligence | core | none | none |

The honest summary: PubTrends overlaps MedRadar's **inputs** (bibliographic metadata) but not its
**purpose** (regulatory/industry direction with auditable forecasting). Its "emerging research areas"
framing is descriptive visualisation, whereas MedRadar's programme requires point-in-time, registered,
scored forecasts.

---

## 8. Migration candidates

Small, well-scoped, Apache-2.0-clean — but all would be **reimplementations under MedRadar tests**
rather than imports, because the surrounding data model is entirely different.

1. **Topic description by one-hot cosine (≈40 lines).** The `unit_c(token)·log1p(total)` score is a
   cheap, dependency-free way to label a cluster of papers. Useful *if* MedRadar ever clusters an
   OpenAlex result set into named technology areas; directly portable in spirit to
   `medradar/intelligence/taxonomy.py` work. **Do not adopt now** — MedRadar uses a curated track
   taxonomy, and an auto-labeller would compete with it.
2. **Composite multi-source similarity (≈10 lines).** The weighted blend of co-citation, bibliographic
   coupling, citation and text similarity is a sane default schema if MedRadar builds a paper graph;
   it also documents sensible relative weights (text dominates at 20).
3. **k-NN sparsification (≈20 lines)** — reusable, but **fix the degree-cap defect** rather than
   replicating it if ever adopted.
4. **Do not migrate:** the Flask/Celery/Postgres/Faiss stack, the pickle cache, the relative-gain
   metric (defective), or any configuration defaults.

**Recommendation: none of these should be migrated now.** They are recorded so that a future
"literature clustering" feature starts from a known-good reference instead of a blank page.

---

## 9. Limitations and leakage risks

### Limitations of the project
- It is an **explorer/dashboard**, not a predictive method: no target, no split, no score.
- Heavy operational footprint (Postgres + pgvector + Redis + Celery + Faiss) for what is, functionally,
  a clustering viewer.
- Datasets are terabyte-scale; cannot be exercised without substantial infrastructure.
- **48 of 52** Python dependencies unpinned → the analysis stack is not reproducible in detail.
- All algorithmic constants (p/q, similarity weights, k, thresholds) are hardcoded with **no
  calibration or sensitivity evidence in the repository**.
- Minor metadata inconsistency: `version.py` says `development` vs `pyproject` `1.0.0`; Python 3.10
  image vs `requires-python ==3.12.*`.
- Two measured algorithmic defects (§6.3): k-NN degree cap not enforced; relative-gain metric biased.

### Leakage risks (would matter if anyone used it for trend claims)
1. **No point-in-time discipline.** A result set is clustered using *all* papers returned, including
   papers published after whatever date the user is reasoning about. Any statement like "this area was
   emerging in 2015" derived from a present-day query leaks the future. This is the single most
   important objection to reusing PubTrends for trend detection.
2. **Cumulative citation counts are contemporaneous**, so they are not leading indicators; ranking
   "impact" or "hot" topics with them is look-ahead if used predictively.
3. **Relative-gain metric is biased toward first-citation-year papers** (§6.3), so it measures
   "newly cited", not "accelerating".
4. **Cluster identity is not stable** across queries or years, so "topic X grew" is not a well-defined
   statement in this architecture.
5. **KMeans is seeded only for small sets?** — `cluster_and_sort` calls `KMeans(n_clusters=n_clusters)`
   with **no `random_state`** (unlike node2vec's `seed=42`), so for result sets > 5,000 papers cluster
   membership is non-deterministic between runs.

---

## 10. Decision

### **STUDY_ONLY**

Reasoning:

- **Licence is not the obstacle.** Apache-2.0 is genuine and clean, with no vendored third-party code,
  so reuse would be legally straightforward. This is the opposite of A01, and it is worth stating
  plainly so the program register does not conflate "unlicensed" with "unusable".
- **There is no method to adopt for the forecasting lane.** PubTrends performs snapshot clustering of a
  literature search and renders per-cluster counts by year. It has no train/test split, no future
  target and no accuracy metric; `predict_analyzer.py` is a random-sample demo. Adopting it would not
  move MedRadar's predictive capability by any measurable amount.
- **The engineering cost is disproportionate.** Reusing it means Postgres + pgvector + Redis + Celery
  + Faiss, plus terabyte-scale data loads — for two algorithms that are ~150 lines between them. And
  deploying that stack to evaluate an algorithm is explicitly forbidden by the brief.
- **The two reusable pieces are better reimplemented than integrated**, and neither is on the current
  critical path (MedRadar has a curated track taxonomy, not a paper-clustering need).
- Rejected alternatives: *ADOPT* impossible (a service, not a library; forbidden stack);
  *ADAPT* would imply a migration I would not recommend now, though the pieces are recorded;
  *REJECT* wrong — the licence is clean, the code is high quality and it is a good reference
  implementation of node2vec-on-bibliometrics; *BLOCKED* wrong — the code was fully accessible, only
  the data/stack were out of scope.

---

## 11. Open questions

1. **Is there any calibrated evaluation of the clustering quality at all?** I found tests for
   loaders/graph/text plumbing but no quantitative evaluation of topic quality or stability. If the
   authors have one, it is not in the repository.
2. **What is the intended meaning of "emerging research areas" in the product?** The code renders
   per-cluster counts by year; whether the deployed site adds any interpretive logic (the `questions`
   feature, `pysrc/papers/questions/questions.py`) is unclear without running the service, which was
   out of scope.
3. **Was the k-NN degree-cap behaviour (§6.3) intentional** (a "keep at least one edge" relaxation) or
   an oversight? It changes the walk graph density for every analysis with `k = 50`.
4. **Was the relative-gain defect (§6.3) noticed?** If "Hot papers" is a headline UI feature, the
   metric as written favours newly-cited papers, which is a different message.
5. **Could the topic-description trick be validated as a labeller** against MedRadar's curated track
   taxonomy on an OpenAlex result set? That is the only cheap experiment that would upgrade the
   STUDY_ONLY verdict for piece #1.

---

### Evidence paths

| Artefact | Path |
|---|---|
| This audit | `docs/phoenix/audits/A02_pubtrends.md` |
| Independent reimplementation | `experiments/phoenix/external/pubtrends/pt_repro.py` |
| Machine-readable results (9/9 checks) | `experiments/phoenix/external/pubtrends/pt_results.json` |
| Evidence record | `experiments/phoenix/external/pubtrends/evidence.json` |
| External checkout (outside repo) | `D:\DEPPSKK\phoenix-external\pubtrends` |
| Upstream | https://github.com/JetBrains-Research/pubtrends · `doi:10.1145/3459930.3469501` |
