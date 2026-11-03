# MedRadar

**An evidence-first research project studying whether publicly observable evidence carries reliable
early signals of meaningful change in medical technology development.**

MedRadar collects free public regulatory, clinical-trial and corporate-filing evidence about
medical-device and drug makers into one auditable event store, and uses it to answer one question —
carefully, and so far with negative results. It is a research instrument, not a product: it does not
predict the future of the medical-technology industry, and nothing here is investment advice.

> 中文简介 → [README.zh-CN.md](README.zh-CN.md) · Current status, research index and roadmap →
> [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) · Data assets →
> [docs/DATA_ASSET_REGISTER.md](docs/DATA_ASSET_REGISTER.md) · Repository audit →
> [docs/REPOSITORY_AUDIT.md](docs/REPOSITORY_AUDIT.md)

## Research Mission

**Core question:**

> Can publicly observable evidence provide reliable early signals of meaningful changes in medical
> technology development?
>
> 公开可观察的信息，能否为医疗技术发展的重要变化提供可靠、可重复验证的早期信号？

Everything in this repository serves that question in one of three ways: **observing** technology
activity in public evidence, **understanding** what changed with traceable evidence, or **testing**
whether the observed change could have been seen earlier. Work that serves none of the three is not
in scope. See [research/MISSION.md](research/MISSION.md) and [research/DATA_PROVENANCE.md](research/DATA_PROVENANCE.md).

The programme is deliberately disciplined about what counts as evidence: protocols are frozen before
experiments, a zero result is reported as a result, and every numeric claim in the papers is mapped to
a machine-checkable claim file.

## What MedRadar Does

These capabilities exist on `main` today and are exercised by the offline test suite.

| Capability | What it actually does |
|---|---|
| Public-source collection | Ingests openFDA 510(k) / PMA / recalls / classification / drugsfda, ClinicalTrials.gov API v2 and (optional) SEC EDGAR 8-K into one SQLite event store. Every HTTP response is cached and every stage is resumable. |
| Point-in-time event model | Each event carries event time, publication time, first-seen time, availability time and a `timestamp_quality` tier. Records whose public time is only estimated or unknown are descriptive only and are excluded from inference. |
| Company and track metrics | Gamma–Poisson shrinkage, track heat index, product-code mix shift (Jensen–Shannon divergence), first-occurrence novelty, block bootstrap + Holm correction. |
| Report and dashboard | A 19-chapter Chinese report plus a self-contained HTML dashboard and replay timeline — zero CDN, zero external requests, works offline and on GitHub Pages. |
| Case library and event study | Traceable cases with verbatim evidence and 1/5/20/60-day abnormal returns; a paper (simulated) portfolio with explicit frictions and cost tiers. |
| Research infrastructure | A bitemporal knowledge store (`medradar/tkg`, valid time vs knowledge time, deterministic point-in-time export) and an append-only forecast registry with as-of scoring. |
| Evidence-grounded agent demo | A deterministic 8-tool workflow that cites stored evidence IDs; it narrates stored evidence and does not establish causality. |
| Offline test suite | 1,074 unittest checks across 47 modules (~25 s, no network, no API key) plus CLI smoke tests in CI. |

The point of the registry and the bitemporal store is not sophistication: it is that a forecast, once
made, cannot be edited afterwards, and that an as-of query cannot return a fact we could not have
known at that time.

## Current Research Status

Four buckets, each corresponding to a different kind of claim. **Read the bucket before the number.**

### Implemented (in `main`, tested)

Collection, point-in-time event storage, metrics, reports/dashboards, case library, replay, event
study and the paper-trading simulation, statistical utilities, bitemporal store, forecast registry,
research agent demo, offline test suite, CI.

### Experimental (in `main`, explicitly unreliable)

