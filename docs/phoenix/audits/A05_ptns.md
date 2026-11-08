# A05 — PTNS: patent citation trajectory prediction (M5)

Audit of: **Ding M, Yu W, Zeng T, Wang S. "PTNS: patent citation trajectory prediction based on temporal
network snapshots." Scientific Reports 2024;14:24034.** doi:[10.1038/s41598-024-75913-0](https://doi.org/10.1038/s41598-024-75913-0)
· [PMC11473824](https://pmc.ncbi.nlm.nih.gov/articles/PMC11473824/)

| Field | Value |
|---|---|
| Name | PTNS — patent citation trajectory prediction via temporal network snapshots (R-GCN + BiLSTM + PCA + Richards curve) |
| Official URL | https://www.nature.com/articles/s41598-024-75913-0 (publisher page redirects to an identity provider for the PDF); full text read from [PMC11473824](https://pmc.ncbi.nlm.nih.gov/articles/PMC11473824/) and [Europe PMC](https://europepmc.org/article/MED/39402175) |
| Type | Public paper (Scientific Reports, open access, CC BY-NC-ND per Europe PMC metadata) |
| Licence / terms | CC BY-NC-ND 4.0 (Europe PMC `license` field: `cc by-nc-nd`). Non-commercial, no derivatives — relevant if MedRadar wanted to reuse any figure or excerpt verbatim. |
| Code public? | **No.** No code-availability statement; no GitHub/Zenodo/figshare link anywhere in the article (full text searched). |
| Data public? | **No.** Data-availability statement (verbatim): "The data shall be made available on request from the first author or the corresponding author." The underlying corpus is Incopat, a **commercial** patent database. |
| Access barrier | Article free (PMC). Code and data behind author request / commercial subscription. |
| GPU / paid needed | **Yes** for replication: PyTorch 2.2.1 + CUDA 12.1, NVIDIA RTX 4060 Laptop GPU, ~46 min training per full run, 3 runs averaged. Also needs Incopat access. |
| Reproducibility status | **Not reproducible.** No code, no data, commercial source database, no parameter-complete description (several equations are images; see §1). Method and evaluation protocol were extracted and re-implemented as logic only, exercised on synthetic data. **No original result was reproduced, and none is claimed.** |

---

## 1) What the source actually says

Task (Introduction / Task Definition):

> "this paper proposes a patent citation trajectory prediction model (PTNS) based on temporal network
> snapshots. It adopts relational graph convolutional networks (R-GCN) to learn the complex relationships among
> multiple attributes of patents and utilizes bidirectional long short-term memory networks (BiLSTM) to
> aggregate the temporal evolution differences of patents. Subsequently, principal component analysis (PCA) is
> used to explore the evolution characteristics of patent citations in depth, thereby capturing the aging effect
> and the 'sleeping beauty' phenomenon."

Snapshots (Research process, step 2 — Network Snapshot Construction):

> "the publication date information of patents is introduced" … "historical patent data can be divided into T
> network snapshots based on the publication year"

Four entities and four relations (Table 1), verbatim rows:

| # | Relationship | Entity |
|---|---|---|
| 1 | technical classification | (publication number, IPC classification code) |
| 2 | cited by | (publication number, publication number) |
| 3 | applied by | (publication number, applicant) |
| 4 | belongs to | (publication number, publication country) |

Relational encoding (R-GCN), Eq. 2 (equation is a raster image; the surrounding prose defines the pieces):

> "h_i^(l+1,t) … ω_ij^(r,l) … ω_ij^(r,l←t-1)" style terms for "the aggregation weight of node i in layer l",
> neighbours "with relational attribute r", and "the aggregation features weight from time t-1 to time t";
> "When [l=1] there are no previous neighbor feature transformations, hence it's a regular R-GCN; when [l>1],
> the R-GCN model can aggregate previous neighbor features, thereby retaining evolutionary differences."

Temporal aggregation: BiLSTM over the snapshot sequence, with two weights ("high & low") for primary vs
secondary IPC and first vs other applicants (Eq. 4). Trajectory fitting: PCA, then four MLPs emit the four
Richards (generalised logistic) parameters, Eq. 5:

> "the Richards growth curve model, the generalized logistic curve, is used … an epidemic (generalized logistic
> curve) model is adopted for fitting and visualization of results"

Metrics (Loss function):

> "MALE: Mean Absolute Logarithmic Error, refers to the mean squared difference between the logarithms of the
> predicted values and the logarithms of the actual (true) values" — note this sentence conflates *absolute* and
> *squared*; the equation itself is an image.
> "RMSLE: Root Mean Squared Logarithmic Error, which is the mean squared difference between the logarithms …"

