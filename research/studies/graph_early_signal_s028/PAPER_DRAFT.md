# Relational Early Signals in Medical Technology Development: A Temporal Network Study

**Study S-028 — paper draft v1**
**Status:** draft, **not submitted, no venue claimed.** Every number is machine-derived from the
committed artifacts listed in §10.
**Authors:** MedRadar research programme (automated research agent). This draft must not be
attributed to a human author until a human reviews it.

---

## Abstract

Does the structure of a company–technology network carry information about a company's future
regulatory activity that conventional temporal models cannot? We study 51 medical-device firms and
38 technology tracks over 2016-11–2026-10, and define the target as a company–track pair's **first
observed qualifying regulatory activity** within the next 2 or 4 quarters. Qualifying means a
Traditional 510(k) or an original PMA, so maintenance filings are excluded. We evaluate with a
purged, expanding-window rolling-origin protocol, compare a 16-feature strong non-graph baseline
against the same baseline plus 12 graph-structural features, and add a **degree- and
time-distribution-preserving randomisation** of the company–technology edges (40 seeds).

The graph features did not improve out-of-sample Average Precision. At the primary horizon the
paired difference was **−0.0061** (95% CI [−0.0222, +0.0045], MDE 0.0194), i.e. a small negative
point estimate that cannot be distinguished from zero; the study can exclude a benefit larger than
0.019 AP. More strongly, the real graph was **no better than its randomised counterparts**: at the
primary horizon **40 of 40** randomisations achieved higher AP than the real graph, and at the
secondary horizon 30 of 40 did. A gradient-boosted learner performed worse on AP, not better.
We therefore report a **negative result**: in this data, relational structure does not beat strong
non-graph temporal baselines, and we cannot attribute any incremental information to the specific
observed connections. We separate this from a stronger claim of "networks are useless", which the
study does not support, and we document the data-infrastructure limits (12.1% entity–track mapping
coverage, no company–company relations, a `decision_date + 14 days` proxy clock) that bound the
conclusion.

## 1. Introduction

Public regulatory filings are the most reliable observable trace of medical-technology development.
A natural hypothesis is that firms do not move independently: a firm may enter a technology area
because peers, suppliers or competitors are already there. If so, the *relational structure* of a
firm–technology network should help predict future activity beyond a firm's own history.

This paper tests that hypothesis directly and pre-registers the conditions under which it would be
accepted or rejected. The contribution is not a model. It is a **falsification protocol plus its
outcome**: a target that is concrete and checkable, a strong non-graph baseline, a constrained
randomisation that is not a straw man, a temporally purged evaluation, and a negative result that
survives all of them.

Two features of this domain matter. First, medical technology is not finance: the canonical
financial-network literature (e.g. [R42]–[R44]) predicts continuous returns from dense, frequently
observed relations, whereas here the outcome is a **right-censored first event** observed through a
sparse administrative channel. Second, the diffusion literature ([R20]–[R24]) and the innovation-
network literature ([R25]–[R27]) establish that relations *can* matter for technology adoption and
invention, but they study patents, alliances or survey adoption — none of which is available here.
What is available is a bipartite company–technology activity graph. We ask whether that graph is
enough.

## 2. Related work

**Temporal and heterogeneous graph learning.** Temporal graph architectures ([R01]–[R06]) and
heterogeneous graph networks ([R11]–[R13]) provide the technical vocabulary. But recent benchmark
work is sobering: TGB [R07] and TGB 2.0 [R08] report that simple methods are often competitive and
that results vary strongly across datasets; DyGLib [R09] shows that some published baselines do not
reproduce under a unified protocol; GraphMixer [R10] reaches strong performance with an MLP plus
neighbour mean-pooling. These findings motivated our ordering: baselines and simple structural
features first, a GNN only if the simple graph features pass a pre-registered bar.

**Link and event prediction.** Link-prediction evaluation is known to be sensitive to negative
sampling and protocol ([R14]–[R19]). Our target is not link prediction in the usual sense — we
predict a future *event* for a currently dormant pair — but the lesson carries over: the comparison
must hold the sample, the learner and the split fixed, and it must use a baseline that is not
trivially weak.

**Early signals.** Weak-signal and early-warning ideas ([R30]–[R33]) motivate the question but also
warn against treating any early fluctuation as evidence. We do not run a lead-time analysis, because
our pre-registered stopping rule forbids it once the primary discrimination test fails.

