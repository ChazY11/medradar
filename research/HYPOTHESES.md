# Cycle 2 hypothesis cards — coverage, power, and the reality of the entry signal

**Written before any cycle-2 experiment is run.** Owner: `research-auditor`.
Created 2026-11-02 on branch `research/cycle2-coverage-power`
(worktree HEAD ref `1749bd5f3af92519f97f0f4978b209da70e45b7b`).
Any change to a card after results are seen must be recorded in `research/DECISIONS.md`
and invalidates the affected comparison.

**Purpose.** Cycle 1 produced (a) a weak entry signal that is not a validated
predictor, and (b) a set of "added source adds nothing" nulls. The open question is
whether these are statements about the world or about our measurement/power. These
cards make that question falsifiable in advance. Every card states the estimand, the
prediction, the exact test, and the result that would kill it.

## Conventions used by every card

- **P1** = frozen curated-parent panel (51 companies; reproduces cycle-1 numbers).
  **P2** = deterministic legal-entity applicant universe built in cycle 2 (see
  `research/CYCLE2_DESIGN.md`).
- **W1/W2/W3** = the pre-declared holdout windows `2025-04-01`, `2025-07-01`,
  `2025-10-01` (the last three origins with a purged training set). No window may be
  selected after results are seen.
- **AP** = average precision (PR-AUC), primary metric. **ΔAP** = paired difference
  `AP(model) − AP(baseline)` on identical rows. **Precision@k** = precision at
  `k = ceil(0.10·N)`. **Brier**, **ECE-10** secondary.
- **MDE₈₀** = minimum detectable absolute effect at 80% power, two-sided α = 0.05,
  with cluster-aware (company and pair) inference.
- **Cluster bootstrap** = 2,000 resamples, fixed seed, resampling company (and pair)
  clusters, never individual rows, because rows repeat companies and pairs across
  origins.
- **Frozen cycle-1 anchors** (audited; see `docs/research/AUDIT_CYCLE2.md`):
  entry 503 positives / 41,003 rows / 24 origins, base rate 0.012267; per-origin
  positives 10–28, candidates 1,634–1,730; holdout rows/positives 1,722/25,
  1,721/27, 1,716/26; entry AP 0.118793 / 0.087657 / 0.113927 (mean 0.106792,
  std 0.013675, rd_only) and 0.132107 / 0.096154 / 0.116347 (mean 0.114869,
  std 0.014715, rd_fin); pair-persistence AP 0.079463 / 0.047244 / 0.027826;
  ΔAP mean 0.055281 (CI excludes 0 only in W3); continuation AP mean 0.773718 vs
  pair baseline 0.755470.
- **Status vocabulary:** `UNTESTED` (no data yet), `PARTIAL` (only degenerate or
  indirect evidence exists), `REJECTED` (falsification condition met), `SUPPORTED`
  (pre-declared success condition met). A card is never "supported" on one window.

## Shared test protocol (applies to every card)

Data: `data/research.sqlite`, opened **read-only**
(`sqlite3.connect("file:...?mode=ro", uri=True)`). Labels and features must satisfy
the frozen protocol in `research/PREDICTION_PROTOCOL.md`: features
`event_date <= τ` **and** `available_at <= τ` (financials `filed <= τ`); labels from
events in `(τ, τ+12m]`; material-event rule exactly as in `docs/REVERSE_RD.md`;
dormancy 36 exact calendar months; origins `τ − 36m >= coverage_start` and
`τ + 12m <= coverage_end`; purge `cutoff + 12m <= origin`; expanding-window rolling
origin; identical algorithm/hyperparameters across panels and specifications. **P1
must first reproduce the frozen numbers; a mismatch blocks every P2 claim**
(pre-registered in `research/CYCLE2_DESIGN.md`).

---

## H-C2-1 — Coverage → power: more entities, enough positives to resolve anything

- **Claim.** Widening the entity universe from the 51 curated corporate parents (P1)
  to a deterministic applicant-entity universe (P2) increases entry positives per
  origin enough that the entry signal becomes statistically resolvable, without the
  base rate collapsing into never-active micro-entities.
