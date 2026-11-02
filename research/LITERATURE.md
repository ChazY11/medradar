# Literature review — predicting corporate technological direction from public pre-cutoff evidence

**Status:** first independent review for the MedRadar Foresight Lab, cycle 2 (branch
`research/cycle2-coverage-power`). Written 2026-11-02 by `research-auditor`.
**Scope:** empirical and methodological work relevant to forecasting a
`(company, technology) × time` milestone from information available at a knowledge
cutoff, in a rare-event, point-in-time, entity-resolved panel.

## Verification note (read this first)

Every entry below was checked against a bibliographic record on **2026-11-02**, not
recalled from memory:

- journal articles and conference papers: the title query was resolved through the
  Crossref REST API (`https://api.crossref.org/works`) and the returned
  title / authors / year / venue were compared with the entry; the DOI is printed in
  each entry so a reader can re-check it;
- the one book: verified through its Google Books record
  (`books.google.co.uk/books?id=v0RKDwAAQBAJ`, ISBN 9781119482109).

**No entry is tagged UNVERIFIED.** Items I could not confirm (e.g. a 1986 AER Jaffe
paper whose Crossref record I could not surface) were **excluded** rather than
asserted. "Limitations" notes are my assessment of what the paper does *not* support;
they are not claims about author intent.

**Volume / issue / page numbers are deliberately omitted.** They were not part of the
field set I verified against Crossref, so printing them would assert unchecked metadata.
Each DOI resolves to the publisher's authoritative numbering; use it for pagination.

Two bibliographic year quirks: Hou, Xue & Zhang carries a 2018 online-first date in
Crossref but is conventionally cited as 2020 (cite as 2020, online 2018); Bailey,
Borwein, López de Prado & Zhu carries a 2016 online date but is conventionally cited as
2017 in the *Journal of Computational Finance* (cite as 2016/2017). Both year pairs are
flagged here so the reader is not surprised by either convention.

## How this review is organised

Eight clusters, 30 entries, followed by **What the literature does NOT settle for
us**. Clusters map to the actual design decisions of this project: what to predict
(clusters 1–2), what to use as early evidence (3), how the panel is built (4), how to
model and score a rare event (5–6), and how not to fool ourselves (7–8).

---

## Cluster 1 — Corporate innovation direction, firm technology entry, forecasting

**1. Kogan, L., Papanikolaou, D., Seru, A. & Stoffman, N. (2017). "Technological
Innovation, Resource Allocation, and Growth." *Quarterly Journal of Economics*. DOI: [10.1093/qje/qjw040](https://doi.org/10.1093/qje/qjw040).**
- *Finding:* constructs a market-value-weighted patent measure (the stock-market
  reaction around patent grants) and shows it predicts firm growth and reallocation
  better than raw patent counts.
- *Why it matters here:* the strongest existing evidence that firm-level innovative
  output is measurable and forward-relevant; supports the premise that a
  company–technology event stream carries information beyond counts.
- *Limitations:* US-listed firms only; assumes semi-strong market efficiency;
  measures realised value, not the *direction* of future research, and has no
  knowledge-cutoff discipline — it is not a forecasting paper.

**2. Kelly, B., Papanikolaou, D., Seru, A. & Taddy, M. (2021). "Measuring
Technological Innovation over the Long Run." *American Economic Review: Insights*. DOI: [10.1257/aeri.20190499](https://doi.org/10.1257/aeri.20190499).**
- *Finding:* a text-embedding measure of patent similarity/novelty that separates
  incremental from breakthrough innovation and tracks long-run technological change;
  the measure correlates with productivity and growth.
- *Why it matters here:* demonstrates that unstructured text can represent
  *technological position* at firm–technology granularity — the natural upgrade path
  from our curated 38-track taxonomy whose unversioned application is a documented
  leakage channel.
- *Limitations:* patent text is a lagging, litigation-shaped record; embeddings are
  corpus-dependent; no point-in-time evaluation and no evidence that the measure
  predicts *entry into a new track* before it happens.

