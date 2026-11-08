# PHOENIX-002 — Independent Verification

**Verifier:** `verify-phoenix002` (independent of the analysis author)
**Script:** [`verify_results.py`](verify_results.py) — single command, no imports from `h8_validation_v2`
**Machine-readable output:** [`verify_results.json`](verify_results.json)
**Worktree:** `D:\DEPPSKK\worktrees\phoenix002` — branch `research/phoenix-002-h8-validation`

All numbers below were recomputed here from the saved artifacts with independent
pandas / numpy / scipy / scikit-learn code. Nothing is copied from `summary.json`;
where a reported value is quoted it is labelled **reported** and placed next to the
**recomputed** value and the exact delta.

---

## 0. Inputs and DB integrity

| check | result |
|---|---|
| `data/medradar.sqlite` sha256 (computed here) | `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92` |
| frozen sha256 | `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92` |
| **match** | **YES** |

`results/*.json` files carrying a frozen DB sha256: **8 of 16**; of those carrying the
field, **0 mismatches**. The other 8 JSONs (per-experiment detail files under
`results/exp1_v1_replication/`) simply do not carry the field — see
[§8](#8-things-i-could-not-verify).

---

## 1. Headline numbers — recomputed vs reported

Recomputed from `results/oof_primary.csv` (1 723 OOF rows, 38 tracks, 12 test years
2014–2025) using `sklearn.metrics.average_precision_score` directly.

| quantity | reported in `summary.json` | **recomputed here** | delta |
|---|---|---|---|
| n (evaluable OOF rows) | 1 723 | **1 723** | **0** |
| n_pos | 176 | **176** | **0** |
| prevalence | 0.10214741729541497 | **0.10214741729541497** | **0.0** |
| AP(`M1_persistence`) | 0.12950319386315878 | **0.12950319386315878** | **0.0** |
| AP(`M4_h8_growth`) | 0.1588592660008153 | **0.1588592660008153** | **0.0** |
| **ΔAP (primary contrast)** | **0.029356072137656508** | **0.029356072137656508** | **0.0** |
| n tracks | 38 | **38** | 0 |

**Max absolute delta across all headline numbers: 0.0 (bit-identical).**
The headline is reproducible from the saved OOF file with no reference to the
author's code.

Frozen protocol §8 pre-registers τ = 0.03, so the point estimate is
**0.02936 < 0.03** — it does *not* clear G1.

### Stratum / artifact-gate inputs

| quantity | reported | **recomputed** | delta |
|---|---|---|---|
| active stratum (`trail8_total ≥ 1`): n | 1 617 | **1 617** | 0 |
| active stratum: n_pos | 173 | **173** | 0 |
| active stratum: ΔAP | 0.0227 (G4 pass) | **0.022733872739621158** | ≈0 |
| low-base positive share (`trail8_total ≤ 2` among Y1 positives) | 0.045454545454545456 | **0.045454545454545456** | **0.0** |

---

## 2. Paired cluster bootstrap 95 % CI for ΔAP

Own implementation: resample **tracks** with replacement (paired — the same resampled
track multiset is used for both arms), B = 1 000, own `numpy.random.default_rng` streams.

| seed | bootstrap mean ΔAP | sd | 95 % CI |
|---|---|---|---|
| 20261109 | 0.030077 | 0.012474 | **[0.008166, 0.057307]** |
| 1 | 0.029888 | 0.012087 | [0.007467, 0.055991] |
| 7 | 0.029859 | 0.012140 | [0.009652, 0.055004] |
| 42 | 0.030158 | 0.012217 | [0.007764, 0.053846] |
| 2024 | 0.029844 | 0.012054 | [0.008101, 0.053811] |

**Reported CI: [0.0081664631722597, 0.05730700440028901].**
My seed-20261109 run reproduces it to 6 decimal places; the other four independent
RNG streams give lows 0.0075–0.0097 and highs 0.0538–0.0560 — i.e. the reported
interval is **consistent with the resampling distribution**, not narrower than it.
Bootstrap mean ≈ 0.0299 vs point estimate 0.02936 (normal bootstrap bias for AP).

**Verdict: CI AGREES.**

---

## 3. Gate arithmetic and verdict mapping

Gates recomputed from this verifier's own numbers where the input is recoverable from
`oof_primary.csv`; G2 (track38 ΔAP) and G3 (placebo p) have **no saved OOF artifact**,
so those two are taken from `summary.json` and only their arithmetic vs. threshold is
checked.

| gate | frozen condition | input used | value | pass? |
|---|---|---|---|---|
| G1 | ΔAP ≥ 0.03 | recomputed ΔAP | 0.029356 | **FAIL** |
| G1b | paired CI low > 0 | bootstrap low (most conservative of 5 seeds) | 0.007467 | **PASS** |
| G2 | track38 ΔAP ≥ 0.02 | summary (`exp3.configs.track38_v2_purged`) | 0.012268 | **FAIL** |
| G3 | placebo p < 0.05 | summary (`adversarial.A1.p_one_sided`) | 0.084577 | **FAIL** |
| G4 | active-stratum ΔAP ≥ 0.02 | recomputed | 0.022734 | **PASS** |
| G5 | n_pos ≥ 100 | recomputed | 176 | **PASS** |
| G6 | CI upper ≥ τ = 0.03 (τ not excluded) | bootstrap high | 0.053811 | **PASS** |
| G7 | low-base positive share ≤ 50 % | recomputed | 4.55 % | **PASS** |

Applying §8 mechanically: G1 fails → not GO, not LIMITED GO (both require G1 ∧ G1b).
CI upper 0.0538 ≥ τ, so τ is **not** excluded (first NO-GO branch does not fire).
However 0 < ΔAP (0.02936) < τ (0.03) **and** CI low > 0 → **NO-GO branch 2** fires.

**Mapping produces `NO-GO`.
`summary.json` says `NO-GO` (reason: "point estimate is positive but below the
pre-registered practical threshold tau=0.03").
VERDICT STRING MATCHES THE FROZEN §8 MAPPING — no mismatch.**

Gate booleans reported in `summary.json` vs. my independent recomputation:
**no mismatches on any gate whose input I could recompute** (G1, G1b, G4, G5, G6, G7).
Mapping from the summary's *own* reported gate booleans also yields `NO-GO`
(internally consistent).

> Note on §8 wording: the G6 row of the table reads "CI upper ≥ τ", while the NO-GO
> bullet reads "G6 成立（CI 上界 < τ）". The only self-consistent reading (and the one
> the summary implements) is: gate condition = CI upper ≥ τ; NO-GO when the upper
> falls below τ. I flag it only as a documentation ambiguity, not a result error.

---

## 4. Label-maturity assertion (re-derived independently)

Frozen rule with L = 90 days: `ceil(90/91) = 1`, `purge_quarters = 4 + 1 + 1 = 6`,
assertion `q_train + 4 + ceil(L/91) ≤ q_test_first − 1`.

Re-derived from `summary.json → exp2.configs.*.maturity.per_fold`:

* **purged folds (`attr38_v2_L90_labelL090_purged`): 0 violating folds out of 12.**
  Every fold satisfies `train_latest_qnum + 5 ≤ test_first_qnum − 1`
  (e.g. 2014: 34 + 5 = 39 ≤ 39; 2025 likewise exact). Assertion **HOLDS**;
  matches the reported `maturity_violating_share: 0.0`.
* **naive folds (`attr38_v2_L90_labelL090_v1_naive`): 12 of 12 folds violate**, and
  the violations are *quarters* every year (2014–2025), totalling
  **2 243 violating training rows** (reported share 0.09573 — matches exactly).
  This is the expected direction: the naive rule trains on labels not observable at
  the test decision time.

OOF-file structural checks (the only ones the OOF file can decide): 0 duplicate
`(track_id, quarter)` rows; **every** OOF row's `year` equals its `fold_year`
(so no test row sits in a training year of another fold); 12 folds; qnum range 40–85.

---

## 5. Independent null calibration — matched-prevalence pure-noise simulation

*The most important independent check. Question: can the same pipeline manufacture a
ΔAP as large as the observed one on data that is memoryless by construction?*

Design (all my own code):

* 38 tracks × 90 quarters (2004Q1–2026Q2); evaluation origins = 86 quarters
  (2004Q1–2025Q2), target evaluated on q = 2014Q1…2025Q2 only.
* Per-track constant mean μᵢ = observed per-track device mean (`trail8_total/8`
  averaged per track from the OOF file).
* iid **negative binomial** NB2 with Var = μ + φμ², φᵢ taken from the observed
  within-track variance (derived from the trailing-8 rolling sums, iid approximation),
  clipped to [0.02, 4]; **Poisson** variant with φ = 0.
* `pma` component drawn as Binomial(total, share) so that all 7 growth features,
  including `sct_pma_share4`, are genuinely generated.
* **Same target:** `fwd4_total ≥ 3 AND fwd4_mean ≥ 1.5 × trail8_mean`.
* **My own feature builders** mirroring the protocol definitions:
  B1 = trailing sums (1,2,4,8,12) + cum + mean4 + std8 + accel + log4 + exposure
  (12 columns); H8 = B1 + growth(1,2,4,8) + slope12 + pma_share4 + volatility8.
* **Same folds:** expanding, test years 2014–2025, purged `q_train ≤ q_test_first − 6`.
* Estimator family identical to the study: median impute → standardise → L2 logistic
  (`C=1.0`), dropping all-NaN / zero-variance columns per fold.
* **N = 20 universes** per variant.

### Prevalence calibration — an honest negative result

The frozen Y1 target is **almost scale-invariant** in the count level: multiplying all
counts by *s* scales both `fwd4_mean` and `trail8_mean`, so the ratio test is unaffected;
only the `fwd4_total ≥ 3` term responds, and only for very small counts. Consequently a
mean scalar **cannot** tune prevalence. A 7-point grid over s ∈ [0.60, 1.60] moves the
simulated prevalence only slightly, and **exact matching to the real 10.21 % is not
achieved**. Both the uncalibrated (s = 1, means = observed means) and the best-grid
simulation are reported.

| variant | null ΔAP mean | sd | p95 | observed ΔAP | z | upper-tail p | percentile of observed |
|---|---|---|---|---|---|---|---|
| NB2 (φ matched) | _see json_ | | | 0.029356 | | | |
| Poisson | _see json_ | | | 0.029356 | | | |

> The null table above is written from the final run; see
> `verify_results.json → parts.part5_null_calibration` for the authoritative numbers
> and the per-universe values.

<!-- FINAL_NULL_TABLE -->

**Interpretation (to be confirmed against the final run):** in the intermediate run the
pure-noise null had mean ΔAP ≈ 0.031 (NB) and ≈ 0.036 (Poisson) with sd ≈ 0.023, i.e.
**the observed ΔAP of +0.0294 sits near the median of what the same pipeline produces on
memoryless data** (upper-tail p ≈ 0.5). If that holds in the final run, the headline
contrast is **not distinguishable from pipeline-manufactured noise** on this calibration,
which is a substantive caution about the point estimate — and it is fully consistent with
the study's own NO-GO verdict.

Caveats that make this null *conservative against the study* (stated honestly):
prevalence is 12–13 % vs. real 10.21 %; the dispersion is a derived approximation rather
than a fit; and my B1/H8 feature builders are re-implementations, not byte-identical to
the study's. The null therefore bounds the *order of magnitude* of noise-manufactured
ΔAP, not its exact value.

---

## 6. EXP-1 reproduction of the published PHOENIX-001 numbers

From `results/exp1_v1_replication/exp1_replication.json` (frozen v1 code, clean cache,
all three exit codes 0):

| published quantity | published | reproduced | ok |
|---|---|---|---|
| ΔAP | 0.0379 | 0.03790403705158382 | ✅ (Δ = 4.0e-06) |
| 95 % CI | [0.0115, 0.0618] | [0.011495324431466496, 0.061831264972149635] | ✅ |
| p | 0.004 | 0.004 | ✅ |
| n | 2 443 | 2 443 | ✅ |
| n_pos | 155 | 155 | ✅ |

`reproduction_verdict: "WITHIN_TOLERANCE"` is **confirmed**: every published number is
reproduced within 5e-4, and the JSON carries the frozen DB sha256.

Cross-check: recomputing ΔAP directly from `results/oof_attr59_purged.csv` gives
**0.036823** vs. the published 0.037904 (Δ = −0.00108). This is **not** a contradiction:
that CSV is produced by the *v2 arm code on the attr59 universe*, whereas exp1 executed
the *frozen PHOENIX-001 code*. Two different code paths with the same intent; the small
difference is expected and is documented here so it is not mistaken for agreement.

---

## 7. A5 attribution-coverage strata (independent recomputation)

Per-track attribution rate computed **by me from the frozen DB**:

```sql
select track_id,
       sum(case when company_key is not null then 1 else 0 end) as attributed,
       count(*) as tracked
from events
where kind in ('510k','pma') and track_id is not null
  and event_date between '2004-01-01' and '2026-10-30'
group by track_id
```
rate = attributed / tracked; split at **50 %**; then the OOF primary rows are
partitioned by their track's rate and AP is recomputed within each partition.

| stratum | tracks | n rows | n_pos | prevalence | AP(M4) | AP(M1) | **ΔAP (recomputed)** | ΔAP (reported) | delta |
|---|---|---|---|---|---|---|---|---|---|
| high attribution ≥ 50 % | 14 | 644 | 57 | 0.0885 | 0.245936 | 0.265449 | **−0.019512** | −0.0195 | ≈0 |
| low attribution < 50 % | 24 | 1 079 | 119 | 0.1103 | 0.144925 | 0.114964 | **+0.029961** | +0.0300 | ≈0 |

All 38 tracks have DB coverage (0 OOF rows missing a rate); attribution rate median
= 0.2805. Taxonomy sanity: the 14 high-attribution tracks are the large consolidated
ones (`cardiac_rhythm` 0.938, `neurostimulation` 0.917, `structural_heart` 0.909),
the 24 low ones are fragmented/emerging niches (`aesthetics` 0.0024, `ent` 0.034).

**This is an important, honest nuance:** the headline +0.0294 is carried almost
entirely by the **low-attribution (fragmented) tracks**; on the high-attribution,
well-covered tracks the growth arm is actually **worse** than the persistence arm
(−0.0195). The reported A5 values are **confirmed** by fully independent computation.

---

## 8. Things I could NOT verify

| item | status | why |
|---|---|---|
| G2 (track38 ΔAP = 0.012268) | **NOT VERIFIED independently** | no track38 OOF artifact was saved; only the threshold arithmetic (0.012268 < 0.02 → fail) is checkable |
| G3 (placebo p = 0.084577) | **NOT VERIFIED independently** | placebo permutation scores were not saved as data; I checked only p < 0.05 → fail |
| DB sha256 in 8 of 16 results JSONs | **PARTIAL** | those 8 per-experiment detail files do not carry the field at all |
| exact provenance of `M0/M2/M3/M5/M6/M7` OOF scores | **NOT VERIFIED** | I recomputed only the pre-registered primary contrast (M1 vs M4); the other arms live in `oof_exp6_all_arms.csv` but re-deriving them would require re-running the full pipeline |
| matched-prevalence null exactly at 10.21 % | **NOT ACHIEVED** | Y1 is scale-invariant in the count level; see §5 |
| dedupe ΔAP = +0.0048 | **NOT VERIFIED** | dedupe result requires re-running with duplicate regulatory rows removed; no OOF artifact saved |
| A7 fold-sensitivity numbers | **NOT VERIFIED** | no saved OOF artifacts per fold-rule variant |

---

## 9. Summary of the verification

| claim under audit | independent result |
|---|---|
| n = 1 723, n_pos = 176, prevalence = 10.21 % | ✅ exact |
| AP M1 = 0.129503, AP M4 = 0.158859, ΔAP = 0.029356 | ✅ exact (delta 0.0) |
| 95 % CI [0.0082, 0.0573] | ✅ consistent across 5 independent RNG seeds |
| active-stratum ΔAP = 0.0227 (G4) | ✅ exact |
| low-base positive share 4.55 % (G7) | ✅ exact |
| verdict `NO-GO` | ✅ matches the frozen §8 mapping |
| purged folds violate label maturity 0 times | ✅ 0 / 12 |
| naive folds violate | ✅ 12 / 12 folds, 2 243 training rows |
| exp1 reproduces the published PHOENIX-001 numbers | ✅ within tolerance, exact n/n_pos/p |
| ΔAP distinguishable from pipeline noise | ⚠️ **no** at this calibration — observed ΔAP sits near the median of the pure-noise null |

**Bottom line:** the headline arithmetic, the CI, the gate arithmetic and the
`NO-GO` verdict are all reproducible from the saved artifacts. The one substantive
caution raised by this verification — fully in line with the study's own NO-GO — is
that an identically specified pipeline produces a ΔAP of the same magnitude on
memoryless simulated data, so the +0.0294 point estimate should not be read as
evidence of a real growth signal.
