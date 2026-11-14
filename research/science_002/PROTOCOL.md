# SCIENCE-002 - Frozen design and analysis plan

**Status:** frozen design. This document fixes the sample, the outcome, the
features, the model ladder, the statistics, the controls and the GO/NO-GO rule
*before* the reported run is produced and committed.

**Freeze timestamp (UTC):** 2026-11-14T10:55Z

---

## 0. Honest status of this pre-registration

This is **not** a blind pre-registration, and it must not be read as one.

The design was fixed through an exploratory pass in which the whole pipeline was
executed end to end. That pass changed one thing that matters: the primary
estimator. A first version used a *pooled* logistic regression (no firm effects)
and evaluated it with a firm-stratified AUC. That estimator produced a
within-firm AUC of 0.356 for the firm-history baseline, i.e. a value that cannot
be read as a signal and is a known artefact: a pooled fit is identified mostly by
between-firm differences, so its coefficients need not rank months correctly
*within* a firm. The estimator was therefore replaced by a ridge logistic with
**firm fixed effects**, whose slopes are identified only from within-firm
variation. That is a correction of a specification defect, disclosed here rather
than silently applied.

The exploratory pass also produced a first estimate of the primary statistic
under the corrected estimator: **delta firm-stratified AUC (B3c - B2c) = -0.034**
with a permutation p of about 0.12. The author therefore knew, when freezing this
document, that the primary result looks null.

What this freeze still buys, and why it is committed separately:

* the sample rules, the outcome definition, the feature blocks, the model ladder,
  the statistics, the controls and the decision rule are fixed **before** the
  reported run, so the reported run cannot be the product of post-hoc choice;
* the deviations log below is empty at freeze time and every later change must be
  appended to it with its reason and its effect;
* a reader can verify from git history that this file precedes the results
  artifact.

What it does **not** support: any claim that the hypothesis was tested blind, or
that the reported p-value is a confirmatory one. Throughout the write-up the
result is labelled **exploratory**, and no confirmatory claim is made.

---

## 1. Question

Can information that a medical-technology issuer had already made public in its
SEC filings predict that issuer's future FDA 510(k) clearance events, **beyond a
strong firm-history baseline**, and specifically **within the firm**?

The pooled cross-company version of the question (can we tell which firms will
have more clearances?) is explicitly *not* the research question, because
SCIENCE-001 showed it is largely answered by firm identity.

## 2. Observation unit

One **issuer-month** (firm i, month m). Prediction instant
`t = last day of m, 23:59:59 UTC`. All features must be publicly available at or
before `t`; the outcome window starts strictly after `t`.

## 3. Population and inclusion (pre-declared, outcome-blind)

Universe = SEC registrants in `company_tickers.json` satisfying **all** of:

1. **Sector.** SEC `sic` in `{3841, 3842, 3843, 3844, 3845, 3851, 3826}`. The
   registrant's own official classification is used; we never override SEC's SIC
   with our own opinion about what a company really is.
2. **Attributable FDA activity.** At least **8** cleared 510(k)s
   (`decision_code == SESE`) with `decision_date` in 2015-01-01..2026-08-31 whose
   applicant string is attributed to the registrant at tier T_A, T_A2 or T_B
   (section 4).
3. **XBRL R&D.** At least four quarterly `ResearchAndDevelopmentExpense` facts,
   and at least one 8-K carrying a verified `acceptanceDateTime`.
4. No registrant may claim an applicant string that another universe registrant
   also claims; such strings are dropped from both (section 4).

**Row-level inclusion.** A firm-month is kept only if

* `month_end + 90 days <= 2026-09-30` (FDA data maturity cut; the export used
  contains decisions to 2026-10-30, so one further month of data is deliberately
  discarded as a cushion against publication backlog), and
* the registrant's own 8-K history begins at least **400 days** before `t`, so
  trailing-365-day activity counts are complete.

**Complete-case rule.** A row enters the model comparison only if every feature of
B0..B3 is finite. B4 uses its own complete case and is reported separately.

