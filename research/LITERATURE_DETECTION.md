# Literature review — detecting change in sparse regulatory event streams

**Status:** independent review for the OBSERVE layer (cycle 3, change detection), branch
`research/change-detection-v1`. Written 2026-11-02 by `detect-auditor`.
**Scope:** statistical change-point detection, biosurveillance aberration detection,
multiple-testing control for alerting systems, the operational cost of false alarms,
weak-signal indicators of emerging technology, and the evaluation of detectors against
injected ground truth — as they apply to *monthly counts of material regulatory events
per (entity, technology track)*.

**What this review is for.** It is not a survey. Each cluster maps to one decision the
detection cycle has to make: which detector family to trust (1–2), what kind of noise
the data actually contains (3–4), how to control the alert count (5), what an alert
costs (6), and what the activity counts can and cannot mean (7).

## Verification note (read this first)

Every entry below was checked against a bibliographic record on **2026-11-02**, not
recalled from memory:

- Method: each DOI was resolved individually through the Crossref REST API
  (`https://api.crossref.org/works/{DOI}`). The title, author list, year, venue,
  volume, issue, page range and DOI printed in each entry are the values returned by
  that record; the DOI is printed so a reader can re-resolve it.
- **20 entries, 0 UNVERIFIED.** No entry relies on recollection for its identity. Two
  further records were resolved and then excluded for length, not because they were in
  doubt: Hutwagner, L., Thompson, W., Seeman, G. M. & Treadwell, T. (2003), "The
  bioterrorism preparedness and response Early Aberration Reporting System (EARS)",
  *Journal of Urban Health*, 80(S1), i89–i96, DOI
  [10.1007/pl00022319](https://doi.org/10.1007/pl00022319); and Li, Y. & Tsung, F.
  (2012), "Multiple attribute control charts with false discovery rate control",
  *Quality and Reliability Engineering International*, 28(8), 857–871, DOI
  [10.1002/qre.1276](https://doi.org/10.1002/qre.1276) (Crossref issued 2011).
- **† = no abstract in the Crossref record.** For those entries the *finding* line is
  a deliberately conservative characterisation restricted to what the title, venue and
  publication type establish. It is not a claim that I read the paper. Twelve of the
  twenty entries carry †. A finding line without † is a paraphrase of the abstract in
  the Crossref record.
- Author and title case are normalised where the record supplied them in upper case
  (Page 1954). Year is the Crossref `issued` year. Two entries are cited by the issued
  year although the printed volume carries the next year — Unkel et al. (issued 2011,
  volume 175 of 2012) and Noufaily et al. (issued 2012, volume 32 of 2013). Volume and
  issue are printed on both so either convention resolves.
- **What this verification does not establish:** that any *number* in a paper is
  correct, or that the paper supports our use of it. The "limitations" notes are my
  assessment of what the paper does not support; they are not claims about author
  intent.

## How this review is organised

Seven clusters, 20 entries, then **What the literature does NOT settle for us**.

1. Sequential change detection and the CUSUM family (4 entries)
2. Bayesian change-point detection and Bayesian model comparison (3)
3. Biosurveillance aberration detection and how it is evaluated (4)
4. Count models with overdispersion and estimated baselines (1)
5. Multiple testing, FDR, and the alerting problem (3)
6. The operational cost of false alarms (2)
7. Early-warning indicators of emerging technology (3)

---

## Cluster 1 — Sequential change detection and the CUSUM family

**1. Page, E. S. (1954). "Continuous inspection schemes." *Biometrika*, 41(1–2),
100–115. DOI: [10.1093/biomet/41.1-2.100](https://doi.org/10.1093/biomet/41.1-2.100).** †
- *Finding:* introduces the scheme that became the CUSUM (cumulative-sum) control
  chart, for detecting a persistent shift in an inspected process.
- *Why it matters here:* the ancestor of our detector 3. The contrast the design draws
  between a "rolling z-score" and a "Poisson CUSUM" is the seventy-year-old distinction
  between a single-look test at each month and an accumulating evidence sum. Naming the
  distinction does not tell us which wins on *our* streams; that is the experiment.
- *Limitations:* continuous measurements, known in-control parameters, a shift of known
  direction; silent on counts, on sparse event streams, and on trend.

**2. Lucas, J. M. (1985). "Counted Data CUSUM's." *Technometrics*, 27(2), 129–144.
DOI: [10.1080/00401706.1985.10488030](https://doi.org/10.1080/00401706.1985.10488030).** †
- *Finding:* extends the CUSUM to counted data rather than continuous measurements —
  the data type our monthly event counts actually are.
- *Why it matters here:* our "Poisson CUSUM" is this paper's scheme. Its design
  parameters (a reference value and a control limit) are set for a *known* in-control
  rate and a *specified* shift size. If the benchmark's grid covers multipliers from
  1.5× to 3×, one control limit cannot be tuned for all of them, and a single
  pre-registered limit will be favourable for the grid points it was tuned on.
- *Limitations:* independent Poisson counts with a stable, known baseline; no treatment
  of a baseline estimated from a short record, of exposure changes, or of many streams
  tested at once.

**3. Moustakides, G. V. (1986). "Optimal stopping times for detecting changes in
distributions." *The Annals of Statistics*, 14(4), 1379–1387. DOI:
[10.1214/aos/1176350164](https://doi.org/10.1214/aos/1176350164).**
- *Finding (abstract):* proves that Page's stopping time is optimal, in a well defined
  minimax sense, for detecting changes in distributions — a generalisation of an
  earlier asymptotic result.
- *Why it matters here:* **this is the single most important entry in the review for
  interpreting hypothesis H-D1.** If the truth generator is a step change in a Poisson
  rate, a CUSUM-like detector is not "better on this data" — it is optimal *for that
  generator* by theorem. A benchmark whose injected change is a step and whose
  headline detectors are likelihood-based therefore cannot return the result "the
  likelihood detectors are not better" except through an implementation defect. The
  hypothesis must be stated against the *mis-specified* change classes to be falsifiable.
- *Limitations:* the optimality is minimax/worst-case, requires the post-change
  distribution (and its magnitude) to be specified, and says nothing about robustness
  to misspecification — spikes, ramps, overdispersion — or about estimated parameters.

**4. Frisén, M. (2003). "Statistical surveillance. Optimality and methods."
*International Statistical Review*, 71(2), 403–434. DOI:
[10.1111/j.1751-5823.2003.tb00205.x](https://doi.org/10.1111/j.1751-5823.2003.tb00205.x).**
- *Finding (abstract):* reviews optimality criteria across the subcultures of statistical
  surveillance, demonstrates the shortcomings of some criteria through their implications,
  and presents the methods uniformly as likelihood ratios so that they can be compared.
- *Why it matters here:* it answers "which detector is best?" with "there is no
  criterion-free answer". Different criteria (minimax expected delay, average run length,
  posterior probability) rank the same methods differently, so "the CUSUM dominates the
  naive baseline" is only meaningful relative to a named criterion. Our design does name
  one — matched FAR plus detection delay — and it has to keep naming it.
- *Limitations:* a review of the surveillance literature, not of sparse regulatory event
  counts; no guidance on five events per decade or on entity panels.

---

## Cluster 2 — Bayesian change-point detection and Bayesian model comparison

**5. Raftery, A. E. & Akman, V. E. (1986). "Bayesian analysis of a Poisson process with
a change-point." *Biometrika*, 73(1), 85–89. DOI:
[10.1093/biomet/73.1.85](https://doi.org/10.1093/biomet/73.1.85).** †
- *Finding:* Bayesian analysis of a single change-point in a Poisson process, treating
  the change-point location and the two rates as parameters with a posterior.
- *Why it matters here:* the direct ancestor of our detector 4 ("Poisson Bayes factor").
  It makes the change-point location a parameter: the segment-length prior then decides
  what counts as "a change" at all. That is a modelling choice with operational
  consequences, and the design does not currently name it.
- *Limitations:* one change-point, one stream, assumed priors; sensitivity to the prior
  on the change-point location is exactly the issue that matters when a stream may
  change repeatedly.

**6. Kass, R. E. & Raftery, A. E. (1995). "Bayes factors." *Journal of the American
Statistical Association*, 90(430), 773–795. DOI:
[10.1080/01621459.1995.10476572](https://doi.org/10.1080/01621459.1995.10476572).** †
- *Finding:* the standard reference for Bayes factors, including guidance on how Bayes
  factor magnitudes are conventionally reported as evidence.
- *Why it matters here:* a Bayes-factor detector needs a threshold, and the familiar
  thresholds (3, 10, 30) are **reporting conventions, not calibrated false-alarm
  rates**. A Bayes-factor detector therefore enters the delay-vs-false-alarm comparison
  with no defined operating point unless its FAR is measured. Comparing it to a CUSUM
  at nominal α without measuring both is not a comparison.
- *Limitations:* conventions, not error-rate control; nothing about sequential
  monitoring of many streams or about repeated looks.

**7. Fearnhead, P. & Liu, Z. (2007). "On-line inference for multiple changepoint
problems." *Journal of the Royal Statistical Society: Series B*, 69(4), 589–605. DOI:
[10.1111/j.1467-9868.2007.00601.x](https://doi.org/10.1111/j.1467-9868.2007.00601.x).**
- *Finding (abstract):* gives an on-line algorithm for exact filtering of multiple
  change-point problems, yielding the joint posterior over the number and position of
  change-points; resampling reduces the cost from quadratic to linear at the price of
  small errors, with two new optimum resampling schemes proposed.
- *Why it matters here:* it shows that "how many changes did this stream have?" is a
  posterior quantity, not a binary alarm. That is a better-shaped output for the OBSERVE
  layer than a threshold crossing, and it is a rival to the four detectors in the design
  that the design does not currently consider — a scope decision worth recording.
- *Limitations:* needs a hazard/segment-length prior; the posterior is conditional on
  the model and prior; no guidance for counts with denominators or entity panels.

---

## Cluster 3 — Biosurveillance aberration detection and how it is evaluated

**8. Farrington, C. P., Andrews, N. J., Beale, A. D. & Catchpole, M. A. (1996). "A
statistical algorithm for the early detection of outbreaks of infectious disease."
*Journal of the Royal Statistical Society: Series A*, 159(3), 547. DOI:
[10.2307/2983331](https://doi.org/10.2307/2983331).** †
- *Finding:* a regression-based (quasi-Poisson) algorithm with a reweighted historical
  baseline, intended to absorb trend, seasonality and past outbreaks, for routine
  prospective surveillance of counts.
- *Why it matters here:* the closest *operational* analogue of our problem — counts,
  many series, a standing false-alarm budget, and a real cost per alert. It also shows
  what our design is missing: it **models** overdispersion and seasonality in the
  baseline rather than merely "checking" them, and it downweights past aberrations so
  one outbreak does not raise the threshold for the next. Our "month-of-year seasonality
  check" is a check, not a correction, and a January deficit of the size measured in
  this lane (see review §3) is not addressed by a check.
- *Limitations:* designed for short-horizon outbreak detection on dense national counts;
  a firm-level baseline of five events per decade is outside its operating regime.

**9. Unkel, S., Farrington, C. P., Garthwaite, P. H., Robertson, C. & Andrews, N.
(2012). "Statistical methods for the prospective detection of infectious disease
outbreaks: a review." *Journal of the Royal Statistical Society: Series A*, 175(1),
49–82. DOI:
[10.1111/j.1467-985x.2011.00714.x](https://doi.org/10.1111/j.1467-985x.2011.00714.x).**
(Crossref issued 2011; printed volume 2012.)
- *Finding (abstract):* a comprehensive review of statistical methods proposed for
  early outbreak detection, illustrated on laboratory and syndromic surveillance data.
- *Why it matters here:* the best single map of the method space we are choosing from,
  and the clearest statement that these methods are compared on timeliness *at an
  operational false-alarm rate*, not on nominal test size. It is also evidence that this
  literature is mature about evaluation — and that our design is re-deriving that
  evaluation practice in a far sparser regime.
- *Limitations:* infectious-disease setting with dense series; nothing on regulatory
  reference events, entity panels, or counts of five per decade.

**10. Noufaily, A., Enki, D. G., Farrington, P., Garthwaite, P., Andrews, N. & Charlett,
A. (2012). "An improved algorithm for outbreak detection in multiple surveillance
systems." *Statistics in Medicine*, 32(7), 1206–1222. DOI:
[10.1002/sim.5595](https://doi.org/10.1002/sim.5595).** (Crossref issued 2012; printed
volume 2013.)
- *Finding (abstract):* reviews the performance of an operational quasi-Poisson
  multiple-surveillance system with the explicit aim of reducing false reports while
  retaining power, using extensive simulations across contrasting scenarios, and
  proposes improvements to trend treatment, seasonality and baseline reweighting.
- *Why it matters here:* **the closest published precedent for our Evaluation A** —
  inject known aberrations over a real baseline and measure false reports against power.
  Two lessons: (i) they tune on a *model of the aberration* and validate against the
  real system's operational record, not against their own injected grid alone; (ii) the
  aberrations they simulate are multiplicative increases over the same quasi-Poisson
  model the detector assumes. The precedent therefore reproduces the circularity that
  §2.1 of the design review objects to.
- *Limitations:* the paper does not claim that performance on model-aligned simulated
  aberrations licenses performance on non-step changes, and we should not either.

**11. Buckeridge, D. L., Burkom, H., Campbell, M., Hogan, W. R. & Moore, A. W. (2005).
"Algorithms for rapid outbreak detection: a research synthesis." *Journal of Biomedical
Informatics*, 38(2), 99–113. DOI:
[10.1016/j.jbi.2004.11.007](https://doi.org/10.1016/j.jbi.2004.11.007).** †
- *Finding:* a research synthesis of outbreak-detection algorithms that compares method
  families together with the evaluation designs used to compare them.
- *Why it matters here:* it is the "how should detectors be compared" reference, and its
  central point is ours: a comparison without a shared, explicit truth model and a
  shared operating point is not interpretable. In our design both the truth model and
  the operating point are chosen by the experimenter, so both must be pre-registered and
  defended, not merely fixed by seed.
- *Limitations:* biosurveillance data, dense series; predates online-FDR and Bayesian
  online change-point methods.

---

## Cluster 4 — Count models with overdispersion and estimated baselines

**12. Weiß, C. H. & Testik, M. C. (2011). "The Poisson INAR(1) CUSUM chart under
overdispersion and estimation error." *IIE Transactions*, 43(11), 805–818. DOI:
[10.1080/0740817x.2010.550910](https://doi.org/10.1080/0740817x.2010.550910).** †
- *Finding:* analyses the Poisson CUSUM chart when the counted process is
  overdispersed/autocorrelated (INAR(1)) and when the in-control rate must be estimated
  rather than known.
- *Why it matters here:* **the single most directly transferable warning in this
  review.** It says that a Poisson CUSUM's nominal false-alarm rate is not its
  operational one when the baseline is estimated or the counts are overdispersed. Our
  streams have both properties by construction — the baseline is a plug-in estimate from
  roughly five events per decade, and the measured variance/mean ratio is 1.36 (median)
  and 3.02 (90th percentile) among the 95 largest streams of the all-events frame, and
  1.11 / 1.40 among the 39 largest streams of the material-only frame (both measured
  2026-11-02; Appendix A of `docs/research/DETECTION_DESIGN_REVIEW.md`). The dispersion
  is therefore mild at stream level; the *larger* departures from a Poisson null in this
  lane are calendar and boundary effects (§3.4 of the same review). Either way, the
  false-alarm axis of the proposed benchmark is a property of the Poisson assumption
  unless it is measured empirically on the real streams.
- *Limitations:* manufacturing/INAR context with a parametric autocorrelation model;
  nothing at five events per decade, nothing on entity heterogeneity.

---

## Cluster 5 — Multiple testing, FDR, and the alerting problem

**13. Benjamini, Y. & Hochberg, Y. (1995). "Controlling the false discovery rate: a
practical and powerful approach to multiple testing." *Journal of the Royal Statistical
Society: Series B*, 57(1), 289–300. DOI:
[10.1111/j.2517-6161.1995.tb02031.x](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x).**
- *Finding (abstract):* defines the false discovery rate — the expected proportion of
  falsely rejected hypotheses — and gives a simple step-up procedure that controls it,
  with more power than family-wise error control when many hypotheses are tested.
- *Why it matters here:* it is the basis of the design's alert-count control, and it is
  the right idea. But the guarantee is for *one* family of hypotheses, in expectation,
  under independence or positive dependence. Our tested cells are neither independent
  (shared monthly volume, shared taxonomy) nor a single family: each stream is also
  examined at 120 successive months, and BH applied once across cells does not control
  the error rate over looks.
- *Limitations:* no time dimension; no per-alert guarantee; nothing about the operating
  cost of an alert or about dependence induced by a common factor.

**14. Benjamini, Y. & Yekutieli, D. (2001). "The control of the false discovery rate in
multiple testing under dependency." *The Annals of Statistics*, 29(4), 1165–1188. DOI:
[10.1214/aos/1013699998](https://doi.org/10.1214/aos/1013699998).**
- *Finding (abstract):* proves that the BH procedure also controls the FDR when the test
  statistics are positive-regression-dependent (PRDS) on the nulls, and gives a
  procedure valid under arbitrary dependency.
- *Why it matters here:* our cells are positively dependent through the panel-wide
  monthly volume, so BH is *arguably* defensible — but that is an argument to be made
  and checked, not assumed, and the arbitrary-dependence variant is the obvious
  sensitivity analysis. It also tells us what to expect operationally: under a strong
  common factor, rejections arrive in bursts, which is precisely the alert-flood failure
  mode the OBSERVE layer must avoid.
- *Limitations:* PRDS has to be established or the conservative variant paid for; no
  guidance for sequential looks.

**15. Foster, D. P. & Stine, R. A. (2008). "α-investing: a procedure for sequential
control of expected false discoveries." *Journal of the Royal Statistical Society:
Series B*, 70(2), 429–444. DOI:
[10.1111/j.1467-9868.2007.00643.x](https://doi.org/10.1111/j.1467-9868.2007.00643.x).**
- *Finding (abstract):* an adaptive sequential multiple-testing procedure that controls
  mFDR — the ratio of expected false rejections to expected total rejections — at every
  rejection, spending and earning α across looks.
- *Why it matters here:* an alerting system tests every month, so the error rate that
  matters is over the *stream of alerts over time*, not over one month's cross-section.
  Re-running BH each month does not control that; α-investing is the published framework
  that does. Its weakness is equally relevant: mFDR is a weaker guarantee than FDR, and
  the wealth/α-spending design is a free parameter that can be tuned to any desired
  alert volume.
- *Limitations:* mFDR not FDR; the α-investment schedule is a design choice; nothing on
  dependent or very sparse streams.

---

## Cluster 6 — The operational cost of false alarms

**16. van der Sijs, H., Aarts, J., Vulto, A. & Berg, M. (2006). "Overriding of drug
safety alerts in computerized physician order entry." *Journal of the American Medical
Informatics Association*, 13(2), 138–147. DOI:
[10.1197/jamia.m1809](https://doi.org/10.1197/jamia.m1809).** †
- *Finding:* reviews and characterises clinicians' overriding of computerised drug-safety
  alerts — the operational form of alert fatigue.
- *Why it matters here:* the operational case for FDR control, from a domain where the
  cost of an alert (clinician time) and the harm of ignoring one (patient safety) are
  both real. The structure transfers: once alert precision falls below what the
  recipient can triage, the alerting channel loses value independently of its recall.
  That is the strongest argument for treating *alerts per month* as a first-class output
  of the OBSERVE layer rather than a diagnostic of it.
- *Limitations:* clinical decision support; the alert cost is clinician time, not analyst
  triage; no transferable quantitative threshold.

**17. Cvach, M. (2012). "Monitor alarm fatigue: an integrative review." *Biomedical
Instrumentation & Technology*, 46(4), 268–277. DOI:
[10.2345/0899-8205-46.4.268](https://doi.org/10.2345/0899-8205-46.4.268).** †
- *Finding:* integrative review of alarm fatigue from physiological monitoring, treating
  the volume of non-actionable alarms as a hazard in itself.
- *Why it matters here:* second independent statement of the same mechanism, from a
  different literature. It supports reporting detection probability *and* alerts per
  stream-year *and* the alert volume the desk would actually receive. A detector that
  wins on delay by firing several times more alerts is not better in the sense the
  OBSERVE layer needs.
- *Limitations:* monitor alarms, not statistical detection theory; defines no false-alarm
  rate and gives no quantitative tolerance.

---

## Cluster 7 — Early-warning indicators of emerging technology

**18. Rotolo, D., Hicks, D. & Martin, B. R. (2015). "What is an emerging technology?"
*Research Policy*, 44(10), 1827–1843. DOI:
[10.1016/j.respol.2015.06.006](https://doi.org/10.1016/j.respol.2015.06.006).** †
- *Finding:* asks and answers what an emerging technology is, arguing that it is a
  multi-attribute construct rather than a single measurable quantity, and relating
  existing indicators to those attributes.
- *Why it matters here:* the conceptual gap between "the count of this company's 510(k)
  filings in this track rose" and "a technology is emerging". Our detector measures a
  rate change in a *record of regulatory filings*; emergence is a construct with several
  attributes, of which filing rate speaks to at most one. This is why the only defensible
  claim for the OBSERVE layer is a statement about activity rate.
- *Limitations:* conceptual/definitional; no detection methodology; does not address
  distinguishing emergence from a filing-cycle artifact.

**19. Kyebambe, M. N., Cheng, G., Huang, Y., He, C. & Zhang, Z. (2017). "Forecasting
emerging technologies: A supervised learning approach through patent analysis."
*Technological Forecasting and Social Change*, 125, 236–244. DOI:
[10.1016/j.techfore.2017.08.002](https://doi.org/10.1016/j.techfore.2017.08.002).** †
- *Finding:* supervised learning on patent data to forecast which technology areas will
  emerge.
- *Why it matters here:* the patent-based counterpart of what we do with regulatory
  events, and a useful contrast in what counts as ground truth. It has a labelled target
  (known emergence); our "real technical change" has none, and the design substitutes
  an independent-source association test for it — a much weaker object than a label.
- *Limitations:* patents, not devices; the supervised target is itself a judgement;
  no false-alarm or alerting evaluation.

**20. Watts, R. J. & Porter, A. L. (1997). "Innovation forecasting." *Technological
Forecasting and Social Change*, 56(1), 25–47. DOI:
[10.1016/s0040-1625(97)00050-4](https://doi.org/10.1016/s0040-1625(97)00050-4).** †
- *Finding:* surveys bibliometric and patent-indicator approaches to forecasting
  innovation.
- *Why it matters here:* the origin of the premise the OBSERVE layer rests on — that
  count indicators move before a technology arrives. The premise is old and reasonable
  at aggregate level; it is **not** a validated law in the medical-device regulatory
  lane, and that is the honest status to attach to any detection we publish.
- *Limitations:* aggregate/technology-level; leading-indicator behaviour is asserted
  more than tested; no detection-error framework.

---

## What the literature does NOT settle for us

- **No published criterion for "real technical change" in a regulatory filing stream.**
  Every method in clusters 1–4 detects a change in the *rate of an observed process*.
  None of them defines, or validates, the thing the OBSERVE layer actually wants
  (a change in a firm's technology programme). The literature can tell us whether a rate
  changed; it cannot tell us whether technology changed. That gap has to be closed by a
  confirmation design, and no published confirmation design exists for this data.
- **No FAR/delay operating point for streams of this sparsity.** Biosurveillance reports
  operational trade-offs on national counts in the hundreds per week. Our median material
  stream has five events *per decade* (measured, review §3.2). This regime is outside
  the methodological literature, so the design must establish and publish its own power
  floor rather than borrow a benchmark.
- **No protocol that prevents a benchmark from confirming the model it injected.** The
  optimality result (entry 3) is stated for a specified change model; the evaluation
  literature (entries 10, 11) compares methods on simulated aberrations from the same
  family the detectors assume. Nobody has published the protocol that would stop our
  semi-synthetic benchmark from being a demonstration of a theorem, and that is precisely
  the protocol we need before the benchmark runs.
- **Overdispersion and estimated baselines are known to inflate false alarms, but the
  size of the inflation at five events per decade is not derivable from the literature.**
  Entry 12 gives the mechanism, not a number for our regime. The number has to be
  measured on our streams.
- **Multiple testing over *both* cells and looks is not solved by BH.** BH controls one
  family; the online-FDR framework controls a weaker quantity (mFDR) with a free
  α-spending parameter. Neither tells us which error rate an analyst-facing alert stream
  should be held to; that is a policy decision the literature leaves to us.
- **Nothing in the literature says how many alerts a month an intelligence desk will
  act on.** The alert-fatigue work gives the mechanism (overriding, desensitisation) and
  no transferable threshold. "False alarms per stream-year ≤ 1" is therefore our
  invention, and should be labelled as such rather than presented as an established
  standard.
- **Indicator work establishes association at aggregate level, not detection validity at
  firm level.** Entries 18–20 support "counts correlate with emerging technology" at
  technology or field level. None supports "a step change in one firm's 510(k) rate is a
  technology change rather than a product refresh or a filing-strategy change" — which is
  exactly the inference the OBSERVE layer is tempted to make.
- **Whether the OBSERVE output should be a binary alarm at all is open.** Entry 7
  (and the multiple-change-point tradition more generally) suggests a posterior over the
  number of change-points as the output. Choosing a binary alarm is a product decision,
  not a finding of the literature.

---

*End of review. 20 entries; 0 UNVERIFIED; 12 marked † (finding limited to the
title-level record because Crossref holds no abstract). If a DOI no longer resolves,
treat that entry as unverified until re-checked.*