- **Why it matters.** 84% of the P1 candidate universe (1,616 of 1,938 cross-product
  cells) has never been observed in a decade; 25 positives per window is the binding
  statistical constraint on every entry claim. If coverage is the bottleneck, the
  correct next move is panel construction; if it is not, the null is about the world.
- **Operational hypothesis.**
  - Estimand: `θ_pos` = median positives per origin over the 24 frozen origins;
    `b` = positives/rows (base rate) under P2; `dup` = share of P2 entities that are
    formatting variants of another entity (manual audit of a random 200-entity sample,
    upper 95% bound).
  - **H0:** `θ_pos <= 39` (less than 1.5× the P1 holdout positive count) **or**
    `b ∉ [0.005, 0.03]`.
  - **H1:** `θ_pos >= 60` **and** `b ∈ [0.005, 0.03]` **and** `dup < 0.05`.
- **Prediction.** `θ_pos` 60–120; `b` 0.008–0.020; candidate rows/origin 3,000–8,000.
  (Mechanically more entities → more candidate pairs, so also report per-entity event
  density; a pure pair-count increase is not evidence of coverage of real activity.)
- **Test procedure.** Build P2 deterministically from `events.applicant_raw`
  (normalisation + exact blocking; fuzzy cross-name merging forbidden), rebuild the
  entry dataset under the identical material-event/dormancy/label/origin rules,
  recompute per-origin candidates and positives. Compare P1 vs P2 descriptively;
  report the focus-company gap (Mindray 90 records, Dräger 25 records absent from P1).
- **Falsification condition.** `θ_pos < 60` at the same origins; **or** `b < 0.005`
  (panel dominated by micro-entities — the comparison is invalid); **or** `dup >= 0.05`
  (the "universe" is name formatting, so positives are duplicated events, not new
  information).
- **Confounders / threats.** `applicant_raw` spelling noise; blocking key determines
  who can ever enter the panel (Papadakis et al.); P2 over-represents large applicants
  whose names are resolvable (selection correlated with outcomes); changing the
  universe also changes prevalence, and AP is prevalence-dependent (Saito &
  Rehmsmeier) — so compare ΔAP, never raw AP across panels.
- **Status.** `UNTESTED` (P2 does not exist yet; task-2 in progress).
- **Evidence pointer.** `docs/REVERSE_RD.md` §Entry; `research/DATA_PROVENANCE.md`
  §4.1–4.2; `experiments/reverse_rd_v2/entry_metrics.json` → `dataset`
  (`candidates_by_origin`, `positives_by_origin`, `observed_pair_count=322`);
  audit doc claims 1 and 3.

---

## H-C2-2 — Entity-granularity ablation: parent vs legal entity changes the estimate

- **Claim.** The cycle-1 entry estimate is an artefact of hand-curated corporate-parent
  aggregation: switching to legal applicant entities (P2) changes entry AP by more
  than the window-to-window dispersion, even under an identical protocol.
- **Why it matters.** Curated parents sometimes fold in subsidiaries (Medtronic
  absorbs Covidien) and sometimes do not; entity choice is a measurement decision that
  can manufacture or destroy persistence. If AP is invariant to it, prior numbers are
  robust to a known defect; if not, every prior entry number needs an entity caveat.
- **Operational hypothesis.**
  - Estimand: `ΔAP_gran = AP_entry(P2) − AP_entry(P1)` for both `rd_only` and
    `rd_financial`, per window and window mean; and `δ_pair = ΔAP(model − pair
    persistence)` under each panel.
  - **H0:** `|ΔAP_gran| <= 0.02` (≈1.4× the larger frozen window std, 0.014715) and
    `sign(δ_pair)` is the same under P1 and P2.
  - **H1:** `|ΔAP_gran| > 0.02` **or** `sign(δ_pair)` flips between panels.
- **Prediction.** P2 increases positives but lowers per-entity event density, so
  entry AP falls: `AP_entry(P2) − AP_entry(P1)` in **−0.05 to −0.01**, and `δ_pair`
  stays non-significant in both panels (the cycle-1 skill was weak either way).
- **Test procedure.** Run the frozen protocol twice (P1 first as a reproduction gate,
  then P2) with identical rows-except-entity, features, model, purge and windows;
  paired cluster bootstrap on the difference; report observed-pair coverage
  (`322/1938 = 16.6%`) under both panels.