| Item | Status |
|---|---|
| FDA Advisory Committee calendar (`medradar/adcom.py`) | Parses **zero** meetings: the calendar rows are rendered client-side. The command returns `status="empty"`/`"source_changed"` with a warning instead of a silent "ok". The frontier feed therefore contains no AdCom signal. |
| NMPA (China) adapter | Deliberately not scraped (HTTP 412 / JavaScript WAF). You must drop a CSV export in place; without it every CN value is `null` and the report says so. It never fabricates a zero. |
| LLM filing judge (`medradar/llm.py`) | Optional, needs an API key; falls back to a deterministic keyword judge and labels the fallback. The published calibration is a 25-item single-annotator pilot, **not** an accuracy guarantee. |
| Frontier feed (`medradar/frontier.py`) | Public-source monitoring of first-posted trials and 8-K designations. Not a pending-application oracle; non-public review status is not observable. |

### Under validation (draft PRs — **not** in `main`)

| Work | State |
|---|---|
| Live Observatory v1 — append-only Observation Ledger ([PR #13](https://github.com/ChazY11/medradar/pull/13)) | Ledger exists and runs locally; 400 observations recorded from a single discovery sweep. Not merged. |
| Observatory Reliability — durable persistence, verified backups, seven-day validation ([PR #14](https://github.com/ChazY11/medradar/pull/14)) | `VALIDATION_IN_PROGRESS` (1 of 28 planned 6-hour slots at the time of writing; window ends 2026-11-10). Deployment is `DEPLOYED_LOCAL`; production is **`NOT_DEPLOYED`**. |
| MedRadar 2.0 product surface ([PR #12](https://github.com/ChazY11/medradar/pull/12)) | Draft. Its CI is red (its new pytest-style modules are imported by the offline `selftest` job which does not install pytest). |

### Not demonstrated (claiming otherwise would be wrong)

- No **predictive skill** for medical-technology change has been demonstrated. The programme results
  index says so in its second sentence: *"The system, as of v0.5.0, has not demonstrated predictive
  skill for corporate technological entry."* ([research/RESULTS/README.md](research/RESULTS/README.md))
- No **lead time**: the pre-registered lead-time gate returned NO-GO (3 eligible pairs against a floor
  of 10).
- No **calibrated forecasts**: 25 prospective forecasts are registered and **none has matured**
  (earliest windows close 2027-10).
- No **point-in-time relation network**: the relation layer is reconstructable but not
  point-in-time and not human-validated.
- No **production deployment** of any continuous-observation service.

## Data Sources

All sources are free and need no credentials. Freshness is measured, not assumed.

| Source | Content | Known freshness / limitation |
|---|---|---|
| openFDA `device/510k`, `device/pma`, `device/recall` | 510(k) clearances, PMA & supplements, device recalls | openFDA bulk lags roughly 2–12 days |
| openFDA `device/classification` | Product codes → regulated definitions | static reference data |
| openFDA `drug/drugsfda` | NDA/BLA/ANDA approvals and review | lags a few days |
| ClinicalTrials.gov API v2 | Trial registrations (drug and device) | a trial is typically posted after enrolment starts |
| SEC EDGAR full-text search | 8-K filing stream used for catalysts and designations | near real time; optional, needs a declared User-Agent |
| FDA Advisory Committee calendar | Meeting schedules and briefing materials | **currently unparseable** (client-side rendering) — see above |

Not used, with reasons: NMPA/CMDE (blocked by a JavaScript WAF), USPTO patents (Open Data Portal
requires a key; adapter only, **no patents collected**), hiring data (not implemented). Procurement
awards exist in the research lane but are **not point-in-time usable** and are therefore excluded
from any predictive claim.

## Research Findings

The scientific record is mostly **negative**, and is reported as such. Every study below keeps its
raw evidence and its pre-registration; corrections are appended, never silently rewritten.

### Five-firm early-signal study — completed, negative (`main`)

`research/studies/early_signal_5firms/` · synthesis: [papers/PAPER_NEGATIVE_v1.md](papers/PAPER_NEGATIVE_v1.md)

A pre-registered study across five medical-device firms asking whether an earlier public source
predicts a later regulatory event often enough to measure lead time, and whether fusing a second
stream improves detection at a fixed false-alarm budget. It returned a negative result in three
independent steps: the earlier sources cannot be joined to the technology tracks (3 eligible pairs
against a floor of 10); the positive class is effectively absent (one qualifying quarter across
sixteen firm-track cells, zero at a stricter silence requirement); and with zero onset quarters in the
primary window the fusion comparison is uninterpretable rather than supportive.

> "At the granularity the data support — firm × track × quarter — the phenomenon this study set out
> to detect does not occur often enough to be measured. **The binding constraint is information, not
> modelling.**"

**Open item:** 69 candidate packets are still `PENDING_HUMAN_REVIEW`. An agent pre-adjudication
exists but is explicitly **not** human truth and may not be used as ground truth or to score the
study's own detectors; it produced 0 confirmed shifts (45 uncertain / 18 routine / 6 not assessable).

### S-028 — graph early signals, exploratory negative + Correction 1 (draft [PR #15](https://github.com/ChazY11/medradar/pull/15), **not merged**)

`research/studies/graph_early_signal_s028/` (branch `research/s028-temporal-graph-early-signal`)

Asked whether company–technology relational structure adds information about a firm's first observable
regulatory activity in a track, controlling for its own history, the track's history and time. Frozen,
pre-registered baselines gave ΔAP = **−0.00609** (company-clustered CI [−0.02219, +0.00450], pair CI
[−0.03347, +0.01043], 0 of 3 windows excluding zero): **no improvement detected**.

`S-028-CORRECTION-1` then invalidated part of the original report — the "well-powered null" label, the
randomisation design's invariance claim, and several literature claims are marked `INVALIDATED`. The
study may be **sealed as a credible exploratory negative result, not as a confirmatory one**; the
correction lists what a confirmatory version would still need. Do not cite S-028 as evidence that
network structure *is* or *is not* informative in general — only that no improvement was detected here.

### S-029 — evidence-based relations, NO-GO for prediction (draft [PR #16](https://github.com/ChazY11/medradar/pull/16), **not merged**)

`research/studies/relation_network_s029/` (branch `research/s029-evidence-based-relations`)

Asked whether time-resolved relationships among companies, institutions, trials and publications can
be reconstructed from verifiable public evidence before any model is fitted. It can be reconstructed:
20,563 claims, 3,418 evidence rows, 130 raw payloads with per-call hash records. It is **not** usable
for prediction, and the pre-registered decision says so in the only vocabulary the protocol allows:

> **`NO-GO FOR PREDICTION`** — "the relations are reconstructable and individually traceable, but they
> are not point-in-time evidence and they are not human-validated."

Failed gates: strict point-in-time availability (0 claims) and human validation (0 of 102 worksheet
rows labelled → `HUMAN_VALIDATION_PENDING`). No precision, recall, F1 or human–machine agreement may
be quoted from S-029.

### Market-to-R&D / horizon forecasting — completed, negative on added sources (`main`)

`docs/REVERSE_RD.md`, `docs/PHASE1.md`, `docs/PHASE2.md`, `docs/PHASE3.md`, `experiments/reverse_rd_v2/`

Predicting future public R&D/regulatory milestones from company, market and publication features.
Ablation across seven source specifications found **no added source produces a statistically
detectable ranking gain**; the continuation target is mostly persistence (per-pair base-rate baseline
AP 0.7913 vs model 0.7935, Δ +0.0022, 95% CI [−0.032, +0.037]). This lane also produced the
append-only forecast registry: 25 prospective forecasts registered, **none matured**, so calibration
is reported as `insufficient_matured_forecasts` rather than claimed.

## Architecture

```
public sources                collection                 storage                      analysis
──────────────                ──────────                 ───────                      ────────
openFDA 510(k)/PMA/recall ─┐
openFDA drugsfda          ─┼─► collectors ───────────►  SQLite event store  ──►  metrics & statistics
ClinicalTrials.gov v2     ─┤   rate-limited,             one `events` table      (shrinkage, mix shift,
SEC EDGAR 8-K (optional)  ─┘   cached, resumable          point-in-time fields     bootstrap, Holm)
FDA AdCom calendar ───────┘   (one shared Fetcher)        + registries/prices            │
                                                                                           ▼
   research infrastructure (same store, read-only)                              report · dashboard ·
   ├── bitemporal TKG  (valid time vs knowledge time)                            case library · replay ·
   ├── forecast registry (append-only, as-of scoring)                            event study · audit
   └── research agent (cites stored evidence IDs)
```

Draft-branch work adds a second, service-shaped layer — an append-only Observation Ledger with
scheduled collection, verified backups and a health/validation state machine (PR #13/#14). It is
**not** part of `main` and is not deployed in production.

Engineering principles that constrain the design: no runtime dependencies (Python standard library
only), no paid services, no hidden network calls in tests, and no number in the report that cannot be
re-derived from the store.

## Getting Started

Verified on Windows 11 with Python 3.12.10 during the 2026-11 maintenance pass. Nothing below needs an
API key.

```bash
git clone https://github.com/ChazY11/medradar.git
cd medradar
python -m venv .venv && . .venv/Scripts/activate     # Windows; use .venv/bin/activate on Unix
pip install -e .                                     # no third-party runtime dependencies

python -m medradar demo        # offline demo: ~0.4 s, writes out/demo/, open out/demo/index.html
python -m medradar selftest    # offline suite: 1,074 checks, 3 skipped, ~25 s
python -m medradar doctor --offline   # environment self-check, no network. Note: doctor creates an
                                      # empty data/medradar.sqlite on first use, which makes three
                                      # local-store artifact tests error instead of skip — so run
                                      # selftest first, or delete that empty file before re-running it.
```

The demo renders the committed snapshot (`docs/metrics.json`); it does not touch the network or a
database. `pip install -e .` needs `setuptools>=68`; on a fresh Python 3.12 virtualenv pip fetches it
for build isolation. For a fully offline install: `pip install setuptools` first, then
`pip install -e . --no-build-isolation`.

**Live collection (not re-verified in the 2026-11 maintenance pass — requires network access and takes
minutes):**

```bash
python -m medradar run --months 24 --with-trade --with-dashboard
# collect -> analyze -> report -> optional paper-trading study and dashboard
python -m medradar collect --sources device,drug,trials --months 120
python -m medradar status
```

Other useful entry points: `medradar cases`, `medradar products`, `medradar replay`,
`medradar stats`, `medradar audit`, `medradar frontier`, `medradar dashboard`. Run
`medradar --help` for the full list (20 subcommands).

## Repository Structure

| Path | What is there | Read it if you want… |
|---|---|---|
| `medradar/` | The Python package: collectors, event store, metrics, report/dashboard, replay, paper trading, statistics, bitemporal store, forecast registry, research agent | to run or extend the instrument |
| `config/` | Hand-curated knowledge: company aliases, track dictionaries, product families, entity universe | to see what the instrument knows |
| `research/` | The research programme: charter, hypotheses, provenance rules, decision log, results index, and `research/studies/` | the science: questions, decisions, results |
| `papers/` | Three draft papers (empirical, methods, negative result) plus machine-checked claim maps | the written record; **drafts, not submitted** |
| `experiments/` | Frozen experiment scripts and outputs (`b0xx/`, `reverse_rd_v1/`, `reverse_rd_v2/`, `detect_v1/`, `cycle2_coverage/`) | to reproduce or audit a specific experiment |
| `docs/` | Methodology, schema contract, data notes, assumptions, calibration, and the GitHub Pages site | the definitions behind every number |
| `tests/` | Offline test suite with synthetic fixtures | to verify a change |
| `scripts/`, `tools/`, `verifier/` | Operational scripts, governance/audit scripts, acceptance-run records | to operate or audit the pipeline |
| `docs/PROJECT_STATUS.md` | The single status overview: capabilities, research index, PR state, roadmap | **start here after the README** |
| `docs/DATA_ASSET_REGISTER.md` | Every database and data asset, with provenance, size and retention rule | to know which data file is authoritative |
| `docs/REPOSITORY_AUDIT.md` | Structure map, redundancy findings, cleanup record, open human decisions | to understand the repository's state |

`data/`, `out/` and `logs/` are runtime directories and are **not** in git.

## Reproducibility

Two different things are called "reproducible" here, and the repository tries to keep them apart.

**Reproducible from a fresh clone.** The offline test suite, the demo, the metrics schema checks, the
claim-map verification (`papers/verify_claims.py`), the frozen-benchmark drift guard
(`experiments/detect_v1/check_frozen_reproduction.py`), and the S-029 evidence chain on its branch
(claims → evidence → per-call request log → committed raw payload hashes). These need no database.

**Reproducible only with the uncommitted local data (workstation-level).** The studies themselves:
`data/medradar.sqlite` (1.37 GB operational store) and the 289 MB frozen research store
(SHA-256 `dd241bfe…`) are **not in git**, so a third party cannot re-derive study counts from a clone.
`research/studies/early_signal_5firms/REPRODUCIBILITY.md` states this plainly; S-028's scripts
additionally contain absolute local paths, and S-029's clock audit reads the local Observation Ledger.
Each frozen artifact records the hash of its input; each study carries a reproducibility document
(`REPRODUCIBILITY.md` on `main`, `REPRODUCE.md` on the S-028/S-029 branches). This gap is
tracked in [docs/DATA_ASSET_REGISTER.md](docs/DATA_ASSET_REGISTER.md) §Regeneration honesty and is the
main reproducibility debt in the project.

## Limitations

- **No demonstrated prediction.** No study shows reliable early signals of technology change. Two
  independent lines (lead-time/fusion; graph structure) returned negative results, and the relation
  network was declared NO-GO for prediction.
- **Underpowered by information, not by modelling.** The event rate in firm × track × quarter is too
  low to measure the phenomenon at the agreed floors.
- **Human validation is incomplete.** 69 packets (five-firm study) and 102 rows (S-029) are unlabelled;
  agent pre-adjudication cannot substitute for human judgement.
- **Point-in-time honesty is limited.** Only some sources expose genuine publication times; several
  lanes rely on a declared lag assumption and are marked `estimated`.
- **Not everything is merged.** S-028, S-029, the Live Observatory and the 2.0 product surface live on
  draft branches. `main` does not contain them.
- **No production deployment, no offsite backup, no cost budget.** The observatory runs on one local
  machine with local backups only; paid infrastructure has not been purchased.
- **The snapshot numbers are stale by construction.** Report figures come from a 2026-10-31 collection
  and move when the pipeline is re-run.

## Roadmap

One research question, three priorities. The single current roadmap lives in
[docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) §Roadmap; this is the summary.

**Priority 1 — Project clarity (this consolidation).** Make repository state, research status and data
assets explicit; keep `main` truthful; stop new capability branches from growing while status is
unclear.

**Priority 2 — Observatory reliability.** Keep the append-only observation record and its backup chain
sustainable and auditable, without new infrastructure. The current seven-day validation must be
allowed to finish and be reported as it actually ended — the result is not to be retrofitted.

**Priority 3 — Core research validation.** Return to the core question with a small, traceable case
study design rather than another large research engineering build.

**Next minimal action:** complete the **69-packet human adjudication** of the five-firm study
(worksheet and validator already exist), because no detector can be scored and no lead-time claim made
until the labels are human. Nothing else should start before that.

Explicit non-goals while the question remains open: no new study number, no new model family, no
knowledge-graph expansion, no new data sources, no production service.

## License and Data Provenance

**Code:** MIT — see [LICENSE](LICENSE). (GitHub's licence detector reports "Other" because the LICENSE
file appends a data notice after the MIT text; the MIT grant is the licence, and `pyproject.toml`
declares `MIT`.)

**Data:** belongs to its publishers. openFDA endpoints are US-government public domain;
ClinicalTrials.gov, SEC EDGAR, Europe PMC and Crossref each carry their own terms and fair-access
requirements; market price bars are vendor-derived research imports and must not be redistributed.
MedRadar does **not** redistribute bulk source data, and the runtime stores (`data/`) are not in git.
Derived aggregates, configuration and reproduction commands are committed. One draft research branch
(S-029) commits per-query raw API payloads for evidence traceability — a known governance item recorded
in [docs/DATA_ASSET_REGISTER.md](docs/DATA_ASSET_REGISTER.md) §Redistribution risk.

**Attribution:** authorship by increment, including the agent teams and models used, is recorded in
[docs/ATTRIBUTION.md](docs/ATTRIBUTION.md).

**Nothing here is investment advice.** The portfolio is a simulation and is labelled as such on every
page it produces.
