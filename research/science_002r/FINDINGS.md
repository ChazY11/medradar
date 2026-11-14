# FINDINGS - SCIENCE-002R independent audit

**Audit verdict: REVISE BEFORE MERGE.** The core NULL survives every attack that
was executed, but the study as committed contains one methodological defect that
changes the estimand (future-driven universe inclusion), three numeric
inconsistencies in its own documents, and one over-read inferential claim.
Those are fixable, and after they are fixed the result is a valid exploratory
null. None of them is unfixable, so this is not a NO-GO.

Every number below is reproducible from `research/science_002r/artifacts/` with
the commands in README.md. The frozen SCIENCE-002 artifacts were not modified.

---

## Severity summary

| id | finding | severity | changes the NULL? |
|---|---|---|---|
| F1 | Universe inclusion depends on post-2020, post-training FDA events | **High** | No - but it changes the estimand and halves the point estimate |
| F2 | Four numeric inconsistencies between the documents and the artifacts | **High** (for auditability) | No |
| F3 | The 95% interval is read as a proof that effects above +0.017 are absent | **Medium** | No - but the claim is overstated |
| F4 | '8.8% coverage' is a universe share presented as if it were recall | **Medium** | No - but the headline limitation is mis-specified |
| F5 | Adjacent issuer-months share 66% of their outcome window; rows are not independent | **Medium** | No - the null survives three permutation schemes and a quarterly rebuild |
| F6 | 2 of 48 universe firms produce no panel rows; the panel is 46 firms | Low | No |
| F7 | One accepted link conflicts with FDA's owner/operator record | Low | No |
| F8 | The 510(k) establishment identifiers are product-code aggregates, not filing-level links | **High for SCIENCE-003** | N/A - blocks the planned next step, not this one |

---

## F1 - Universe inclusion is decided by future outcomes (High)

**What the protocol says.** A registrant enters the universe if it has at least 8
attributable cleared 510(k)s between 2015-01-01 and **2026-08-31**.

**Why that is a defect.** The panel starts 2021-01, the model is trained to
2024-12-31 and the holdout starts 2025-01-01. Eligibility therefore uses FDA events
that happen *after* every training row and, for early rows, after the prediction
instant itself. Enrolment is a function of the outcome.

**Measured.** Rebuilding the universe with eligibility decided only on information
that existed before the panel starts (cutoff 2020-12-31):

| eligibility asked as of | firms | dropped vs original | holdout rows | holdout prevalence | firms in stratified AUC | delta | permutation p | 95% CI | LOFO delta | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 (as committed) | 48 | 0 | 782 | 0.531 | 31 | **-0.0337** | 0.094 | [-0.083, +0.017] | -0.002 | NULL |
| 2024-12-31 (before holdout) | 42 | 6 | 710 | 0.544 | 27 | **-0.0337** | 0.128 | [-0.079, +0.018] | -0.009 | NULL |
| 2020-12-31 (before panel) | 31 | **17** | 530 | **0.649** | 21 | **-0.0107** | 0.630 | [-0.058, +0.042] | +0.002 | NULL |

17 of 48 firms only become eligible through post-2020 clearances. Two of them are
extreme: **PROCEPT BioRobotics** has 8 attributable clearances in the full window and
**0** before 2021, and **Hyperfine** has 14 and **0**. Their inclusion is entirely a
consequence of events inside the study period.

**Effect on the reported numbers.** The point estimate moves from -0.034 to -0.011,
i.e. it more than halves, and holdout prevalence moves from 53% to 65%. The
direction does not reverse and no scenario approaches the GO rule. The audit
therefore records: *the original sample is not an as-of-prediction sample, its
point estimate is sample-dependent, and its conclusion is nevertheless robust*.

**Why this is High.** A reviewer is entitled to read '48 listed medtech issuers,
2021-2026' as a sample defined before the outcomes were known. It is not. Nothing
in the write-up said so before this audit.

**Repair.** Either (a) re-specify the rule as '≥8 clearances before the panel
starts' and re-run (31 firms; the audit has done exactly this and the conclusion
holds), or (b) keep the current rule and report it as *selected on the full window*,
with the 2020-12-31 rebuild as the primary sensitivity. The audit recommends (a)
for any future version and (b) as the minimum for the current text.

