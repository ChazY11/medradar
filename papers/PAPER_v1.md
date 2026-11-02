# Predicting corporate technological evolution from public regulatory filings: five retractions, a controlled-truth frontier, and one confirmed decision rule

**MedRadar Foresight Lab** · version 1 draft · 2026-11-03

---

## Abstract

We ask whether the technological evolution of medical-device firms can be anticipated from public
regulatory filings. We assembled a frozen corpus of **31,802** premarket submissions (510(k) and PMA)
covering **2016-11** to 2026-09 — **119** months — with a deterministic legal-entity universe of
**9,412** entities, and we added two independent evidence lanes: **2,663** device clinical trials
(**43** device tracks, **46** companies) and an archived hiring signal for thirteen firms.

Across seventeen experiment cycles we ran four families of tests: calibrated change detection against
a controlled-truth benchmark, entry and co-movement analyses, an independent-lane association test, and
a rolling-origin benchmark (376 cells, 12 origins, **717** observations). **Five findings that looked
positive were retracted, each by a specific design flaw or control that we then made permanent**: an
entry denominator that mixed legal-entity appearance with firm-level entry; a co-movement signal that
was track growth rather than synchronisation; a cross-lane association that did not exist once the
correct cells were used; a post-hoc nomination whose "holdout" had already been used for selection; and
a benchmark whose outcome was defined against the same window that triggered the signal.

The durable results are negative or methodological. At a controlled 2 % false-alarm rate the best
detector reaches sensitivity **0.223**; the ordering of four detectors is not stable across
resolutions, and above a 2-month bin width the winner is not identifiable. A naive momentum rule flags
**35 of 53** companies while an exact binomial test supports **4**. In a rolling-origin benchmark no
predictor's 95 % interval excludes 1, and the calibrated signal fires **5 flags in 717** observations,
too rarely to trigger on. We show that profile verdicts are unstable across as-of dates (40 stable, 13
changed, **2** reversed of 53), and we report a point-in-time rebuild with **0** leakage problems after
closing a real leakage path in the trial lane and the product-code map.

One narrow exception emerged **after drafting**, and is reported here as an addition rather than folded
into the claim above: a pre-registered confirmatory test shows that a two-month post-alert window
separates transient spikes from sustained changes well enough to make *promotion* a measured decision —
sustained-change precision **0.914** against a **0.696** base rate, with **78.7 %** of spikes caught —
while the three-way ramp-versus-level distinction remains unrecovered. That result was obtained by fixing
a defect found in the discovery sample, so it is a post-discovery confirmation and carries that caveat.

We conclude that this data supports **narrow, budget-explicit statements about public filing rates**
and nothing about intent, capability or internal R&D, and we publish the measurement rules that make
that distinction operational. Every number in this paper is machine-verified against a committed
artifact (Appendix A).

---

## 1. Introduction

Forecasting what a firm will build next is the kind of question that invites confident answers and
punishes them later. The mission behind this work is to build an *open research platform* that predicts
corporate research directions and continuously tests its own predictive ability — and, crucially, to
record where it fails instead of smoothing failures into success stories.

This paper reports the first seventeen cycles of that programme. It is deliberately not a success
story. Its contribution is a **measurement apparatus** and a **failure ledger**: a pre-registered
way of asking whether public data can anticipate technological redirection, plus a documented account
of every claim the apparatus destroyed, including five of our own.

The question we can actually test is narrower than the question that motivates the work. Public
premarket submissions record that a firm asked a regulator for permission to market a device. They do
not record why, what the firm will do next, or what it is capable of. Any model built on them is a model
of **filing behaviour**, and the paper keeps that distinction in every claim.

Three design commitments follow.

1. **Falsifiable targets only.** Every analysis is stated with a statistic, a null, and — when it does
   not reject — a minimum detectable effect. A null without a budget is not a result.
2. **Controls become structure.** Each retraction in this paper produced a *rule* that is now enforced
   in code or by schema, so the same mistake cannot silently recur (Section 5).
