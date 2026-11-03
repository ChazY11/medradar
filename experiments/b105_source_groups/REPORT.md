# B-018 — source-group re-test on the P2 entity panel, with MDEs (b105)

Worktree `D:\DEPPSKK\worktrees\es-ai-review`, branch `research/early-signal-ai-review`.
Store: `data/research.sqlite` (read-only). The frozen cycle-2 P2 panel and the committed
`reverse_rd_v2` ablation files were not modified.

## Answer

**No source group adds ranking value on the P2 entity panel, and every point estimate is
negative.** The harness is faithful: the 16-feature reference re-fitted on the frozen P2
panel reproduces the committed P2 window and pooled APs **exactly** (all three windows and
pooled to 1e-9).

| group added to the 16 reference features | ΔAP (pooled) | company-clustered 95% CI | MDE (ΔAP) | verdict |
|---|---:|---|---:|---|
| financial (11 features) | −0.015058 | [−0.036061, +0.000317] | 0.026360 | **underpowered** |
| market (8 features) | −0.013181 | [−0.033461, −0.0000019] | 0.024151 | **negative association** (CI excludes zero below; not a null) |
| publication (5 features) | −0.010438 | [−0.030600, +0.002854] | 0.024131 | **underpowered** |

The two nulls (financial, publication) are **not** well-powered at the pre-declared
0.02 ΔAP bound: their MDEs are 0.024–0.026, so effects of that size cannot be excluded —
none of these results is an unqualified "no effect". The market group is worse than the
reference at the 5 % level (upper CI edge is 1.9e-6 below zero): a detectable anti-signal,
not a null.

## Design (frozen, reused)

| element | value |
|---|---|
| panel | `experiments.cycle2_coverage.run_cycle2.build_p2` — 161,636 examples, 1,082 positives, 193 entities, 24 origins, 2016-11-01..2026-10-16 |
| reference features | `rd_plus_entry_history`, 16 features |
| group features | frozen builders: `financial_features.FEATURES` (11), `market_features.FEATURES` (8), `publication_features.PUBLICATION_FEATURES` (5) |
| rows/origins | identical for all four specs; holdouts 2025-04-01 / 2025-07-01 / 2025-10-01 |
| purge | `cutoff + 12 months <= origin` |
| model | `LogisticBaseline(epochs=180, learning_rate=0.15, l2=1.0)` |
| inference | pooled AP over the 3 holdout windows; paired **company-clustered** bootstrap, 2,000 resamples, seed 20261103 (parent-company cluster where the exact join exists, entity otherwise); MDE = `evalstats.mde_from_se(se_delta)` |
| pre-declared rule | evaluable if ≥20 % of holdout rows **and** ≥20 holdout positives carry the group; a null is "well-powered negative" only if MDE ≤ 0.02 ΔAP, else "underpowered"; a CI excluding zero (either side) is never a null |

Feature definition reuse: the frozen builders were called per (parent company, cutoff); only
the row→company dispatch is new, because the frozen `attach_*` helpers read
`example["company_key"]`, which on this panel is the *entity* key, not a parent company.
No new feature definition was introduced (deviation stated explicitly).

## Entity → company join (the binding constraint)

P2 rows are deterministic applicant entities; the source tables are company-level. The join
is exact and uses the store's own linkage, never a name/alias proxy: an entity maps only when
its exact `entity_key`'s 510(k)/PMA rows carry **exactly one** distinct `company_key`.

- 71 of the 193 panel entities (40 parent companies) map; **0 ambiguous**; no name matching.
- 59,026 / 161,636 panel rows (36.5 %) inherit any company-level features; the other 63.5 %
  cannot be joined and are reported NOT_EVALUABLE for every group — **no proxy substituted**.
- Holdout coverage (rows / positives with the group, of 20,671 / 140):
  financial 4,822 (23.3 %) / 56; market 5,995 (29.0 %) / 62; publication 7,496 (36.3 %) / 81.
  All above the pre-declared floor, so all three groups are evaluable.
- Source tables: financial_facts 43,420 rows / 32 companies; market_bars 40 tickers (38
  companies with complete features); publication_counts 51 companies / 616 annual counts.

## Per-window AP and ΔAP

