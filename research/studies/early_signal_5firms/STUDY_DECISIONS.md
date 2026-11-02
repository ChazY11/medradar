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