**Leakage, overfitting and rare events.** Data leakage ([R34], [R35]) and backtest overfitting
([R36]) motivate the purge/embargo design and the point-in-time audit. Because events are rare
(1.02% prevalence at the primary horizon), we take AUPRC as the primary metric ([R37], [R38]),
report proper scoring rules and calibration ([R39], [R40]), and note that with such low prevalence
calibration is nearly uninformative. Rare-event logistic regression has known small-sample
pathologies ([R41]), which is why we report minimum detectable effects rather than only p-values.

## 3. Data

Frozen input: `research.sqlite`, SHA-256 `dd241bfe…1eeeb71e0d`, 289,443,840 bytes, verified before
every run. It contains 55,090 510(k)/PMA rows; after the material-PMA rule, 31,802 material events,
of which **25,947 are qualifying** (25,603 Traditional 510(k) + 344 original PMA). Excluded:
4,685 Special 510(k) (15.0% of 510(k)s), 527 Abbreviated, 321 Direct, 76 Dual-Track, 7 Post-NSE,
and 239 PMA supplements.

**Entities.** 51 curated `company_key` firms, 38 device `track_id` tracks, 322 observed pairs out of
1,938 possible (16.6%). Crucially, only **3,833 of 31,802 material events (12.1%)** carry *both* a
company key and a track id; 2,885 qualifying events (11.1%) do so, forming 303 pairs. The graph is
therefore built on roughly one eighth of the event channel, and this bounds every conclusion.

**Clocks.** `available_at = event_date + 14 days` for all rows — a documented *estimate* of the bulk
publication lag, not a measurement. `first_seen_at` has a single value (2026-11-01) for all
historical rows. This is a `historical_proxy_asof` dataset: the study is a historical simulation, not
a point-in-time validation.

## 4. Target and evaluation design

**Unit.** `(company c, track k, quarter t)` where both c and k are observable at t and the pair has
had no material event in `(t − 36 months, t]`.

**Label.** `first_observed_qualifying_regulatory_activity`: at least one qualifying event in
`(t, t + H]`. Primary `H = 4 quarters`, secondary `H = 2 quarters`, fixed before results.

**Split.** Quarterly expanding-window rolling origin; a training example may be used at origin t only
if `cutoff + H ≤ t` (purge). The last three evaluable origins are holdout windows
(H4q: 2025-04-01, 2025-07-01, 2025-10-01). Never a random split.

**Scale.** H4q: 41,003 rows, 418 positives, base rate 1.019%, 24 origins. H2q: 44,433 rows, 239
positives, base rate 0.538%, 26 origins.

**Metric.** Average Precision (AUPRC), paired against the strong baseline on identical rows; plus
ROC-AUC, Brier, ECE, P@10%, recall@10%. Inference uses a paired **company-clustered** bootstrap
(2,000 resamples, seed 7) with the pair-clustered bootstrap as a second clustering; MDE at 80% power
is `2.8016 × SE`; multiplicity is controlled by Benjamini–Hochberg at q = 0.10 over eight
pre-registered tests.

## 5. Methods

**Baselines.** B0: constant/company/track/pair historical base rates. B1: ten company/track/pair
history features. B2 (= B3): the frozen 16-feature specification (history + entry history, no
financials). B2g: the same 16 features with HistGradientBoosting.

**Graph features (G1), 12 in total, each computed from a snapshot using only events with
`available_at ≤ t`.** Four peer-entry features (count and time-decayed count of *other* firms' first
entries into the track, similarity-weighted and max-similarity variants); two similarity features
(cosine of 12-month portfolios to track incumbents); two two-hop features (2-hop reach, time-decayed
2-hop activity); one track-co-occurrence feature; three centrality features (company eigenvector,
company clustering, track entrant centrality).

**Randomisation (G2).** Each snapshot is rewired by degree-preserving block swaps over
`(company, track)` activity blocks, preserving every firm's number of active tracks and every track's
number of active firms; rewired edges draw dates from that track's observed date pool, preserving the
per-track time distribution. Only the 12 graph features are recomputed; the other 16 features, the
labels, rows, learner, hyperparameters, purge and metric are identical. **40 seeds.**

**Learner.** One deterministic L2 logistic regression for every feature-set comparison (mirroring the
frozen benchmark; its vectorised form agrees with the repository implementation to 3.5e-17), so that
differences are attributable to features, not to the model.

**Harness validation.** Before any S-028 result, the pipeline reproduces the frozen cycle-2 P1
benchmark exactly: 41,003 rows / 503 positives / 24 origins; per-window AP 0.137085, 0.095027,
0.100476; pooled AP 0.101060 vs persistence 0.044614 (all |diff| < 3e-7).

## 6. Results

### 6.1 Baselines are weak but real

