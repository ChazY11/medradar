# EVALSTATS — cluster-aware evaluation statistics (cycle 2)

Status: implemented in [`medradar/intelligence/evalstats.py`](../../medradar/intelligence/evalstats.py),
tested offline in [`tests/test_evalstats.py`](../../tests/test_evalstats.py) (37 tests).
Pure standard library; no third-party import, no I/O, no network, no database.
Every random draw is behind an explicit seed, so a reported interval is
reproducible to the last digit.

This module exists because the cycle-1/2 benchmark's inference was too thin:

* The frozen panels are **not i.i.d.** Rows repeat 51 companies and ~1,900
  company x track pairs over quarterly origins. A row bootstrap answers a
  different (easier) question.
* A CI that includes zero is not "no effect". With ~26 positives per holdout
  window the design cannot resolve the AP differences the mission cares about;
  the minimum detectable effect has to be reported next to the interval.
* The mission requires **mean lead time at a matched false-alarm rate**, which
  the previous evaluation code did not implement at all, and it must not
  silently drop positives that are never detected inside the follow-up window.

## 1. API surface

All functions return plain `dict`/`list`/`float`/`None` (JSON-ready). The
canonical metric definitions stay in
[`evaluation/metrics.py`](../../medradar/intelligence/evaluation/metrics.py);
`evalstats.average_precision` **is** `metrics.pr_auc` (an alias, not a copy).

| Function | Role |
|---|---|
| `average_precision(labels, probabilities)` | alias of `metrics.pr_auc` |
| `average_precision_weighted(labels, probabilities, weights)` | tie-aware AP on an integer-weighted row multiset; proven equal to `pr_auc` on materialised duplicates (test) |
| `clustered_bootstrap_delta_ap(labels, p_a, p_b, clusters=None, *, resamples=2000, seed=7, confidence=0.95)` | percentile cluster-bootstrap CI for `AP(a) − AP(b)` |
| `clustered_bootstrap_metric_ci(labels, p, clusters=None, *, metric="brier"\|"ece", resamples=2000, seed=7, confidence=0.95)` | cluster-bootstrap CI for Brier / ECE |
| `clustered_bootstrap_brier_ci(...)`, `clustered_bootstrap_ece_ci(...)` | thin wrappers |
| `mde_from_se(se_delta_ap, *, alpha=0.05, power=0.8)` | **preferred** MDE from an observed bootstrap SE |
| `power_at_delta(delta, se_delta_ap, *, alpha=0.05)` | two-sided normal-approximation power |
| `average_precision_mde(n_rows, n_positives, *, alpha=0.05, power=0.8, assumed_ap=None, scorer_correlation=0.0, resamples=1000, seed=7)` | design-stage MDE (analytic; conservative default) |
| `ap_mde_calibration(n_rows, n_positives, *, assumed_ap=None, ..., seed=7)` | synthetic known-effect calibration check |
| `matched_far_lead_time(units, *, scores=("score_a","score_b"), label_key="label", event_date_key="event_date", origin_date_key="origin_date", censor_date_key="censor_date", unit_id_key="unit_id", far=0.10, curve_fars=...)` | matched-FAR mean lead time + POD curve for two scorers |
| `cluster_bootstrap_delta_ap(labels, p_a, p_b, clusters, *, resamples=2000, seed=7, confidence=0.95)` | stable cycle-2 integration name; returns `delta`, `ci_low`, `ci_high`, `valid_resamples`, `n_clusters`, `n_positives`, `p_delta_le_zero` |
| `minimum_detectable_delta_ap(n_rows, n_positives, *, alpha=0.05, power=0.8, assumed_ap=None, scorer_correlation=0.0, resamples=1000, seed=7)` | stable cycle-2 integration name; returns `mde` + `method` |
| `lead_time_at_matched_false_alarm(scores_a, scores_b, labels, lead_days, *, k=None, far=0.10)` | stable cycle-2 integration name; parallel-array variant that matches the selection size `k` |
| `bootstrap_ci_metric(metric_fn, labels, probabilities, *, resamples=2000, seed=7)` | i.i.d. row-bootstrap CI for an arbitrary metric callable (Brier/ECE) |

## 2. Average precision — one definition

`pr_auc` is the canonical implementation. It ranks by score descending, treats
equal scores as **one** threshold, and accumulates

```
AP = Σ_blocks (Δrecall_block) × (precision at block end)
   = Σ_blocks (tp_block / n_pos) × (tp_cum / (tp_cum + fp_cum))
```

The bootstrap must evaluate that same statistic on a resampled row multiset.
`average_precision_weighted` does exactly that with integer multiplicities, and
a test asserts it equals `pr_auc` after physically duplicating rows (including
tied scores). It returns `None` when the weighted sample has a single label
class, matching `pr_auc`'s convention. Point estimates in every CI function are
computed with `pr_auc`, never with a second inlined formula.

