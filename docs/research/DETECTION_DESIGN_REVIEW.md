# Adversarial design review — the pre-registered OBSERVE detection benchmark

**Status:** independent review of `DECISIONS.md` D-013 and the detection design recorded in
`research/STATE.json` → `active_work.design`, written **before the benchmark runs**.
Author: `detect-auditor`. Date: 2026-11-02. Branch: `research/change-detection-v1`.
**Nothing in the repository was modified by this review except the three documents named in
the task.** Everything in §3 is a measurement I ran, read-only, on the frozen inputs; the
script that reproduces every figure is **Appendix A**.

## 0. Scope, and what I did not review

I reviewed the design as *stated*: the stream definition, the four detectors, Evaluation A,
Evaluation B, the guards and the decision rule. I did **not** review the detector
implementation (`task-4` was still in flight), so this document cannot comment on code
correctness — only on whether the design can produce a valid answer if the code is correct.
I did not run any detector. I did not use the network for anything except bibliographic
verification of the literature review (`research/LITERATURE_DETECTION.md`).

Two claims in the design are taken as given and are not re-litigated here: the deterministic
legal-entity universe is an improvement on the curated roster, and a material-event lane is
the right lane for the OBSERVE layer. Both are defensible. The objections below are about
what happens *after* those choices.

## 1. Verdict

The design is well-shaped and unusually honest in its reporting language. It is not yet a
falsifiable experiment, for four independent reasons.

1. **Evaluation A's truth model is the likelihood detectors' own model.** Moustakides (1986)
   proves the CUSUM optimal for exactly the change model that ARM-1 injects. A win for the
   likelihood detectors on ARM-1 is therefore a demonstration of a theorem, and H-D1's kill
   condition cannot fire. The benchmark as specified can only fail by implementation bug.
2. **The false-alarm axis is nominal, not measured.** In this lane the Poisson null is
   violated by calendar and boundary effects that are bigger than the effect being compared:
   the final month carries 52.8% of the mean volume, January carries 85.6%, and the
   November 2025 dip is lane-specific (−64% in the PMA lane against −31% in 510(k)). Detector
   differences live in the tail that these effects populate.
3. **Evaluation B has no independent source and a control design that manufactures its own
   result.** The PMA-lane split is the same filing system (98.56% of it is administrative
   supplements), the publication series is annual and covers 51 of the 200 cohort entities,
   the procurement table has no dates and is flagged not point-in-time usable, and there is no
   trials data in any shipped database. Meanwhile the matched-control design selects controls
   from *non-detection* periods, which is selection on the outcome.
4. **The frame is too sparse for the metrics.** 8.0% of stream-months are non-zero; the median
   material stream has five events per decade; 56.5% of stream-months have a zero trailing
   twelve-month baseline, so the "naive rate multiplier" baseline comparator is undefined on
   more than half the data unless a zero rule is specified; and 72% of streams cannot detect a
   2× step within the window even with a known baseline. After the guard that makes detection
   meaningful, 39 streams remain, on which one replicate has a binomial standard error of
   8.0 percentage points at p = 0.5.

**The single change I would insist on before the benchmark runs:** *add the zero-injection
arm (ARM-0) on the real streams, calibrate every detector's threshold there to a common
number of alerts per stream-year, and draw the delay-vs-false-alarm frontier at that matched
**empirical** false-alarm rate — not at a nominal α.* This is one change, it is cheap, and
without it the benchmark's comparison axis is a property of the Poisson assumption rather
than of this data. §8 and §9 spell out exactly how.

## 2. What the design gets right (so that the rest of this review is read in proportion)

- Using **real monthly shapes** rather than synthetic streams: the seasonality and
  autocorrelation that a purely synthetic generator would omit are retained.
- Four **detector families** with a naive comparator, rather than a single model.
- **Leave-company-out** as a stability requirement, which most published detector
  comparisons do not do.
- **Pre-registered guards** (minimum baseline/total events, seasonality, product-code audit,
  spike-vs-level-shift), which is more than the biosurveillance literature standardly does.
- A decision rule that explicitly permits **"a tie or a loss is reported as such"**.
- The reporting language already concedes the correct scope: a positive result licenses only
  that "the detector finds rate changes in this data earlier at the same false-alarm budget",
  not that the change is strategically important. That concession is right, and §4 shows it
  needs to be enforced mechanically rather than rhetorically.

## 3. The lane the detectors will actually see

Every figure below is printed by Appendix A. Two frames are used and are labelled
consistently: the **material lane** (510(k) clearances plus original PMA approvals, all
entities) and the **mapped material frame** (the subset that also has a `company_key` and a
`track_id`, which is the closest computable proxy for the detection panel; it is *smaller*
than the 200-entity panel, so it is a lower bound on what the panel will contain, and its
sparsity is the same in kind).

### 3.1 Most of the lane is administrative, not technical

The `events` table is exactly two openFDA bulk sources: 31,219 510(k) rows and 23,871 PMA
rows, over 2016-11-01 … 2026-10-18, all 55,090 with `timestamp_quality = 'estimated'`.

Of the 23,871 PMA rows, **23,527 (98.56%) are supplements and only 344 are original
approvals**. The supplement reasons are administrative: 16,680 "Process Change —
Manufacturer/Sterilizer/Packager/Supplier", 3,552 "Change Design/Components/
Specifications/Material", 1,713 labelling, 681 location change, 561 post-approval study
protocol. The material-event rule correctly excludes them — but two consequences follow that
the design has not priced:

- **The PMA half of the lane is essentially empty.** 344 original approvals over 120 months
  is 2.9 per month across 10,309 raw applicant strings. The material lane is therefore
  **31,563 events (57.3% of the table), 263.0 per month**, and it is 98.9% 510(k). Any
  statement of the form "we detect changes in the PMA lane" is a statement about 344 events.
- **15.0% of the 510(k) half is explicitly product refresh.** `clearance_type` is
  Traditional 25,603 (82.0%), **Special 4,685 (15.0%)**, Abbreviated 527 (1.7%), Direct 321
  (1.0%), Dual Track 76, Post-NSE 7. A Special 510(k) is by regulatory definition a
  modification to the filer's *own previously cleared* device. So before any detector runs,
  roughly one event in six in the "material" lane is a device modification, which is exactly
  the confounder the brief asks the detectors to separate from technical change.