3. **Point-in-time or it did not happen.** Claims about what the system knew on a date are backed by
   frozen, hash-verified snapshots, and the pipeline is cut at the as-of date, including every
   auxiliary input.

---

## 2. Data and provenance

### 2.1 Regulatory lane

The primary corpus is a frozen SQLite database of premarket submissions: **31,802** events, both
510(k) clearances and PMA approvals, spanning **2016-11** to 2026-09 (**119** months). Bulk availability
of the underlying records is estimated as decision date plus fourteen days, and the final month of the
window is treated as partially observed and excluded from month-level analysis.

Applicant strings are resolved to legal entities by a deterministic, table-driven normaliser with **no
fuzzy matching**: **9,412** entities are produced from 10,309 raw strings. Two strings denote the same
entity if and only if the normaliser returns the same canonical form. This choice trades recall for
auditability — we can explain every merge — and it is why the entity universe is a *measurement
instrument* rather than a convenience.

Each event is assigned to a technology track (38 tracks in the lane) using product codes; approximately
94 % of assignments are deterministic from a curated code-to-track table and the remainder fall back to
keyword rules. Product-code taxonomy is **not** versioned by effective date, which matters later: new
codes appearing in the taxonomy can manufacture apparent technological waves (Section 4.4).

Data density is the binding constraint throughout. The median cell — one company in one track — holds
25 material events over the window, a rate of about **0.21** events per month, and most months are
empty. Every statistical limitation in this paper traces back to this number.

### 2.2 Independent lanes

Two additional lanes were collected to test whether detected changes are corroborated elsewhere.

**Device trials.** The ClinicalTrials.gov API v2 provides interventional studies with structured
sponsor and intervention fields. A bounded collection run returned **2,663** trial events mapped to
**43** device tracks across **46** companies, using the repository's audited collector. Coverage is
partial by construction: 55 % of returned studies attribute to a curated company and 48 % map to a
device track.

**Hiring.** Public archival data (Internet Archive CDX index) yields monthly counts of distinct
job-posting URLs first captured, a posting-flow proxy that is genuinely historical because the archive
predates the analysis. Coverage is uneven: thirteen firms have posting URLs, but the usability floor
admits few companies, and the lane cannot cover four of the five mandated deep-case firms for
structural reasons (an independent filer only since 2023; a board archived too sparsely; two firms whose
job-level URLs were never archived).

### 2.3 Point-in-time discipline

Analysis code is separated from data access, and every profile can be rebuilt at a past date via an
explicit **as-of cut** that truncates the regulatory lane, the trial lane and the product-code
first-seen map. Profiles carry a per-record leakage audit block. We froze four snapshots
(2020-12-31, 2022-12-31, 2024-12-31, 2026-11-02), each with a manifest recording a SHA-256 per artifact
and per input source; the 2020-12-31 snapshot uses **12,853** lane events and the audit finds **0**
leakage problems across the auditable snapshots.

---

## 3. Methods

### 3.1 Change detection under a controlled false-alarm rate

We compare four detectors on the same monthly series: a naive rate multiplier, a rolling z-score, a
Poisson CUSUM [Page 1954], and a Poisson Bayes-factor rule. Rather than fixing a threshold per detector —
which invites tuning — we calibrate each to a target false-alarm rate (FAR) on a null panel, and measure
sensitivity on a semi-synthetic panel where known changes are injected. Injections are paired across
detectors with common random numbers, inference is by entity-clustered bootstrap, and multiplicity is
controlled by the Benjamini–Hochberg procedure [Benjamini & Hochberg 1995]. Results are reported as a
frontier of sensitivity against FAR rather than a single operating point.

### 3.2 Calibrated comparisons with explicit power

Where two periods are compared (momentum), we use a two-sided exact binomial test of the recent count
conditional on the total — the Poisson rate-ratio test under a constant-rate null [Wald 1945]. When it
does not reject, we report the **minimum detectable ratio at 80 % power** implied by the observed
counts, so a null is never read as "no change".

