# LABELING PROTOCOL — what counts as a technology shift, and who is allowed to say so

**Study:** `early_signal_5firms` · **Status:** draft for human sign-off · **Applies to:** `CASE_CANDIDATES.json`

---

## 1. Division of labour (binding)

| actor | may do | may not do |
|---|---|---|
| the agent | assemble candidate packets, retrieve evidence, compute measurable features, flag ambiguity, prepare the review form | **assign any label**; declare a case confirmed; treat its own judgement as human truth |
| a named human reviewer | adjudicate every case, record reasoning and the evidence used | delegate the label back to the agent for convenience |

Every packet is emitted with `human_review_status = PENDING_HUMAN_REVIEW` and `final_label = null`. A pipeline that
auto-fills labels would be manufacturing the gold standard it is then scored against.

## 2. Two independent targets

### Target A — Observable technology milestone (measurable, not a matter of taste)

A case is a **milestone** only if all hold:

1. the event is a **regulatory clearance/approval** (510(k) or PMA) or a documented product commercialisation with a
   public date;
2. it falls in a **study track** for the firm in question;
3. the firm had **no event in that track for at least 12 months** beforehand (the `novel_entry` stratum), or the
   reviewer records a documented strategic statement (e.g. an 8-K, an earnings-call disclosure) naming the direction;
4. the **date of first public confirmation** is recorded separately from the event date.

Target A is auditable and can be scored mechanically once the reviewer signs the definition. It measures *observable
activity*, not strategic intent.

### Target B — Expert-adjudicated technology shift (human only)

The reviewer answers, using multiple sources:

- Did the firm's technology positioning actually change, or is this an ordinary product iteration?
- Is the change **sustained** (visible in later periods), or a one-off?
- Could it be an artefact of **taxonomy churn** (a product code remapped between tracks)?
- Could it be an artefact of **corporate restructuring** (entity renamed, business unit sold, e.g. the GE lineage)?
- Can the **date of change** and the **date of first public confirmation** be separated?

Allowed labels, mutually exclusive:

| label | meaning |
|---|---|
| `Confirmed Shift` | positioning changed, sustained, independently confirmable, dates separable |
| `Routine Iteration` | an incremental product update within an existing direction |
| `False Signal / No Confirmed Shift` | the candidate does not correspond to a real change |
| `Uncertain` | evidence conflicts or is insufficient to decide, but the case is real |
| `Insufficient Observation` | too little time/coverage after the candidate to judge (not a negative) |

**`Insufficient Observation` is not a negative label.** Cases without a mature observation window may not be counted as
false alerts; they are censored and reported as such.

## 3. Independence requirement (the core anti-circularity rule)

A case may only be labelled `Confirmed Shift` if the confirming evidence is **independent of the source that raised
the candidate**:

- candidate raised by a 510(k) → confirmation may come from trials, 8-K disclosures, recalls, or a documented
  commercial launch — **not** from another 510(k) in the same track by the same firm;
- candidate raised by a trial → confirmation may come from a clearance or a commercial milestone;
- if no independent source exists, the case cannot be confirmed and must be labelled `Uncertain` or
  `Insufficient Observation`.

This rule exists because the programme has already retracted a finding whose "confirmation" came from the same signal
family that produced the alert.

## 4. Evidence packet fields (fixed)

`case_id`, `company`, `technology_track`, `track_role` (confirmatory / exploratory), `stratum_by_gap_rule`,
`era`, `candidate_alert` (rule, quarter, event date, days since previous), `evidence` (event id, kind, product code,
applicant string, source, URL, declared availability with its basis), `counter_evidence`, `independent_outcome`,
`human_review_status`, `final_label`, `review_note`.

The reviewer fills `counter_evidence`, `independent_outcome`, `final_label`, `review_note`, and must record **which
sources were searched** even when nothing was found — an empty search and a searched-and-empty verdict are different
facts.

## 5. Sampling rules (already applied)

- Selection is **outcome-blind**: a prospective gap rule (≥12 months = `novel_entry`; 4–11 = `ambiguous`; ≤3 =
  `routine` control), stratified by era and track, fixed seed 8080.
- No case was chosen because it is famous or because its outcome is known.
- 60 candidates: 20 / 20 / 20 across the three strata. The `routine` stratum exists so that a classifier that calls
  everything a shift is visibly penalised.

## 6. Handling of known contamination risks

| risk | treatment |
|---|---|
| taxonomy remap | a case whose candidate-ness depends on a product code that moved tracks must be flagged; the labelling form asks for it explicitly |
| corporate restructuring | GE lineage cases must state which legal entity the evidence belongs to; absent that, `Uncertain` |
| Dräger | not evaluable in any domain (6 observations in 4 quarters); descriptive only, excluded from scoring |
| alias false positives | `Surge Medical Sales`-type substring matches are excluded from candidate generation; six flagged strings await human adjudication |

## 7. What the 60 packets are not

They are **candidates**, not a benchmark. Until a human reviewer adjudicates them, no recall, precision, lead time or
calibration statement may be computed from this set, and none is claimed in Phase 0.
