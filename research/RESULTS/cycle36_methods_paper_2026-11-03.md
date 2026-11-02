# Cycle 36 — second paper: the measurement discipline, with its own verified claim map (2026-11-03)

**Status:** completed. Closes B-069. Decision: D-067.
Artifacts: `papers/PAPER_METHODS_v1.md`, `papers/CLAIMS_METHODS.json` (22 claims),
`papers/build_claims_methods.py`, `papers/README.md`; `tools/round_end.py` now runs both claim maps.

## Why a second paper rather than a longer first one

The empirical paper answers an empirical question and carries five retractions plus one confirmed rule. The
transferable output — the **measurement discipline** that produced those retractions — is a claim about a different
audience: people building self-auditing research systems. Folding it into a results narrative would bury it.

## What the methods paper says

**Nine rules, each tied to the failure that motivated it:**

1. State the unit you measure (entity appearance ≠ firm entry; **79 %** of entry events).
2. A ratio is not evidence (**35 of 53** flagged vs **4** supported; MDE range **1.77×–22.93×**).
3. A benchmark outcome must not use the window that triggered the signal (**0.49 → 1.22**).
4. A holdout cannot confirm a hypothesis nominated with its help (**3** nominated, **0** confirmed).
5. A negative conclusion about data availability is as falsifiable as a positive claim (**11** firms after the
   collector fix).
6. Robustness in the preferred direction is not validation.
7. Check the pipeline, not just the statistics.
8. Report class-specific recall, not only aggregate accuracy.
9. A forecast registered after its outcome is known is a label (**7** of 32; Brier **0.337**).

**Two enforcement mechanisms:** the profile schema rejects any profile lacking contradictory evidence, and the
round-end command's exit code is the completion claim. The paper's argument is that rules in prose decay and these
do not.

**Two results needing an intermediate category:** the post-failure density confirmation (**0.018** inversion,
**0.023** overlap, rank correlation **0.882** then **0.908** with effect ratio **2.18×**), and the pipeline test
that found the detector but not the filter (**0.800 / 0.667 / 0.373**; difference **+0.133**, interval
**−0.074 … 0.344**).

## Sourcing

`papers/CLAIMS_METHODS.json` declares **22** quantitative claims with their artifacts and exact substrings;
`verify_claims.py --claims` checks both directions — **22/22 pass**. The round-end gate now runs **both** claim maps,
so the methods paper cannot drift either. `papers/README.md` indexes the two papers and says how to read them
together.

## Status and gap

Draft v1: not submitted, no venue claimed. The gap is honest and stated in the paper: it is a practice report from
one programme, not a validated framework — and the programme's own instrumentation artefact (a "coverage too thin"
conclusion that was a pagination bug) is cited as the reason for caution.

## Verification

- `verify_claims.py --paper papers/PAPER_METHODS_v1.md --claims papers/CLAIMS_METHODS.json` → 22/22.
- `python tools/round_end.py` → **8 steps, 0 failures**: test suite, both claim maps, figures, profile self-check,
  snapshot chain, objective audit, repository state.

## Next

1. Refresh `ROADMAP.md` with what is done and what remains before the objective can be declared complete.
2. Mature the prospective forecast set as the lane advances (earliest 2026-Q4).
3. Consider a figure showing the retraction-to-rule mapping for the methods paper.
