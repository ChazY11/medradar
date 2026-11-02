# MedRadar Foresight Lab — Mission

**Status:** living document. The mission changes only by an explicit, recorded decision (see `DECISIONS.md`).
**Established:** 2026-11-02. **Basis:** project brief "MEDRADAR — PROJECT HORIZON".

## 1. The scientific question

How much of a corporation's *future* technological direction can be predicted from
*publicly available information before the fact* — and what does the residual
unpredictability tell us about how technological evolution actually happens?

Concretely, for a company `c`, a technology family `t`, and a knowledge cutoff `τ`:

> Given only evidence that was publicly obtainable at or before `τ`, what is the
> probability that `(c, t)` exhibits a verifiable public technology milestone in
> `(τ, τ + h]`?

This must be answered with predictions that a third party can falsify by waiting.

## 2. Non-negotiable epistemic rules

These are constraints on *us*, not on the data. Violating one invalidates the result.

1. **Predict forward, never explain backward.** Every experiment states: prediction
   date, information cutoff, target definition, observation window, success
   condition, failure condition. No feature may use information published after the
   cutoff. `event_date`, `published_at`, `first_seen_at`, `available_at` and
   ingestion time are distinct concepts and must never be conflated.
2. **Falsifiable targets only.** No claim of the form "company X is secretly
   developing Y". Only claims of the form "a verifiable public milestone of type Z
   for (company, technology) occurs within h months of τ".
3. **Complex models must beat simple baselines.** Every study reports a historical
   frequency baseline and a no-feature persistence baseline before any learned
   model. Architectural complexity is not evidence of skill.
4. **Prediction is not causation.** Predictive skill does not identify a causal
   market→R&D mechanism. Causal language requires an identification design we have
   not yet built.
5. **Failure is a result.** Unreproducible experiments, models that fail to beat
   baselines, data sources that add no information, unstable estimates, rejected
   hypotheses and negative findings are recorded and published, not hidden.
6. **No fabricated numbers, ever.** Every number in a report must be traceable to a
   committed artifact or a re-runnable command. If a claim cannot be reproduced it
   is reported as FAIL.
7. **Pre-registration of the test set.** Final evaluation windows are locked before
   modelling and are not re-chosen to improve results.

## 3. Scope

**Sector (first):** medical devices. Chosen for data density and comparability, not
because the method is sector-specific.

**Deep-case companies (5, mandated):** Medtronic, GE HealthCare, Philips, Dräger,
Mindray. The deep cases are *not* the training sample; they are the interpretability
cases and the human-readable evidence chains.

**Comparison pool:** a systematic cohort of comparable firms built from the industry
lane itself (not hand-picked) used for statistical power and generalization tests.

**Unit of analysis:** `Company × Technology × Time`. Never `Company` alone for
forecasting; never `Technology` alone.

**Horizon:** 12 and 24 months primary; 3 and 6 months only if data supports it.

**Out of scope until later:** cross-industry transfer (robotics, semiconductors,
energy); causal identification without a design; LLM-generated probabilities.

## 4. Three required scientific contributions

**A — Open Research Benchmark.**
A point-in-time, reproducible dataset and evaluation protocol for corporate
technology forecasting: historical technology footprints, regulatory/product events,
patents and publications, financials, procurement, public hiring, capital-market
signals; explicit knowledge-cutoff semantics; training/validation/test protocol.
Every datum carries source, event time, knowledge time and licence/quality marks.
Shareable portions are opened.

**B — Forward-Looking Prediction Method.**
Methods that genuinely improve out-of-sample forecast quality, lead time or
calibration against strong baselines: Bayesian forecasting, temporal change-point
detection, survival analysis, multimodal temporal learning, temporal knowledge-graph
learning, evidence-aware representation learning, calibration. The goal is a method
that survives purged rolling-origin evaluation — not a novel architecture.

**C — Empirical Discovery.**
Reliable, falsifiable findings about the *timing relations* between public signals
and technological activity: whether hiring leads team expansion, whether procurement
reveals demand before R&D, whether capital-market signals carry incremental
information after controlling for sector, whether financial capacity predicts entry
into new technology areas — and honest nulls where none of this holds.

## 5. What success looks like (falsifiable, cumulative)

- A benchmark any external researcher can re-run offline and get identical numbers.
- Frozen, timestamped forecasts that later resolve against genuinely future data,
  with a published calibration report (including when calibration is worse than the
  base rate).
- At least one empirical claim about lead/lag structure that survives purging,
  clustering-aware inference and out-of-window replication — *or* a well-powered
  demonstration that no such claim is sustainable on public data.
- Every negative result from section 2.5 published alongside positive ones.

## 6. The loop

`Observe → Question → Hypothesize → Implement → Experiment → Evaluate → Record → Improve`

Each cycle must leave at least one verifiable artifact: code, data-quality
improvement, evaluation set, reproducible experiment, evidence-backed finding, or a
recorded negative result. `STATE.json` records where the loop currently stands.

## 7. Honest position as of 2026-11-02

What we can already say, with evidence in `RESULTS/`:

- Predicting *continued* public activity for an already-active `(company, track)`
  pair is easy (AP ≈ 0.77) but a one-parameter per-pair persistence baseline reaches
  AP ≈ 0.76; the model's advantage is not statistically detectable.
- Predicting *first entry* into a dormant technology track is hard: base rate 1.23%,
  AP ≈ 0.11. The point estimate beats persistence baselines but only one of three
  holdout windows excludes zero, so it is **not yet a validated predictor**.
- No added source tested so far (consolidated SEC financials, point-in-time market
  features, OpenAlex publication counts) produces a detectable ranking gain. These
  may be true nulls or underpowered tests — distinguishing those two is an active
  question, not a settled one.
- No forecast has yet matured, so we have **no** calibration evidence of our own.

What we must not say: that the system predicts corporate R&D direction, that it
finds causal market→R&D mechanisms, or that any complex model beats baselines.
