# ERRATA - every correction the audit applies to SCIENCE-002

Rules followed:

* **The frozen experiment is not touched.** No file in
  `research/science_002/artifacts/` and no module that produced them is edited.
  `PROTOCOL.md` is a frozen pre-registration and is **not** edited either;
  corrections that concern the protocol are recorded here and in the corrected
  documents, never by rewriting the protocol.
* Every correction below is a **documentation or interpretation** correction. None
  changes a number that the code computed.
* Each entry states its effect on the verdict. The verdict does not change.

---

## E1 - '78 rows with missing R&D features' is really 217

**Where.** `DATASET_CARD.md` section 3; `RESULTS.md` section 2.
**Was.** "rows with any missing R&D feature: 78".
**Is.** The complete-case filter drops **217** rows (2,771 -> 2,554). The 78 is the
number of rows whose *entire* R&D block is missing (the panel meta key
`n_missing_rd_feature_rows`); the complete-case rule requires all four B3
features, and the union of the per-feature gaps is 217 (rd_ttm_log 78, rd_yoy 144,
rd_to_sales 118, rd_growth_vol 177, overlapping).
**Effect.** None on any model; 2,554 was always the number used. Corrected in both
documents, with the per-feature counts added so the arithmetic is checkable.

## E2 - The 95% interval was read as a proof of absence

**Where.** `RESULTS.md` section 9.
**Was.** "a within-firm improvement larger than +0.017 AUC can be excluded at 95%".
**Is.** "the point estimate is -0.034; the 95% cluster-bootstrap interval is
[-0.083, +0.017] and an independent firm jackknife gives [-0.100, +0.032]. A
positive within-firm effect of about +0.03 is therefore disfavoured but not
excluded; effects of 0.055 or larger were detectable at 80% power and were not
found. The minimum detectable effect is a property of the design, not a bound on
the true effect."
**Why.** A two-sided percentile interval from 31 clusters does not license a
one-sided exclusion statement, and the independent jackknife interval is 40% wider
at the upper end (STATISTICAL_REVIEW.md section 3).
**Effect.** None on the verdict; the claim of precision is weakened, which is the
honest direction.

## E3 - The panel contains 46 firms, not 48

**Where.** `DATASET_CARD.md` sections 1 and 3.
**Was.** "48 firms x 66 months = 2,771 rows after 397 drops".
**Is.** 48 firms are in the **universe**; **46** contribute at least one row.
CARLSMED (22 attributable clearances) and SHOULDER INNOVATIONS (8) fail the
400-day SEC-coverage margin in every month and contribute zero rows. 48 x 66 -
2,771 = 397 remains the correct row arithmetic.
**Effect.** None on any model (they were never in the panel). Corrects the
population statement.

## E4 - '8.8% attribution coverage' is a universe share, not a recall

**Where.** `DATASET_CARD.md` sections 3 and 6; `RESULTS.md` section 10;
`README.md`.
**Was.** "8.8% attribution coverage ... the study's main measurement limit".
**Is.** "The 48-firm universe captures 3,143 of the **35,680** cleared 510(k)s filed
in 2015-2026 (8.81%) - a share of the whole FDA filing population, not a recall of
these firms' own activity. Recall cannot be computed because no public source
publishes a firm's true clearance total at legal-entity level; it is reported as
**unknown**. The audit enumerates 167 unattributed applicant strings that carry a
universe firm's brand token (444 clearances) as evidence of visible blind spots."
**Effect.** None on the verdict. It changes what the study's headline limitation
means, and it is the fairer statement: 8.8% does not mean "we see 8.8% of
Stryker".

## E5 - 'Fifteen of 44 holdout firms' is 13 of 44

**Where.** `DATASET_CARD.md` section 4.
**Was.** "Fifteen of 46 holdout firms have a single class" (and, in the same
paragraph, a reference to 44).
**Is.** **13 of 44** complete-case holdout firms have one class (44 - 31 = 13); when
every panel row is counted rather than the complete case, it is 15 of 46. The 31
firms in the stratified statistic is consistent with the complete case.
**Effect.** None on the model; reconciles three firm counts that were used
interchangeably (46 panel, 44 complete case, 31 stratified).

