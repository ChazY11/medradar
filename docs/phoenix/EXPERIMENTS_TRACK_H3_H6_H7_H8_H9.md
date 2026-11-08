# PHOENIX-001 — Track-level experiments: H3 / H6 / H7 / H8 / H9

> Protocol: `phoenix-001/v1` (`docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md`), **unmodified**.
> Harness: `experiments/phoenix/common/phoenix_common.py` v1.0.0, **unmodified**.
> Database: `data/medradar.sqlite`, SHA-256 `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92`
> (re-verified on every run, `sha256_matches_frozen = true`, `integrity_check = ok`).
> Task: `T-TRACK` (protocol §2.2). Headline lag `L090`; `L000`/`L180` re-run end to end.
> Seed `20261108` everywhere; bootstrap `B = 1000`, clustered by `track_id`.
> Branch: `research/phoenix-001-external-methods` (read-only work; no commits, no branch changes).
> All numbers below were read from `results/*.json`; no number is hand-computed or extrapolated.

Every hypothesis is reported whether or not it worked. **Three of the four predictive
hypotheses are negative**, and the one positive result (H8) is modest and is reported with
a placebo control.

---

## 0. Read this before any number: what is actually evaluable

The frozen T-TRACK panel is reproduced exactly (4904 rows, 59 tracks, 4255 labelled,
406 positives, prevalence **9.5417 %**), matching `reports/03_harness_smoke.json`. But the
walk-forward evaluation uses a much smaller subset, and this is the single most important
fact for interpreting everything below:

| quantity | all origins | walk-forward evaluable |
|---|---|---|
| rows | 4,255 | **2,443** |
| positives | 406 | **155** |
| prevalence | 9.5417 % | **6.3447 %** |
| period | 2004Q1–2024Q2 | 2014Q1–2024Q2 |

Why: the growth label needs four *forward* quarters, and `build_joint_panel` trims the frame
at `ORIGIN_END = 2025Q2`, so every origin after **2024Q2** carries `y = NaN`
(`results/audit_track.json → L5_overlap.last_labelable_origin`). Consequently **11 of the 12
folds are evaluable** and the 2025 fold is empty. The frozen holdout 2022Q1–2025Q2 is
therefore only observable through 2024Q2: `n = 590`, `n_pos = 31`.

**155 positives over 59 tracks.** A cluster bootstrap over 59 tracks with 155 positives has
very wide CIs. As a reference, the 95 % CI on B0's AP (a constant) is already
[0.0476, 0.1032] wide. AP differences below ~0.03 in this setup are noise unless the paired
bootstrap says otherwise — which is exactly what the paired tests below check.

---

## 1. Reproduction

Six commands, in order, from `experiments/phoenix/hypotheses/track/`. Measured from a
**clean cache** (cache/ deleted) on 2026-11-08: all exit 0, total **268 s**, no GPU, no
network, no new packages (pandas 3.0.3 / numpy 2.5.1 / scipy 1.18.1 / sklearn 1.9.1;
`ruptures` is *not* installed — PELT is implemented in `cp_methods.py`).

| # | command | wall | log |
|---|---|---|---|
| — | `python selftest.py` | 5.4 s | `evidence/00_selftest.log` |
| 1 | `python build_panel.py` | 26.6 s | `evidence/01_build_panel.log` |
| 2 | `python entrants_hhi.py` | 44.9 s | `evidence/02_entrants_hhi.log` |
| 3 | `python run_track.py` | 99.2 s | `evidence/03_run_track.log` |
| 4 | `python changepoint_bench.py` | 67.5 s | `evidence/04_changepoint_bench.log` |
| 5 | `python audit_track.py` | 24.6 s | `evidence/05_audit_track.log` |

Re-running the whole chain reproduces every statistic exactly (fixed seed; verified after a
clean-cache rebuild — only `elapsed_sec` and log timestamps differ). Self-tests: **17/17 PASS**
(`results/selftest.json`), including PELT recovering a synthetic step, CUSUM not firing on a
flat series, features at an origin being unchanged when all later events are deleted, and fold
boundaries being strictly ordered.

---

## 2. Arms (frozen before results were seen)

