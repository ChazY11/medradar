# Audit C — T-TRACK target definition and mathematical coupling

**Verdict up front.** Yes: the published H8 gain (+0.0379 held-out dAP over B1 persistence) is
consistent with — and quantitatively indistinguishable from — a **target-definition artifact**.
Under simulated pure noise with **no trend and no change points**, the identical v1 pipeline
produces a mean dAP of **+0.0373** (negative binomial, sd 0.0224) and **+0.0833** (Poisson,
sd 0.0372); the real +0.0379 sits at the **45th percentile** of the NB noise band and the **5th
percentile** of the Poisson band, and **20/20** universes are positive under both noise models.
When the target's `>= 1.5 x trailing8 mean` ratio rule is removed (`any_activity` target) the H8
edge collapses to **+0.0007 / +0.0010**. The mechanism is not a leak: it is that the label's own
acceptance region is a **non-monotone function of the past activity level**, and the H8 feature
block supplies nonlinear level transforms (`sct_slope12`, `sct_volatility8`) that let a logistic
model fit that construction rule better than B1's (near-)linear level features. The gain is
"predictability of the label rule", not of the future.

The naive vacuous-positive story is **small** and is reported honestly: only **1.0%** of full-panel
positives and **1.9%** of v1 evaluable positives have `trailing8 total == 0`. The artifact is the
*systematic level dependence of the ratio target*, not a handful of 0/0 rows. A second mechanical
subgroup is larger: **8.4%** of evaluable positives are 3-event positives whose ratio test is
automatically satisfied (`t8 <= 4`), i.e. created by the `>= 3` floor alone.

---

## Provenance and command

```
python experiments/phoenix/h8_validation_v2/audits/c_target.py
```

- Must be run from the repo root (`D:\DEPPSKK\worktrees\phoenix002`); runtime **~80 s**
  (79.3 s recorded in `c_target.json`).
- Writes exactly one file: `experiments/phoenix/h8_validation_v2/audits/c_target.json` (41,874 B).
- DB verified read-only: SHA-256 `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92`
  (`matches_frozen = True`, `integrity_check = ok`), opened via `?mode=ro&immutable=1`.
- No existing file was modified. v1 code is imported, not edited
  (`phoenix_common`, `track_common`, `run_track`); no v1 `RunLog` is instantiated, so no v1
  evidence log is overwritten.
- Panels: v1 cached `track_panel_L090.pkl` / `L000.pkl` (**4,904 rows × 89 cols, 59 tracks,
  86 quarters 2004Q1–2025Q2**); full labelled panel **4,255 rows / 406 positives**;
  v1 walk-forward evaluable rows **2,443 / 155 positives / 11 folds**.

Reproduction check (exact, to machine precision):
`AP_B1 = 0.1234103229`, `AP_H8 = 0.16131436`, `dAP = +0.0379040371` — identical to
`results/h8_scitrends.json`. The v1 run has **11** folds (2014–2024), not 12: `build_joint_panel`
trims to `ORIGIN_END` *before* `add_forward_target`, so the last origin with a complete 4-quarter
forward window is 2024Q2 and the 2025 fold is empty.

---

## Part 1 — Label decomposition

`y = 1` iff `sum(n_device over q+1..q+4) >= 3` **and** `fwd_mean >= 1.5 x trailing8_mean`
(denominator / bucket are on the **event clock**, `n_device`).

### 1a. Full labelled panel (4,255 rows, 406 positives, prevalence 9.54%)

| trailing8 total (events / 8Q) | rows | positives | trigger rate P(y=1) | share of all positives |
|---|---:|---:|---:|---:|
| 0 | 1,604 | 4 | 0.0025 | 0.99% |
| 1–2 | 180 | 17 | 0.0944 | 4.19% |
| 3–5 | 205 | 77 | **0.3756** | 18.97% |
| 6–12 | 206 | 59 | 0.2864 | 14.53% |
| 13+ | 2,060 | 249 | **0.1209** | 61.33% |

- Positives with `trailing8 total == 0` (ratio vacuous, `0 >= 0`): **4 / 406 = 0.99%**.
- Positives with `trailing8 mean < 0.5` (`t8 < 4`): **53 / 406 = 13.05%**.
- Positives with the minimum forward count (`fwd_sum == 3`): **40 / 406 = 9.85%**; **all 40**
  also have `t8 <= 4`, so for every one of them the ratio test is satisfied automatically
  (`fwd_mean = 0.75 >= 1.5 x t8/8` whenever `t8 <= 4`). They are **floor positives**, not
  growth positives.