Dataset (Dataset construction):

> "Based on the classification of the national economy of the polyurethane field and the International Patent
> Classification (IPC) specifically related to it, a total of 133,857 invention and utility model patents with
> publication years ranging from 2004 to 2023 were retrieved from the Incopat database."

Splits and protocol:

> "the first 10 network snapshots are utilized for feature learning, while the subsequent 10 snapshots are used
> for evaluation. The ratio of partitioning between the training and testing sets is 2:1."

Subtask definitions (verbatim): "New Patents: … low citation frequencies, less than 2." · "Grown Patents: …
high historical citation frequencies, greater than 4." · "Random Patents: … randomly sampled without restricting
the citation frequency."

Hyperparameters (Table 3): 2 R-GCN layers, hidden 64, graph_emb 128, influence_emb 128, dropout 0.5, batch 128,
lr 0.01, 35 epochs, "final experimental results were based on the average of three runs".

Baselines: TGNN, HINTS, HDGNN, DeepCCP. Reported headline: RMSLE lower by "approximately 0.04, 0.14, and 0.18"
and MALE by "approximately 0.04, 0.12, and 0.16" for new/grown/random patents; PTNS runtime ≈46 min (HDGNN ≈60,
TGNN ≈2).

**Two internal inconsistencies found in the text (verified quotes, not my paraphrase):**

1. *Domain.* The Introduction says the empirical analysis uses "patent data from the aviation industry", while
   §Dataset construction and §Polyurethane field say the corpus is **polyurethane** patents. The aviation
   sentence appears to be a leftover; the actual corpus is polyurethane.
2. *Split.* "first 10 … subsequent 10 … ratio … 2:1" is arithmetically inconsistent (10:10 is 1:1). Presumably
   the 2:1 refers to something else (e.g. evaluation-period length), but it is not stated.

## 2) What is NOT disclosed

- **Code** — none anywhere. No framework config, no data loader, no training script.
- **Data** — "on request"; the raw corpus is licensed from Incopat, so even a granted request would likely be
  restricted. No node counts, no edge counts, no per-year snapshot sizes, no citation-count distributions beyond
  a qualitative figure.
- **The equations themselves** are raster images (`M18.gif` … `M76.gif` in the PMC HTML). Equations 1, 2, 4, 5,
  6, 7 cannot be read as text; only the prose around them. This alone makes exact re-implementation impossible
  without guesswork.
- **Implementation details** that materially change results: the adjacency/alignment construction between
  snapshots ("alignment lists"), how the two "high/low" weights are set, the PCA dimensionality retained, the
  MLP widths, the Richards parameter bounds/initialisation, the loss weighting between the trajectory fit and the
  citation count, and the exact bootstrap/seed handling behind "average of three runs".
- **How the 133,857-patent corpus becomes a citation graph** — citation edges within the corpus only, or
  outward citations to patents outside the 133,857? Undisclosed, and it changes the label distribution entirely.
- **The forecast-horizon evaluation is partly post hoc**: the "future unknown trajectory" demonstration uses
  "50% of the historical data from 2018 to 2022 to predict its future citation trajectory in 2023–2027", with no
  statement of how 2023–2027 ground truth could exist for a paper published in 2024 (it cannot, for the out-years;
  those are forecasts, not evaluations).

## 3) Method extraction (precise enough to re-implement the *logic*)

```
Inputs
  patent p : publication number, publication year, IPC codes (primary + secondary),
             applicant(s) (first vs others), publication country, citation list
  snapshots: S_t = (V_t, E_t, A_t, t)   t = publication year, 2004..2023
  relations: r = {technical classification, cited-by, applied-by, belongs-to}
  series    : P = {S_1..S_T}; predict y_{T+1..T+N} = cumulative citation count of p

Representation
  2-layer R-GCN per snapshot, hidden 64, graph embedding 128, dropout 0.5
  inter-snapshot aggregation of previous-node features (alignment list)

Temporal model
  BiLSTM over node-embedding sequence (10 historical snapshots)
  two influence weights: high for primary IPC / first applicant, low otherwise

Trajectory head
  concat 4 relational sequences -> PCA -> 4 MLPs -> Richards params (K, B, nu, t0 [ + Q offset ])
  Richards: y(t) = K / (1 + Q*exp(-B*(t - t0)))^(1/nu)      [standard generalised logistic;
            the paper's own equations are images, so this is the canonical form of the curve they name]

Evaluation
  history  = snapshots 1..10 ; evaluation = snapshots 11..20
  subtasks : new (final cum < 2) | grown (final cum > 4) | random (all)
  horizons : T+1 .. T+10 (performance reported to decay with horizon)
  metrics  : MALE, RMSLE on log1p counts
  averaging: 3 runs
```