- **Falsification condition.** `|ΔAP_gran| <= 0.02` with overlapping CIs → granularity
  is **not** a first-order determinant (then prior numbers get a "robust to entity
  choice" note). If instead `AP_entry(P2) > AP_entry(P1) + 0.05`, the parent folding
  was destroying real signal and the direction is opposite to prediction — report as
  a refuted prediction, not as support.
- **Confounders / threats.** P2's resolvable entities are a size-selected sample;
  merging decisions inside P1 are undocumented; label density and prevalence differ,
  so AP comparison is only valid with ΔAP and a common baseline; the single protocol
  is held fixed to keep the comparison attributable to one variable.
- **Status.** `UNTESTED`.
- **Evidence pointer.** `research/CYCLE2_DESIGN.md` §H2.3;
  `research/DATA_PROVENANCE.md` §4.3–4.4; `docs/REVERSE_RD.md` "company aliases are
  incomplete and acquisitions change ownership over time".

---

## H-C2-3 — Heterogeneity: predictability concentrates in identifiable strata

- **Claim.** Entry predictability is not uniform: it concentrates in high-activity
  technology tracks and/or high-activity companies, and the pooled AP hides most of it.
- **Why it matters.** A pooled AP of 0.107 with per-origin range 0.018–0.237 suggests
  strong non-stationarity; if the signal lives in a pre-identifiable stratum, the
  programme should forecast there and stop pooling. If not, the pooled weak result is
  the honest summary.
- **Operational hypothesis.**
  - Estimand: for each pre-declared stratification — (i) track activity tercile,
    (ii) company activity tercile, (iii) origin era (2020–2021 / 2022–2024 / W1–W3) —
    the gap `G = AP(top tercile) − AP(bottom tercile)` with a cluster-aware CI.
    Terciles are computed **only on purged training rows** at each origin, never on
    evaluation rows.
  - **H0:** `G <= 0` in every stratification (or not estimable).
  - **H1:** `G > 0` in at least 2 of 3 stratifications, 95% CI excluding 0 after
    Holm adjustment, with ≥10 positives in each compared cell.
- **Prediction.** `G_track` +0.05 to +0.15; `G_company` +0.03 to +0.10; era: AP in
  2020–2021 near chance (consistent with the frozen first-origin AP 0.018130).
- **Test procedure.** Per-stratum AP on W1–W3 and pooled; company/pair-cluster
  bootstrap for `G`; permutation test for top-vs-bottom labelling; report n rows,
  n positives and "not estimable" where positives < 10. Pre-register the three
  stratifications before running.
- **Falsification condition.** All `G <= 0.02` or all adjusted CIs include 0 → no
  exploitable heterogeneity (the pooled weak signal is the result). Any apparent `G`
  that disappears when the stratum base rate is matched is also a falsification
  (heterogeneity was prevalence, not skill).
- **Confounders / threats.** Sparse positives: the frozen holdout subgroups are
  **degenerate** — with 1716 rows / 26 positives across 51 companies and 38 tracks,
  most subgroup APs are `null` and single-positive groups report AP = 1.0 (observed:
  `orthofix`, `stryker`, `teleflex` each 1 positive → AP 1.0). Multiplicity across
  3 stratifications × 2 models × 3 windows; terciles computed on the same history
  used for training make membership partially endogenous.
- **Status.** `PARTIAL` — the frozen `holdout_subgroups` cannot estimate this
  (positives per company: 0–2). Only *origin-era* heterogeneity has evidence
  (per-origin AP 0.018130 at 2021-01-01 vs 0.237008 at 2023-07-01, mean 0.115007,
  std 0.057940, rd_only). Track/company heterogeneity is UNTESTED at adequate n.
- **Evidence pointer.** `experiments/reverse_rd_v2/entry_metrics.json` →
  `models[*].holdout_subgroups`, `models[*].origin_metrics`; `REPORT.md` §B "Per-origin
  variance" and the negative-results section.

---

## H-C2-4 — Lead time at matched false-alarm rate

- **Claim.** At an identical false-alarm rate, the learned entry model precedes the
  per-pair persistence baseline on the future events it detects; if not, it adds no
  operational value regardless of its AP.
- **Why it matters.** AP is a ranking summary. A forecast system is judged by *when*
  it rings the alarm at an acceptable false-alarm cost. The frozen reports give only
  an unconditional mean positive lead time (190.65 days) and a useless FPR@0.5
  (exactly 0 in every window because no predicted probability reaches 0.5).
- **Operational hypothesis.**
  - Estimand: `ΔL = L_model(FAR*) − L_pair(FAR*)`, where `L` is the restricted mean
    lead time (days) over true positives selected at a **pre-declared** false-alarm
    rate `FAR* = 0.05` (sensitivity 0.02 and 0.10), with positives never selected by
    either model censored at the 365-day horizon end (never dropped).
  - **H0:** `ΔL <= 0`.
  - **H1:** `ΔL >= 30 days`, 95% cluster CI excluding 0, with the model detecting at
    least as many positives at `FAR*` as the baseline (otherwise the comparison is on
    a shrunken event set and must be reported as such).
- **Prediction.** `ΔL` +30 to +90 days at `FAR*=0.05`; if `ΔL ≈ 0` while
  `ΔAP > 0`, AP skill is operationally empty and must be labelled so.
- **Test procedure.** Persist per-row holdout probabilities from the cycle-2 driver
  (the frozen artifacts store metrics only); choose each predictor's threshold to hit
  `FAR*` on the **test origin's negatives** (or on purged development origins — one
  rule pre-declared and reported); compute lead = `first_target_event_date − cutoff`
  in days for selected positives; estimate ΔL with company/pair-cluster bootstrap;
  report detection counts, censored counts, and per-window results.