- Minimum forward events among positives: **3** (mechanical).

### 1b. v1 walk-forward evaluable rows (2,443 rows, 155 positives, prevalence 6.34%)

| trailing8 total | rows | positives | trigger rate | AP_B1 | AP_H8 | dAP |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 956 | 3 | 0.0031 | 0.0023 | 0.0026 | +0.0003 |
| 1–2 | 110 | 5 | 0.0455 | 0.0409 | 0.0434 | +0.0025 |
| 3–5 | 85 | 22 | 0.2588 | 0.2249 | 0.2568 | +0.0319 |
| 6–12 | 54 | 19 | **0.3519** | 0.3468 | 0.2791 | **−0.0677** |
| 13+ | 1,238 | 106 | 0.0856 | 0.1243 | 0.1627 | **+0.0384** |

- Vacuous-ratio positives (`t8 == 0`): **3 / 155 = 1.94%**.
- `trailing8 mean < 0.5`: **23 / 155 = 14.84%**.
- Floor (3-event) positives: **13 / 155 = 8.39%**, all 13 with `t8 <= 4` (fully ratio-vacuous).
- `t_*` trial-only rows in the evaluable set: **858 (35.12% of rows), 0 positives**.

**Reading.** The trigger rate is **not monotone in activity**: it peaks at 3–12 trailing events
and falls by a factor 3 in the 13+ bucket (0.1209 vs 0.3756 full panel). That is the ratio rule
doing the work: the higher the trailing level, the harder the `1.5x` test. Only 1–2% of positives
are literally 0-denominator; the artifact is the *graded* dependence on the denominator, which
Part 3 shows reproduces on pure noise.

---

## Part 2 — Mechanical coupling between label and features

Label clock = `n_device` (`event_date`); feature clock = `f_n_device` (`available_at + 90 d`).

| | corr(f, n) | fraction rows exactly equal | mean \|diff\| (events / quarter) | column sums |
|---|---:|---:|---:|---:|
| **L000** | **1.000000** | **1.000000** | **0.0000** | 34,885 = 34,885 |
| **L090** | 0.916498 | 0.489396 | 2.7504 | 34,475 vs 34,885 |

- At **L000 the feature column IS the label column** (identity by construction); the label's
  trailing mean is reproduced exactly by `f_n_device_sum8 / 8`.