At H4q, pooled AP: constant 0.0134, track base rate 0.0339, company base rate 0.0380, pair base rate
0.0406, B1 0.0690, **B2 0.0751**. B2 is the strongest configuration in all three holdout windows.
The signal is a weak ranking, not a reliable prediction: at a 10% review budget, precision is 5.8%
and recall 44.8% at a 1.02% base rate.

### 6.2 Graph features do not help

Adding the 12 graph features (28 total) gives pooled AP **0.0690**, i.e. **−0.0061** relative to B2,
with company-clustered 95% CI [−0.0222, +0.0045], pair-clustered CI [−0.0335, +0.0104], and MDE
0.0194. Zero of three windows excludes zero. At H2q the difference is −0.0003 [−0.0107, +0.0536].
The pre-registered rule therefore returns **NULL (well-powered)**, and we can exclude a benefit
larger than 0.019 AP at the primary horizon.

All six ablation variants also fall below B2 (pooled AP 0.0673–0.0734), and removing either the
peer-entry or the similarity group *increases* AP slightly — consistent with those features acting
as noise rather than diluted signal. The two features most likely to be mere re-expressions of
history (`g_twohop_reach`, max |r| = 0.849 with a baseline feature; `g_company_eigenvector`, 0.779)
are confirmed as near-redundant: removing the two-hop or centrality group changes AP by less than
0.001. But the remaining features, which have genuine independent variance, also fail to predict.

### 6.3 The real graph does not beat matched random graphs

At H4q the real graph reaches pooled AP 0.06900 while the 40 degree- and time-preserving
randomisations reach 0.06919–0.08198 (median 0.07432): **40 of 40 randomisations are better**. At
H2q the real graph is at about the 25th percentile of its randomisation distribution (30 of 40
better). The pre-registered H2 criterion — real AP above the 97.5th percentile — is not merely
unmet; the direction is opposite.

We report two non-exclusive explanations. Substantively, the specific assignment of firms to tracks
carries no detectable predictive value beyond what node degrees and timing already carry. Technically,
the real graph is highly uneven (mean firm degree 3–4) and rewiring flattens activity; an L2
logistic regression can fit the flattened representation better without that implying the random
graph is more informative. This data cannot separate the two, and we do not claim the randomised
graph is "better".

### 6.4 A stronger learner is worse, and metric choice would reverse the conclusion

HistGradientBoosting on the same features yields pooled AP 0.0567 at H4q (logistic 0.0751) and
0.0354 at H2q (logistic 0.0674; paired CI [−0.0959, −0.0005] excludes zero). Yet its ROC-AUC is
*higher* (0.7847 vs 0.7652; 0.8114 vs 0.7816). The conclusion therefore depends on the pre-declared
metric, which is exactly why it was declared in advance.

### 6.5 Heterogeneity is not decidable

Of 38 tracks only 6 meet the pre-declared reporting floor (n ≥ 10, positives ≥ 5) at H4q, and 5 of 51
firms; at H2q one track and one firm. No track is significantly positive. We therefore report H4 as
**undeterminable**, not as conditional effectiveness. Any "it works in sector X" claim would be
post-hoc selection.

## 7. Discussion

The result is a well-powered negative **for a specific and pre-specified graph**: a sparse
company–technology bipartite activity graph over 51 firms. It is not a negative for relational
structure in general, and three concrete reasons why this graph might fail are worth separating:

1. **Coverage.** 12.1% of events enter the graph. If the unmapped 88% are systematically different
   (e.g. smaller firms, newer codes), the graph is a biased sample of the network.
2. **Scale.** 51 nodes with mean degree ~3 is far below the regime where graph structure is known to
   carry much information; two-hop neighbourhoods approach the whole graph.
3. **Construct.** "Shared regulatory activity in a track" is a weak proxy for a real relationship.
   The data contain no company–company relations at all, so the graph is a co-activity projection,
   not a relationship network.

The third point is the most important: **the study of relational information requires relational
data.** Our negative result should be read as evidence that the available relational proxy is
insufficient, not that relations do not matter.

## 8. Limitations

Summarised here, in full in `LIMITATIONS.md`. The knowledge clock is an estimate (`decision_date +
14 days`); the taxonomy and entity maps use modern knowledge (84 events are dated before the relevant
acquisition completed yet attributed to the parent; 44.11% of `bd`'s events come from acquired
aliases); the graph covers 12.1% of events; "first" means first observed in the window, with 71.4% of
eventually observed pairs already active at the first origin; the label is regulatory activity, not
innovation; no company–company, institutional or paper-author relation exists; the randomised null
tests edge arrangement, not rich relationship; statistical power excludes effects only above 0.019 AP
(H4q); per-track heterogeneity is undecidable; per-case failure analysis is not yet complete; and no
GNN was run, by design.