What is *re-implementable* honestly: the snapshot construction, the subtask definitions, the horizon sweep, the
Richards curve and the two metrics. What is **not**: the R-GCN/BiLSTM/PCA stack as configured, because the
equations, the alignment construction, the influence weights and the data are all unavailable.

## 4) Data requirements, and whether that data exists in a medical-device regulatory setting

Required: (a) a longitudinal *citation* graph with citing and cited identifiers, (b) per-entity attributes
(classification codes, applicant, country), (c) yearly snapshots, (d) a commercial patent database for coverage.

In a medical-device regulatory setting, the analogue exists but is weaker:

| PTNS need | MedRadar reality |
|---|---|
| citation edges between entities | **No citation graph.** MedRadar has `events` (510(k)/PMA/recall/trial/8-K) with `product_code`, `track_id`, `company_key` — co-occurrence and sequence, not citation. |
| per-year snapshots | Yes: `event_date` 1966→2026, so `track_id`/`product_code` yearly panels are constructible. |
| entity attributes | Yes: `product_codes` (specialty, regulation_number, device_name), `companies` (sector, country). |
| labels (future citations) | **No analogue.** The closest traction proxies are subsequent 510(k)/PMA submissions in the same product code, recall events, or trial starts — all *different constructs* from citations. |
| commercial database | MedRadar's sources are openFDA/SEC/ClinicalTrials — free, so no licence barrier. |

Conclusion: PTNS's actual target variable does not exist for medical devices. Only its *snapshot-and-horizon
evaluation protocol* and its *curve-fitting/metric* machinery transfer.

## 5) My independent implementation and its self-test result

File: `experiments/phoenix/external/methods/trajectory_features.py`; exercised by `selftest_synthetic.py`
(**56/56 checks pass**, exit 0).

