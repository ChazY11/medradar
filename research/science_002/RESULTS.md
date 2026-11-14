# RESULTS - SCIENCE-002 cross-source early-signal experiment

**Protocol:** `PROTOCOL.md`, frozen at commit `f5dad80` (2026-11-14T10:55Z) before
this run. **Post-freeze deviations: none.**
**Experiment payload:** `artifacts/experiment_results.json`, payload SHA-256
`0098a84e501b3648bfd1f6022e418b6cecd38c4f4b8eeafa2cfb505373c65d61`
(regenerated identically by the audit's A7 check); the confirmatory subset of the
payload (everything except the stochastic placebo-feature draws) hashes to
`088afd0fad469fb606e07f83065ee987cfacefcc5ed5d7a1cb411e8f106fa17f`.
**Verdict: NULL** - the experiment is valid and no within-firm incremental signal
was detected. It is **not** a NO-GO: every feasibility gate and both positive
controls passed. It is **not** a GO.

---

## 1. The question this actually tested

> Inside one medical-technology issuer, do the R&D/technology facts that issuer had
> already made public in SEC filings rank the issuer's future 90-day FDA 510(k)
> clearance months above its non-clearance months **better than its own clearance
> history and ordinary disclosure activity do**?

Firm identity is deliberately *removed* from the comparison by estimating the
models with firm fixed effects. The pooled question (which firms clear more
devices?) is reported in section 5 and is explicitly **not** treated as a finding
about early signal.

## 2. The sample actually used

| | |
|---|---|
| SEC registrants investigated | 62 |
| registrants in the universe | **48** |
| excluded, with reason | 14 |
| attributable cleared 510(k)s, 2015-01-01..2026-08-31 | **3,143** |
| issuer-months constructed | 2,771 |
| dropped: SEC history shorter than 400 days before t | 397 |
| dropped: incomplete R&D features | 78 |
| complete-case rows | **2,554** |
| train (2021-01..2024-12) | 1,772 |
| holdout (2025-01..2026-06) | **782** |
| holdout firms / firms in the stratified statistic | 44 / **31** |
| holdout prevalence | **53.1%** (train 49.9%) |

The holdout has 415 clearance months and 367 empty months. Fifteen of the 44
holdout firms have only one class and are therefore excluded from every
within-firm statistic; they still contribute to fitting.

## 3. Primary result

Statistic: `delta = S(B3c) - S(B2c)` on the holdout, where `S` is the
firm-stratified AUC (unweighted mean of per-firm AUCs, 31 firms).

| | |
|---|---|
| **delta firm-stratified AUC (B3c - B2c)** | **-0.034** |
| within-firm permutation p (two-sided, 2,000 perms) | **0.096** |
| positive-tail p | 0.949 |
| circular-shift permutation p (two-sided, 2,000 perms) | 0.200 |
| cluster-bootstrap 95% CI for delta (2,000 draws over firms) | **[-0.083, +0.017]** |
| firms where B3c beat B2c | **12 / 31** |
| per-firm delta median / range | 0.000 / [-0.750, +0.333] |

**Reading.** No positive effect. The point estimate is negative and is not
significant under either null; the magnitude is driven by a few firms with very
negative per-firm deltas rather than by a uniform shift. The upper confidence bound
is the informative part: **a within-firm improvement larger than +0.017 AUC can be
excluded at 95%** on this holdout. Smaller effects cannot be excluded, and the
minimum detectable delta at 80% power is **0.055**.

## 4. The model ladder

### 4.1 Firm-conditional (primary family, firm fixed effects)

| model | predictors | holdout firm-stratified AUC | 95% cluster CI | firms |
|---|---|---|---|---|
| B0c | intercept + firm dummies only | 0.500 | - (exact by construction) | 44 |
| B1c | + firm clearance history | 0.454 | [0.387, 0.523] | 31 |
| B2c | + disclosure activity & seasonality | **0.486** | [0.417, 0.557] | 31 |
| B3c | + SEC R&D features | **0.453** | [0.384, 0.518] | 31 |

All three lie within chance variation of 0.5 and none is above it. Adding the SEC
R&D block moves the statistic by -0.034 (p = 0.096); adding R&D over history alone
(B3c - B1c) moves it by **-0.001** [-0.073, +0.079].

### 4.2 Pooled (descriptive only - do not read as signal)

| model | predictors | pooled holdout AUC | 95% cluster CI |
|---|---|---|---|
| B0 | none | 0.500 | - |
| B1 | firm clearance history | **0.829** | [0.751, 0.889] |
| B2 | + disclosure activity | 0.828 | [0.749, 0.888] |
| B3 | + SEC R&D features | 0.833 | [0.755, 0.891] |

Pooled delta (B3 - B2) = **+0.005** [-0.005, +0.017]: nothing. The entire pooled
performance is firm composition, exactly as SCIENCE-001 found. This number is
reported for completeness and is **not** evidence of an early signal.

## 5. Why the pooled number is not the finding

The same ladder read two ways:

| | pooled AUC | firm-stratified AUC |
|---|---|---|
| B1 | **0.829** | 0.454 |
| B2 | 0.828 | 0.486 |
| B3 | 0.833 | 0.453 |

A model that ranks *firms* almost perfectly ranks *months inside a firm* at
chance. The gap is the measurement artefact SCIENCE-001 warned about, reproduced on
a completely different outcome (FDA clearance instead of SEC item codes) and a
completely different source pair (SEC -> FDA instead of SEC -> SEC).

## 6. Cross-firm generalisation (leave-one-firm-out, pooled models)

| | mean per-firm AUC over held-out firms | firms |
|---|---|---|
| B2 | 0.385 | 31 |
| B3 | 0.383 | 31 |
| delta B3 - B2 | **-0.002** (16/31 firms positive) | 31 |

This is worse than chance and it is a real result, not a coding error: a
coefficient vector estimated across firms encodes between-firm contrasts, and when
applied inside a single held-out firm those contrasts can order months *backwards*.
It is the cross-firm analogue of the pooled/within gap in section 5, and it is the
strongest available argument against the pooled design that most published
early-signal work uses.

## 7. Controls

| control | expectation | observed |
|---|---|---|
| positive control: firm history predicts clearance across firms (pooled B1) | >> 0.5 | **0.829** [0.751, 0.889] |
| positive control: activity predicts *any* 8-K (pooled B2) | > 0.55 | **0.632** (B3 0.647) |
| placebo outcome: 8-K item 5.07 (annual-meeting votes) through B2c/B3c | no difference | delta **-0.011**, stratified B3c 0.505 (prevalence 31.8%) |
| label transplant across firms (pooled) | ~0.5 | B1 0.496, B2 0.497, B3 0.504 |
| **placebo features**: R&D columns shuffled within firm, model refitted, 100 draws | observed delta inside the band | band [-0.037, +0.017], observed **-0.034**, p = 0.0495 |

The two positive controls pass, so the label machinery and the history baseline
work. The placebo outcome is null, as it should be.

The **placebo-feature** control is the only uncomfortable number in this report and
it is not being smoothed over: the observed delta sits at the negative edge of the
band produced by shuffling the R&D columns within each firm (p = 0.0495, 5/100
draws at or beyond it). Two readings are consistent with the data. Either the real
R&D timing carries a small *negative* association with the next quarter's clearance
months - for example clearances cluster when R&D spending is temporarily flat - or
the 5% tail is chance at 100 draws. Nothing in this design can separate those, and
the permutation null (p = 0.096), the circular-shift null (p = 0.200) and the
leave-one-firm-out delta (-0.002) do not support any positive claim either way. It
is reported because a reader who recomputes will see it.

## 8. Secondary analyses

* **B4 extended R&D block** (three lagged growth terms + intensity relative to the
  firm's own three-year mean): delta B4c - B3c = **+0.009** on 773 holdout rows
  (B3c 0.434 -> B4c 0.444). Null.
* **Placebo outcome** 5.07 through the same firm-conditional ladder: delta -0.011.
* **Label transplant** (each firm's scores paired with another firm's labels):
  pooled AUCs 0.496 / 0.497 / 0.504 for B1 / B2 / B3.
* **Delta B3c against B1c** (does R&D add over firm history alone, with no activity
  block): -0.001 [-0.073, +0.079].

### 8.1 Pre-registered sensitivities (full table in AUDIT.md section 4)

| scenario | firms | delta (B3c - B2c) | permutation p | 95% CI | verdict |
|---|---|---|---|---|---|
| base | 48 | **-0.034** | 0.100 | [-0.084, +0.018] | NULL |
| S1 strict attribution (T_A + T_A2 only, drops the 2026 ownership map) | 45 | **-0.043** | 0.047 | [-0.089, +0.008] | NULL |
| S2 drop SIC 3826 | 47 | **-0.027** | 0.210 | [-0.070, +0.021] | NULL |
| S3a availability lag 0 days | 48 | **-0.020** | 0.292 | [-0.068, +0.033] | NULL |
| S3b availability lag 60 days | 48 | **-0.028** | 0.157 | [-0.074, +0.022] | NULL |

Every point estimate is non-positive (-0.043 to -0.020) and no scenario reaches the
GO rule, so the conclusion does not depend on the attribution tier or the
availability lag. S1's p = 0.047 is a nominally significant **negative** association,
not a positive one; it was not a pre-registered directional hypothesis, it is not
robust across the other specifications, and it is the same pattern the R&D-timing
placebo flagged in section 7. It is reported as a caution, not as a finding.

## 9. Power, stated plainly

| quantity | value |
|---|---|
| holdout positives / negatives | 415 / 367 |
| firms entering the stratified statistic | 31 |
| Hanley-McNeil minimum detectable AUC at 80% power | **0.642** |
| permutation-null sd of delta | 0.0197 |
| minimum detectable delta at 80% power (2.8 x sd) | **0.055** |
| 95% CI upper bound on delta | **+0.017** |

So: effects of a size that would matter (say +0.05 AUC within firm) were
detectable and were not found; effects below +0.017 are excluded; effects between
+0.017 and +0.055 are neither detected nor excluded. The study is a feasibility gate
with a tight null on the upper side and a soft floor on the lower side.

## 10. What this experiment can and cannot say

**Can say**

* On 48 SEC-registered device issuers, 2021-01..2026-06, and a 90-day 510(k)
  clearance indicator, the issuer's own SEC R&D facts add **no detectable
  within-firm discrimination** over its clearance history and disclosure activity.
* R&D *growth* is the only SEC R&D feature with material within-firm variance
  (94% of its variance is within firm); R&D *level* and *intensity* are firm
  characteristics (2% and 4% within-firm variance) and cannot be tested this way.
* Firm identity dominates pooled discrimination (0.83) while within-firm
  discrimination is at chance - replicated across two different outcome families.
* A pooled model does not transfer across firms: leave-one-firm-out AUC is 0.385,
  i.e. worse than chance.
* Cross-source SEC->FDA linkage is feasible but partial: 8.8% of cleared 510(k)s in
  the window are attributable to the 48 firms with exact-name evidence only.

**Cannot say**

* that SEC filings contain no information about future regulatory activity - only
  that these four fixed R&D/activity blocks, at monthly resolution, do not;
* anything about lead time in days, because no public-availability timestamp exists
  for FDA data (TIME_SEMANTICS.md);
* anything about *which specific* clearance will occur, or about clinical value;
* anything causal: R&D spending and clearance timing plausibly share drivers
  (programme maturity, hiring, cash) that this design cannot separate;
* that the null generalises to smaller firms, to firms outside the SIC gate, or to
  the 91% of FDA clearances that exact-name attribution does not reach.

## 11. Reproduce

```
python research/science_002/cli.py fetch        # network once; ~250 MB openFDA + SEC JSON
python research/science_002/cli.py universe     # offline
python research/science_002/cli.py panel        # offline
python research/science_002/cli.py experiment   # offline, ~4 min
python research/science_002/cli.py audit        # offline, ~12 min (3 experiment runs)
python research/science_002/cli.py figures      # offline
python -m pytest tests/test_science_002.py -q   # offline, synthetic fixtures
```

Figures: `artifacts/figures/figure1_sample_structure.png`,
`figure2_model_ladder.png`, `figure3_primary_null.png`, with source hashes in
`artifacts/figures/figures_manifest.json`.