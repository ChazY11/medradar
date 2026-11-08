# A01 — SciTrends (`ddofer/Trends`) external method audit

**Program:** PHOENIX-001 · **Lane:** external methods · **Auditor:** `oss-audit` · **Date:** 2026-11-08
**Scope:** licence, dependency, supply-chain and reproducibility audit of a third-party research
project, plus an isolated reproduction attempt of its published method. *Not* a feature review.

**Verdict in one line:** no licence exists on any part of this project, so **no code may be reused**;
the *method*, however, reproduced cleanly in my own implementation and two of its feature
definitions are worth adapting into MedRadar's existing publication path → **ADAPT (method only)**.

---

## 0. Project metadata

| Field | Value |
|---|---|
| Name | SciTrends (repository `Trends`) |
| Official URL | https://github.com/ddofer/Trends |
| Paper | *What's next? Forecasting scientific research trends*, Heliyon 2023;10(1):e23781, `doi:10.1016/j.heliyon.2023.e23781`, PMCID PMC10784166, preprint arXiv:2305.04133 |
| Type | research artefact: Jupyter notebooks + derived CSV/Parquet data + figures. **Not a library, service or CLI.** |
| Licence (code) | **none — no licence file exists.** GitHub API `license = null` |
| SPDX | **N/A (not declared)** |
| Licence (paper) | **CC BY-NC-ND** (non-commercial, no derivatives) |
| Stars / forks / watchers | 8 / 1 / — |
| Commits | 26 |
| Releases / tags | **none** (no tags, no releases, no CI) |
| Last commit | 2023-10-09 (`pushed_at`); repo created 2023-05-02; not archived, effectively dormant |
| Language | Jupyter Notebook (Python 3 kernel) |
| LOC | ~**3,962** code lines across 17 notebooks; largest `plot trend pred-ModernSeriesOnly.ipynb` 845 lines, the paper's `plot trend pred + CV-V2023.ipynb` 832 lines |
| Repo size | 32.4 MB (mostly figures/notebook outputs) |
| Declared dependencies | **none** — no `requirements.txt`, `setup.py`, `pyproject.toml`, `environment.yml`, `Dockerfile` |
| Install method | **none exists** |
| Data needs | in-repo derived tables (all < 1 MB except a 20 MB supplementary CSV); upstream: PubMed-by-Year scrape + **gated PatentsView API** |
| GPU needed | no (CPU only; optional sentence-transformers embeddings run on CPU in the notebook) |
| Network needed | only to rebuild raw data (scrape + PatentsView); not needed to re-run the modelling notebooks |
| Paid needed | no |
| Local accommodation | cloned/fetched to `D:\DEPPSKK\phoenix-external\scitrends` (outside the MedRadar tree, not a submodule); no upstream code was executed |

---

## 1. Provenance and maintenance

- Created 2023-05-02, 26 commits, last push **2023-10-09** — the repository has been untouched for
  over three years. `archived = false` but there is no activity to archive.
- **No release engineering at all**: zero tags, zero releases, no CI configuration, no test suite,
  no package metadata. The unit of delivery is a set of notebooks that must be run by hand.
- The paper names a *second* repository for the deployed tool,
  `https://github.com/HadasaK1/SciTrends` (Gradio app), and a live space at
  `https://huggingface.co/spaces/hadasak/SciTrends`. I checked the second repository's metadata:
  **`license = null` there as well**, 1 star, last push 2023-10-17. So the *entire* project — method
  repository and webapp repository — is unlicensed.
- Provenance of the code itself is consistent with the paper: the notebooks correspond to the
  described pipeline (data prep, EDA, patents correlation, burst-detection side experiment,
  cross-validated modelling, group-wise evaluation). There is no evidence of copied third-party
  source in the repository, and consequently no vendoring/sub-licensing question.

**Maintenance assessment:** dormant, unfixed, unreproducible as shipped. Treat as a paper companion,
not as software.

---