- **Falsification condition.** `ΔL <= 0`, or CI includes 0 at all three FARs, or the
  model selects fewer positives at matched FAR in a majority of windows → the model
  has no matched-FAR lead-time advantage; drop any "earlier warning" claim.
- **Confounders / threats.** Threshold choice at low prevalence is unstable
  (FAR=0.05 of 1,690 negatives ≈ 85 alerts/window); lead time is right-censored at
  12 months for late events; adjacent windows overlap (not independent); pair
  persistence can score many pairs identically (ties) — break ties deterministically
  and report.
- **Status.** `UNTESTED` (no matched-FAR computation exists; the frozen reports say
  FPR@0.5 is uninformative and give only mean lead time).
- **Evidence pointer.** `research/PREDICTION_PROTOCOL.md` §5;
  `entry_metrics.json` → `holdout_window_summary.models.*.mean_lead_time_days`
  (window mean 190.646819 days); `REPORT.md` §B.

---

## H-C2-5 — The "no added source helps" null is an underpowered null (MDE framing)

- **Claim.** The cycle-1 negative result "no added source produces a detectable
  ranking gain" is **uninformative**: the minimum detectable effect at ~25–27
  positives per window is much larger than the marginal effects observed, so the null
  cannot distinguish "sources are uninformative" from "the test cannot see an effect
  of the size these sources could plausibly produce".
- **Why it matters.** This is the difference between a scientific conclusion and a
  measurement statement. Mission rule: "Every null result is accompanied by the MDE …
  never silently as 'no effect'." Frozen reports currently contain **no MDE at all**
  (audited); the two candidate interpretations in `STATE.json` are "sources
  uninformative" vs "test underpowered" — this card decides between them.
- **Operational hypothesis.**
  - Estimand: `MDE₈₀(ΔAP)` for the paired model-vs-baseline and for each marginal
    source delta (financial, market, publication) at the observed positive counts,
    per window and pooled; and `n_pos` required to detect the observed marginal
    effect at 80% power.
  - **H0 (well-powered null):** `MDE₈₀ <= |observed ΔAP|` for each source.
  - **H1 (underpowered null):** `MDE₈₀ > |observed ΔAP|` (strictly greater; the null
    is not informative about an effect of that magnitude).
- **Prediction.** `MDE₈₀` for pooled entry ΔAP ≈ 0.08–0.12, i.e. ~10× the observed
  financial marginal +0.008077; required positives to detect +0.008 at 80% power
  ≥ 1,000 (vs 78 in three overlapping windows). Therefore **H1**, not H0: the added-
  source nulls are underpowered. (This is an analytic order-of-magnitude prediction,
  not a measurement; the exact number comes from the test.)
