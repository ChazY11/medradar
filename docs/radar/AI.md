# The local enrichment model: what it is, what it may do, and what it measured

Status: **implemented and measured; not on the critical path.**

RADAR-001 required a real local small-model test, not a plan. This document records the model,
the prompt, the vetting gate, the measured numbers, and — most importantly — the limits those
numbers imply.

## What the model is

| | |
| --- | --- |
| Model | Qwen3-0.6B (local directory, no download at run time) |
| Runtime | `transformers` + PyTorch, CPU, float32, 4 threads |
| Process | one-shot subprocess per batch, lowered priority, exits when the batch ends |
| Interpreter | `MEDRADAR_AI_PYTHON` (an ML virtualenv); the serving interpreter does not need torch |
| Prompt | `radar-ai-prompt-1` (`medradar/radar/ai/prompts.py`) |
| Output contract | one JSON object: `topics[]`, `organizations[]`, `summary` |

4B-class models are deliberately excluded as a default: the measured peak of the 0.6B build is
already the dominant memory cost on the production host (see below).

## What the model may do

It proposes, and every proposal is stored in `ai_candidate` with the deterministic verdict.
Nothing it produces is a confirmed fact, because two independent checks must pass:

1. **Topic claim**: the topic id must exist in the committed taxonomy, and the
   `evidence_quote` must appear **verbatim** in the record's own title/abstract/description.
2. **Organisation claim**: the published name must resolve through the committed alias table,
   and its quote must be verbatim.

A rejected claim is stored with its reason. A rejected claim is a *correct behaviour*, not a
miss: it is the gate doing its job.

The model is also allowed to return nothing. An empty `topics` list is a valid, stored answer.

## What it measured

From the acceptance run (`evidence/acceptance_report.md`, test E), 11 real labelled records,
4 CPU threads:

| Metric | Value | Reading |
| --- | --- | --- |
| JSON validity | **1.0** | the prompt's single-object contract held for every answer |
| Topic precision | **0.18** | the 0.6B model over-labels |
| Topic recall | **0.18** | and still misses most expected topics |
| Topic F1 | **0.18** | *not usable as a classifier* |
| Organisation accuracy | **0.73** | better, but the alias table alone does better |
| Evidence fidelity | **1.0** | every accepted claim's quote was verbatim; the gate holds |
| Throughput | ~9.6 tokens/s | ≈18 s per record on 4 threads |
| Peak RSS | ~3.17 GB | float32 weights + PyTorch |
| Model load | ~7 s | paid once per batch, returned to the OS on exit |

**The honest conclusion is negative.** For *this* taxonomy and *this* corpus, the rule layer
(FDA product codes + curated keyword regexes + alias resolution) is more accurate, faster,
cheaper and fully auditable. The model is therefore wired as an optional enrichment stage that
adds candidate topics for human review, and the product does not depend on it.

That is the same conclusion the earlier local-LLM research in this repository reached, and it
is recorded here rather than buried.

## Resource safety

The measured 3.2 GB peak is why the guard exists and why its estimate is not optimistic:

* `RadarScheduler._run_ai` asks the guard for `estimated_model_mb=3300` and 1.5x headroom;
* on the 2 vCPU / 4 GB production host the guard refuses, records the refusal with the exact
  memory figures, and the cycle continues — **discovery is never delayed by AI**;
* the backlog is retained (state `DEFERRED`), so nothing is lost;
* the model runs in its own process, so its memory returns to the OS when the batch ends;
* acceptance test G measured a live discovery check and the read-only API *while* the worker
  ran, and both stayed within their thresholds.

To enable enrichment on the production host, use a quantised or bf16 build (≈1.5–1.8 GB) and
re-run the acceptance to record the new peak before enabling it in production.

## Running it

```
# one batch, writes results to the ledger and the runtime state
MEDRADAR_AI_PYTHON=/path/to/mlvenv/bin/python \
  python -m medradar radar ai run --limit 8 --model /path/to/Qwen3-0.6B

# status
python -m medradar radar ai status

# measured evaluation against the labelled set
MEDRADAR_AI_PYTHON=/path/to/mlvenv/bin/python \
  python -m medradar radar ai eval --model /path/to/Qwen3-0.6B \
         --out docs/radar/evidence/ai_eval.json
```

`MEDRADAR_AI_MODEL` points at the model directory if `--model` is not given.

## The labelled set

`config/radar/ai_eval_set.json` — 14 records keyed by **official identifier** (so it survives a
database rebuild), hand-labelled by reading each record's official title and abstract. Its own
`limitations` field records that 14 items can detect a broken prompt or a fabrication, not
establish general accuracy, and that the sample is skewed towards prediction papers.

Four of the 14 records were not present in the evaluation ledger at run time (they belong to
sources fetched on a different day); the report says `evaluated: 11` rather than silently
scoring them.