### 3.3 Pre-registration and split samples

Analyses that could be tuned are pre-registered in a public decision log before they run: the statistic,
the null, the lags, the split point, the decision rule and the expected failure mode. Where a candidate
is selected by looking at results, confirmation requires a **clean design**: nomination from a disjoint
window, then a test on the untouched remainder. We report both the contaminated and the clean result when
both exist.

### 3.4 Rolling-origin evaluation

For predictability we use rolling origins: at each origin the signal sees only data up to that month;
the outcome is the following 12 months; cells are compared with **restricted** and **long-run** baselines
to separate genuine momentum from regression to the mean. Inference is a company-clustered bootstrap
(2,000 replications).

---

## 4. Results

### 4.1 Detection at a controlled false-alarm rate

At a 2 % FAR on the controlled-truth benchmark, sensitivity is **0.223** for the naive rate multiplier,
**0.181** for CUSUM, **0.122** for the Bayes factor, and **0.112** for the rolling z-score. Detection is
possible; the best operating point is weak. At monthly resolution the ordering favours the naive method,
which is uncomfortable and, as the next subsection shows, not stable.

### 4.2 Resolution dependence: no detector is identifiable, but the layer still has to choose one

Repeating the benchmark across bin widths produces a **crossover at a 2-month width** (about 0.42
expected events per bin). Above the crossover the identity of the best detector changes across widths —
naive, CUSUM, z-score and back — and no detector dominates. We therefore report the frontier and say
what it shows: at this sample size, **the best detector is not identifiable**, and any single-winner
claim is an artefact of the chosen resolution.

That is an honest limitation but not an operational answer, because the layer must run at some
resolution. We fixed the deployment resolution to **3 months (quarterly)** — the cadence of portfolio
decisions and re-forecasting this system serves — and read the sweep there. At quarterly resolution with
a 2 % false-alarm budget the **rolling z-score** reaches sensitivity **0.147** (95 % CI 0.112–0.182),
against 0.073 for the Bayes factor, 0.065 for CUSUM and 0.025 for the naive rule: within that resolution
its interval overlaps none of the others, so it is the best of the four *there*.

The identifiability check still fails, and instructively: the winner across widths is naive (1 month),
CUSUM (2), z-score (3), CUSUM (4), z-score (6), and the Kendall tau between the quarterly ranking and the
monthly one is **−1.0** — a complete reversal. The layer therefore "names" a detector only as a
resolution-specific deployment choice, states `resolution: 3 months` wherever the choice is used, and
never cites it as a ranking. If the operating resolution changes, the detector must be re-measured,
because at monthly resolution the same detector is **last**.

### 4.3 Five retracted findings

The programme's most reliable output is the list of things that looked true and were not.

| # | Finding | What destroyed it |
|---|---|---|
| 1 | An entry-prediction signal with measurable skill | A persistence baseline explained the apparent skill; the residual gain was inside the interval |
| 2 | Cross-firm co-movement of technology entry | Conditioning on track volume removed it: **3 of 32** cells survived a lane-volume null, **0 of 32** a track-volume null |
| 3 | Trial activity confirms clearance activity | On **16** eligible cells the whole lag profile sat inside the null band; the largest correlation was **0.036** |
| 4 | An industry entry wave in one IVD track | **3,804** of 4,814 entries (**79 %**) were first-ever appearances of a legal entity, not established firms entering; under a prior-filer control the track collapsed to p = **1.0** and **1,010** entries remained |
| 5 | A replicated entry wave after split-sample testing | The candidate had been nominated with the "holdout" included, so the split-sample p-value was not confirmatory; the clean design nominated **3** tracks and confirmed **0** |