## 3. Clustered bootstrap of `AP(a) − AP(b)`

Algorithm (Cameron–Gelbach–Miller cluster bootstrap):

1. rows are grouped into `G` clusters (company, or `(company_key, track_id)`);
2. draw `G` clusters with replacement, uniformly;
3. concatenate every row of the drawn clusters — a cluster drawn twice
   contributes its rows twice; the pairing is preserved because both scorers
   score the identical resampled rows;
4. compute `AP(a) − AP(b)` on the resample; repeat `resamples` times;
5. report the percentile interval at `[α/2, 1−α/2]`.

Conventions:

* Percentile indices use the repo's existing `int(q × size)` convention, the
  same as `metrics.paired_bootstrap_delta_ap` and `util.bootstrap_ci`, so the
  three are comparable without re-explaining endpoints.
* Invalid resamples (single label class, hence undefined AP) are **skipped and
  counted** in `skipped_resamples`; they never silently change the denominator.
* Validity is asymptotic in the number of **clusters**. One cluster, or no valid
  resample, returns `ci_low = ci_high = None` with a reason, not a fake
  zero-width interval.
* `clusters=None` is the i.i.d. row bootstrap and the payload says
  `cluster_method = "iid_row"`; it is not cluster-robust.
* Cluster ids are canonicalised by `(type, repr)`, so strings, ints and tuples
  work and the result does not depend on row ordering.
* `confidence` and `alpha` are two-sided.

Deterministic: same input + `seed` ⇒ byte-identical payload. Not a Bayesian
posterior and not bias-corrected; no studentisation.

Cost is `O(resamples × n_rows)` per metric pass. Measured on this machine
(synthetic panels with 51 company clusters, 2,000 resamples, seed 7, for
`clustered_bootstrap_delta_ap`):

| Rows | Time |
|---:|---:|
| 1,722 (P1 window size) | 0.72 s |
| 6,735 (P2 window size) | 2.77 s |
| 41,003 (P1 panel) | 19.8 s |
| 161,636 (P2 panel) | 99.8 s |

Plan for tens of seconds on the full P2 panel; the per-window analysis is
sub-second to a few seconds. (Times are wall-clock on the development machine
and will differ elsewhere.)

## 4. MDE / power

### 4.1 Preferred path: observed bootstrap SE

`mde_from_se(se_delta_ap, alpha, power)` reports

```
MDE = (z_{1−α/2} + z_power) × SE(AP(a) − AP(b))
```

with the SE taken from `clustered_bootstrap_delta_ap(...)["se_delta"]` on the
actual holdout. This is the honest route: it includes the real score
distribution's variance, the cluster design effect and the score correlation.
The assumption is only that the delta-AP bootstrap distribution is roughly
normal and symmetric; inspect the percentile interval as well.

### 4.2 Design-stage path (counts only)

`average_precision_mde(n_rows, n_positives, ...)` uses the plug-in
approximation

```
Var(AP)          ≈ m (1 − m) / n_positives
Var(AP_a − AP_b) ≈ 2 (1 − ρ) Var(AP)
SE               = sqrt(Var(delta))
MDE              = (z_{1−α/2} + z_power) × SE
```

`m` is the assumed AP level (`assumed_ap`) and `ρ` the score correlation. The
defaults are deliberately conservative: `m = 0.5` (which maximises `m(1−m)`) and
`ρ = 0`, so the headline `mde` is an **upper bound** on the smallest detectable
difference. This matters: an AP difference computed from near-random scorers is
much less variable than one from real, heterogeneous scorers. A no-skill
simulation (reported as `mde_delta_ap_null_simulation`, using an exact rank-space
Monte Carlo) is therefore a **lower bound and must not be used as the planned
MDE** — it would overstate power dramatically. In the P1 panel it gives 0.0027
while the conservative design bound is 0.0883.

The design bound is monotone decreasing in `n_positives` at fixed `assumed_ap`
(proportional to `1/√n_positives`), independent of `n_rows`. Note that replacing
negatives with positives at fixed `n_rows` raises the base rate and is *not*
covered by that monotonicity statement.

Measured design values (`minimum_detectable_delta_ap`, `assumed_ap = 0.5`,
`ρ = 0`, `resamples = 1000`, seed 7):

| Panel scale | rows | positives | base rate | SE(ΔAP) | **MDE** | no-skill lower bound |
|---|---:|---:|---:|---:|---:|---:|
| P1 holdout window | 1,716 | 26 | 0.01515 | 0.13868 | **0.38851** | 0.02859 |
| P2 holdout window (approx) | 6,735 | 45 | 0.00668 | 0.10541 | **0.29531** | 0.01042 |
| P1 panel | 41,003 | 503 | 0.01227 | 0.03153 | **0.08833** | 0.00265 |
| P2 panel | 161,636 | 1,082 | 0.00669 | 0.02150 | **0.06022** | 0.00093 |