- **Test procedure.** Implement a label-preserving, cluster-aware power simulation:
  on frozen holdout rows/residuals, plant marginal ΔAP effects on a grid
  {0.005, 0.01, 0.02, 0.04, 0.08, 0.15}, re-estimate the paired bootstrap decision
  over 2,000 replicates (seed fixed before running), and read off the smallest
  detonable effect at 80% power. Report per source, per window and pooled; report
  sensitivity to the assumed correlation between paired predictions. Cross-check the
  approximation against the analytic binomial order `sqrt(AP(1−AP)/n_pos)`.
- **Falsification condition.** If `MDE₈₀ <= |observed ΔAP|` for a given source, then
  that source's null **is** well-powered and the "no added value" conclusion is
  licensed for it (report as a supported negative, not underpowered). If
  `MDE₈₀ > 0.5` AP units, the test is uninformative at any plausible effect size and
  no further source testing should be run on this panel.
- **Confounders / threats.** Power depends on the assumed effect structure (uniform
  vs concentrated), so the simulation is a lower-bound design decision, not truth;
  overlapping windows are not independent — cluster by company/pair, never by window;
  prevalence shifts under P2 change both AP and its variance.
- **Status.** `UNTESTED` (analytic prediction only; frozen artifacts contain no MDE
  field — see audit). The eval-stats engine is being built separately (task-1).
- **Evidence pointer.** `REPORT.md` §C (marginal deltas vs A/D), §B (financial marginal
  +0.008077 entry; −0.001030 continuation); `research/STATE.json`
  `established_findings`; `research/PREDICTION_PROTOCOL.md` §6.

---

## H-C2-6 — Signal resolution under the expanded panel (pre-registered decision rule)

- **Claim.** Under P2 the entry signal is either resolved (ΔAP vs persistence
  detectable) or the test becomes *conclusively* underpowered; the pre-registered
  decision rule fires either way. "Still underpowered" is not an acceptable default
  two cycles in a row.
- **Why it matters.** The cycle exists to convert an ambiguous negative into a
  decisive outcome. This card binds the team to the decision rule written before the
  run (`CYCLE2_DESIGN.md` §decision rule) and prevents a post-hoc interpretation.
- **Operational hypothesis.**
  - Estimand: `ΔAP_P2 = AP(model) − AP(pair persistence)` per window W1–W3 and pooled,
    with company/pair-cluster 95% CIs; `MDE₈₀(ΔAP_P2)` at the observed positives.
  - **H0:** `ΔAP_P2 = 0`.
  - **H1a (supported signal):** `ΔAP_P2 > 0` with CI excluding 0 in **≥2 of 3**
    pre-declared windows and sign-stable across all three.
  - **H1b (well-powered negative):** H0 not rejected **and**
    `MDE₈₀(ΔAP_P2) < 0.055281` (the cycle-1 mean point estimate).
  - **H1c (still underpowered):** H0 not rejected **and** `MDE₈₀ >= 0.055281`.
- **Prediction.** With ≥60 positives/origin, `MDE₈₀` falls to roughly 0.03–0.05; the
  cycle-1 point estimate is 0.0553, so the outcome is borderline. I predict **H1b**
  (well-powered negative) is the most likely single outcome, with H1a plausible if P2
  also sharpens the label. H1c would falsify the coverage hypothesis (H-C2-1).
- **Test procedure.** Cycle-2 driver on P2, identical protocol; pre-declared windows;
  report all windows, pooled cluster-robust estimate, and MDE₈₀; no window selection.
  Also report the same three quantities on P1 as the reproduction check.
- **Falsification condition.** If H1c fires (neither supported nor well-powered), the
  coverage→power premise failed: report "still underpowered" and specify the positive
  count needed next (do not run more sources). If the P1 reproduction mismatches the
  frozen numbers, no P2 result may be reported at all.
- **Confounders / threats.** P2 prevalence differs from P1 (AP incomparability);
  windows share overlapping 12-month label windows; entity-resolution errors may be
  correlated with the outcome (e.g. larger firms linked better and also more active);
  MDE is model-dependent.
- **Status.** `UNTESTED`; decision rule pre-registered.
- **Evidence pointer.** `research/CYCLE2_DESIGN.md` §Protocol, §Decision rule;
  `entry_metrics.json` → `model_vs_pair_baseline` (Δ 0.039329 / 0.040413 / 0.086101;
  only W3 CI excludes 0); `continuation_metrics.json` → same comparison (only W1
  excludes 0).

