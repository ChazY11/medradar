# Papers

Three papers, all drafts in the repository rather than submissions. Each carries a **machine-verified claim map**:
every quantitative statement is declared with the artifact that contains it and the exact substring to find, and the
verifier fails if either side drifts.

| paper | question | claim map | verifier |
|---|---|---|---|
| [`PAPER_v1.md`](PAPER_v1.md) | Can corporate technological change be anticipated from public regulatory filings? | [`CLAIMS.json`](CLAIMS.json) (88 claims) | `python papers/verify_claims.py` |
| [`PAPER_METHODS_v1.md`](PAPER_METHODS_v1.md) | What measurement discipline did a year of self-audit produce, and how is it enforced? | [`CLAIMS_METHODS.json`](CLAIMS_METHODS.json) (25 claims) | `python papers/verify_claims.py --paper papers/PAPER_METHODS_v1.md --claims papers/CLAIMS_METHODS.json` |
| [`PAPER_NEGATIVE_v1.md`](PAPER_NEGATIVE_v1.md) | What can public filing data *not* tell us about early technology change? | [`CLAIMS_NEGATIVE.json`](CLAIMS_NEGATIVE.json) (15 claims) | `python papers/verify_claims.py --paper papers/PAPER_NEGATIVE_v1.md --claims papers/CLAIMS_NEGATIVE.json` |

**Results update.** [`PAPER_UPDATE_v1.md`](PAPER_UPDATE_v1.md) — what changed after the first draft: a marginal full-history entry signal, a pre-registered domain-level successor, a closed five-firm negative and corrected prospective claims; claim map [`CLAIMS_UPDATE.json`](CLAIMS_UPDATE.json) (79 claims); `python papers/verify_claims.py --paper papers/PAPER_UPDATE_v1.md --claims papers/CLAIMS_UPDATE.json`.

**How to read them together.** The empirical paper reports the results — including five retractions with the control
that killed each one — and the one confirmed decision rule with its narrow scope. The methods paper derives nine rules
from those failures and describes the two mechanisms that enforce them: a profile schema that rejects an absence of
contradictory evidence, and a round-end command whose exit code is the completion claim. The negative paper reports
the five-firm study's three pre-registered gates, all of which returned negative, and states precisely which question
public data cannot answer: at firm × technology-track × quarter resolution, sustained technology changes are absent
(1 qualifying quarter in sixteen cells over nine years), so fusion and lead time are untestable.

**Status.** All three are draft v1: not submitted, no venue claimed. Figures (`figures/`) are generated as SVG from
the artifacts by `figures.py` and verified by `verify_figures.py`. Known gaps are recorded in the decision logs
(`research/DECISIONS.md` D-038/D-067 and `research/studies/early_signal_5firms/STUDY_DECISIONS.md` S-001…S-015).