Finding 4 deserves emphasis because it recurred in a second form. Removing events on recently created
product codes *strengthened* the apparent wave (p = **0.0010**), which read as robustness — but the
control that mattered was the entry definition, not the taxonomy. A robustness check that moves the
estimate in the "right" direction is not evidence that the estimate is right.

Two of the retracted results are worth stating with their budgets, because "we found nothing" and "we
could not have found anything" are different claims. The entry-prediction model of Finding 1 reached a
Δ across the average precision baseline of **0.056** on the curated panel, with an interval that covered
zero; on the entity panel it reached **0.097**. The corresponding minimum detectable effect at 140
positives was **0.167**, so the experiment could not have resolved an effect of the size it observed.
Finding 5's holdout had a **0.25** probability of detecting a wave that concentrated 30 % of entries in a
single six-month block — enough to exclude only strong clustering.

### 4.4 Calibration: a ratio rule is not evidence

Applying momentum to the full roster makes the same point at scale. A conventional rule — flag when the
recent-to-prior rate ratio is at least 1.25 — flags **35 of 53** companies. An exact binomial test at
α = 0.05 supports **4**. The survivors are Olympus (rate ratio **4.17**), Philips (**2.03**), Steris
(0.50) and Medline (0.44); the remainder are indistinguishable from a constant rate.

The instructive failures are small counts: a company with four events against one has a rate ratio of
4.00 but p = 0.375 and a minimum detectable ratio of **22.93**. Reporting the ratio invites a claim;
reporting the MDE prevents it. Per-company MDEs span 1.77× to 22.93×, which is why detected counts
cannot be compared across companies as a ranking.

### 4.5 Rolling-origin: a null, and a design flaw caught inside it

The benchmark covers **376** cells, **12** origins and **717** observations. The pre-registered outcome —
does the future block beat the recent block? — produced strongly negative lifts: **0.49** for naive
increase flags, with an interval excluding 1. That looks like anti-prediction and it is an artefact: a
cell is flagged because its recent block is high, so the next block falls back at a constant rate.
Regression to the mean was built into the numerator.

Comparing against the cell's long-run rate instead, the naive-increase lift flips to **1.22** and **no
predictor's interval excludes 1**. The calibrated signal fires **5 flags in 717** observations — too rare
to trigger on. The honest statement is: no evidence of 12-month-ahead predictability above baseline,
with intervals reported; and calibration, which made momentum honest, simultaneously made it too sparse
to predict with at this data's resolution.

### 4.6 Verdict instability across as-of dates

Tracking 53 companies through four as-of dates: **40** verdicts are stable, 13 change at least once and
**2** reverse outright (one company goes no-change → decreasing → increasing → no-change; another
increasing → decreasing → no-change). A quarter of nowcasts moving with the evaluation date is exactly
what the measured MDEs predict, and it is the honest way to present a nowcast: a statement about this
data at this date, not a property of the company.

### 4.7 An Understand layer that cannot flatter itself

Because no association survived, the system's usable output is not a prediction but a **profile**: seven
required fields — identity, technology footprint, momentum, concentration, independent corroboration,
contradictory evidence, limits and provenance. Two rules make it honest: no scores (every sentence is
generated from the numbers in the same structure), and contradictory evidence as a required field, so a
profile without the list of checks it ran is rejected before rendering.

The profile's momentum field now also carries the **validated detector** rather than only a rate test: a
nested `deployment_alerts` block applies the quarterly rolling z-score at threshold 3.5 — the operating point
measured in Section 4.2 — reports alerts from the last eight quarters, and states the measured false-alarm
rate (0.018) and sensitivity (0.147) **inside the profile**. On Medtronic the block returns two live alerts,
each two events against a baseline of 0.25; the counts are printed beside the alert so that "calibrated"
cannot be read as "substantial". The promotion rule of §4.9 is deliberately **not** applied automatically:
it requires the live alert stream and an explicit decision, and automating it would convert a measured rule
into an opaque default.

---

## 4.9 A confirmed decision rule, and how narrowly it is confirmed