| origin | reference AP | +financial | Δ | +market | Δ | +publication | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-04-01 | 0.083252 | 0.080741 | −0.002512 | 0.081519 | −0.001733 | 0.079998 | −0.003254 |
| 2025-07-01 | 0.149928 | 0.135675 | −0.014253 | 0.143650 | −0.006278 | 0.141837 | −0.008091 |
| 2025-10-01 | 0.192212 | 0.160182 | −0.032030 | 0.168008 | −0.024204 | 0.175461 | −0.016751 |
| mean window AP | 0.141797 | 0.125533 | | 0.131059 | | 0.132432 | |
| pooled AP | 0.129189 | 0.114131 | −0.015058 | 0.116008 | −0.013181 | 0.118751 | −0.010438 |

Bootstrap detail (pooled, 20,671 rows / 140 positives, 161 clusters = 40 parent companies +
121 unmapped entities): financial se 0.009409, p(Δ≤0)=0.971; market se 0.008620,
p(Δ≤0)=0.9755; publication se 0.008613, p(Δ≤0)=0.9175.

## Agreement with the committed parent-level ablation

`reverse_rd_v2` entry-target holdout point ΔAP (no CIs/MDEs were computed there):
financial **+0.001729** (D−C), market **−0.005340** (E−D), publication **+0.002879** (F−D).

| group | entity ΔAP | parent ΔAP | same sign? | parent ΔAP inside entity CI? |
|---|---:|---:|---|---|
| financial | −0.015058 | +0.001729 | no | **no** (CI upper +0.000317) |
| market | −0.013181 | −0.005340 | yes | yes |
| publication | −0.010438 | +0.002879 | no | yes |

So the entity-level re-test **agrees with the parent-level direction only for market**; for
financial the entity point estimate and CI are on the opposite side of the parent's small
positive (the parent marginal is outside the entity CI), and publication's parent marginal is
inside the (wide) entity CI. Because the parent ablation has no interval, "agreement" here is
descriptive, not a test.

## Interpretation and limits

- On this entity panel no group improves ranking; all pooled point estimates are negative and
  the degradation grows in the later windows. This is a *within-panel* statement about adding
  these company-level groups to a 16-feature entity model, not a claim that the sources lack
  information for company-level questions.
- 63.5 % of rows cannot carry any group value; the effective treatment is partial and the
  missingness pattern (e.g. `fin_facts_available` is effectively a roster-size indicator) can
  itself move scores. That caveat applies to every number above.
- MDEs (0.024–0.026) are just above the pre-declared 0.02 bound: the two nulls are
  **underpowered**, not well-powered negatives. Larger entity coverage (or a company-level
  panel, where these sources are defined) is required to decide whether a 0.02-scale effect
  exists.
- Label windows of the three consecutive quarterly origins overlap, as in the committed
  artifact; the paired bootstrap resamples whole parent-company clusters and is deterministic
  (seed 20261103).

## Files and reproduction

| file | role |
|---|---|
| `experiments/b105_source_groups/build_entity_panel_with_sources.py` | builds the P2 panel, exact entity→company join, attaches the frozen source groups, emits availability report |
| `experiments/b105_source_groups/run_analysis.py` | 4-spec backtest + company-clustered bootstrap + MDEs + parent comparison; `--reclassify` re-applies the verdict rule without refitting |
| `experiments/b105_source_groups/results.json` | every number above |
| `experiments/b105_source_groups/data_availability.json` | join/coverage/missingness accounting per group and per origin |
| `experiments/b105_source_groups/panel_entity_sources.jsonl.gz` | 161,636-row panel artifact, 5.8 MB, fully regenerable; **not committed** (regenerate with the build script) |
| `tests/test_source_groups.py` | 24 tests |

```
python experiments/b105_source_groups/build_entity_panel_with_sources.py   # ~40 s
python experiments/b105_source_groups/run_analysis.py                       # 4 x 3 fits, ~25 min
python experiments/b105_source_groups/run_analysis.py --reclassify          # no refit
python -m unittest tests.test_source_groups                                 # 24 tests, OK
```

`results.json` is deterministic (sorted keys, no timestamps); the verdict blocks were last
written by `--reclassify` after fixing the negative-CI wording — no metric was changed.
