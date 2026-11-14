# AUDIT - independent adversarial review of SCIENCE-002

**Status:** all checks pass. **Audit script:** `audit.py`; **artifact:**
`artifacts/audit_results.json` (A7 records the confirmatory-subset digest
`088afd0fad469fb606e07f83065ee987cfacefcc5ed5d7a1cb411e8f106fa17f`). **Sensitivities:**
`sensitivity.py` -> `artifacts/sensitivity_results.json`.

The audit re-implements the availability rules with different code (bisect on
sorted date lists, direct filtering over the cached SEC records) rather than
calling the panel's own functions. A mismatch is treated as a defect, never as a
rounding difference.

---

## 1. What was checked, and what each check proves

| id | check | result |
|---|---|---|
| A1 | independent re-implementation of `clr_365`, `clr_730`, `n_8k_90`, `n_801_90`, `n_202_90`, `rd_ttm_log` on 60 random rows | **0 mismatches** |
| A2 | latest availability timestamp used by any feature is `<= t` | **0 violations** in 60 rows |
| A3 | labels reproduced from the clearance index; no clearance inside the feature cut | **0 mismatches, 0 overlaps** across all 2,771 rows |
| A4 | no applicant string or FDA `k_number` attributed to two firms | **0 collisions** (148 applicant roots, 8,176 k_numbers) |
| A5 | only outcome-blind row drops; single-class firms enumerated | **2 drop reasons, both structural**; 6 single-class firms in the panel |
| A6 | inject a filing accepted **after** `t`; no feature may change | **0 changes** in 20 executed injections |
| A7 | rerun the frozen experiment with the same seed; payload must be identical | **identical**, and identical to the committed artifact |
| A8 | rerun with a different permutation seed; the verdict must not move | p = 0.096 vs 0.091, **same verdict** |

## 2. Leakage vectors, one by one

### 2.1 Future SEC information in a historical feature

The panel builder can only see filings whose `acceptanceDateTime` is at or before
the month-end instant, and XBRL facts whose `filed` day is at or before it.
Asserted in code, then **executed**: A6 appends a synthetic 8-K accepted one minute
after `t`, with both an 8.01 and a 2.02 item, and recomputes `n_8k_90`,
`n_801_90`, `n_202_90`, `n_8k_365`, `n_801_365`. Nothing moved in 20/20 cases.
A2 independently confirms that the *latest* timestamp any feature could have read
is at or before `t`.

**Residual risk.** Day-granularity XBRL: a fact filed on the last day of the month
is treated as known at that day's end. That is a <= 24 h generosity, uniform across
firms and months, and it cannot manufacture a *within-firm* ordering by itself.

### 2.2 The outcome leaking into the features

The historical clearance counts use `decision_date <= t - 30 days`; the outcome
window is `(t, t + 90 days]`. The windows are disjoint by 31 days. A3 recomputes
every label from the raw clearance index and checks the minimum window date against
the feature cut: **0 overlaps in 2,771 rows**.

**Why the reverse leak is impossible.** A firm announces a clearance only after FDA
decides, so an 8-K accepted at or before `t` cannot describe a clearance whose
`decision_date` is after `t`. The audit does not rely on that argument alone: A3
checks the data, and the positive control (activity predicts any 8-K at AUC 0.63)
shows the activity series is live rather than degenerate.

### 2.3 Firm-history baseline estimated on the whole window

`clr_rate_365`, `clr_rate_730` and `months_since_clear` are computed per row from a
date cutoff strictly before `t`, never from a firm-level mean over the panel. A1
recomputes them independently with `bisect` and finds 0/60 mismatches.

### 2.4 Duplicate or double-counted subsidiaries

Two failure modes were possible: the same FDA clearance credited to two firms, and
the same group appearing twice. A4 verifies both directions on the actual data:
**0 shared applicant roots, 0 shared k_numbers**, across 148 roots and 8,176
clearances. The ambiguity rule (an applicant claimed by two registrants is dropped
from both) is also pinned by a synthetic collision in the test suite.

### 2.5 Entity attribution errors

See ENTITY_RESOLUTION.md. The audit adds two mechanical confirmations: every
accepted link carries its literal evidence string, and the owner/operator relation
is re-read from the FDA file rather than trusted from a derived table. The
`GE MEDICAL SYSTEMS -> GE HealthCare Technologies` link and the **absence** of
`STRYKER SPINE -> Stryker` (FDA lists it under VB Spine) are the two cases that
show the rule following the source rather than the brand.

### 2.6 Hidden sample selection

A5 enumerates every drop: 397 firm-months dropped for insufficient SEC coverage,
78 for incomplete R&D features, and the maturity cut. None of the three references
the label. 6 of 48 firms are single-class in the panel; they are kept for fitting
and excluded from the stratified statistic, and the statistic always reports its
firm count (31).

### 2.7 Do the statistical claims match their nulls?

* The primary null is a **within-firm** permutation. Under H0 each within-firm AUC
  has expectation 0.5, so the null distribution must be centred at 0. It is:
  null mean **0.000**, 95% band **[-0.040, +0.038]** over 2,000 permutations. This
  is a genuine centred two-sided test, unlike the absolute-from-zero rule in
  SCIENCE-001, which was reported there as off-centre and is not repeated here.
* The circular-shift variant, which preserves serial correlation, gives a wider
  band ([-0.048, +0.051]) and a larger p (0.200).
* A8 shows the p-value is seed-stable (0.096 vs 0.091) and the verdict does not
  move.
