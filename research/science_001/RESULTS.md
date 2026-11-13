# RESULTS - the first exploratory experiment

Pre-registration: `PROTOCOL.md`, SHA-256
`0c44ad25005eb731140a555f679d9be06501b819c5e5036cf4a009edd3e48768`
(embedded in `artifacts/experiment_results.json`; the test suite fails if it drifts).
**Deviations: none.**

---

## 1. What we actually tested

> Does the R&D/technology intensity of a firm's own 8-K prose predict, 90 days
> later, an independently defined technology-transaction disclosure (SEC item
> 1.01 material agreement, or 2.01 completed acquisition/disposition)?

* observation unit: one original 8-K accession;
* input: rates of 25 + 25 pre-registered R&D and technology terms per 1,000
  words, from that filing's own body and exhibits, plus an activity control;
* outcome: SEC item codes of *later* filings only - never the unit's own text;
* split: chronological, train <= 2024-12-31, holdout >= 2025-01-01;
* primary statistic: dAUC = AUC(B3) - AUC(B2), circular-shift permutation null,
  2,000 permutations, seed 20261114;
* controls declared in advance: placebood outcome (item 5.07), positive control
  (any 8-K), cross-firm label transplant, cluster bootstrap over issuers.

## 2. The sample

| | count |
|---|---|
| issuers in registry | 12 (11 file 8-K; Philips files 20-F/6-K and is used only for the clock) |
| full-submission files downloaded and hashed | **720** |
| in the 2021-01-01 .. 2026-09-30 panel | **683** (671 8-K + 12 8-K/A) |
| analysis events after excluding amendments and censored windows | **636** |
| dropped: forward window not fully observable | 35 |
| download failures | 0 |
| filings excluded as not 8-K/8-K/A | 9 836 |
| filings excluded as outside the window | 31 |
| verified acceptance instants (grade A) | 720 / 720 |

Per year: 2021:116, 2022:103, 2023:109, 2024:118, 2025:131, 2026:106 (panel).

Holdout: 199 events, 50 positive (25.1%). Train: 437 events, 25.9% positive.

## 3. Result

| model | predictors | holdout AUC | 95% cluster-bootstrap CI |
|---|---|---|---|
| B0 prevalence | none | 0.500 | - |
| B1 firm mean | none (per-firm train rate) | **0.724** | [0.576, 0.865] |
| B2 activity | prior-90d 8-K count, item 2.02 | 0.533 | [0.422, 0.636] |
| B3 activity + prose | B2 + `rd_per_1k` + `tech_per_1k` | **0.467** | [0.355, 0.577] |

**Primary test: dAUC = -0.066. Permutation p (two-sided) = 0.839; one-sided
p(dAUC > 0) = 0.161. Cluster-bootstrap 95% CI for dAUC: [-0.187, +0.058].**

Verdict: **null**. Adding R&D/technology prose to the activity baseline does not
improve discrimination, and the point estimate is if anything negative. The
honest summary of the resolvable range: this design can exclude an AUC gain
larger than about **+0.06**, and cannot exclude anything smaller.

## 4. Controls, and why the null is interpretable

A null is only worth reporting if the machinery can find real signal. It can:

| control | expected | observed |
|---|---|---|
| positive control: activity -> any 8-K in 90 days | clearly > 0.5 | **AUC 0.825** (B3 0.841); prevalence 96.5% |
| placebo outcome: tech prose -> item 5.07 (annual-meeting votes) | null difference | **dAUC = +0.001, p = 0.936**; but B3 AUC 0.609 because activity predicts meeting season - i.e. the pipeline finds autocorrelation where it exists |
| cross-firm label transplant (negative control) | ~0.5 | **0.538** |
| univariate AUCs | ~0.5 for prose | rd 0.440, tech 0.438, dev 0.415, words 0.546 |

So the pipeline detects event structure when event structure is present. The
prose features specifically carry none.

## 5. The result that matters more than the null

**B1 - firm identity alone - reaches AUC 0.724 [0.576, 0.865]**, far above every
model that uses disclosure content. The 90-day technology-event label is largely
a *firm property*:

| issuer | events | P(1.01/2.01 8-K in next 90d) |
|---|---|---|
| ZBH | 72 | 0.514 |
| BAX | 79 | 0.481 |
| SYK | 53 | 0.340 |
| BSX | 78 | 0.321 |
| GEHC | 48 | 0.271 |
| MDT | 54 | 0.204 |
| DXCM | 67 | 0.149 |
| ABT | 52 | 0.115 |
| RMD | 39 | 0.077 |
| EW | 46 | 0.043 |
| ISRG | 48 | **0.000** |

