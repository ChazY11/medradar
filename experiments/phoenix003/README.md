# experiments/phoenix003 — Regulatory-anchored early-evidence discovery

PHOENIX-003 asks one question: **before a device firm reaches an important regulatory milestone,
does an independent public source already describe the related technical activity — and could an
observer have identified it without knowing the future?**

The protocol, the frozen parameters and the failure modes this design must survive are in
[`docs/phoenix003/FROZEN_PROTOCOL.md`](../../docs/phoenix003/FROZEN_PROTOCOL.md). Read that first;
everything here implements it.

## Layout

```
FROZEN_RULES.json          machine-readable protocol parameters (code reads only this file)
REGULATORY_ANCHORS.jsonl   deliverable: de-duplicated regulatory anchors (Target A / Target B flags)
EVIDENCE_LINKS.jsonl       deliverable: every candidate, verified, ambiguous and rejected link
HUMAN_REVIEW_QUEUE.csv/md  deterministic review batch; the human_* columns are empty by design

code/
  phoenix003_common.py     dates, tokenizer, lineage resolver, Clopper-Pearson, io
  freeze_vocab.py          freezes the name vocabulary from the static catalogue + name corpus
  a1_anchors.py            canonical milestones -> first-in-code anchors (Target A)
  b_links.py               tier ladder L1..L5 over the frozen external corpora
  b2_novelty.py            pre-regulatory check + Target-B novelty flags
  c_controls.py            C1 keyword baseline, C3 matched decoys, C4 time placebo, C5 concentration
  d_leadtime.py            lead times, intervals, identifiability, mechanical verdict
  e_review_queue.py        human review batch
  run_pipeline.py          runs every stage and writes results/manifest.json (sha256 of everything)
  selftest_offline.py      26 deterministic tests; no network, no database

dataset/
  firm_lineage.json        brand-lineage attribution rules (frozen)
  frozen_vocab.json        generic vocabulary, brand tokens, applicant document frequency
  ctgov_compact.jsonl.gz   ClinicalTrials.gov, firm-anchored (schema: fetch/FETCH_SPEC.md)
  epmc_compact.jsonl.gz    Europe PMC, firm-affiliation anchored
  (*_ext_compact.jsonl.gz) the pre-registered extension stratum, kept separate on purpose

fetch/
  FETCH_SPEC.md            the frozen acquisition contract (written before any anchor existed)
  fetch_ctgov.py fetch_epmc.py fetch_ext.py
  *_FETCH_MANIFEST.json    per-query counts, hashes, limitations
  *_run.log                full stdout of the real runs

results/                   every number the docs quote (json) + pipeline.log + manifest.json
```

## Reproduce

```bash
# everything, from the committed corpora (offline, ~2 minutes)
python experiments/phoenix003/code/run_pipeline.py --db data/medradar.sqlite

# tests only (no database, no network)
python experiments/phoenix003/code/selftest_offline.py

# re-harvest the external corpora (network; politeness rules in fetch/FETCH_SPEC.md)
python experiments/phoenix003/fetch/fetch_ctgov.py
python experiments/phoenix003/fetch/fetch_epmc.py
python experiments/phoenix003/fetch/fetch_ext.py
```

The store is opened `mode=ro`; nothing in this directory writes to it.

## What is *not* here, on purpose

* No trained model, no Precision/Recall/F1: there is no supervised label set, so those numbers
  would be fabricated.
* No claim of prospective prediction. The store is a single 2026-10-30 snapshot with no
  observation clock; the study is a retrospective evidence study and is labelled as such.
* No LLM in the primary analysis. A model may propose candidates; it may not certify them.
  Only machine-checkable conditions produce `VERIFIED_L1`/`VERIFIED_L2`.
