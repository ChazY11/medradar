# B-017 — fixed-cohort sensitivity run on the cycle-2 P2 entity panel (b102)

Worktree `D:\DEPPSKK\worktrees\es-ai-review`, branch `research/early-signal-ai-review`.
Input DB: `data/research.sqlite` sha256 `dd241bfec138d797…` (same digest as the committed
`config/universe_v1.json` source), opened read-only. Nothing in the frozen cycle-2 files was
changed; this run only re-runs the P2 pipeline on a **fixed** cohort.

## Answer

**The conclusion is unchanged.** With the cohort pinned to the artefact's exact 200 entity
keys, the P2 headline becomes pooled ΔAP **+0.095211** vs MDE **0.087630** (committed:
+0.097321 vs 0.087689), and the cluster CI on ΔAP still excludes zero in **3/3 holdout
windows under both clusterings** (entity and company×track). Direction, sign stability,
magnitude (97.8% of the committed ΔAP) and the pre-registered H2.2 rule all hold.

The 5/200 gap is real and its net metric effect is small (pooled ΔAP −0.0021; largest
per-window shift −0.0067); it is caused by *universe code drift*, not by the five keys
themselves (see below).

## What was run

Exact frozen P2 specification, cohort replaced by the artefact's keys:

| element | value |
|---|---|
| panel builder | `experiments.cycle2_coverage.panel.build_entry_panel` (committed, reused) |
| entity key | deterministic `normalise_applicant` → `entity_key` (no fuzzy matching) |
| cohort | `config/universe_v1.json["cohort"]["entity_keys"]`, 200 exact keys, **not recomputed** |
| features | `rd_plus_entry_history`, 16 features (no financials) |
| horizon / dormancy / origins | 12 months / 36 months / quarterly |
| purge | `cutoff + 12 months <= origin` |
| holdouts | 3 (2025-04-01, 2025-07-01, 2025-10-01; the last three evaluable origins) |
| model | `LogisticBaseline(epochs=180, learning_rate=0.15, l2=1.0)` |
| comparator | per-pair persistence base rate (same as committed analysis) |
| inference | cluster bootstrap, 2,000 resamples, seed 7; ΔAP vs paired baseline; MDE from entity-cluster SE |

`run_fixed_cohort.py` also runs the **full** `run_backtest` (all origins) and asserts that the
per-window AP from the full backtest equals the per-window prediction fits to 1e-9, so the
window metrics used here are the frozen spec's own numbers.

Panel comparison:

| | committed P2 (recomputed cohort) | fixed cohort (artefact keys) |
|---|---:|---:|
| examples | 161,636 | 161,419 |
| positives | 1,082 | 1,072 |
| entities / tracks / origins | 193 / 38 / 24 | 193 / 38 / 24 |
| material events in cohort | 8,632 | 8,623 |
| coverage | 2016-11-01 .. 2026-10-16 | 2016-11-01 .. 2026-10-16 |

Of the 200 artefact keys, **7 have no usable tracked panel event** in the current store
(`hardy-diagnostics-acc754f9`, `hartalega-ngc-f9a1db94`, `liofilchem-3590e134`,
`o-m-halyard-bdf9bf76`, `orthocon-249e1a94`, `siemens-healthcare-diagnostics-products-d55ee10a`,
`thermo-fisher-scientific-bc0d5cbb`); an eighth (`surgentec-fc099756`) has tracked events only
after the last evaluable origin, so it enters the event count (193 usable entities) but produces
no example row (192 entities appear in examples).

## Old vs new — per window

| origin | rows | pos | model AP old → new | pair-base AP old → new | ΔAP old → new | Δ change | CI excl. 0 (entity / pair) |
|---|---:|---:|---|---|---|---:|---|
| 2025-04-01 | 6,890 → 6,891 | 41 → 42 | 0.083252 → 0.083335 | 0.025087 → 0.025270 | 0.058165 → 0.058065 | −0.000100 | yes/yes → yes/yes |
| 2025-07-01 | 6,890 → 6,891 | 46 → 47 | 0.149928 → 0.148838 | 0.030997 → 0.031248 | 0.118931 → 0.117590 | −0.001342 | yes/yes → yes/yes |
| 2025-10-01 | 6,891 → 6,892 | 53 → 52 | 0.192212 → 0.184980 | 0.042947 → 0.042443 | 0.149265 → 0.142536 | −0.006729 | yes/yes → yes/yes |

## Old vs new — pooled