**Implication for the design.** The benchmark injects "technical change" into a lane in which
15% of events are refresh *and* the headline truth is unobservable. This is not a reason to
change the lane — it is the lane we have — but it is a reason that the report must state the
lane's composition next to every detection claim, and that "the material-event lane measures
technology activity" must be reported as an assumption, not a definition.

### 3.2 "Monthly event counts" is mostly zeros

In the mapped material frame: **316 streams, 3,744 material events**, median **5 events per
stream per decade** (p25 = 2, p75 = 13, max 220). Only **89 streams (28.2%) reach 12 events**
over the whole window; **39 (12.3%) reach 24**; 10 reach 60. **8.0% of stream-months are
non-zero** (3,048 of 37,920).

Three consequences the design must handle explicitly:

- **The naive rate-multiplier comparator is undefined on most of the data.**
  **56.5% of stream-months (19,267 of 34,128) have a zero trailing-twelve-month sum**, and
  **94.0% of streams have at least one such month**. If the naive comparator divides by a
  trailing mean, it will be undefined, infinite, or silently dropped on the majority of
  stream-months — and any comparison restricted to the subset where it *is* defined is biased
  in favour of the detectors that handle zeros natively. A zero-baseline rule (an additive
  floor, or a smoothed rate, applied identically to every detector) must be pre-registered or
  the comparison is not fair.
- **The "minimum baseline events" guard is doing enormous work.** 22.5% of streams have an
  entirely empty first 60 months. The guard that makes the benchmark meaningful is also the
  guard that discards most of the panel, and the discarded part is the majority.
- **A stream is not a time series in any useful sense at S-LO.** Five events in ten years is
  a point process, not a rate. Detection claims on such a stream are claims about one or two
  events.

### 3.3 How much information one stream carries (feasibility, not opinion)

For a Poisson stream with monthly rate λ and a *known* baseline, the per-month
Kullback–Leibler information for a step to mλ is λ(m ln m − m + 1). Accumulating
log(1/α) = 4.605 nats (α = 0.01) therefore takes ≈ 4.605 / KL months. Applying this to the
316-stream material frame (order-of-magnitude, known-baseline, single known step — the most
favourable case any detector will face):

| injected step | median implied months to detect | share needing > 120 months | streams able to detect within 12 months |
|---|---|---|---|
| ×1.5 | 1,021 | 94% | 0 |
| ×2.0 | 286 | 72% | 3 |
| ×3.0 | 85 | 43% | 21 |

**Implication for the design.** The benchmark's detection-probability grid is censored for
most of its cells by the data, not by the detector. A ×1.5 step — a realistic change for a
mid-size firm — is undetectable in a decade on 94% of streams. The comparison that the design
actually runs is therefore a comparison on a handful of streams (the ~21–39 that can detect
×3 and, with luck, ×2), and "detection probability across the seeded grid" will be a number
close to zero for most grid points, dominated by which streams the grid landed on. This is
not an argument against running the benchmark; it is an argument that **the verdict must be
reported per stratum with the censoring share**, and that "the detector wins across the grid"
must not be said when 72% of the grid is undetectable.

### 3.4 Two calendar artifacts, both larger than the effect

- **Boundary truncation.** The material lane averages 263.0 events/month (median 260.5, range
  139–331). The last six months are 286, 331, 287, 256, 323, **139**. The final month is at
  **52.8% of the mean**. In the mapped material frame the final month is at **35.3%** of its
  mean, and for the 89 largest mapped material streams the aggregate final-month count is
  **0.36×** their own preceding-twelve-month mean. A detector run on the live end of this
  series will fire on the boundary in every high-count stream simultaneously. The last
  *complete* month is 2026-09; 2026-10 is not a month of low activity, it is a month of
  incomplete publication.
- **A lane-specific collapse.** November 2025 is the material lane's second low month (209
  events, 79.5% of mean). It is not shared evenly across the two sources: 510(k) runs
  207/308/291 (2025-10/11/12) while PMA runs **80/227/218** — a **−64%** collapse in the PMA
  lane against −31% in 510(k). Whatever caused it, it is a *source-coverage* event, not a firm
  event, and it is precisely the kind of artifact that an "independent source" test using the
  other FDA lane would treat as confirmation (see §5.1). **The cause must be established in
  the data-artifact audit before any use of 2025-11 is interpreted; I did not establish it and
  I do not assume it.**
- **Seasonality.** January material-lane volume averages 227.9 against 266.2 for other months,
  a **14.4% deficit** (21.7% in the all-events table). A "month-of-year seasonality check" does
  not correct a 14% systematic calendar effect; it only confirms it exists. Either the
  baseline is estimated with month effects (as Farrington-type algorithms do) or the FAR
  calibration in ARM-0 must absorb them.

### 3.5 Taxonomy churn, and 31.4% of events with no track

- 2,202 distinct product codes appear in the lane; the map (`config/product_code_tracks.json`)
  has 1,958 entries; **1,274 of the 2,202 lane codes are absent from the map** (1,030 map
  entries are never seen in the lane). **17,308 events (31.4%) have no `track_id`** and cannot
  enter any technology dimension.
- **487 product codes first appear on or after 2022-01-01.** In the tracks where the OBSERVE
  layer most wants news, recent activity is carried by codes that did not exist earlier:
  in the last 24 months, **41.0% of ep_pfa events, 17.9% of structural_heart events and 12.3%
  of medical_ai events** are filed under codes born in 2022 or later (versus 0.7% for
  cardiac_rhythm). Over the whole window those shares are 11.5%, 5.1% and 8.2%.

**Implication.** A device family migrating from an old code to a newly created code produces a
**down-step in one stream and an up-step in another** with no change in technology. This
happens at a materially different rate by track, and it happens fastest in the frontier tracks.
On the *track aggregate* the two steps may partially cancel; per *entity × track* they need
not, and per entity they are guaranteed to appear when only one firm's devices migrate. The
design's "product-code reassignment audit" must therefore be a *rate*, not a checklist: report
per track the share of activity carried by post-2022 codes, and exclude code-birth months from
the false-alarm accounting (or add them to ARM-2 as a nuisance class).

### 3.6 There is no independent source in the spine

This is the hardest fact in this review, and it is decisive for Evaluation B. The census:

