# Papers

Two papers, both drafts in the repository rather than submissions. Each carries a **machine-verified claim map**:
every quantitative statement is declared with the artifact that contains it and the exact substring to find, and
the verifier fails if either side drifts.

| paper | question | claim map | verifier |
|---|---|---|---|
| [`PAPER_v1.md`](PAPER_v1.md) | Can corporate technological change be anticipated from public regulatory filings? | [`CLAIMS.json`](CLAIMS.json) (82 claims) | `python papers/verify_claims.py` |
| [`PAPER_METHODS_v1.md`](PAPER_METHODS_v1.md) | What measurement discipline did a year of self-audit produce, and how is it enforced? | [`CLAIMS_METHODS.json`](CLAIMS_METHODS.json) (22 claims) | `python papers/verify_claims.py --paper papers/PAPER_METHODS_v1.md --claims papers/CLAIMS_METHODS.json` |

**How to read them together.** The empirical paper reports the results — including five retractions with the
control that killed each one — and the one confirmed decision rule with its narrow scope. The methods paper
derives nine rules from those failures and describes the two mechanisms that enforce them: a profile schema that
rejects an absence of contradictory evidence, and a round-end command whose exit code is the completion claim.

**Status.** Both are draft v1: not submitted, no venue claimed. Figures (`figures/`) are generated as SVG from the
artifacts by `figures.py` and verified by `verify_figures.py`. Known gaps are recorded in the decision log
(`research/DECISIONS.md`, entries D-038 and D-067).