| arm | model | features |
|---|---|---|
| B0 | constant | training-fold prevalence |
| B1 | L2 logistic | own device history (trailing 1/2/4/8/12Q sums, cumulative, mean4, std8, acceleration, log4) + exposure |
| B2 | raw score | 8Q mean + linear-trend extrapolation over the next 4 quarters (protocol §4) |
| B5 | L2 logistic | all four source histories (510k, pma, trial, recall) + device + total + exposure (62 features) |
| H3 | B1 + | entrant features: entrants this quarter, trailing 4Q/8Q, cumulative, entrant share of active companies |
| H6 | B5 + | HHI: single-quarter (carried forward), pooled 4Q, Δ4Q, Δ8Q, pooled Δ4Q |
| H8 | B1 + | SciTrends-style growth: growth over 1/2/4/8Q, log-linear slope over 12Q, PMA share, volatility |
| H9 | L2 logistic per source | `F_dev` (510k+pma), `F_trial`, `F_recall`, `F_8k`, `F_fusion` |

All arms are fitted on the training folds only (imputer + scaler inside the training fold,
never on test), scored out-of-fold, and evaluated on **identical rows**, so every contrast is
paired. B2 is a raw ratio score: its Brier/calibration numbers are not probabilities and are
not interpretable (reported for completeness only).

---

## 3. H3 — Do entrants lead track-level growth?

**Pre-registered definition (§6 H3):** `T-TRACK`, `AP(B1 + entrant features) − AP(B1)` on the
holdout; supported iff **ΔAP ≥ 0.02 and paired p < 0.05**. Additional:
`corr(entrants_t, rate_{t+1..t+4})` with a permutation test and an explicit statement about
whether the association is only contemporaneous.

**n = 2,443, n_pos = 155, prevalence = 6.3447 %.**

### 3.1 Predictive arm

| arm | AP | 95 % cluster CI | ROC-AUC | P@10 % | lift@10 % | top-10 tracks/quarter |
|---|---|---|---|---|---|---|
| B1 persistence | 0.1234 | [0.0833, 0.1795] | 0.722 | 0.1434 | 2.261 | 0.1071 |
| **H3 = B1 + entrants** | **0.1411** | **[0.0869, 0.2083]** | 0.722 | 0.1803 | 2.842 | 0.1333 |
| B0 constant | 0.0728 | [0.0476, 0.1032] | 0.561 | 0.0492 | 0.775 | 0.0571 |

**Primary contrast: ΔAP = +0.0177, 95 % CI [−0.0150, +0.0462], raw paired-bootstrap
p = 0.2460.** The point estimate is *below* the pre-registered 0.02 threshold and the CI
straddles zero.

By lag scenario: `L000` ΔAP +0.0183 [−0.0117, +0.0441], p = 0.1940 · `L090` +0.0177, p = 0.2460 ·
`L180` +0.0234 [−0.0113, +0.0524], p = 0.1800 (this one crosses the 0.02 threshold but is not
significant, so it is INCONCLUSIVE, not support).

Stability (AP by 3-year block, H3 arm vs B1): 2014–16 0.157 vs 0.138 · 2017–19 0.190 vs 0.156 ·
2020–22 0.084 vs 0.074 · 2023–25 0.098 vs 0.089. Direction is consistent but the gaps (0.008–0.034)
are inside the noise band. Per-track AP: median 0.170 (p25 0.095, p75 0.249, 30 tracks with ≥1 positive).

### 3.2 Descriptive association — and the confound that explains it

`corr(entrants_t, rate_{t+k})`, event clock, rows from the quarter *after* each track's first
observed quarter (every incumbent is by definition an "entrant" in the first quarter, so that
quarter is excluded). Circular-shift permutation null within track, cluster bootstrap by track.

| k | single-quarter rate ρ | p_perm | forward-4Q rate ρ | p_perm |
|---|---|---|---|---|
| 0 | −0.073 | 1.000 | −0.105 | 0.115 |
| 1 | −0.104 | 0.008 | **−0.114** | **0.004** |
| 2 | −0.099 | 0.044 | −0.118 | 0.001 |
| 3 | −0.102 | 0.004 | −0.118 | 0.001 |
| 4 | −0.098 | 0.091 | −0.121 | <0.001 |

The raw association is **negative**, not positive, and it is *not* stronger at k = 0 than at
k = 1–4, i.e. it is not a "contemporaneous only" effect. But it is an artefact:

