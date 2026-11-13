# CHANGEPOINT — change detection for the OBSERVE layer

Status: implemented in [`medradar/intelligence/changepoint.py`](../../medradar/intelligence/changepoint.py),
tested offline in [`tests/test_changepoint.py`](../../tests/test_changepoint.py) (44 test
methods, 92 subtests). Pure standard library (`math`, `typing`); no I/O, no network, no
randomness, no wall clock. Run the tests with:

```
python -m pytest tests/test_changepoint.py -o addopts="" -q
```

This is the statistical core of the OBSERVE layer: given a monthly stream of public
regulatory events for one cell (company x technology track, or company x domain), decide
whether the *rate* of activity changed. It is deliberately separate from Understand
(what the change means) and Anticipate (what happens next).

**A detection is a statistical statement about the rate of observed public regulatory
events in a cell. It is not a claim about intent, capability, internal R&D, product
quality or future performance. A quiet cell is not "doing nothing" — it may simply not
file through the paths this corpus observes.**

## 1. Contract

A *stream* is a list of `(date_iso_string, count)` pairs in ascending monthly order,
`count >= 0`, integer-valued. A *detection* is a plain dict and is **at most one per
stream per detector** (the first declaration):

| key | meaning |
|---|---|
| `index` | position in the stream where the change is declared |
| `date` | `stream[index][0]`, verbatim — dates are never parsed or invented |
| `direction` | `"up"` or `"down"` |
| `statistic` | the detector's own statistic at declaration |
| `threshold` | the threshold it crossed |
| `baseline_rate` | mean count over all months **before** `index` (events/month) |
| `observed_rate` | mean count over all months **at/after** `index` (events/month) |

`baseline_rate`/`observed_rate` are the harness's descriptive fields, not what triggered
the detector. `observed_rate` uses the remaining stream as look-ahead, so a
spike-then-revert stream reports a diluted rate: that dilution *is* the signal that the
elevation did not persist. The triggering value is `statistic`.

**Causal declaration.** A detector may only use months up to the month it alarms on, so
`index` can be later than the true onset and never earlier. `index` is the alarm month for
naive / z-score / CUSUM; for the Bayes factor it is the reported change point (never later
than the alarm, and never earlier than `BAYES_INDEX_TOLERANCE` allows relative to the best
split).

**Degenerate input returns `[]` and never raises:** empty or one-point streams, malformed
rows (negative/fractional/non-numeric counts, non-string dates), all-zero streams,
streams with fewer than `min_baseline_events` events, histories shorter than a detector's
minimum, and invalid parameters (non-positive thresholds, `window < 2`, ...).

**Determinism and purity.** No randomness, no clock, no dict-ordering dependence, the
input stream is never mutated, and a tuple-of-tuples stream behaves exactly like a list.

`DETECTORS` maps the stable names the evaluation harness imports — `"naive_multiplier"`,
`"rolling_zscore"`, `"poisson_cusum"`, `"poisson_bayes_factor"` — to the four functions.

## 2. The four detectors

### 2.1 `detect_naive_threshold(stream, *, multiplier=3.0, min_baseline_events=3)`

The baseline comparator (the straw man a real detector must beat). Trailing
`NAIVE_OBSERVED_WINDOW = 3` months are compared with the rate over **all** months before
that window; the statistic is the rate ratio. One-sided (up only). Two sparse-data
guards: the baseline must contain `min_baseline_events` events and the observation window
must contain at least `NAIVE_MIN_OBSERVED_EVENTS = 6` events. Six is deliberate: at
0.2 events/month (the real corpus shape, 78% zero months) a 3-month window usually holds
0-2 events, and a ratio from that is noise. With the floor at 4, the detector alarmed on
39% of uninjected real cells; at 6, on 8-10% (measured, see §3).

No notion of persistence: a single large spike is declared a change.

### 2.2 `detect_rolling_zscore(stream, *, window=12, min_window_events=5, threshold=3.0)`

Two-window comparison: the last `window` months (total `C`) against the previous `window`
months (total `R`), using the variance-stabilised (Anscombe) normal score

```
z = (2 sqrt(C + 3/8) - 2 sqrt(R + 3/8)) / sqrt(2)
```