Reading example: on a single P1 holdout window, an AP difference below roughly
**0.39** cannot be detected at 80% power with 26 positives; a delta of 0.05 with
a CI spanning zero is an underpowered null, not evidence of no effect. On the
pooled P1 panel the conservative bound is ~0.088; pooled P2 ~0.060.

### 4.3 Synthetic known-effect calibration

`ap_mde_calibration(n_rows, n_positives, ...)` runs two checks on synthetic data:

1. the cheap rank-space null simulation vs a full Gaussian Monte-Carlo SD
   (`null_se_ratio` should be near 1);
2. a **known effect**: `score_a = skill × label + noise`, `score_b = noise`,
   with `skill` calibrated so the population ΔAP equals the reported MDE. The
   function then measures the achieved power of the paired bootstrap over
   replicates and compares it with the normal-approximation prediction.

Measured (seed 7, `null_reps = 300`, `null_trials = 1000`):

| Calibration scale | design MDE | null SE ratio | measured effect ΔAP | median bootstrap SE | empirical MDE | achieved power | predicted power | consistent |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| P1 window (1,716 / 26, 80 reps, 60 boot) | 0.38851 | 0.888 | 0.37584 | 0.09110 | 0.25522 | 1.00 | 0.98483 | yes |
| synthetic (240 / 20, 80 reps, 100 boot) | 0.44297 | 0.975 | 0.44761 | 0.10107 | 0.28316 | 1.00 | 0.99322 | yes |

Interpretation, stated honestly: the conservative design MDE is detectable at
**at least** the nominal power on synthetic known-effect data (achieved power
1.00 > 0.8), and the normal-approximation MDE conversion is consistent with the
bootstrap (achieved vs predicted differs by < 0.02). The empirical MDE from the
bootstrap SE is *smaller* than the worst-case design bound (ratio 0.64–0.66) on
these synthetic DGPs, which is exactly why the observed-SE route is preferred
when real data are available.

## 5. Mean lead time at a matched false-alarm rate

`matched_far_lead_time(units, ..., far=0.10)` accepts one mapping per candidate
unit with:

* `score_a`, `score_b` — the two scorers' scores;
* `label` — 1 if the target event is a true positive, 0 otherwise;
* `origin_date` — the scoring date lead time is measured from;
* `event_date` — the observed target date for positives (`None` = never observed);
* optional `censor_date` — end of follow-up;
* optional `unit_id` — deterministic tie-break.

Matching rule (explicit and symmetric): let `m = floor(far × n_negatives)`.
Both scorers are given exactly `m` false alarms: the `m` highest-scoring
negative units are selected as the ensured false positives, and a positive is
**detected iff its score is strictly greater than the score of the `m`-th
highest negative**. Negative ties at the threshold are broken by unit id so the
count is exact. Therefore the empirical false-alarm rate `m / n_negatives` is
identical for both scorers by construction; the selection sizes differ, and that
is the point (a better scorer detects more true positives at the same false-alarm
budget). For `m = 0` the threshold is the highest negative score and no negative
is selected.

Censoring (reported, never dropped):

* a selected positive contributes to `mean_lead_time_days` only if `event_date`
  exists and is not after `censor_date`;
* selected positives that are censored go to `censored_detected_positives`; the
  mean is explicitly conditional on an observed lead, and `observed_leads` is
  reported next to it;
* positives with an event *before* the origin are counted in
  `negative_lead_positives` and excluded from the mean (look-ahead/label error),
  not used as a negative lead;
* missed positives are `undetected_positives`; the data-level ceiling is
  `positives_without_observable_lead` and `max_detection_probability`, so a
  detection probability is never read as 100% when the follow-up cannot see
  every event.

The `pod_curve` field repeats the whole computation for every requested FAR
(`curve_fars`), giving the probability-of-detection curve for both scorers; it is
monotone non-decreasing in FAR by construction of the threshold rule.

`lead_time_at_matched_false_alarm(...)` is the parallel-array integration
variant used by the cycle-2 analyzer: it matches the **selection size** `k`
(default: `k` read off scorer A at `far`) instead of the false-positive count, so
the two empirical FARs can differ (both are reported). It counts selected
positives whose `lead_days is None` as `n_censored` and reports the difference.

## 6. Brier / ECE intervals

`clustered_bootstrap_brier_ci` and `clustered_bootstrap_ece_ci` reuse the same
cluster resampler. The point value is the canonical `metrics.brier` /
`metrics.ece` (10 equal-width bins); resampled values use the identical formula
on the row multiset. Degenerate behaviour matches the AP bootstrap (fewer than
two clusters ⇒ no interval). `bootstrap_ci_metric(metric_fn, ...)` is the i.i.d.
row-bootstrap fallback for arbitrary callables; it is not cluster-robust and is
labelled `cluster_method = "iid_row"`.

