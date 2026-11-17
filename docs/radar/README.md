# RADAR-001 — Live Intelligence & Company Technology Graph

A continuously running system that discovers new public medical-technology information,
records it with its evidence and with the two dates that matter, relates it to companies and
technologies, and renders each company's technology tree from the resulting database.

It runs against real public sources. It is not a demo, a static UI, or a one-off collection
script: the scheduler keeps checking, and a cycle with no new information is reported as
exactly that.

```
python -m medradar radar watch --interval 300          # the continuous system
python -m medradar radar status                        # sources, latency, backlog, integrity
```

Open the workbench (`python -m medradar web --radar-dir data/radar`) and the two new pages are
at **`/radar`** (Live Intelligence Feed) and **`/radar/technology-map`** (Company Technology
Map).

## What is in this directory

| Document | Contents |
| --- | --- |
| [`DESIGN.md`](DESIGN.md) | the architecture, the data contracts, the confirmation levels, the two clocks, and the reuse audit of PRs #13/#14/#28/#29/#30/#35/#50/#52 |
| [`SOURCES.md`](SOURCES.md) | every source, its verified access decision, its licence and its cadence |
| [`AI.md`](AI.md) | the local small model, its vetting gate, and its measured (poor) accuracy |
| [`ACCEPTANCE.md`](ACCEPTANCE.md) | tests A–G: what was executed, what it returned |
| [`LIMITATIONS.md`](LIMITATIONS.md) | what the system cannot do and what the live data actually supports |
| [`CHANGE_REQUEST.md`](CHANGE_REQUEST.md) | the production deployment change order (not executed) |
| [`evidence/`](evidence/) | the raw evidence: source probe, acceptance report, evaluation, UI checks |

## The three capabilities

### A. Live intelligence radar

Five sources are enabled, each with its own adapter, cadence, cursor, retry policy and health:

| Source | What it contributes |
| --- | --- |
| openFDA 510(k)/PMA | regulatory clearances by applicant and product code |
| PubMed (E-utilities) | publications, with affiliation and abstract |
| Crossref | the same literature through a second, independent API |
| Philips official news | vendor press releases with a provable publication timestamp |
| Dräger official newsroom | vendor press releases with a sitemap `lastmod` |

GE HealthCare is listed and **disabled**: its newsroom refuses anonymous automated access, and
that is shown as an access restriction rather than as "no results".

Every observation keeps four separate times — event date, source publication time, source
update time, and MedRadar's first-observation time — plus a content hash, a version, and the
full payload history.

### B. Intelligence correlation

Rules and official identifiers first: FDA product codes, curated organisation aliases, keyword
regexes. Every relation carries its method, its confidence, its evidence id and its confirmation
level. A regulatory record can make a device `TOPIC_RELATED` to a topic; only the vendor's own
statement can make a reported capability; a paper affiliation can never become a product claim.

### C. Company technology graph

A bitemporal, append-only assertion store (the in-tree `medradar.tkg`) answers:

* **what is the tree now** — topics → companies → products → evidence, each branch citable;
* **what did MedRadar know on date T** — knowledge time, which excludes everything discovered later;
* **what was publicly true on date T** — public time, explicitly labelled as a reconstruction;
* **what changed between two dates** — a diff of assertions, not of the world.

## Quick start

```bash
# 1. verify that the sources are still reachable and permitted (writes evidence)
python scripts/radar_source_probe.py --out docs/radar/evidence/source_probe.json

# 2. create the store
python -m medradar radar init

# 3. one real incremental check, then classify/link/publish
python -m medradar radar run
python -m medradar radar advance

# 4. look at it
python -m medradar radar status
python -m medradar radar feed --limit 10
python -m medradar radar map --company philips
python -m medradar radar compare

# 5. keep it running
python -m medradar radar watch --interval 300
```

Data lives in `data/radar/` (`radar.db`, `graph.db`) by default; override with
`MEDRADAR_RADAR_DIR` or `--data-dir`.

## Tests

```bash
python -m pytest tests/ -k radar -q          # 105 tests, offline
python scripts/radar_acceptance.py --data-dir data/radar --model /path/to/Qwen3-0.6B \
       --ai-python /path/to/mlvenv/bin/python
```

The unit/integration suite is offline: no network, no model, no production data.

## Non-negotiables encoded in the code

* A failed fetch never advances a cursor and never reads as "no change".
* `UNCHANGED` is a check result, never a change row.
* `first_observed_at` is immutable and enforced by a SQL trigger.
* A backfilled record must declare a reason; a historical record imported on purpose is never
  presented as today's news.
* A blocked source is a state, not an absence.
* A model proposal is a candidate until an independent rule agrees, and its quote must be
  verbatim in the source.
* No evidence found is not evidence of absence, and the product says so in every comparison.