## F2 - Four numeric inconsistencies (High, auditability)

| # | document claim | artifact fact |
|---|---|---|
| F2.1 | '78 rows dropped for incomplete R&D features' (DATASET_CARD section 3, RESULTS section 2) | the complete-case drop is **217** rows (2,771 -> 2,554). 78 is the number of rows with *no* R&D feature at all. |
| F2.2 | '48 firms x 66 months' as the panel denominator (DATASET_CARD section 3) | the panel contains **46** firms; CARLSMED and SHOULDER INNOVATIONS contribute **0 rows** because their 8-K history starts too late. 397 = 48x66 - 2,771 is still the right arithmetic, but 'firms in the panel' is 46. |
| F2.3 | 'Fifteen of 44 holdout firms have a single class' (DATASET_CARD section 4) | **13 of 44** complete-case holdout firms (15 of 46 when all panel rows are counted). 44 - 31 = 13. |
| F2.4 | '189 accepted links over 62 candidate registrants -> 48 firms' (ENTITY_RESOLUTION section 3) | 189 links belong to the 62 candidates; **148** belong to the 48 universe firms. Both are true for their own denominator; the text allows the reader to attach 189 to 48. |

These are documentation defects, not computation defects: the artifacts are
internally consistent and the models were fitted on the artifacts. They are
nevertheless High for auditability, because a reader who recomputes any of them
will conclude that the numbers cannot be trusted. All four are corrected in
ERRATA.md.

## F3 - The precision claim over-reads the interval (Medium)

RESULTS.md section 9 says: *'a within-firm improvement larger than +0.017 AUC can
be excluded at 95%'*. That sentence treats a percentile cluster-bootstrap bound as
a proof of absence. Three problems:

1. It is a **two-sided 95% interval from 31 clusters**; its tails are not calibrated
   to support a one-sided 'excluded at 95%' statement about a magnitude.
2. The interval is **not stable across resampling schemes**. An independent
   leave-one-firm-out jackknife gives SE 0.0337 and a 95% interval of
   **[-0.100, +0.032]** - an upper bound nearly twice the bootstrap's +0.017.
3. The minimum detectable effect (0.055) is a property of the design at 80% power
   under a normal approximation; it is **not** a bound on the true effect, and the
   text occasionally reads as if the truth lies between the MDE and the interval.

**Correct statement.** 'The point estimate is -0.034; the 95% bootstrap interval is
[-0.083, +0.017] and an independent jackknife interval is [-0.100, +0.032]. On this
sample and design, a positive within-firm effect of about +0.03 or larger is
disfavoured by the bootstrap interval but not excluded by the jackknife; effects of
0.05 or larger were detectable at 80% power and were not found.'

## F4 - 'Coverage' is a universe share, not recall (Medium)

3,143 / 35,680 = 8.81% is the share of *all* cleared 510(k)s in the window that the
48-firm universe captures. It is not, and cannot be, the share of those firms' own
FDA activity that the mapping captures (**recall**), because no public source
publishes a firm's true clearance total at the legal-entity level.

The audit therefore reports recall as **unknown**, and separately enumerates the
misses it can *see*: 167 applicant strings that carry a universe firm's brand token
but were not attributed, covering 444 clearances. Those are unadjudicated - some are
the same group under a 'dba' name, some are different companies - but they prove the
name channel has structural blind spots. Examples:

| firm | unattributed applicant string | clearances |
|---|---|---|
| SYK | HOWMEDICA OSTEONICS DBA STRYKER ORTHOPAEDICS | 28 |
| SYK | STRYKER ORTHOPAEDICS | 9 |
| GEHC | GE HUALUN MEDICAL SYSTEMS | 12 |
| TFX | ARROW INTERNATIONAL SUBSIDIARY OF TELEFLEX | 9 |
| MMM | 3M HEALTHCARE | 6 |
| STE | STERIS CORPORATIONS (plural) | 7 |
| BLCO | BAUSCH LOMB ('&' -> 'AND' normalisation mismatch) | 6 |