## 7. Exact vs approximate

| Item | Status |
|---|---|
| AP point estimate | exact for the frozen data (canonical `pr_auc`) |
| Weighted AP on a resample | exact re-expression, asserted equal to `pr_auc` on duplicates |
| Brier/ECE point estimates | exact (canonical functions) |
| Cluster-bootstrap interval | exact resampling algorithm; validity **asymptotic in the number of clusters**; percentile interval, not bias-corrected |
| MDE from observed SE | normal approximation, symmetric-delta assumption |
| Design-stage MDE | plug-in `m(1−m)/n_pos` approximation; conservative at `m = 0.5`; **not** the observed-SE MDE |
| No-skill simulated MDE | exact within a label-independent Gaussian-copula/rank model; **optimistic lower bound**, not a planning value |
| Calibration check | synthetic only; one effect geometry (`skill × label + noise`) |
| Lead-time matching | exact integer false-positive matching; mean lead conditional on observed leads (censoring reported) |

## 8. Limitations and things a reader must know

1. **52 clusters is not many.** The company-cluster interval is asymptotic in the
   number of clusters (51 companies). The pair-cluster version (hundreds to ~1,900
   clusters) is the better-identified interval when most pairs appear more than
   once; both are reported.
2. **Percentile intervals are not bias-corrected** and can be asymmetric. Do not
   invert them into a p-value; use `p_delta_le_zero` only as a descriptive
   bootstrap tail share.
3. **The design-stage MDE is conservative on purpose.** It is an upper bound
   assuming worst-case AP variance and independent scores. The observed-SE MDE
   (`mde_from_se`) is the number to cite when data exist. If both are reported,
   say which is which.
4. **A null inside a wide interval is not evidence of no effect.** With 26
   positives the P1 window bound is ~0.39 in ΔAP; the honest label is
   "underpowered null".
5. **Lead-time means are conditional on detection.** Censored positives are
   counted and reported; they are not imputed. Do not compare a mean lead that
   dropped censoring with one that kept it.
6. **Matched FAR changes which units are selected.** The metric is not "each
   scorer at its own best threshold"; the false-alarm count is held fixed and
   the detection set is scorer-dependent.
7. **No causal claim.** These are sampling-variability statements about a metric
   on the observed data; the target definition, unversioned track taxonomy and
   left-censoring of pre-2016 activity are unchanged by this module.

## 9. How to run

```powershell
cd <REDACTED_LOCAL_PATH>
$env:PYTHONIOENCODING="utf-8"
python -m pytest tests/test_evalstats.py -o addopts="" -q
# 37 passed in 0.71s
```

Minimal use on a holdout window (rows with `label`, model/baseline scores and
company / pair cluster ids):

```python
from medradar.intelligence import evalstats

ci = evalstats.clustered_bootstrap_delta_ap(
    labels, model_scores, baseline_scores, company_keys, resamples=2000, seed=7)
mde = evalstats.mde_from_se(ci["se_delta"])          # observed-SE MDE (preferred)
design = evalstats.average_precision_mde(len(labels), sum(labels), assumed_ap=0.11)
lead = evalstats.matched_far_lead_time(units, far=0.10)   # matched-FAR lead time
```

## 10. Cycle-2 wiring

`experiments/cycle2_coverage/analyze_cycle2.py` imports this module optionally and
uses: `clustered_bootstrap_delta_ap` (entity and pair clusters, `se_delta`),
`mde_from_se`, `average_precision_mde`, `matched_far_lead_time`. The stable
integration names are exported at module top level so the analyzer needs no
changes:

* `cluster_bootstrap_delta_ap(labels, p_a, p_b, clusters, *, resamples=2000, seed=7, confidence=0.95)`
  → at least `delta`, `ci_low`, `ci_high`, `valid_resamples`, `n_clusters`,
  `n_positives`, `p_delta_le_zero`; `se_delta` is also present.
* `minimum_detectable_delta_ap(n_rows, n_positives, *, alpha=0.05, power=0.8, resamples=1000, seed=7)`
  → `mde`, `method`, plus the conservative/optimistic split.
* `lead_time_at_matched_false_alarm(scores_a, scores_b, labels, lead_days, *, k=None)`
  → per-scorer `mean_lead_days`, `n_detected`, `n_censored`, `far`, and the
  difference.
* `bootstrap_ci_metric(metric_fn, labels, probabilities, *, resamples=2000, seed=7)`.

The figures in this document are synthetic benchmarks/calibrations produced by
the commands above; they are not the cycle-2 panel results and no real panel
number is claimed here.