**Note added after drafting.** Section 4 removed every association claim this programme made. This
subsection reports the one thing that survived an out-of-sample test — not an association, but a
**decision rule** about alerts.

*Setup.* Three known shapes — a one-month spike, a twelve-month level shift, a twelve-month ramp — were
injected into real (company, track) series at magnitudes of three times the cell's baseline rate. A fixed
detector (three-month rate ≥ twice the eighteen-month baseline) produced the alerts. The classifier may use
only the two months after the alert.

*Pre-registered attempt, and its failure.* The first classifier also looked at the alert month itself.
Balanced accuracy was **0.394** against a 0.333 chance line, and sustained-change precision **0.764** against
a **0.728** base rate: the rule was barely better than always answering "level shift".

*Why it failed.* For a spike the alert month **is** the pulse, so the burst inflated the "post-alert" rate
and the rule almost never called a spike (recall 0.171).

*The fix, and its confirmation.* Excluding the alert month from the window lifted balanced accuracy to
**0.608** on the discovery sample. Because that improvement came from seeing the failure, it was
pre-registered as a confirmatory test on **fresh injections**: three new origins per cell, each at least
six months from the discovery origin, zero origins inside the guard band; same shapes, magnitudes and
detector. Result over **494 alerts**:

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike | 118 | 15 | 17 | **0.787** |
| level | 0 | 144 | 31 | 0.823 |
| ramp | 3 | 142 | 24 | 0.142 |

Balanced accuracy **0.584** (95 % CI 0.556–0.607) and sustained-change precision **0.914** (95 % CI
0.892–0.934) against a **0.696** base rate — both clearing the floors fixed before the run.

*What is confirmed, and what is not.* The **binary** decision — promote an alert to "technology change", or
treat it as a transient spike — is now evidence-based: 0.914 precision instead of 0.696, driven by catching
78.7 % of spikes. The **three-way** distinction is not: ramp recall is 0.142, so a ramp cannot be separated
from a level shift at this counting rate. The aggregate balanced accuracy passes because two of three classes
separate, which is a narrower success than the number suggests.

*Caveat.* Cell reuse across discovery and confirmation is a declared limitation — only the injection months
were fresh. This is a post-discovery confirmation, weaker than confirming an a-priori hypothesis, and it does
not rescue any earlier finding: the five retractions and the rolling-origin null stand. It says nothing about
whether a promoted change is technological.

---

## 4.10 Figures

Four figures are generated **from the committed artifacts** by `papers/figures.py`, which emits SVG
directly (the repository is stdlib-only, so there is no plotting dependency). `papers/verify_figures.py`
re-derives every plotted value from its source artifact, checks the SVG parses, and checks the paper
links it.

- **Figure 1** (fig1_frontier) — detection sensitivity against false-alarm rate for the four detectors on
  the track-level panels, with entity-clustered intervals. Read it as a frontier, not a ranking:
  the ordering at 2 % FAR is why Section 4.2 exists.
- **Figure 2** (fig2_calibration) — rate ratio against exact p-value across 50 companies. Grey markers
  pass the 1.25 ratio rule but not the test; that gap is the calibration result of Section 4.4.
- **Figure 3** (fig3_rolling_origin) — rolling-origin lift with company-clustered intervals for the
  twelve predictor/outcome pairs. Every interval crosses 1 (Section 4.5).
- **Figure 4** (fig4_verdict_stability) — one cell per company and as-of date. Colour changes down a
  column are nowcast verdicts that move with the evaluation date (Section 4.6).

Files: [`fig1_frontier.svg`](figures/fig1_frontier.svg) ·
[`fig2_calibration.svg`](figures/fig2_calibration.svg) ·
[`fig3_rolling_origin.svg`](figures/fig3_rolling_origin.svg) ·
[`fig4_verdict_stability.svg`](figures/fig4_verdict_stability.svg).
Plotted values are recorded in `papers/figures/figures_data.json` for verification.