## 9. Conclusion

After controlling for firm history, track history and time, a sparse company–technology network did
not improve prediction of a firm's first observed qualifying regulatory activity, and its specific
edge arrangement did not outperform degree- and time-matched randomisations. The combination of a
frozen pre-registration, an exactly reproduced benchmark harness, a strong non-graph baseline, a
non-straw-man randomisation and a full negative-results register makes this a trustworthy negative.
The next question is not "which GNN?", but **"is there relational data with enough coverage and the
right construct to test the hypothesis at all?"**

## 10. Reproducibility and artifacts

All code and artifacts are in `research/studies/graph_early_signal_s028/`. Deterministic seeds:
logistic learner (none needed), HGB `random_state=20261104`, randomisation seeds `20261104 + r`,
bootstrap seed 7. The frozen database is SHA-256 verified at load. See `REPRODUCE.md`.

## References

[R01] Xu et al. (2020) Inductive Representation Learning on Temporal Graphs.
[R02] Rossi et al. (2020) Temporal Graph Networks for Deep Learning on Dynamic Graphs.
[R03] Pareja et al. (2020) EvolveGCN.
[R04] Sankar et al. (2018) DySAT.
[R05] Kumar, Zhang, Leskovec (2019) JODIE.
[R06] Trivedi et al. (2018) DyRep.
[R07] Huang et al. (2023) TGB: Towards Better Dynamic Graph Learning.
[R08] Gastinger et al. (2024) TGB 2.0.
[R09] Yu et al. (2023) DyGLib.
[R10] Cong et al. (2023) GraphMixer.
[R11] Wang et al. (2019) Heterogeneous Graph Attention Network.
[R12] Schlichtkrull et al. (2017) R-GCN.
[R13] Hu et al. (2020) Heterogeneous Graph Transformer.
[R14] Liben-Nowell & Kleinberg (2007) The link-prediction problem for social networks.
[R15] Yang, Lichtenwalter, Chawla (2015) Evaluating link prediction methods.
[R16] Zhang & Chen (2018) Link Prediction Based on Graph Neural Networks.
[R17] Mao et al. (2023) Revisiting Link Prediction.
[R18] Kotnis & Nastase (2017/2018) Negative sampling in link prediction.
[R19] Divakaran & Mohan (2020) Temporal Link Prediction: A Survey.
[R20] Rogers (2003) Diffusion of Innovations.
[R21] Jaffe, Trajtenberg, Henderson (1993) Geographic Localization of Knowledge Spillovers.
[R22] Keller (2004) International Technology Diffusion.
[R23] Comin & Hobijn (2010) An Exploration of Technology Diffusion.
[R24] Cappellaro, Ghislandi, Anessi-Pessina (2011) Diffusion of medical technology.
[R25] Powell, Koput, Smith-Doerr (1996) Interorganizational Collaboration and the Locus of Innovation.
[R26] Fleming, King, Juda (2007) Small Worlds and Regional Innovation.
[R27] Bloom, Schankerman, Van Reenen (2013) Identifying Technology Spillovers.
[R28] Priem, Piwowar, Orr (2022) OpenAlex.
[R29] Wang et al. (2020) Microsoft Academic Graph.
[R30] Ansoff (1975) Managing Strategic Surprise by Response to Weak Signals.
[R31] Scheffer et al. (2009) Early-warning signals for critical transitions.
[R32] Dakos et al. (2012) Methods for detecting early warnings of critical transitions.
[R33] Chen (2006) CiteSpace II.
[R34] Kaufman et al. (2012) Leakage in data mining.
[R35] Kapoor & Narayanan (2022) Leakage and the Reproducibility Crisis.
[R36] Bailey et al. (2016) The probability of backtest overfitting.
[R37] Saito & Rehmsmeier (2015) The Precision-Recall Plot.
[R38] Davis & Goadrich (2006) Precision-Recall and ROC curves.
[R39] Gneiting & Raftery (2007) Strictly Proper Scoring Rules.
[R40] Van Calster et al. (2019) Calibration.
[R41] King & Zeng (2001) Logistic Regression in Rare Events Data.
[R42] Gu, Kelly & Xiu (2020) Empirical Asset Pricing via Machine Learning.
[R43] Niu et al. (2024) Evaluating Financial Relational Graphs.
[R44] Xu et al. (2021) HIST.

*Full verified metadata (authors, venue, year, DOI/arXiv, fetched URL, verification status) is in
`artifacts/literature_refs.json`; venue attributions not verified are marked in
`LITERATURE_REVIEW.md`.*
