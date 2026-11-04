# Local small-LM event extraction - benchmark report

> **REAL_DOCUMENT_UNLABELLED — real public documents, no human event labels; harness-level measurements only, no accuracy claim.**
>
> The documents in this run are real, publicly retrievable records; their provenance, hashes and retrieval dates are in the run manifest. Every harness-level number below (JSON validity, schema pass rate, verbatim quote location, abstention, latency, resources) was measured on those documents. No precision, recall or F1 is reported, because no human event labels exist for them: the corpus has not been annotated, so **nothing here measures extraction accuracy** and nothing here may be quoted as if it did.

Run `phase2-2026-11-04` - status: **REAL_DOCUMENT_UNLABELLED**

## Run identity

- run_id: `phase2-2026-11-04`
- created_at (UTC): 2026-11-04T00:56:24.442560+00:00
- status: `REAL_DOCUMENT_UNLABELLED`
- dataset: `real-medtech-documents-5firms` version `2026-11-04`; 19 cases; label tiers ['source_record_derived']
- dataset sha256: `92a41a66ccb121b06be0cf344e97f75ce988f571b2740e3c82bc27463e81af07` (source files: `92a41a66ccb121b06be0cf344e97f75ce988f571b2740e3c82bc27463e81af07`)
- cases per split: test=19
- seeds: [0]
- git: commit `dde4348569b5fcc4e49cb1661cdfcd7c884420b1`, branch `research/local-llm-foundation`, dirty=True
- config sha256: `7233e4c89f002152edf7989874a99de943d23950b9f329313d5182a7e5059b94`
- note: REAL_DOCUMENT_UNLABELLED — real public documents, no human event labels; harness-level measurements only, no accuracy claim
- note: validator: injected
- config: `{'corpus_dir': 'D:\\DEPPSKK\\worktrees\\local-llm-research\\experiments\\local_llm_event_extraction\\datasets\\real\\corpus\\2026-11-04', 'corpus_manifest_sha256': '92a41a66ccb121b06be0cf344e97f75ce988f571b2740e3c82bc27463e81af07', 'gate_env': {'MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD': '1'}, 'note': 'REAL_DOCUMENT_UNLABELLED run: real public documents, silver labels only for part of the corpus, no human labels. Accuracy is not research grade.'}`

## Arms

| Adapter | Display name | Backend | Status / reason |
|---|---|---|---|
| `rules-baseline` | ARM A - deterministic rules baseline | rule_based | RUN |
| `hf-qwen3-4b-instruct` | ARM B - Qwen/Qwen3-4B-Instruct-2507 (nf4) local | hf_local | RUN |

## Event-level metrics (micro, over events)

