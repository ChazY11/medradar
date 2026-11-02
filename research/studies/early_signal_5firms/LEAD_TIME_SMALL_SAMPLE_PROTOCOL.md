# PROTOCOL AMENDMENT — small-sample lead-time estimation (scope S1-crosswalk-effective)

**Status:** FROZEN before the distribution was computed · **Study:** `early_signal_5firms` ·
**Parent:** `PHASE1_PROTOCOL.md` (G1), `STUDY_DECISIONS.md` S-020 (crosswalk GO, fragile)

> G1 passed on the frozen *pair* count (17) but the 17 pairs reuse only **9 distinct later clearances**, below the floor
> of 10 independent pieces of evidence. Rather than declare victory or abandon the result, this amendment fixes **how
> the 9 observations may be described**. It is written before the numbers are computed.

---

## 1. What is being estimated

The lead time, in quarters and days, between a **trial assigned to a device track by the keyword crosswalk** and the
**first subsequent regulatory clearance in that same track for that firm** — on the nine distinct later clearances that
the authorised crosswalk found.

This is a **description of nine events**, not an estimate of a population quantity. No claim about medical devices in
general, or about early warning, follows from it.

## 2. Independence rule (frozen)

- The unit of observation is the **distinct later clearance**, not the pair. If several trials precede the same
  clearance, they are one observation, reported with all candidate trials listed.
- Therefore **n = number of distinct later clearances** (measured: 9), and no statistic may be reported with n = 17.

## 3. Representative choice (frozen, conservative)

For each distinct clearance:

- **Representative pair = the latest paired trial**, i.e. the **minimum** lead among that event's candidate trials.
  This cannot inflate the lead time.
- The **maximum** lead for the same event (earliest paired trial) is reported **only as an upper bound**, labelled
  `upper_bound`, and never used in a median or share.

## 4. What will be reported

- per-event table: firm, track, clearance kind/date/id, representative trial date/id, matched keywords, lead in
  quarters and days, candidate-trial count, minimum and maximum lead;
- the distribution of representative leads: **median, IQR, range**, plus the number of events with lead ≥ 1 and ≥ 2
  quarters;
- per-firm and per-track breakdowns, with a statement where a group has fewer than three events;
- **no confidence interval.** With 9 events across 3 firms, a bootstrap interval would be dominated by which firm is
  resampled; reporting one would imply inferential content this design does not have.

## 5. Underpowering statement (mandatory wording)

Every mention of these numbers must carry, in the same sentence, the fact that the frozen G1 independence floor is 10
and that **n = 9**. The verdict line must read: *"descriptive only; n = 9 independent events, below the floor of 10,
therefore underpowered and not a lead-time estimate."*

## 6. Human-review boundary

The nine events are emitted as **evidence packets** with `human_review_status = PENDING_HUMAN_REVIEW`. A reviewer must
confirm, per packet: that the trial is genuinely device-relevant (not a drug trial matched by a keyword accident), that
the clearance belongs to the same firm-track, and that the lead is not an artefact of the post-hoc crosswalk. Until
that is done, the packets are candidates, not labels.

## 7. What this cannot support, whatever the numbers say

- Not a lead-time estimate; not a detection performance claim; not a statement that trials predict clearances.
- Not generalisable: nine events, three firms, a text heuristic crosswalk built for this corpus.
- Not evidence about technology change: a trial preceding a clearance by two quarters is compatible with both "early
  warning" and "the same R&D programme happening to be filed in that order".
