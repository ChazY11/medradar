# LLM job-text experiment · arm table

Provenance (from run manifests, not retyped): model `Qwen/Qwen3-4B-Instruct-2507` revision `unpinned-local-weights` (local weights directory has no immutable HF revision; the unpinned override and the weights fingerprint are recorded instead); weights sha256 `6e200db34e5751f4…`; prompt `job-extract-v2` template sha256 `76266549bcf47675…`; schema `medradar.job_text_extraction.v1`; subset rule `phase4-jobsplit-v1` (salt `phase4-jobsplit-v1`, n_primary=12, n_negative=8); input_char_budget=[3000]; max_new_tokens=[320].

Generated: 2026-11-04T14:37:12.610187+00:00
## Headline metrics (per arm, same items)

| Arm | n | items (primary/negative) | JSON valid | Schema pass | Claim-quote locatability | Function cue-support (field / any quote) | Track cue-support (field / any quote) | Abstain rate | Neg-control false positives | Median latency (s) | Peak VRAM (MiB) |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 20 | 12/8 | 1.000 | 1.000 | 0.940 (79/84) | 1.000 / 1.000 | 1.000 / 1.000 | 0.100 | 0.000 (0/8) | 0.005 | n/a |
| B | 20 | 12/8 | 1.000 | 1.000 | 0.894 (59/66) | 0.588 / 0.650 | 0.500 / 0.500 | 0.000 | 0.125 (1/8) | 20.856 | 13199 |
| C | — | — | — | — | — | — | — | — | — | — | — |

**Arm C = NOT_RUN.** NOT_RUN: the only existing QLoRA adapter (PR #20, overnight-2026-11-04) was trained on regulatory-event text under the frozen event schema (event category, three timestamps, company entity, product). Job text is a different task with a different output contract, and the adapter was never trained on job postings. Running it would measure schema/task incompatibility, not job-text extraction capability, so arm C produces no number here. This is a statement about the experiment design, not about the model.

## Negative-control detail (headline, not a footnote)

| Arm | n negatives | FP (track or R&D class) | FP track only | FP R&D function only | Abstained | UNCLASSIFIED both | Correct rejection |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 8 | 0 | 0 | 0 | 0 | 0 | 8 |
| B | 8 | 1 | 1 | 0 | 0 | 0 | 7 |

Definition: a negative-control posting is a real posted role whose **title** declares a non-technical occupation (Buyer/Planner, customer service, warehouse, administrative, finance, non-technical co-op). False positive = arm asserted a technology track or an R&D function class on such a posting.

## Error taxonomy (counts)

| Arm | Error counts |
|---|---|
| A | quote_not_located=5 |
| B | TIMEOUT=2, function_label_without_located_quote=3, function_quote_lacks_class_cue=7, internal_contradiction=4, negative_control_false_positive=1, quote_not_located=7, track_on_non_technical_function=4, track_quote_lacks_track_keyword=4 |

## Internal consistency (no gold standard needed)

A structurally valid payload can still be self-contradictory: a technology track attached to a `SALES_ADMIN_OTHER` / `UNCLASSIFIED` function class, or `r_and_d_evidence=true` for such a class. That is a reliability failure regardless of what the true label is.

| Arm | schema-ok items | contradictions | contradiction rate | track-on-commercial | R&D-flag-on-commercial |
|---|---:|---:|---:|---:|---:|
| A | 20 | 0 | 0.000 | 0 | 0 |
| B | 20 | 4 | 0.200 | 4 | 0 |

## Explicit non-metrics

- Precision / Recall / F1: **NOT_EVALUABLE: no human gold standard exists for this corpus**.
- Confidence calibration: **NOT_AVAILABLE: rule-derived strength / qualitative note, not a calibrated probability**.
- Cue-support rates are a conservative deterministic check against committed cue lists; a False does not prove a label wrong, and arm A's support is circular by construction.

## Arm A vs arm B agreement on the shared primary sample

- shared primary items: 12
- both arms UNCLASSIFIED (no direction claimed): 0
- A UNCLASSIFIED / B labelled: 2
- A labelled / B UNCLASSIFIED: 0
- both labelled: 10
- same function class: 8
- same non-UNCLASSIFIED track: 1

> agreement between classifiers, NOT accuracy: there is no human gold standard.

