# Cycle 33 — a round now ends with one command, and the paper states its scope (2026-11-03)

**Status:** completed. Closes B-066. Decision: D-063.
Artifacts: `tools/round_end.py`, `tools/round_end.json`, `tools/round_end.log`,
`papers/PAPER_v1.md` §6 (limitations rewritten).

## The round-end routine is executable

`tools/round_end.py` runs every verifier in the repository in one pass and writes a machine-readable summary plus
a readable log. A round is not finished until this exits 0.

| step | current result |
|---|---|
| test suite (`medradar selftest`) | **PASS** — OK (skipped=3) |
| paper claim map | **PASS** — 78 claims, 0 failures |
| paper figures | **PASS** — 4 figures, 0 failures |
| profile self-check | **PASS** — 5 profiles, 0 failures |
| snapshot chain | **PASS** — 0 leakage problems |
| objective audit | **PASS** — 11 PASS / 0 FAIL / 1 N/A |
| repository state | **PASS** — HEAD synced with remote |

**7 PASS, 0 FAIL, ~23 s.**

Two implementation details are recorded because both were wrong on the first attempt: unittest reports its
summary on **stderr**, so a stdout-only extractor silently reported the last documentation line instead of
`OK (skipped=3)`; and a generic "last line containing a keyword" heuristic reported the audit's profile
self-check evidence rather than its own summary, so each step now declares its markers.

## The paper's limitations now say what a reader previously had to reconstruct

Section 6 states plainly:

- **Exactly one decision rule was confirmed** against **five retractions** — that ratio is the honest summary;
- promotion requires a **named human sign-off**, no automated path exists, and a test prevents one being added;
- the **ramp label is withheld below 1.0 event per series-month**, those alerts reported as
  `sustained_unresolved`;
- the **density scaling is a post-failure confirmation** and should be weighted differently from a first-pass
  result;
- the repository contains an **executable objective audit and round-end routine**, so progress can be re-run
  rather than trusted.

## Verification

- `python tools/round_end.py` → exit 0, 7 PASS / 0 FAIL.
- `python papers/verify_claims.py` → 78/78 after the limitations rewrite.
- `python -m medradar selftest` → 892 tests OK (skipped=3).

## Next

1. Use `round_end.py` as the completion gate for every subsequent round.
2. Consider a second paper focused on the measurement rules and the density confirmation.
3. Decide whether the promotion ledger should log relabelling events.