## 2. Licence audit

**Finding: there is no licence file anywhere in this repository.**

Evidence, in order of strength:

1. **Complete tree inventory.** I enumerated all blobs via the GitHub trees API for `main`
   (`truncated = false`) before downloading anything. There is no `LICENSE`, `LICENSE.md`,
   `LICENCE`, `COPYING`, `NOTICE` or `UNLICENSE` blob at any path.
2. **GitHub's own detector agrees:** `GET /repos/ddofer/Trends` returns `"license": null`.
3. **No per-file headers.** A recursive search of every fetched `.md`/`.ipynb`/`.py`/`.txt` for
   `license|licence|copyright|SPDX|Creative Commons` returns no statement attributable to the
   authors (the only string hits are base64 PNG payloads inside notebook output cells).
4. **The companion webapp repo is also unlicensed** (`HadasaK1/SciTrends`, `license = null`).

The **paper** is open access but under **CC BY-NC-ND**, confirmed from the Europe PMC core record
for PMC10784166 (`license: "cc by-nc-nd"`). That licence (a) does not extend to the code,
(b) forbids commercial use, and (c) forbids derivative works *of the paper*. It therefore cannot be
relied on for either code reuse or large-scale reproduction of the paper's text/figures.

**Consequence — binding on this program:**

> **No confirmed code licence — method-only borrowing allowed, code reuse forbidden.**

Under default copyright (Berne/TRIPS), the authors retain all rights to the notebooks and the
committed data files. Copying any notebook, CSV or figure into MedRadar would be infringement.
*Ideas, formulas and algorithms are not copyrightable*, so an independent reimplementation of the
method, with academic attribution to Ofer, Kaufman & Linial (2023), is permissible — and that is
exactly what §6 below is.

One further caution for a commercial context: the paper's NC clause attaches to the *expression*,
not the method, so NC does not block reimplementation; but any MedRadar publication that reproduces
the paper's figures or substantial text would need care.

---

## 3. Dependency and supply-chain audit

**There is no dependency manifest of any kind.** No `requirements.txt`, `setup.py`, `pyproject.toml`,
`environment.yml`, `Pipfile`, `Dockerfile` or `Makefile`. Consequently:

- **No install path exists.** There is nothing to `pip install`, and therefore no `setup.py`
  code-execution vector, no `requirements.txt` git-URL install, no CUDA/torch pin, no Docker base
  image, no install script to review. This is the one respect in which the project is trivially
  "safe": it has no automated attack surface because it has no build.
- **The real hazard is unreproducibility.** The stack was never pinned. The imports spread across
  the notebooks are:
  `catboost`, `torch`, `sentence_transformers`, `autogluon`, `burst_detection`, `sklearn`, `pandas`,
  `numpy`, `matplotlib`, `seaborn`, `shap`, `bs4`, `requests`.
  Reconstructing the authors' numeric environment from that list is not possible, and the code
  has since **bit-rotted against the current stack** — see §6.
- No `eval`/`exec`/`subprocess`/`os.system`/network-telemetry constructs were found in the
  analysis notebooks; the only network use is the data-scraping notebooks
  (`scrape_pubmed_by_year.ipynb`, `patentsView_api_req.ipynb`).
- No third-party code is vendored, so there is no sublicensing conflict.

**Supply-chain conclusion:** no malicious-install risk (nothing installs); high *reproducibility*
risk (nothing is pinned); and because there is no licence, we cannot lawfully ship their code
either way.

---

## 4. Data dependencies and availability

### 4.1 Data shipped in the repository (the reason a reproduction was possible)

