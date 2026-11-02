# Study decision log — early_signal_5firms

Append-only. Entries are numbered `S-nnn` and record decisions made inside this study; the programme's main
`research/DECISIONS.md` is left untouched (it is prior record, not this study's scratchpad).

---

## S-001 — Study store is the main-clone store, not the curated research lane

**Date:** 2026-11-03 (system clock) · **Status:** accepted

The curated research lane holds 55,090 events (510(k)+PMA only, 51-firm roster). The main-clone store holds 375,378
events across 510(k) (176,466), **device recalls (59,646)**, PMA (57,372), **clinical trials (55,592)**, SEC 8-K
(20,976) and drug approvals (5,326), with event dates from 1966. Only the latter can speak to the directive's
cross-source questions. Both stores remain read-only for this study; no file under `data/` is committed.

## S-002 — No source reaches Tier A for historical availability

**Date:** 2026-11-03 · **Status:** accepted

`first_seen_at` in both stores is the collection date (2026-10-30/31), not the source's publication time. openFDA
bulk extracts and ctgov therefore reach **Tier B** at best: availability must be reconstructed as `event_date + lag`
with a declared assumption (30 days) and tested by sensitivity analysis. `procurement_awards` is Tier C
(`announcement_date`/`award_date` NULL, `data_quality = first_publication_unknown`) and may not enter lead-time
conclusions. `publication_counts` is annual and company-level only. **Patents are absent from every frozen store.**

## S-003 — Domain amendment is pre-registered, not smuggled

**Date:** 2026-11-03 · **Status:** accepted (human sign-off pending)

Coverage evidence supports cross-company validation on **two** tracks only (`imaging_us`, `respiratory`, three firms
each), not the directive's 12–18 combinations. `DOMAIN_AMENDMENT_001.md` fixes the confirmatory/secondary/exploratory
split **before** any outcome was examined, and does not touch the pre-declared floors or the window.

## S-004 — Dräger is descriptive only; Mindray's roster gap is a bookkeeping defect

**Date:** 2026-11-03 · **Status:** accepted

Dräger has 6 in-window observations in 4 quarters in respiratory and none elsewhere: it cannot enter any evaluation.
Dräger and Mindray have **no `company_key`** in the store's roster, so key-based counting reports zero events for both;
probing `applicant_raw` finds 48 and 244 events respectively. This is resolved by alias matching, which carries a
measured false-positive mode (`Surge Medical Sales` matching `GE MEDICAL`), now excluded.

## S-005 — The pilot's outcome is a declared non-result, and the pilot's own leak audit was defective

**Date:** 2026-11-03 · **Status:** accepted, recorded rather than hidden

The minimal replay produced **0 hits for both M0 and M1** over 9 rule-based positives in 164 events. The likely cause
is a specification mismatch (single-event entries versus a rate-anomaly detector) plus 0.85 events per cell-quarter.
Separately, the first leak audit asserted the wrong property and emitted 118 spurious violations; it was corrected to
test visibility-before-decision-cutoff, which passes with 0 violations. The defect is documented in
`PILOT_RESULTS.md` §2 rather than quietly fixed.

## S-006 — Phase 1 conditions (pre-committed)

**Date:** 2026-11-03 · **Status:** open

Phase 1 may only begin if: (a) the positive definition becomes a *sustained* change; (b) an earlier source survives
the tier audit so lead time is measurable at all; (c) per-cell results are reported separately and cross-firm pooling
is limited to the two confirmatory tracks; (d) 60 candidate cases are adjudicated by a named human reviewer with the
independence rule enforced. Until then Phase 1 is **CONDITIONAL-GO at best**.

---

## S-007 — G1 = NO-GO for lead-time measurement (pre-registered gate, run as specified)

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `EARLIER_SOURCE_AUDIT.json`, `LEAD_LAG_PROBE.json`,
`PHASE1_SHRINKAGE.md`

The frozen G1 criteria (≥10 eligible pairs with lead ≥2 quarters across ≥2 firms) were applied to three scopes:
S1 primary (trials on the device tracks) produced **0** pairs; S2 (assumed crosswalk `t_respiratory → respiratory`)
produced **3** pairs across 2 firms; S3 firm-level produced 0 eligible pairs because every trial is followed by a
clearance within the 2-quarter floor. The best scope reaches 3 pairs, below the floor of 10, so **G1 = NO-GO**.

Cause is structural, not statistical: the trial lane assigns therapy-area tracks (`t_*`), only four of which have an
id-identical device counterpart, and only one of those touches a confirmatory track. A crosswalk would have to be
built and reviewed, and building it after seeing outcomes would violate pre-registration. SEC 8-K is unusable at cell
level: 1,360 of 20,976 records carry a company_key (~5 per firm in the window) and none carries a track.

## S-008 — Firm-level pairing is recorded as invalid for inference, with the number that shows why

**Date:** 2026-11-03 · **Status:** accepted

At firm level, Medtronic's 113 in-window trials pair to the next clearance with **303,942** skipped follow-on events,
and **112 of 113** pairs fall below the 2-quarter floor. With thousands of clearances any trial will be followed by
one almost immediately, so the pairing carries almost no information about whether a technology change exists. This
is recorded so that no later analysis revives firm-level lead times as if they were evidence.

## S-009 — Next question is concurrent detection (O1), not lead time

**Date:** 2026-11-03 · **Status:** open, awaiting human decision

The corpus can support a question about *as-it-happens* multi-source detection (H1) but not about lead time (H2). The
recommendation in `PHASE1_SHRINKAGE.md` §6 is to run O1 next, after the positive definition is changed to a sustained
change, and to state the lead-time question as unanswerable on this corpus rather than replace it with a proxy.
O2 (a reviewed trial crosswalk) would need a human-adjudicated mapping before it can be used; O3 (patents/procurement)
remains blocked by access and by Tier C timestamps.

---

## S-010 — O1 is underpowered: the confirmatory cells contain almost no sustained changes

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `CONCURRENT_DETECTION.{json,md}`, `PHASE1B_PROTOCOL.md`

The amended positive definition (≥2 regulatory events within 4 quarters after ≥12 months of silence) yields
**1 onset** across the six confirmatory firm-track cells in the evaluation window 2022-Q1…2025-Q4 (24 company-years).
Under the frozen underpowered clause (<10 onsets), no comparison between M0, M1, M2 and M5 may be reported as support
or refutation of H1. The descriptive numbers are: M0 recall 1.0 (3 alerts), M1 1.0 (5 alerts), M2 0.0 (10 alerts),
M5 1.0 (10 alerts) — all with intervals spanning nearly the whole unit range ([0.207, 1.0] or wider), which is what a
single positive case produces.

The binding constraint is now clear and is **not** observation count: the cells carry enough quarter-observations
(164 events, 6 cells) but almost no *sustained changes*. A change-detection study cannot be powered on two tracks.

## S-011 — Second defect in my own leak audit, recorded rather than hidden

**Date:** 2026-11-03 · **Status:** accepted

The O1 leak audit initially aborted with 7 violations. Cause: the quarterly cutoff was computed as the 28th of the
quarter's final month instead of the real last day, so events published in the final days of a quarter were flagged.
Fixed with `calendar.monthrange`; the audit then reports **0 violations**. This is the second time an availability
audit of mine tested a slightly wrong property (the first is in `PILOT_RESULTS.md` §2), and the pattern is now
explicit in the study log: **audit cutoffs are code and must carry the same test discipline as models.**

## S-012 — The honest state of the study, and the decision that is not mine

**Date:** 2026-11-03 · **Status:** open, awaiting human decision

Three findings now bound this study:
1. lead time is unmeasurable here (G1 NO-GO, S-007): the trial lane cannot be joined to the device tracks;
2. the confirmatory cell set is too thin for change detection (S-010): 1 sustained onset in 4 years;
3. the only defensible multi-source pairing available is partial independence (recalls share the regulator).

Therefore the choice is between (a) **expanding** the cell set to the exploratory tracks (pre-registering a
multiplicity control, since per-firm exploratory cells invite cherry-picking), (b) **changing the unit** from
quarter-counts to event-level sequences, or (c) **closing** the programme at this scope and publishing the negative
result. Each is a scientific judgement about what the question is worth, and none is the agent's to make silently.

---

## S-013 — Expanded design: 5 two-stream cells, and still 0 onsets

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `CELL_INVENTORY.json`, `PHASE1C_PROTOCOL.md`,
`CONCURRENT_DETECTION_EXPANDED.json`

Coverage-only cell selection found **47** firm-track cells touched by any stream and only **5** with both streams above
the frozen floors (GE `imaging_mr_ct`; Medtronic `cardiac_rhythm`, `diabetes_cgm`, `insulin_delivery`; Philips
`imaging_mr_ct`), plus **11** regulatory-only cells. The protocol (sign test + Holm across three fusion-vs-single
comparisons, ≥10 onsets, pooled gain ≥0.10) was frozen before the run.

Result: **0 onsets** in the primary evaluation window (5 cells, 2022-2025); the frozen underpowered clause fires, so
no model comparison is interpreted. The 11 secondary cells also produced 0 onsets. Leak audit: 0 violations.

## S-014 — The positive class is empty at this granularity; the incidence ladder separates cause from definition

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `ONSET_LADDER.json`, `CLAIMS_EVIDENCE.json`

Before writing up "zero onsets", the ladder distinguished *no changes in the corpus* from *a definition that cannot
fire*. Across 16 cells and 2017-2025 there is exactly **1** quarter preceded by twelve months of silence, and it
qualifies as an onset; requiring twenty-four months of silence leaves **0** candidates. Loosening the episode window
(4 → 8 quarters) or raising the event requirement (2 → 3) does not change that. The cells' activity is continuous:
active tracks report regularly, quiet tracks never accumulate events.

Therefore the study's target phenomenon does not occur often enough to measure at firm × track × quarter granularity,
and the negative result is **definitional as well as empirical**: a different operationalisation of change could
behave differently, which is stated in the paper's limitations rather than hidden.

## S-015 — Third paper written from the negative evidence

**Date:** 2026-11-03 · **Status:** accepted

`papers/PAPER_NEGATIVE_v1.md` synthesises the three pre-registered gates (G1 NO-GO; two-track O1 underpowered with 1
onset; expanded O1 underpowered with 0 onsets), the taxonomy gap that caused the first, and the incidence ladder that
explains the second and third. Its 15 quantitative claims are verified in both directions by
`papers/CLAIMS_NEGATIVE.json` (`verify_claims.py --claims`, 15/15). No refuted result is re-used as valid, and the
paper states explicitly that the definitional limitation is not resolved by it.

---

## S-016 — Phase 1D: the fine unit does not detect earlier, and calibration took three attempts

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `EVENT_SEQUENCE_DETECTION.{json,md}`,
`PHASE1D_PROTOCOL.md`, `medradar/studies/pointprocess.py`, `tests/test_study_pointprocess.py` (20 tests)

Under controlled truth (rate ×2 or ×3 injected at 60 % of each cell's real sequence, 200 replications, 16 cells), at a
matched nominal false-alarm budget of 0.10 per run:

| multiplier | interval detector A delay | quarterly detector B delay | power A | power B | paired median difference |
|---|---|---:|---:|---:|---|
| ×2 | 185.5 d | 48.5 d | 0.762 | 0.333 | +133.9 [71.5, 165.2] |
| ×3 | 88.7 d | 56.0 d | 0.906 | 0.466 | +32.7 [23.9, 60.9] |

Both intervals exclude zero and both point estimates are positive: **the coarser quarterly detector fires earlier**,
while the interval detector detects more injections. The fine unit buys **power, not latency** — the likelihood ratio
needs several post-change events to accumulate evidence, whereas a quarterly bin boundaries converts a rate jump into
an immediate z-score.

**Two caveats that must travel with these numbers.** (i) Delays are conditional on detection, so a detector that fires
rarely has an optimistically short conditional delay; power is reported alongside for exactly that reason.
(ii) Realised false-alarm rates could not be exactly matched because the coarse detector's null statistic has heavy
ties at its maximum: A realised 0.095 while B realised 0.029, i.e. B was **stricter** than the nominal budget and still
earlier. That asymmetry narrows the claim from "B is better" to "at or below the same budget, B's detections come
earlier".

## S-017 — Three calibration defects found and fixed inside one round; the sequence is recorded

**Date:** 2026-11-03 · **Status:** accepted

1. **Poisson null miscalibrated on real data.** The first run calibrated the interval detector with parametric Poisson
   simulations; realised false-alarm rates on rotated real sequences averaged **0.84** against a 0.10 target (per-cell
   0.22–1.0), because filing sequences are overdispersed and bursty. Parametric calibration was abandoned.
2. **Ties inflated the empirical rate.** A plain quantile with a `≥` rule counted every tied value as an alarm and gave
   B **0.26**. Thresholds now use a strict-above rule.
3. **Over-correction to zero.** The strict rule pushed both realised rates to **0.0** when null statistics tied at the
   maximum; the final rule allows ⌊budget·n⌋ observations above the threshold.
Realised rates after the fixes: A **0.095**, B **0.029**. All three defects are recorded because the pattern — an audit
or calibration that is subtly wrong on real data — has now occurred four times in this study.

## S-018 — The negative arc is closed; what remains is data, not methods

**Date:** 2026-11-03 · **Status:** accepted

Four independent lines now agree, each with a frozen gate:
1. **Lead time** is unmeasurable on this corpus (G1: trial lane uses therapy-area tracks; 3 pairs vs a floor of 10);
2. **Sustained changes do not occur** at firm × track × quarter (1 qualifying quarter in 16 cells over 9 years; 0 at
   24-month silence);
3. **Fusion cannot be tested** (0 onsets in the expanded evaluation window);
4. **The finer unit does not help**: it detects more injections but later (S-016).

Therefore further method work inside this corpus cannot answer the directive's question. The remaining options are
data-shaped: an event-level source with earlier availability (patents, regulatory pre-submission, procurement with
usable dates), a different target with an independently recorded confirmation date, or a coarser unit where changes do
exist. All three require inputs this session cannot obtain, so the study stops here with its negative result published
in `papers/PAPER_NEGATIVE_v1.md` rather than continuing to produce models that have nothing to detect.

---

## S-019 — Owner sign-off recorded (2026-11-03): scope, and the one boundary that stays

**Date:** 2026-11-03 · **Status:** accepted · **Author:** project owner (`ChazY11`), recorded by the agent

The project owner gave blanket approval in session ("我都同意，我都人工同意了"). To keep the record honest, this entry
states exactly what that approval covers and what it does not.

**Signed off by the owner:**

1. `DOMAIN_AMENDMENT_001.md` — the two-domain confirmatory set, the secondary/exploratory split, and dropping
   `advanced_imaging` as a cross-company domain.
2. The GE HealthCare lineage treatment — claims speak of "the GE imaging business lineage", never the post-2023 legal
   entity, until a reviewer establishes continuity.
3. Adjudication of the six flagged `applicant_raw` strings: they are accepted as reviewed; the substring false positive
   (`Surge Medical Sales`) stays excluded.
4. The four study protocols as frozen: `PHASE1_PROTOCOL.md`, `PHASE1B_PROTOCOL.md`, `PHASE1C_PROTOCOL.md`,
   `PHASE1D_PROTOCOL.md`.
5. Authorisation to build the therapy-area → device-track crosswalk (O2), to re-run G1 with it as a new scope, and to
   open a pull request from this branch.

**Not covered — and not fabricated:** the **60 case labels**. `CASE_CANDIDATES.json` still holds
`final_label = null` and `human_review_status = PENDING_HUMAN_REVIEW` for every packet. A blanket statement is not a
per-case adjudication, and an agent may not convert one into the other. The review worksheet remains the only path to
Target B, one case at a time.

**Consequence for later sections.** Where the study previously wrote "PENDING_HUMAN_REVIEW" against a protocol or a
domain decision, that now means "owner-approved, not peer-reviewed". Peer review is still outstanding and is said so in
the papers.

---

## S-020 — Authorised crosswalk flips G1 formally, but the independence check makes it fragile

**Date:** 2026-11-03 · **Status:** accepted · **Authorisation:** S-019 · **Evidence:** `CROSSWALK.json`,
`LEAD_LAG_PROBE_CROSSWALK.json`, `medradar/studies/crosswalk.py` (11 tests)

With the owner-authorised text crosswalk, the trial lane can finally be joined to device tracks. Coverage is reported with
its denominators: **2,157 of 19,057** trials assigned (11.3 %), **122 ambiguous** (left unassigned by rule), 16,778 with
no device keyword — consistent with most ctgov records being drug trials. Among the five study firms, **71 trials**
receive a device track.

Applying the frozen G1 criteria unchanged to scope S1-crosswalk: **17 eligible pairs** (trial → later clearance in the
same device track, lead ≥ 2 quarters) across **3 firms** (GE HealthCare, Medtronic, Philips) → the frozen gate returns
**GO**, where the therapy-area route returned 3 pairs.

**A post-hoc but conservative check changes the reading.** The frozen count is *pairs*; a pair is not independent
evidence if several trials point at the same later clearance. The 17 pairs reuse only **9 distinct later clearances**
(independence ratio 0.53); the worst cell is `philips|respiratory`, where 6 trials pair to the single clearance in that
cell. Under a distinct-event count the gate is **below the floor of 10**.

Verdict recorded as **"GO (frozen count) / FRAGILE (independence check)"**. This is a tightening applied **after**
seeing the numbers, which is disclosed because it moves the conclusion in the conservative direction; it does not
manufacture a positive. Phase 1 lead-time estimation, if pursued, must carry `n_effective = 9` and treat any interval
built on it as underpowered.

## S-021 — External sources probed again; still unavailable

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `EXTERNAL_SOURCE_PROBE.json`

The previously blocked sources were re-probed rather than assumed blocked (see the probe artifact): the result decides
whether the third option in `PHASE1_SHRINKAGE.md` §5 (new data) is actionable now. Where a probe fails, the study
records the status code and the date instead of an opinion.

---

## S-022 — Correction to S-021: HTTP 200 is not usable data; patents are still unavailable, Europe PMC is new

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `EXTERNAL_SOURCE_PROBE.json`,
`experiments/b093/check_patents_endpoint.py`

The first probe (S-021) recorded "reachable" from HTTP status codes and would have supported the wrong conclusion. A
payload check corrects it:

| source | status | content type | usable as data |
|---|---:|---|---|
| PatentsView legacy API | 200 | **text/html** | **no** — the endpoint now returns USPTO's data-platform landing page; the JSON API has been retired or moved, and the replacement needs registration |
| PatentsView search API | DNS failure | — | no |
| SEC EDGAR companyfacts | 200 | application/json | **yes** |
| ClinicalTrials.gov API | 200 | application/json | **yes** |
| openFDA 510(k) | 200 | application/json | **yes** |
| **Europe PMC** | 200 | application/json | **yes** — a publication source the study had never used |

Consequences: **patents remain Tier D** (no machine API without registration), so the third option in
`PHASE1_SHRINKAGE.md` §5 is not unblocked by reachability. But **Europe PMC opens a genuinely new earlier source**:
publication dates with abstracts, queryable by organisation. That is the first new source since the study began that
(a) is point-in-time dateable, (b) is independent of the regulatory family, and (c) is machine-readable without
credentials. It requires its own coverage and availability audit before any use, and no claim in this study depends on
it yet.

**Lesson recorded:** a probe that reports only status codes can "unblock" a source that has no data behind the URL.
The probe now records content type and a `usable_json` flag, and both are in the committed artifact.

---

## S-023 — PR publication blocked on authentication; branch is merge-ready

**Date:** 2026-11-03 · **Status:** blocked (external), not a scientific issue

The owner authorised opening a pull request (S-019). The branch `research/early-signal-5firms` is pushed and the compare
page reports **"Able to merge"** with **11 commits, 89 files changed**, but the browser session is no longer signed in:
requesting `https://github.com/settings/profile` redirects to the sign-in page. Creating the PR needs an authenticated
session, and the agent holds no credential and will not ask for one or fabricate one.

State left for the owner: open `https://github.com/ChazY11/medradar/compare/main...research/early-signal-5firms`
after signing in, and create the PR (the title/body drafted for PR #5's sibling work can be reused; this branch's
summary is in `PHASE0_REPORT.md`, `PHASE1_SHRINKAGE.md` and `PAPER_NEGATIVE_v1.md`).

Nothing else in the study is blocked: the branch is complete, verified by the round-end gate (12 steps, 0 failures),
and `main` remains untouched at `ae18f27`.

---

## S-024 — Nine-event description: a median lead of 3.3 quarters, on a truncated sample

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `LEAD_TIME_SMALL_SAMPLE.{json,md}`,
`LEAD_TIME_SMALL_SAMPLE_PROTOCOL.md`, `medradar/studies/leadtimedesc.py` (7 tests)

Protocol frozen first (independence = distinct later clearance; conservative representative = latest paired trial;
no confidence interval at n = 9). Result: **17 pairs collapse to 9 events**; representative leads have median **3.3
quarters**, IQR **[2.26, 9.31]**, range **[2.09, 19.67]**. Per event, the leads run from 2.09 quarters (Philips,
wearable_remote) to 19.67 quarters (Philips, vascular_access), with one event whose six candidate trials span 12.2–23.7
quarters (`philips|respiratory`).

**The description is conditional and I have to say how.** Every event entered only because its lead was already ≥ 2
quarters — that is the G1 eligibility rule — so the shares `share ≥ 1q = 1.0` and `share ≥ 2q = 1.0` are **tautologies,
not findings**, and the median is the median of a **truncated** distribution. The artifact carries this as a
`conditioning` block and the markdown states it under the distribution. The study therefore cannot say how often leads
are shorter than two quarters, because such pairs were excluded by design.

Per the frozen wording, every mention carries: **"descriptive only; n = 9 independent events, below the floor of 10,
therefore underpowered and not a lead-time estimate."**

## S-025 — Nine evidence packets handed to human review; nothing labelled

**Date:** 2026-11-03 · **Status:** accepted (human review pending) · **Evidence:** `CASE_PACKETS_SMALL_SAMPLE.json`

Each of the nine events has a packet with firm, track, clearance id/date, the representative trial id/date, candidate
trial count and lead range, and four review questions: is the trial device-relevant rather than a drug trial matched by
keyword accident; does the clearance belong to the same firm-track; could the lead be an artefact of the post-hoc
crosswalk; and does a third source place the programme before the clearance. All nine are
`PENDING_HUMAN_REVIEW` with `final_label = null`. **No label was produced by the agent**, consistent with S-019.

---

## S-026 — Independent review of the publication head (performed by the agent, authorised by the owner)

**Date:** 2026-11-03 · **Status:** accepted · **Head reviewed:** `23e9d9b` (equals `origin/research/early-signal-5firms`)

The owner instructed the agent to review the branch itself rather than wait for a human reviewer ("你自行复核"). This
entry records what was actually checked, on the exact head that was published, so the claim is re-runnable.

| check | result |
|---|---|
| head equals the remote branch tip | **yes** (`23e9d9b` on both) |
| commits / files against `main` | 13 commits, 96 files |
| files under `data/` | **0** |
| `.sqlite` / `.db` artifacts | **0** |
| runtime dependencies | `dependencies = []` (stdlib only) |
| secret scan over added lines (private keys, `ghp_`/`gho_`, `sk-`, cloud keys) | **0 hits** |
| `round_end.py` on this head | **12 steps, 0 failures** |
| claim maps | paper **88/88**, methods **25/25**, negative **24/24** |
| study test suite | 81 passed (coverage, pairing, concurrent, pointprocess, crosswalk, leadtimedesc) |
| figures | 5 + 5 verified, layout 0 problems |
| profiles / snapshots | 5/5 profiles, 0 leakage problems |
| objective audit | 11 PASS / 0 FAIL / 1 N/A |
| human-review integrity | 60 candidate packets + 9 small-sample packets = **69, all `PENDING_HUMAN_REVIEW`, 0 labelled** |

**Review conclusion:** the branch is consistent with the study's own record — every negative gate is documented with its
frozen criterion, the only positive-looking result (G1 via the crosswalk) is published together with the independence
check that makes it fragile, and no case label was fabricated. Publication approved on that basis.

**What this review is not.** It is a *procedural and reproducibility* review, not peer review of the science, and not
human adjudication of the 69 packets. Both remain outstanding and are stated as such in the paper and in S-019.

---

## S-027 — Publication record: PR #6 merged into main as `4627672`

**Date:** 2026-11-03 · **Status:** accepted · **PR:** https://github.com/ChazY11/medradar/pull/6

The study branch was published and merged, after the agent-performed review recorded in S-026 and with all five CI
checks green on the merged head.

| item | value |
|---|---|
| pull request | **#6**, base `main`, head `research/early-signal-5firms` |
| reviewed head | `bb8f9f8` (14 commits, 97 files) |
| CI | 5 of 5 checks passed (py3.10/3.11/3.12 offline suites + wheel smoke, Windows data-files demo, offline data stats) |
| merge | merge commit **`4627672`**, history preserved (no squash) |
| `main` before | `ae18f27`; **after: `4627672`**, 174 commits |
| local `main` | fast-forwarded to `4627672` |
| gate on `main` after merge | **12 steps, 0 failures** |

**What is now on `main`:** the complete study directory (36 files), all six protocols including the small-sample
amendment, the crosswalk and its G1 re-run, the concurrent-detection and event-sequence experiments, the nine-event
description with its nine packets, and the third paper with its 24-claim map. The three papers are indexed in
`papers/README.md`.

**What is still not done, and cannot be done by the agent:** adjudicating the **69 packets** (60 candidates + 9
small-sample) — they remain `PENDING_HUMAN_REVIEW` with `final_label = null`, verified programmatically in the review.
Target B analysis therefore still does not exist, and neither paper claims it does.

---

## S-028 — Third-source cross-check run: one near-term hit, three decade-old keyword matches

**Date:** 2026-11-03 · **Status:** accepted · **Branch:** `research/early-signal-third-source` ·
**Evidence:** `THIRD_SOURCE_CROSSWALK.{json,md}`, `THIRD_SOURCE_PROTOCOL.md`, `medradar/studies/thirdsource.py`
(15 tests), `experiments/b095/europepmc_crosscheck.py`

Protocol frozen before any query. Nine events queried against Europe PMC with deterministic
`(AFF:"company") AND ("keyword")` strings, all recorded verbatim; availability = first publication date; trial reports
excluded as non-independent.

Result: **4 `SUPPORTED_BEFORE`, 5 `AFTER_CLEARANCE`** — but the distances change the reading, so a distance class was
added as a **descriptive** field (not a status change):

| distance class | count | meaning |
|---|---:|---|
| NEAR (≤1 year before clearance) | 6 (all AFTER_CLEARANCE except one) | the only class that can be read as programme-level corroboration |
| MID (1–3 years) | 0 | — |
| DISTANT (>3 years before) | **3** | keyword+affiliation matches **6.7, 14.5 and 23.3 years** old — not corroboration of this clearance |

So the honest summary is: **exactly one event (LT-07, Philips respiratory) has a near-term prior publication** (76 days
before the clearance, a low-cost ventilator study in *PLoS ONE*); three "before" hits are decades-old matches; five
events have publications only **after** the clearance. One distant hit is not even a paper but a patent-style record
(`Catheter introducer with thin walled sheath`).

**Disclosed deviation.** The packets carry no crosswalk keyword phrases (they were not propagated when the packets were
built), so the keyword terms come from the track's own keyword list, longest first. Every query is recorded, so the
deviation is visible and reproducible.

## S-029 — What the third-source check does and does not buy

**Date:** 2026-11-03 · **Status:** accepted

**Buys:** packets now carry an independent evidence field with a citable record (or an explicit `NO_RECORD` /
`AFTER_CLEARANCE` status), which is what a human reviewer needs to adjudicate.

**Does not buy:** any corroboration of a programme-level early signal. A keyword+affiliation search matches work from
any era; three of the four "before" hits predate their clearance by 6.7–23.3 years, and an old paper by the same
company in the same track says nothing about whether *this* clearance was prefigured. `NO_RECORD` is a null search, not
evidence of absence. No label was created: all packets remain `PENDING_HUMAN_REVIEW` with `final_label = null`
(`CASE_PACKETS_SMALL_SAMPLE_V2.json` preserves every original field and adds `third_source`).

**Consequence:** the third-source line is now closed as far as the agent may take it. Extracting a real
programme-level prior-publication signal would need author-level disambiguation and topic modelling of the paper's
content — a different study, and one that would need its own pre-registration.

---

## S-030 — Agent pre-adjudication: a new, explicitly non-human tier (owner-instructed)

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `ADJUDICATION_AMENDMENT_002.md`,
`medradar/studies/adjudication.py` (19 tests), `experiments/b096/adjudicate_packets.py`, `ADJUDICATION_AGENT_V1.{json,md}`

The owner instructed the agent to adjudicate the 69 packets. `LABELING_PROTOCOL.md` forbids the agent from producing
human truth, so the instruction is honoured by creating a **third tier** rather than by breaking the rule:

| tier | authority | usable as ground truth | usable to score the study's detectors |
|---|---|---|---|
| `PENDING_HUMAN_REVIEW` | none yet | — | no |
| **`AGENT_PRE_ADJUDICATION`** (new) | `agent_rubric_v1`, deterministic | **no** | **no** |
| human adjudication | named reviewer | yes | yes |

`agent_preliminary_label` is a **separate field**; `human_review_status` stays `PENDING_HUMAN_REVIEW` and
`final_label` stays null on all 69 packets, so a reader who opens a packet still sees the human boundary.

## S-031 — The rubric was wrong on its first run, and the correction is recorded before any distribution was published

**Date:** 2026-11-03 · **Status:** accepted

**The defect:** the first application scored *regulatory* packets (the 60 candidates) by searching **trial text** for
device keywords. Regulatory events carry no trial conditions, so every candidate scored `NONE` and the "distribution"
was an artefact of the wrong field. Caught before publication; the rubric now judges regulatory packets from the
**product code's own track mapping** (`relevance_from_mapping`) and keeps trial text only for the nine small-sample
packets.

**The corrected distribution** (69 packets, rubric `agent_rubric_v1`, second run):

| agent preliminary label | packets |
|---|---:|
| `Uncertain (agent-preliminary)` | **45** |
| `Routine Iteration (agent-preliminary)` | **18** |
| `Not Assessable (agent-preliminary)` | **6** |
| `False Signal / No Confirmed Shift (agent-preliminary)` | **0** |
| `Confirmed Shift (agent-preliminary)` | **0** |

Rules that fired: "strong relevance, consistent taxonomy, no near third source" 36; "strong relevance in the routine
stratum" 18; "strong relevance but no checkable mapping" 9 (all nine small-sample packets, whose clearance ids are
synthetic); "no rule matched" 6.

**What this distribution means:** the rubric finds **no packet it can call a confirmed shift**, 45 it cannot resolve
without a human, 18 that look like routine iteration, and 6 it cannot assess at all. That is consistent with the
study's overall result — but it is **not evidence for it**: the labels are the agent's own, and using them to score the
study's detectors would be exactly the circularity this programme retracted once.

**What it does not mean:** that 45 packets are "probably shifts"; that the rubric is a substitute for a reviewer; or
that any Target B analysis now exists. Target B still requires a named human.

---

## S-032 — Human review workbench delivered; the labels remain the owner's

**Date:** 2026-11-03 · **Status:** accepted (awaiting human labels) · **Evidence:** `HUMAN_REVIEW_WORKSHEET.csv`,
`HUMAN_REVIEW_WORKSHEET.md`, `REVIEW_GUIDE.md`, `medradar/studies/humanreview.py` (15 tests),
`experiments/b097/build_review_worksheet.py`, `experiments/b098/ingest_human_review.py`

The owner chose to adjudicate the packets personally. The agent's job is therefore to make that act cheap and
un-fakeable, not to label anything:

- **`HUMAN_REVIEW_WORKSHEET.csv`** — 69 rows, evidence columns pre-filled (firm, track, stratum, dates, product code and
  its mapped track, Europe PMC status and lead, a one-line summary, the rubric's preliminary label for contrast), five
  empty human columns.
- **Ordering by evidence strength** so a reviewer can stop early: NEAR third-source first (1 packet), DISTANT (3),
  novel-entry with consistent mapping, routine-stratum controls, then unassessable.
- **`REVIEW_GUIDE.md`** — the five labels, the independence rule, what to write in each column, how to query the store
  for more evidence, and how to submit.
- **`experiments/b098/ingest_human_review.py`** — validates every row and **refuses to write** on any defect: empty label,
  unknown label, missing reviewer, missing reason, `Confirmed Shift` without an independent confirmation, duplicate
  packet ids. Verified against the empty worksheet: it refuses with 207 problems (69 rows × 3 missing fields).
- **`medradar/studies/humanreview.py`** — the vocabulary, validation and summarisation; the agreement between human
  labels and the agent rubric is computed as a **descriptive diagnostic only**, with the prohibition against tuning
  written into the returned note.

**What has not changed:** no label exists yet. `ADJUDICATION_HUMAN_V1.json` is produced only by running the ingester on a
completed worksheet, and until then Target B remains empty.

---

## S-033 — The review workbench is verified end-to-end, including its refusals

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `HUMAN_REVIEW_WORKSHEET.xlsx`, `REVIEW_GUIDE.md` §8,
`experiments/b097/build_review_xlsx.py`, `experiments/b098/verify_review_path.py`

The owner asked to review the packets, then asked for the file to be opened. The CSV opened but was hard to use in Excel
(`####` on date columns, no label validation), so a formatted workbook was added: frozen header, auto-filter, readable
widths, shaded human columns, and a **drop-down restricted to the five labels**, plus an INSTRUCTIONS sheet. The
ingester now reads either format.

The path was then verified end-to-end on temporary copies (`verify_review_path.py`), which is the part that matters:

| case | expected | observed |
|---|---|---|
| all 69 rows filled correctly | accept | **exit 0**, dry run |
| one row missing the reviewer | refuse | **exit 2**, 1 problem, packet named |
| `Confirmed Shift` without independent confirmation | refuse | **exit 2**, 14 problems |
| out-of-vocabulary label | refuse | **exit 2**, 1 problem |
| output file written during any dry run | none | **none** |

No synthetic label entered the study: every case wrote to a temporary directory, and no
`ADJUDICATION_HUMAN_V1.json` exists yet.
---

## S-034 — External AI review ingested as a non-human tier; the halt rule fires and the nine-event lead-time is withdrawn

**Date:** 2026-11-03 · **Status:** accepted · **Evidence:** `AI_REVIEW_ADJUDICATION_V1.json`,
`AI_REVIEW_DECISION_2026-11-03.md`, `external_ai_review_2026-11-03/` (delivery pinned by SHA-256),
`experiments/b099/ingest_external_ai_review.py`

**What was delivered.** The project owner commissioned an independent AI review (Codex/chat-GPT-driven) of all 69
packets, delivered against commit `969fd0c`. Its own header says it is **"AI advice only, not a human gold standard,
may not be used to score detectors; the original human fields remain empty; this review had read the earlier labels,
so it is not blind"** (`AI_REVIEW_69.md`, `AI_REVIEW_69.json` authority `AI_ONLY_NOT_HUMAN_GOLD_STANDARD`,
`blind_review: false`, `may_score_detectors: false`).

**How it was ingested.** Not as human truth. A new tier `EXTERNAL_AI_REVIEW` is registered by
`experiments/b099/ingest_external_ai_review.py`, which validates: 69 unique ids exactly covering the frozen worksheet;
**all five human fields empty on all 69 rows**; labels inside the frozen vocabulary; every
`ai_eligible_for_target_b_scoring=false`; the source commit; CSV/JSON label agreement; and the non-human reviewer
field. It refuses to write on any defect. `can_count_as_human_truth=false` and `eligible_for_target_b_scoring=false`
are written into the artifact. The human-review requirement is **not** discharged.

**Label distribution (69 packets):** Routine Iteration **52**, Uncertain **9**, False Signal / No Confirmed Shift
**8**, Confirmed Shift **0**, Insufficient Observation 0. Agreement with the earlier agent pre-adjudication is
observed 0.478, kappa 0.160 (descriptive only; the reviewer had seen the earlier labels, so this is neither
independent nor usable to score anything).

**The halt rule fires.** The Phase-0 rule was: fewer than ~10 `Confirmed Shift` labels across the confirmatory tracks
⇒ narrow the study to a descriptive design. The count is **0**. Target B therefore stays empty; no Target B metric,
calibration, detector score or five-firm comparative claim may be produced from this tier.

**The nine-event lead-time description is withdrawn, not merely downgraded.** 8 of the 9 small-sample pairs
(`LT-02 … LT-09`) are device/project mismatches and `LT-01` is Uncertain, so the 3.3-quarter median lead in
`LEAD_TIME_SMALL_SAMPLE.md` is **not a lead-time estimate of anything**; the file now carries a withdrawal banner and
is kept only as the record of what was computed.

**Other evidence the review supplies** (all in `AI_REVIEW_ADJUDICATION_V1.json`): 13 `novel_entry` packets are flagged
`LEFT_CENSORED_GAP_NONE` (first observation in-window, not proven first entry) and 43 packets have earlier
same-applicant/same-product-code records in the current store; 5 candidate packets are manufacturing/QC notices
not product-platform events (ES5-022/044/052/053/057); one packet is a De Novo misrecorded as a 510(k) (ES5-010); the
packet set is Philips 23 / Medtronic 21 / GE HealthCare 16 / Mindray 9 / **Dräger 0**, so no equal-depth five-firm
comparison can be claimed from it.

**What this does not change.** The pilot's concurrent-detection null, the coverage matrix, the entity/domain audit and
every main-programme result stand. Nor does the review license the opposite claim ("the firms never shift"): it judges
whether *these packets' evidence chains* support a technology shift.

**Remaining human work:** resolve the 9 high-uncertainty packets and the 8 evidence mismatches first
(`HUMAN_DECISION_QUEUE.md`), then the rest; a named human must sign, and `experiments/b098/ingest_human_review.py`
still refuses anything less. Until then, Target B is unlabelled.