---

## 5. Measurement rules the programme now enforces

Each retraction left a rule; the rules are the most transferable output of this work.

1. **State the unit you measure.** Entity appearance is not firm entry. Mixing them manufactures waves.
2. **A benchmark outcome must not use the window that triggered the signal.** Otherwise the estimator
   measures its own conditioning.
3. **A ratio is not evidence.** Report a test and, when it fails to reject, a minimum detectable effect.
4. **A holdout cannot confirm a hypothesis nominated with its help.** Nomination and confirmation use
   disjoint data.
5. **A negative conclusion about data availability is as falsifiable as a positive claim.** Our "coverage
   too thin" conclusion was a pagination bug in our own collector; the measurement must be checked before
   the conclusion is carried forward.
6. **Robustness in the preferred direction is not validation.** The estimate that strengthens under a
   control can still be wrong for a different reason.
7. **Check the pipeline, not just the statistics.** Two of our five retractions came from code paths —
   an entry denominator and a trial-lane cut — not from the analysis.

---

## 6. Limitations

The results are bounded by the corpus. Filing rates are a censored, delayed and coarse view of
innovation; the lane holds about **0.21** events per cell-month, so most estimates carry wide budgets.
The taxonomy is unversioned, so apparent novelty can be classification churn. Entity resolution is
deliberately conservative, so some true activity is split across entities. The trial and hiring lanes are
partial samples, not censuses. No result here speaks to intent, capability, internal R&D, or future
technology: they are statements about public regulatory activity and, where relevant, about the
resolution of this data. The programme's canonical track record, including retractions and their reasons,
is the committed decision log and results index.

---

## 7. Reproduction

The corpus, code and artifacts are in a single repository. Every analysis is a runnable script, and the
figures in this paper are re-derivable:

```bash
python -m medradar selftest                      # 854 tests
python experiments/detect_v1/benchmark.py        # controlled-truth frontier
python experiments/b050/rolling_origin.py        # rolling-origin benchmark
python experiments/b027/snapshot_diff.py         # point-in-time audit + snapshot diffs
python experiments/b027/selfcheck.py             # profile self-check (5 profiles + 4 snapshots)
python papers/figures.py                         # regenerate the four figures from the artifacts
python papers/verify_figures.py                  # re-derive every plotted value; check paper links
python papers/verify_claims.py                   # every number in this paper, sourced
```

Artifacts are frozen where they must not move: the research lane database, the trial database, the
forecast registry, and four dated profile snapshots with SHA-256 manifests. The paper's numbers are
verified against those artifacts by `verify_claims.py`, which fails if a claim's source does not contain
the recorded value or if the paper's text does not contain it either.

---

## 8. References

**Data sources.** ClinicalTrials.gov API v2, U.S. National Library of Medicine. Internet Archive
Common Crawl CDX / Wayback CDX index, Internet Archive. U.S. FDA premarket notification (510(k)) and
premarket approval (PMA) datasets.

**Methods.** Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical
and powerful approach to multiple testing. *Journal of the Royal Statistical Society B* 57(1), 289–300.
Page, E. S. (1954). Continuous inspection schemes. *Biometrika* 41(1/2), 100–115. Wald, A. (1945).
Sequential tests of statistical hypotheses. *Annals of Mathematical Statistics* 16(2), 117–186.

**Programme record.** The authoritative internal record is `research/DECISIONS.md` (pre-registrations,
outcomes and retractions), `research/RESULTS/` (one report per cycle) and `research/STATE.json`
(machine-readable state of findings, limitations and blockers).

---

## Appendix A — claim map

`papers/CLAIMS.json` lists every quantitative claim in this paper with the artifact that contains it and
the exact source substring. `papers/verify_claims.py` re-checks both directions (artifact contains the
value; paper contains the value) and exits non-zero on any mismatch. A claim that cannot be located in a
committed artifact is a defect in the paper, not a matter of interpretation.
