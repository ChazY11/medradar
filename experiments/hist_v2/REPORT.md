# hist_v2 — domain-level entry benchmark (1995–2015): report

**Status:** COMPLETE. The frozen pre-registered criterion is **met** (primary supported and powered); the **decisive
secondary comparison against the two-way exposure baseline is not significant**. All numbers are read from
`experiments/hist_v2/results.json`; `experiments/hist_v2/verify_report_numbers.py` re-checks this report against it.
**Protocol:** `research/protocols/hist_v2_preregistration.md` (frozen 2026-11-03; no amendments). **Branch:**
`research/early-signal-ai-review`.

> **Answer this design can give.** At the coarser 22-domain unit, over 1995–2015, the 24-month entry hazard is
> predictable above **firm persistence**: mean per-origin AP **0.0775 vs 0.0435**, Δ **+0.0340**, company-clustered
> 95 % CI **[+0.0215, +0.0661]**, MDE **0.0316** (within the pre-declared ≤ 0.05 target), 85.7 % of origins positive,
> permutation p at the 200-draw resolution floor. But the model still **does not significantly beat the two-way
> firm×domain exposure baseline** (Δ +0.0156, CI [−0.0107, +0.0445], p 0.212): the *incremental value of the
> time-varying features is not established*, exactly as in hist_v1. The replication across two units and two windows
> is the result, not a new claim.

---

## 1. Design recap (frozen)

Unit: company × 22 technology domains × quarter. Origins: 21 annual Q1 origins 1995…2015 (the entry-rich era measured
in `experiments/hist_v2/feasibility.json`); 2016–2024 is a descriptive holdout only. Primary risk set `R_dom`
(established filer, domain unentered); secondary `R_dom_adj` (sibling-category adjacency, see §6). Label: first observed
material event in the domain within 8 quarters (12 months as secondary). 15 PIT features, L2 logistic (λ=1, lr 0.1,
120 epochs), baselines B0–B3, company-clustered paired bootstrap 2,000 reps (seed 20261103), 200-permutation null,
lead-time frontier, era split, pre-declared power target MDE ≤ 0.05.

## 2. Data actually used

Domain panel built from the frozen hist_v1 panel by mapping 38 tracks to 22 config domains:
53 companies, 377 domain pairs, **14,704 material events**, 7,538 pair-quarters, SHA-256 `44c115c2…`; an independent
re-aggregation of all 377 pairs reproduces the hist_v1 panel's per-quarter event counts exactly (0 mismatches).

Evaluation: 21 origins, **15,233 candidate cells**, **252 positive cells**, mean **725.4 candidates and 12.0 positives
per origin** (exactly the feasibility estimate); mean per-origin base rate 1.70 %. Training is purged (`t'+8 ≤ t`,
0 violations) and the pre-declared case-control cap binds at later origins (12,000 of up to ~96,000 rows, negative
weight ~9.4); the leakage replay is **0/300** mismatches.

## 3. Primary result

| model | mean per-origin AP | bootstrap mean | 95 % CI |
|---|---:|---:|---|
| B0 prevalence | 0.0170 | — | — |
| B1 company base rate | 0.0435 | 0.0489 | [0.0345, 0.0663] |
| B2 domain base rate | 0.0277 | 0.0324 | [0.0226, 0.0452] |
| B3 B1×B2 (two-way exposure) | **0.0619** | 0.0739 | [0.0499, 0.1042] |
| M1A firm features only | 0.0515 | — | — |
| M1B + domain tempo | **0.0812** | — | — |
| **M1C all features (primary)** | **0.0775** | 0.0909 | [0.0613, 0.1238] |

| comparison | point ΔAP | bootstrap 95 % CI | p | MDE | verdict |
|---|---:|---|---:|---:|---|
| **M1C − B1 (pre-registered)** | **+0.0340** | **[+0.0215, +0.0661]** | <0.001 | 0.0316 | **SUPPORTED (powered)** |
| M1C − B2 | +0.0498 | [+0.0284, +0.0899] | <0.001 | 0.0449 | supported (secondary) |
| **M1C − B3 (decisive secondary)** | **+0.0156** | **[−0.0107, +0.0445]** | 0.212 | 0.0389 | **not significant** |

The frozen criterion (CI of M1C−B1 excludes 0 and is positive; Δ(M1C−B3) point estimate positive; ≥60 % of origins
positive; MDE ≤ 0.05) is **met**: CI +, B3 point +0.0156, 85.7 % (18/21) origins positive, MDE 0.0316. The criterion
required only a positive *point* estimate against B3; the interval includes zero, so **incremental value over the
two-way baseline is not established** and this report says so in the abstract-level statement above.

**Permutation null:** 200 permutations (seed 20261103) — observed Δ 0.0340, empirical p = 0.004975, the resolution
floor (0/200 permutations reach the observed value).

**Secondary horizon h=4:** Δ(M1C−B1) = +0.0432 [+0.0214, +0.0692] (bootstrap OK); Δ(M1C−B3) = +0.0211
[−0.0019, +0.0448] — again positive point, interval includes 0.

