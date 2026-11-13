# PHOENIX-003 — Next experiment

Derived only from what this round measured. Every proposal below names the result that motivates
it, the design that would test it, and the reason it is not being run now. Ordered by expected
information per unit of work.

---

## The single change that would make the next round different

PHOENIX-003 selected milestones and then looked backwards for evidence. The control battery shows
why that cannot work: **any** milestone of a publishing firm has earlier product-named records, so a
backwards search cannot distinguish signal from base rate.

Flipping the direction removes the problem. The remaining candidate for a genuine "early signal" is
not a date but an **object**: a device name that appears in public evidence while it has *no*
regulatory footprint at all. That object is observable in the present, and its later fate is
measurable. This is what `NEXT_EXPERIMENT.md` should be built on.

## N1 — Prospective evidence-first registry (highest value)

**Motivated by:** F6 (92 % of backwards matches are follow-up of regulated products) and F8 (a
hindsight-free query reaches the eventual evidence 82.9 % of the time, at 119 records per
milestone).

**Design.** Every week, run the frozen hindsight-free query against the two corpora for a fixed
list of firms, and record every *newly observed* product-name token that (a) appears in a paper or
trial and (b) has **no** canonical regulatory record yet. Freeze the observation time, the token,
the source id and the query that produced it. Then wait. The outcome is the time to first FDA
record for that token, and the measurable quantity is the **precision of the registry** — the share
of registered tokens that eventually get a regulatory record — against a matched background of
tokens invented by a decoy procedure.

**Why it is decisive.** It converts the lead-time question into a survival/precision question
answerable with the same control battery (decoy tokens, shifted observation dates), and it removes
the hindsight term entirely because the observation date is the date of *collection*, not of
metadata.

**Cost / blocker.** Needs continuous collection (the repo's observatory machinery already does
append-only collection, PR #13, unmerged) and years of waiting. Start it now; it will not pay off
this quarter. This is the only design on this list that can produce a *prospective* claim.

## N2 — Human adjudication of the 28 strict cases (cheapest, immediate)

**Motivated by:** F7 and U2. `HUMAN_REVIEW_QUEUE.csv` has the 40 highest-value rows; the 28 strict
cases are ranks 1–28.

**Design.** A domain annotator answers the three frozen questions per row (same technology? public
before the milestone? identifiable without knowing the outcome?) on a 3-point scale, blind to the
queue's ordering rationale. Report inter-rater agreement over a 10-case overlap and the resulting
adjudicated case count with a Clopper-Pearson interval.

**What it buys.** A real precision number for the strict class, which this round explicitly refuses
to report. Without it, the 28 cases stay "machine-verified" and no stronger claim is possible.

## N3 — Cross-registry novelty check (fixes a known defect)

**Motivated by:** U3/U5 and the Melody case. A product approved earlier by HDE, or cleared in
Europe, looks brand-new to a 510(k)/PMA-only corpus.

**Design.** Add two public registers with stable identifiers: the EUDAMED / national competent
authority CE-mark listings (or, if access is impractical, a frozen copy of the FDA HDE list) and a
non-US trial register (ISRCTN/DRKS/ChiCTR are OAI/JSON-friendly). Re-classify the 28 strict cases
with a "first public regulatory footprint anywhere" date instead of "first FDA record".

**Expected outcome.** Some of the 28 will move from pre-regulatory to pre-existing. That is a
success: the point is to make the class honest. The Melody case predicts at least one.

## N4 — Product-code-level base rate, not firm-level

**Motivated by:** F4/F5. The decoy is currently matched at the *firm* level, which is a weak null.

**Design.** Build the base rate inside the same product code: for each anchor, the null is "some
other firm's device in the same FDA product code appears in public evidence before this date". That
isolates the technology class and removes the confound that firms publish at different rates. If
specificity stays below 3 against this harder null, the instrument is definitively dead; if it
survives, it becomes interesting.

**Why not now.** It needs the product-code → evidence mapping at a granularity the corpora do not
support for codes with very few firms; a pilot on the 5 largest codes is the right scope.

## N5 — Hiring as an independent leading source, done properly

**Motivated by:** the brief's list of candidate evidence sources, of which hiring is the one this
round did not touch. S-031/PR #22 explored it and found the lane honest but noisy.

**Design.** Only if a lawful, stable source with historical snapshots exists. The trap to avoid is
the same one this round measured: "capability keyword appears in a job post before the milestone"
will link almost every milestone, exactly like C1 (99.3 %). A defensible version needs
(i) an employer-verified posting, (ii) a *new* capability term absent from the firm's earlier
postings, and (iii) the same decoy/placebo battery.

## N6 — Do not do

* **Do not add models or features to the backwards task.** This round measured that the signal is a
  base rate; a larger model fits the base rate more precisely.
* **Do not report the 187-anchor lead time as a product metric.** It is the number C1 explains.
* **Do not enlarge the firm list to raise the strict-case count.** F9 shows stability already;
  more firms buy more of the same and increase the risk of a publication-footprint artefact.

## Concrete acceptance criteria for PHOENIX-004

1. The prospective registry (N1) must be running with a frozen query and a committed decoy
   background before any result is examined.
2. The 28 strict cases (N2) must have ≥ 2 independent human adjudications and a reported
   agreement statistic, or be reported as unadjudicated.
3. Any lead-time number must be reported next to C1, C3 and C4 recomputed for that round's sample.
   A round that omits the keyword baseline is not admissible, regardless of its p-values.
4. The pre-regulatory class must use "first public regulatory footprint anywhere" (N3), not
   "first FDA record", or the claim must say FDA-only.
5. No Precision/Recall/F1 without a human label set; no "early warning" language for a
   retrospective association.