This is the single most useful finding of the study for MedRadar's programme: a
model of "which firm is this" beats a model of "what did this firm say". Any fu-
ture early-signal work on this source must therefore be **firm-conditional**
(hazards / matched within-firm designs), not pooled cross-firm classification,
or it will be measuring industry composition and calling it signal.

## 6. Why the permutation null is not centred at zero

The null distribution of dAUC is centred at **-0.107** (95% band
[-0.186, -0.024]), not at 0. That is a property of the *statistic*, not a bug:
models are fitted on train and held fixed, so circularly shifting holdout labels
within a firm preserves each firm's label multiset but destroys the alignment
between the extra prose features and the within-firm order that the fit partly
captured. The consequence for reading the table is important and is stated on
the figure: **only the observed percentile is interpretable**, and it is inside
the band (p = 0.839). The point estimate -0.066 must not be read as "prose harms
prediction"; it is inside chance-order variation.

## 7. 8-K/A amendments

12 amendments in the panel. EDGAR publishes no amendment-to-original key, so the
link is reconstructed:

| evidence | count |
|---|---|
| original accession quoted in the amendment text | 0 |
| a filing date named near "Form 8-K"/"amendment" vocabulary, resolving to one candidate | **5** |
| no textual evidence, but identical SEC item set on the closest preceding 8-K | 4 |
| assumption only (closest preceding 8-K, item sets differ) | 3 |

Textual resolution rate: **5/12 (42%)**; nothing reaches "high". Amendments were
therefore excluded from the experiment as observation units rather than being
silently merged, and the item-set tier is labelled low-confidence in the artifact.

## 8. What this experiment can and cannot answer

**Can answer (with the stated uncertainty):**
* EDGAR's acceptance instant is reconstructible to the second for every filing
  tested, and is a valid lower bound on public availability.
* For 8-Ks, the acceptance-to-archival-write gap is a median 35 s before the
  17:30 ET cut-off and a median 11.6 h after it (weekend for Friday evenings).
* On this panel, R&D/technology word rates in 8-K prose do **not** improve
  prediction of the 1.01/2.01 event family over an activity baseline, and cannot
  hide an improvement above ~0.06 AUC at this sample size.
* Firm identity is a much stronger predictor than disclosure content.

**Cannot answer:**
* anything about lead time - no predictive skill was established, so there is no
  lead to measure;
* whether *other* disclosure content (10-K R&D sections, 8-K Item 8.01 product
  events, earnings-call transcripts) carries signal - only this operationalisation
  was pre-registered and tested;
* whether the 1.01/2.01 label captures "meaningful technology change" - it is a
  legal form category, and ISRG's 0/48 shows how firm-specific it is;
* causal direction: agreement disclosures and R&D language plausibly share a
  common driver (pipeline maturity), which this design cannot separate;
* population inference: 11 issuers, one chronological split, 11 bootstrap
  clusters. The intervals are wide by construction and are reported as such.

## 9. Power, stated plainly

Holdout has 50 positives and 149 negatives. With Hanley-McNeil standard errors,
the minimum detectable **AUC** at 80% power is **0.64**. For the *difference*
statistic the permutation band is ~0.16 wide. A true small effect (dAUC 0.02-0.05)
would be invisible here. The study is therefore a feasibility gate, not a verdict
on the hypothesis in general: it establishes that this operationalisation, at
this n, has no detectable signal - not that EDGAR prose is uninformative in
principle.

## 10. Next experiment worth doing

Three changes, in order of expected value:

1. **Make the unit firm-time, not filing-time.** Firm-conditional hazard models
   on an issuer-month panel of 40-60 medtech issuers (EDGAR makes this cheap),
   with firm fixed effects and a firm-held-out validation split. This directly
   attacks the B1 finding.
2. **Use an outcome with date-level PIT semantics independent of EDGAR**:
   FDA 510(k)/PMA decision dates, which have their own publication dates and are
   the thing MedRadar's thesis is actually about. Then lead time is measurable,
   because the outcome is not another disclosure.
3. **Replace the lexicon input** with a structured R&D signal: XBRL
   `ResearchAndDevelopmentExpense` (already collected elsewhere in this repo),
   plus 8-K Item 8.01 product/regulatory events, instead of word rates in prose.

Until (1) and (2) exist, no lead-time claim should be made.

## 11. Reproduce

```
python research/science_001/cli.py all
python -m pytest tests/test_science_001.py -q
```

Figures: `artifacts/figures/figure1_time_evidence.png` (time evidence) and
`artifacts/figures/figure2_experiment.png` (the experiment), both regenerated from
committed artifacts by `figures.py`; their source hashes are recorded in
`artifacts/figures/figures_manifest.json`.