---

## H-C2-7 — Calibration at 1.2% prevalence: probabilities are overconfident, and post-hoc calibration fixes Brier without fixing AP

- **Claim.** Entry-model predicted probabilities are miscalibrated in the direction of
  overconfidence (calibration slope < 1), and an isotonic/Platt map fitted only on
  purged development origins improves Brier/ECE while leaving AP unchanged.
- **Why it matters.** The programme has zero matured registered forecasts
  (`registry.sqlite`: 25 forecasts, 0 resolutions), so its only probability evidence is
  backtest Brier/ECE. If those probabilities are overconfident, any future decision
  rule that thresholds them will over-alert; if they are already calibrated, the
  calibration workstream is unnecessary.
- **Operational hypothesis.**
  - Estimand: calibration slope `β` and intercept `α` from regressing observed labels
    on `logit(p)` on holdout rows; `ECE-10`; `ΔBrier = Brier(p) − Brier(recalibrated p)`
    where the map is fitted **only** on purged development origins.
  - **H0:** `β = 1` and `α = 0` (95% CI includes both) and `ΔBrier <= 0`.
  - **H1:** `β < 1` (overconfident) or `|α| > 0.5`, **and** `ΔBrier >= 0.0005` with CI
    excluding 0.
- **Prediction.** `β` 0.4–0.8 with negative `α`; `ΔBrier` +0.0003 to +0.001; AP
  unchanged (a monotone recalibration cannot change AP — report this as a check, not
  as a gain). Frozen anchors: ECE 0.004204 (rd_only) / 0.004395 (rd_fin), Brier
  0.014393 / 0.014349 vs constant-prevalence Brier 0.015119 → only weak probability
  skill, consistent with miscalibration.
- **Test procedure.** Re-run the driver to persist per-row holdout probabilities;
  compute `α`, `β` by logistic regression on W1–W3 with pair/company-cluster bootstrap;
  fit isotonic and Platt maps on purged development origins only; report reliability
  with **quantile** bins (not fixed 10-bin ECE at 1.5% prevalence, where most bins have
  0 positives) and ≥50 positives per reported bin or mark as not estimable.
- **Falsification condition.** `β` CI includes 1 and `ECE-10 <= 0.005` → no
  miscalibration to fix; `ΔBrier` CI includes 0 → recalibration does not help and the
  card is rejected. A change in AP under a supposedly monotone map is a bug, not a
  result.
- **Confounders / threats.** With 26 positives, isotonic regression overfits and the
  calibration slope is imprecise (need ≥50 events for stable calibration per Van
  Calster et al.); Brier is dominated by the negative class; averaging over overlapping
  windows inflates apparent calibration evidence; a "calibrated" model can still be
  useless (discrimination unchanged).
- **Status.** `PARTIAL` — Brier/ECE exist but no slope/intercept, no recalibration, and
  the 10-bin ECE at 1.5% prevalence is close to uninformative. No matured forecasts.
- **Evidence pointer.** `entry_metrics.json` → `holdout_window_summary`; 
  `research/STATE.json` "no forecast has matured"; `research/PREDICTION_PROTOCOL.md`
  §8.

---

## Card registry and kill conditions (summary)

| ID | Hypothesis | Primary estimand | Kill if (falsification) | Status |
|---|---|---|---|---|
| H-C2-1 | Coverage→power | median positives/origin, base rate, duplicate rate | positives <60, base rate <0.5%, dup ≥5% | UNTESTED |
| H-C2-2 | Entity-granularity ablation | ΔAP(P2−P1) | \|ΔAP\| ≤0.02 and same sign δ_pair | UNTESTED |
| H-C2-3 | Heterogeneity | G = AP(top) − AP(bottom) per stratification | all G ≤0.02 or adjusted CIs include 0 | PARTIAL |
| H-C2-4 | Matched-FAR lead time | ΔL at FAR*=0.05 | ΔL ≤0 or CI includes 0 at all FARs | UNTESTED |
| H-C2-5 | Underpowered null (MDE) | MDE₈₀ vs observed ΔAP | MDE₈₀ ≤ observed ΔAP ⇒ null is well-powered | UNTESTED |
| H-C2-6 | Signal resolution decision | ΔAP_P2 + MDE₈₀ | "still underpowered" (H1c) | UNTESTED |
| H-C2-7 | Calibration | calibration slope β, ΔBrier | β CI includes 1 and ECE ≤0.005 | PARTIAL |

