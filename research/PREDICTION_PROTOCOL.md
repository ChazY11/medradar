# Prediction protocol (pre-registered)

This is the frozen evaluation contract. It is written *before* cycle-2 modelling and
may only change by a recorded decision that invalidates prior results.

## 1. Targets

### T-cont (continuation)
At quarterly quarter-start cutoff `τ`, for a `(company, track)` pair: label = 1 iff a
**material event** exists for that pair in `(τ, τ + 12 months]`.

### T-entry (first entry / dormant → active)
At `τ`, candidate pairs are `(company, track)` where the company has ≥1 material
event with `event_date <= τ`, `track_id` is non-null, and the pair has **zero**
material events in `(τ − 36 months, τ]`. Label = 1 iff a material event exists for
the pair in `(τ, τ + 12 months]`.

### Material event definition (identical for both targets)
- any `510(k)` row **linked to a company**, plus
- `PMA` rows whose `supplement_number` is empty / `0` / `S0`, or whose
  `supplement_type` contains `PANEL TRACK`.

A regulatory milestone is a **lagging proxy** for R&D activity. It is not internal
R&D start, not product launch, and not evidence that a company was not already
working in the area.

### Horizons
Primary: 12 months. Secondary: 24 months. 3/6 months only if positive counts allow.
The 24-month label may only be treated as known when its full window has closed.

## 2. Time discipline

- Features at `τ` use only rows with `event_date <= τ` **and** `available_at <= τ`;
  financial facts additionally require `filed <= τ`.
- Labels use events in `(τ, τ + h]` only.
- A row is *mature* iff `τ + h <= coverage_end`; otherwise its label is `null` and
  the row is `pending`, never guessed. Pending origins are omitted by default.
- **Purge/embargo:** a training example may train an origin only if its label window
  has closed: `cutoff + h <= origin`. Violating this leaks up to 9 months of the test
  window into training and inflates calibration.
- Origin eligibility (T-entry): `τ − 36 months >= coverage_start` and
  `τ + 12 months <= coverage_end`. Dormancy uses exact calendar months, not 1095 days.

## 3. Splitting

Expanding-window rolling origin. No random splits anywhere. The last K evaluable
origins are sequential holdout windows (K = 3 primary). Adjacent windows' 12-month
label windows overlap, so windows are **not independent replications**; per-window
mean/std is descriptive dispersion, not a confidence interval.

## 4. Baselines (mandatory, fitted only on purged training rows)

1. **Historical frequency:** training prevalence (constant).
2. **Persistence:** company base rate, track base rate, per-pair base rate (the
   primary no-feature benchmark; supports a claim of "stable per-pair activity").
3. **Classical ML:** logistic regression with training-only median imputation and
   standardization, fixed hyperparameters across all cells and windows.
4. Complex models only after a baseline gap is demonstrated.

## 5. Metrics (all reported, per window and summarized)

PR-AUC / average precision (primary ranking metric under imbalance);
Precision@ceil(10%N); Brier; ECE-10; false-positive rate at a **pre-specified**
threshold; **lead time at matched false-alarm rate** with never-detected units
counted as censored (not dropped); per-origin AP stability; n rows; n positives;
training rows; cluster-aware confidence intervals (cluster by company and by pair).

Explicitly discouraged: ROC-AUC alone (optimistic under 1% prevalence); FPR@0.5 when
no predicted probability reaches 0.5 (it is then uninformative and must be labelled
as such, as in v2 entry results).

## 6. Inference

- Uncertainty is cluster-aware: rows repeat companies and pairs across quarters.
  Row-level bootstrap understates uncertainty and is not accepted for a headline claim.
- Every model-vs-baseline comparison reports a paired bootstrap CI on the difference.
- Every null result is accompanied by the **minimum detectable effect** at the
  observed number of positives, so a null is reported as "underpowered" or "no effect
  detectable at this power", never silently as "no effect".
- Overlapping-labelled windows are reported per window; a pooled estimate must use
  cluster-robust inference and must not treat windows as independent draws.

## 7. Success and failure conditions (pre-declared)

A predictive claim is **supported** only if all hold:
(a) it beats the relevant persistence baseline on the primary metric;
(b) the cluster-aware CI on the difference excludes zero;
(c) the sign is stable across all reported holdout windows (not just the last);
(d) it survives the same protocol on an independent entity cohort (e.g. legal-entity
universe vs corporate-parent universe); and
(e) it is reproducible from a committed artifact by a single command.

Otherwise it is reported as **not supported** — including when the point estimate is
favourable. A single favourable window is a hypothesis, not a finding.

## 8. Forecast registry discipline (prospective track record)

- A registered forecast is immutable. A model update creates a new record; it never
  overwrites the old one.
- Each record stores: prediction id, company, technology, prediction date, knowledge
  cutoff, horizon, predicted event, probability, model version, data version,
  supporting evidence, contradictory evidence, machine-checkable verification rule,
  and (later) the resolved outcome.
- Outcome verification is rule-based against future public events, with the source
  coverage guard: a forecast cannot resolve before the source that could observe the
  event has published past the horizon.
- Scoring is as-of: only forecasts whose window fully closed may enter a calibration
  cohort. Nowcasts (window already open at registration) are scored in a **separate**
  cohort and never merged into the pure-future headline.
- Calibration reports must include the base-rate comparison, and say
  `insufficient_matured_forecasts` when that is the truth.

## 9. What this protocol forbids

- Choosing the holdout window after seeing results.
- Tuning on the test window and reporting it as out-of-sample.
- Reporting only successful predictions' lead time.
- Reporting a null without its power/MDE.
- Using future-published data to build historical features.
- Labelling a retrieval-time knowledge clock as a historical publication time.
