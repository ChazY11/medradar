# What public filing data cannot tell us about early technology change: a negative result from five medical-device firms

**MedRadar Foresight Lab** · negative-result paper, draft v1 · 2026-11-03 · study `early_signal_5firms` ·
branch `research/early-signal-5firms`

---

## Abstract

We asked whether publicly available evidence can identify a meaningful change in a medical-device firm's technology
positioning earlier than conventional regulatory monitoring, and designed a pre-registered study to measure it across
five firms. We report a negative result in three independent steps.

First, **the earlier sources cannot be joined to the technology tracks**: the trial corpus (55,592 records) is indexed
by therapy area rather than by device track, so on the study's tracks there are zero trial records to pair; SEC 8-K is
trackless and carries a company key for 1,360 of 20,976 records. The pre-registered lead-time gate therefore returned
NO-GO with 3 eligible pairs against a floor of 10.

Second, **the positive class is effectively absent**. Under a definition fixed in advance — at least two regulatory
events within four quarters, after twelve months of silence — sixteen firm-track cells covering 2017–2025 produced
**one** qualifying quarter, and requiring twenty-four months of silence produced **none**. Activity in these cells is
continuous: tracks that are active stay active, and tracks that are quiet never accumulate the events.

Third, **the fusion hypothesis cannot be tested on this corpus**: with 0 onset quarters in the primary evaluation
window, no comparison between persistence, regulatory, recall and fused detectors is interpretable, and we report it
as underpowered rather than as support or refutation.

We conclude that at the granularity the data support — firm × track × quarter — the phenomenon this study set out to
detect does not occur often enough to be measured. The binding constraint is information, not modelling.

---

## 1. What was tested, and how the conclusion was bounded

The study followed the discipline of its parent programme: **freeze the decision rule, then run**. Four protocols were
written before their experiments (`PHASE1_PROTOCOL.md`, `PHASE1B_PROTOCOL.md`, `PHASE1C_PROTOCOL.md`, and the
Phase 0 `PROTOCOL.md`), each with an explicit underpowered clause and a rule that a zero result is a result.

Two questions were pursued:

- **Q1 (lead time).** Can an earlier source be paired to a later regulatory event on the study's tracks, often enough
  to estimate how early a change is visible?
- **Q2 (fusion).** At an equal false-alarm budget, does adding a second recording stream improve detection of a
  *sustained* change over the regulatory stream alone?

Q1 was gated on a frozen criterion (≥10 eligible pairs across ≥2 firms); Q2 on a frozen criterion (≥10 onsets, a
pooled recall gain ≥0.10, and a Holm-adjusted sign test).

## 2. Q1: the sources cannot be joined

| finding | number | artifact |
|---|---|---|
| clinical trials in the store | 55,592 | `EARLIER_SOURCE_AUDIT.json` |
| trials assigned to the study's *device* tracks | **0** | same |
| therapy-area tracks with an id-identical device counterpart | 4 (`t_respiratory`, `t_ophthalmology`, `t_urology`, `t_womens_health`) | same |
| SEC 8-K records | 20,976 | same |
| 8-K records carrying a company key | **1,360** (≈5 per firm in window) | same |
| eligible trial→clearance pairs, primary scope | **0** | `LEAD_LAG_PROBE.json` |
| eligible pairs, assumed crosswalk | **3** across 2 firms | same |
| firm-level pairing | 0 eligible pairs, **303,942** skipped follow-on events | same |

The trial lane's taxonomy is the obstacle, not the volume. Building a therapy-area → device-track crosswalk after
observing outcomes would violate pre-registration, so the gate was reported as **NO-GO**, not re-opened. The same
shortage shapes the cell set: of the **47** firm-track cells that any stream touches, only **5** carry both streams
above the pre-declared floors.

**A note on firm-level pairing.** With thousands of clearances, "the next clearance after a trial" is usually days
away: Medtronic's 113 trials leave 303,942 follow-on events and 112 of 113 pairs below the two-quarter floor. A
pairing that nearly always succeeds carries no information about whether a change occurred.

## 3. Q2: the positive class is empty

Amended definition, fixed before the O1 run: a **sustained onset** is a firm-track quarter with at least one event
that opens an episode containing **≥2 regulatory events within four quarters**, after **≥12 months of silence**.

| set | cells | onsets in evaluation window (2022–2025) | artifact |
|---|---:|---:|---|
| primary (both streams above floors) | 5 | **0** | `CONCURRENT_DETECTION_EXPANDED.json` |
| secondary (regulatory only) | 11 | **0** | same |
| earlier two-track run | 6 | **1** | `CONCURRENT_DETECTION.json` |