| Adapter | Support | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rules-baseline` | 19 | 1 | 4 | 18 | 0.200 | 0.053 | 0.083 |
| `hf-qwen3-4b-instruct` | 19 | 17 | 3 | 2 | 0.850 | 0.895 | 0.872 |

## Field and failure metrics

| Adapter | Entity acc. | Event-date acc. | Published-at acc. | Citation correct | Abstention | Wrong abstention | False assertion | Parse failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `rules-baseline` | 1.000 | 0.500 | 1.000 | not measured | 0.737 | 0.737 | not measured | 0.000 |
| `hf-qwen3-4b-instruct` | 1.000 | 1.000 | 1.000 | not measured | 0.000 | 0.000 | not measured | 0.000 |

## Per-arm summary

**`rules-baseline`**

| Metric | Value |
|---|---:|
| support (documents with a prediction record) | 19 |
| tp / fp / fn | 1 / 4 / 18 |
| precision | 0.200 |
| recall | 0.053 |
| f1 | 0.083 |
| entity match accuracy | 1.000 |
| event-date accuracy | 0.500 |
| published-at accuracy | 1.000 |
| citation correctness | not measured |
| abstention rate | 0.737 |
| wrong abstention rate | 0.737 |
| false assertion rate | not measured |
| parse failure rate | 0.000 |

**`hf-qwen3-4b-instruct`**

| Metric | Value |
|---|---:|
| support (documents with a prediction record) | 19 |
| tp / fp / fn | 17 / 3 / 2 |
| precision | 0.850 |
| recall | 0.895 |
| f1 | 0.872 |
| entity match accuracy | 1.000 |
| event-date accuracy | 1.000 |
| published-at accuracy | 1.000 |
| citation correctness | not measured |
| abstention rate | 0.000 |
| wrong abstention rate | 0.000 |
| false assertion rate | not measured |
| parse failure rate | 0.000 |

## Per-category metrics

**`rules-baseline`**

| Category | Gold | Predicted | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| clinical_trial_result | 0 | 2 | 0 | 2 | 0 | 0.000 | not measured |
| clinical_trial_start | 5 | 0 | 0 | 0 | 5 | not measured | 0.000 |
| m_and_a | 0 | 1 | 0 | 1 | 0 | 0.000 | not measured |
| regulatory_approval | 4 | 0 | 0 | 0 | 4 | not measured | 0.000 |
| regulatory_clearance | 5 | 0 | 0 | 0 | 5 | not measured | 0.000 |
| safety_recall | 5 | 2 | 1 | 1 | 4 | 0.500 | 0.200 |

**`hf-qwen3-4b-instruct`**

| Category | Gold | Predicted | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| clinical_trial_result | 0 | 1 | 0 | 1 | 0 | 0.000 | not measured |
| clinical_trial_start | 5 | 5 | 5 | 0 | 0 | 1.000 | 1.000 |
| manufacturing_change | 0 | 2 | 0 | 2 | 0 | 0.000 | not measured |
| regulatory_approval | 4 | 2 | 2 | 0 | 2 | 1.000 | 0.500 |
| regulatory_clearance | 5 | 5 | 5 | 0 | 0 | 1.000 | 1.000 |
| safety_recall | 5 | 5 | 5 | 0 | 0 | 1.000 | 1.000 |

## Per-source-type metrics

**`rules-baseline`** by source type

| Source type | Gold | Predicted | TP | FP | FN |
|---|---:|---:|---:|---:|---:|
| clinical_trial_record | 5 | 1 | 0 | 1 | 5 |
| fda_510k | 5 | 0 | 0 | 0 | 5 |
| fda_pma | 4 | 1 | 0 | 1 | 4 |
| fda_recall | 5 | 3 | 1 | 2 | 4 |

**`hf-qwen3-4b-instruct`** by source type

| Source type | Gold | Predicted | TP | FP | FN |
|---|---:|---:|---:|---:|---:|
| clinical_trial_record | 5 | 6 | 5 | 1 | 0 |
| fda_510k | 5 | 5 | 5 | 0 | 0 |
| fda_pma | 4 | 4 | 2 | 2 | 2 |
| fda_recall | 5 | 5 | 5 | 0 | 0 |

## Error taxonomy

| Adapter | Error | Count |
|---|---|---:|
| `rules-baseline` | false_positive | 4 |
| `rules-baseline` | false_negative | 18 |
| `rules-baseline` | date_mismatch | 1 |
| `rules-baseline` | wrong_abstention | 14 |
| `hf-qwen3-4b-instruct` | false_positive | 3 |
| `hf-qwen3-4b-instruct` | false_negative | 2 |

## Measured resources

| Adapter | Wall (s) | CPU (s) | Peak RSS (MB) | Peak VRAM (MB) | Tokens in | Tokens out | Est. cost (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rules-baseline` | 0.287 | 0.266 | 33.590 | not measured | not measured | not measured | not measured |
| `hf-qwen3-4b-instruct` | 546.134 | 510.359 | 2324.430 | 5020.208 | 30768 | 5230 | not measured |

`not measured` is a real value: the backend did not report it (no tokenizer, no GPU, remote arm). It is never rendered as zero.

## Matching protocol

Scoring protocol version: `v1`