| source | what exists | why it cannot serve |
|---|---|---|
| PMA lane vs 510(k) lane | both openFDA bulk, same applicant strings, same 14-day assumed availability | same filing system; 98.56% of the PMA lane is administrative; the lanes' coverage moves independently (2025-11) |
| `publication_counts` | 616 rows, **annual** 2014–2026, **51 companies** | 1 observation per 12-month confirmation window; 51 of 200 cohort entities; annual cannot resolve a monthly detection |
| `procurement_awards` | 3,453 rows | `award_date` is NULL in **3,453 of 3,453** rows and `pit_usable = 0` in **3,453 of 3,453** |
| ClinicalTrials | *nothing* | no trials table exists in any shipped database; `data/tkg.sqlite` contains only event (55,090), product_code, company and track nodes; `scripts/backfill_trials.py` writes to `data/medradar.sqlite`, which is not present |

**Implication.** Evaluation B, as designed, cannot be run. The choice is between (a) marking
the confirmation test `BLOCKED` and reporting detection results without a confirmation claim,
or (b) building a genuinely external monthly series (trials, patents, hiring, procurement with
dates) before the benchmark. Option (a) is honest and can be done now; it also means the
OBSERVE layer's first publication must say "these are rate changes in the filing record", not
"these are real changes". Option (b) is the right medium-term move but is a separate work item,
not a benchmark parameter.

### 3.7 Entity namespaces are assembled from the future

The universe artifact merges 10,309 raw applicant strings into 9,412 entities (4,632 with
detailed records). **770 of the 4,632 detailed entities (16.6%) merge two or more raw strings**
— up to eight — and in the 200-entity cohort **106 of 200** merge at least two. Merging is by
name normalisation over the *whole window*, so a stream's 2017 activity can be attributed to
an entity name that only becomes associated with that firm in 2026.

Two distinct problems:

- **Discontinuity.** When a firm's applicant string changes (rename, merger, subsidiary
  hand-off), the merged stream continues only if the merge anticipated it; otherwise the old
  string's stream dies and a new one is born, producing a down-step/up-step pair that no
  detector should read as a technology change.
- **Look-ahead.** The panel's identity is a full-sample construct. That is acceptable for a
  *hindcast* benchmark, but it means the benchmark measures detection on a cleaner,
  better-identified panel than any live run would have had, and it does not license statements
  of the form "we would have caught this in month 3". The Anticipate layer's point-in-time
  discipline (available-at, purge rules) has no counterpart in this panel, and the design
  should say so.

### 3.8 The timestamps are estimated, not measured

- `event_date == decision_date` for **23,871 of 23,871** PMA rows: the date is a decision date,
  not a receipt date.
- `available_at` and `published_at` are **exactly `event_date + 14 days` for all 55,090 rows**
  (minimum, p10, median, p90 and maximum are all 14). There is no measured publication lag in
  the store — only an assumed constant.
- `first_seen_at` runs from 14 to 3,652 days after the decision, median **1,858 days**: that is
  when our own backfill first saw the record, and it is years after the fact.

**Implication.** Any statement about how fast the OBSERVE layer would notice a real decision is
a statement about a 14-day assumption, not a measurement. The 14-day constant also means the
"publication lag" perturbation in H-D5 is the only way to test how the detectors behave when
that assumption fails — and it will fail, because a bulk file is published when it is
published, not 14 days after every decision inside it.

## 4. Is an injected step change a fair proxy for "real technical change"?

No, and the design has to say so rather than let ARM-1 stand in for it. There are three
separate failures, and they need three separate fixes.

### 4.1 Three failures

