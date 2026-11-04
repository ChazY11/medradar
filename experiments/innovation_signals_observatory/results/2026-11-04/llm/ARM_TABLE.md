# LLM job-text experiment · arm table

Schema: `medradar.job_text_extraction.v1` · prompt: `None` · generated: 2026-11-04T13:18:09.386877+00:00

## Headline metrics (per arm, same items)

| Arm | n | items (primary/negative) | JSON valid | Schema pass | Claim-quote locatability | Function cue-support | Track cue-support | Abstain rate | Neg-control false positives | Median latency (s) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 42 | 32/10 | 1.000 | 1.000 | 1.000 (192/192) | 1.000 (37/37) | 1.000 (5/5) | 0.119 | 0.000 (0/10) | 0.006 |
| C | — | — | — | — | — | — | — | — | — | — |

**Arm C = NOT_RUN.** NOT_RUN: the only existing QLoRA adapter (PR #20, overnight-2026-11-04) was trained on regulatory-event text under the frozen event schema (event category, three timestamps, company entity, product). Job text is a different task with a different output contract, and the adapter was never trained on job postings. Running it would measure schema/task incompatibility, not job-text extraction capability, so arm C produces no number here. This is a statement about the experiment design, not about the model.

## Negative-control detail (headline, not a footnote)

| Arm | n negatives | FP (track or R&D class) | FP track only | FP R&D function only | Abstained | UNCLASSIFIED both | Correct rejection |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 10 | 0 | 0 | 0 | 1 | 1 | 10 |

Definition: a negative-control posting is a real posted role whose **title** declares a non-technical occupation (Buyer/Planner, customer service, warehouse, administrative, finance, non-technical co-op). False positive = arm asserted a technology track or an R&D function class on such a posting.

## Error taxonomy (counts)

| Arm | Error counts |
|---|---|
| A | (none) |

## Explicit non-metrics

- Precision / Recall / F1: **NOT_EVALUABLE: no human gold standard exists for this corpus**.
- Confidence calibration: **NOT_AVAILABLE: rule-derived strength / qualitative note, not a calibrated probability**.
- Cue-support rates are a conservative deterministic check against committed cue lists; a False does not prove a label wrong, and arm A's support is circular by construction.