The incidence ladder (`ONSET_LADDER.json`) explains why, and shows the finding is not an artefact of one threshold
choice:

| definition | candidate quarters after silence | qualifying onsets | cells with an onset |
|---|---:|---:|---:|
| 12 months silence, episode 4 quarters, ≥2 events (frozen) | 1 | **1** | 1 / 16 |
| 12 months silence, episode 8 quarters, ≥3 events | 1 | 1 | 1 / 16 |
| 24 months silence, any episode, any ≥2 threshold | **0** | **0** | 0 / 16 |

Loosening the episode window does not help; **lengthening** the silence requirement removes the last candidate. The
corpus's activity is continuous at this granularity: an active firm-track reports events regularly, and an inactive one
reports almost nothing. The "change" this study defined does not appear.

Two consequences follow, both stated in advance of the analysis:

1. **A rate-anomaly detector cannot find a change that is not there.** The Phase 0 pilot's zero recall (M0 and M1 both
   0 over 9 positives) and the expanded run's zero onsets are the same fact measured twice.
2. **Underpowering is not a sample-size problem that more data would fix at this unit.** Nine years of five firms is
   the corpus; the missing quantity is the *number of change events*, not the number of observations.

## 4. What remains measurable

Zero onsets does not make the corpus useless. Three things are still estimated, and were:

- **Activity levels and their persistence** — the quantity the deployed profile engine already reports, with measured
  detector error rates from the parent programme.
- **Source availability**, rigorously: no source in these stores reaches a verifiable first-publication timestamp
  (`first_seen_at` is the collection date), so availability is reconstructed with a declared lag and a sensitivity
  analysis. That is a reusable instrument, and its audits are recorded (including two defects of our own, fixed and
  documented).
- **Coverage**, cell by cell: 5 firms × 42 touched tracks, of which 2 tracks support cross-firm comparison at the
  pre-declared floors.

## 5. Why this is a result and not a failure

A study that reports only the cells where its definition happened to fire would have produced a number — for example a
recall of 1.0 from a single onset — and that number would have been worthless. Three pre-registered gates, all
negative, now bound the question:

| gate | criterion (frozen) | result | verdict |
|---|---|---|---|
| G1 lead time | ≥10 eligible pairs, ≥2 firms | 3 pairs, 2 firms | **NO-GO** |
| O1 two-track fusion | ≥10 onsets | 1 onset | **underpowered** |
| O1 expanded fusion | ≥10 onsets | 0 onsets | **underpowered** |

The transferable statement is: **at firm × technology-track × quarterly resolution, public regulatory recording of
medical devices does not exhibit sustained changes to detect; the detectable signal is continuous activity.** Any
future study of early warning in this domain must either change the unit (firm-level, all tracks, or event-level
sequences), change the target (a milestone with an independently recorded confirmation date), or obtain data with
higher temporal resolution than quarterly filings.

## 6. Limitations, including the ones that limit us

- The result is **definitional as well as empirical**: a different operationalisation of "change" (for example a shift
  in track mix rather than in count) could behave differently. We did not test that, and we do not claim our definition
  is the only reasonable one.
- Recalls share a regulator with clearances, so the second stream's independence is **partial**.
- Two of the five firms are resolved by applicant-string matching, with one confirmed false-positive mode
  (`Surge Medical Sales` matching `GE MEDICAL`) and six strings awaiting adjudication. Dräger has no evaluable cell.
- The 60 candidate cases remain **PENDING_HUMAN_REVIEW**; no human label exists, so no Target B analysis was possible.
- Patents are absent from every frozen store; procurement timestamps are unusable (Tier C); the hiring lane is partial.

## 7. Reproduction

```bash
python experiments/b080/coverage_audit.py             # coverage matrix + evidence-time audit
python experiments/b081/entity_and_domain_audit.py    # entity resolution + domain sharing
python experiments/b084/earlier_source_audit.py       # trial/8-K tiers and the taxonomy gap
python experiments/b085/lead_lag_probe.py             # frozen G1 gate
python experiments/b086/concurrent_detection.py       # two-track O1
python experiments/b087/cell_inventory.py             # coverage-only cell selection
python experiments/b088/concurrent_expanded.py        # expanded O1 with sign test + Holm
python experiments/b089/onset_ladder.py               # positive-class incidence ladder
```

Every number above is asserted against its artifact by `papers/CLAIMS_NEGATIVE.json` and
`papers/verify_claims.py --paper papers/PAPER_NEGATIVE_v1.md --claims papers/CLAIMS_NEGATIVE.json`.