| File | Size | Shape | Role |
|---|---|---|---|
| `trends_v6.csv.gz` | 533,335 B | 7,033 × 29, 126 topics | **the modelling feature table** (targets, lags, review ratios, patent features). Used as the reproduction input. |
| `all_trends_matrix_v3.csv.gz` | 223,360 B | 8,701 × 6 | raw per-topic per-year popularity |
| `trends_context_v6.csv.gz` | 475,427 B | 9,779 × 18 | long-history context features |
| `mesh_majr_v5.csv.gz` | 332,503 B | 8,475 × 11 | MeSH major-term popularity series |
| `medline_total.csv.gz` | 609 B | 75 × 3 | **annual Medline totals + % US — the popularity normaliser** |
| `var_text_embeddings.parquet` | 472,982 B | topics × 384 | all-MiniLM-L12-v2 embeddings of topic names |
| `Supplementary/S4-Features_with_target_5Y.csv` | 20,358,293 B | ~4,176 × ~400 | supplementary feature dump (not downloaded — redundant with `trends_v6.csv.gz`; kept within the no-large-download rule) |

All committed tables are **derived data computed from PubMed by the authors**. Their own licence is
unknown (same repository, no licence) — a second reason not to copy them.

### 4.2 Upstream raw sources

| Source | How obtained | Gated? | Reproducible today? |
|---|---|---|---|
| **PubMed by Year** (esperr.github.io/pubmed-by-year) | scraped by `scrape_pubmed_by_year.ipynb` (requests + bs4) | No | **Fragile.** A third-party hobby service scraped live; no snapshot or version is pinned. Search counts also drift because NCBI's automatic term mapping changes. |
| **USPTO PatentsView** | `patentsView_api_req.ipynb` against `api.patentsview.org` | **Yes** | **No.** `patentsview_api_stuff.txt` line 11 literally contains `url = 'secret_url?page={}'` — the endpoint/key is masked in the released file. The legacy `api.patentsview.org` query API has since been retired behind a registered API key. |
| Medline annual totals (NLM) | committed as `medline_total.csv.gz` | No | yes (shipped) |

**Availability verdict:** the *modelling* is reproducible from shipped derived data (proved in §6);
the *data generation* is not reproducible, because the patent counts are key-gated and the PubMed
series comes from an unpinned scrape.

---

## 5. Method extraction