**3. Hoberg, G. & Phillips, G. (2016). "Text-Based Network Industries and Endogenous
Product Differentiation." *Journal of Political Economy*. DOI:
[10.1086/688176](https://doi.org/10.1086/688176).**
- *Finding:* firm product descriptions in 10-K filings recover dynamic peer groups
  and product-market positioning that change faster than fixed SIC codes.
- *Why it matters here:* the clearest demonstration that fixed, hand-curated
  taxonomies mis-measure firm positioning over time; our current product-code→track
  map is exactly such a fixed map applied to history.
- *Limitations:* product-market space, not technology space; only US filers; no
  prediction target, and text-derived peers can be endogenous to disclosure policy.

---

## Cluster 2 — Patent-based technological positioning and knowledge relatedness

**4. Jaffe, A. B. (1989). "Characterizing the 'technological position' of firms, with
application to quantifying technological opportunity and research spillovers."
*Research Policy*. DOI:
[10.1016/0048-7333(89)90007-3](https://doi.org/10.1016/0048-7333(89)90007-3).**
- *Finding:* represents each firm as a distribution over patent classes, then
  measures technological position, opportunity and spillovers as
  proximity-weighted external R&D.
- *Why it matters here:* the canonical operationalisation of "technology footprint"
  that our `rd_company_active_tracks_*` / novelty-share features approximate crudely;
  it also names the confound — opportunity differs by field, so raw activity counts
  are not comparable across tracks.
- *Limitations:* class-level aggregation is arbitrary and class schemes are revised;
  patents require an assignee-harmonisation step (see cluster 4) that the paper
  assumes away.

**5. Breschi, S., Lissoni, F. & Malerba, F. (2003). "Knowledge-relatedness in firm
technological diversification." *Research Policy*. DOI:
[10.1016/S0048-7333(02)00004-5](https://doi.org/10.1016/S0048-7333(02)00004-5).**
- *Finding:* measures knowledge relatedness between technology classes from their
  co-occurrence inside patents; firm diversification is strongly conditioned by
  relatedness — firms move preferentially into related classes.
- *Why it matters here:* gives the empirical basis for a **relatedness/density
  feature** for entry: the hypothesis that a dormant pair is more likely to activate
  if it is adjacent to the company's existing knowledge base.
- *Limitations:* patent co-classification is noisy and examiners apply it
  inconsistently; large-firm patenting samples; relatedness is not a causal driver.

**6. Yayavaram, S. & Ahuja, G. (2008). "Decomposability in Knowledge Structures and
Its Impact on the Usefulness of Inventions and Knowledge-base Malleability."
*Administrative Science Quarterly*. DOI:
[10.2189/asqu.53.2.333](https://doi.org/10.2189/asqu.53.2.333).**
- *Finding:* in the 1984–1994 semiconductor industry, a *nearly decomposable*
  knowledge base (discernible clusters linked by cross-cluster couplings) increases
  both invention usefulness and the knowledge base's capacity to change.
- *Why it matters here:* predicts that entry probability is not just a function of
  activity counts but of the *coupling structure* of a company's track portfolio —
  a testable heterogeneity and a possible feature family beyond track counts.
- *Limitations:* one industry and one 11-year window; the coupling measure depends on
  the patent classification and on firm boundary definitions.

**7. Aharonson, B. S. & Schilling, M. A. (2016). "Mapping the technological landscape:
Measuring technology distance, technological footprints, and technology evolution."
*Research Policy*. DOI:
[10.1016/j.respol.2015.08.001](https://doi.org/10.1016/j.respol.2015.08.001).**
- *Finding:* defines technology distance and technological-footprint measures from
  patent portfolios and uses them to trace how firms' positions move over time.
- *Why it matters here:* closest methodological template for a versioned technology
  space in which "entry into a new area" is a *distance* statement, not a membership
  statement — directly relevant to operationalising the entry target.
- *Limitations:* descriptive mapping, not prediction; distance measures are sensitive
  to patent-class granularity and truncation (young firms have thin footprints).

**8. Hidalgo, C. A., Klinger, B., Barabási, A.-L. & Hausmann, R. (2007). "The Product
Space Conditions the Development of Nations." *Science*. DOI:
[10.1126/science.1144581](https://doi.org/10.1126/science.1144581).**
- *Finding:* countries diversify into products that are close to their existing
  capability set; a density/relatedness measure computed on the product space predicts
  the direction of future diversification.
- *Why it matters here:* the cleanest statement of the "adjacent diversification"
  prior that our entry target tests at firm level: a firm should be more likely to
  enter a track close to its current tracks. It also shows the evaluation design —
  out-of-sample prediction of *which* new activity appears — that we need.
- *Limitations:* national/product aggregation, not firms; "relatedness" is
  observational co-export, so the mechanism (capabilities vs demand) is unresolved.

---

## Cluster 3 — Weak / early signals: hiring, procurement, publications, market

**9. Ansoff, H. I. (1975). "Managing Strategic Surprise by Response to Weak Signals."
*California Management Review*. DOI:
[10.2307/41164635](https://doi.org/10.2307/41164635).**
- *Finding:* defines weak signals as early, ambiguous indicators of strategic
  discontinuity and proposes a graduated response rather than waiting for strong
  signals.
- *Why it matters here:* the intellectual origin of the "early signal" premise; it
  correctly warns that weak signals are ambiguous and must be scored
  probabilistically — which is what a calibrated forecast is supposed to do.
- *Limitations:* conceptual/managerial, not empirical; no operational definition of
  signal strength or false-alarm cost, so it cannot license a specific feature or
  metric.

**10. Choi, H. & Varian, H. (2012). "Predicting the Present with Google Trends."
*Economic Record*. DOI:
[10.1111/j.1475-4932.2012.00809.x](https://doi.org/10.1111/j.1475-4932.2012.00809.x).**
- *Finding:* search-query indices improve nowcasts of economic indicators (e.g. auto
  sales, unemployment) relative to simple time-series baselines.
- *Why it matters here:* proof of concept that a cheap, public, high-frequency
  "attention" signal can add incremental predictive value — the same incremental-gain
  test we apply to financial/market/publication sources.
- *Limitations:* nowcasting, not forecasting a discrete future event; query choice is
  researcher-degrees-of-freedom; short samples; online-search behaviour may not reveal
  corporate R&D intent.

**11. Edquist, C. & Zabala-Iturriagagoitia, J. M. (2012). "Public Procurement for
Innovation as mission-oriented innovation policy." *Research Policy*. DOI:
[10.1016/j.respol.2012.04.022](https://doi.org/10.1016/j.respol.2012.04.022).**
- *Finding:* argues public procurement can function as a demand-side innovation
  instrument, and reviews when procurement pulls innovation rather than buying off the
  shelf.
- *Why it matters here:* the theoretical case for procurement as a leading demand
  signal; it is why the USAspending lane was attempted. It also implies the signal is
  buyer- and mission-specific, not a generic firm-level covariate.
- *Limitations:* mostly conceptual/case evidence; no firm-level predictive evaluation
  and no point-in-time procurement data — consistent with our documented exclusion of
  procurement from gain claims (`pit_usable=0`).

**12. Hershbein, B. & Kahn, L. B. (2018). "Do Recessions Accelerate Routine-Biased
Technological Change? Evidence from Vacancy Postings." *American Economic Review*. DOI: [10.1257/aer.20161570](https://doi.org/10.1257/aer.20161570).**
- *Finding:* using job-vacancy postings, shows demand for routine work fell and
  technological upgrading accelerated, especially over the Great Recession.
- *Why it matters here:* the best available evidence that *hiring demand* contains
  information about a firm's technology trajectory — the missing "hiring" source in
  our data, and the strongest argument for collecting vacancy data if licensing and
  point-in-time availability can be shown.
- *Limitations:* vacancy text measures labour demand, not R&D projects; coverage of
  postings is partial and changes over time; the paper never predicts firm–technology
  entry, so the transfer to our target is untested.

---

## Cluster 4 — Entity resolution, record linkage, firm-identifier measurement error

**13. Fellegi, I. P. & Sunter, A. B. (1969). "A Theory for Record Linkage." *Journal
of the American Statistical Association* 64(328). DOI:
[10.1080/01621459.1969.10501049](https://doi.org/10.1080/01621459.1969.10501049).**
- *Finding:* formalises probabilistic record linkage with match weights derived from
  agreement/disagreement patterns, and a decision rule with error-rate bounds.
- *Why it matters here:* our 510(k)→company link is exactly this problem (16.9% link
  rate; 284 unlinked rows that name a curated company). It gives the standard for
  storing match evidence and estimating false-link/false-non-link rates — evidence
  the `events` table currently does **not** retain (`company_key` has no confidence,
  alias or rule version).
- *Limitations:* conditional-independence assumptions across fields are often
  violated; pairwise model does not handle clustering/merges of many records; assumes
  a clean reference file, which our 51-company roster is not.

**14. Papadakis, G., Skoutas, D., Thanos, E. & Palpanas, T. (2020). "Blocking and
Filtering Techniques for Entity Resolution." *ACM Computing Surveys*. DOI:
[10.1145/3377455](https://doi.org/10.1145/3377455).**
- *Finding:* surveys blocking (candidate generation) and filtering (pair
  classification) methods, and documents the recall/efficiency trade-off that
  dominates real linkage pipelines.
- *Why it matters here:* a deterministic applicant-entity universe (cycle-2 P2) is a
  blocking decision; this literature says the blocking key determines which entities
  can ever be linked and therefore who enters the panel — i.e. the universe is a
  measurement choice, not a neutral data cleaning step.
- *Limitations:* computer-science focus on efficiency and pair-quality metrics, not
  on downstream economic bias; little guidance on evaluating linkage error in a
  forecasting panel.

**15. Kalemli-Özcan, Ş., Sørensen, B., Villegas-Sanchez, C., Volosovych, V. &
Yeşiltaş, S. (2015). "How to Construct Nationally Representative Firm Level Data from
the Orbis Global Database." NBER Working Paper 21558. DOI:
[10.3386/w21558](https://doi.org/10.3386/w21558).**
- *Finding:* documents how raw commercial firm databases (Orbis) must be cleaned and
  re-weighted to be nationally representative, and how coverage and consolidation
  choices change measured aggregates.
- *Why it matters here:* direct precedent for treating a firm panel as a *constructed
  measurement*: entity consolidation (parent vs legal entity), coverage and
  re-weighting materially change the sample. This is the methodological basis for the
  cycle-2 entity-granularity ablation (P1 vs P2), and a warning that a larger panel
  can be a *less* representative one.
- *Limitations:* commercial database with country-varying coverage; the paper's
  focus is aggregate measurement (SMEs, concentration), not event-level forecasting
  or rare-event labels.

---

## Cluster 5 — Discrete-time survival and rare-event prediction

**16. Allison, P. D. (1982). "Discrete-Time Methods for the Analysis of Event
Histories." *Sociological Methodology*. DOI:
[10.2307/270718](https://doi.org/10.2307/270718).**
- *Finding:* shows that discrete-time hazard models can be estimated by pooled
  logistic regression on person-period data, with time dummies or a baseline hazard.
- *Why it matters here:* our data are naturally discrete-time (quarterly origins,
  censored labels); this justifies the logistic formulation but also names the
  requirement our current model omits: **explicit duration dependence** (our
  `rd_pair_inactive_months` is a linear-ish covariate, not a flexible baseline
  hazard).
- *Limitations:* assumes the discretisation is fine relative to the hazard; ignores
  competing risks and unobserved heterogeneity; pooled logit standard errors need
  clustering by unit (our rows repeat company–track pairs across origins).

**17. King, G. & Zeng, L. (2001). "Logistic Regression in Rare Events Data."
*Political Analysis*. DOI:
[10.1093/oxfordjournals.pan.a004868](https://doi.org/10.1093/oxfordjournals.pan.a004868).**
- *Finding:* rare-event logit coefficients are biased toward zero and standard errors
  are unreliable; proposes prior correction/weighting and shows when case-control
  sampling helps.
- *Why it matters here:* our entry base rate is 1.2% (503/41,003) and per-window
  positives are 25–27. This paper is the reason a plain logit on 1.2% prevalence
  cannot be trusted at face value, and why "how many positives" is a *statistical*
  constraint, not just a data-size one.
- *Limitations:* concerned with parameter bias/coverage, not ranking (AP) or
  calibration; the recommended corrections change predicted probabilities and can
  therefore interact with the calibration metrics we report.

**18. Saito, T. & Rehmsmeier, M. (2015). "The Precision-Recall Plot Is More
Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced
Datasets." *PLOS ONE*. DOI:
[10.1371/journal.pone.0118432](https://doi.org/10.1371/journal.pone.0118432).**
- *Finding:* under class imbalance, PR curves discriminate better than ROC curves,
  and high ROC-AUC can coexist with poor precision.
- *Why it matters here:* the justification for making AP the primary metric and for
  explicitly discarding ROC-AUC/FPR@0.5 for the entry target (our frozen metrics show
  FPR@0.5 = 0 everywhere because no probability reaches 0.5).
- *Limitations:* AP is prevalence-dependent, so AP values are **not** comparable
  across panels with different base rates — a direct warning for the cycle-2
  coverage-expansion comparison, which must hold prevalence or report it.

**19. Davis, J. & Goadrich, M. (2006). "The relationship between Precision-Recall and
ROC curves." *Proceedings of the 23rd International Conference on Machine Learning
(ICML)*. DOI: [10.1145/1143844.1143874](https://doi.org/10.1145/1143844.1143874).**
- *Finding:* establishes the formal correspondence between PR and ROC spaces and shows
  that PR curves are more sensitive to class imbalance under a fixed ranking.
- *Why it matters here:* supports the choice of AP and precision@k as decision-relevant
  metrics for a 1.2% base rate, and explains why a model can look excellent on ROC and
  useless on AP.
- *Limitations:* abstract curve properties, not a recommendation for a particular
  operating threshold; says nothing about uncertainty or clustered resampling.

---

## Cluster 6 — Calibration and proper scoring rules

**20. Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms of
Probability." *Monthly Weather Review*. DOI:
[10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2).**
- *Finding:* introduces the mean squared probability error (Brier score) as a scoring
  rule for probabilistic forecasts.
- *Why it matters here:* Brier is a headline metric in our frozen reports; but for a
  1.2% base rate it is dominated by the negative class, which is why it must be read
  alongside a prevalence baseline and calibration diagnostics.
- *Limitations:* decomposes poorly by itself; not the right primary ranking metric
  under extreme imbalance; no uncertainty guidance.

**21. Gneiting, T. & Raftery, A. E. (2007). "Strictly Proper Scoring Rules, Prediction,
and Estimation." *Journal of the American Statistical Association*. DOI:
[10.1198/016214506000001437](https://doi.org/10.1198/016214506000001437).**
- *Finding:* characterises strictly proper scoring rules (Brier, log, CRPS) and shows
  why only proper rules discourage hedging and can be used for estimation.
- *Why it matters here:* justifies scoring our probabilities with Brier/log rather
  than ad-hoc accuracy or F1, and requires that any "improvement" claim be made on a
  proper score — not just on a threshold metric like FPR.
- *Limitations:* proper scores are comparable across models only for the same
  target/event definition; they do not by themselves test whether a model is useful at
  an operating point, and they say nothing about clustered uncertainty.

**22. Niculescu-Mizil, A. & Caruana, R. (2005). "Predicting good probabilities with
supervised learning." *Proceedings of the 22nd International Conference on Machine
Learning (ICML)*. DOI:
[10.1145/1102351.1102430](https://doi.org/10.1145/1102351.1102430).**
- *Finding:* many supervised models are systematically miscalibrated; Platt scaling
  and isotonic regression on held-out data improve probability estimates without
  changing ranking.
- *Why it matters here:* our logistic baseline can be calibrated but is still
  sensitive to rare-event bias and to the median imputation/standardisation choices;
  post-hoc calibration on **purged** development origins is a legitimate, cheap
  improvement to test (and must not be fitted on the holdout).
- *Limitations:* calibration maps are themselves estimated and can overfit with small
  positive counts; ranking metrics are unchanged by monotone recalibration, so it
  cannot rescue AP.

**23. Van Calster, B., McLernon, D. J., van Smeden, M., Wynants, L. & Steyerberg,
E. W. (2019). "Calibration: the Achilles heel of predictive analytics." *BMC
Medicine* 17. DOI:
[10.1186/s12916-019-1466-7](https://doi.org/10.1186/s12916-019-1466-7).**
- *Finding:* model calibration is routinely ignored in applied prediction research;
  discrimination without calibration is insufficient, and calibration should be
  reported with slope/intercept and a calibration plot, not only a summary score.
- *Why it matters here:* our programme currently registers zero matured forecasts, so
  our calibration evidence is absent; this paper defines the minimum report we owe
  when forecasts mature (slope, intercept, plot, base-rate comparison).
- *Limitations:* clinical-prediction focus; guidance assumes reasonably large
  validation samples — exactly what a 25-positive window does not provide.

---

## Cluster 7 — Look-ahead bias, point-in-time data, backtest overfitting

**24. Banz, R. W. & Breen, W. J. (1986). "Sample-Dependent Results Using Accounting and
Market Data: Some Evidence." *Journal of Finance*. DOI:
[10.1111/j.1540-6261.1986.tb04548.x](https://doi.org/10.1111/j.1540-6261.1986.tb04548.x).**
- *Finding:* classic demonstration that using accounting data before it was publicly
  reported (i.e. look-ahead) changes and can reverse conclusions about return
  predictability.
- *Why it matters here:* the ancestral reference for our dual-time rule
  (`event_date <= τ` **and** `available_at <= τ`, financials `filed <= τ`). Our
  leakage replay is a concrete audit of exactly the failure this paper documents.
- *Limitations:* equity-return setting; date-level accounting availability, not
  document-level publication timestamps; does not address semantic leakage from
  present-day taxonomies.

**25. Bailey, D. H., Borwein, J. M., López de Prado, M. & Zhu, Q. J. (2016/2017). "The
probability of backtest overfitting." *The Journal of Computational Finance*.
DOI: [10.21314/JCF.2016.322](https://doi.org/10.21314/JCF.2016.322).**
- *Finding:* defines the probability of backtest overfitting (PBO) and the
  combinatorially symmetric cross-validation (CSCV) procedure that estimates how
  likely the in-sample-best strategy is to underperform out of sample.
- *Why it matters here:* our programme compares several feature specifications
  (A–G) across a small number of windows; without an explicit multiple-comparison /
  overfitting budget, "spec D gains +0.008 AP" can be noise. PBO is the right framing
  for reporting specification-selection risk honestly.
- *Limitations:* designed for strategy selection on long return series; the number of
  independent observations here is tiny and windows overlap, so PBO estimates will be
  extremely noisy — use it as an interpretive discipline, not a precise probability.

**26. Hou, K., Xue, C. & Zhang, L. (2020, online 2018). "Replicating Anomalies."
*Review of Financial Studies*. DOI:
[10.1093/rfs/hhy131](https://doi.org/10.1093/rfs/hhy131).**
- *Finding:* re-tests hundreds of published return anomalies with consistent
  methodology and finds a large fraction fail once microcaps, weighting and multiple
  testing are handled.
- *Why it matters here:* the best-known large-scale demonstration that "publishable
  effect sizes often vanish under stricter, pre-registered replication" — the standard
  our own cycle-2 reproductions should be held to.
- *Limitations:* finance-return anomalies, not forecasting AP; the failure mechanism
  there (microcaps, weighting) does not map one-to-one onto a 51-entity,
  regulatory-event panel.

---

## Cluster 8 — Rolling-origin, purged / embargoed temporal validation

**27. Tashman, L. J. (2000). "Out-of-sample tests of forecasting accuracy: an analysis
and review." *International Journal of Forecasting*. DOI:
[10.1016/S0169-2070(00)00065-0](https://doi.org/10.1016/S0169-2070(00)00065-0).**
- *Finding:* reviews out-of-sample evaluation designs and recommends rolling/recursive
  origin evaluation that mimics real forecast timing rather than a single split.
- *Why it matters here:* the protocol's expanding-window rolling origin is the
  standard this paper describes; it also motivates reporting **per-origin** results
  because a single holdout is fragile (our entry AP ranges 0.018–0.237 across
  origins).
- *Limitations:* univariate forecasting context; assumes one forecast per origin and
  does not address overlapping multi-period labels or cross-sectional dependence —
  both of which apply to us.

**28. Bergmeir, C. & Benítez, J. M. (2012). "On the use of cross-validation for time
series predictor evaluation." *Information Sciences*. DOI:
[10.1016/j.ins.2011.12.028](https://doi.org/10.1016/j.ins.2011.12.028).**
- *Finding:* examines when cross-validation is valid for time-series evaluation and
  how it compares with out-of-sample holdouts; argues CV can be appropriate in some
  settings but not when serial dependence is ignored.
- *Why it matters here:* warns that the "no random splits anywhere" rule is right for
  our serially dependent, overlapping-label data — and that a purged/blocked design is
  the defensible alternative to random k-fold.
- *Limitations:* prediction-error setting; does not cover the case where the label is
  a rare future event and the training/test windows overlap for months (our
  multi-window holdouts).

**29. Cerqueira, V., Torgo, L. & Mozetič, I. (2020). "Evaluating time series
forecasting models: an empirical study on performance estimation methods." *Machine
Learning* 109. DOI:
[10.1007/s10994-020-05910-7](https://doi.org/10.1007/s10994-020-05910-7).**
- *Finding:* large empirical comparison of performance-estimation methods for time
  series (holdout, rolling, cross-validation variants); no method dominates, and the
  choice interacts with series length and dependence.
- *Why it matters here:* supports pre-registering one estimation design (ours:
  expanding purged rolling origin) and reporting dispersion across origins rather than
  claiming a single point estimate is precise.
- *Limitations:* regression/point-forecast losses; not classification AP with
  overlapping event labels; no guidance on clustered entity panels.

**30. López de Prado, M. (2018). *Advances in Financial Machine Learning*. John
Wiley & Sons. ISBN 9781119482109 (verified via Google Books record
`v0RKDwAAQBAJ`).**
- *Finding:* introduces purged k-fold cross-validation and embargoes to prevent
  information from labels that span the test window leaking into training, plus
  combinatorial purged CV for backtest evaluation.
- *Why it matters here:* the direct methodological source for our purge rule
  `cutoff + 12m <= origin`. Our audit independently rebuilt the purged training sets
  and confirmed this rule holds for every evaluated origin (see
  `docs/research/AUDIT_CYCLE2.md`).
- *Limitations:* written for financial ML where labels have overlapping horizons and
  samples are abundant; the book gives no guidance on tiny-positive regimes
  (25–27 positives/window) or on entity-panel construction, and the embargo length is
  a judgement call.

---

## What the literature does NOT settle for us

- **No established benchmark for firm-level *technology-track entry* prediction from
  public pre-cutoff evidence.** The closest work predicts aggregate diversification
  (Hidalgo et al.) or measures innovation ex post (Kogan et al., Kelly et al.). There
  is no published AP / Brier / MDE reference for our target, so we cannot say "0.11
  AP is good/bad for this problem" from the literature alone.
- **No accepted answer to the entity-granularity problem.** Record-linkage theory
  (Fellegi–Sunter) and firm-panel construction work (Kalemli-Özcan et al.) tell us the
  choice matters, but neither gives a test for which unit is *right* for forecasting.
  Our P1-vs-P2 ablation is therefore filling a genuine gap, not replicating a known
  result.
- **No evidence on how left-censoring from a truncated regulatory window biases
  technology-entry labels.** Our 2016-11-01 bulk-window truncation is a
  measurement-window problem that survival analysis handles only if the entry clock is
  observable; the literature does not tell us the size or direction of the bias.
- **Prevalence-dependence of AP is acknowledged (Saito & Rehmsmeier) but there is no
  accepted protocol for comparing AP across panels with different base rates** — the
  exact comparison the cycle-2 coverage expansion requires.
- **Whether weak signals (hiring, procurement, publications) carry incremental
  ranking information for corporate technology direction is untested in this domain.**
  The weak-signal idea (Ansoff) and demand-pull theory (Edquist & Zabala) are
  conceptual; Google-Trends-style nowcasting (Choi & Varian) is a different target.
  Vacancy data (Hershbein & Kahn) is the most promising untested source for us.
- **Calibration of rare-event corporate forecasts is essentially unstudied.** The
  calibration literature (Brier, Gneiting & Raftery, Niculescu-Mizil & Caruana, Van
  Calster et al.) is clinical/financial; none of it tells us how to calibrate with ~25
  positives per evaluation window, or how much calibration evidence is enough to
  report.
- **No standard operating point for lead-time vs false-alarm rate in technology
  foresight.** Matched-FAR lead-time comparisons exist in detection theory and
  clinical screening, but no discipline has published a target lead-time/false-alarm
  trade-off for corporate R&D milestones — so our matched-FAR comparison has to define
  its own estimand and justify it.
- **Multiple-testing / specification-selection discipline for small-window,
  overlapping-label forecasting panels is not settled.** Backtest-overfitting work
  (Bailey et al.) and replication work (Hou et al.) show the danger, but neither gives
  a power calculation for "how many additional sources can we test before the nulls
  become uninterpretable" at our sample size.

---

*End of review. 30 entries; 0 UNVERIFIED. If a future reader finds a DOI that no
longer resolves, treat that entry as unverified until re-checked.*