Exclusion reasons are written for every candidate to
`artifacts/entity_exclusions.csv`; no exclusion depends on the outcome.

## 4. Cross-source identity (summary; full rules in ENTITY_RESOLUTION.md)

Attribution requires **exact equality of normalised token strings** after removing
corporate-form and state tokens. No fuzzy ratio, no edit distance, no manual
override.

* **T_A** - applicant string normalises to the registrant's current SEC title.
* **T_A2** - applicant string normalises to a former name SEC publishes in the
  registrant's own submissions record.
* **T_B** - the applicant string equals an FDA establishment-registration name
  whose FDA-published **owner/operator firm name** normalises to the registrant's
  SEC title. The registration/listing export is a **2026 snapshot**, so this is a
  present-day ownership map applied to history. The attribution is held constant
  across the whole panel, so no firm's event stream changes at an acquisition
  date; the group composition is, however, the 2026 one.
* **Ambiguous** - an applicant string claimed by two registrants is dropped from
  both and recorded.

Pre-registered sensitivities: **S1** reruns everything on T_A+T_A2 only; **S2**
reruns on the SIC set without 3826.

## 5. Outcome

`label = 1` iff the issuer has at least one **cleared** 510(k)
(`decision_code == SESE`) with `decision_date` in `(t, t + 90 days]`, else 0.
A row whose window is not fully observable is dropped, never labelled 0.

The label is a **regulatory event**, not a measure of technical merit, clinical
benefit or commercial success. Clearance is routine for large firms; that is a
property of the label, not a defect of the design, and it is quantified in
RESULTS.md.

Pre-registered secondary outcomes (reported regardless of result):

* placebo outcome: 8-K item **5.07** (submission of matters to a vote) within
  `(t, t+90d]` - a governance ritual with no technological content;
* positive control: **any** 8-K within `(t, t+90d]`.

## 6. Features (fixed before the run; all availability-stamped)

Availability rule per family:

| family | rule |
|---|---|
| 8-K activity | filing `acceptanceDateTime` (UTC second) `<= t` |
| XBRL facts | fact `filed` day `<= t` **and** fiscal period end `<= t`; first-reported value only |
| clearance history | `decision_date <= t - 30 days` |

The 30-day availability lag is a conservative stand-in for the undocumented FDA
database refresh delay. The 2026-11 export contains decisions to 2026-10-30 while
its `last_updated` is 2026-11-02, i.e. a dataset-level freshness of at most about
10 days; 30 is used so a clearance is never assumed knowable sooner than it could
have been. Pre-registered sensitivity **S3** reruns with lag 0 and lag 60.

| block | features |
|---|---|
| B1 firm history | `clr_rate_365`, `clr_rate_730`, `months_since_clear` |
| B2 activity | B1 + `n_8k_90`, `n_8k_365`, `n_801_90`, `n_801_365`, `n_202_90`, `days_since_8k`, `t_years`, `month_sin`, `month_cos` |
| B3 SEC R&D | B2 + `rd_ttm_log`, `rd_yoy`, `rd_to_sales`, `rd_growth_vol` |
| B4 extended R&D (secondary) | B3 + `rd_yoy_lag1`, `rd_yoy_lag2`, `rd_yoy_lag3`, `rd_intensity_rel` |

No feature is fitted, tuned or selected on the outcome. The B2 block is what
firm history plus ordinary disclosure activity means; B3 is the only block that
could answer the research question.

## 7. Models

Ridge-penalised logistic regression, `lambda = 1.0`, Newton/IRLS to convergence,
features standardised with **train** means and standard deviations.

Two estimators of the same ladder, used for different questions:

* **pooled** (B0..B3): no firm effects. Used for descriptive pooled AUC, for
  leave-one-firm-out generalisation, and for the positive controls.
* **firm-conditional** (B0c..B3c): the same features plus one dummy per firm. The
  slope coefficients are identified from within-firm variation only, and a firm
  dummy cannot change a within-firm ranking, so the firm-stratified AUC of these
  models measures the within-firm signal. **This is the primary family.**