**Within-track high-pass control** (each track's own trailing-8Q mean removed from both
series): forward-4Q ρ at k = 0/1/2/3/4 = **+0.035 / −0.003 / −0.006 / −0.014 / −0.020**.
The association vanishes.

The mechanism is visible in `results/audit_track.json → calendar_confound_table`: company
entry is front-loaded in the single-snapshot 89-company registry (mean **1.379** entrants per
track-quarter in 2004, falling to **0.076** in 2025) while device volume rises over calendar
time (mean **4.18** device events per track-quarter in 2004 → **9.35** in 2017). A raw pooled
correlation therefore picks up "early calendar time" rather than a lead relationship.

> **H3 verdict: NOT SUPPORTED.** Predictive ΔAP 0.0177 (< 0.02), p = 0.2460. The descriptive
> association is *negative* and disappears under a within-track calendar control, so it does
> not support "entrants lead growth" either.
> Evidence class: **S** for the predictive arm, **R** for the association analysis.

---

## 4. H6 — Does track concentration (HHI) explain or predict subsequent diffusion?

**Pre-registered definition (§6 H6):** test 1 = `Spearman(ΔHHI_{t−4→t}, ΔHHI_{t→t+4})` with a
cluster-bootstrap CI; test 2 = `AP(B5 + HHI) − AP(B5)` on the holdout. Supported iff
**ΔAP ≥ 0.02 and p < 0.05 AND the test-1 CI excludes 0**.

**n = 2,443, n_pos = 155, prevalence = 6.3447 %.**

### 4.1 Test 2 — incremental prediction

| arm | AP | 95 % CI | ROC-AUC | P@10 % | top-10 tracks/quarter |
|---|---|---|---|---|---|
| B5 full | 0.1434 | [0.1004, 0.2168] | 0.776 | 0.1475 | 0.1429 |
| **H6 = B5 + HHI** | **0.1567** | **[0.1057, 0.2321]** | 0.783 | 0.1639 | 0.1548 |

**Primary contrast: ΔAP = +0.0133, 95 % CI [−0.0014, +0.0329], raw p = 0.0820.** Below the
0.02 threshold and not significant. By lag: L000 +0.0045 (p = 0.690) · L090 +0.0133 (p = 0.082) ·
L180 +0.0130 (p = 0.066). Stability: 0.192/0.154/0.146/0.161 for H6 vs 0.182/0.140/0.115/0.134
for B5 — consistently a little better, but the pooled gain is smaller than the threshold.

### 4.2 Test 1 — descriptive association