- At **L090** they diverge only by a ~1-quarter shift: `corr(f_n_device_sum8, event-clock t8) =
  **0.998341** (Spearman 0.997732), 48.3% of rows exactly equal, mean `|f_n_device_sum8 − t8| =
  3.142` events, mean `|f_n_device_sum8/8 − t_mean8| = **0.393** events/quarter`, and
  `corr(f_n_device_mean4, t_mean8) = 0.994258`. The feature level is, for practical purposes, the
  label denominator one quarter earlier.

### Algebraic relation of the H8 block to the label denominator

`sct_growth{w} = (sum_w − prev_sum_w) / (prev_sum_w + 1)` on `f_n_device` — reconstructed with
**max abs error 0.00e+00**; `sct_pma_share4 = f_n_pma_sum4 / (f_n_device_sum4 + 1)` — also exact.
Consequently:
- `sct_growth8`'s **numerator is the trailing-8Q sum itself**; at L000 that IS `8 x label denominator`.
- `sct_volatility8 = f_n_device_std8 / (f_n_device_mean4 + 1)` is a level/dispersion function of
  the same series.
- `sct_slope12` is an OLS slope of `log1p(trailing 12 f_n_device)` — a nonlinear transform of the
  same series.
- `sct_pma_share4`'s denominator is the feature-clock activity level.

**All seven H8 features are algebraic functions of the same device-count series whose trailing
mean is the label denominator.** There is no independent information channel.

### corr(H8 feature, trailing level)

| feature | r vs label denominator | rho vs label denominator | r vs feature level | rho vs feature level |
|---|---:|---:|---:|---:|
| sct_growth1 | −0.0050 | +0.0182 | −0.0057 | +0.0166 |
| sct_growth2 | −0.0170 | +0.0175 | −0.0198 | +0.0155 |
| sct_growth4 | −0.0073 | +0.0505 | −0.0154 | +0.0358 |
| sct_growth8 | +0.0418 | +0.2134 | +0.0338 | +0.2126 |
| sct_slope12 | +0.0783 | +0.1693 | +0.0682 | +0.1600 |
| **sct_pma_share4** | **+0.5265** | **+0.8057** | +0.5234 | **+0.8040** |
| **sct_volatility8** | +0.0949 | **+0.6237** | +0.0956 | **+0.6281** |

Honest correction to the audit hypothesis: the four `sct_growth{w}` **ratios are scale-normalised
by `(prev + 1)` and do *not* anti-correlate with the level** (r ≈ 0). The level coupling lives in
`sct_pma_share4` (Spearman +0.80) and `sct_volatility8` (Spearman +0.62) — two features that are
(at least non-monotonically) functions of track size, plus the residual `+0.21` for
`sct_growth8`. Part 3b shows the noise dAP is carried by `sct_slope12` and `sct_volatility8`, not
by the four growth ratios or the PMA share.

---

## Part 3 — Mean reversion: pure-noise simulation

### Simulation assumptions (exact)

- **20 universes** per noise model, **59 tracks × 86 quarters** (2004Q1–2025Q2), dense panel.
- **No trend, no change points, no calendar effect, no cross-track dynamics.** Only
  cross-sectional level heterogeneity.
- Per-track mean `λ_track` drawn **with replacement from the 59 observed per-track device
  events/quarter** (38 non-zero + 21 zero tracks) → observed track-size distribution and
  zero-inflation matched.
- **Poisson:** `X_t ~ Poisson(λ_track)`, iid across quarters.
- **Negative binomial:** `X_t ~ NB2(mean = λ_track, Var = μ + μ²/r)` with **r = 1.4265**, chosen
  so the median within-track dispersion index (`Var/mean = 1.7010`, observed) is matched.
- PMA split: per-track PMA probability drawn from the observed per-track PMA shares;
  `f_n_pma ~ Binomial(X_t, p_track)`, `f_n_510k = f_n_device − f_n_pma` (affects only
  `sct_pma_share4`).
- Feature clock: `f_n_device[q] = n_device[q−1]` (single-quarter lag; L090 analogue).
  `exposure_q = t`, `log_exposure = log1p(t)`.
- Target: **identical** `pc.add_forward_target(target='growth')` call (≥3 and ≥1.5×).
- Features: **identical** v1 builders (`add_history_features` + `add_growth_features`).
- Model: **identical** `pc.LogisticModel` (median impute → standardise → L2 C=1).
- Evaluation: **identical** `pc.walk_forward_folds(2014, 2025)`, OOF AP pooled over folds,
  B1_persistence vs H8_growth paired on identical rows.

### Results (20 universes each)

| noise model | AP_B1 mean | AP_H8 mean | **mean dAP** | median dAP | sd | min | max | P(dAP>0) | real +0.0379 pctile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Poisson | 0.1375 | 0.2208 | **+0.0833** | +0.0766 | 0.0372 | +0.0217 | +0.1598 | **20/20** | **5th** |
| Negative binomial | 0.2612 | 0.2985 | **+0.0373** | +0.0418 | 0.0224 | +0.0033 | +0.0818 | **20/20** | **45th** |

The published v1 dAP (**+0.0379**) is **inside the pure-noise band under both models** and is
within 0.0006 of the NB noise mean. Mean prevalence differs from the real data (Poisson 4.35%,
NB 13.07%, real 6.34%); the NB arm therefore over-states AP levels, and Poisson is the closer
match for `AP_B1` (0.137 vs 0.123). See limitations.

### 3b. Mechanism — ablations on the same pure-noise universes (8 universes each, mean dAP)

| arm | dAP Poisson | dAP NB |
|---|---:|---:|
| B1 + growth1248 (4 ratio features only) | +0.0016 | +0.0024 |
| **B1 + sct_slope12** | **+0.0666** | **+0.0389** |
| B1 + sct_pma_share4 | +0.0003 | −0.0003 |
| **B1 + sct_volatility8** | **+0.0571** | **+0.0217** |
| H8 all | +0.0967 | +0.0465 |
| **ratio-free target (`any_activity`)** | **+0.0007** | **+0.0010** |

Two facts pin the mechanism:
1. The noise gain comes from **`sct_slope12` and `sct_volatility8`** — nonlinear level transforms —
   while the four "growth ratio" features and the PMA share contribute ≈ 0.
2. With the **`1.5x` ratio rule removed** (same features, same models, `y = 1` iff ≥1 forward
   event), the H8 edge **vanishes** (+0.0007 / +0.0010). On real data the same control gives
   **dAP = +0.00045** for a `fwd_sum >= 3`-only target (no ratio). The H8 edge exists *only*
   because the target contains a trailing-level ratio.

**Mechanism.** `y` requires forward activity ≥ 1.5× the trailing level and ≥ 3 events. The first
condition makes `P(y=1)` *decreasing* in the trailing level; the second makes it *increasing* in
the level. The acceptance region is therefore **non-monotone in the track's own past activity**.
`P(y=1)` is accordingly non-monotone in `t8` (table 1a). B1's level features are close to linear
in that level, so it can only partially fit the non-monotonicity; `sct_slope12` (slope of
`log1p`) and `sct_volatility8` (dispersion normalised by level) provide a nonlinear basis that
fits the label's own construction rule. A logistic model then "predicts" the label from its own
denominator — under a completely memoryless process.

### 3c. Trigger profile: real vs pure noise (same label definition; 5 universes pooled)

| bucket | real | Poisson | NB |
|---|---:|---:|---:|
| 0 | 0.0025 | 0.0023 | 0.0044 |
| 1–2 | 0.0944 | 0.0999 | 0.1274 |
| 3–5 | 0.3756 | 0.1540 | 0.2220 |
| 6–12 | 0.2864 | 0.2787 | 0.3131 |
| 13+ | 0.1209 | 0.0434 | 0.2042 |

The **rise-then-collapse shape is reproduced by pure noise**, so "growth is rarer in mature
tracks" is partly a property of the label, not of the technology. Caveat: the real profile peaks
at 3–5 events while Poisson peaks at 6–12, Poisson underestimates the 13+ rate (0.043 vs real
0.121) and NB overestimates it (0.204 vs 0.121). This is a qualitative mechanism demonstration,
not a calibrated null.

---

## Part 4 — Decomposing the published v1 dAP (+0.037904)

Pooled: `AP_B1 = 0.123410`, `AP_H8 = 0.161314`, `dAP = +0.037904` (11 folds, 2,443 rows, 155 pos).

### 4a. By trailing-activity stratum

| stratum (t8) | n | pos | prevalence | AP_B1 | AP_H8 | dAP |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 956 | 3 | 0.0031 | 0.0023 | 0.0026 | +0.0003 |
| 1–2 | 110 | 5 | 0.0455 | 0.0409 | 0.0434 | +0.0025 |
| 3–5 | 85 | 22 | 0.2588 | 0.2249 | 0.2568 | +0.0319 |
| 6–12 | 54 | 19 | 0.3519 | 0.3468 | 0.2791 | **−0.0677** |
| 13+ | 1,238 | 106 | 0.0856 | 0.1243 | 0.1627 | **+0.0384** |

The gain is **not** carried by low-trailing rows: the 0 bucket contributes **+0.0003** (3
positives) and 1–2 contributes +0.0025. It is a pooled-ranking effect concentrated in the
**13+ bucket (106 of 155 positives, +0.0384)** and offset partly by the 6–12 bucket (−0.0677 on
19 positives, i.e. noise-level instability at that sample size).

### 4b. By year (11 walk-forward folds)

| year | n | pos | AP_B1 | AP_H8 | dAP |
|---|---:|---:|---:|---:|---:|
| 2014 | 228 | 12 | 0.1746 | 0.2124 | +0.0378 |
| 2015 | 228 | 19 | 0.1713 | 0.2053 | +0.0340 |
| 2016 | 229 | 24 | 0.1595 | 0.2700 | +0.1105 |
| 2017 | 232 | 23 | 0.1779 | 0.2947 | +0.1168 |
| 2018 | 232 | 14 | 0.1607 | 0.2403 | +0.0797 |
| 2019 | 232 | 13 | 0.2100 | 0.1264 | **−0.0836** |
| 2020 | 236 | 16 | 0.1247 | 0.2069 | +0.0821 |
| 2021 | 236 | 3 | 0.0398 | 0.0804 | +0.0406 |
| 2022 | 236 | 9 | 0.0920 | 0.1168 | +0.0248 |
| 2023 | 236 | 14 | 0.0931 | 0.1777 | +0.0846 |
| 2024 | 118 | 8 | 0.0970 | 0.4326 | **+0.3356** |

Sign is unstable (2019 strongly negative) and the largest single contribution is the
**half-year 2024 fold (+0.3356 from 8 positives)**. The effect is not a stable, era-robust signal.

### 4c. By track — per-track AP delta and leave-one-track-out (LOTO) contribution

59 tracks in the evaluable set; **30 have ≥1 positive** (AP delta computable). LOTO contribution
= full pooled dAP − pooled dAP with that track removed.

| track | n | pos | AP_B1 | AP_H8 | per-track dAP |
|---|---:|---:|---:|---:|---:|
| trauma | 42 | 5 | 0.2587 | 0.9029 | +0.6441 |
| endoscopy | 42 | 4 | 0.2514 | 0.8929 | +0.6415 |
| heart_failure | 42 | 5 | 0.1052 | 0.3993 | +0.2941 |
| imaging_us | 42 | 2 | 0.0590 | 0.3333 | +0.2743 |
| patient_monitoring | 42 | 6 | 0.1080 | 0.3118 | +0.2038 |
| neurovascular | 42 | 2 | 0.3611 | 0.1214 | −0.2397 |
| insulin_delivery | 42 | 8 | 0.5235 | 0.4247 | −0.0989 |
| ophthalmology | 42 | 8 | 0.5954 | 0.5389 | −0.0565 |
| wound_care | 42 | 2 | 0.0901 | 0.0464 | −0.0436 |
| diabetes_cgm | 42 | 6 | 0.1681 | 0.1511 | −0.0170 |

Leave-one-track-out (LOTO) contributions available in `c_target.json`:

| track | pos | per-track dAP | LOTO contribution |
|---|---:|---:|---:|
| ivd_immuno | 8 | +0.0556 | +0.00475 |
| patient_monitoring | 6 | +0.2038 | +0.00423 |
| wearable_remote | 10 | +0.0355 | +0.00371 |
| imaging_us | 2 | +0.2743 | +0.00348 |
| trauma | 5 | +0.6441 | +0.00276 |
| infection_control | 9 | −0.0149 | −0.00447 |
| insulin_delivery | 8 | −0.0989 | −0.00306 |
| dialysis | 6 | +0.0313 | −0.00264 |
| wound_care | 2 | −0.0436 | −0.00245 |
| diabetes_cgm | 6 | −0.0170 | −0.00200 |

The five largest positive LOTO contributors sum to **+0.0189**, i.e. **49.9%** of the +0.0379
pooled dAP, and every one of them is driven by a track with **2–10 positives** (per-track APs of
0.90 on 4–5 positives are not credible precision estimates). The effect is thin and unstable, not
concentrated in a single explainable unit.

### 4d. Dropping low-trailing origins, and the `t_*` tracks

| subset | n | pos | AP_B1 | AP_H8 | dAP |
|---|---:|---:|---:|---:|---:|
| all | 2,443 | 155 | 0.1234 | 0.1613 | +0.0379 |
| drop `t8 <= 0` | 1,487 | 152 | 0.1315 | 0.1644 | +0.0329 |
| drop `t8 <= 2` | 1,377 | 147 | 0.1349 | 0.1745 | **+0.0396** |
| drop `t8 <= 3` | 1,328 | 132 | 0.1343 | 0.1706 | +0.0363 |
| device tracks only (drop 21 `t_*`) | 1,585 | 155 | 0.1302 | 0.1625 | **+0.0323** |

- Dropping origins with `trailing8 total <= 2` **does not remove the gain** (+0.0396, slightly
  *higher*) — direct evidence that the near-zero-denominator rows are not the source. This is the
  key negative result against the naive "vacuous ratio" explanation.
- The **21 `t_*` trial-only tracks** contribute **858 rows (35.1% of evaluable rows)** with
  **zero positives**. They have all-zero device features and all-negative labels, so no arm can
  rank within them. Removing them lowers dAP from +0.037904 to +0.032269, i.e. they account for
  **+0.005635 = 14.87%** of the published dAP — through the pooled AP's negative-block denominator
  and the different intercept/score shift of the two arms, not through any predictive signal.

---

## Part 5 — `sct_pma_share4`: technology-progress proxy?

`sct_pma_share4 = f_n_pma_sum4 / (f_n_device_sum4 + 1)`.

| property | value |
|---|---:|
| mean / median / sd | 0.2423 / 0.0000 / 0.3776 |
| max | 0.9986 |
| rows exactly 0 | **63.44%** |
| rows > 0.99 | 2.69% |
| distinct values | 773 |
| tracks total / with device events / with any PMA | 59 / 38 / 30 |
| tracks with a **constant** value (std = 0) | **29 / 59 (49.2%)** |
| tracks identically 0 | 29 / 59 (49.2%) |
| overall PMA fraction of device events | 0.7718 |
| corr(track mean share, track total device events), 38 device tracks | Pearson **+0.514**, Spearman **+0.841** |
| corr(share, own activity level `f_n_device_sum4`), pooled | Pearson +0.527, Spearman **+0.804** |
| variance decomposition | total 0.14260 = between-track 0.12392 + within-track 0.01648, **ICC = 0.869** |
| corr with calendar time | pooled r **+0.084** (rho +0.073); within-track demeaned r +0.312 |

**Verdict: no — it cannot reasonably be called a technology-progress proxy.** It is a
track-level *composition / regulatory-pathway* attribute: 87% of its variance is between tracks,
half the tracks have a constant value (29/59, mostly all-zero because 21 `t_*` tracks have no
device events and 8 device tracks have only 510(k)s), 63% of rows are exactly zero, and across
device tracks it is strongly ordered by track **size** (Spearman 0.84). Its pooled correlation
with calendar time is +0.08 — no coherent progress trend. The only defensible reading is "share
of a track's recent device activity that went through the PMA (class III) pathway", confounded
with track size. In H8 it contributes **≈ 0** to the observed dAP anyway (Part 3b: +0.0003
Poisson / −0.0003 NB), so it is not the driver of the artefact — it is a mislabelled feature.

---

## Limitations and honesty notes

1. **Simulation prevalence is not matched exactly.** Real evaluable prevalence 6.34%; Poisson
   noise 4.35%, NB noise 13.07%. dAP magnitudes depend on prevalence and on `AP_B1` level
   (noise `AP_B1` 0.137 Poisson / 0.261 NB vs real 0.123). The comparison should therefore be read
   as "the real dAP is inside the pure-noise band under both plausible noise models, and the sign
   is positive in 40/40 universes", not as a calibrated p-value. Poisson is the closer match on
   `AP_B1`; NB is the closer match on dAP magnitude and on the 13+ trigger rate.
2. The simulation replicates the target, features, model and folds exactly but approximates the
   L090 clock as a one-quarter shift (`f_n_device[q] = n_device[q−1]`) instead of a 90-day
   calendar shift; 48.9% of real L090 rows are exactly equal anyway and the trailing-8 sums
   correlate 0.9983, so the approximation is benign for this question.
3. Trigger-profile comparison (3c) is qualitative (5 pooled universes); the real profile peaks
   one bucket earlier than Poisson.
4. Not done within the timebox (explicitly flagged, not hidden): a matched-prevalence simulation
   calibration; a label-permutation / circular-shift placebo on the real panel; bootstrap CIs on
   the stratum- and track-level dAPs. The pooled contrast CIs are already in the v1 results
   (+0.0115, +0.0618); the noise bands above are wider than that and centred on it.

## Bottom line

The H8 result is **not** evidence that "SciTrends-style growth features transfer to medical-device
event data". The v1 target is a *ratio against the track's own trailing activity*; the H8 block is
a set of nonlinear functions of that same activity series; the label's acceptance region is
non-monotone in that trailing activity; and a logistic model given the H8 nonlinear basis
reproduces the label at +0.0379 dAP **on a memoryless Poisson/NB process with no trend and no
change points**, with 40/40 simulated universes positive and the real value at the 45th
percentile of the NB noise distribution. Remove the ratio rule and the edge disappears
(+0.0007). Treat H8's apparent value as a **target-definition artefact**; any H8 claim in
PHOENIX-002 must first replace the ratio target with an absolute (trend- or level-conditioned)
target, or be re-tested against a mean-reverting null like the one implemented here.
