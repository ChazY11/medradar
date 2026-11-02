# Nine measurement rules for an autonomous empirical research programme: what a year of self-audit taught us

**MedRadar Foresight Lab** · methods paper, version 1 draft · 2026-11-03

---

## Abstract

Autonomous research systems are usually evaluated on the claims they produce. This paper argues that the more
transferable output of such a system is its **measurement discipline** — the set of rules that stopped it from
publishing false claims — and that those rules can be made mechanical.

We report the practice of a programme that spent thirty-five cycles asking whether public regulatory filings
anticipate corporate technological change. It shipped one confirmed decision rule and **retracted five findings**,
each for a specific, diagnosed reason: an entry denominator that mixed legal-entity appearance with firm entry; a
co-movement signal that was track growth; a cross-lane association that vanished on correct cells; a post-hoc
nomination whose holdout had been used for selection; and a benchmark whose outcome was defined against the signal
itself. Two further results needed unusual handling: a screening rule that **passed a revised criterion after
failing a stricter one**, and a forecast set in which **seven registrations turned out to be backfilled labels**.

From those failures we derive **nine rules**, each tied to the failure it prevented, and describe the two
mechanisms that enforce them: a **schema that rejects a profile without contradictory evidence** and a **round-end
verification command whose exit code is the completion claim**. We argue that a negative-result discipline is not
modesty but an engineering strategy: it converts each failure into a constraint that cannot recur silently.

---

## 1. The problem with claims

A system that reports its own results will, unless constrained, report its own noise. The constraint cannot be
good intentions, for three reasons the programme encountered directly:

1. **Selection is invisible from the inside.** The candidate that looks best is the candidate that benefited from
   the selection, and nothing in the reporting distinguishes the two.
2. **Code paths fail statistically.** Two of the five retractions were caused by an access bug and an
   entry-definition bug, not by an estimator.
3. **Prose outlives code.** A limitation written in a methods note can be quoted for years after the code that
   measured it changed.

Each rule below exists because one of these happened.

---

## 2. The nine rules

**Rule 1 — State the unit you measure.** Entity appearance is not firm entry. A corpus of filings resolves to
legal entities, and an entity's first filing is a registration event; a firm's entry into a technology area is a
different thing. Scoring the first as the second inflated one candidate by a factor that took a dedicated control
to expose: **79 %** of entry events were first appearances of a legal entity.

**Rule 2 — A ratio is not evidence.** Report a test, and when it fails to reject, report the **minimum detectable
effect**. On one roster a conventional 1.25 ratio rule flagged **35 of 53** companies while an exact binomial test
supported **4**; per-company minimum detectable ratios spanned **1.77× to 22.93×**, which is why detected counts
cannot be compared across companies as a ranking.

**Rule 3 — A benchmark outcome must not use the window that triggered the signal.** Our first rolling-origin
benchmark compared future activity with the *recent* window that had caused the flag. That comparison is
mechanically biased: the estimator measures its own conditioning. Corrected against the long-run baseline, the
naive-increase lift moved from **0.49** to **1.22** and no predictor's interval excluded 1.

**Rule 4 — A holdout cannot confirm a hypothesis nominated with its help.** A candidate selected by looking at
p-values cannot then be tested on the same window. The clean design nominates on one window and tests on another;
it nominated **3** tracks and confirmed **0**.

**Rule 5 — A negative conclusion about data availability is as falsifiable as a positive claim.** We concluded
that a hiring lane covered too few firms to test anything. That conclusion was a **pagination bug in our own
collector**, not a property of the source; the corrected panel covered **11** firms with posting URLs and the
conclusion changed. The measurement must be checked before the conclusion is carried forward.

**Rule 6 — Robustness in the preferred direction is not validation.** An estimate that *strengthens* under a
control can still be wrong for a different reason. Ours strengthened when recently created product codes were
removed — and was still killed by a different control, the entry definition.