Two-sided: `"up"` for `z > threshold`, `"down"` for `z < -threshold`. `min_window_events`
guards the normal approximation: on the observed side for `up`, on the reference side for
`down` (an observed zero is a legitimate decrease, so the floor cannot live there). Needs
`2 * window` months.

The plain Poisson score `(C - R) / sqrt(R)` was measured to alarm on **70% of uninjected
real cells** at the default threshold — its normal approximation is far too optimistic at
0-3 events/month. The Anscombe form alarms on 12% while keeping the "N standard
deviations" reading of the same threshold. This is the newest and least battle-tested of
the four.

### 2.3 `detect_poisson_cusum(stream, *, baseline_window=24, threshold=5.0, drift=0.5, min_baseline_events=3)`

One-sided Poisson CUSUM in log-likelihood-ratio form. Every month from `MIN_BASELINE_MONTHS`
on is a candidate change point `s`; `mu0` is re-estimated from the `baseline_window` months
before `s` (a *local* reference, so slow drift does not poison it), the target rate is

```
mu1 = mu0 + max(drift, drift * mu0)
```

and increments `x ln(mu1/mu0) - (mu1 - mu0)` are accumulated with a zero floor. The
earliest alarm month across candidates is declared. The `max(drift, .)` floor matters: a
purely relative +50% target would chase a +0.05 events/month shift in a 0.1 events/month
cell, while a purely absolute one would miss a doubling of a dense cell.

Power on injected real cells is the best of the four (+5x: 0.62 detected within 12 months),
and so is the false-alarm propensity (50% of uninjected cells at the default threshold).
That is not a bug in the implementation: at sparse rates a couple of extra filings are
genuinely strong Poisson evidence, and real filings are bursty (overdispersed) relative to
Poisson. Threshold 8-12 is the intended operating range; the harness's calibration grid
already contains both.

### 2.4 `detect_poisson_bayes_factor(stream, *, baseline_window=24, threshold=10.0, prior_shape=1.0, prior_rate=1.0, min_baseline_events=3)`

Bayesian Poisson rate-change statistic. At every month `t` and candidate change point
`tau` in the recent window, it compares two independent Poisson-Gamma segments with one
constant-rate segment. With `Gamma(a, b)` priors the segment marginal likelihood is
closed-form:

```
log p(data | a, b) = a ln b - ln Gamma(a) + ln Gamma(a + S) - (a + S) ln(b + L)
```

(`S` events over `L` months; the `prod 1/x_i!` factors cancel between models). Candidate
log Bayes factors are **averaged** over `tau` (uniform prior, log-sum-exp) rather than
maximised, so a split supported by only one month cannot carry the statistic; the reported
change point is the **latest** `tau` within `BAYES_INDEX_TOLERANCE = 2` nats of the best
one. `threshold` is a **natural-log** Bayes factor: the default 10 means `BF ~= e^10 ~=
22,000`, i.e. "very strong" in Jeffreys' scale. Two-sided: a sustained decrease is
declared `"down"`.

This is the best-behaved detector on real data (1.9% of uninjected cells at the default)
and the most resistant to bursts, at the cost of being the most conservative: threshold
2-5 is the sensitive range, and the default 10 buys false-alarm control.

## 3. Measured behaviour (this corpus, these defaults)

Measurements use the real 120-month cells in `experiments/detect_v1/streams.json`
(107 track cells / 124 domain cells; median 24 events per cell, 78% zero months) and the
injection procedure of the pre-registered benchmark (`experiments/detect_v1/benchmark.py`:
Poisson re-draw of the post-onset months, onsets 36/54/72/84, multipliers 2/3/5, 12-month
horizon). The real-data half is read-only; nothing in `data/` was written.

### 3.1 Uninjected real cells at default thresholds

Fraction of cells with at least one declaration over 120 months (per-cell-year rate in
brackets; each cell is 10 cell-years):

| detector | track cells (107) | domain cells (124) |
|---|---|---|
| `naive_multiplier` | 9 (8.4%) [0.008] | 12 (9.7%) [0.010] |
| `rolling_zscore` | 13 (12.1%) [0.012] | 13 (10.5%) [0.011] |
| `poisson_cusum` | 54 (50.5%) [0.051] | 66 (53.2%) [0.053] |
| `poisson_bayes_factor` | 2 (1.9%) [0.002] | 3 (2.4%) [0.002] |

