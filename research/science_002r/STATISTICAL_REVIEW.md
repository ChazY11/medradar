# STATISTICAL_REVIEW - AUC, permutation, bootstrap, interval and power

Everything in this file was recomputed from the committed artifacts
(`artifacts/stats_review.json`) plus a re-derivation from first principles. The
frozen experiment code was imported, never edited.

---

## 1. Firm-stratified AUC

**Implementation check.** `experiment.stratified_auc` groups the holdout rows by
firm, computes the Mann-Whitney AUC inside each group with tie handling, keeps only
groups that contain both classes, and averages the per-firm values **unweighted**.
Verified by direct recomputation from `panel.csv` + `experiment_results.json`:

| quantity | committed | recomputed by the audit |
|---|---|---|
| stratified B2c | 0.4864 | 0.4864 |
| stratified B3c | 0.4527 | 0.4527 |
| delta B3c - B2c | -0.0337 | -0.0337 |
| firms contributing | 31 | 31 |
| firms where B3c > B2c | 12 | 12 |
| per-firm delta median | 0.000 | 0.000 |

**Equal weighting.** Confirmed: the statistic is `mean(per-firm AUC)`, not
`weighted by rows`. This matters because firms differ in size; a row-weighted
version would mostly measure the largest firms. The code does what the protocol
says.

**Single-class firms.** 13 of the 44 complete-case holdout firms have one class and
are excluded from the statistic, which reports its firm count (31) and is
accompanied by the CI. The excluded firms are listed in
`artifacts/internal_consistency.json`.

**Same sample for both models.** B2c and B3c are fitted on the same 1,772 train rows
and scored on the same 782 holdout rows; the complete-case mask is computed from the
union of B0..B3 features once, before fitting. Confirmed by reading
`experiment.run`: `rows = panel_result.complete_case(("B0","B1","B2","B3"))`.

**Firm fixed effects.** `RidgeLogit(firm_effects=True)` adds one dummy per firm
(dropping the first) to the design matrix; since a dummy is constant inside a firm,
it cannot change a within-firm ranking, so the stratified AUC of B2c/B3c is
identified from within-firm variation in the features only. This is the design's
strongest single property and it is implemented correctly. `B0c` (intercept +
dummies, no features) has stratified AUC exactly 0.5 by construction, and the
experiment reports it as the calibration of the statistic.

**Cross-firm model.** Leave-one-firm-out refits the *pooled* (no firm effects) model
on the other firms' training rows and scores the held-out firm. It never uses the
held-out firm's identity in fitting. Verified in `experiment.run`.

## 2. Permutation test

**Null is the right one.** The question is "inside a firm, does the model rank event
months above non-event months better than chance". Under H0 the labels are
exchangeable within a firm conditional on the firm, so a within-firm shuffle targets
exactly the null being tested. The statistic under H0 has expectation 0.5 per firm,
so the null is centred on 0 - and empirically it is: null mean **0.000**, 95% band
**[-0.040, +0.038]** over 2,000 permutations. This is a proper conditional
randomisation test, unlike the absolute-from-zero rule that SCIENCE-001 had to
correct.