**Programme-level discipline for this cycle.**
1. P1 reproduction is a hard gate: if any frozen number fails to reproduce, no P2 claim
   is reported until the harness defect is fixed.
2. Report per window **and** window mean; never select a window after the fact.
3. Every null gets an MDE (H-C2-5); every positive claim must survive the P1-vs-P2
   ablation (H-C2-2) and the cluster-aware CI (protocol §6).
4. Stratified analyses (H-C2-3) are pre-registered with multiplicity control and
   "not estimable" verdicts where positives < 10.
5. Calibration claims (H-C2-7) require matured forecasts; backtest calibration is
   reported as backtest calibration, never as a prospective track record.
6. Any card whose prediction was directionally wrong is recorded as refuted in
   `research/DECISIONS.md`; refutations are results, not failures to hide.

---

## Cycle-2 outcome (recorded by the Lead, 2026-11-02, after the run)

Written after the pre-registered analysis was executed once. Numbers are read from
`experiments/cycle2_coverage/REPORT.md` and `analysis.json`; nothing here re-estimates
them.

| ID | Verdict | Evidence |
|---|---|---|
| H-C2-1 | **REFUTED at the stated threshold, direction confirmed** | Positives per holdout window rise 25-27 (P1) to 41-53 (P2), i.e. ~1.7x, not the predicted >=60; candidate universe grows 1,716 -> 6,890 rows/window; base rate falls to 0.60-0.77% (inside the predicted 0.5-3% band); observed pairs 322 -> 634. The coverage→power mechanism is real but weaker than predicted because base rate falls as entities are added. |
| H-C2-2 | **PARTIAL — not a clean ablation** | P1 vs P2 ΔAP is +0.0564 vs +0.0973 and the inference changes from cluster-dependent to robust, but the panels also differ in *composition* (51 curated large parents vs 200 activity-ranked entities). A clean single-variable test needs acquisition chains (backlog B-020). |
| H-C2-3 | **NOT ESTIMABLE (failed as designed)** | The pre-declared firm-scale split is degenerate: all P1 rows fall in `lower_activity`, all P2 rows in `high_activity`, because the scale variable is endogenous to cohort selection. Mission question 6 remains open pending an exogenous scale measure (B-019). |
| H-C2-4 | **REFUTED (no lead-time advantage)** | At matched FAR the model detects +0.32/+0.30/+0.35 (P1) and +0.41/+0.43/+0.41 (P2) more positives than persistence, but the lead-time delta is negative in four of six windows (to −31 days). Detection advantage, not earlier warning. Reporting rule recorded as DECISIONS D-009. |
| H-C2-5 | **SUPPORTED as a statement about cycle 1** | Cycle-1 configuration: observed ΔAP 0.0564 < MDE80 0.0708, pair-cluster CI includes zero -> underpowered, not a licensed "no effect". Design-stage MDE for a 26-positive window is 0.3885, ~50x the +0.008 financial marginal. |
| H-C2-6 | **SUPPORTED branch H1a (signal resolvable on P2)** | P2 ΔAP +0.0973 with entity CI [+0.0426,+0.1697] and pair CI [+0.0491,+0.1583]; 3/3 windows exclude zero under both clusterings; observed ΔAP exceeds MDE 0.0877. Pre-registered support condition met on P2, not on P1. |
| H-C2-7 | **UNTESTED (still no matured forecast)** | Registry still reports insufficient_matured_forecasts; backtest calibration was not claimed as a prospective track record. |

**What the Lead changed in the plan because of this cycle.**
1. The default entry panel is now the entity cohort, not the curated roster.
2. Every future null must carry an MDE or it is not publishable (protocol §6, B-018).
3. The heterogeneity card is re-opened as a design problem (B-019), not a data problem.
4. "Earlier warning" is removed from the claim set until a lead-time advantage appears;
   the supported operational claim is "more true entries at the same false-alarm budget".
