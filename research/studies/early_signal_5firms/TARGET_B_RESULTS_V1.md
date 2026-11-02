# Target B — final adjudication results (owner-authorised AI adjudication)

**Status:** final for this study by owner authorisation (2026-11-03). **Human truth: no.** The labels are the
owner-authorised external AI review; they may not be described as expert or human adjudication.
**Artifacts:** `ADJUDICATION_FINAL_V1.json` (labels + provenance), `CASE_PACKETS_FINAL_V1.json` (additive merge;
V2 unchanged). **Reproduce:** `python experiments/b100/finalise_ai_adjudication.py`.

## Label distribution (69 packets)

| label | packets |
|---|---:|
| `Confirmed Shift` | 0 |
| `Routine Iteration` | 52 |
| `False Signal / No Confirmed Shift` | 8 |
| `Uncertain` | 9 |
| `Insufficient Observation` | 0 |

**Target B result:** 0/69 confirmed shifts (0.0%; one-sided 95 % Wilson upper bound 5.3%); 8 false signals; 52 routine iterations; 9 uncertain.

## By origin

| origin | label | packets |
|---|---|---:|
| candidate | Routine Iteration | 52 |
| candidate | Uncertain | 8 |
| small_sample | False Signal / No Confirmed Shift | 8 |
| small_sample | Uncertain | 1 |

## By firm

| firm | label | packets |
|---|---|---:|
| ge_healthcare | Routine Iteration | 13 |
| ge_healthcare | Uncertain | 3 |
| medtronic | False Signal / No Confirmed Shift | 4 |
| medtronic | Routine Iteration | 14 |
| medtronic | Uncertain | 3 |
| mindray | Routine Iteration | 8 |
| mindray | Uncertain | 1 |
| philips | False Signal / No Confirmed Shift | 4 |
| philips | Routine Iteration | 17 |
| philips | Uncertain | 2 |

## Hypotheses

| hypothesis | status | why |
|---|---|---|
| H1_fusion | NOT_EVALUABLE | H1 needs positive labels to compare fusion recall against the best single source at a fixed false-alarm budget; the final adjudication contains no `Confirmed Shift`, so recall is undefined |
| H2_lead_time | NOT_EVALUABLE (and the prior description is withdrawn) | lead time is measured from an alert to a confirmed milestone; with zero confirmed milestones there is no lead time to measure, and the 9-event description was withdrawn in S-034 because 8/9 pairs are device/project mismatches |
| H3_heterogeneity | DESCRIPTIVE_ONLY | the label distribution by firm/track is reported, but with zero confirmed shifts there is no positive class to compare across firms |
| H4_density | NOT_TESTABLE | density bounds recall and lead time only if positives exist; there are none in the final set |

## What this means

- The candidate-generation design is **not validated**: it produced 0 confirmed shifts in 69 candidates.
- The nine-event lead-time description stays withdrawn (8/9 pairs are device/project mismatches, S-034).
- H1 (fusion) and H2 (lead time) cannot be evaluated for lack of positives; H3 is descriptive only; H4 is not
  testable. No recall, precision, calibration or lead-time claim is made.
- The study closes as a **negative result about its candidate generator**, not as evidence that the firms do
  not shift.