These "false" alarms are not all noise: the real cells genuinely change level (new product
lines, acquisitions, first filings in a new pathway). The uninjected-cell rate is an upper
bound on detector noise, not a pure noise measurement.

### 3.2 Injected sustained shifts — detection probability within 12 months (track cells, 1,284 trials each)

| detector | x2 | x3 | x5 | median delay (x5) |
|---|---|---|---|---|
| `naive_multiplier` | 0.10 | 0.24 | 0.49 | 4 months |
| `rolling_zscore` | 0.04 | 0.15 | 0.44 | 8 months |
| `poisson_cusum` | 0.27 | 0.44 | 0.62 | 4 months |
| `poisson_bayes_factor` | 0.04 | 0.16 | 0.48 | 2 months |

A detection is counted only when `index` is inside `[onset, onset+12]` and direction is
`"up"`, exactly as the harness counts it.

### 3.3 Injected single-month spikes — fraction wrongly declared an upward change

| detector | x2 spike | x5 spike |
|---|---|---|
| `naive_multiplier` | 0.012 | 0.054 |
| `rolling_zscore` | 0.002 | 0.014 |
| `poisson_cusum` | 0.058 | 0.136 |
| `poisson_bayes_factor` | 0.002 | 0.007 |

### 3.4 Hand-built streams in the unit tests

| stream | behaviour |
|---|---|
| clean +5x step at month 48 (2 to 10 events/month, 60 months) | every detector declares up; indices 48 (Bayes), 49 (naive, CUSUM), 51 (z-score); none precedes the onset |
| same step with all counts x10 | every detector still detects (scaling invariance) |
| downward step (2 to 0 events/month) | naive and CUSUM silent (one-sided by contract); z-score and Bayes factor declare `"down"` |
| 120-month sparse cell (17 isolated 1s, no two in a row) | no detection from any detector |
| same cell with one 3-event burst month | no detection from any detector |
| 60-month stationary cell around 3 events/month | no detection from any detector |
| +50% and +100% sustained shifts | naive and Bayes factor silent at defaults |
| one 30x spike month | all four declare `"up"`; naive/z-score/CUSUM at the spike month, Bayes factor 2 months early (see §4.4); no detection for a 3x spike |

## 4. Failure modes and limitations

1. **Sparse counts and overdispersion.** Most cell-months are 0 and real filings arrive in
   bursts, so monthly counts are overdispersed relative to Poisson. A cluster of two or
   three filings is a statistically strong Poisson signal and can be declared a change;
   the CUSUM is the most exposed (50% of real cells at its default threshold). A
   negative-binomial or quasi-likelihood model would be the principled fix and is not
   implemented.
2. **Seasonality.** No detector removes monthly/quarterly/annual cycles (budget months,
   fiscal-year end, advisory-committee calendars). A cell with a recurring cycle can look
   like a change every year; the z-score is the most exposed because it compares one year
   with the previous one.
3. **Variable exposure.** The count has no offset. A change in the *population* of filings
   (a new regulatory pathway, a resumed collection feed, a product-line reclassification,
   an acquisition changing the legal-entity key) is indistinguishable from a change in
   activity. Any detection must be checked against collection/exposure changes before it
   is treated as a signal.
4. **Clustered events and single spikes.** A one-month burst is a real short-run rate
   increase, so every rate detector can flag a large enough burst; this is a statistical
   statement, not a regime change. Only the Bayes factor has any structural resistance.
   Persistence should be checked (e.g. 2-3 consecutive monthly declarations) before acting
   on a borderline alert.
5. **Single change point.** Only one change in a fixed window is modelled: two changes close
   together, a slow ramp or a mean-reverting pulse are collapsed or missed. CUSUM's local
   baseline re-estimation makes it drift-robust but means it can declare a *later* change
   point than the true onset when the elevated period itself supplies the reference.
6. **Bayes-factor localisation of a burst.** A one-month burst is not identifiable in a
   two-segment model: the reported change point can sit 1-2 months before the burst (the
   evidence is spread over the months preceding it). For a *sustained* shift the change
   point is sharp. The reported `index` can therefore be slightly early for bursts — never
   earlier than the latest near-optimal split, but a burst makes "latest" ambiguous.