- **unit**: events, micro-averaged over documents that have a prediction record
- **matching**: greedy 1:1 within each document: gold events in dataset order, predicted events in output order, first compatible unused pair wins
- **match_requires**: predicted.company.canonical_id == gold.company_canonical_id; predicted.event_category == gold.event_category; dates compatible: exact equality when gold.event_date is present; date-agnostic when gold.event_date is null
- **field_protocol**: entity/date/published-at/citation metrics use a second greedy pairing that requires only event_category, so a wrong entity or date is reported as such instead of collapsing into fp+fn
- **date_rule**: exact string equality on YYYY / YYYY-MM / YYYY-MM-DD when the gold date is present; a null gold date is date-agnostic
- **citation_rule**: correct when at least one predicted evidence quote is a verbatim substring of the document (whitespace/case-normalised fallback) and overlaps the gold evidence quote (containment, or longest common substring >= max(24, half the gold quote length))
- **abstention_rule**: a document abstains when it asserts zero extracted events (no events, all abstained, or a parse failure); wrong_abstention is an abstention on a document that has gold events
- **negative_control_rule**: a case with expected_abstain=True and no gold events; asserting any event on it is a false assertion
- **duplicate_rule**: identical asserted events within one document are counted in the error taxonomy
- **zero_denominator**: null (not measured), never 0.0
- **support**: documents that have a prediction record
- **seeds**: 0

Arm `rules-baseline` rule table (`rules-v1`, deterministic):

