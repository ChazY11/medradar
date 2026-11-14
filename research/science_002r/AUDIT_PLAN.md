# AUDIT_PLAN - SCIENCE-002R

**Auditor role:** independent review of PR #42 (SCIENCE-002). **Target of the
review:** commit `a3c3516fc3395117763e28dd029c214fb7d3d0ee`, the head of
`research/science-002-cross-source`.

**Stance.** The audit's job is to try to break the study. Every claim in RESULTS.md
is treated as a hypothesis about the code, not as a fact. Where a claim cannot be
verified because the denominator does not exist in the evidence, the audit says so
explicitly instead of substituting an estimate.

**Immutability.** No file under `research/science_002/` is modified by this
audit. All new code, data and prose live in `research/science_002r/`. The
original artifacts stay exactly as committed, and the audit re-runs the frozen code
as a library rather than editing it.

---

## 1. Hypotheses to attack (fixed before running the experiments)

| id | hypothesis under attack | why it matters | how it is tested |
|---|---|---|---|
| **H1** | Universe inclusion is decided by clearances through 2026-08-31, while training ends 2024-12-31. Sample membership therefore depends on post-training FDA events. | If selection correlates with the outcome, the holdout composition and the estimand are not what the protocol says. | Rebuild the universe under two stricter, pre-declared eligibility dates (2020-12-31 and 2024-12-31) and re-run the identical primary analysis. |
| **H2** | Adjacent issuer-months have 90-day outcome windows that overlap by two thirds, so holdout rows are not independent. A within-firm shuffle destroys the serial structure and may understate the null variance. | The p-value and CI are the only inferential content of a NULL. | Quantify label autocorrelation and the implied design effect; re-run with non-overlapping (quarterly) observations; re-run the permutation with block and circular schemes. |
| **H3** | The reported reading 'improvements larger than +0.017 AUC can be excluded at 95%' over-reads a percentile bootstrap bound, and the MDE is presented as if it bounded the true effect. | Over-claiming precision is the most likely way a NULL misleads. | Re-derive the CI's meaning and the MDE's conditions from first principles; state the correct reading in ERRATA. |
| **H4** | '8.8% attribution coverage' is a share of *all* FDA clearances, not a recall of the 48 firms' own activity. Recall is unknown. | The headline limitation may be mis-specified in both directions: too pessimistic as a measure of firm activity, too optimistic as a measure of what the label captures. | Define four distinct quantities; build an independent, number-based attribution channel from FDA establishment identifiers and compare it with the name-based one. |
| **H5** | A historical knowledge leak exists in (a) the 2026 ownership snapshot applied to history, (b) XBRL restatements, (c) the 30-day availability lag, or (d) the historical clearance counts. | Any of these would make the NULL uninterpretable rather than conservative. | Executed adversarial tests: as-of reconstruction, restatement injection, lag sweep, window-overlap checks. |
| **H6** | Reported counts do not reconcile across documents (48/46/44/31 firms; 78 versus 217 complete-case drops). | Numbers that cannot be reconciled cannot be audited. | Recompute every reported count from artifacts with an explicit numerator/denominator, and log every mismatch. |
| **H7** | The committed artifacts are not reproducible from the frozen commit and the cached raw sources. | Reproducibility is the only defence against a silently edited result. | Fresh worktree, offline replay, byte comparison against the committed artifacts. |

## 2. Pre-declared decision rules

* **ACCEPT WITH ERRATA** requires *all* of: (i) H5 refuted by executed tests; (ii)
H1 does not reverse the sign of the primary statistic nor move it outside the
original 95% interval; (iii) H7 passes byte-for-byte; (iv) every H6 mismatch is
either corrected in ERRATA or shown to be a wording issue with no numeric effect.
* **REVISE BEFORE MERGE** if any of: H1 moves the primary statistic in a way that
changes its interpretation, H2 shows the inference is invalid rather than merely
imprecise, or H6 mismatches turn out to be numeric rather than editorial.
* **NO-GO** if any of: a genuine future-information leak is found; the label cannot
be shown to be independent of the features; the attribution error rate is high
enough that the label measures the wrong entity; or the primary statistic cannot be
reproduced at all.

An **ACCEPT before all P0 items are closed is not permitted**, regardless of CI
status.

## 3. Work plan (execution order)

1. Fix the audit environment and record it (H7 baseline).
2. Re-derive every reported count from artifacts (H6).
3. Re-run the frozen pipeline offline in a clean worktree (H7).
4. Selection-bias rebuild under pre-cutoff eligibility (H1).
5. Statistical audit: AUC, permutation validity, overlap-induced dependence,
   bootstrap, CI and MDE interpretation (H2, H3).
6. Entity audit and the number-based attribution channel (H4).
7. Time-semantics adversarial tests (H5).
8. Targeted repairs: documentation corrections and new tests only; the frozen
   experiment is never edited.
9. SCIENCE-003 readiness assessment: what the establishment identifiers can and
   cannot establish, measured rather than assumed.
10. Reports and Draft PR against the SCIENCE-002 branch.

## 4. What this audit will *not* do

* It will not re-tune the model, add features, change the outcome, or re-split the
  sample in a way that could make the result look better or worse.
* It will not present a post-audit re-analysis as original protocol output.
* It will not claim recall, precision, or a publication timestamp that the evidence
  does not contain.
* It will not treat 'all tests pass' as evidence about the science.
