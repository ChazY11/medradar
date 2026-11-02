# Cycle 3b — correction: detector ranking is resolution-dependent (2026-11-02)

**Status:** completed. Supersedes the *general* form of the cycle-3 headline, not its artifacts.
**Evidence:** `experiments/detect_v1/benchmark.json` (six panels), `REPORT.md` §0 and §5b.
**Pre-registration:** `DECISIONS.md` D-017 (declared before the runs), D-018 (outcome).

## What happened

Cycle 3 reported that at a matched 2 % per-stream false-alarm budget the naive rate-multiplier
alert beats every likelihood detector, and that data density is the binding constraint. A design
review noted that this could be model-conditional. Three sensitivities were therefore pre-declared
and run with the default panels re-verified point-for-point against the frozen frontier
(`check_frozen_reproduction.py` → PASS).

| panel | naive | rolling z | CUSUM | Bayes factor | paired Bayes − naive |
|---|---:|---:|---:|---:|---|
| track, monthly (frozen) | 0.223 | 0.112 | 0.181 | 0.122 | −0.101 [−0.134, −0.067] |
| stable codes (churn masked) | 0.222 | 0.114 | 0.183 | 0.124 | −0.098 [−0.132, −0.064] |
| no Special 510(k) | 0.224 | 0.031 | 0.026 | 0.096 | −0.127 [−0.169, −0.088] |
| **quarterly (3-month bins)** | **0.025** | 0.010 | 0.006 | **0.129** | **+0.104 [+0.068, +0.140]** |

## What the correction is

**Detector ranking is resolution-dependent on this lane.** At monthly resolution the simple
rate-ratio test wins; at quarterly resolution it collapses and the Poisson Bayes factor becomes the
best detector with a paired advantage that excludes zero. Neither panel is "the answer".

Consequences that are now in force:

1. The cycle-3 statement is restated as **monthly-resolution-specific**; the claim "the simple
   baseline is not beaten" no longer stands unqualified.
2. The claim "likelihood detection is unnecessary here" is **retracted** — it was never stated as
   such, but the monthly result could be misread that way, and the quarterly panel forbids it.
3. The OBSERVE layer must choose a detector **at the resolution it will actually operate at**.
4. The two other sensitivities **confirm** cycle 3 rather than correcting it: removing 15.01 %
   Special 510(k)s leaves the naive detector best, and masking late-appearing product codes changes
   nothing material.

## New hypothesis (not a finding)

Why does aggregation reverse the ranking? Hypothesis: at monthly resolution one observation
already crosses a rate threshold (favouring the rate-ratio test and defeating evidence
accumulation), while at quarterly resolution a bin aggregates several events and the likelihood
ratio can separate a sustained shift from a burst. **Testable** by sweeping bin width
(1, 2, 3, 4, 6 months) and checking whether the crossover point tracks the expected count per bin.
Queued as B-038. Until that test runs, the mechanism is speculative and is labelled as such.

## What did not change

- Absolute detection is still low at every resolution: the best quarterly detector recovers
  0.129 of injected shifts at a 2 % budget. Data density remains the primary constraint.
- The independent-confirmation question is still **blocked** (no second source).
- A detection is still only a statement about the rate of public regulatory activity.