- `regulatory_negative`: A regulator refused, rejected or blocked the product. (patterns: `\bcomplete response letter\b`, `\bnot\s+(?:been\s+)?approved\b`, `\bdeclin(?:ed\|es)\s+to\s+approve\b`, `\brefus(?:ed\|es)\s+to\s+(?:approve\|clear\|grant)\b`, `\bdeni(?:ed\|es)\b`, `\brejected\b`, `\bwarning letter\b`, `\bfailed to (?:win\|gain\|obtain) (?:approval\|clearance)\b`)
- `regulatory_submission`: A dossier was filed with a regulator. (patterns: `\b510\s*\(k\)\s+submission\b`, `\bpremarket approval application\b`, `\b(?:submitted\|filed)\b[^.]{0,60}\b(?:510\s*\(k\)\|pma\|premarket\|de novo)\b`, `\bregulatory submission\b`)
- `regulatory_approval`: A regulator granted approval (e.g. PMA). (patterns: `\bpremarket approval\b`, `\bfda approval\b`, `\bapproved by the\b[^.]{0,20}\bfood and drug administration\b`, `\b(?:granted\|received\|obtained\|won)\b[^.]{0,40}\bapproval\b`, `\bpma (?:approval\|supplement)\b`)
- `regulatory_clearance`: A regulator cleared a device (510(k), CE mark, De Novo). (patterns: `\b510\s*\(k\)\s+clearance\b`, `\bfda clearance\b`, `\bclear(?:ed\|ance)\b[^.]{0,40}\bfood and drug administration\b`, `\bfood and drug administration\b[^.]{0,60}\bclearance\b`, `\bce mark\b`, `\bde novo\b`, `\bgranted\b[^.]{0,40}\bclearance\b`, `\bclearance\b`)
- `safety_recall`: A product was recalled or withdrawn from the market. (patterns: `\brecall(?:s\|ed)?\b`, `\bclass (?:i\|ii\|iii) recall\b`, `\bfield safety (?:notice\|corrective action)\b`, `\bmarket withdrawal\b`, `\bwithdraw(?:s\|n)?\b[^.]{0,40}\bfrom (?:the )?market\b`, `\bsafety alert\b`)
- `clinical_trial_start`: A clinical trial or study started. (patterns: `\b(?:initiated\|began\|started\|commenced\|launched)\b[^.]{0,60}\b(?:phase\s+(?:i\|ii\|iii\|1\|2\|3)\|pivotal\|clinical)\s+(?:trial\|study)\b`, `\b(?:phase\s+(?:i\|ii\|iii\|1\|2\|3)\|pivotal\|clinical)\s+(?:trial\|study)\b[^.]{0,40}\b(?:began\|started\|initiated\|commenced)\b`, `\b(?:study\|trial)\s+(?:began\|started\|was initiated)\b`, `\bfirst patient (?:was )?(?:enrolled\|dosed)\b`, `\b(?:enrolled\|dosed)\b[^.]{0,30}\bfirst patient\b`)
- `clinical_trial_result`: Trial results were reported. (patterns: `\btopline (?:results\|data)\b`, `\b(?:primary\|secondary) endpoint\b`, `\bmet (?:the \|its )?(?:primary\|secondary) endpoint\b`, `\bresults (?:from\|of) the\b[^.]{0,60}\b(?:trial\|study)\b`, `\bdid not meet\b[^.]{0,40}\bendpoint\b`)
- `product_discontinuation`: A product or line was discontinued. (patterns: `\bdiscontinu(?:ed\|es\|ation)\b`, `\bceas(?:ed\|es)\b[^.]{0,40}\b(?:sales\|distribution\|manufacturing)\b`, `\bend(?:ed\|s)\b[^.]{0,30}\b(?:sales\|distribution)\b`)
- `product_launch`: A product was launched or made commercially available. (patterns: `\blaunch(?:ed\|es\|ing)?\b`, `\bcommercial(?:ly)? (?:launch\|availability\|release)\b`, `\bnow available\b`, `\bmarket (?:launch\|release\|availability)\b`, `\bintroduc(?:ed\|es)\b[^.]{0,40}\b(?:product\|system\|device\|platform)\b`, `\breleased\b[^.]{0,40}\b(?:commercially\|in the us\|nationwide)\b`, `\bbeg(?:an\|un)\b[^.]{0,40}\b(?:selling\|shipping\|commercial)\b`)
- `m_and_a`: One company acquired or merged with another. (patterns: `\bdefinitive agreement to acquire\b`, `\bacquir(?:e\|ed\|es\|ing\|ition)\b`, `\bmerger\b`)
- `rd_collaboration`: A research/development collaboration or licence was announced. (patterns: `\bjoint development\b`, `\bco-?develop(?:ment\|ed\|s)?\b`, `\bresearch (?:agreement\|collaboration)\b`, `\blicen[cs]e agreement\b`, `\bcollaborat(?:e\|ed\|ion\|ions)\b`)
- `partnership`: A commercial partnership or alliance was announced. (patterns: `\bstrategic alliance\b`, `\bpartnership\b`, `\bpartner(?:ed\|s)? with\b`)
- `manufacturing_change`: A manufacturing footprint change. (patterns: `\bmanufacturing (?:facility\|expansion\|plant\|site)\b`, `\bnew (?:manufacturing\|production) (?:line\|facility\|site)\b`)
- `patent_grant`: A patent was granted. (patterns: `\bpatent (?:was \|is \|has been )?granted\b`, `\b(?:granted\|issued)\b[^.]{0,30}\bpatent\b`)
- `scientific_publication`: A peer-reviewed result was published. (patterns: `\bpublished\b[^.]{0,60}\b(?:journal\|peer[- ]reviewed\|study\|paper\|article)\b`, `\bpublished in\b`, `\bpeer[- ]reviewed\b`, `\bjournal of\b`, `\bmanuscript\b`)

## What this does not show

- It does not show how any model performs on real medtech documents. The documents are hand-written synthetic fixtures.
- It does not show whether local small models beat the rule baseline in production; no model was loaded for this run.
- It does not contain human-confirmed labels. Label tiers recorded above: ['source_record_derived'].
- It does not estimate cost or latency of a real local deployment. Wall/CPU/RSS numbers are for this process on this machine and only for the cases that actually ran.
- It does not validate the rule table against an external corpus; the rule table is included only so arm A's behaviour is inspectable.
- It does not turn `not measured` into zero: any field rendered as `not measured` was genuinely unavailable, and a zero denominator is `None` in `metrics.json`, never `0.0`.
- Arm A's scores on this fixture set are partly a property of the fixtures: several sentences were written deliberately in the keyword style the rule table targets, and the synthetic roster aliases were supplied to arm A. That is not a field accuracy estimate.

## Artifacts

- `predictions.jsonl` - one record per (adapter, case), appended live
- `metrics.json` - per-adapter metric reports and NOT RUN reasons
- `manifest.json` - dataset/adapter/git/config identity and resources