`Spearman(ΔHHI_{t−4→t}, ΔHHI_{t→t+4}) = **−0.4419**, 95 % cluster CI [−0.4776, −0.4110],
p_boot < 0.001, n_pairs = 3,380 over 56 tracks (8Q-window sensitivity: −0.4042).

The CI excludes zero, so **test 1 technically passes** — but the sign is negative, which is
what a noisy, mean-reverting concentration series produces mechanically (an above-average HHI
change is followed by a below-average one). It is a statement about mean reversion in a
single-quarter event-share index, not evidence that concentration "explains subsequent
diffusion".

> **H6 verdict: NOT SUPPORTED.** Test 2 fails (ΔAP 0.0133 < 0.02, p = 0.0820); test 1 passes
> but with a negative, mean-reverting sign that does not support the hypothesis's direction.
> Evidence class: **S** for the predictive arm, **R** for the association test.

---

## 5. H7 — Change-point detection vs a fixed threshold (controlled simulation)

**This is the only controlled experiment in the round. It proves detector properties under a
known ground truth. It is NOT evidence that real medical-technology history contains
detectable change points.** Evidence class: **method research**, not D/R/S.

Design exactly as §6 H7: the 30 tracks with the most device events; real quarterly series
2004Q1–2025Q2 (86 quarters); a step change injected at τ ~ Uniform{12,…,74}; multiplier
m ∈ {1.5, 2.0, 3.0} applied to a 4-quarter moving-average baseline of the real series; noise
negative binomial with a per-track size parameter estimated from residuals to that 4Q moving
average (**16/30 tracks negbin, 14/30 Poisson fallback**, median r = 32.8; Poisson when the
moment estimate was unstable ≤ 0 or > 200 — recorded per track in `per_track_inputs`);
**200 replications per (track, m)** plus matched no-change null series with the same τ draws.
**24,000 series** (6,000 null + 18,000 injected), actual runtime **66.7 s**.

Detectors, all self-implemented in `cp_methods.py`:
(a) fixed threshold `y_t > k × trailing-8Q mean` (Laplace-smoothed so it stays tunable);
(b) standardised CUSUM k = 0.5 with NB/Poisson standardisation and reset on alarm;
(c) **PELT** with a Poisson segment cost and a BIC-style penalty `λ·log n` (exact recursion,
PELT pruning; no library);
(d) SciTrends-style growth threshold `(last 4Q + 1)/(previous 4Q + 1) − 1 > θ`.

Detection = at least one alarm within **±2 quarters** of τ; delay = first such alarm − τ.
Every detector was **tuned on the null series to the most sensitive setting with a
false-alarm rate ≤ 5 % per quarter** before any change series were touched.

### 5.1 Tuning table (this is what makes the comparison fair)

| detector | tuned parameter | FA / quarter at tuning | null detection within ±2Q | protocol-literal parameter | FA / quarter there | over budget? |
|---|---|---|---|---|---|---|
| fixed threshold | k = **2.60** | 4.68 % | 0.189 | k = 2.0 | **10.62 %** | **YES (2.1×)** |
| growth threshold | θ = **1.25** | 4.85 % | 0.148 | θ = 0.50 | **16.78 %** | **YES (3.4×)** |
| CUSUM | h = **3.50** | 4.49 % | 0.216 | h = 5.0 | 2.56 % | no |
| PELT | λ = **1.00** | 4.81 % | 0.227 | λ = 1.0 | 4.81 % | no |

The null floor is the key reference: at a 5 %/quarter budget a detector fires somewhere in a
5-quarter window by chance ≈ 1 − 0.95⁵ = 22.6 % of the time, and the measured null
within-window detection is 0.15–0.23. Detection rates must be read against that floor, not
against zero. PELT's tuned penalty happens to coincide with the protocol-literal λ = 1.0.

### 5.2 Detector comparison at the matched false-alarm budget

| detector | m = 1.5 | m = 2.0 | m = 3.0 | **pooled (18,000 series)** | Δ vs fixed [95 % CI] | p | median delay (m=2) |
|---|---|---|---|---|---|---|---|
| fixed threshold | 0.325 | 0.559 | 0.880 | **0.5881** | — | — | 0 (IQR 0–1) |
| growth threshold | 0.220 | 0.358 | 0.680 | **0.4196** | −0.1685 [−0.179, −0.158] | <0.001 | 1 (0–2) |
| CUSUM | 0.501 | 0.733 | 0.907 | **0.7136** | **+0.1254 [+0.0584, +0.1941]** | <0.001 | 0 (0–1) |
| PELT | 0.501 | 0.736 | 0.904 | **0.7138** | **+0.1257 [+0.0523, +0.2021]** | 0.002 | 0 (0–0) |

At the *protocol-literal* settings the ordering reverses — but only because two of those
settings are far over the false-alarm budget:

| detector (literal) | FA / quarter | pooled detection |
|---|---|---|
| fixed, k = 2.0 | 10.62 % | 0.810 |
| growth, θ = 0.50 | 16.78 % | 0.787 |
| CUSUM, h = 5.0 | 2.56 % | 0.615 |
| PELT, λ = 1.0 | 4.81 % | 0.714 |

So the naive reading "the fixed threshold is better (0.81 vs 0.62)" is an artefact of it
firing **more than twice as often** as the budget allows. The pre-registered rule requires the
matched-budget comparison, and there PELT and CUSUM both beat it by ~12.5 percentage points.

### 5.3 Where each detector wins (matched budget, detection rate by track-size tercile)

| tercile | fixed | growth | CUSUM | PELT |
|---|---|---|---|---|
| small (10 tracks) | **0.652** | 0.498 | 0.560 | 0.533 |
| medium (10) | 0.580 | 0.405 | 0.721 | 0.738 |
| large (10) | 0.532 | 0.356 | 0.859 | 0.871 |

The fixed ratio threshold is actually the best detector on the *smallest* tracks and the worst
on the largest. A practical recommendation follows: use the cheap fixed threshold where counts
are tiny, and a change-point detector where volume is sufficient for standardisation to be
informative. Delay is ≤1 quarter for every detector that fires (PELT is tightest, IQR 0–0).

> **H7 verdict: SUPPORTED** (protocol rule: ≥1 change-point detector beats the fixed threshold
> by ≥10 pp at the matched budget with a CI excluding 0). PELT +0.126 [+0.052, +0.202],
> p = 0.002. **Interpretation is strictly conditional:** the win holds only once the false-alarm
> budgets are equalised; at the protocol's literal thresholds the fixed detector is more
> sensitive and far more false-alarm prone.
> Evidence class: **method research / controlled simulation — not D/R/S history evidence.**

---

## 6. H8 — Do SciTrends-type growth features transfer to medical-device events?

**Pre-registered definition (§6 H8):** `AP(B1 + growth features) − AP(B1)` on the holdout;
supported iff **ΔAP ≥ 0.03 and p < 0.05**. Growth features (independently implemented, not the
authors' code): multi-window growth 1/2/4/8Q, log-linear 12Q slope, PMA share of device events
as a "high-barrier share" analogue, acceleration (already in B1), volatility.

**n = 2,443, n_pos = 155, prevalence = 6.3447 %.**

| arm | AP | 95 % CI | ROC-AUC | P@10 % | lift@10 % | top-10 tracks/quarter |
|---|---|---|---|---|---|---|
| B1 persistence | 0.1234 | [0.0833, 0.1795] | 0.722 | 0.1434 | 2.261 | 0.1071 |
| **H8 = B1 + growth** | **0.1613** | **[0.1187, 0.2095]** | 0.798 | 0.1762 | 2.778 | **0.1690** |

**Primary contrast: ΔAP = +0.0379, 95 % CI [+0.0115, +0.0618], raw paired-bootstrap
p = 0.0040.** This is the only predictive hypothesis that clears its threshold.

Robustness (all from the same JSON):

| check | H8 arm | B1 | result |
|---|---|---|---|
| L000 (nominal clock) | 0.1745 (p = 0.010) | 0.1395 | holds |
| L090 (headline) | 0.1613 (p = 0.004) | 0.1234 | holds |
| L180 (stress) | 0.1632 (p = 0.036) | 0.1275 | holds |
| 2014–16 | 0.185 | 0.138 | better |
| 2017–19 | 0.197 | 0.156 | better |
| 2020–22 | 0.101 | 0.074 | better |
| 2023–25 | 0.230 | 0.089 | better |
| non-overlapping Q1-only origins (n=640) | 0.175 | 0.143 | better |
| holdout 2022Q1–2024Q2 (n=590, 31 pos) | 0.159 | 0.081 | better |
| **placebo: growth features shuffled across tracks within each quarter** | **0.1191** | 0.1234 | **collapses to ≈ B1** (real 0.1613 → placebo 0.1191) |

Per-track AP: median 0.218 (p25 0.125, p75 0.328). Calibration slope is 0.418 — the arm ranks
well but its probabilities are not calibrated (true of every arm here; the task is ranking).

Leakage sanity: the maximum absolute single-feature correlation with the label across **all 79
model features is 0.2729** (`sct_volatility8`); nothing is near the 0.80 screen
(`audit_track.json → L1`). The placebo collapses the arm to the B1 level, so the gain is
carried by track-specific, time-aligned information rather than by how the arm is wired.

> **H8 verdict: SUPPORTED** (ΔAP 0.0379 ≥ 0.03, p = 0.0040). The effect is **modest** — about
> 4 AP points, right at the edge of the noise band this sample can resolve — but it is
> direction-consistent across all three lag scenarios, all four 3-year blocks, the
> non-overlapping sensitivity, the holdout, and it survives a placebo control.
> **Not** a reproduction of SciTrends accuracy: the target, domain and frequency are different,
> and the patent leading-indicator component is untestable (no patent data in the database).
> Evidence class: **S**.

---

## 7. H9 — Is fusing data sources better than the strongest single source?

**Pre-registered definition (§6 H9):** `AP(F_fusion) − max_s AP(F_s) ≥ 0.02` and paired
p < 0.05; counter-evidence condition: if the strongest single source is already ≥ 90 % of
fusion, state "no material fusion gain". Per-source-window reporting is required.

### 7.1 A hard data fact that changes the design

The frozen DB contains 20,976 `8k_catalyst` events, and **not one of them carries a
`track_id`** (`results/entrants_hhi_summary.json → source_coverage`: `8k_catalyst` 0/20,976
with a track; `drug_approval` 0/2,678; `510k` 40,196/70,796; `pma` 37,553/46,008; `trial`
30,983/54,811; `device_recall` 39,656/58,567). **`F_8k` is therefore not constructible at
track level** — this is not a time-coverage issue (the 8k series starting 2015), it is a total
absence of track attribution. The pre-registered five-arm design is run with the four
constructible arms (`F_dev`, `F_trial`, `F_recall`, `F_fusion`). This deviation was decided
from the schema before any model was fitted and is recorded in `results/h9_fusion.json`.

Because the three constructible sources all cover the same 2004–2025 window, there is no
source-availability window to stratify on; AP by 3-year block is reported instead.

### 7.2 Results

| arm | AP | 95 % CI | ROC-AUC | top-10 tracks/quarter (42 quarters) |
|---|---|---|---|---|
| `F_dev` (510k + pma) | **0.1454** | [0.0936, 0.2320] | 0.740 | 0.1405 |
| `F_trial` | 0.0927 | [0.0615, 0.1293] | 0.684 | 0.1000 |
| `F_recall` | 0.0970 | [0.0612, 0.1535] | 0.643 | 0.0929 |
| `F_8k` | **UNAVAILABLE** | — | — | — |
| `F_fusion` (dev+trial+recall) | 0.1404 | [0.0912, 0.2218] | 0.755 | 0.1190 |

**Primary contrast: `AP(F_fusion) − AP(F_dev)` = −0.0050, 95 % CI [−0.0360, +0.0172],
raw p = 0.6280.** Same conclusion at every lag: L000 +0.0074 (p = 0.846), L090 −0.0050
(p = 0.628), L180 −0.0035 (p = 0.734).

Fusion/best-single ratio = 0.1404 / 0.1454 = **0.966**, so the pre-registered counter-evidence
condition is met: **no material fusion gain**.

By era (AP): 2014–16 dev 0.185 / fusion 0.182 · 2017–19 0.154 / 0.137 · 2020–22 0.094 / **0.127** ·
2023–25 0.100 / **0.132**. Fusion adds nothing in the early eras and is *better* in the two most
recent blocks — but that is 28 and 22 positives respectively, and the pooled contrast is zero.

> **H9 verdict: NOT SUPPORTED.** Fusion does not beat the strongest single source (ΔAP −0.0050,
> p = 0.628), and the fusion-to-single ratio of 0.966 triggers the pre-registered "no material
> fusion gain" statement. The event data (510k+pma) carries essentially all of the signal; trial
> and recall histories add nothing on top of it.
> Evidence class: **S**.

---

## 8. Cross-cutting validity audit (protocol §7)

Every number below is from `results/audit_track.json`.

| item | result |
|---|---|
| **L1** label-leak screen | max \|corr(feature, y)\| over 79 features = **0.2729** (`sct_volatility8`). Nothing above 0.80; `suspected_label_leak = []`. |
| **L2** future information | **PASS.** Delete every event whose feature quarter is after the origin, rebuild the panel: features at the origin are identical at 2012Q3 and 2018Q2 (`max_abs_diff = 0.0e+00`, no column differs, 58–59 tracks compared). Also asserted in `selftest.py`. |
| **L3** entity mapping | 2 `applicant_raw` → multiple `company_key` conflicts (Johnson & Johnson Vision Care / Surgical Vision). `company_key` unavailability by kind: 510k 81.97 %, pma 29.25 %, trial 30.50 %, recall 51.27 %, 8k 93.52 %. This is a **coverage restriction built into the frozen entity universe**, applied equally to features and labels — not a leak. |
| **L4** left truncation | exposure_q mean 41.6, median 41, min 0, max 85. Share of **labelled** rows with exposure_q < 8 = **1.39 %** — exactly 59 rows (one per track) at exposure_q = 7; the 8Q trailing window makes `y` undefined below that, so they are not excluded by any post-hoc filter. |
| **L5** sample overlap | 4,255 all origins / 406 positives; 2,443 evaluable / 155 positives; Q1-only non-overlapping subset 640 / 46. Consecutive origins share 3 of 4 forward quarters; a Q1-only sensitivity is reported for every arm. Last labelable origin **2024Q2** (the 2025 fold is empty). |
| **L6** duplicates | 7,572 groups share (company_key, track_id, product_code, event_date). Counted, not removed — mostly legitimate distinct submissions; the label only asks whether *any* device event occurred in the forward window. |
| **L7** track anachronism | 2 of 59 tracks first appear at/after 2014 (`aesthetics` 2015-03-30, `t_gene_therapy` 2018-05-11). Every evaluable origin is 2014Q1 or later, so no evaluable row can predate its track's first observed event; the residual risk is confined to track labelling of pre-2014 training rows. |
| **L8** single snapshot | Not correctable — `available_at == event_date` for all rows. This is why the headline is `L090`, a conservative lag *we* inject, and why no result here is class **P**. |

Additional controls specific to this task: the **H8 placebo** (§6), the **H3 within-track
high-pass calendar control** (§3.2), and the **H7 matched false-alarm budget** (§5.1).

---

## 9. Verdict summary

| hypothesis | primary contrast (L090) | 95 % CI | raw p | verdict | evidence class |
|---|---|---|---|---|---|
| **H3** entrants lead growth | ΔAP +0.0177 | [−0.0150, +0.0462] | 0.2460 | **NOT SUPPORTED** | S (predictive), R (association) |
| **H6** HHI predicts diffusion | ΔAP +0.0133 | [−0.0014, +0.0329] | 0.0820 | **NOT SUPPORTED** | S / R |
| **H7** change-point > fixed threshold | Δdetection +0.126 (PELT) | [+0.052, +0.202] | 0.0020 | **SUPPORTED** (conditional on matched FA budget) | method research only |
| **H8** SciTrends growth features | ΔAP +0.0379 | [+0.0115, +0.0618] | 0.0040 | **SUPPORTED** (modest) | S |
| **H9** source fusion | ΔAP −0.0050 | [−0.0360, +0.0172] | 0.6280 | **NOT SUPPORTED** (no material gain) | S |

p-values are **raw and unadjusted** (paired cluster bootstrap, two-sided) so the Lead can
Holm-combine them across the whole program. For information, Holm over these five track-level
tests alone (raw p: H7 0.002, H8 0.004, H6 0.082, H3 0.246, H9 0.628) gives
H7 **0.010**, H8 **0.016**, H6 0.246, H3 0.492, H9 0.628 — unchanged at the 5 % level.
This is *not* the program-level correction, which is the Lead's to compute.

---

## 10. What is *not* claimed

1. **No result here is class P.** The database is a single 2026-10-30 snapshot with
   `available_at == event_date`; the lag is injected by us. Highest class is S.
2. **H7 proves nothing about history.** It is a controlled simulation with a known step
   change. It says which detector is better *if* a step change exists, not that any real track
   has one.
3. **H8 is not a SciTrends replication.** Different target, domain, frequency; the patent
   leading indicator is untestable here. 4 AP points on 155 positives is a small effect.
4. **H3's descriptive correlation is a calendar artefact**, not a lead relationship — see §3.2.
   One must not quote the raw −0.11 without the high-pass control.
5. **H6 test 1's CI excludes zero, but the sign is negative** (mean reversion). That is not
   evidence for the hypothesis's direction.
6. **B2's Brier score and calibration slope are meaningless** (raw ratio score, not a
   probability).
7. **155 positives / 59 tracks.** Everything is uncertain; the CIs are reported so this is
   visible rather than hidden.

## 11. Files

Code (`experiments/phoenix/hypotheses/track/`): `track_common.py` (panel, features, H3/H6
descriptive statistics, logging), `cp_methods.py` (PELT, CUSUM, thresholds), `build_panel.py`,
`entrants_hhi.py`, `run_track.py`, `changepoint_bench.py`, `audit_track.py`, `selftest.py`.

Results (`results/`): `panel_facts.json`, `entrants_hhi_summary.json`, `track_all_metrics.json`,
`primary_tests.json`, `h3h6_descriptive.json`, `h3_entrants.json`, `h6_hhi.json`,
`h7_changepoint.json`, `changepoint_bench.json`, `h8_scitrends.json`, `h9_fusion.json`,
`audit_track.json`, `selftest.json`.

Logs (`evidence/`): `00_selftest.log` … `05_audit_track.log` (real stdout/stderr with
wall-clock timestamps and exit codes).

Cache (`cache/`, rebuildable, not a deliverable): `track_panel_L{000,090,180}.pkl`,
`entrants_hhi_L{000,090,180}.csv`.
