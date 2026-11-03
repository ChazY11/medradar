# S-028 独立统计复核与修正 / Independent Statistical Review & Correction

**Study:** S-028 — Relational early signals in medical technology development (temporal graph)
**Branch:** `research/s028-temporal-graph-early-signal` (PR #15, draft)
**Reviewer:** independent statistical review (this file is new; the historical reports
`STATISTICAL_VALIDATION.md` and `PHASE_REPORT_ZH.md` are **not** edited — they are
cross-referenced below and remain part of the record).
**Evidence:** `artifacts/correction_round_1/stats_audit_original.json` (machine-readable
audit of every recomputed number vs its original counterpart) and
`artifacts/correction_round_1/stats_corrected_original.json` (corrected pipeline on the
original stored predictions). Code: `code/audit_21_statistics.py`,
`code/s028_stats_corrected.py`. No model was refitted; no original artifact or code file
was modified.

> **Tag vocabulary used below:** `ORIGINAL_RESULT` (reproduced as reported),
> `CORRECTED_RESULT` (recomputed differently), `UNCHANGED_FINDING` (conclusion survives
> the re-derivation), `INVALIDATED_FINDING` (must not be used), `UNRESOLVED_LIMITATION`.
>
> All line numbers were taken at audit time (2026-11-04, ~02:45 +08:00). The frozen code
> files (`s028_stats.py`, `s028_lib.py`, `s028_experiment.py`) and artifacts were not
> modified by this review. Some narrative documents (e.g. `PHASE_REPORT_ZH.md`) may be
> updated concurrently by the Lead; line references in those files are approximate.

---

## 0. Executive summary

| # | reported claim | status | corrected statement |
|---|---|---|---|
| 1 | pooled ΔAP = −0.00609, company CI [−0.02219,+0.00450], pair CI [−0.03347,+0.01043] | `ORIGINAL_RESULT` (exactly reproduced) | Fine as a finite-population cluster interval for the *pooled triplicated-row* estimand; coverage simulation ≈95% (§2). |
| 2 | MDE(80%) = 0.01943 = 2.801585 × bootstrap SE | `CORRECTED_RESULT` | Arithmetic correct, but it is the *pooled-test only* and *post hoc* MDE; quantile-bootstrap version 0.01971, jackknife version 0.01091, pair-clustered 0.0297–0.0351. **The pre-registered compound rule's MDE is ≈0.0374 AP (49.8 % of the baseline AP 0.0751), and its power at 0.0194 is only ≈16 %.** |
| 3 | "NULL (well-powered)" | `INVALIDATED_FINDING` (label) | The label is nearly a tautology (§5): a CI that contains 0 automatically satisfies |ΔAP| < MDE. Replace with an explicit power statement (§8). |
| 4 | "no network effect exists" | `INVALIDATED_FINDING` (never licensed) | Only "no detectable incremental signal"; gains up to ≈0.010 AP (13.9 % of baseline, pair-clustered) are not excluded, and gains below ≈0.019 (pooled) / ≈0.037 (rule) are not reliably detectable. |
| 5 | "40/40 randomisations beat the real graph" | `INVALIDATED_FINDING` (method) | Given the broken randomised null model this cannot be used. Independently, 40 draws only resolve one-sided tails to 1/41 = 0.0244; and under a valid null "real below all randomisations" means the real arrangement is *atypical*, **not** that random relations have predictive value (§4). **Corrected-G2 re-derivation (§12): H4q 40/40 null draws ≥ real for N1 and N2 (p(real>random)=1.0; reverse tail p=1/41=0.0244) → H2 NOT SUPPORTED; H2q 16/40 (N1) / 20/40 (N2) → NOT SUPPORTED, inconclusive.** |
| 6 | BH q=0.10 over the pre-registered family, 0/8 rejections | `UNCHANGED_FINDING` (conclusion) + code `BUG` | Correct step-up also rejects nothing (min p = 0.1895). The pointwise implementation is conservative, the printed `bh_threshold`s are mis-assigned, and the tested family is not the pre-registered one (§3). |
| 7 | H4 conditional effects undeterminable; 6/38 tracks + 5/51 companies reportable | `UNCHANGED_FINDING` (strengthened) | Counts reproduce, but they are inflated ∼3× by overlapping-window triplication; on unique pairs **0/38 and 0/51** strata qualify (§6). |
| 8 | 0/3 holdout windows exclude 0 | `UNCHANGED_FINDING` | Verified against stored per-window CIs. |

**Bottom line.** The narrow empirical claim — *G1 did not improve out-of-sample AP over the
strong non-graph B2 baseline, and no window/clustering/estimator variant shows evidence of
improvement* — is `UNCHANGED_FINDING` and defensible. The surrounding claims — "well-powered",
"random relations are informative", the numerical MDE as a design guarantee, and the BH table
as a pre-registered correction — are `INVALIDATED_FINDING` or `CORRECTED_RESULT`.

---

## 1. MDE: what formula was used, what it means, and what was actually powered

### 1.1 The formula that was used

`code/s028_stats.py` line 33 and `code/s028_lib.py` line 803:

```
MDE_Z = z_{0.975} + z_{0.80} = 1.959964 + 0.841621 = 2.801585
mde_80 = MDE_Z * SE_bootstrap(ΔAP)          # s028_lib.py line 854
```

Reproduced exactly: H4q company `0.01942800955574231 / 0.006934649334481127 = 2.801585`;
H2q company `0.04365763797760765 / 0.015583192363468409 = 2.801585`. `ORIGINAL_RESULT`.

This is the standard normal-theory minimum detectable effect for a two-sided 5 % test with
80 % power **when the SE is known and the estimator is approximately normal**:

```
power(δ) = Φ(δ/SE − 1.96) + Φ(−δ/SE − 1.96)   ⇒   power(2.8016·SE) = 0.80.
```

### 1.2 Why a normal-theory MDE is not defensible here

1. **Bounded, skewed, non-pivotal statistic.** ΔAP ∈ [−1, 1] and AP itself is a ratio of
   discrete rank statistics on ~5,000 rows / 51 clusters. The percentile bootstrap
   distribution of ΔAP is strongly skewed: H4q company skewness −1.76, H4q pair −0.93,
   H2q company **+2.89** with bootstrap bias **+0.0050**. The normal-theory MDE is a
   *location-shift/asymmetry-free* approximation; it is not the power of the percentile-CI
   test actually used. `CORRECTED_RESULT`.
2. **The SE is estimated, not known.** With only 51 company clusters the SE is itself
   noisy, and the choice of variance estimator changes the MDE by a factor >1.5:
   - H4q company: bootstrap SE 0.006935 → MDE 0.01943; delete-one-company jackknife
     SE 0.003818 → MDE(t) 0.01091; quantile-bootstrap MDE 0.01971.
   - H4q pair: bootstrap SE 0.010612 → MDE 0.02973; jackknife SE 0.006792 → 0.01904;
     quantile-bootstrap MDE 0.03507.
   - H2q company: bootstrap MDE 0.04366 vs jackknife 0.02704 vs quantile 0.01473 — the
     three "MDEs" differ by 3× because the bootstrap distribution is pathological.
   `CORRECTED_RESULT`.
3. **The MDE is post hoc.** The *method* is pre-registered (`PRE_REGISTRATION.md` §10.4,
   lines 198–199: "以 bootstrap 的 ΔAP 标准误反推 80% 功效下的最小可检测效应"), but the exact
   constant 2.8016 appears only in `EXPERIMENT_PROTOCOL.md` line 75, which is **not**
   included in `artifacts/prereg_freeze*.json`, and the number was computed from the
   realised bootstrap SE after every prediction existed (`predictions_H4q.json.gz`
   mtime 2026-11-04 01:54:49; `statistical_validation.json` 01:57:14). It is therefore an
   observed-data estimate, not a design-stage power guarantee. `CORRECTED_RESULT`.
4. **MDE ≠ exclusion bound.** Detection and exclusion are different: the 95 % CI *upper*
   bound is the exclusion statement (H4q: +0.00450 company, +0.01043 pair). Statements
   such as "可排除 >0.019 AP 的收益" (`HYPOTHESIS_REGISTRY.md` line 21,
   `PHASE_REPORT_ZH.md` line 262) confuse the two: the study's own 95 % pair-clustered CI
   excludes gains *larger than ≈0.0104*, not ≈0.019. `CORRECTED_RESULT`.
5. **The wrong test.** The pre-registered H1 verdict is a **conjunction**
   (`PRE_REGISTRATION.md` §11): (a) ≥2 of 3 windows' company CI excludes 0, (b) pooled
   company **and** pair CIs exclude 0, (c) point estimate ≥ MDE. The reported 0.01943 is
   the MDE of the pooled company test alone. `CORRECTED_RESULT`.

### 1.3 Corrected MDEs and power (H4q, baseline AP = 0.075093)

| quantity | value | note |
|---|---:|---|
| reported normal-theory MDE | **0.019428** | = 2.801585 × 0.006935; 25.9 % of baseline |
| skew-aware quantile-bootstrap MDE | **0.019712** | power(δ)=P(δ+E > −q₀.₀₂₅(E)); power at the reported MDE = **0.784** < 0.80 |
| delete-one-company jackknife MDE | **0.010909** | t-quantile version, SE 0.003818 |
| pair-clustered quantile-bootstrap MDE | **0.035071** | power at the reported pair MDE = 0.630 |
| **rule-level MDE (80 %, pre-registered compound rule)** | **0.037365** | **49.8 % of baseline AP** |
| **power of the actual rule at δ = 0.019428** | **0.1625** | components: ≥2/3 windows 0.196; both clusterings 0.419; point ≥ MDE 0.498 |

H2q (secondary, baseline AP = 0.067350): reported MDE 0.043658 (64.8 % of baseline);
quantile 0.014728; jackknife 0.027040; rule-level MDE **0.058668 (87.1 % of baseline)**,
rule power at the reported MDE 0.437. The three pooled MDEs differ wildly because the H2q
company bootstrap is right-skewed with a +0.005 bias — **none of them should be quoted as
"the" MDE**; report the range and the CI instead. `CORRECTED_RESULT` /
`UNRESOLVED_LIMITATION`.

### 1.4 What effect sizes could not be ruled out

- At 95 % (two-sided), pair-clustered CI upper bound **+0.010428** ⇒ improvements larger
  than ≈0.0104 AP (**13.9 %** of baseline AP) are excluded; improvements **up to ≈0.0104
  are not excluded** (company-clustered: up to +0.0045, 6.0 %).
- The pooled test has 80 % power only at **≈0.0194 AP (25.9 %)**; the study's own
  pre-registered decision rule needs **≈0.0374 AP (49.8 %)** for 80 % power.
- Therefore the honest conclusion is: *no detected incremental signal; the data are
  consistent with no effect, but also with small-to-moderate positive effects, and the
  study is not well-powered for its own pre-registered rule.*
- Tag: `CORRECTED_RESULT`; the phrase "no network effect exists" is
  `INVALIDATED_FINDING`.

---

## 2. Bootstrap: clustering unit, overlapping windows, duplication, p-value semantics

### 2.1 What `paired_cluster_bootstrap` does (`s028_lib.py` lines 800–857)

- concatenates the three holdout windows into one flat row set (5159 rows for H4q);
- resamples whole clusters with replacement — `companies` (line 817) or `pairs`;
- re-scores both models on the same resampled rows (paired difference);
- returns the percentile 2.5/97.5 interval (line 849), `SE` (848),
  `mde_80 = 2.8016·SE` (854), `p_one_sided = mean(draws ≤ 0)` (855).

`ORIGINAL_RESULT` (all stored numbers reproduce exactly with seed 7/2000 resamples).

### 2.2 Overlapping windows duplicate rows and events (`BUG-BOOT-1`)

The three holdout origins are consecutive quarters with a 4-quarter label horizon, so the
label periods overlap by up to 3 quarters:

| fact (H4q) | value |
|---|---:|
| pooled rows | 5,159 |
| distinct company–track pairs | **1,729** |
| row multiplicity per pair | {3: 1,709; 2: 12; 1: 8} |
| positive rows | 67 |
| **distinct positive pairs (effective events)** | **32** |
| pairs positive in one window and negative in another | **13** |
| pooled AP (0.06900) vs mean of window APs (0.07858) | lower |

Consequences (`CORRECTED_RESULT`):
- The pooled AP is not a proper out-of-sample ranking metric: the same pair can enter the
  positive side (window 2025-07) and the negative side (window 2025-04) with nearly equal
  predicted probabilities, depressing pooled AP relative to per-window AP. The estimand is
  "AP of a triplicated mixed-window row set", not "AP at a holdout origin".
- Because pair-cluster resampling keeps all rows of a pair together (and company resampling
  keeps all rows of a company), the *coverage* of the finite-population estimand is not
  compromised per se (simulation below ≈95 %), but the **effective number of independent
  positive events is ≈32, not 67**, so precision/MDE statements built on "67 positives"
  overstate the information content.
- The negative point estimate is **not robust**: dropping the overlap and keeping one row
  per pair gives ΔAP = **+0.000623** (first window) or **−0.016894** (last window)
  (`DISCREPANT`). "G1 is worse than B2" must not be claimed; "no improvement detected"
  is the defensible statement.

### 2.3 What `p_one_sided = mean(draws ≤ 0)` actually measures (`BUG-BOOT-2`)

It is the **one-sided percentile-bootstrap tail probability** P\*(ΔAP\* ≤ 0), i.e. a
bootstrap approximation of P(Δ̂ ≤ 0 | data). It is *not* P(H₀ | data), it is not a
posterior probability, and it is not the statistic the decision rule uses (which is a
two-sided 95 % CI). It is asymptotically a one-sided p-value only if the bootstrap
distribution is approximately pivotal/symmetric:

| test | reported p | normal-theory 1−Φ(Δ/SE) | bootstrap skew |
|---|---:|---:|---:|
| H4q company | 0.8935 | 0.8104 | −1.76 |
| H2q company | 0.4590 | 0.5080 | **+2.89** |

For H4q the skew moves the bootstrap p by 0.083 relative to the normal approximation; for
H2q the bootstrap distribution is biased +0.005 and has a 5.2× asymmetric CI. The p-values
are also fed into BH (see §3) even though the verdict is CI-based — internally inconsistent
inference. `CORRECTED_RESULT`.

### 2.4 Resampling clusters while concatenating duplicated rows (`BUG-BOOT-3`)

- Resampling a cluster twice duplicates all its rows exactly, creating tie blocks that
  `fast_ap` collapses; for a rank statistic this changes the effective weighting.
- The result is estimator-dependent: bootstrap vs delete-one-cluster jackknife SE ratios
  are **1.82×** (H4q company) and **1.56×** (H4q pair); jackknife CIs are much narrower:

| scheme (H4q) | 95 % CI | SE | MDE(80 %) |
|---|---|---:|---:|
| company, percentile bootstrap (reported) | [−0.022187, +0.004500] | 0.006935 | 0.019428 |
| company, delete-one jackknife t (df 50) | [−0.013758, +0.001579] | 0.003818 | 0.010909 |
| pair, percentile bootstrap (reported) | [−0.033468, +0.010428] | 0.010612 | 0.029729 |
| pair, delete-one jackknife t (df 1728) | [−0.019411, +0.007232] | 0.006792 | 0.019039 |
| company seed-averaged (5 seeds) | [−0.025219, −0.021319] ∪ [+0.003693, +0.005714] endpoints | 0.00655–0.00747 | — |
| equal-weight mean over windows (company bootstrap) | [−0.032386, +0.007312] (p=0.8405) | — | — |

- The windows are **not resampled**: the interval is conditional on the 3 realised holdout
  quarters and does not represent uncertainty over other holdout periods
  (`UNRESOLVED_LIMITATION`).

### 2.5 Is the confidence interval a valid uncertainty statement? (calibration simulation)

A cluster-resampling simulation (population = observed rows; 150 experiments × 150
bootstrap resamples; whole clusters resampled) of the exact CI procedure gives:

| unit (H4q) | coverage of the finite-population ΔAP | 95 % Wilson CI |
|---|---:|---|
| company | **0.953** | 0.907–0.977 |
| pair | **0.947** | 0.898–0.973 |

So the percentile cluster CI is approximately calibrated **for the pooled finite-population
estimand**, despite the skew and the 51 clusters. The interval is not invalid; what is
invalid is quoting it as an unconditional/pre-registered power statement and treating
"contains 0" as proof of absence (`CORRECTED_RESULT`). The H2q company bootstrap, however,
is not usable (bias +0.005, skew +2.89, CI [−0.010664, +0.053627] with a 5.2× asymmetric
shape); any H2q interval/MDE claim should be treated as `UNRESOLVED_LIMITATION`.

### 2.6 Is the "no evidence of improvement" conclusion stable?

`UNCHANGED_FINDING`. Every defensible variant has an interval containing zero:
reported company/pair percentile CIs; 5-seed CIs; delete-one jackknife-t CIs;
equal-weight mean-over-windows CI (p=0.8405); per-window CIs (0/3 exclude zero). The
**sign** and the **width** are not stable, and the pooled positive count is not 67
independent events — so the conclusion is "not detected / underpowered for small effects",
not "no effect".

---

## 3. Multiplicity: the BH implementation is buggy (but the conclusion survives)

### 3.1 The bug (`code/s028_stats.py` lines 117–129) (`BUG-BH-1`)

```python
indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
...
for rank, (index, value) in enumerate(reversed(indexed), start=1):
    threshold = q * (m - rank + 1) / m        # ascending rank threshold
    if value <= threshold and previous >= 0:  # pointwise test; `previous >= 0` is dead code
        result[index]["reject"] = True
    previous = min(previous, value)
for entry in result:
    entry["bh_threshold"] = q * (entry["index"] + 1) / m   # original index, NOT rank
```

Two defects:
1. **Pointwise instead of step-up.** BH rejects all ranks ≤ k_max where
   k_max = max{k: p₍ₖ₎ ≤ q·k/m}. The code compares each p to its own q·k/m and never
   propagates the step-up. The resulting reject set is a **subset** of the correct BH set
   ⇒ **conservative**, not anti-conservative.
2. **Mis-assigned thresholds.** `bh_threshold` uses the unsorted original index, so the
   printed table pairs each p with another rank's threshold (e.g. p=0.8935 was printed with
   0.0125 but its ascending rank is 7, whose threshold is 0.0875; the smallest p=0.1895 is
   rank 1 and must be compared with 0.0125). The displayed table in
   `STATISTICAL_VALIDATION.md` §3 is therefore not a BH table.

