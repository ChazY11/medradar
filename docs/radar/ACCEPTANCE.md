# Acceptance — tests A to G

Run with:

```bash
python scripts/radar_acceptance.py \
  --data-dir data/radar --out docs/radar/evidence \
  --model /path/to/Qwen3-0.6B --ai-python /path/to/mlvenv/bin/python \
  --api-url http://127.0.0.1:8791
```

The generated report is [`evidence/acceptance_report.md`](evidence/acceptance_report.md) with
its full machine-readable twin [`evidence/acceptance_report.json`](evidence/acceptance_report.json).
Every number below was measured by that run; a test that cannot run is reported `SKIPPED` with
its reason, never `PASS`.

**Result: 7 of 7 executed tests passed**, over a live store of 8,593 observations across five
enabled sources and one blocked source.

| Test | What it proves |
| --- | --- |
| A — Live Source Discovery | a real HTTP check of a real public source produces recorded observations with official identifiers and URLs |
| B — Incremental Detection | an unchanged source publishes nothing; a changed source produces `UPDATED` with a second version and keeps the first |
| C — Cross-source Correlation | a company+topic is supported by an FDA record *and* a publication from an independent API, at `TOPIC_RELATED` |
| D — Technology Map | all three focus companies have evidence-backed branches, traceable to a citable official URL |
| E — Background AI | the local model runs in its own process and its accuracy, speed and memory are measured; discovery keeps working without it |
| F — Recovery | a mid-scope failure keeps the watermark, a restart resumes from the checkpoint, nothing is duplicated |
| G — Resource Safety | a live discovery check and the read-only API keep working while the model batch runs |

---

## A — Live Source Discovery

A real PubMed E-utilities check ran in **7.7 s over 15 HTTP requests** and the ledger now holds
**484 PubMed observations**, each with its official identifier (`PMID:…`) and official URL.

What "recorded" means here: `first_observed_at` is a real clock reading written by the ledger,
`published_at` is what the source states, and the payload version plus its content hash were
appended to `observation_version`. No synthetic record was inserted.

## B — Incremental Detection

Two halves:

1. **A real source re-check.** Re-checking `philips_official` immediately after a successful
   run produced **0 new and 0 updated** records, and the run was reported as `NO_NEW_RECORDS` —
   a result, not an error.
2. **A controlled change on an isolated fixture source**, whose bytes this system controls.
   The first load produced `NEW`; editing one title and adding a correction field produced
   `UPDATED` with a second payload version; the original version, its content hash and
   `first_observed_at` were all preserved; the change row records the changed field.

This is the mechanism that a real source update would exercise, tested where the bytes can be
changed deterministically.

## C — Cross-source Correlation

**6 (company, topic) pairs** are supported by *both* an openFDA regulatory record and a
publication from an independent literature API, out of 10,285 topic relations. Every one of
them is `TOPIC_RELATED`: no record states that a specific product implements a specific
algorithm, so nothing stronger is asserted.

A worked example resolves the pair back to its evidence rows, each with its source URL.

`OFFICIAL_IDENTIFIER_MATCH` is implemented and unit-tested, but is **empty on the current
corpus**: PubMed publishes a PMID and Crossref a DOI, so the same paper usually has no shared
identifier string. That is reported as a finding, not hidden (see `LIMITATIONS.md` §3).

## D — Technology Map

14 topic branches, **23,619 nodes / 18,184 edges**, all three focus companies present with
products and evidence rows, and a company node resolves to its official source URL.

The map is computed from the assertion store on every request; there is no static list of
company capabilities anywhere in the repository.

## E — Background AI

Qwen3-0.6B, CPU, float32, 4 threads, in its own interpreter:

| Metric | Measured |
| --- | --- |
| JSON validity | **1.0** |
| Topic precision / recall / F1 | **0.18 / 0.18 / 0.18** |
| Organisation accuracy | **0.73** |
| Evidence fidelity (accepted claims with a verbatim quote) | **1.0** |
| Throughput | **≈8.5 tokens/s**, ≈18 s per record |
| Peak RSS | **3,177 MB** |
| Model load | ≈7 s, once per batch |

**This is a negative result, reported as such**: the 0.6B model is not usable as a topic
classifier for this taxonomy. The rule layer is more accurate and fully auditable. The model is
kept as an optional candidate generator behind the verbatim-quote gate, and the product does not
depend on it.

Failure tolerance was verified in the same run: with the model unavailable, discovery and the
graph kept working and the backlog was retained rather than lost.

## F — Recovery

* A transport failure deliberately injected mid-scope left the run `FAILED`, **the watermark
  unchanged**, the page that had already succeeded durably recorded, and a checkpoint saved.
* The restart **resumed the same run** (`resumed: true`), completed the scope, advanced the
  watermark, and recorded **no duplicate** observation.
* `fleet consistency` stayed clean and no `INTERRUPTED` run was left in the history.
* Transport classification: **403 is terminal and never retried**, **429 is retried with
  `Retry-After` honoured**, **404 is not a refusal**.

## G — Resource Safety

A live discovery check was timed with no AI running and again while the model worker ran in its
own process, with a probe polling the read-only API throughout:

| Measurement | Value |
| --- | --- |
| Discovery, no AI | 0.17 s |
| Discovery, during the model batch | 0.19 s (1.1×) |
| API requests served during the batch | 3, median **29.5 ms**, max 52.1 ms |
| Worker peak RSS | measured by the worker (≈3.2 GB, see test E) |
| Host memory available during the batch | 11.5 GB (floor 900 MB) |

The worker is a one-shot low-priority process: it exits when the batch ends, so its memory goes
back to the OS. On the 2 vCPU / 4 GB production host the guard refuses the batch (the estimate
is set from the measured peak), discovery is unaffected, and the backlog is retained.

---

## What is *not* claimed here

* No three-day or seven-day continuous-run metric is claimed. The system is designed for it and
  the scheduler runs, but the natural-run observation period starts at deployment.
* No pixel screenshot is included: the browser backend could not capture one (recorded in
  [`evidence/ui_acceptance.json`](evidence/ui_acceptance.json)). Browser verification used the
  accessibility tree and DOM text instead.
* No claim that the sources are complete. Product codes, query terms and cadences are scope
  decisions; see [`LIMITATIONS.md`](LIMITATIONS.md).
