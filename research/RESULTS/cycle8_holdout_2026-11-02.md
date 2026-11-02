# Cycle 8 — split-sample test: no entry-clustering claim survives (2026-11-02)

**Status:** completed. Closes B-046 and the entry-clustering thread **as a null**.
Evidence: `experiments/detect_v1/aesthetics_holdout.json`, `aesthetics_holdout.log`.
Decisions: D-026 (pre-registration), D-027 (outcome + methodological correction).

## What was pre-registered, and what was wrong with it

D-026 fixed a split-sample test for the `aesthetics` candidate: estimate on 2016-11…2022-12, test on
2023-01…2026-09, threshold untouched, power reported.

Running it exposed a flaw in the pre-registration itself: **`aesthetics` was nominated in cycle 7 using
the full window, which includes the holdout months.** A holdout cannot confirm a hypothesis that was
chosen with its help. The split-sample p-value is therefore not confirmatory, whatever its value.

## Both designs, honestly reported

**Post-hoc candidate (not confirmatory).** Estimation p = 0.0215 (14 entries), holdout p = 0.0360
(13 entries). Looks like replication; is not. The candidate is **not even nominated** by the clean
early-window design (p = 0.0215 does not survive BH across 30 tracks).

**Clean design (confirmatory).** Nominate on the estimation window only (BH q=0.10 over 30 tracks),
then test the nominees on the untouched holdout at α = 0.05:

| nominated track | estimation p | holdout p | confirms |
|---|---:|---:|---|
| `ivd_molecular` | 0.0015 | — (no holdout entries) | no |
| `medical_ai` | 0.0045 | 0.8411 | no |
| `vascular_access` | 0.0070 | 0.0825 | no |

**3 nominated, 0 confirmed.**

## Power, so the null is not over-read

With 13 holdout entries, detection probability for a wave concentrating 30 % / 50 % / 70 % of entries
in a six-month block is **0.25 / 0.52 / 0.95**. The holdout can rule out strong clustering; it cannot
rule out weak clustering. The correct sentence is **"no evidence of replication"**, not "proven
absence".

## What is closed

The B-042/B-043/B-046 thread is closed as a null: **this lane does not support a claim that any device
technology area shows an industry-wide wave of first entries.** The two candidates that appeared —
`ivd_immuno` (cycle 6) and `aesthetics` (cycle 7) — failed for different reasons, both now recorded:

| candidate | why it failed |
|---|---|
| `ivd_immuno` | **entity appearance**, not firm entry (79 % of raw entries were first-ever legal entities) |
| `aesthetics` | **post-hoc selection**; not nominated by a clean early-window design, and its apparent replication used the holdout |

## Why the programme stops searching here

Three cycles were spent trying to rescue a positive clustering finding. The recurring limit is not the
statistic but the **information content of the lane**: one regulatory filing stream at ~0.2 events per
cell-month cannot support these claims. Continuing to re-specify clustering tests on the same data
would be the "unlimited algorithm trial-and-error" the mission explicitly forbids.

Next priorities move off clustering:

1. **B-030 hiring** — the densest remaining independent signal, and the one that would change the
   information content rather than the estimator;
2. **B-031 patents** — the second declared gap;
3. **B-027 company technology profile** — the Understand-layer deliverable that does not depend on a
   positive clustering result.

## The programme's ledger after eight cycles

Six tempting positives, all dissolved under a better control or a cleaner design; zero surviving
positive claims; one increasingly precise map of what this data cannot support, with every retraction
and its reason committed. The map is the deliverable, and it is now specific enough to direct the next
data acquisition rather than another round of specification search.
