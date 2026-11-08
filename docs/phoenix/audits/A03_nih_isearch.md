# A03 — NIH iSearch "Predicted breakthroughs in biomedicine" (M3)

Auditing the NIH iSearch Analytics knowledge-base article:
https://support.analytics.nih.gov/hc/en-us/articles/16798095205531-Predicted-breakthroughs-in-biomedicine

…and, because that page is unreachable, the **published** method that the same NIH group (NIH Office of Portfolio
Analysis) has documented for predictive-breakthrough detection:

**Davis MT, Busse BL, Arabi S, Meyer P, Hoppe TA, Meseroll RA, Hutchins BI, Willis KA, Santangelo GM.
"Prediction of transformative breakthroughs in biomedical research." bioRxiv 2025.12.16.694385.**
doi:[10.64898/2025.12.16.694385](https://doi.org/10.64898/2025.12.16.694385) · posted 17 Dec 2025 ·
code: [github.com/NIHOPA/predictivebreakthroughs](https://github.com/NIHOPA/predictivebreakthroughs)

| Field | Value |
|---|---|
| Name | NIH iSearch "Predicted breakthroughs in biomedicine"; underlying method: co-citation network + RMCL topic trajectories + logistic regression breakthrough signal |
| Official URL | https://support.analytics.nih.gov/hc/en-us/articles/16798095205531-Predicted-breakthroughs-in-biomedicine — **inaccessible** (see §1) |
| Type | Public platform documentation (iSearch) + public paper (bioRxiv preprint, not yet peer-reviewed) + public-but-restricted code |
| Licence / terms | Preprint: bioRxiv posting, no reuse licence asserted in the page I read. Code: **"Use of this software requires a license. No rights are granted beyond the view access permitted by the GitHub Terms and Conditions."** (README, verbatim). Data: figshare snapshot linked from the paper's Data/Code page; licence not verified (short-link resolution blocked, §2). |
| Code public? | **Visible, not licensed for use.** Full Java (CCN, R-MCL) + R (trajectories) + Python (logistic regression, candidate generation) source is readable on GitHub under a "contact the authors for a licence" notice. |
| Data public? | **Partly.** The citation snapshot is on figshare; the derived artefacts (trajectories, cluster attributes, breakthrough data, gold-standard tables) are supplementary Data S1–S7 which were not retrieved. The full pipeline additionally requires a MongoDB restore of a multi-GB citation dump. |
| Access barrier | (a) the iSearch article itself is down at the CDN edge; (b) code licence is "requires a license"; (c) compute: full CCN ≈ "at least 384GB of RAM" and ~8 h on a large EC2 instance; R-MCL of the latest year needs "JVM size … 350g". Not runnable on a laptop. |
| GPU / paid needed | No GPU. **Paid/borrowed**: 384–350 GB RAM server (the README explicitly positions this as an AWS EC2 job, i.e. cloud spend). |
| Reproducibility status | **Scaffolding reproduced (logic only); original results not reproduced and not claimed.** No NIH/OPA compute, no citation dump, no licence. Trajectory feature logic (two-year %New, ancestral %New, entropy cohesion, contemporaneous-only influence) and the majority-overlap trajectory linker were re-implemented and self-tested on synthetic data. |

---

## 1) What the source actually says

### 1a. The iSearch article is inaccessible — documented, not worked around

The official URL could not be retrieved. Verified attempts on 2026-11-08:

| Attempt | Result |
|---|---|
| `web_fetch` https URL | `TypeError: fetch failed` |
| `web_fetch` http URL | **HTTP 403 — Cloudflare "Error 1034: Edge IP Restricted"**; page states "The host (support.analytics.nih.gov) resolved to an IP address that the owner of the website does not have access to." (Ray ID a5758af97cf558c7) |
| Zendesk Help Center JSON API (`/api/v2/help_center/en-us/articles/16798095205531.json`) | `fetch failed` |

So this is a **server-side/DNS-level outage of the vendor's own help centre**, not a paywall and not something I
declined to bypass. Consequences, stated plainly:

- I have **not** read the iSearch article, so I cannot report what it says about the *product's* algorithm,
  feature list, refresh cadence, or how it defines a "breakthrough" in-product.
- Everything in §1b–§1d below is from the **published method paper by the same NIH group**, which is the
  scientific basis of NIH's predictive-breakthrough work. I do not assert that the shipped iSearch feature is
  identical to the preprint's pipeline; that equivalence is **unknown** (§2).

### 1b. How a "research breakthrough" is defined (published definition)

The paper does not define a breakthrough by a metric. It defines it **operationally, by external recognition**,
and hand-curates the label:

> "We next identified trajectories that represented 21 different examples of biomedically relevant topics that
> produced breakthroughs … Each of these achievements, which together spanned a 30 year time frame (1984 through
> 2014), was associated with one or more prestigious awards (13 received Nobel prizes and an additional 3 merited
> Lasker awards)"

> "Based upon the descriptions accompanying the announcement of a Nobel prize, Lasker award, or other formal
> recognition of each of these breakthroughs, we manually curated the key transformative papers and years in which
> they were published. This in turn determined the 'breakthrough cluster' and corresponding 'gold standard'
> trajectory"

So: **breakthrough := a discovery recognised by a Nobel Prize / Lasker Award (or comparable formal recognition),
with the announcing paper(s) manually identified and mapped to a topic cluster and year.** Award committees and
manual curation are the ground truth — not citation counts.

And the authors immediately bound what that buys:

> "Since not all discoveries that significantly advance human health are recognized by a major award, it is
> impossible to define the comprehensive set of true instances of breakthroughs, and therefore difficult to
> assess precision and recall."

### 1c. Topic discovery: co-citation network + R-MCL (this is the "clustering")

> "we created a comprehensive network (graph) of the PubMed database, in which publications (nodes) are connected
> by co-citation links (edges)"

> "converting each paper to a sparse vector representing the total number of times it is cited, the identity of
> each paper with which it is co-cited, and the number of those co-citations, and then calculating the cosine
> similarity of all vectors pairwise"

> "we began by constructing a CCN of the 17.2M cited papers in PubMed for all years … through the end of 2017"

> "we chose a low inflation setting of the Regularized Markov Cluster (RMCL) algorithm as the best means of
> identifying the high betweenness edges that bridge distinct topics … as opposed to clustering methods like
> k-means that require the number of topics to be (often arbitrarily) pre-defined. RMCL analysis indicated that
> the 17.2M papers in our network represent a total of 23,867 connected topic clusters, each of which is linked
> directly to a median of 5 (mean of 8.9) nearest neighbor topic clusters."

Because a predictive claim must not use the future, they rebuilt the network year by year:

> "we needed to detect past examples of diagnostic signals without relying upon information 'leaked' from the
> future. We therefore built 36 additional historical CCN/RMCL networks, one for each year between 1981 and 2017,
> excluding all papers and citations beyond the terminal year"

Trajectories are then chained across those yearly networks:

> "we adopted the most straightforward means of matching each cluster to its closest counterpart in these
> historical networks—asking if they shared a simple majority of their papers. If so, we connected them in series,
> so that each cluster from the network of year x is linked to its counterparts in year x-1 and x+1"

**On "recursive multi-level clustering":** no public source I could reach describes the method as recursive or
multi-level. What is documented is **one level** of clustering (RMCL partition into ~23,867 topic clusters) plus a
second-order structure that is *not* a clustering of clusters: a "coarsened version of the entire PubMed CCN/RMCL
network" where "each red dot … represents a topic cluster with its associated intra-cluster edges, collapsed into
one node; each group of high-betweenness edges that bridges two clusters is also collapsed into one edge" — i.e. a
cluster-graph for visualisation and neighbour analysis. Whether the iSearch product internally recurses (e.g.
hierarchical sub-clusters) **is unknown** because its documentation is unreachable. Do not assume it does.

### 1d. The four diagnostic features and the predictive model

Verbatim definitions from the public text:

> "%New … the number of papers published in calendar years 1995 and 1996 can easily be calculated as a percentage
> of all papers assigned to that 1996 cluster" — i.e. **share of the cluster's papers published in year x or x−1**
> (explicitly a two-year window).

> "The second important feature … measures the growth of the literature contained in a cluster's most recent
> ancestor, as described by its trajectory"

> "The third feature is a measure of topic cohesion (calculated as entropy)"

> "The fourth feature captures the occurrence of highly influential publications, as measured by a modified
> version of the Relative Citation Ratio (RCR) … We therefore calculated the influence of each paper as a series
> of snapshots in time, year by year, using only information that would have been available contemporaneously …
> This generates approximately 334 million historical RCR (hRCR) values for the 28 million papers we analyzed. We
> exclusively used hRCRs in our regression"

Model and search:

> "we applied logistic regression to our gold standard trajectories" … "we generated a model consolidating those
> four features into one, and then applied that model to all 186,449 clusters in two distinct 4-year windows that
> are 20 years apart (setA: 1994 through 1997 and setB: 2014 through 2017). To avoid trivial or non-biomedical
> positives in the outputs, we limited the analysis to clusters with 40 or more publications, at least 5% of which
> were linked to at least one NIH award."

Reported yield and historical validation (the "case validation" the audit asks about):

> "We identified 18 and 19 clusters in setA and setB, respectively, that matched the signature of an impending
> breakthrough … This represents an average of 4.6 (median of 5) signals of future biomedical breakthroughs per
> year"

> "Of the 18 diagnostic signals identified in the setA time frame, we previously identified three as gold
> standards … Of the remaining 15, 11 have received prizes or awards … Two topics … were in a group that produced
> translational breakthroughs … one appears to be a false positive signal" (the COX-2/coxib episode)

> "we compiled a comprehensive list of the Lasker awards and Nobel prizes in Medicine since 2014 that we neither
> used as gold standards nor discovered in setA or setB (six each) … Of the remaining eleven, all corresponded to a
> positive logistic regression signal … nine met all the criteria established by our gold standards"

Lead time:

> "those 'signal clusters' precede publication of the key breakthrough papers by up to 12 years (5.6 years on
> average)"

And the self-reported limits — worth quoting because they are stronger than most critiques:

> "for several reasons the accuracy of our predictions and/or the length of the time that elapses between the
> signal and the breakthrough could differ for setB relative to the gold standard or setA signals … the
> exponential expansion of the PubMed database since 1997 … could reduce accuracy by lowering the signal-to-noise
> ratio … the shift in setB to more clinical topics … may result in slower progress, a lower probability of
> achieving the predicted breakthroughs, or both"

### 1e. What the code repository discloses that the paper does not

`github.com/NIHOPA/predictivebreakthroughs` (README, verbatim highlights): the pipeline is CCN computation (Java,
MongoDB-backed citation snapshot, `--threshold 0.35` for edges, `--maxYear` for time slicing) → R-MCL clustering
(`--inflation 1.2 --maxIterations 500`) → R trajectory generation (`trajectory_code_r/1_year_on_year_dynamics.R`,
`2_trajectory_links.R`, `3_node_attributes_merge.R`, `4_trace_trajectories.R`) → Python logistic regression and
candidate filtering (`breakthrough_candidates_code_py/logistic_regression.py`, `breakthrough_candidates.py`,
`cluster.py`, `emergence_candidates.py`, `prediction.py`). Environment: Java 21+, MongoDB 7.x. Scale caveat:

> "For the CCN that includes all articles through the end of 2017, this requires 14.7 billion computations at
> ~500k/sec, the equivalent of approximately eight hours run time on an AWS EC2 server. The computation requires
> at least 384GB of RAM, making computation on a desktop computer not feasible."

## 2) What is NOT disclosed

- **The iSearch product's own definition and algorithm** — the article is down (§1a). Whether the shipped feature
  uses these four features, these filters (≥40 papers, ≥5% NIH-linked), these windows, or a different rule set is
  **unknown**. Marked unknown rather than inferred.
- **Whether the production system is recursive / hierarchical.** Unknown; no accessible source says so.
- **The trained logistic regression coefficients** — described as "a model consolidating those four features into
  one"; the consolidated score form is in supplementary Methods/Data, not the public text. `logistic_regression.py`
  is public but the trained weights are not shipped as data.
- **The entropy feature's input distribution** — "calculated as entropy" of *what* is in supplementary Methods. A
  reimplementation must choose (journal? MeSH? neighbour-cluster mix?) and declare it.
- **The hRCR implementation** — "a modified version of the Relative Citation Ratio"; the modification is in
  supplementary Methods.
- **Data S1–S7, table S1–S3, supplementary text/figures** — not retrieved. Table S1 (the 21 gold standards with
  years and awards) is the label set; without it the supervised task cannot be rebuilt.
- **Figshare data licence** — the short link `https://figshare.com/s/ca05c0539e77fb2a1dc1` returned HTTP 202
  (challenge page) on my HEAD request; I did not download the snapshot to inspect its licence.
- **Cluster labelling** — how the ~23.9k clusters are named/described in the product (needed to make output
  human-usable) is not in the paper.

## 3) Method extraction (precise enough to re-implement, with unknowns isolated)

```
Corpus
  PubMed cited papers, all years through 2017 (17.2M nodes)   [later years via --maxYear runs]

Step 1 — co-citation network (CCN), per terminal year Y
  each paper -> sparse vector over co-cited papers with co-citation counts
  edge weight w(i,j) = cosine similarity of the two sparse vectors
  keep edges with w >= 0.35                       [README default = manuscript value]
  build for each year 1981..2017 from data <= Y    [no future information]

Step 2 — clustering
  R-MCL (regularized Markov clustering) on the weighted CCN
  inflation = 1.2, maxIterations = 500            [README: manuscript values]
  output: partition of papers into ~23,867 clusters (2017 network)

Step 3 — trajectory linking across yearly partitions
  cluster c_Y links to c_(Y-1) if they share a simple majority of papers
  chain backwards to first appearance -> topic trajectory
  (paper reports cluster stability: ~80% chance similar papers stay together >30 years)

Step 4 — features at the terminal cluster of a trajectory
  %New              = share of cluster papers published in year Y or Y-1        [explicit 2-year window]
  ancestral %New    = %New of the cluster's most recent ancestor
  cohesion          = 1 - H(partition)/log(k)   [entropy; the partition is UNDISCLOSED - must be chosen]
  influence (whRCR) = sum of contemporaneous hRCR over cluster papers
                      hRCR(Y) uses only citations dated <= Y      [hard leakage rule]
  (+ mean/SD of each over the 5 preceding years; reported to matter little)

Step 5 — logistic regression
  fit on gold-standard trajectory years (label = year of breakthrough cluster)
  apply to all clusters in a 4-year window
  filters: n_papers >= 40 AND >= 5% of papers NIH-award-linked
  windows used: setA 1994-1997, setB 2014-2017 (186,449 clusters each)

Step 6 — evaluation
  gold standard: 21 topics (1984-2014), 13 Nobel + 3 Lasker + others, breakthrough year manually curated
  signal (highest-%New) cluster year vs breakthrough year -> lead time (max 12y, mean 5.6y)
  out-of-sample check: Lasker/Nobel 2014+ not used in training -> 11/11 positive signals, 9/11 met all criteria
  reported limitation: no complete ground-truth set -> precision/recall not computable
```

## 4) Data requirements, and whether that data exists in a medical-device regulatory setting

Required: a **scholarly citation graph** (co-citation is the core construct), a **gold-standard label set**, a
**funding-acknowledgement linkage** (for the ≥5% NIH filter), and 350–400 GB of RAM.

| Requirement | MedRadar reality |
|---|---|
| co-citation graph over papers | **absent.** No bibliographic layer at all (no citations, no papers). |
| yearly network snapshots | constructible *only* for MedRadar's own event types (authorisations, recalls, trials, 8-Ks) — a different graph with different semantics. |
| gold-standard breakthrough labels | **absent**, and there is no device analogue of a Nobel prize. Candidate proxies would be first-in-class authorisations, breakthrough-device designations, or guideline inclusion — each a *different construct* needing its own curation. |
| funding/acknowledgement feature | `ctgov` trial records carry funders; authorisation records do not. Partial at best. |
| 350–400 GB RAM / long compute | Not available; no cloud spend allowed. |
| publication-level "new" counts | no publication stream. The nearest analogue is new `event` counts per track per year — i.e. M6's machinery, not M3's. |

Conclusion: M3's *substrate* (literature) does not exist in MedRadar. The transferable parts are the **leakage
discipline** and the **recency-burst feature**, not the pipeline.

## 5) My independent implementation and its self-test result

Files: `experiments/phoenix/external/methods/trajectory_features.py` (shared with M5), exercised by
`selftest_synthetic.py` — **56/56 checks pass**, exit 0.

Implemented from the paper's public descriptions only:

| Element | Implementation | Self-test evidence |
|---|---|---|
| `%New` | `pct_new()` counts papers in year **x and x−1** | hand-built cluster 1974/1990/1995/1996 at year 1996 → 0.500 (correct two-year window; a one-year window would give 0.25) |
| ancestral `%New` | `ancestral_pct_new()` reads the previous snapshot | equals `pct_new(previous)` exactly |
| cohesion | `shannon_entropy()`, `topical_cohesion()` = 1 − H/log k | uniform 4-bin → cohesion 0.0, entropy = ln 4; single-bin → 1.0 |
| influence | `whrcr()` = sum; `contemporaneous_influence()` drops citations dated after Y | citation series (1990:1, 1995:3, **2000:100**) at Y=1995 → 4.0, not 104.0 — the future-leak guard is verified numerically |
| trajectory linking | `link_trajectories()` majority-overlap chaining, three rule variants (`of_terminal`, `of_earlier`, `of_both`) because the paper does not say which side's majority | planted 3-year growing cluster recovered as a chain of length 3; unrelated cluster stays separate (chains [3,1]) |
| splits/merges | `find_branches()` reports one-to-many majority overlaps | present, not unit-tested against real data |

**Not implemented, deliberately:** the CCN cosine build, R-MCL, and the logistic regression on real clusters —
each needs the 384 GB citation graph and/or the undisclosed label tables. I did **not** attempt to recreate
"23,867 clusters" or any of the paper's yield/lead-time figures, and I make no claim about them.

## 6) Applicability to MedRadar

Narrow, and mostly negative on the pipeline while positive on two ideas:

1. **Leakage discipline — adopt the principle.** The paper's "build a network for every year using only data up to
   that year" rule is the cleanest statement of point-in-time correctness in any of the four audited methods.
   MedRadar has the fields to enforce it (`event_date`, `as_of`, `available_at`, `timestamp_quality`); any
   MedRadar feature must be computable from `available_at <= t`, not merely `event_date <= t`.
2. **Recency-burst feature — cheap and portable.** `%New`-style "share of the track's activity in the last two
   years" is directly computable on MedRadar `events` by `track_id`/`product_code`, and is a far better-motivated
   novelty indicator than raw counts.
3. **Entropy as a diversification measure — portable**, and it complements M6's HHI (HHI and 1−H/log k are both
   concentration measures; reporting both guards against a single index's artefacts).
4. **The full pipeline — reject for now.** No citation graph, no award-based labels, no 384 GB. Rebuilding it on
   MedRadar event co-occurrence would be a *new method* with unvalidated semantics, not a migration.
5. **Product-level caution.** Because the iSearch article is unreachable, no claim should be made inside MedRadar
   about "what iSearch does". Cite the preprint for the method, not the product.

## 7) Limitations, bias and leakage risks

- **Label bias is severe and acknowledged.** Ground truth = Nobel/Lasker recognition. That systematically favours
  fields with prize infrastructure (basic biomedical discovery), penalises translational, device, nursing,
  public-health and health-services research, and has a long recognition lag (award follows discovery by years to
  decades, which *inflates* apparent lead time). The paper itself notes it cannot compute precision/recall.
- **Survivorship in the gold standards.** 21 curated success stories are used to *learn* what success looks like;
  the negative class is the unremarkable remainder. That is a case-control design with a hand-curated case set.
- **Award-recency leakage.** The 2014+ out-of-sample check is stronger, but "we previously identified three as
  gold standards" in setA means part of setA's apparent success is in-sample.
- **Journal/field skew avoided deliberately, but not prestige skew.** The paper argues against journal-level
  metrics (and shows JCR would 7× the false positives) — good — yet RCR itself embeds field-normalised citation
  prestige.
- **Residual look-ahead.** "excluding all papers and citations beyond the terminal year" is the right rule, but
  the *mapping* of papers to clusters in year Y is computed from a network built in year Y; if the R-MCL partition
  for year Y is later revised (they claim ~80% stability, i.e. ~20% churn), historical signals are not perfectly
  reproducible from the present-day pipeline. This is a reproducibility hazard, not just a modelling choice.
- **Compute-locked.** 384 GB RAM for CCN and 350 GB JVM for latest-year R-MCL makes independent verification
  impossible for a small team; a single re-run is a cloud-spend event.
- **Code licence blocks reuse.** "Use of this software requires a license. No rights are granted beyond the view
  access permitted by the GitHub Terms and Conditions." Viewing ≠ using; MedRadar cannot vendor this code.
- **Preprint status.** Not peer-reviewed at the time of audit; treat effect sizes (5.6 y mean lead, 12 y max) as
  provisional.
- **Leakage risk if reimplemented naively.** Co-citation weights computed from the *final* network leak future
  citations into past snapshots. Any port must recompute weights per snapshot year, as the paper says it does —
  this is the single easiest way to accidentally reproduce a too-good result.

## 8) Decision

**STUDY_ONLY.**

Reasoning: the *published* method is unusual in being both precisely described and accompanied by source code —
but the code is licence-restricted ("requires a license"), the data pipeline needs 350–400 GB of RAM (cloud
spend), the label tables (Data S1–S7) were not obtained, and the product documentation that this task actually
names is **offline at the vendor's edge**. MedRadar additionally lacks the required substrate entirely (no
citation graph, no award labels). What is worth migrating is two design principles — strict point-in-time network
construction, and a two-year recency-burst *share* feature — plus entropy as a concentration measure alongside M6's
HHI. Those are extracted and implemented here; the pipeline is not recommended. If the iSearch article comes back
up, re-audit §1a/§2 before anyone repeats a claim about the product.

