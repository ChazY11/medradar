# Cycle 3c — memory parameterisation and the bin-width sweep (2026-11-02)

**Status:** completed. Corrects the *identity* of the winning detector in cycle 3b; the reversal
itself survives. Evidence: `experiments/detect_v1/benchmark.json`, `bin_sweep.json`, `REPORT.md`
§5b/§5d. Decisions: D-020.

## The defect found while running the follow-up

The detectors express their memory windows in **stream units**. Left fixed while bin width grows,
a 3-month panel silently gives CUSUM/Bayes a 72-month baseline (24 bins) instead of 24 months, the
z-score a 36-month window instead of 12, and a 6-month panel a baseline of 144 months — longer than
the panel itself. Cycle 3b's quarterly comparison therefore varied aggregation **and** memory at the
same time.

## What changed (disclosed, never silent)

`check_frozen_reproduction.py` now separates frozen-monthly panels from bin-width panels. The three
monthly panels are **identical** to their committed values (PASS). The quarterly panel is reported
as changed:

| quarterly read-out, 2 % budget | before memory fix | after memory fix |
|---|---:|---:|
| naive rate multiplier | 0.025 | 0.025 |
| rolling z-score | 0.010 | **0.147** |
| Poisson CUSUM | 0.006 | 0.065 |
| Poisson Bayes factor | 0.129 | 0.073 |

**The reversal survives — the named winner does not.** The naive detector still collapses at
quarterly resolution and all three likelihood detectors now beat it (z +0.122 [+0.080,+0.164],
Bayes +0.048 [+0.019,+0.075], CUSUM +0.040 [+0.005,+0.080]), but the best detector is the **rolling
z-score**, not the Bayes factor. Cycle 3b's "+0.104 for the Bayes factor" was partly a
72-month-baseline advantage.

## Bin-width sweep (B-038)

1, 2, 3, 4, 6 month bins; identical lane, entity assignment, calendar onsets, 12-month horizon,
2 % budget and seeds; memory rescaled to constant calendar length.

| width | expected events/bin | naive | z | CUSUM | Bayes | best |
|---:|---:|---:|---:|---:|---:|---|
| 1 m | 0.210 | 0.223 | 0.112 | 0.181 | 0.122 | naive |
| 2 m | 0.424 | 0.007 | 0.083 | 0.111 | 0.088 | CUSUM |
| 3 m | 0.641 | 0.025 | 0.147 | 0.065 | 0.073 | z-score |
| 4 m | 0.862 | 0.004 | 0.092 | 0.176 | 0.060 | CUSUM |
| 6 m | 1.316 | 0.071 | 0.179 | 0.153 | 0.135 | z-score |

**Crossover at 2 months** (~0.42 expected events per bin). But the winner above the crossover is
**unstable**, alternating between z-score and CUSUM.

## What this establishes, and what it does not

Establishes:
- the naive rate-ratio test is **resolution-fragile**: it wins only at the finest resolution and
  collapses at the next width;
- the mechanism behind its failure is at least consistent with a fixed multiplicative threshold plus
  fixed event guards that cannot absorb a change in bin width;
- at this sample size the **identity of the best detector above the crossover is not identifiable** —
  the ranking is unstable across widths.

Does **not** establish:
- that any one likelihood detector should be deployed. Choosing one requires fixing the deployment
  resolution, re-calibrating memory in calendar time, and re-running this sweep on those panels;
- that the naive detector's collapse is purely statistical: its internal guards are in bins and
  cannot be rescaled, so part of the collapse is parameterisation. This is stated as a limitation.

## Consequence for the OBSERVE layer

Do not deploy on the basis of a single resolution. The layer must (1) fix the resolution it will
operate at, (2) express every detector's memory in calendar time, and (3) re-run this sweep there
before naming a detector. Until then the only claim that travels is "the matched rate-ratio test is
resolution-fragile, and no likelihood detector is reliably better at monthly resolution".