| quantity | committed | fixed cohort |
|---|---:|---:|
| rows / positives | 20,671 / 140 | 20,674 / 141 |
| model AP | 0.129189 | 0.126987 |
| pair-base AP | 0.031868 | 0.031776 |
| **ΔAP** | **0.097321** | **0.095211** |
| entity CI [low, high] | [0.042609, 0.169722] | [0.040998, 0.164244] |
| pair CI [low, high] | [0.049106, 0.158317] | [0.046478, 0.157435] |
| bootstrap SE (entity / pair) | 0.031300 / 0.027715 | 0.031279 / 0.028009 |
| p(ΔAP ≤ 0), entity / pair | 0.0000 / 0.0000 | 0.0005 / 0.0000 |
| **MDE from observed SE** | **0.087689** | **0.087630** |
| ΔAP > MDE | yes | yes |

Verdict block: `direction_unchanged = true`, `sign_stable_positive = true`,
`windows_excluding_zero_unchanged = true`, `rule_satisfied_unchanged = true`,
`conclusion_unchanged = true`, `magnitude_retained = 0.9783`.

## The 5/200 gap, quantified

The artefact cohort and today's recomputation agree on **195/200** keys:

- only in the artefact (5): `resmed-c6c5d1cf` (Resmed Corp), `si-bone-aac3a36e` (SI-BONE),
  `sonoscape-medical-b154c140` (Sonoscape Medical), `tandem-diabetes-care-c365c570`
  (Tandem Diabetes Care), `zhejiang-innuovo-rehabilitation-devices-c2a04b1b`
  (Zhejiang Innuovo Rehabilitation Devices);
- only in the recomputation (5): `cook-ireland-4fd2deea` (Cook Ireland),
  `foundation-medicine-e8a2f38b` (Foundation Medicine), `medtronic-minimed-4064e4dd`
  (Medtronic Minimed), `medtronic-vascular-a716a021` (Medtronic Vascular),
  `ventana-medical-systems-0f10151a` (Ventana Medical Systems).

Rows attributable to the swapped keys: artefact-only keys contribute 4,050 panel rows /
12 positives; recomputed-only keys contribute 4,267 rows / 22 positives. The net
−217 rows / −10 positives **exactly equals** the whole-panel difference, so the panel-level
difference is entirely the swap; the small *holdout* row/positive differences (+3 rows,
+1 positive pooled) come from the per-origin active-entity/track sets shifting when the keys
change.

**Why the gap exists (measured):** at the *same* DB sha256, the current universe builder yields
4,354 entities versus 4,632 entity records in the artefact (278 keys absent today) and 33
shared entities whose `n_material`/`active_years` differ; even `select_cohort` over the
artefact's own records does not reproduce the artefact cohort (the build additionally pinned
one entity per mandated focus company and replaced the lowest-ranked entry). This is
**code/version drift in entity preparation between the branch that produced the artefact and
HEAD**, not data drift — the committed cohort cannot be reproduced from HEAD code, which is
exactly what B-017/D-008 asked to quantify.

## Does the conclusion survive the 5-key exclusion/replacement?

Yes. Against the committed numbers (ΔAP +0.0973, MDE 0.0877, 3/3 windows):
ΔAP +0.0952, MDE 0.0876, 3/3 windows under both clusterings, both pooled CIs exclude zero,
sign stable, ΔAP still exceeds its MDE. The acceptance answer is **"conclusion unchanged;
the fixed-cohort effect is 97.8% of the committed effect and remains above the MDE."**

## Reproduction

```
python experiments/b102_cohort_sensitivity/run_fixed_cohort.py               # full run
python experiments/b102_cohort_sensitivity/run_fixed_cohort.py --skip-backtest  # fast (3 window fits)
python -m unittest tests.test_fixed_cohort                                   # 20 tests
```

Outputs: `fixed_cohort_report.json` (all numbers above, plus the prediction-level inference,
per-window table, gap lists and artefacts), `backtest_fixed_cohort.json` (full `run_backtest`
artefact). The full backtest was run and its three holdout-window APs equal the per-window
prediction-fit APs to 1e-9 (asserted in `run()`). Output is deterministic by construction — no
timestamps are recorded, all JSON is sorted-key, and the synthetic end-to-end test re-runs
byte-identically.

## Honest limits

- This is a **sensitivity run on the artefact's cohort keys**, not an exact reproduction of the
  committed panel: HEAD's entity preparation differs (278 universe records absent, 33 drifted),
  so the panel is the current pipeline on the curated key list.
- The committed P2 cohort is itself not reproducible from HEAD; the fixed run removes the
  cohort-selection variance but not the entity-prep drift.
- Holdout label windows overlap by design (three consecutive quarterly origins), as in the
  committed artifact; AP comparisons are restricted to the paired holdout rows.
- The per-window ΔAP is a paired bootstrap over entity and pair clusters (same conventions as
  `analyze_cycle2.py`); the MDE is the normal-approximation value from the observed entity-
  cluster SE, not a design-stage value.
