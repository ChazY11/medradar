# SCIENCE-001 - Pre-registered protocol

**Status:** frozen before the analysis dataset was built and before any outcome
(label) distribution was observed. The only results the author had seen when this
file was written were the Phase-1 *time-semantics* results (raw timestamp strings,
timezone offsets, DST behaviour) - no forward-event labels, no prevalence, no
model output.

**Freeze timestamp (UTC):** 2026-11-13T18:40Z. The experiment writes the SHA-256
of this file into its results artifact, so any later edit to the protocol is
detectable.

**Study type:** exploratory, single chronological holdout, small issuer panel.
This protocol exists to stop post-hoc hypothesis repair. It does *not* turn the
result into a confirmatory one.

---

## 1. Question

Does a firm's public disclosure, at a moment when it is observable, carry
information about the arrival of a subsequent, *independently defined* discrete
corporate event?

This is the MedRadar long-run question ("can publicly observable evidence give
reliable early signals of meaningful change in medical technology?") reduced to
one measurable, falsifiable instance on one source (SEC EDGAR) and one event
family (technology-transaction disclosures).

## 2. Observation unit

One **original Form 8-K disclosure event** = one accession number, one issuer, one
SEC acceptance instant.

- 8-K/A amendments are *not* separate units (they amend an earlier event and
  would double count it). They are linked back to the original and reported as a
  separate descriptive result.
- A unit is kept only if its full 90-day forward window lies inside the sample
  window; otherwise it is censored and dropped (see section 7).

## 3. Population and inclusion rules

Issuers: the twelve listed medical-technology issuers registered in
`edgar.py:ISSUERS`, CIK resolved from SEC's own `company_tickers.json` and
verified against the CIK/name/SIC returned by `data.sec.gov/submissions`.

- Eleven file 8-K (US domestic or dual-registrant); one (Philips) is a foreign
  private issuer filing 20-F/6-K and is used **only** in the time-semantics
  strata, never in the panel.
- Selection criterion is a priori segment membership (large-cap medical devices,
  diagnostics, imaging, surgical robotics), not data availability. Issuers with
  short EDGAR histories are kept and their shorter coverage is reported, not
  padded.

Analysis window: SEC filing date between **2021-01-01 and 2026-09-30**
(US/Eastern calendar day).

## 4. Time model (the point-in-time guarantee)

Only one instant is used to decide what was knowable: the **verified acceptance
instant** in UTC, obtained from the raw archive header `ACCEPTANCE-DATETIME`
(US/Eastern wall clock) converted with the DST rule and cross-checked against
`data.sec.gov@ acceptanceDateTime` (see `timesemantics.py` and `TIME_SEMANTICS.md`).

Rules enforced in code:

1. Every feature of a unit is computed from that unit's own archived bytes.
2. Every label of a unit is computed from filings accepted **strictly later**
   than that unit.
3. No filing accepted after a unit's acceptance instant may influence any feature
   of that unit. Nothing is imputed backwards.
4. `filingDate` (a calendar day) is never used as an instant.
5. Acceptance is a **lower bound** on public availability; the study therefore
   never claims a tighter availability instant than acceptance gives it.

## 5. Input features (fixed lexicon, fixed formula)

From the 8-K body and its EX-99/EX-10 exhibits, after HTML stripping:

- `rd_per_1k` - rate per 1,000 words of the 25 pre-registered research/clinical
  development terms listed in `features.py:RD_TERMS`;
- `tech_per_1k` - rate per 1,000 words of the 25 pre-registered
  technology/innovation terms listed in `features.py:TECH_TERMS`;
- `is_earnings` - 1 if the filing carries SEC item 2.02;
- `n_prior_events` - count of the same issuer's 8-Ks accepted in the preceding
  90 days (activity control);
- `words`, `n_documents`, `exhibit_share` - length/shape controls, reported.

Terms were fixed before any label was computed. They are not tuned, expanded, or
pruned per outcome.

## 6. Outcome (label) - independently defined

`label_tech_event` = 1 iff, within **90 days after** the unit's acceptance
instant, the same issuer files an 8-K whose **SEC-assigned item code set**
contains item **1.01** (entry into a material definitive agreement) or **2.01**
(completion of acquisition or disposition of assets); else 0.

Non-circularity, explicitly:

- the input is *prose* from filing *i*;
- the outcome is *item metadata* from filing *j* (j not equal to i), with
  acceptance_j later than acceptance_i;
- the item codes are assigned from the cover-page checkboxes, not from any text
  classifier we run;
- therefore the same bytes cannot construct both sides.

Placebo outcome `label_placebo` = same construction with item **5.07** (submission
of matters to a vote of security holders), a seasonal governance ritual with no
technological content. It is the pre-specified negative control for the *outcome*.

Positive control `label_any_8k` = any 8-K accepted within 90 days. Activity
should predict this. If it does not, the label machinery is broken and no
negative result from this study is interpretable.

## 7. Split, censoring, and dependence

- **Train:** acceptance date up to and including **2024-12-31**.
- **Test (holdout):** acceptance date from **2025-01-01** onwards.
- The split is chronological, never random. No random scatter of temporally
  adjacent observations of one firm across splits.
- Censoring: a unit whose acceptance + 90 days exceeds the sample end
  (2026-09-30) is dropped, not labelled 0.
- Residual dependence: all firms appear in both splits. Twelve firms is too few
  for a firm-held-out split to have power, so this is stated as a limitation
  rather than fixed. Uncertainty is therefore computed with a **cluster bootstrap
  over issuers**, and the permutation scheme preserves within-firm label ordering.

## 8. Model ladder (fixed)

| id | model | predictors |
|---|---|---|
| B0 | `B0_prevalence` | none (train prevalence) |
| B1 | `B1_firm_mean` | none (per-firm train prevalence, Laplace-smoothed) |
| B2 | `B2_activity` | `n_prior_events`, `is_earnings` |
| B3 | `B3_activity_plus_dev_prose` | B2 + `rd_per_1k` + `tech_per_1k` |

Ridge-penalised logistic regression (lambda = 1.0, IRLS, 60 iterations max),
features standardised with **train** means and standard deviations only.

## 9. Primary test (one test, pre-specified direction)

Statistic: **dAUC = AUC_test(B3) - AUC_test(B2)**.

H1 direction: dAUC > 0. H0: dAUC = 0.

Null distribution: **circular shift of the label series within each issuer** in
the holdout, 2,000 permutations, seed 20261114. A circular shift keeps each
issuer's exact label multiset, its prevalence, and its serial correlation, and
destroys only the alignment between prose features and subsequent events.

p-value: two-sided (1 + #{|dAUC_perm| >= |dAUC_obs|}) / (1 + B); the one-sided
positive tail is reported alongside. Models are fitted on train only and held
fixed; only holdout labels are permuted.

Significance threshold: alpha = 0.05. No multiplicity correction is applied
because there is exactly one primary test; the two secondary analyses (placebo
outcome, positive control) are declared in advance and reported in full
regardless of outcome.

## 10. Secondary and control analyses (declared in advance)

1. Placebo outcome (item 5.07) through the identical ladder.
2. Positive control (`label_any_8k` vs activity).
3. **Label-transplant negative control**: each issuer's scores paired with the
   next issuer's label series. A primary AUC that is not materially above this
   control indicates a firm-general artefact rather than an event relation.
4. Univariate AUC per feature (descriptive).
5. Cluster-bootstrap 95% CI for every AUC and for dAUC (2,000 draws over
   issuers).
6. Power: Hanley-McNeil standard error for AUC; minimum detectable AUC at 80%
   power given the holdout's realised class counts.

## 11. Stopping rules (all decided before the run)

- If holdout n < 100, or class prevalence < 5% or > 50%, the experiment stops
  at **feasibility reporting only**: descriptive statistics and power analysis
  are published, no model comparison is claimed.
- If the positive control fails (AUC <= 0.55 for the activity baseline), the label
  construction is declared broken and no other result is interpreted.
- A null or adverse result is published as the result. The hypothesis is not
  revised and the run is not repeated with different lexicons, windows, splits,
  or thresholds.

## 12. Reading rules for the result

A positive result here means *only*: in this 12-issuer panel, in this 2021-2026
window, prose-level R&D/technology intensity preceded the 1.01/2.01 event family
more often than a chance-order null predicts. It is **not** evidence of
predictive skill, not a lead-time estimate, and not a causal claim. A null result
is a real finding about what EDGAR prose does *not* contain at this sample size.

## 13. Deviations log

Any deviation from this protocol must be appended here, with its reason and its
effect. An empty log means none occurred.

_(no deviations recorded)_