Implemented from the paper's *logic* only (no original code, no original data):
`cumulative_from_events` (contemporaneous cumulative series), `assign_subtask` (<2 / >4 / all),
`richards` (generalised logistic, 5-parameter form stated explicitly because the paper's Eq. 5 is an image),
`fit_richards` (bounded least squares on cumulative counts), `male` / `msle` / `rmsle`,
`rolling_origin_backtest` (history window → T+N prediction → per-horizon metrics, per subtask),
plus a transparent log-linear baseline standing in for the unavailable R-GCN/BiLSTM learner.

Synthetic validation results (seeded, reproducible):

- Richards fit on a noise-free synthetic curve with known K=250, B=0.55, ν=1.3: recovered K=250.00, R²=1.000 —
  the curve and fitter are correct.
- MALE hand-check: MALE([3],[4]) = |ln5 − ln4| = 0.223144 exactly; RMSLE = 0 for a perfect forecast; MSLE = MALE²
  for a single point.
- Subtask boundaries follow the paper literally, including the **gap**: exactly 2, 3 or 4 citations belong to
  neither the "new" (<2) nor the "grown" (>4) restricted subtask. This gap is in the paper and is preserved in
  code rather than silently closed.
- Backtest on 120 synthetic patent-like trajectories (history=10, horizons 1/2/5/10): RMSLE rises monotonically
  with horizon (0.521, 0.750, 1.236, 1.401), which is the qualitative pattern the paper reports for its own
  horizons — i.e. the protocol reproduces the *expected behaviour*, not the paper's numbers.

**This reproduces no PTNS result.** No R-GCN, no BiLSTM, no PCA, no Incopat data, no comparison against TGNN/HINTS/
HDGNN/DeepCCP. The paper's claims (RMSLE −0.04/−0.14/−0.18) remain unverified by me and are unreproducible
without its code and data.

## 6) Applicability to MedRadar

Low-to-moderate, and only in parts:

1. **Multi-horizon evaluation protocol — usable.** `rolling_origin_backtest` gives MedRadar a clean way to score
   any trajectory forecaster at T+1/T+3/T+5 with MALE/RMSLE and disclose decay with horizon. This is
   methodologically hygienic and cheap.
2. **Curve-fitting view of a technology's traction — usable with a different target.** Richards fitting applies to
   any cumulative series; in MedRadar the honest target is cumulative authorisations or cumulative recall/trial
   counts per `track_id`/`product_code`, not citations.
3. **Snapshot construction — usable.** Yearly panels of `events` by `track_id` with per-year attributes is already
   how MedRadar's temporal analysis works.
4. **The model itself — not recommended.** A 2-layer R-GCN + BiLSTM + PCA on 133k entities needs dense yearly
   graphs; MedRadar's medical-device event graph is sparse, has no citation relation, and its entities
   (product codes, firms) are far fewer. The compute cost (GPU) and the missing relational substrate make it a
   poor fit; there is also no approved GPU budget.
5. **"Sleeping beauty" framing — interesting, not actionable** without a citation-like attention signal.

## 7) Limitations, bias and leakage risks

- **Irreproducibility is the first limitation.** No code, no data, equation images. Any downstream use must be
  labelled "method idea", never "validated method".
- **Domain mismatch.** Polyurethane patent citations (2004–2023, Chinese applicants dominant) do not transfer to
  US medical-device regulation; citation behaviour is jurisdiction- and field-specific.
- **Citation ≠ impact.** The paper equates citation counts with "value"/"impact"; the literature it cites
  (Harhoff et al.) supports a correlation, not an equivalence. Medical-device "impact" is better proxied by
  authorisations, recalls, or adoption.
- **Temporal leakage risk in any copy of this design.** Features must be built only from snapshots ≤ T. The
  paper does state "based on time-series network snapshots" and evaluates future snapshots, which is the right
  shape; but the 2023–2027 "future trajectory" demonstration cannot be evaluated against ground truth for
  out-years, so those curves are forecasts presented visually, not scored.
- **Left/right censoring.** Patents published 2020–2023 have short citation windows; "new vs grown" labels are
  measured at different maturities, which biases the subtask comparisons toward `grown` being hard.
- **Selection by database.** Incopat coverage favours Chinese filings; the task's "predict new/grown/random"
  split is a property of that corpus.
- **Metric opacity.** The prose mis-describes MALE (squared vs absolute) and the offset for the logarithm is
  unstated; a re-implementation must declare both choices, as mine does (log1p, absolute logs).
- **Leakage to avoid in MedRadar.** If the protocol is reused, the evaluation window must be strictly after the
  feature window *and* after `available_at` (ingestion time), else look-ahead bias enters through late-arriving
  records.

## 8) Decision

**STUDY_ONLY** (with two component-level ADAPT items: the multi-horizon backtest protocol and MALE/RMSLE
reporting).

Reasoning: the paper fails the reproducibility bar outright — no code, no data, no readable equations, commercial
source database — so nothing from it can be trusted as a validated recipe; the target construct (patent
citations) has no counterpart in MedRadar's regulatory-event data; and the model class requires GPU compute that
is out of scope. What survives is a small, honest methodological transfer (horizon-wise evaluation with log-error
metrics, plus curve fitting for cumulative traction series), which is implemented and self-tested here. Decision
would move to ADAPT only if MedRadar acquired a genuine citation-like graph (e.g. patent→device or
guideline→device linkage) — which it does not have.

## 9) Open questions

1. Are the citation edges restricted to the 133,857-patent corpus, or do they include external cited patents?
   (Determines label distribution and graph density.)
2. What exactly does "ratio of partitioning … 2:1" refer to, given 10+10 snapshots?
3. Which distribution is the "topical"/"influence" PCA applied to — node embeddings, per-relation sequences, or
   both? (Eq. 5 is an image.)
4. What is the offset used inside the logarithm for MALE/RMSLE (counts can be 0)?
5. Does "aviation industry" in the Introduction indicate a second, unreported case study?
6. Would the authors release code under a licence compatible with non-commercial research use if asked?
   (Untested — I did not contact the authors.)

## Evidence paths

- `experiments/phoenix/external/methods/trajectory_features.py` — Richards fit, MALE/RMSLE, subtasks, backtest, cluster chaining
- `experiments/phoenix/external/methods/selftest_synthetic.py` — 56 checks incl. the synthetic backtest above
- `experiments/phoenix/external/methods_audit_summary.json` — machine-readable decision record
- `experiments/phoenix/external/methods/evidence.json` — what was verified and how

## Citations

- Ding M, Yu W, Zeng T, Wang S. Sci Rep 2024;14:24034. https://doi.org/10.1038/s41598-024-75913-0 ·
  https://pmc.ncbi.nlm.nih.gov/articles/PMC11473824/ ·
  https://europepmc.org/article/MED/39402175 (metadata incl. CC BY-NC-ND, `hasData=Y` referring to the
  on-request statement, no code link)