### 3.2 Correct re-derivation

8 p-values used by the script:
`[0.8935, 0.7445, 0.6325, 0.8840, 0.4590, 0.5985, 0.9075, 0.1895]`.
Sorted ascending: `0.1895, 0.4590, 0.5985, 0.6325, 0.7445, 0.8840, 0.8935, 0.9075`.
Correct thresholds q·k/m = `0.0125, 0.0250, 0.0375, 0.0500, 0.0625, 0.0750, 0.0875, 0.1000`.
The smallest p (0.1895) already exceeds 0.0125, so **k_max = 0 → 0 rejections**, identical
to the buggy implementation (0 rejections). The conclusion "no significance survives" is
`UNCHANGED_FINDING`; the code and the printed table are `BUG`.

### 3.3 The family is not the pre-registered family

`PRE_REGISTRATION.md` §10.5 defines the family as **{H1: 3 holdout windows + pooled;
H2: 3 windows}** (7 tests). The script instead assembles **2 horizons × (pooled + 3
windows) = 8 H1 tests** and omits H2 (which is decided by a randomisation quantile, not a
p-value). So the claim "BH over the pre-registered family" is inaccurate
(`CORRECTED_RESULT`). The per-window p-values are also dependent (overlapping outcomes),
though BH remains valid under positive dependence and nothing is close to rejection.
With q=0.10 and min p=0.1895 no family definition (4, 7 or 8 tests) rejects anything.

