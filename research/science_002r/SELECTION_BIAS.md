# SELECTION_BIAS - does the sample depend on outcomes that had not happened yet?

**Question.** SCIENCE-002 admits a registrant to the universe when it has ≥8
attributable cleared 510(k)s in 2015-01-01..**2026-08-31**. The panel starts
2021-01, the model is trained to 2024-12-31, and the holdout runs 2025-01..2026-06.
Eligibility is therefore partly decided by events that occur after the prediction
instant of most rows, and after every training row.

This is the highest-priority audit item because it attacks the *sample*, not the
model: no amount of statistical machinery can repair a sample that was chosen using
the outcome.

## 1. Direction of the bias is provable without a model

For any cutoff C, the pre-cutoff clearance count is ≤ the full-window count. The
strict rule can therefore only **remove** firms from the committed universe; it can
never add one. The audited sample is thus a superset of every stricter sample, and
the audit's job is to measure what the extra firms do to the statistic.

## 2. Result

| eligibility as of | firms | dropped | holdout rows | prevalence | firms in stratified AUC | delta | p | 95% CI | LOFO delta |
|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 (committed) | 48 | 0 | 782 | 0.531 | 31 | **-0.0337** | 0.094 | [-0.083, +0.017] | -0.002 |
| 2024-12-31 (before holdout) | 42 | 6 | 710 | 0.544 | 27 | **-0.0337** | 0.128 | [-0.079, +0.018] | -0.009 |
| 2020-12-31 (before panel) | 31 | **17** | 530 | **0.649** | 21 | **-0.0107** | 0.630 | [-0.058, +0.042] | +0.002 |

The committed scenario reproduces the frozen payload exactly (-0.033664), which is
also the audit's check that its harness is faithful.

## 3. Which firms depend on future events

The 17 firms removed by the pre-panel rule, with their full-window and pre-2021
clearance counts:

| firm | clearances 2015-2026 | clearances before 2021 |
|---|---|---|
| CARL | 22 | 1 |
| TNDM | 20 | 7 |
| PODD | 19 | 6 |
| CBLL | 15 | 3 |
| HYPR | 14 | **0** |
| ALGN | 13 | 3 |
| SGHT | 11 | 3 |
| STIM | 11 | 3 |
| OM | 10 | 4 |
| ANIK | 9 | 2 |
| STXS | 9 | 5 |
| HAE | 8 | 4 |
| IRIX | 8 | 5 |
| LMAT | 8 | 7 |
| LNSR | 8 | 7 |
| PRCT | 8 | **0** |
| SI | 8 | 2 |

PROCEPT BioRobotics and Hyperfine are the cleanest illustrations: they are in the
study *only* because of clearances that occurred after the panel began. Their
rows exist because of their future.

## 4. What changes, and what does not

**Changes.** Holdout prevalence rises from 53% to 65%, the number of firms
contributing to the within-firm statistic falls from 31 to 21, and the point
estimate moves from -0.034 to -0.011 - a 68% reduction in magnitude, though it
remains on the same side of zero and far from the GO threshold.

**Does not change.** No scenario produces a positive significant effect, no scenario
passes the GO rule, and the pooled firm-history baseline stays at 0.83 in every
scenario. The NULL verdict is not an artefact of the selection rule; if anything the
selection rule makes the study *look more* negative than a defensible sample does.

**Why it still matters.** The committed text presents 48 issuers as the study
population without disclosing that membership was decided after the fact. A reader
is entitled to assume the opposite. The corrected interpretation is: *the committed
analysis is a valid exploratory null on a sample selected on the full window; a
sample selected before the panel yields the same verdict with a smaller effect.*

## 5. Recommended repair

1. State the selection rule explicitly as "≥8 attributable clearances in the full
   2015-2026 extraction window, i.e. a sample selected on data that includes the
   holdout period", and rename the study population accordingly.
2. Add the 2020-12-31 rebuild as the primary sensitivity (numbers above).
3. For any future version, adopt the pre-panel rule as the headline rule; it is
   the only one that satisfies 'as of the prediction instant'.
4. Do not silently re-run with different cutoffs and keep the best-looking one; the
   protocol's own anti-fishing rule forbids it. The audit reports every cutoff it
   ran, including the one that moves the estimate toward zero.

## 6. Reproduce

```
$env:MEDRADAR_S2_CACHE = "<path to science_002 data/cache>"
python -m research.science_002r.run selection   # writes artifacts/selection_bias.json
```

The run takes about ten minutes (three full experiment runs at the frozen 2,000
permutations and 2,000 bootstrap draws). The ledger of every firm's counts at every
cutoff is stored in the artifact, not just the summary.