**(i) Semantic.** A step in a filing rate is a change in *filing behaviour*. The lane contains
15.0% Special 510(k)s (modifications of the filer's own device), 1.7% Abbreviated 510(k)s
(guidance-based) and 31.4% of events with no track at all; and a 510(k) can be filed for a new
device, for a family extension, or to keep a line alive. A 2× step in a stream can be produced
by a reorganisation of the regulatory function, a decision to file in-house instead of through
a subsidiary, or a product refresh cycle. None of those is a technology change. The design
cannot fix this by injection; it can only fix it by labelling the output correctly.

**(ii) Distributional.** The injected change is a **permanent multiplicative shift at a known
onset**. Real technical change in this lane is at least four other things: a **spike** (one
device family clears in one month), a **ramp** (a programme builds over 6–18 months), a
**transient plateau** (a burst that ends), and a **composition change** (the same total activity
but a different mix across tracks — which a per-stream level detector cannot see at all). A
detector tuned for the permanent step is not wrong about the world; it is answering a narrower
question than the layer needs. This is exactly what the biosurveillance evaluation literature
does — Noufaily et al. inject multiplicative aberrations into a quasi-Poisson baseline, and
their detectors are built for those aberrations — so we would be reproducing a known circularity
rather than testing a new one.

**(iii) Evidentiary.** "Real technical change" has **no label** in this data. The design
replaces the missing label with an injected one, and then, in Evaluation B, replaces it again
with an *association* to another series. Nothing in the design checks that a detector which
wins on injected steps also produces better real-data alerts. The two evaluations are not
linked.

### 4.2 What a comparison on semi-synthetic data actually licenses

Precisely this, and no more:

> Under a Poisson step-change model with plug-in baselines estimated from the pre-onset segment,
> on streams with at least N material events, detector X achieved a median detection delay of
> *d* months at an empirical false-alarm rate of one alert per stream-year on the same panel,
> for injected multipliers in [a, b].

It does **not** license: "detector X finds real technical change earlier"; "detector X is the
right detector for the OBSERVE layer"; "the advantage survives real change"; or "this company's
technology programme changed". The design's own D-013 already concedes the last item; the
first three have to be conceded too, and the report should contain the licensed sentence
verbatim with the model stated, so that no reader can upgrade it.

### 4.3 The construct-validity gap (the criticism I most want the Lead to absorb)

The benchmark exists to **choose a detector for real data**, but it contains no test that the
ranking on ARM-1 transfers to ARM-2 (mis-specified change) or to ARM-3 (real data). Add the
cheap version now and the expensive version when a source exists:

- **Cheap, possible today:** report the rank agreement between ARM-1 and ARM-2. If the detector
  that wins on tidy steps is *not* the detector that wins on spikes/ramps/nuisance, then ARM-1
  cannot select the deployed detector, and the report must say that the choice is being made on
  the ARM-2 battery. This is a single number (Spearman ρ between the two fold-level rankings,
  plus per-stratum winners) and it is the most informative number the whole benchmark can
  produce.
- **Expensive, blocked on §3.6:** report the rank agreement between ARM-2 and ARM-3 confirmed-
  alert precision. Until a genuinely external source exists, this is `BLOCKED` and the report
  must say so.

### 4.4 Four implementation ambiguities that will decide the result if they are not fixed in advance

These are not quibbles: each of them, left open, can silently determine which detector "wins".

1. **How the injection is realised.** "Inject a known step into the real monthly shape" can
   mean (a) multiply the realised counts by the multiplier (which produces non-integer,
   artificially overdispersed counts no Poisson detector assumes), (b) resample each month from
   a Poisson with rate m·λ̂ (which throws away the real month-to-month shape the design wanted
   to keep), or (c) reweight the empirical distribution of counts. These three give different
   answers and different detector rankings. Pre-register one, and state what it does to the
   variance.
2. **Where the baseline comes from.** If the generator's baseline is the plug-in estimate from
   pre-onset months, that is fine — but the *detector* must then re-estimate it from the same
   data it is given, and the generator's knowledge must not leak into the detector. If the
   baseline is fitted across the injected segment, the result is contaminated. Pre-register the
   estimator and the segment.
3. **The zero-baseline rule** for the naive comparator (§3.2) and the smoothing applied to the
   detectors that need one. If the naive comparator is undefined on 56.5% of stream-months and
   and the other detectors are not, the comparison is not between detectors.
4. **Threshold selection.** A CUSUM's control limit, a z-score's threshold and a Bayes factor's
   cutoff are all free parameters. If they are set to nominal α = 0.01 and compared, the detector
   whose nominal α is least conservative on sparse data will look best. Calibrate all of them on
   the same empirical axis (ARM-0) or the comparison is a comparison of nominal conventions.

## 5. Evaluation B is not yet a test

### 5.1 Circularity: the "independent source" is the same system

The design's first suggested confirmation source is the **PMA lane versus the 510(k) lane**.
That is not independent in any of the senses that matter:

- **Same origin.** Both lanes are openFDA bulk files, ingested by the same pipeline, with the
  same applicant strings and the same assumed 14-day availability. An alert in the 510(k) lane
  and elevated activity in the PMA lane can both be consequences of one ingestion snapshot, one
  regulatory workload, or one product programme with a 510(k) and a supplement filed in the same
  quarter.
- **Same object, wrong kind of activity.** 98.56% of the PMA lane is supplements, and 16,680 of
  the 23,527 supplements are manufacturing/site process changes. "Confirmed by the PMA lane"
  therefore means "the firm also processed paperwork", which is close to the opposite of
  "the technology changed".
- **It moves independently for mundane reasons.** November 2025: PMA −64%, 510(k) −31%. A
  confirmation test built on these two lanes will sometimes "confirm" because the other lane's
  coverage recovered.

### 5.2 Selection on the outcome: the matched-control design manufactures an uplift

Detections are, by construction, months in which the stream exceeded its baseline. Control
periods defined as "matched non-detection periods" are therefore *lower-activity* periods in the
same stream. Comparing the following 12 months in the two groups compares a high-activity state
with a low-activity state in a persistent process, so the post-window will be higher in the
detection group even if the detector is detecting pure noise. Regression to the mean and
selection on the outcome are the same mechanism here, and the design as written does not block
either.

The fix is cheap and must be pre-registered: match controls **within the same stream**, on
**pre-window activity level** (e.g. preceding 12-month count), and on calendar month; then test
the confirmation difference against a within-stream permutation null. If the uplift does not
survive that, the confirmation result is an artifact.

### 5.3 Wrong sign for the window

Trials and publications *precede* device clearance; they are inputs to a regulatory submission,
not consequences of it. A 12-month-*after* window is the wrong direction for a leading source,
and the right direction only for a lagging source (procurement, post-market studies, guideline
inclusion). The design must state which direction each source is expected to move and why; a
two-sided window with no prior is a fishing licence.

### 5.4 Multiplicity in two dimensions

BH controls one family of hypotheses. The design applies it across cells, which addresses
multiplicity **across streams at one time**. It does not address multiplicity **across 120
monthly looks within a stream**: a rolling z-score thresholded at 3σ on every month does not
have the false-alarm rate its nominal α implies over the monitoring horizon, and no BH over
cells repairs that. The two error rates an alerting system needs are (i) expected fraction of
false alerts among alerts in a month (BH/BY territory) and (ii) expected number of false alerts
per stream-year across the whole history (sequential-monitoring territory, α-spending /
α-investing). The design controls (i) and reports the metric for (ii) without controlling it.

Also: BH's guarantee needs independence or PRDS; the cells here share a monthly volume factor
and a taxonomy, which is *plausibly* PRDS but must be argued, with BY at the same q as the
sensitivity analysis — and under a strong common factor, BH rejections arrive in bursts, which
is the alert-flood failure mode the layer exists to avoid.

## 6. Confounders: mechanism → false detection → guard

| # | Confounder | How it produces a false detection | Guard (concrete) |
|---|---|---|---|
| 1 | **Exposure / denominator change** (portfolio, divestiture, M&A, in-housing) | filing rate changes because the denominator changed, not the technology | report a per-entity "applicant-string set change" flag; ARM-2 rename perturbation; exclude or annotate months where the entity's merged-string set changes |
| 2 | **Product-code reassignment** (FDA recodes a device family) | one stream down-steps, another up-steps, no technology change | count code births per track (487 since 2022); report each track's share of activity from post-2022 codes (ep_pfa 41.0% in last 24 months); flag code-birth months; add as an ARM-2 nuisance class |
| 3 | **Taxonomy versioning** (one fixed map applied to ten years) | a code newly assigned to a track moves history between tracks | the map has 1,958 entries against 2,202 lane codes (1,274 lane codes absent from the map; 31.4% of events untracked); version the map by effective date, or report detection sensitivity to the mapping choice |
| 4 | **Right-censoring / publication lag** | final month at 52.8% of mean volume → alerts in every active stream | drop the last 2 months from detection (report them separately); ARM-0 must include the censored tail or the empirical FAR is measured on cleaner data than production sees |
| 5 | **Entity rename / reorganisation** | stream dies and a new one is born at hand-off | 770/4,632 entities (106/200 cohort) merge ≥2 strings; flag entities whose member set spans disjoint date ranges; ARM-2 split-stream perturbation |
| 6 | **Common-mode regulatory volume** (shutdowns, backlog, bulk-file cadence) | a panel-wide dip alarms hundreds of streams at once | condition on panel-wide monthly volume (as an offset or a monitor); the 2025-11 PMA −64% is the test case; ARM-0 must contain such months |
| 7 | **Seasonality** | January is 14.4% low | estimate month effects in the baseline (Farrington-style) or calibrate FAR on a seasonal null; the "check" is not a correction |
| 8 | **Outcome-defined windows** | 12-month-after windows are chosen because the source exists, not because the mechanism predicts it | pre-register direction and length per source; report both directions |
| 9 | **Multiple looks** | 120 monthly tests at nominal α | α-spending / α-investing for the time axis; report alerts per stream-year as the operational metric |
| 10 | **Refresh vs technology** | 15.0% Special 510(k)s are modifications | report the composition; treat "special 510(k) share" as a covariate in any interpretation; never call a rate change a technology change |

## 7. What would make the whole comparison invalid

Each item is a check the Lead can run before reporting anything.

1. **FAR measured nominally rather than empirically.** Check: does the report show, for every
   detector, the number of alerts per stream-year *on the real streams with no injection*? If
   no, the frontier is a property of the Poisson assumption and cross-detector claims are
   unidentifiable.
2. **The detectors given unequal information.** Check: same baseline estimator, same smoothing,
   same zero rule, same available history for all four detectors.
3. **A single replicate per cell.** Check: on the 39-stream S-HI material frame, a one-replicate detection
   probability has a binomial standard error of 8.0pp at p = 0.5. If the detector ranking is
   reported without paired seeds and Monte Carlo intervals, it is noise.
4. **The injection realised by rescaling rather than resampling** (§4.4.1). Check: state the
   mechanism and the resulting variance; if counts become non-integer, the Poisson detectors
   are being tested against a model they do not assume.
5. **Guards chosen after seeing which streams separate the detectors.** Check: strata are fixed
   in advance (they are, in `research/HYPOTHESES_DETECTION.md`), and the sensitivity of the
   verdict to the guard threshold is reported.
6. **Confirmation counted from a same-system source.** Check: the confirmation source is outside
   openFDA, or the claim is labelled "not independent".
7. **Confirmation controls not matched on pre-window activity.** Check: the uplift survives
   activity-level matching (§5.2).
8. **BH claimed to control FDR across dependence without argument, and without BY.** Check:
   the dependence argument is written down and BY is reported.
9. **A pooled headline across strata.** Check: S-HI / S-MID / S-LO reported separately; no
   verdict from S-LO.
10. **A "best detector" chosen on a favourable subset** (magnitude, onset window, stratum or
    metric). Check: one pre-registered primary endpoint, everything else labelled secondary.

Any one of these left unrepaired makes the comparison non-identifiable. Items 1, 3, 6 and 7 are
the four I would not sign off without.

## 8. The minimum defensible evaluation

The cheapest version that can produce an honest answer. It needs no new data and no new
modelling.

**Arms.**

- **ARM-0 — null arm, no injection.** All four detectors on the real streams, thresholds swept.
  Output: the empirical false-alarm curve (alerts per stream-year) per detector per stratum;
  the threshold that gives **FAR\* = 1 alert per stream-year in S-HI**; the alert census by
  month and by panel-wide volume (this also produces H-D7 for free).
- **ARM-1 — model-aligned steps** (the Lead's seeded grid), with **common random numbers across
  detectors**, ≥100 replicates per (stream, onset, magnitude), paired comparisons. One injection
  mechanism, stated (§4.4.1).
- **ARM-2 — misaligned + nuisance battery**, same seeds: single-month spike; 3–6-month ramp;
  transient plateau; panel-wide −50% volume in one month; 2-month publication lag at the end;
  entity rename split; product-code-birth migration. This is the arm that decides the
  recommendation.
- **ARM-3 — real data**: alert set at FAR\*, BY as well as BH, artifact-conditioned per §6, and
  **no confirmation claim** until a source exists.

**Metrics, pre-registered.** Primary: **detection probability at FAR\***, by stratum and
magnitude, with Monte Carlo 95% intervals. Secondary: D50 with the censored share reported;
alerts per stream-year; confirmed-alert precision (ARM-3, `BLOCKED`). Tertiary: rank agreement
ARM-1 vs ARM-2 (§4.3).

**Decision rule.** Report three verdicts separately and never merge them:
(i) *model-conditional* — the ARM-1 result, stated with its model; (ii) *mis-specification* —
the ARM-2 result; (iii) *operational* — the ARM-0-calibrated comparison. **Only (iii) may be
used to choose the detector deployed in the OBSERVE layer.** If (ii) and (i) disagree, the
report says so in the first paragraph.

**Reporting.** Stratum breakdown, censoring share, MC intervals, lane composition (§3.1), and
the licensed sentence from §4.2 quoted verbatim.

## 9. The strongest cheap improvement — and the rest ranked

**The single change I would insist on before the benchmark runs: ARM-0 and FAR\*.**
Concretely: run all four detectors on the real streams with **no injection**, sweep thresholds,
and calibrate every detector to **one alert per stream-year in S-HI**. Then draw the
delay-vs-false-alarm frontier at that measured operating point, and report the nominal-α
frontier only as a secondary, clearly model-conditional result.

Why this one: it is the only change that makes the comparison *identifiable*. Everything else on
the list makes the answer more precise; this one makes it an answer at all. It also costs
almost nothing — it is the same detector code run on the same streams with the injection
switched off, plus a threshold sweep — and it delivers three other things the design currently
lacks: a real-data alert census, the artifact share for H-D7, and the only defensible
definition of "matched FAR".

| change | cost | value |
|---|---|---|
| **ARM-0 + empirical FAR\*** | ~1 day, no new data | **makes the comparison identifiable** — the insistence |
| Common random numbers + paired differences + MC intervals (≥100 replicates) | <1 day | turns an 8pp-noise ranking into a measurable one |
| Pre-registered zero-baseline rule, applied to all four detectors | <1 day | removes the 56.5% undefined-baseline bias in favour of zero-native detectors |
| Fix the injection mechanism (resample vs rescale) in writing | hours | prevents a silently determined result |
| ARM-2 nuisance battery (spike, ramp, transient, volume shock, lag, rename, code birth) | 1–2 days | tests the claim the layer actually needs |
| ARM-1 → ARM-2 rank agreement | hours | single most informative number; closes the construct-validity gap for free |
| Drop the final 2 months from detection and from FAR calibration | hours | removes the 52.8%-of-mean boundary artifact |
| Version the taxonomy by effective date | 1–2 weeks | removes the code-migration confounder (ep_pfa 41.0% recent activity under post-2022 codes) |
| Build a genuinely external monthly series (trials / patents / dated procurement) | weeks | unblocks H-D3 and Evaluation B — a separate work item, not a benchmark parameter |
| Point-in-time entity namespace (versioned merges) | weeks | turns a hindcast panel into a live-capable one |
| Richer output than a binary alarm (posterior over number of change-points) | design + weeks | better-shaped product, out of scope for this cycle |

## 10. What this review does not establish

- **It does not say the detectors will fail.** It says the specified benchmark cannot show that
  they succeed, and it states what would have to change for that.
- **It does not fix the 2025-11 dip's cause.** I report the size and the lane asymmetry; the
  cause belongs to the data-artifact audit, and I did not assume it.
- **It does not validate the Lead's panel construction.** I measured the shipped
  `config/universe_v1.json` and a computable proxy frame; the actual 200-entity detection panel
  does not exist yet, and its sparsity may be somewhat better or worse than the proxy. The
  qualitative conclusions (mostly zeros; a handful of usable streams; code and name churn in the
  frontier tracks) are robust to that difference; the exact counts are not, and every one is
  labelled with the frame it came from.
- **It does not cover detector code.** `task-4` was in flight.
- **It does not cover the Understand layer.** Whether a detected rate change means anything
  strategically is not a detection question, and the answer must not be smuggled in.

---

## Appendix A — reproduction script for every number in §3

Run from the repo root: `python appendix_a.py`. It opens `data/research.sqlite` read-only
(`mode=ro`), reads `config/universe_v1.json` and `config/product_code_tracks.json`, and prints
each figure quoted above, section by section (`== A1 … == == A8 … ==`). Every §3 number appears
in its output; numbers belonging to different frames (the material lane versus the mapped
material frame) are labelled with the frame they came from. Requires `numpy` (already a project
dependency).

```python
"""Reproduction of every number quoted in DETECTION_DESIGN_REVIEW.md section 3.
Read-only. Run:  python appendix_a.py
Paths are relative to the repo root D:\\DEPPSKK\\worktrees\\integration-v2.
"""
import collections
import json
import sqlite3

import numpy as np

DB = "file:data/research.sqlite?mode=ro"
UNIV = "config/universe_v1.json"
MAP = "config/product_code_tracks.json"
MONTHS0, MONTHS1 = "2016-11-01", "2026-11-01"

con = sqlite3.connect(DB, uri=True)
cur = con.cursor()


def material_only(kind, payload):
    """Material lane = 510(k) clearance or ORIGINAL PMA approval (no supplement)."""
    if kind == "510k":
        return True
    p = json.loads(payload)
    return p.get("supplement_number") in (None, "", "null")


# ---------------------------------------------------------------- A1 lane census
print("== A1 lane census ==")
print("events total:", cur.execute("SELECT COUNT(*) FROM events").fetchone()[0])
print("date range:", cur.execute("SELECT MIN(event_date), MAX(event_date) FROM events").fetchone())
for r in cur.execute("SELECT source, kind, COUNT(*) FROM events GROUP BY 1,2 ORDER BY 3 DESC"):
    print("  source/kind", r)
print("timestamp_quality values:",
      cur.execute("SELECT timestamp_quality, COUNT(*) FROM events GROUP BY 1").fetchall())

# PMA supplement structure
sup_types, sup_reasons = collections.Counter(), collections.Counter()
n_pma = n_sup = 0
for payload, in cur.execute("SELECT payload FROM events WHERE kind='pma'"):
    p = json.loads(payload)
    n_pma += 1
    if p.get("supplement_number") in (None, "", "null"):
        continue
    n_sup += 1
    sup_types[p.get("supplement_type")] += 1
    sup_reasons[p.get("supplement_reason")] += 1
print("PMA rows:", n_pma, "| PMA supplements:", n_sup,
      "| supplement share: %.2f%%" % (100 * n_sup / n_pma),
      "| originals:", n_pma - n_sup)
print("supplement_reason top:", sup_reasons.most_common(5))
print("supplement_type top:", sup_types.most_common(3))

ct = collections.Counter()
for payload, in cur.execute("SELECT payload FROM events WHERE kind='510k'"):
    ct[json.loads(payload).get("clearance_type")] += 1
n_510k = sum(ct.values())
print("510(k) clearance_type:", [(k, v, "%.1f%%" % (100 * v / n_510k)) for k, v in ct.most_common()])
print("material lane size:", n_510k + (n_pma - n_sup), "of", n_pma + n_510k,
      "= %.1f%%" % (100 * (n_510k + n_pma - n_sup) / (n_pma + n_510k)),
      "| per month:", round((n_510k + n_pma - n_sup) / 120.0, 1))

# ---------------------------------------------------------------- A2 stream frame
print("\n== A2 material stream frame (company_key proxy frame) ==")
months = [r[0] for r in cur.execute(
    "SELECT DISTINCT substr(event_date,1,7) FROM events "
    "WHERE event_date>=? AND event_date<? ORDER BY 1", (MONTHS0, MONTHS1))]
midx = {m: i for i, m in enumerate(months)}
S = {}
mat_month = collections.Counter()
for ck, tk, m, kind, payload in cur.execute(
        "SELECT company_key, track_id, substr(event_date,1,7), kind, payload FROM events "
        "WHERE company_key IS NOT NULL AND company_key<>'' AND track_id IS NOT NULL "
        "AND track_id<>'' AND event_date>=? AND event_date<?", (MONTHS0, MONTHS1)):
    if not material_only(kind, payload):
        continue
    S.setdefault((ck, tk), np.zeros(len(months)))[midx[m]] += 1
    mat_month[m] += 1
vals = np.sort(np.array([v.sum() for v in S.values()]))
print("streams:", len(vals), "| material events in frame:", int(vals.sum()))
print("events/stream: median", np.median(vals), "| p25", np.percentile(vals, 25),
      "| p75", np.percentile(vals, 75), "| max", int(vals.max()))
for thr in (12, 24, 60):
    print("  streams with >= %d: %d (%.1f%%)" % (thr, (vals >= thr).sum(), 100 * (vals >= thr).mean()))
nz = int(sum(int((v > 0).sum()) for v in S.values()))
print("non-zero stream-months: %d of %d = %.1f%%"
      % (nz, len(vals) * len(months), 100 * nz / (len(vals) * len(months))))

# zero trailing-12-month baseline (naive rate multiplier undefined)
zero12 = tot12 = 0
for v in S.values():
    for t in range(12, len(v)):
        tot12 += 1
        zero12 += int(v[t - 12:t].sum() == 0)
print("stream-months with zero trailing-12-month baseline: %d of %d = %.1f%%"
      % (zero12, tot12, 100 * zero12 / tot12))
print("streams with >=1 undefined trailing-12 month: %d of %d = %.1f%%"
      % (sum(1 for v in S.values() if any(v[t - 12:t].sum() == 0 for t in range(12, len(v)))),
         len(vals), 100 * sum(1 for v in S.values()
                              if any(v[t - 12:t].sum() == 0 for t in range(12, len(v)))) / len(vals)))
print("streams with empty first 60 months: %d of %d = %.1f%%"
      % (sum(1 for v in S.values() if v[:60].sum() == 0),
         len(vals), 100 * sum(1 for v in S.values() if v[:60].sum() == 0) / len(vals)))

# dispersion
disp = [v.var() / v.mean() for v in S.values() if v.sum() >= 24 and v.mean() > 0]
print("dispersion (var/mean) over %d streams with >=24 events: median %.2f | p10 %.2f | p90 %.2f"
      % (len(disp), np.median(disp), np.percentile(disp, 10), np.percentile(disp, 90)))

# ---------------------------------------------------------------- A3 feasibility
print("\n== A3 detection-delay feasibility (Wald order of magnitude) ==")
print("delay ~ log(1/alpha)/KL(m*lam||lam); alpha=0.01 -> 4.605")
lam = vals / 120.0
for mult, kl in ((1.5, 0.1082), (2.0, 0.3863), (3.0, 1.2957)):
    d = 4.605 / (kl * lam)
    print("  step x%.1f: median implied months %.0f | share >36m %.0f%% | share >120m %.0f%% | streams <=12m %d"
          % (mult, np.median(d), 100 * (d > 36).mean(), 100 * (d > 120).mean(), (d <= 12).sum()))

# ---------------------------------------------------------------- A4 truncation
print("\n== A4 truncation and seasonality ==")
# (a) the full material lane, every entity, regardless of mapping
lane = collections.Counter()
for m, kind, payload in cur.execute(
        "SELECT substr(event_date,1,7), kind, payload FROM events "
        "WHERE event_date>=? AND event_date<?", (MONTHS0, MONTHS1)):
    if material_only(kind, payload):
        lane[m] += 1
lanev = np.array([lane[m] for m in months], dtype=float)
print("full material lane monthly: n=%d sum=%d mean %.1f median %.1f min %d max %d"
      % (len(lanev), lanev.sum(), lanev.mean(), np.median(lanev), lanev.min(), lanev.max()))
print("last 6 material-lane months:", [(m, lane[m]) for m in months[-6:]])
print("last month %s = %d = %.1f%% of mean" % (months[-1], lane[months[-1]],
                                               100 * lane[months[-1]] / lanev.mean()))
jan = [lane[m] for m in months if m.endswith("-01")]
oth = [lane[m] for m in months if not m.endswith("-01")]
print("material lane Jan mean %.1f | other mean %.1f | Jan deficit %.1f%%"
      % (np.mean(jan), np.mean(oth), 100 * (1 - np.mean(jan) / np.mean(oth))))
print("2025-11 material lane = %d = %.1f%% of mean" % (lane["2025-11"],
                                                       100 * lane["2025-11"] / lanev.mean()))
# (b) the mapped material frame (company_key + track), mean 31.2/month
mf = np.array([mat_month[m] for m in months], dtype=float)
print("mapped material frame monthly: mean %.1f | 2026-10 %d = %.1f%% of mean | 2025-11 %d = %.1f%%"
      % (mf.mean(), mat_month[months[-1]], 100 * mat_month[months[-1]] / mf.mean(),
         mat_month["2025-11"], 100 * mat_month["2025-11"] / mf.mean()))
tot_month = dict(cur.execute(
    "SELECT substr(event_date,1,7), COUNT(*) FROM events WHERE event_date>=? AND event_date<? "
    "GROUP BY 1", (MONTHS0, MONTHS1)).fetchall())
print("all-event monthly median:", np.median(list(tot_month.values())),
      "| 2026-10 =", tot_month["2026-10"],
      "= %.1f%% of median" % (100 * tot_month["2026-10"] / np.median(list(tot_month.values()))))
big = [v for v in S.values() if v.sum() >= 12]
now = len(months) - 1
a = sum(v[now] for v in big)
b = sum(v[now - 12:now].mean() for v in big)
print("largest %d mapped material streams: 2026-10 total %d vs own 12m monthly-mean sum %.1f -> ratio %.2f"
      % (len(big), a, b, a / b))
bykind = collections.defaultdict(dict)
for m, k, c in cur.execute("SELECT substr(event_date,1,7) m, kind, COUNT(*) FROM events "
                           "WHERE event_date>=? AND event_date<? GROUP BY 1,2", (MONTHS0, MONTHS1)):
    bykind[m][k] = c
for m in ("2025-10", "2025-11", "2025-12", "2026-09", "2026-10"):
    print("  %s 510k=%d pma=%d" % (m, bykind[m].get("510k", 0), bykind[m].get("pma", 0)))
# (c) dispersion, both frames, stated honestly
Sall = {}
for ck, tk, m in cur.execute(
        "SELECT company_key, track_id, substr(event_date,1,7) FROM events "
        "WHERE company_key IS NOT NULL AND company_key<>'' AND track_id IS NOT NULL "
        "AND track_id<>'' AND event_date>=? AND event_date<?", (MONTHS0, MONTHS1)):
    Sall.setdefault((ck, tk), np.zeros(len(months)))[midx[m]] += 1
for label, frame, thr in (("all-events frame", Sall, 24), ("material-only frame", S, 24)):
    d = [v.var() / v.mean() for v in frame.values() if v.sum() >= thr and v.mean() > 0]
    print("dispersion %s, %d streams >=%d events: median %.2f | p10 %.2f | p90 %.2f"
          % (label, len(d), thr, np.median(d), np.percentile(d, 10), np.percentile(d, 90)))

# ---------------------------------------------------------------- A5 taxonomy churn
print("\n== A5 taxonomy churn ==")
mp = json.load(open(MAP, encoding="utf-8"))
codes = collections.defaultdict(list)
n_notrack = 0
n_ev = 0
for pc, tk, d in cur.execute("SELECT product_code, track_id, event_date FROM events"):
    n_ev += 1
    if pc:
        codes[pc].append(d)
    if not tk:
        n_notrack += 1
print("distinct product codes in lane:", len(codes), "| map entries:", len(mp),
      "| codes absent from map:", len([c for c in codes if c not in mp]),
      "| map entries never seen:", len([c for c in mp if c not in codes]))
print("events without track_id: %d of %d = %.1f%%" % (n_notrack, n_ev, 100 * n_notrack / n_ev))
first = {c: min(v) for c, v in codes.items()}
late = {c for c, f in first.items() if f >= "2022-01-01"}
print("codes first seen 2022-01-01 or later:", len(late))
per = collections.defaultdict(lambda: [0, 0, 0, 0])
for tk, pc, d in cur.execute("SELECT track_id, product_code, event_date FROM events "
                             "WHERE track_id IS NOT NULL AND track_id<>''"):
    r = per[tk]
    r[0] += 1
    if pc in late:
        r[1] += 1
    if d >= "2024-10-01":
        r[2] += 1
        if pc in late:
            r[3] += 1
for tk in ("ep_pfa", "structural_heart", "medical_ai", "ortho_joint", "ivd_molecular", "cardiac_rhythm"):
    r = per[tk]
    print("  %-16s events %5d | from codes born >=2022 %.1f%% | last-24m share from those codes %.1f%%"
          % (tk, r[0], 100 * r[1] / r[0], 100 * (r[3] / r[2] if r[2] else 0)))

# ---------------------------------------------------------------- A6 universe / entity namespace
print("\n== A6 universe and entity namespace ==")
u = json.load(open(UNIV, encoding="utf-8"))
ents = u["entities"]
by_key = {e["entity_key"]: e for e in ents}
cohort = u["cohort"]["entity_keys"]
print("entities detailed:", len(ents), "| cohort:", len(cohort), "| raw applicant strings:",
      u["counts"]["raw_applicant_strings"])
nm = np.array([e["n_material"] for e in ents])
print("whole universe: entities with n_material >=12: %d (%.1f%%) | >=24: %d (%.1f%%)"
      % ((nm >= 12).sum(), 100 * (nm >= 12).mean(), (nm >= 24).sum(), 100 * (nm >= 24).mean()))
cnm = np.array([by_key[k]["n_material"] for k in cohort])
print("cohort: n_material sum %d median %.0f min %d max %d"
      % (cnm.sum(), np.median(cnm), cnm.min(), cnm.max()))
cells = np.array([c for k in cohort for c in (by_key[k].get("tracks") or {}).values()])
print("cohort (entity,track) cells non-empty: %d | >=24: %d | >=12: %d"
      % (len(cells), (cells >= 24).sum(), (cells >= 12).sum()))
multi = sum(1 for e in ents if len(e.get("members") or []) >= 2)
mc = sum(1 for k in cohort if len(by_key[k].get("members") or []) >= 2)
print("entities merging >=2 raw applicant strings: %d of %d = %.1f%% (cohort %d of %d)"
      % (multi, len(ents), 100 * multi / len(ents), mc, len(cohort)))
print("max merged strings: universe %d | cohort %d"
      % (max(len(e.get("members") or []) for e in ents),
         max(len(by_key[k].get("members") or []) for k in cohort)))
for name, f in u["focus_companies"].items():
    es = f.get("entities") or []
    print("  focus %-13s entities %2d | material %4d | cohort entities %d"
          % (name, len(es), sum(e.get("n_material", 0) for e in es),
             sum(1 for e in es if e["entity_key"] in cohort)))

# ---------------------------------------------------------------- A7 timestamps
print("\n== A7 timestamps ==")
rows = cur.execute("SELECT event_date, available_at, published_at, first_seen_at FROM events").fetchall()


def lag(a, b):
    import datetime
    try:
        return (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days
    except Exception:
        return None


for name, i in (("available_at", 1), ("published_at", 2), ("first_seen_at", 3)):
    d = sorted(x for x in (lag(r[0], r[i]) for r in rows) if x is not None)
    print("  %-14s n=%d min=%d p10=%d median=%.1f p90=%d max=%d"
          % (name, len(d), d[0], d[int(.1 * (len(d) - 1))], np.median(d),
             d[int(.9 * (len(d) - 1))], d[-1]))
same = 0
tot = 0
for payload, ed in cur.execute("SELECT payload, event_date FROM events WHERE kind='pma'"):
    tot += 1
    if json.loads(payload).get("decision_date") == ed:
        same += 1
print("PMA rows where event_date == decision_date: %d of %d" % (same, tot))

# ---------------------------------------------------------------- A8 independent-source census
print("\n== A8 independent-source census ==")
print("publication_counts:", cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT company_key), MIN(year), MAX(year), SUM(works) "
    "FROM publication_counts").fetchone())
print("procurement_awards:", cur.execute(
    "SELECT COUNT(*), "
    "SUM(CASE WHEN award_date IS NULL OR award_date='' THEN 1 ELSE 0 END), "
    "SUM(CASE WHEN pit_usable=0 THEN 1 ELSE 0 END) FROM procurement_awards").fetchone())
con.close()
try:
    tkg = sqlite3.connect("file:data/tkg.sqlite?mode=ro", uri=True)
    print("tkg node types:", tkg.execute(
        "SELECT node_type, COUNT(*) FROM nodes GROUP BY 1 ORDER BY 2 DESC").fetchall())
    tkg.close()
except Exception as e:
    print("tkg check failed:", e)
print("\n== END ==")
```

---

*End of review. Written before the benchmark ran. If any part of this review is later
contradicted by a measurement, the measurement wins and this file is corrected — see
`research/DECISIONS.md` for the record of any change.*
