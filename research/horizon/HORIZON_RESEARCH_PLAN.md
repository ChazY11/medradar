# HORIZON-001 — Research Plan

**Task:** global medical-technology data frontier exploration and real data-asset
construction, as the data-side counterpart to ATLAS-001.
**Branch:** `research/horizon-001`
**Worktree:** `D:\DEPPSKK\worktrees\horizon-001`
**Base commit:** `b2a14c0a92332c004445de686daee97754cf94cb` (verified `origin/main` HEAD at start)
**Code root:** `research/horizon/`

---

## 1. Division of labour with ATLAS-001

| | ATLAS-001 | HORIZON-001 (this work) |
|---|---|---|
| owns | core schema, company/product identity model, unified evidence DB, four-clock temporal model, versioning, knowledge graph, migrations, integration tests | source discovery, official API/bulk acquisition, patent breakthrough, foreign regulatory DBs, product identifiers, scholarly/clinical/grant evidence, industry data, per-source quality audit, licences, versioned exports |
| files | `medradar/`, `tests/`, `docs/`, migrations | `research/horizon/` only |

**A builds structure, B finds data.** We do not change ATLAS-001's schema. Until a
stable Evidence Contract is published, we emit our own versioned format
`horizon.evidence.v1` and provide a converter. Interfaces are documented in
`ATLAS_HANDOFF.md`.

### Isolation guarantees (all verified, not asserted)

1. Separate git worktree, separate branch, from `main` HEAD — not from ATLAS-001's branch.
2. No shared working directory: `D:\DEPPSKK\worktrees\horizon-001` vs `D:\DEPPSKK\worktrees\atlas-001`.
3. Write scope is `research/horizon/**`. No edits to `medradar/`, `tests/`, `docs/`, top-level files.
4. No shared SQLite database. HORIZON uses only JSONL + its own bounded staging files.
5. PHOENIX-001/002/003 artefacts are read-only history and are not touched.
6. No direct pushes to `main`; delivery is a Draft PR only, never auto-merged.
7. No force-push; no history rewriting.
8. All commits are made by the Lead only; parallel workstreams write files, not commits.

---

## 2. Why not "more sources"

DATA-EXPANSION-001 already surveyed 59 sources and shipped 17 connectors. The
binding constraints it reported were not source count but:

* **cross-source product identity** — the same device under different names/IDs;
* **company attribution over time** — historical subsidiaries vs current parents;
* **temporal semantics** — filing vs publication vs clearance vs our fetch;
* **patents had no working acquisition asset at all.**

So this round is scored on *independent evidence obtained*, not sources touched.
Every source is assessed on six questions before it earns engineering time:

1. What does it carry that nothing we have carries?
2. Can its records be joined to a concrete company or product?
3. Does it have verifiable time fields, and are they *public-observability* times?
4. Is automated access and reuse lawful?
5. How much of its content is genuinely independent of existing sources?
6. What is the ongoing maintenance cost?

---

## 3. Priority order and rationale

| # | Workstream | Why it is at this rank | Success criterion |
|---|---|---|---|
| 1 | **Patent frontier** | The largest known hole. Highest information content per record (applicant + IPC + priority + publication date). Directly supplies the `source_public_at` clock that PHOENIX's early-signal work needs. | Real, traceable patent records with applicant/IPC/filing/publication dates, or a precise blocker + lawful unlock route |
| 2 | **Global regulatory network** | The identity spine. Official identifiers (UDI-DI, licence number) are what make cross-source identity decidable at all. Canada MDALL was already shown to be reachable. | Deepened US + CA samples, one further jurisdiction, and a measured cross-source identity experiment |
| 3 | **Scholarly / clinical / grant** | Existing coverage is broad, so the increment is not more rows but *de-duplication and verified linkage*. | Distinct-work counts after dedup, and only machine-verifiable relations |
| 4 | **Industry / trade / procurement** | Real but structurally weaker: HS codes are coarse and procurement notices rarely name a device. | Honest bounded series + explicit statement of what cannot be concluded |

---

## 4. Resource budget (enforced in code, not by intention)

All HTTP goes through `hz.http.BoundedClient`, which refuses to exceed its own
budget and writes a request log for every attempt.