The last two are *normalisation* artefacts of the frozen rule, not ownership
subtleties: a plural and an ampersand defeat exact-root equality. See
ENTITY_AUDIT.md section 4.

## F5 - Rows are not independent, and the write-up does not say so (Medium)

With 90-day outcome windows on monthly rows, consecutive rows share two thirds of
their window. Measured within-firm label autocorrelation on the holdout:
**lag 1 = 0.717, lag 2 = 0.526, lag 3 = 0.370** (3, 4, 5 and 6 months apart lie
outside the window; the 0.370 at lag 3 is firm-level rate persistence, not overlap).
782 holdout rows across 44 firms therefore represent far fewer than 782 independent
observations; the protocol's power statement implicitly treats them as independent.

The audit executed three substitutes, none of which changes the verdict:

| inference | delta | p |
|---|---|---|
| within-firm shuffle (as committed) | -0.034 | 0.094 |
| circular shift (as committed, reported in SCIENCE-002) | -0.034 | 0.20 |
| **three-month block shift** (audit) | -0.034 | 0.22 |
| **non-overlapping quarterly rows** (audit) | **+0.012** | 0.79 |

Under non-overlapping observations the point estimate is +0.012 with p = 0.79 on
260 holdout rows and 29 firms - indistinguishable from zero and, if anything, the
opposite sign to the committed estimate. This strengthens the null and weakens any
reading of the -0.034 as a real negative association.

## F6 - Two universe firms have no rows (Low)

CARLSMED (22 attributable clearances) and SHOULDER INNOVATIONS (8) fail the
400-day SEC coverage margin in every month and therefore contribute no rows. The
panel is 46 firms, not 48. No model is affected; the documents are.

## F7 - One attribution conflicts with FDA (Low)

Of the 148 accepted links among the 48 universe firms, **1** has an FDA
owner/operator record pointing at a different firm: the applicant
`TELEFLEX` is registered under **VASCULAR SOLUTIONS** (a Teleflex acquisition),
3 clearances. That is an acquisition artefact rather than an error, and it is the
*only* conflict among 148 links, which is a strong positive result for the
attribution layer. 3 further links have no registration record at all.

## F8 - The establishment identifiers do not do what SCIENCE-003 assumes (High for the next phase)

SCIENCE-002's NEXT_STEPS proposes re-deriving attribution through
`openfda.registration_number` / `fei_number`. **Measured, that will not work
as stated.** On 176,625 510(k) records:

| property | value |
|---|---|
| records carrying any registration number | 173,426 (98.2%) |
| records carrying exactly one | 1,299 (0.74%) |
| median registration numbers per record | **104** |
| 90th percentile | 431 |
| maximum | 1,438 |
| distinct registration-number sets | 4,049 |
| sets shared by more than one applicant | **3,282** |
| applicants sharing the single largest set | **1,104** |

These identifiers are a **product-code-level aggregate** inherited from device
listing (they describe every establishment that lists a device with that product
code), not the establishment that filed the submission. A 2021 Shanghai United
Imaging 510(k) carries 86 registration numbers; a 2019 Togo Medikit 510(k) carries
202. Attributing a filing to a parent through this field would attach the filing to
hundreds of unrelated establishments. **This is a NO-GO for the proposed
SCIENCE-003 measurement plan in its current form**, and it was verified on the real
data rather than assumed. SCIENCE003_READINESS.md sets out what would have to be
true instead.

---

## What was checked and cleared

| risk | test | result |
|---|---|---|
| Future SEC filing entering a feature | injected a synthetic 8-K accepted 59 s after t (30 rows, executed) | 0 changes |
| XBRL restatement backfilled into history | injected a later-filed restatement of a known fact (40 rows) | 0 changes |
| Label window overlapping the feature cut | recomputed on all 2,554 complete-case rows | 0 violations |
| Unbounded clearance history in features | inspected `clearance_counts` cutoff = t - 30 d | enforced and verified |
| Double-attributed clearances | 8,176 k_numbers over 148 links | 0 shared |
| Artifacts not reproducible | fresh worktree, offline replay, byte comparison of 10 artifacts | **all identical** |
| Figure numbers not reproducible | figures read only committed artifacts; manifest records input hashes | verified |