**Rule 7 — Check the pipeline, not just the statistics.** Two retractions came from code paths. Every artifact we
now ship is re-derivable, and the round-end routine re-runs the verifiers rather than trusting their last report.

**Rule 8 — Report class-specific recall, not only aggregate accuracy.** A window-length sweep produced a
classifier whose *balanced accuracy was highest at the shortest window* — because that window could never see a
ramp forming, so it mislabelled every ramp and scored those cases "right". Aggregate accuracy would have
recommended the worst configuration for the task.

**Rule 9 — A forecast registered after its outcome is known is a label.** Of 32 forecasts registered from a
snapshot, **7** had outcome windows already observed and matured immediately; they scored a Brier of **0.337** and
an accuracy equal to the majority-class rate. They are excluded, and registration now filters on outcome windows
entirely in the future.

---

## 3. Two mechanisms that enforce discipline

Rules written in prose decay. Two mechanisms do not.

**A schema that rejects self-flattery.** Every company profile has seven required fields, one of which is
**contradictory evidence**: the checks that were run and what they found against the reading. A profile missing that
field is rejected by validation and refused by the renderer. The rule is thereby a type error rather than a
suggestion.

**A round-end command whose exit code is the claim.** A round is not finished until a single command re-runs the
test suite, the paper's claim map, the figure re-derivation, the profile self-check, the snapshot-chain audit and
the objective audit. This removed the main remaining opportunity for an over-stated summary: the summary cannot
claim more than the pipeline can verify.

---

## 4. Two results that needed unusual handling

**A confirmation that arrived after a failure.** A screening rule failed its pre-registered criterion: strict
monotonicity broke on an inversion of **0.018** and two intervals overlapped by **0.023**, even though the effect
roughly halved and the rank correlation was **0.882**. We recorded the failure, identified the criterion as the
defect, pre-registered a robust criterion, and confirmed it on **fresh draws** (rank correlation **0.908**, effect
ratio **2.18×**). The result is reported as a **post-failure confirmation** wherever it appears. We think this
intermediate category — weaker than a first-pass confirmation, stronger than an exploratory finding — is
under-used and should be reported explicitly rather than folded into either extreme.

**A pipeline test that found the component, not the filter.** An end-to-end evaluation compared alerts that were
promoted with those that were not: persistence was **0.800**, **0.667** and **0.373** for promoted, unpromoted and
non-alert cell-quarters respectively. The detector carries information about persistence; the marginal contribution
of the promotion filter is **not established** (difference **+0.133**, interval **−0.074 … 0.344**). Reporting only
the verdict, or only the contrast, would each mislead. Both are reported.

---

## 5. Discussion

**Negative results are an engineering strategy, not modesty.** Each retraction left a rule that is now enforced in
code or schema. The programme's value after thirty-five cycles is not its one confirmed rule but the set of
constraints that make the next false claim harder to publish.

**The discipline has costs.** Pre-registration slows iteration; class-specific reporting requires more estimands;
refusing to re-tune after a failure leaves obvious improvements untaken. We consider these acceptable because the
alternative — a system that reports its own noise with increasing confidence — is worse than slow.

**What this does not establish.** That these rules generalise beyond this corpus, this domain, or this model. They
are offered as a practice report with reproducible artefacts, not as a validated framework; the programme itself
found that one of its own negative conclusions was an instrumentation artefact, which is the appropriate caution.

---

## 6. Reproduction

Every claim in this paper is listed in `papers/CLAIMS_METHODS.json` with the artifact that contains it and the exact
substring; `papers/verify_claims.py --claims papers/CLAIMS_METHODS.json` checks both directions and fails on any
mismatch. The rules are enforced in `medradar/intelligence/profile.py` (contradictory-evidence schema),
`medradar/intelligence/snapshot.py` (frozen snapshots with manifests), `medradar/intelligence/forecasts.py`
(hash-verified registrations) and `tools/round_end.py` (the completion gate).

The companion paper, `papers/PAPER_v1.md`, reports the empirical results these rules were derived from, including the
five retractions in full.