| Workstream | request cap | byte cap | notes |
|---|---|---|---|
| patents (EPO) | 300 | 95 MB | ~10 weekly sitemaps + ≤235 front pages |
| regulatory | ~150 | ~80 MB | per-source caps, no pagination loops |
| scholarly | ~250 | ~60 MB | page sizes ≤ 50 |
| industry | ~200 | ~60 MB | bulk files preferred over API pagination |

Machine: Windows 11, Core Ultra 9 285H, 32 GB RAM, RTX 5080 Laptop.
**No model training this round.** Pure data engineering: Python 3.12, SQLite/JSONL,
`requests`, `lxml`, `pandas`. No GPU use. No proxy. No paid API. No purchased data.
No credential use, no account registration.

---

## 5. Evidence discipline

Four levels, tracked separately per source and never promoted into one another:

* **ACCESS SUCCESS** — the endpoint answered, proven by `PROBES.json` (status, bytes, sha256).
* **DATA SUCCESS** — the body has stable structure and the needed fields, proven by a saved raw sample plus a parser that reproduces records.
* **IDENTITY SUCCESS** — evidence pins a specific company/device, proven by an identifier issued by the source, not by a name match.
* **RESEARCH SUCCESS** — the new information is a measurable increment, proven by an experiment against a recorded baseline.

### The four clocks

| field | meaning | example |
|---|---|---|
| `event_at` | when the described event occurred | patent filing date (INID 22) |
| `source_public_at` | when a human could first have seen the record | patent publication date (INID 43/45) |
| `first_observed_at` | when HORIZON first saw it | this round |
| `fetched_at` | this retrieval | this round |

`hz.timeq.audit_clocks()` refuses records without `source_public_at` for any
historical-observability claim, and rejects records where the publication date
precedes the event date. Using `event_at` as `source_public_at` is the single
error that manufactures retrospective foresight, so it is checked in code.

A concrete instance of why this matters, from the patent work below: a granted EP
patent's front page carries **both** the application publication date (INID 43)
and the grant publication date (INID 45). EP2490731B1 has 43 = 2012-08-29 and
45 = 2024-06-05. Choosing 43 for a 2024 grant would place a document roughly
**twelve years** before it was observable.

---

## 6. Deliverables

```
research/horizon/
  HORIZON_RESEARCH_PLAN.md        this file
  WORKSTREAM_BRIEF.md             shared rules for all data workstreams
  GLOBAL_SOURCE_DEEP_AUDIT.md     per-source deep audit
  PATENT_ACCESS_REPORT.md         patent channels, successes, blockers, unlock routes
  REGULATORY_FRONTIER_REPORT.md   cross-jurisdiction registration data
  INDUSTRY_DATA_REPORT.md         trade + procurement
  EXPERIMENT_RESULTS.md           EXP-H1/H2/H3 measured results
  DATA_QUALITY_AUDIT.md           duplication, mis-attribution, time semantics, licences
  ATLAS_HANDOFF.md                schema, fields, samples, compatibility, limits
  EXECUTIVE_SUMMARY_ZH.md         中文总结
  hz/                             the shared engineering core
  SOURCE_PROBES/<suite>/          PROBES.json + REQUEST_LOG.jsonl
  CONNECTORS/                     per-source adapters
  DATASETS/                       bounded raw samples + PROVENANCE.json
  registry/sources/               one JSON per source: access, licence, blockers
  experiments/                    experiment inputs and measurements
  exports/<id>/                   versioned JSONL + MANIFEST.json for ATLAS-001
```

Nothing here is a placeholder: each file corresponds to code that ran, data that
was saved, or a probe that was executed and logged.

---

## 7. Reproduction

```powershell
cd D:\DEPPSKK\worktrees\horizon-001\research\horizon
python -m hz.cli sources                 # source register
python -m hz.cli probe --suite patents   # access evidence for patent channels
python -m hz.cli verify                  # offline integrity self-check
python CONNECTORS\patents\run_collect.py # bounded patent sample
```

Every collector is deterministic given its recorded inputs except for the live
HTTP responses, which are content-hashed in `PROVENANCE.json` so a third party
can tell whether a re-run saw the same bytes.