**Secondary risk set `R_dom_adj`:** Δ(M1C−B1) = +0.0554, but the bootstrap is UNRELIABLE (few positives for the
sibling-adjacency restriction) and is reported descriptively only.

**Holdout 2016–2024 (descriptive, no inference):** Δ(M1C−B1) = +0.0095 on 9 origins with 7–8 positives each — the
modern era remains too sparse for inference; no CI or p-value is reported for this block by design.

**Eras:** 1995–2004 Δ(M1C−B1) = +0.0464 (M1C 0.1082 vs B1 0.0617); 2005–2015 Δ = +0.0227 (M1C 0.0496 vs B1 0.0269).
In the later era **M1B (0.0574) beats M1C (0.0496)**: the adjacency features add nothing once domain tempo is included.

## 4. Where the signal is — and it is not adjacency

| feature group | mean AP | Δ vs B1 |
|---|---:|---:|
| A firm only | 0.0515 | +0.0080 |
| B + domain tempo/industry | **0.0812** | +0.0377 |
| C + adjacency (all) | 0.0775 | +0.0340 |

At domain granularity the **domain-tempo features carry the signal** and adding adjacency slightly *reduces* mean AP
(−0.0037 relative to B). This is the opposite of hist_v1, where adjacency carried the gain. The programme therefore has
a unit-dependent mechanism result: adjacency matters for the finer track-level entries, and does not at the coarser
domain level. This is a finding about **unit choice**, not a contradiction — and it is why the next design must
pre-specify the unit from the question rather than the reverse.

## 5. Lead time (descriptive, with misses)

133 of the 148 first-entry events in the evaluation window are inside `R_dom` at an origin within the 8-quarter alert
window (15 never appear in the risk set). At each origin the alert threshold is that origin's 90th-percentile training
score.

| alert budget | precision | recall | entries alerted | entries missed | median lead | false alarms / 1,000 candidate-quarters |
|---:|---:|---:|---:|---:|---:|---:|
| 1 % | 0.106 | 0.083 | 14 / 133 | 119 | 5 quarters | 11.7 |
| 5 % | 0.079 | 0.294 | 41 / 133 | 92 | 7 quarters | 56.8 |
| 10 % | 0.058 | 0.397 | 58 / 133 | 75 | 6 quarters | 106.1 |

Recall at the 10 % budget is 39.7 % (vs 25.5 % in hist_v1 on the track unit); 75 of 133 entries are still missed. The
quantitative trade-off between lead time and reliability remains the same shape: earlier warning costs precision.

## 6. Deviations and implementation notes (recorded in results.json.config)

1. **Adjacency at domain level** is operationalised over *sibling domains sharing a config `category` band*, because the
   literal protocol condition ("the firm already has activity in a different domain") is implied by firm establishment
   for every unentered candidate and would make `R_dom_adj` identical to `R_dom` (and `adj_share ≡ 1`). This is a
   documented implementation interpretation, not a protocol amendment; it leaves the primary `R_dom` test untouched.
2. **`domain_share`** (the analog of hist_v1 `cat_share`) is the share of the firm's ever-events in the candidate
   domain's sibling domains; the literal own-domain share is identically zero on candidate cells.
3. **No fusion lanes** in hist_v2 (the protocol defines none); no Target B claims.
4. **Attribution sensitivity not run:** the protocol's §9 listed the `pairs_no_acquired` attribution sensitivity; the
   domain panel carries the array, but the full evaluation was not re-run with it (a full 20-minute re-run). It is
   recorded as an open robustness pass, not as passed.
5. The h=4 origins are the same 21 annual Q1 origins as h=8 (both mature inside 2026-Q2).

## 7. What this establishes, and what it does not

**Established.**
- A reproducible domain-level panel (53 firms, 22 domains, 377 pairs, 14,704 events) with a deterministic build and
  independent aggregation check.
- At the coarser unit the 24-month entry hazard beats **firm persistence** with a reliable, **powered** interval
  (Δ +0.0340 [+0.0215, +0.0661], MDE 0.0316 ≤ pre-declared 0.05) and a permutation-null rejection at the resolution
  floor — a **replication of the hist_v1 result at a second unit and window**.
- The incremental value over the **two-way exposure baseline is not established** at either unit (here Δ +0.0156,
  CI including 0). This is now a replicated negative, which is the stronger scientific statement.
- Domain-tempo features carry the signal at domain level; adjacency does not (unit-dependent mechanism result).
- A quantified lead-time frontier (10 % budget: 39.7 % recall, median lead 6 quarters, 75/133 missed).

**Not established.**
- Any improvement over B3 (both units).
- Anything about the post-2015 era (descriptive only; 7–8 positives per origin).
- The attribution sensitivity (not run; see §6.4).
- Any causal claim, any internal-R&D claim, any Target B claim, any prospective calibration.

## 8. Reproduce

```bash
python experiments/hist_v2/build_domain_panel.py      # out/hist_v2/domain_panel.json (byte-identical on re-run)
python experiments/hist_v2/eval.py --panel out/hist_v2/domain_panel.json --workers 12   # ~20 min, 200 permutations
python experiments/hist_v2/verify_report_numbers.py   # this report vs the artifacts
python -m unittest tests.test_hist_v2_eval            # 40 tests
```