## E6 - 189 links belong to 62 candidates; 148 belong to the 48 firms

**Where.** `ENTITY_RESOLUTION.md` section 3; `DATASET_CARD.md` section 1.
**Was.** "Total accepted: 189 links over 62 candidate registrants -> 48 firms in the
universe", which lets a reader attach 189 to the 48.
**Is.** 189 links across the **62** candidate registrants (T_A 59, T_A2 4, T_B 126);
**148** of them belong to the 48 universe firms (T_A 46, T_A2 4, T_B 98), carrying
1,945 / 88 / 1,110 clearances respectively.
**Effect.** None. Adds the tier-level numbers that make the T_B dependence visible
(**35% of all attributed clearances** pass through the undated ownership snapshot).

## E7 - The sample is selected on data that includes the holdout period

**Where.** `RESULTS.md` section 2 and `DATASET_CARD.md` section 2 (a
disclosure paragraph was added). `PROTOCOL.md` is *not* edited - it is a frozen
document, and the deviation is recorded here instead.
**Is.** A registrant enters the universe when it has >= 8 attributable cleared 510(k)s
in 2015-01-01..**2026-08-31**. Because the training window ends 2024-12-31, eligibility
depends on events after every training row; 17 of the 48 firms would not qualify if
eligibility had been decided before the panel began (PROCEPT BioRobotics and
Hyperfine have **zero** pre-2021 clearances and are in the study only because of
their post-2020 activity). The pre-panel rebuild gives 31 firms, prevalence 0.649
and delta -0.011 (p = 0.63), versus 48 firms, prevalence 0.531 and delta -0.034
(p = 0.094).
**Effect.** The NULL verdict is unchanged and no scenario approaches GO, but the
point estimate is not an as-of-prediction quantity and must be labelled as a
sample selected on the full window. Full analysis: SELECTION_BIAS.md.

## E8 - The within-firm variance table is scoped to the complete case

**Where.** `DATASET_CARD.md` section 5.
**Was.** a table of "share of total variance that is within firm" with
`rd_to_sales` = 0.04, presented without a sample definition.
**Is.** The values are correct **on the 2,554-row complete-case analysis sample**.
On all 2,771 panel rows, `rd_to_sales` has a within-firm share of **0.265**
(driven by extreme ratios: p99 = 1.79, max = 7.0). `rd_ttm_log` stays at 0.02 in
both scopes and `rd_yoy` at 0.93 in both. The conclusion "the within-firm test
is essentially a test of R&D growth" holds for the model sample; it would be too
strong a claim about the raw panel.
**Effect.** None on the model. Tightens a descriptive claim.

---

## Not corrected here (deliberately)

| issue | why it is not corrected in this branch |
|---|---|
| The universe rule itself (E7) | changing it requires re-running the experiment and re-freezing; that is a v2 decision for the author, not something an auditor may do to a frozen study. The corrected numbers are provided instead. |
| The normalisation holes (`&` -> `AND`, plurals) | they change the accepted link set; the audit names the affected strings and leaves the decision to the author (ENTITY_AUDIT.md section 3). |
| The 30-day availability lag | it is a documented assumption with a lag-0/lag-60 sensitivity that does not change the verdict; the audit found no evidence that would justify a different central value. |
| The `n_missing_rd_feature_rows` key in `panel_summary.json` | it is an artifact produced by frozen code; the audit documents its narrower meaning rather than editing generated data. |

## Net effect on the reported result

| quantity | before | after audit |
|---|---|---|
| primary delta | -0.034 | **-0.034 (unchanged)** |
| permutation p | 0.094 | 0.094 (unchanged) |
| 95% interval | [-0.083, +0.017] | [-0.083, +0.017] bootstrap, **[-0.100, +0.032] jackknife** |
| verdict | NULL | **NULL (unchanged)** |
| sample characterisation | "48 listed medtech issuers, 2021-2026" | "48 registrants selected on the full 2015-2026 window; 46 contribute rows; 31 enter the stratified statistic" |