* Bootstrap is clustered on firms, and the statistic inside each draw is recomputed
  from that draw's firms only (not read from a fixed per-firm table).

### 2.8 Can the figures be reproduced from the artifacts?

`figures.py` reads only `experiment_results.json`, `panel.csv` and `universe.csv`
and writes `figures_manifest.json` with the SHA-256 of its three inputs and of every
PNG. No figure recomputes a model. A7 confirms that
`experiment_results.json` is byte-reproducible from the frozen code and cache.

## 3. Defects the audit actually found (and what happened to them)

Honesty about the process matters more than a clean table, so:

1. **The primary estimator was wrong in the first design.** A pooled logistic
   regression evaluated with a within-firm AUC produced 0.356 for the firm-history
   baseline - below chance, which is an artefact of identifying coefficients from
   between-firm variation. Fixed **before the freeze** by adding firm fixed effects;
   disclosed in PROTOCOL.md section 0, not buried.
2. **The pooled confidence intervals were computed with the wrong statistic**
   (stratified instead of pooled AUC), which made figure 2's left panel show
   0.29-0.42 error bars around a 0.83 point estimate. Caught in review **before**
   the figures were committed; the bootstrap now computes pooled AUC for pooled
   models. The committed artifact is the corrected one.
3. **The audit's own independent re-implementation was off by up to one day** in
   its 90-day activity window, because it used integer day arithmetic
   (`(t - stamp).days <= 90`) instead of an exact timestamp comparison. It
   disagreed with the panel on 5 of 60 rows. On inspection the *panel* was correct
   and the *auditor* was wrong; the auditor was fixed to use exact `timedelta`
   comparisons, and A1 now reports 0 mismatches. This is the audit working as
   intended: it surfaced a discrepancy and the discrepancy was resolved against
   evidence, not against whichever side was easier to change.

No defect was found in the label construction, the attribution uniqueness, or the
point-in-time ordering.

## 4. Pre-registered sensitivities

Each scenario rebuilds the universe and the panel from the same cached bytes and
recomputes the primary statistic (1,000 permutations / 1,000 bootstrap draws; the
primary test keeps 2,000 of each).

| scenario | firms | complete cases | delta (B3c - B2c) | permutation p | 95% CI | pooled AUC(B1) | LOFO delta | verdict |
|---|---|---|---|---|---|---|---|---|
| base | 48 | 2,554 | **-0.034** | 0.100 | [-0.084, +0.018] | 0.829 | -0.002 | NULL |
| S1 strict attribution (T_A + T_A2 only) | 45 | 2,414 | **-0.043** | 0.047 | [-0.089, +0.008] | 0.787 | -0.012 | NULL |
| S2 no SIC 3826 | 47 | 2,488 | **-0.027** | 0.210 | [-0.070, +0.021] | 0.821 | -0.004 | NULL |
| S3a availability lag 0 days | 48 | 2,554 | **-0.020** | 0.292 | [-0.068, +0.033] | 0.828 | +0.019 | NULL |
| S3b availability lag 60 days | 48 | 2,554 | **-0.028** | 0.157 | [-0.074, +0.022] | 0.828 | +0.004 | NULL |

Two things to read carefully:

* **S1 does not rescue the design, and it is not a positive result.** Removing the
  2026 ownership map leaves 45 firms and moves the delta to -0.043 with p = 0.047.
  That is a nominally significant **negative** association, not a positive one. A
  negative association between R&D growth and the next quarter's clearance months
  is not something this study claims as a finding: it was not pre-registered as a
  directional hypothesis, it is not robust across the base and S2/S3 specifications,
  and it is the same pattern the R&D-timing placebo flagged (RESULTS.md section 7).
  Reporting it as a discovery would be exactly the post-hoc reframing the protocol
  exists to prevent.
* The direction of every point estimate is non-positive (range -0.043 to -0.020),
  the LOFO delta is between -0.012 and +0.019, and no scenario reaches the GO rule.
  The conclusion is insensitive to the two attribution and lag assumptions that the
  design most depends on.

## 5. Residual risks the audit cannot remove

1. **8.8% attribution coverage.** Only 3,143 of 35,680 cleared 510(k)s in the
   window belong to the 48 firms. No audit step can create data that exact-name
   matching does not reach; NEXT_STEPS.md item 1 is the fix.
2. **2026 ownership snapshot.** Tier-B attribution is a present-day grouping
   applied to history. S1 bounds its influence (-0.043 vs -0.034); it does not
   eliminate it.
3. **Label saturation.** 7 holdout firms at 1.00 and 8 at 0.00; the effective
   within-firm sample is 31 firms. The effective sample size for the primary test
   is 31, not 782.
4. **One chronological split.** 2025-01..2026-06. A different period could behave
   differently, and this design cannot tell.
5. **One outcome definition.** Other clearance-based outcomes (novel product
   codes, count models) would test the same question with different power; they
   were not pre-registered here and are listed in NEXT_STEPS.md.
6. **The freeze is not blind.** PROTOCOL.md section 0 states what was already known
   when the design was frozen. The audit cannot restore blindness; it can only
   confirm that no threshold, feature, outcome or decision rule moved afterwards.
   It did not: git history shows `PROTOCOL.md` (f5dad80) precedes the results
   commit, and the deviations log is empty.

## 6. Audit verdict

**PASS, with the residual risks in section 5.** The experiment is valid, its
positive controls work, its null is properly centred and seed-stable, its numbers
are reproducible from committed artifacts, and none of the checks found a leak,
a double count, or a selection effect. The verdict **NULL** stands.