7. **Near-end censoring.** The Bayes factor needs `BAYES_MIN_POST_MONTHS = 3` months after
   the change point, so a change in the last two months of a stream cannot be declared by
   it. CUSUM and z-score need their own windows; the naive comparator needs
   `MIN_BASELINE_MONTHS + NAIVE_OBSERVED_WINDOW` months of history.
8. **No multiple-testing guarantee.** One declaration per stream at a nominal threshold is
   not a family-wise error rate over ~2,000 cells. The real corpus will produce alerts at
   any non-trivial false-alarm rate; the benchmark's matched-FAR evaluation and a per-cell
   hypothesis test (as in `experiments/detect_v1/realdetect.py`) are the right controls.

## 5. What the Lead must not conclude from a detection

* **Not intent, capability or strategy.** "This company is investing in surgical robotics"
  is not implied by a jump in 510(k) filings assigned to a technology track. The track
  assignment itself is heuristic (product-code mapping + keyword fallback).
* **Not a quality or safety signal.** A rate increase is not a defect, a recall risk or a
  quality change.
* **Not a forecast.** OBSERVE says what happened to an event rate; it does not say the rate
  will stay elevated in Anticipate's horizon.
* **Not comparable across cells or companies.** Rates, eligibility and reporting
  completeness differ by company size, track and regulatory pathway; a detection in a
  24-event cell and one in an 86-event cell are not the same evidence.
* **Not proof that a difference between detectors is real.** With at most one declaration
  per stream, a calibrated false-alarm target above 0.1 alarms/cell-year can never be
  binding (see integration note 1) — treat the benchmark's sensitivity ordering with care.

## 6. Integration notes for the evaluation harness

1. **The calibration target may be unreachable in the wrong direction.** The contract
   allows at most one detection per stream per detector, so over a 120-month stream the
   realised FAR is at most `1/10 = 0.1` alarms per cell-year. With
   `TARGET_FAR = 0.25` in `experiments/detect_v1/benchmark.py`, *every* knob on every grid
   passes the FAR screen, so `chosen = max(passing, key=knob)` always selects the most
   conservative knob (e.g. Bayes-factor threshold 30, CUSUM 12). That reports near-zero
   detection power for every detector. If sensitivity is the point of the benchmark,
   either lower `TARGET_FAR` below the 0.1 floor (e.g. 0.02) or count alarms rather than
   alarmed cells. (Reported to the Lead; the detector code does not depend on it.)
2. **The Bayes-factor index is its estimated change point, not its alarm month.** The
   harness's hit test `onset <= index <= onset+12` counts a declaration as a miss when the
   Bayes factor localises a sustained shift one month before the injected onset (measured
   on the calibration grid: a few percent of trials; on the clean unit-test step it lands
   exactly on the onset). If that matters, either accept a 1-month tolerance or expose the
   alarm month as an extra key.
3. **Threshold grids are monotone in the expected direction.** Measured FAR by knob:
   z-score 2.0/2.5/3.0/3.5/4.0/5.0 -> 0.58/0.23/0.12/0.04/0.01/0.00; CUSUM
   2/3/4/5/8/12 -> 0.99/0.81/0.64/0.50/0.27/0.13; Bayes factor 2/3/5/10/20/30 ->
   0.38/0.24/0.13/0.02/0.00/0.00 (track cells, uninjected). The grids are sensible; the
   selection rule is what needs fixing.
4. **`observed_rate` is a reporting field.** Acting on it as an effect size is legitimate
   only for sustained changes; for transients it is diluted by construction (§1).

## 7. Test inventory

44 test methods / 92 subtests, all offline and deterministic:
contract keys and types, exact detector registry, all degenerate and malformed inputs,
invalid parameters, realistic sparse streams (and a burst inside one), stable streams,
modest shifts, clean step change (declaration, causality, latency, threshold crossing),
downward change (one-sided vs two-sided), large vs moderate single spikes and spike
dilution, tenfold count scaling, rate/date/index consistency, non-mutation, tuple input,
float-valued integer counts, and parameter-suppression guards that prove each knob is
actually used.