**Two-sided p.** ` (1 + #{|T*| >= |T_obs|}) / (1 + B)` is the standard two-sided
randomisation p with the plus-one correction for a finite permutation sample. On
2,000 draws its resolution is 0.0005; the reported 0.094 is stable across seeds
(0.096 vs 0.091 in the frozen audit's A8, both computed at 2,000 draws).

**The overlap problem - and what it does to this test.** Adjacent issuer-months have
90-day outcome windows that overlap by two thirds, so rows are not independent and a
shuffle destroys the serial structure the data actually has. Measured within-firm
label autocorrelation:

| lag (months) | window overlap | correlation (holdout) |
|---|---|---|
| 1 | 66% | **0.717** |
| 2 | 32% | **0.526** |
| 3 | 0% | **0.370** |

Lag 3 has no window overlap and still correlates 0.37, which is firm-level rate
persistence (a busy firm stays busy). The design effect is therefore substantial:
782 holdout rows are not 782 independent observations; a conservative reading is
that they carry the information of roughly a third of that number.

Three permutation schemes were run (all at 2,000 draws):

| scheme | delta | p | null sd |
|---|---|---|---|
| within-firm shuffle (committed) | -0.034 | **0.094** | 0.0197 |
| circular shift (committed) | -0.034 | 0.20 | 0.026 |
| **3-month block shift (audit)** | -0.034 | **0.223** | 0.0267 |

Block shifting preserves the joint clustering of the label within a quarter and is
the scheme closest to the dependence structure. It gives a *larger* p. So the small
estimated effect is not an artefact of the shuffle; if anything the shuffle is
mildly anti-conservative, exactly as suspected, and correcting it moves the result
further into the null.

**Stronger test of the same worry.** Rebuilding the panel with non-overlapping
quarterly observations (every third month, 90-day windows no longer overlap) and
re-running the identical model ladder:

| quantity | monthly (committed) | quarterly (audit) |
|---|---|---|
| holdout rows | 782 | 260 |
| firms in stratified AUC | 31 | 29 |
| stratified B2c | 0.486 | 0.388 |
| stratified B3c | 0.453 | 0.400 |
| delta | -0.034 | **+0.012** |
| permutation p | 0.094 | **0.789** |

The sign flips and the p-value is 0.79. This is the correct way to read the
monthly estimate: it is not a robust negative association, it is noise whose sign
depends on the dependence structure. The audit therefore rejects any reading of
-0.034 as evidence that R&D *hurts* prediction, and keeps only the null.

## 3. Cluster bootstrap

**Implementation.** Firms are resampled with replacement (`draws = 2000`, each draw
picks 44 firms from 44 with replacement, duplicates kept), and the statistic is
recomputed *from that draw's rows only* - in particular the stratified AUC is
recomputed inside the draw, not read from a fixed per-firm table. Duplicated firms
are relabelled `firm#j` so they enter as independent clusters. Verified in
`experiment.run`.

**Is 31 clusters enough?** Marginal. The percentile interval assumes the bootstrap
distribution approximates the sampling distribution, which needs more clusters than
31 for a statistic as non-smooth as an AUC. The audit therefore ran an independent
**leave-one-firm-out jackknife**:

| method | point | SE | 95% interval |
|---|---|---|---|
| cluster bootstrap (committed) | -0.0337 | - | **[-0.083, +0.017]** |
| jackknife over firms (audit) | -0.0337 | **0.0337** | **[-0.100, +0.032]** |
| leave-one-firm-out range | - | - | [-0.046, -0.010] |

The jackknife interval is **40% wider at the upper end**. Removing any single firm
never flips the sign (all leave-one-out values are between -0.046 and -0.010), which
is a genuine robustness statement: no one firm drives the estimate. But the
bootstrap's +0.017 upper bound is optimistic relative to the jackknife's +0.032, and
the write-up used the tighter number to claim exclusion.

## 4. Interval and power: what may and may not be said

**What the interval supports.** With a point estimate of -0.034 and intervals
[-0.083, +0.017] (bootstrap) / [-0.100, +0.032] (jackknife), the data are compatible
with a zero effect. A positive within-firm effect of about +0.03 is *disfavoured* by
the bootstrap but *not excluded* by the jackknife.

**What it does not support.** The sentence in RESULTS.md that improvements larger
than +0.017 "can be excluded at 95%" over-reads a two-sided percentile interval
from 31 clusters, and it contradicts the audit's independent interval. Corrected in
ERRATA.md (E2).

**MDE.** The Hanley-McNeil figure (0.642 minimum detectable AUC) and the
`2.8 x sd_null` figure (0.055 minimum detectable delta) are *design properties*: what
an 80%-power test would have caught. They are not bounds on the true effect, and a
non-significant result does not mean the effect lies above or below them. The
protocol uses them correctly; RESULTS.md section 9 is where the wording drifts.

**Power with dependence.** Both MDE figures assume independent observations. Given
the measured autocorrelation, the true MDE is *larger* than 0.055 - the study is
less powerful than its stated figure. This is another reason the audit's verdict
stays at NULL rather than 'no effect exists'.

## 5. Multiplicity

One primary test was pre-registered and one is reported as primary. The audit
checked that no secondary analysis is presented as confirmatory: the sensitivity
table in RESULTS.md labels every row NULL and AUDIT.md calls S1's p = 0.047 a
*negative* association that was not a pre-registered directional hypothesis. That
is the correct treatment. The one place the text needs tightening is the
placebo-feature p = 0.0495, which is reported but should not be read as a second
test - the audit recommends wording it as 'a 5-in-100 tail at 100 draws, not
interpreted'.

## 6. Reproduce

```
$env:MEDRADAR_S2_CACHE = "<path to science_002 data/cache>"
python -m research.science_002r.run stats       # writes artifacts/stats_review.json
```