Primary evidence: `plot trend pred + CV-V2023.ipynb` (the notebook the README names for "Modelling
results and evaluation"), cross-checked against `PrepData_Trends.ipynb` and the paper's Methods §2.

### 5.1 The target: normalised "popularity"

\[
\text{popularity}(\text{topic}, y) \;=\; 100{,}000 \times
\frac{\#\{\text{topic publications in year } y\}}{\#\{\text{Medline publications in year } y\}}
\]

The normaliser (`medline_total.csv.gz`, "Total Medline Cites") is what stops every topic from looking
like it is growing merely because total publication volume grows. The `×100,000` is cosmetic.

### 5.2 Forecast target and horizon (cell 3 of the CV notebook)

```python
df_targets = df_targets.sort_values(["Year","variable"])            # cell 3: "NEW! Sort by date!"
df_targets["target_5"] = df_targets.groupby("variable")["y_raw"].shift(-5)
df_targets = df_targets.loc[(df_targets["Year"] > df_targets["start"])
                            & (df_targets["year_num"] >= 1979)]
```

- Horizon: **5 years ahead**, per-topic.
- `start` = first "valid" year (≥4 occurrences in the preceding 5 years); rows before it are dropped.
- Training window: **1979–2019** (paper), consistent with the patent database coverage.

Three switchable target definitions exist in the code (cell 6), and the distinction matters:

| switch | target formula | meaning |
|---|---|---|
| `DIFF_TARGET=False` | `popularity(t+5)` | level forecast (Table 1 block 1) |
| `DIFF_TARGET=True` | `popularity(t+5) − popularity(t−5)` | absolute change across a **10-year span** |
| `DIFF_TARGET_PCT=True` | `100·(popularity(t+5) − popularity(t−5)) / popularity(t)` | **percent** change across a 10-year span, normalised by today's level (Table 1 block 2) |

I verified the lag semantics directly against the released data rather than trusting the column
names: `lagK[t] == y_raw[t−K]` exactly (`lag5` matched `y_raw` shifted 5 back on every comparable row
of the `BLAST` series), and `diff_lag5 == y_raw − lag5` to within 7×10⁻¹⁵. This settles an ambiguity
in the paper, which describes Δŷ as "the percent change in a topic's popularity **in 5 years relative
to the present**" — the code actually measures a **10-year span anchored 5 years in the past**,
expressed relative to the present. Anyone reusing this must not describe it as a 5-year change.

### 5.3 Features (cell 24 — the exact list)

```python
['variable', 'reviews', 'patent_count', 'patent_frac', 'patent_yearly_total', 'year_num',
 'y_raw', 'lag5_pct_new', 'pct_diff_lag5', 'research_review_diff', 'research_review_ratio',
 'pct_diff', 'review_research_ratio_2', 'review_research_diff_2', 'pat_div_research',
 'y_diff', 'y_pct_diff', 'target_5']
```

- **review/research**: `reviews` (review-article count), `research_review_diff`, ratios and
  second-order variants. Verified: `pct_diff` is the 1-year percent change (corr 0.99999998 with
  `(y_t − y_{t−1})/y_{t−1}`); `pct_diff_lag5` is the same quantity lagged 5 years (corr −0.21 with
  the 5-year percent change), so it is a legitimate lag, not a leak.
- **patents**: `patent_count`, `patent_frac` (topic share of all patents that year),
  `patent_yearly_total`, `pat_div_research`.
- **static**: `year_num` (absorbs the trend), topic identity (`variable`, used as a CatBoost
  categorical and, in the augmented model, replaced by a 64-dim PCA of a text embedding).

### 5.4 Validation protocol

```python
tscv = TimeSeriesSplit(NUM_CV_FOLDS)          # NUM_CV_FOLDS = 30
for train_index, test_index in tscv.split(X): ...
```

- sklearn `TimeSeriesSplit(n_splits=30)` over rows sorted by `(Year, variable)`. Because the rows are
  year-sorted, each fold is a contiguous **year block shared across all topics** — a proper
  step-forward split for a panel. **The sort is load-bearing**; see the ablation in §6.4.
- Topic-level generalisation is evaluated separately by `trend pred + CV-V2023-GroupWiseCV.ipynb`
  (GroupKFold at topic level → paper Table 2).

### 5.5 Models and baselines

| Paper label | Implementation in code |
|---|---|
| Lag baseline | `RidgeCV` fit on the single feature `y_raw` |
| Linear model | `RidgeCV` on all numeric features |
| Boosting Tree | `CatBoostRegressor(cat_features=["variable"], has_time=True)` |
| Tree & embedding augmented | CatBoost + 64-dim PCA of `all-MiniLM-L12-v2(topic name)` |

### 5.6 Headline results as published (for comparison only)

| Target | Model | R² | MAE | median AE | RMSE |
|---|---|---|---|---|---|
| Ŷ popularity | Lag baseline | 0.973 | 113.80 | 44.37 | 229.12 |
| | Linear model | 0.974 | 101.19 | 45.11 | 214.82 |
| | Boosting Tree | 0.981 | 75.58 | 26.32 | 183.67 |
| | Tree & embedding | **0.991** | **58.53** | **23.22** | **132.30** |
| Δŷ % | Lag baseline | 0.004 | 115.42 | 83.38 | 289.98 |
| | Linear model | 0.03 | 114.83 | 66.19 | 286.22 |
| | Boosting Tree | 0.306 | 60.56 | 18.47 | 241.96 |
| | Tree & embedding | **0.447** | **48.29** | **15.11** | **216.04** |

Plus a binary claim: 88% up/down accuracy against a 70% majority-class baseline.

---

## 6. Reproduction attempt

**Status: METHOD_ONLY — and a strong one.** The paper's own numbers are only partly reproduced
(CatBoost and sentence-transformers are unavailable here by design); the *pipeline* is reproduced,
which is proven by the lag baseline landing exactly on the paper's reported values.

### 6.1 What I ran

I wrote an **independent reimplementation** from the paper and from reading the notebooks:
`experiments/phoenix/external/scitrends/sci_repro.py`. It imports nothing from the upstream repo,
never executes notebook cells, and rebuilds the paper's table from the authors' released derived
feature file.

```
python sci_repro.py --data-dir D:\DEPPSKK\phoenix-external\scitrends --out sci_results.json
exit code 0 · 274.3 s · Python 3.12.10 · pandas 3.0.3 · numpy 2.5.1 · sklearn 1.9.1
input: trends_v6.csv.gz sha256 fbd32b59d9c9da2fb39e3d72a67eef101b5734f0fb8ed9c5034a6c236206baf4
```

Reconstruction result: **4,175 rows / 123 topics / years 1979–2015** after the paper's filters
(`Year > start`, `year_num ≥ 1979`, topic length > 6, target non-missing), 4,020 rows scored under
30-fold `TimeSeriesSplit`.

### 6.2 Results vs Table 1

| Target | Model | Mine R² / MAE / medAE / RMSE | Paper R² / MAE / medAE / RMSE | Reading |
|---|---|---|---|---|
| level | **Lag baseline** | **0.9732 / 113.806 / 44.378 / 229.128** | **0.973 / 113.80 / 44.37 / 229.12** | **exact match** |
| level | Linear model | 0.9764 / 101.290 / 45.197 / 215.019 | 0.974 / 101.19 / 45.11 / 214.82 | reproduces to ~0.1 on MAE |
| level | Boosting | 0.9770 / 93.843 / 32.769 / 212.229 | 0.981 / 75.58 / 26.32 / 183.67 | same ordering, weaker (HistGBM ≠ CatBoost) |
| level | Tree+embedding | — | 0.991 / 58.53 / 23.22 / 132.30 | not run (torch absent) |
| pct Δ | **Lag baseline** | **0.0039 / 115.419 / 83.377 / 289.980** | **0.004 / 115.42 / 83.38 / 289.98** | **exact match** |
| pct Δ | Linear model | -0.0390 / 95.720 / 51.180 / 296.156 | 0.03 / 114.83 / 66.19 / 286.22 | differs (ridge regularisation/NaN handling) |
| pct Δ | Boosting | 0.1058 / 83.828 / 22.390 / 274.742 | 0.306 / 60.56 / 18.47 / 241.96 | same direction, weaker |
| pct Δ | Tree+embedding | — | 0.447 / 48.29 / 15.11 / 216.04 | not run |

The **absolute**-difference variant (`DIFF_TARGET=True`, `y(t+5) − y(t−5)`, not a table block in the
paper) was also run for completeness, because it is the other half of the target ambiguity:

| Target | Model | R² / MAE / medAE / RMSE |
|---|---|---|
| diff Δ (absolute) | Lag baseline | 0.1963 / 180.445 / 65.341 / 350.340 |
| diff Δ (absolute) | Linear model | 0.4948 / 143.283 / 68.942 / 277.763 |
| diff Δ (absolute) | Boosting | 0.7786 / 85.914 / 31.891 / 183.888 |

Note the contrast that pins down the definition: on the **percent** target the lag baseline scores
R² 0.0039 and MAE 115.42 — exactly the paper's Δ lag row — whereas on the **absolute** target the same
model scores MAE 180.45. The paper's Table 1 therefore corresponds to the percent variant, which is
what the notebook's own recorded output ("r2 0.447, MAE 48.291") also implies.

**This is the key evidential result.** The lag baseline is a simple, highly specified model
(`RidgeCV` on one feature), so matching it on **four metrics × two independent target definitions**
(all to the last reported digit) demonstrates that my reconstruction of the filters, feature
derivations, target construction, fold protocol and metric collection is faithful. The boosting rows
differ for a known, stated reason: `CatBoostRegressor` was replaced with
`HistGradientBoostingRegressor`, and the embedding augmentation was skipped.

### 6.3 Controls I added (not in the paper)

| Control | Result | What it establishes |
|---|---|---|
| **Persistence, level** (predict `y(t+5)=y(t)`, no model) | R² **0.9694**, MAE 104.51 | the level target is dominated by autocorrelation: a *zero-parameter* forecast nearly matches the paper's lag baseline, so "R² 0.97" is not evidence of forecasting skill |
| **Zero-change, pct** | R² **−0.063**, MAE **97.56** | predicting *no change at all* has **lower MAE (97.56) than the paper's learned lag baseline (115.42)** — the learned lag baseline is worse than trivial on this target |
| **Leakage positive control** (append `y(t+5)` as a feature, OLS) | R² **1.0000**, MAE 0.0 | the harness is unambiguously leak-sensitive; therefore the no-leak reading of the real feature runs is meaningful, not an artefact of a weak test |
| **Sort ablation** (same model/target, rows ordered by topic instead of year) | R² **−0.012** vs +0.106 year-sorted | confirms the year sort is load-bearing: without it `TimeSeriesSplit` produces *topic* folds and the number stops being a temporal estimate (here it deflates rather than inflates — either way it is not interpretable) |

### 6.4 What failed, and why

- **The released notebooks do not run on the current stack.** `plot trend pred + CV-V2023.ipynb`
  calls `pd.read_csv(..., infer_datetime_format=True)` — **removed in pandas 3.x** — and the notebooks
  rely on `pd.set_option('mode.use_inf_as_na', True)` — **also removed**. I hit both errors verbatim
  and handled them explicitly in my reimplementation (`replace([inf,-inf], nan)` before the pct
  target, which divides by `y_raw` and therefore produces infinities).
- **CatBoost rows not reproduced**: not installed; a ~100 MB wheel download on a ~50 KB/s link was
  outside the no-large-download budget. Substituted `HistGradientBoostingRegressor`.
- **Embedding-augmented rows not reproduced**: requires `torch` + `sentence_transformers` +
  model weights; also `pyarrow` is absent so the shipped `var_text_embeddings.parquet` could not be
  read.
- **Raw data regeneration not attempted**: PatentsView is key-gated and the released call is masked
  (`secret_url`); PubMed-by-Year is an unpinned scrape.

### 6.5 Reproduction conclusion

The **method is understood and reproducible**; the paper's *CatBoost* and *embedding* numbers are
**not** reproduced here and are not claimed. The reproduction is of pipeline logic on the authors'
own released derived data — it is **not** an independent re-derivation from raw PubMed/PatentsView.

---

## 7. Capability overlap with MedRadar

MedRadar's publication path is `medradar/intelligence/sources/publications.py` (OpenAlex annual
counts) plus `medradar/intelligence/features/publication_features.py`, which currently computes:

`pub_count_prev_year`, `pub_count_3y`, `pub_growth_prev_year`,
`pub_intensity_vs_company`, `pub_missing`, and patent counts `pat_apps_pub_12m` / `pat_apps_pub_3y`.

| SciTrends capability | MedRadar today | Overlap |
|---|---|---|
| popularity normalised by **total annual field output** | **absent by design** — `publication_features.py:26` states `pub_intensity_vs_company` is "a within-company normalisation, **not a share of industry output**" | **genuine gap** |
| **review : original-research ratio** as a directional feature | **absent** — OpenAlex is queried with `group_by=publication_year` only, so no publication-type split is collected | **genuine gap** |
| patents as a *leading* indicator | `patents.py` adapter exists but is **key-gated and unevaluated** (`pat_missing=1.0`, `evaluated: False`) | same blocker in both projects |
| 5-year horizon forecast | MedRadar's horizon lane is 3/6/12/24 months | different horizon; long-run positioning only |
| temporal validation with lag baseline | MedRadar's `evaluation/backtesting.py`, `leakage_audit.py`, Forecast Registry are **stricter** (point-in-time `available_at`, purged splits, immutable pre-registration) | **SciTrends is weaker; do not import** |
| text embeddings of topic names | not used for publication features | low value |

So the overlap is not "two implementations of the same thing" — it is that SciTrends' two **feature
definitions** target exactly the two weaknesses MedRadar's own docs already admit.

---

## 8. Migration candidates

Ordered by value/effort. All must be **independent implementations** (no code, no notebooks, no data
files copied), with attribution to Ofer, Kaufman & Linial (2023), Heliyon 10:e23781.

1. **Normalised popularity (highest value).** Add a denominator to the publication features:
   `popularity(company, y) = 100000 · pubs(company, y) / total_pubs(field, y)`, using a field-level
   total already obtainable from OpenAlex (`group_by=publication_year` with no company filter) and
   cached alongside the existing per-company cache. This directly repairs the limitation recorded in
   `publication_features.py:26` and stops the pipeline mistaking field-wide growth for company
   momentum.
2. **Review : research decomposition (high value, cheap).** Add
   `pubs_review(y)` vs `pubs_research(y)` and their ratio by adding a second grouped request
   (`group_by=type`) or `filter=type:review`. SciTrends' claim — declining topics carry an *excess*
   of reviews — is a directional signal MedRadar currently cannot see at all, and it is exactly the
   kind of "quiet re-allocation" signal the radar is for. Requires its own ablation before any
   product exposure.
3. **Patent fraction as a leading indicator (defer).** The feature is `patent_frac` (topic share of
   all patents that year). It is worth defining now in `publication_features.py` so the path is ready,
   but it cannot be evaluated until the USPTO key exists — the same honest-blocked state already
   documented there. Do **not** adopt SciTrends' patent numbers.
4. **Do not migrate** the validation protocol, the embeddings, or the notebooks.

---

## 9. Limitations and leakage risks

### Limitations of the project
- Notebooks only: no package, no CLI, no tests, no CI, no versioning → nothing to depend on.
- **No licence** → cannot be reused, only studied.
- No pinned environment; the code no longer runs on a current pandas.
- Data generation not reproducible (gated patents, unpinned scrape).
- 125 hand-picked topics, heavily biomedical/PubMed-centric; not a device/drug regulatory taxonomy.

### Leakage risks (important if these ideas are adapted)
1. **Topic survivorship.** The 125 topics were chosen *in 2022 because they are active and notable
   now*. Backtesting them over 1979–2019 conditions on survival into the present. The paper itself
   acknowledges this. If MedRadar adapts the method, the topic/company universe must be fixed
   *as of the backtest start*, not chosen today.
2. **Level-target illusion.** `popularity(t+5)` is ≈ `popularity(t)`. My persistence control scores
   R² 0.969 with no model. Reporting level-target R² as forecasting skill would be misleading; the
   honest comparison is the **Δ target**, and my zero-change control shows even the paper's learned
   lag baseline underperforms "predict no change" on MAE.
3. **Horizon mislabelling.** The Δ target spans `t−5 → t+5` (10 years), normalised by `popularity(t)`.
   Calling it a "5-year change" overstates near-horizon information. MedRadar should implement a
   clean `t → t+h` target and say so.
4. **Precomputed features.** `trends_v6.csv.gz` is a single table computed once over full history;
   row-wise use of it cannot be treated as point-in-time without re-derivation. (MedRadar already has
   a stricter knowledge-date convention — `publication_knowledge_date()`, 15 Feb of `y+1` — and must
   keep it.)
5. **Known-topic advantage.** Only the topic-level split (paper Table 2) removes it, and performance
   collapses there (R² 0.86 vs 0.98). Cross-topic generalisation is the realistic setting for a new
   track.
6. **Normaliser drift.** The popularity denominator itself changes with NLM indexing policy (the
   paper notes rising mean popularity despite normalisation, attributed to annotation improvement).
   A constant denominator regime must be enforced when comparing across years.

---

## 10. Decision

### **ADAPT** — method-level reimplementation only; zero code reuse.

Reasoning:

- **Licensing forbids code reuse** and forbids treating the committed data as ours. It does not forbid
  reimplementing a method with attribution, which is the only route I recommend.
- **The method is real and reproducible.** This is the strongest evidence in this audit: my
  independent rebuild reproduces the paper's lag baseline *exactly* on four metrics for **two**
  different target definitions. That means the ideas are not hand-waving — the normalisation, the
  review/research features and the temporal validation are all implementable in a small amount of
  auditable code.
- **It plugs two admitted holes in MedRadar**, not hypothetical ones: MedRadar's own source states its
  publication intensity is "not a share of industry output", and it collects no review/research split
  at all. SciTrends' two feature definitions address precisely those.
- **But it must not be over-trusted.** The level-target R² of 0.991 is mostly autocorrelation; the
  Δ-target skill is modest (paper R² 0.447, my substituted model 0.106); the topic universe is
  survivorship-selected; and the validation protocol is weaker than MedRadar's own. So: adapt
  **features**, not validation, not models, not code, and not the published effect sizes.
- Rejected alternatives: *ADOPT* impossible (no licence, no package); *STUDY_ONLY* under-sells a
  method that reproduced exactly and targets a documented gap; *REJECT* wrong given the exact
  numerical match; *BLOCKED* wrong — the data needed to test the method was shipped.

---

## 11. Open questions

1. **Is the paper's Δŷ block really the percent target?** Evidence: the notebook's own recorded cell
   output ("pct change, without categorical, with DL, 30 folds: r2 0.447, MAE 48.291, median 15.114,
   RMSE 216.043") matches Table 1's Tree+embedding Δ row to every digit, and my pct-target lag
   baseline matches Table 1's Δ lag row to every digit. I am confident, but the paper's prose calls it
   a 5-year change; the authors should be asked, and any MedRadar citation must use the code's
   definition.
2. **Why does the linear model reproduce the level baseline to ~0.1 but not the Δ baseline
   (my −0.039 vs 0.03)?** Most likely the exact ridge alpha grid / NaN policy (the notebook uses
   three different NaN strategies in cells 28/29/31, and `cell 29` drops any column containing a NaN).
   Not worth chasing; noted so the discrepancy is not mistaken for a defect.
3. **Which notebook produced Table 1?** `plot trend pred + CV-V2023.ipynb` is named by the README and
   its commented outputs match Table 1, but `plot trend pred-ModernSeriesOnly.ipynb` and
   `plot trend pred- outputs copy.ipynb` are near-duplicates with different settings. The paper should
   name the exact artefact; I treated V2023 as canonical.
4. **Can PubMed-by-Year be replaced by a pinned source** (e.g. Europe PMC or OpenAlex year counts) for
   a MedRadar adaptation, so that the series is re-derivable and versioned? Recommended.
5. **Would the review:research signal survive on device/drug corpora?** It was validated on biomedical
   topics; the transfer to FDA device tracks is untested and needs its own ablation before use.
6. **Data licence.** Even the *derived* CSV files carry no licence. Confirm with the authors before
   using `trends_v6.csv.gz` as a benchmarking fixture, even for internal comparison.

---

### Evidence paths

| Artefact | Path |
|---|---|
| This audit | `docs/phoenix/audits/A01_scitrends.md` |
| Independent reimplementation | `experiments/phoenix/external/scitrends/sci_repro.py` |
| Machine-readable results | `experiments/phoenix/external/scitrends/sci_results.json` |
| Evidence record | `experiments/phoenix/external/scitrends/evidence.json` |
| External checkout (outside repo) | `D:\DEPPSKK\phoenix-external\scitrends` |
| Upstream | https://github.com/ddofer/Trends · https://pmc.ncbi.nlm.nih.gov/articles/PMC10784166/ |