---

## 4. The 40 randomisations: resolution, p-value bounds, and the correct null interpretation

### 4.1 Resolution

With R = 40 draws, the smallest attainable one-sided randomisation p is **1/(R+1) =
1/41 = 0.02439** (two-sided floor 2/41 = 0.04878). A "97.5th percentile" of 40 draws sits
between the 39th and 40th order statistics — essentially the maximum; a tail beyond the
2.5 % point is not resolvable. Amendment 1's arithmetic (A1.1) is correct about the floor,
but the report's "far beyond the resolution" phrasing overstates what 40 draws can say:
"40/40" is the *smallest possible* one-sided evidence, not a well-resolved effect size.

### 4.2 Implementation detail (`BUG-H2-2`)

`s028_stats.py` lines 262–265 use `sorted(random)[int(0.975*len(random))]`; for n=40 that
is index 39 = **the maximum**. numpy's linear 97.5th percentile is 0.081343 (H4q) vs the
code's threshold 0.081982 (H2q: 0.094572 vs 0.100692). The implemented criterion was
therefore "real > max", i.e. stricter (conservative) than the stated "real > 97.5th
percentile". `CORRECTED_RESULT`.

### 4.3 Reproduced numbers and correct tail arithmetic

| | H4q | H2q |
|---|---:|---:|
| real pooled AP | 0.069003 | 0.067036 |
| randomised min / median / max | 0.069187 / 0.074115 / 0.081982 | 0.061335 / 0.073054 / 0.100692 |
| # randomisations ≥ real | **40/40** | **30/40** (75 %) |
| one-sided p, pre-registered direction (real > random) = (1+#random≥real)/41 | **1.0000** | **0.7561** |
| one-sided p, reverse direction (real < random) | 0.02439 | 0.26829 |
| two-sided p = 2(1+#...)/41 | 0.04878 | 0.53659 |
| per-window fraction random ≥ real | 1.000 / 0.525 / 0.825 | — |

So: the **pre-registered H2 direction has p = 1.0** — no evidence at all that the real graph
beats the null. The reverse-direction p = 1/41 is a *post-hoc* tail and, in addition,
inherits the broken null model. The pooled 40/40 is driven by the first and third windows;
the second window is at the 52.5th percentile.

### 4.4 Correct null-model interpretation

Under a valid degree- and time-preserving randomisation null, "real AP below all 40
randomisations" means the **real company–track arrangement is atypical in the wrong
direction**: it is *worse* than matched rearrangements. It is **not** evidence that
"random relations have predictive value", because the randomisation null does not assert
that random graphs are meaningful — it asserts that, if arrangement carries no
information, the real graph should look like a typical random graph. The observed deviation
would at most say the real arrangement is anti-informative relative to that null (and with
the broken null model, not even that). `INVALIDATED_FINDING` for every relational claim
that was built on this; H2 remains `UNRESOLVED_LIMITATION` until a corrected-G2 artifact
exists. `s028_stats_corrected.py` already supports the corrected schema
(`artifacts/correction_round_1/g2_corrected_<H4q|H2q>.json`) and will recompute the
randomisation distribution, empirical p-values `(1+#{random≥real})/(R+1)`, numpy quantiles
and attained resolution as soon as those rows are available.

### 4.5 What 40 draws can support

- Empirical p-values with a floor of 1/41; a median with resolution ~1/40; a 2.5th/97.5th
  percentile indistinguishable from the min/max.
- A "real is below the minimum of 40" statement (if the null model is valid). Under the
  invalid null model, even that is not usable as a method claim (`INVALIDATED_FINDING`).
- It cannot support a claim about the shape of the null distribution, about "all random
  relations", or about relational value in general.

---

## 5. Pre-registration fidelity of `decide()`

`corr.literal_decision()` re-implements §11 and matches the stored `decision` object on
both horizons (criteria (a),(b),(c), window counts, and the phrase-level NULL branch):
**`ORIGINAL_RESULT` / PASS**. Observations:

1. **(c) uses the point estimate against the pooled MDE.** The code implements
   `point >= mde` literally (line 142). This makes SUPPORT power-dependent: a real effect
   smaller than the MDE can never satisfy (c). `UNRESOLVED_LIMITATION` of the protocol,
   complied with faithfully.
2. **The NULL/UNDERPOWERED split is not operational.** `decide()` (lines 151–154) chooses
   "NULL (well-powered)" iff `|point| < MDE`. But whenever a 95 % CI contains 0,
   `|point| ≤ 1.96·SE < 2.80·SE = MDE` (verified: all 10 reported interval cases satisfy
   it), so the label is triggered *automatically* by non-rejection; the protocol's
   UNDERPOWERED branch ("MDE larger than any reasonable effect", line 215) has no
   threshold. The "well-powered" label therefore carries essentially no information
   beyond "not significant". `CORRECTED_RESULT` (label) / `INVALIDATED_FINDING` (use of
   it to claim adequate power).
3. **A post-hoc verdict label.** Lines 147–150 add "NULL (G1 significantly worse than
   baseline)", which is not in `PRE_REGISTRATION.md` §11. It was not triggered by the
   stored results, but it is a silent extension of the decision rule. `CORRECTED_RESULT`.
4. **MDE planning.** The *method* was frozen (§10.4) before results; the *number* was not
   (`BUG-MDE-3`, §1.2.3).
5. **Stratification deviation.** `HYPOTHESIS_REGISTRY.md` line 12 pre-declares strata
   `track / is_major / year`, while `strata()` reports `track / company / origin`
   (the code's own note replaces year by origin). `is_major` is never reported anywhere in
   the code. Minor pre-registration deviation (`CORRECTED_RESULT`).
6. **Protocol hashes.** `PRE_REGISTRATION.md` still matches the Amendment-1 freeze hash
   `49785703a5722c8b9fdec2682950620242c599a2369e00e93b070c95058c2521` (no silent edit).
   `HYPOTHESIS_REGISTRY.md` no longer matches its freeze hash because results were appended
   (allowed by its own append-only rule). `ORIGINAL_RESULT`.

---

## 6. Stability strata and the "0/3 windows" statement

`strata()` (`s028_stats.py` lines 97–114) reproduces the stored values exactly: H4q 6/38
tracks and 5/51 companies; H2q 1/38 and 1/51 (`ORIGINAL_RESULT`). Defects:

- **Thresholds inflated by duplication (`BUG-STRATA-1`).** n ≥ 10 / positives ≥ 5 are
  applied to pooled rows where each pair appears up to 3 times. Recomputing on unique
  pairs (positive if positive in any window) gives **0/38 tracks and 0/51 companies for
  H4q**, and **0/38, 0/51 for H2q**. The honest H4 statement is stronger than the report:
  no stratum meets the pre-declared reporting threshold; "6/38 tracks examined" is an
  artefact of triplication. `CORRECTED_RESULT`.
- **Field lookup fallback** (line 101) silently degrades to the window dict if the field
  is ever missing, which would produce empty strata rather than an error. Not triggered by
  the current calls (`tracks`, `companies`, `cutoff` all exist) but fragile.
  `UNRESOLVED_LIMITATION` (code smell, no numeric impact).
- The code's year-stratification substitution (origin instead of year) is documented in the
  JSON note; it is a deviation from §10.6, not from §11.
- **"0/3 windows exclude zero"** matches the stored per-window CIs exactly
  (`UNCHANGED_FINDING`).

---

## 7. Claim audit: what is invalidated vs unchanged

| original claim / number | tag | action |
|---|---|---|
| Pooled APs (B2 0.075093, G1 0.069003), ΔAP −0.006089, company/pair CIs, per-window APs/positives | `ORIGINAL_RESULT` | reproduced exactly; keep as finite-population estimates |
| "MDE(80%) = 0.01943" as *the* MDE and as a design power guarantee | `CORRECTED_RESULT` / `INVALIDATED_FINDING` (interpretation) | report 0.0194 pooled, 0.0197 quantile, 0.0109 jackknife-company, 0.0374 rule-level |
| "NULL (well-powered)" | `INVALIDATED_FINDING` | replace with explicit power bound (§8) |
| "no network effect exists" / "well-powered negative" | `INVALIDATED_FINDING` | only "no detectable incremental signal" |
| "point estimate negative / G1 worse than B2" | `CORRECTED_RESULT` | sign flips under deduplication; do not claim direction |
| "40/40 randomisations beat the real graph" / H2 reversed | `INVALIDATED_FINDING` (method) | H2 unresolved until corrected G2 |
| "random relations have predictive value" | `INVALIDATED_FINDING` | not licensed even by a valid null |
| "BH q=0.10 over the pre-registered family; 0/8" | `UNCHANGED_FINDING` (0 rejections) + `BUG` (code/family) | fix BH and report the correct family; conclusion unchanged |
| "H4 undeterminable; 6/38, 5/51 reportable" | `UNCHANGED_FINDING` (strengthened) | on unique pairs 0/38, 0/51 |
| "0/3 windows exclude 0" | `UNCHANGED_FINDING` | verified |
| "well-powered" wording in `STATISTICAL_VALIDATION.md`, `GRAPH_RESULTS.md`, `PHASE_REPORT_ZH.md`, `HYPOTHESIS_REGISTRY.md`, `PAPER_DRAFT.md` | historical record | do not edit those files; this correction supersedes the wording |

---

## 8. Honest wording that should replace "NULL (well-powered)"

**H1 (Chinese, recommended):**

> H1 未获支持。在合并的四个季度 horizon 上，G1 相对 B2 的配对 ΔAP = −0.0061
> （企业聚类 95% CI [−0.0222, +0.0045]；企业—赛道对聚类 95% CI [−0.0335, +0.0104]），
> 3 个 holdout 窗口中 0 个排除 0。该设计对合并检验的 MDE(80%) 为 0.0194 AP（基线
> 0.0751 的 25.9%），但预设的复合判定规则在同样效应下只能达到约 16% 功效，其 80%
> 功效所需效应约为 0.0374 AP（基线的 49.8%）。因此本研究的结论是"未检测到图特征的
> 增量信号"；数据与"无效应"一致，但也与至多约 0.0104 AP（对聚类上界，基线 13.9%）
> 的正效应一致，更小或中等增益既不能被排除、也不能被可靠检出。不得表述为
> "well-powered"、"网络效应不存在"或"G1 比 B2 差"。

**H1 (English, recommended):**

> H1 was not supported. The paired ΔAP(G1−B2) was −0.0061 (company-clustered 95% CI
> [−0.0222, +0.0045]; pair-clustered [−0.0335, +0.0104]); 0 of 3 holdout windows excluded
> zero. The pooled-test MDE(80%) is 0.0194 AP (25.9% of the 0.0751 baseline), but the
> pre-registered compound decision rule has only ≈16% power at that effect and would need
> ≈0.0374 AP (49.8% of baseline) for 80% power. The correct conclusion is *no detected
> incremental signal*: the data are consistent with no effect but also with a positive
> effect up to ≈0.0104 AP (pair-clustered upper bound, 13.9% of baseline); smaller and
> moderate gains are neither excluded nor reliably detectable. The study is not
> well-powered for its own decision rule, and "no network effect exists" / "G1 is worse
> than B2" are not supported.

**H2 (corrected-G2 re-derivation, §12):**

> The original randomised null model was invalid (edge loss / broken bipartite degree
> sequences / collapsed weights), so the original 40/40 comparison cannot be
> interpreted. The corrected-G2 re-derivation (S-028-CORRECTION-1, N1 and N2) gives:
> H4q real pooled AP 0.069003 vs corrected null 0.069730–0.082003 (N1) and
> 0.069160–0.083421 (N2); 40/40 null draws ≥ real; pre-registered p(real > random) =
> 1.0; correct 97.5th percentile 0.081879 (N1) / 0.081842 (N2). **H2 NOT SUPPORTED**
> for H4q, with the direction reversed; the reverse tail is exploratory and at the
> 1/41 resolution floor (p = 0.0244). H2q: 16/40 (N1), 20/40 (N2) null draws ≥ real,
> p = 0.415 / 0.512, real within 0.0001–0.0007 of the null median — **NOT SUPPORTED
> (inconclusive; consistent with the null)**. A random graph scoring higher is a
> statement about the real graph, not evidence that random relations predict.

**H4:**

> H4 is not identifiable: on unique company–track pairs (removing the ∼3× overlap
> triplication) no track or company stratum meets the pre-declared n ≥ 10 / positives ≥ 5
> threshold. No conditional-effect claim is reportable.

---

## 9. Deliverables and how to reproduce

| file | content |
|---|---|
| `code/audit_21_statistics.py` | self-contained audit on the original artifacts; prints + writes `artifacts/correction_round_1/stats_audit_original.json` (143 findings: PASS/DISCREPANT/BUG, 13 documented bugs with line numbers, claims mapping, coverage simulation, provenance hashes) |
| `code/s028_stats_corrected.py` | corrected pipeline; works on the original predictions and on the corrected-G2 sets (`g2_corrected_<label>_<N1|N2>.json`; `--g2-model {N1,N2,both,none}`; schema documented in the module docstring); writes `artifacts/correction_round_1/stats_corrected_<tag>.json` |
| `artifacts/correction_round_1/stats_audit_original.json` | machine-readable audit (every recomputed number + original counterpart + verdict) |
| `artifacts/correction_round_1/stats_corrected_original.json` | corrected numbers on the original artifacts (`tag="original"`) |
| `artifacts/correction_round_1/stats_corrected_g2.json` | corrected-G2 H2 re-derivation for both null models (`--g2-model both`; N1 and N2, per-window breakdown, resolution, invariants, provenance) |

Reproduce (cwd = `research/studies/graph_early_signal_s028/code/`):

```
python audit_21_statistics.py                 # ~103 s
python s028_stats_corrected.py                # ~62 s, both horizons, original data
# corrected-G2 H2 re-derivation (S-028-CORRECTION-1):
python s028_stats_corrected.py --g2-model both \
    --out artifacts/correction_round_1/stats_corrected_g2.json    # ~73 s
```

Both scripts import `s028_lib.fast_ap` (the frozen metric implementation, validated to
1.1e-16) and never refit a model; no original file is written.

---

## 10. Open limitations (not resolved by this review)

- `UNRESOLVED_LIMITATION` — ~~no valid randomisation distribution for H2 until
  corrected-G2 artifacts exist~~ **resolved by S-028-CORRECTION-1 (§12)**: corrected-G2
  N1/N2 artifacts now exist and the H2 re-derivation is in
  `artifacts/correction_round_1/stats_corrected_g2.json`. Remaining limitation: only two
  null constructions (neither preserves company strength exactly) and only 40 draws.
- `UNRESOLVED_LIMITATION` — the pooled estimand (triplicated overlapping-window rows) is
  not the same as a single-origin out-of-sample metric; with only 3 holdout windows no
  window-level generalisation is identified. The corrected pipeline reports the equal-weight
  mean-over-windows statistic as the time-aware alternative.
- `UNRESOLVED_LIMITATION` — H2q's company-clustered bootstrap distribution is pathological
  (skew +2.89, bias +0.005, 5.2× asymmetric CI); its MDE/CI cannot be quoted as a stable
  number.
- `UNRESOLVED_LIMITATION` — rule-level MDE uses a multivariate-normal location-shift power
  approximation (covariance from the joint company-cluster bootstrap; pair statistic
  assumed perfectly correlated). It is a defensible order-of-magnitude statement
  (≈0.04 AP for H4q, ≈0.06 AP for H2q), not an exact design guarantee; different
  alternative constructions can move it.
- `UNRESOLVED_LIMITATION` — protocol criteria (c) and the NULL/UNDERPOWERED split need a
  dated amendment before the next round; this review does not rewrite the protocol.

---

## 12. Corrected-G2 H2 re-derivation (S-028-CORRECTION-1)

**Inputs (read-only):** `artifacts/correction_round_1/g2_corrected_H4q_N1.json`,
`g2_corrected_H4q_N2.json`, `g2_corrected_H2q_N1.json`, `g2_corrected_H2q_N2.json`
(N1 = strict degree-preserving simple bipartite double-edge swap; N2 = N1 + exact
per-track activity volumes and exact per-track window-date / first-touch date
multisets; company strength is **not** exactly preserved in either model and is
reported per record). Pipeline: `code/s028_stats_corrected.py --g2-model both`.
Machine-readable output: `artifacts/correction_round_1/stats_corrected_g2.json`.
All numbers below were recomputed from the 40 `records` of each artifact (not taken
from the Lead or from the artifact `summary`), and the artifact SHA-256 is recorded in
the output's `provenance`.

**Artifact validation.** For all four files: the 40 records' `test_labels_sha256`
match the top-level hashes; `G1_vs_stored.identical = true` with max absolute
probability difference 4.2e-17; the `controls` B2/G1 pooled APs equal the stored
values (H4q: B2 0.075093, G1 0.069003; H2q: B2 0.067350, G1 0.067036); all
`invariants` boolean flags are true. N1 leaves tracked strength free (per-record
max track-strength deviation 49–62, temporal total variation ≈0.51–0.59); N2 makes
those two quantities exactly 0 (exact per-track volume and date multisets), while
company-strength deviation is 28–55 (N1) vs 28–42 (N2) — i.e. N2 is a *stricter*
track-side null, and the two models give the same qualitative answer.

### 12.1 H4q (primary): real pooled AP = 0.069003

| null model | null min | null median | null max | #null ≥ real | fraction | p (real > random, pre-registered) | p (real < random, reverse) | correct 97.5th pct | real > q97.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|
| N1 (R=40) | 0.069730 | 0.075508 | 0.082003 | 40/40 | 1.000 | **1.0000** | **0.02439** | 0.081879 | No |
| N2 (R=40) | 0.069160 | 0.075184 | 0.083421 | 40/40 | 1.000 | **1.0000** | **0.02439** | 0.081842 | No |

The Lead's figures are verified: N1 0.069730 / 0.075508 / 0.082003; N2 0.069160 /
0.075184 / 0.083421; N1–N2 pooled-median gap 0.000324. With R=40 the one-sided
resolution floor is **1/(R+1) = 1/41 = 0.02439** (two-sided 2/41 = 0.04878); the
reverse-tail p sits exactly at that floor, so the reversal is at the strongest
attainable tail evidence, not a resolved effect size. The correct 97.5th percentile
(numpy linear interpolation; *not* the original code's `sorted[int(0.975*R)] = max`)
is 0.081879 (N1) / 0.081842 (N2), both far above the real 0.069003 — criterion (d)
fails decisively under either threshold.

Per holdout window (real vs null median; #null draws ≥ real):

| window | real AP | N1 null median | N1 #≥real | N2 null median | N2 #≥real |
|---|---:|---:|---:|---:|---:|
| 2025-04-01 | 0.093252 | 0.116080 | 40/40 | 0.119148 | 40/40 |
| 2025-07-01 | 0.064258 | 0.064963 | 23/40 | 0.064102 | 18/40 |
| 2025-10-01 | 0.078224 | 0.081399 | 31/40 | 0.082270 | 27/40 |

The pooled reversal is driven by the first and third windows (the first is a genuine
large separation); the middle window is essentially at the null (N1: real slightly
below the median; N2: real slightly above the median). It is therefore **not**
a per-quarter reversal and must not be reported as one.

**Verdict — H4q: NOT SUPPORTED.** The pre-registered H2 direction is "real pooled AP
above the randomisation distribution's 97.5th percentile". The real graph is below
*every* draw of both corrected nulls (p for the pre-registered direction = 1.0), and
the entire null mass lies above the real AP. The relational claim is withdrawn under
§11. The reverse-direction tail (p = 1/41 = 0.0244) is an *exploratory* statement
("the real arrangement ranks worse than a degree-/volume-/time-matched rearrangement
on this pooled estimator") and, by itself, is bounded by the 1/41 resolution floor.
H1 is also not supported, so the §11 conjunction (d)+(e) fails independently.

### 12.2 H2q (secondary): real pooled AP = 0.067036

| null model | null min | null median | null max | #null ≥ real | fraction | p (real > random) | p (real < random) | correct 97.5th pct | real > q97.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|
| N1 (R=40) | 0.056490 | 0.066147 | 0.082306 | 16/40 | 0.400 | 0.41463 | 0.60976 | 0.074001 | No |
| N2 (R=40) | 0.061180 | 0.066827 | 0.073801 | 20/40 | 0.500 | 0.51220 | 0.51220 | 0.073125 | No |

Per window (real vs null median; #null ≥ real):

| window | real AP | N1 null median | N1 #≥real | N2 null median | N2 #≥real |
|---|---:|---:|---:|---:|---:|
| 2025-10-01 | 0.030133 | 0.031175 | 28/40 | 0.030803 | 29/40 |
| 2026-01-01 | 0.077081 | 0.082932 | 30/40 | 0.079991 | 27/40 |
| 2026-04-01 | 0.135761 | 0.131897 | 14/40 | 0.133963 | 18/40 |

The Lead's 16/40 (N1) and 20/40 (N2) are verified; N1–N2 median gap 0.000681.
**Verdict — H2q: NOT SUPPORTED (and effectively inconclusive).** The real AP sits
between the null min and max and only 0.0001–0.0007 from the null median; there is no
evidence it exceeds the 97.5th percentile (0.0740 / 0.0731), and no reversal either.
Under the pre-registered rule this is a failure to support, not a positive result.

### 12.3 The pre-registered direction and the correct null interpretation

The protocol's H2 direction is **real ABOVE random**: a random graph scoring *higher*
than the real graph is the **opposite** of H2. It is a statement about the real graph
— namely that, conditional on the null's preserved invariants, the real
company–track arrangement ranks *worse* than a matched rearrangement on this pooled
estimator. It is **not** evidence that random relations have predictive value: the
null asserts no relational information, so random graphs are not claimed to be
"informative"; if anything, a real graph below the null means the real arrangement is
atypical in an anti-informative direction relative to the null. This sentence should
appear verbatim wherever the H4q reversal is reported.

### 12.4 Does the triplication make the H4q reversal fragile? (Lead's point 3 — confirmed)

**Confirmed, with a precise scope.** The pooled estimator triplicates company–track
pairs (H4q: 5,159 rows = 1,729 distinct pairs; multiplicity {3: 1,709, 2: 12, 1: 8}),
and the same is true of the corrected-G2 evaluation. Both arms are scored on the
**same holdout rows with the same labels and the same pooled AP functional**; the
randomisation only changes which graph produced the G1 features. The randomisation
test is therefore a valid paired/exchangeability comparison *for that pooled
estimand*: the duplication weights are identically applied to real and null draws, so
they cannot manufacture a real-vs-null difference. This is different from the
G1-vs-B2 sign flip found in §2.2: that flip arose because *deduplicating changes the
estimand and hence the real arm's point estimate*; it does not invalidate a paired
comparison in which both arms are re-scored under the same deduplication. What is at
risk is **external validity, not internal validity**:

- The claim is about the triplicated/overlapping-window metric, not about a
  single-origin out-of-sample AP; the pooled weighting (pairs present in 3 windows
  count 3×) and the 13 cross-window contradictory labels are arbitrary design
  choices, and per-window results differ (2025-07 shows no reversal).
- Generalisation to "the real graph ranks worse than a degree-matched random graph"
  holds only *conditional on the null model's preserved invariants*. N1 leaves
  track activity volume and per-track time distribution free; N2 fixes them exactly.
  Both give the same verdict and nearly identical medians (gap 0.0003), so the
  reversal is **not** an artefact of the N1/N2 choice — but neither model preserves
  company strength exactly (max deviation 28–55), so a strength-matched null remains
  untested.
- The reversal is a 1/41-resolution tail; it should be described as "the real pooled
  AP is below the entire 40-draw corrected null (exploratory reverse-tail p = 1/41)",
  never as a precise effect size or a per-quarter finding.

### 12.5 H2 verdict summary

| horizon | real AP | N1 | N2 | pre-registered criterion (d) | verdict |
|---|---:|---|---|---|---|
| H4q | 0.069003 | 40/40 null ≥ real; p(real>random)=1.0 | 40/40; p=1.0 | real > q97.5 fails | **NOT SUPPORTED** (direction reversed; exploratory reverse-tail p=1/41) |
| H2q | 0.067036 | 16/40; p=0.4146 | 20/40; p=0.5122 | real > q97.5 fails | **NOT SUPPORTED** (consistent with null; no reversal) |

Caveats stated in §12.4 apply; H1 remains not supported (§1–§5), so the §11 H2
conjunction cannot be satisfied for either horizon. The original "40/40" claim remains
`INVALIDATED_FINDING` because it came from the broken null; the corrected-G2 result
above is a *new*, methodologically valid observation and should be cited as
S-028-CORRECTION-1, not as the original result.

---

*End of correction. Historical files `STATISTICAL_VALIDATION.md` and
`PHASE_REPORT_ZH.md` are preserved unchanged by this reviewer.*