## 9) Open questions

1. What does the iSearch article actually claim (breakthrough definition, feature list, freshness, validation)?
   **Blocked** by the Cloudflare 1034 outage at the vendor's edge — retry later.
2. Is the shipped iSearch feature the same pipeline as the preprint, or a predecessor/successor? Unknown.
3. Does the production system use recursive/hierarchical clustering anywhere? No accessible source says so.
4. What distribution does the "entropy" cohesion feature use? (Supplementary Methods; not retrieved.)
5. What exactly is the "modified RCR"? (Supplementary Methods; not retrieved.)
6. What licence applies to the figshare citation snapshot, and is it redistributable for non-commercial research?
   (Short-link resolution returned 202; not downloaded.)
7. Would NIH OPA grant a research licence for the code, and is there a non-AWS path to run the CCN? (Untested;
   I did not contact the authors and will not spend cloud budget.)

## Evidence paths

- `experiments/phoenix/external/methods/trajectory_features.py` — %New (2-year window), ancestral %New, entropy
  cohesion, whRCR, contemporaneous influence guard, majority-overlap trajectory linking, branch detection
- `experiments/phoenix/external/methods/selftest_synthetic.py` — 56 checks incl. the leakage-guard and chaining
  checks reported in §5
- `experiments/phoenix/external/methods/evidence.json` — retrieval + verification record (incl. the failed
  attempts and their exact error strings)
- `experiments/phoenix/external/methods_audit_summary.json` — machine-readable decision record

## Citations

- Davis MT, Busse BL, Arabi S, Meyer P, Hoppe TA, Meseroll RA, Hutchins BI, Willis KA, Santangelo GM.
  *Prediction of transformative breakthroughs in biomedical research.* bioRxiv 2025.12.16.694385.
  https://doi.org/10.64898/2025.12.16.694385 ·
  https://www.biorxiv.org/content/10.64898/2025.12.16.694385v1.full
- Code: https://github.com/NIHOPA/predictivebreakthroughs (README quoted in §1e; licence notice quoted in the
  metadata table)
- Data/Code page: https://www.biorxiv.org/content/10.64898/2025.12.16.694385v1.external-links
  (links to the GitHub repo and to `https://figshare.com/s/ca05c0539e77fb2a1dc1`)
- NIH iSearch article (inaccessible on 2026-11-08): https://support.analytics.nih.gov/hc/en-us/articles/16798095205531-Predicted-breakthroughs-in-biomedicine