B0c (intercept + dummies) has a firm-stratified AUC of exactly 0.5 by
construction and is reported as the calibration of the statistic.

## 8. Split

* **Train:** `month_end <= 2024-12-31`
* **Holdout:** `month_end >= 2025-01-01`

Chronological, never random. All firms appear in both splits; a firm-held-out
split is used as a separate generalisation check (section 10), not as the primary
split, because 40-50 firms cannot support both.

## 9. Primary statistic and test

**Statistic.** `delta = S(B3c) - S(B2c)` on the holdout, where `S(model)` is the
**firm-stratified AUC**: the unweighted mean of per-firm AUCs over firms with both
classes present. `delta > 0` means SEC R&D features rank event months above
non-event months *inside the same firm* better than the history+activity baseline.

**Null.** Within-firm random permutation of the holdout label vector (2,000
permutations, seed 20261114). This is a conditional randomisation test: under H0
each within-firm AUC has expectation 0.5, so the null distribution of `delta` is
centred at 0 and the absolute-value tail rule is a conventional two-sided test.
The one-sided positive tail is reported as well. A circular-shift variant (which
preserves serial correlation and is the scheme used in SCIENCE-001) is reported
alongside.

**Uncertainty.** Cluster bootstrap over firms, 2,000 draws, seed 20261114, for
every AUC and for `delta`.

**Multiplicity.** Exactly one primary test. Everything else is secondary or
control and is reported in full, not selectively.

## 10. Secondary and control analyses (declared in advance)

1. Pooled holdout AUC for B0..B3 with cluster CIs (descriptive only).
2. `delta` of B3c against B1c (does R&D add over firm history alone?).
3. **Leave-one-firm-out** with the pooled models: fit on the train years of the
   other firms, score the held-out firm, average per-firm AUC. Firm effects are
   not used here by design.
4. Positive control: pooled AUC of B1 (firm history) must be >= 0.60; pooled AUC of
   B2 for the *any 8-K* outcome must be >= 0.55. If either fails, the label
   machinery is broken and no other result is interpreted.
5. Placebo outcome: item 5.07 through B2c/B3c.
6. Placebo features: R&D columns shuffled within each firm across months, model
   refitted, 100 draws; the observed `delta` must lie inside that band for a
   positive result to be taken seriously.
7. Label transplant across firms on the pooled models (a cross-firm null).
8. B4 extended R&D block against B3c.
9. Sensitivities S1 (strict entity tiers), S2 (no SIC 3826), S3 (lag 0 / 60).

## 11. Power

Hanley-McNeil minimum detectable AUC at 80% power, plus the permutation-null
standard deviation converted to a minimum detectable `delta`
(`2.8 x sd_null`). Both are reported with the result.

## 12. Decision rule (fixed)

Feasibility gates - if any fails the verdict is **NO-GO**:

* holdout rows >= 300;
* holdout prevalence within [0.05, 0.95];
* firms contributing to the stratified AUC >= 20;
* pooled AUC(B1) >= 0.60;
* pooled AUC(B2) for any-8-K >= 0.55.

**GO** requires all of: `delta > 0`, permutation p < 0.05 (two-sided),
cluster-bootstrap 95% CI lower bound > 0, and leave-one-firm-out `delta` > 0.
A GO verdict would still be reported as preliminary and exploratory.

Otherwise the verdict is **NULL**: the experiment is valid and no incremental
signal beyond the pre-registered threshold was detected.

## 13. Reading rules

A NULL here means: *for this universe, this 90-day clearance indicator, these
SEC R&D features and this holdout, no within-firm incremental discrimination was
detected, and improvements larger than the upper confidence bound can be
excluded.* It does not mean that SEC filings contain no information about future
regulatory activity, and it is not evidence that FDA clearance is unpredictable.
A GO would mean an exploratory signal worth replicating on new firms and a new
period, not a validated predictor.

## 14. Deviations log

Any change after the freeze must be appended here with its reason and its effect
on every reported number. An empty log means none occurred.

_(no post-freeze deviations recorded)_
