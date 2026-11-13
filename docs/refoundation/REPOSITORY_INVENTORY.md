# REPOSITORY_INVENTORY — MedRadar asset map at `main` `b2a14c0`

> **Audit:** REFOUNDATION-001 · **Owner:** `inventory-auditor` · **Date:** 2026-11-12 (Asia/Shanghai)
> **Worktree audited:** `<REDACTED_LOCAL_PATH> (branch `audit/refoundation-001` = `main` `b2a14c0`)
> **Companion:** [`BRANCH_PR_AUDIT.md`](BRANCH_PR_AUDIT.md) · **Ground truth:** [`_FACTS.md`](_FACTS.md), [`_evidence/repo_facts.json`](_evidence/repo_facts.json)
> **Machine-readable evidence:** [`_evidence/inventory/inventory_facts.json`](_evidence/inventory/inventory_facts.json), [`_evidence/inventory/ancestry_verify.json`](_evidence/inventory/ancestry_verify.json)

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** The full asset map of `origin/main` (`b2a14c0`, 1,135 files): `medradar/`, `config/`, `experiments/`, `research/`, `papers/`, `verifier/`, `tools/`, `scripts/`, `tests/`, `docs/`, `.github/`, plus every branch-only module family that the open PRs introduce. PR/branch accounting is the companion document; this document answers *what exists, where, in what state, and what to do with it*.

**Method.**

1. Read [`_FACTS.md`](_FACTS.md) §0 audit doctrine and §6–§8 asset footprint first; treated it as ground truth to be **re-derived**, not trusted.
2. Enumerated every blob with `git ls-tree -r -l origin/main`, aggregated by top-level and by directory, then read module docstrings and headers **from git objects** (`git show origin/main:<path>`) — never from the working tree or README.
3. For branch-only families: `git diff --name-status origin/main...origin/<head>` plus `git merge-base --is-ancestor` (see §14), so a family is attributed to the branch that actually contains it.
4. Re-measured the test baseline first-hand: `python -B -m pytest -p no:cacheprovider -q` on `b2a14c0` exits **0**; `--collect-only -q` reports **1,074** tests across 47 modules (no cache or byte-code written into the worktree).
5. Every non-obvious number was produced by a committed script under [`_evidence/inventory/`](_evidence/inventory/) and is reproducible (§16).

**Labels.** Every claim below carries one of **[FACT]**, **[INFERENCE]**, **[RECOMMENDATION]**, **[UNVERIFIED]** (doctrine in `_FACTS.md:12-31`). A row without a label is FACT-by-measurement and cites its locator.

**Evidence base.**

| Evidence | What it proves |
|---|---|
| `git ls-tree -r -l origin/main` | 1,135 files / 30,474,497 B; per-path sizes used in every table |
| `git show origin/main:<path>` | docstrings, line counts, CLI parser names, state files |
| `git diff --name-status origin/main...origin/<branch>` | branch-only inventory and copy-paste volume |
| `git merge-base --is-ancestor A B` | hidden stack membership (§14.3) — **not** diff similarity |
| `python -m pytest` / `--collect-only -q` on `b2a14c0` | test baseline 1,074 / exit 0 |
| `_evidence/repo_facts.json` | PR ledger, branch divergence, Pages, worktrees |

**Limits (explicit).**

1. **No network.** PR `mergeStateStatus`, review state, labels and issue links come from `repo_facts.json` as collected 2026-11-12; I did not re-query GitHub. Where I state `CONFLICTING` for PR #1 I additionally proved it locally with `git merge-tree` (§16).
2. **No execution of branch code.** Branch-only families were inventoried statically. Their tests were *not* run — only their existence/count is reported. Any "works" claim about a branch is [UNVERIFIED].
3. **No data download.** Data-rights cells report *what committed files declare* (e.g. `config/sources.json`, `research/data_expansion/LICENCE_AND_COST_AUDIT.md`) and defer the authoritative judgement to `DATA_GOVERNANCE_AUDIT`.
4. **Line counts** are newline counts from `git show` and can differ ±1 at EOF from tool-based counts.
5. **A branch's tree is not merged content.** Every "NOT ON MAIN" statement was checked with `git merge-base --is-ancestor`; a clean 3-way merge is reported separately and never equated with "safe to merge".
6. **`research/` state files disagree** (§6.1); I report all competing sources rather than picking a winner.

---

## 1. Headline numbers

| Metric | Value | Label |
|---|---|---|
| `main` HEAD | `b2a14c0a92332c004445de686daee97754cf94cb` (PR #11 merge, 2026-11-02) | FACT `_FACTS.md:61-63` |
| Files / bytes on `main` | **1,135** / **30,474,497 B (29.06 MiB)** | FACT, `inventory_facts.json` |
| Python on `main` | 87 pkg modules + 47 test modules + 12 scripts + 10 tools + 1 verifier + 17 paper scripts = **41,881 LOC** in `medradar/` alone | FACT (`metrics.py`) |
| Package version | `0.5.0` (`pyproject.toml:3`, `medradar/__init__.py:21`) vs README "v0.2.2/v0.3.0" | FACT; contradiction C1 `_FACTS.md:249` |
| CLI subcommands | **20** (`medradar/__main__.py`, `add_parser` count) | FACT §3.3 |
| Offline test baseline | **1,074 collected, run exit 0** on `b2a14c0` | FACT (measured; §11) |
| Commits reachable on `main` | 154 ahead of the oldest open branch; 140–154 commits of work landed 2026-11-01→11-02 | FACT (`_FACTS.md:154-183`) |
| Open PRs / drafts | 20 / 19, adding **2,824,212** lines vs 541,569 merged | FACT `_FACTS.md:68-73` |
| Non-main remote branches | **33** (34 non-HEAD remote refs incl. `main`); **49** local heads | FACT (`ancestry_extra.py`, `repo_facts.json`) |
| Published state | GitHub Pages builds `main:/docs` at `b2a14c0` only | FACT `_FACTS.md:239` |

**The single most important inventory fact.** Everything that a reader would call "MedRadar 2.0" — product/company/radar/analyst UI, live observatory, reliability/backup layer, PHOENIX/ATLAS/HORIZON/CONVERGENCE research programmes, S-028/S-029/S-031 studies, local-LLM/QLoRA lane, data-expansion lane — **is absent from `main`**. `main` is a complete, passing, *v0.5.0-era* FDA/device intelligence pipeline plus one merged early-signal study; the other 2.8 M lines live only on branches (§14). [FACT]

---

## 2. Per-top-level footprint of `main`

| Top-level | Files | Bytes | MiB | Share | What it is |
|---|---:|---:|---:|---:|---|
| `experiments/` | 657 | 15,778,771 | 15.05 | 51.8 % | 34 experiment directories: 29 `b0xx` cycle dirs + `detect_v1`, `detect_v1_verify`, `cycle2_coverage`, `reverse_rd_v1/v2` |
| `docs/` | 60 | 6,704,394 | 6.39 | 22.0 % | 36 Markdown contracts + 4 generated HTML + 5 PNG + `metrics.json` + `summary.csv` |
| `config/` | 10 | 2,283,315 | 2.18 | 7.5 % | curated JSON/CSV knowledge (universe, product catalog, tracks, sources) |
| `medradar/` | 87 | 1,853,319 | 1.77 | 6.1 % | the shipped stdlib-only Python package |
| `research/` | 116 | 1,396,890 | 1.33 | 4.6 % | programme state + 46 `RESULTS/` reports + 50-file early-signal study |
| `tests/` | 105 | 1,315,504 | 1.25 | 4.3 % | 47 test modules + 57 fixtures |
| `papers/` | 32 | 534,818 | 0.51 | 1.8 % | 3 drafts + 3 machine-verified claim maps + figures + 2 selftest logs |
| `scripts/` | 13 | 401,951 | 0.38 | 1.3 % | 12 operator/generator scripts + `nightly.ps1` |
| `tools/` | 15 | 63,663 | 0.06 | 0.2 % | round-end audit / state-update plumbing |
| `verifier/` | 22 | 34,482 | 0.03 | 0.1 % | `verifier/v1` acceptance verifier + 19 committed run artifacts |
| `.github/` | 8 | 15,046 | 0.01 | 0.05 % | 4 workflows, 3 issue templates, PR template |
| root `*.md`/config | 10 | 93,400 | 0.09 | 0.3 % | README ×2, CHANGELOG, ROADMAP, CONTRIBUTING, pyproject, LICENSE, MANIFEST, ignore attrs |
| **Total** | **1,135** | **30,474,497** | **29.06** | 100 % | |

### 2.1 Root files

| Path | Bytes | Lines | Role | Label |
|---|---:|---:|---|---|
| `README.md` | 31,738 | — | long English brief; mixes product, research, results; not a reliable description | FACT; C3 `_FACTS.md:251` |
| `README.zh-CN.md` | 26,132 | — | Chinese mirror | FACT |
| `CHANGELOG.md` | 23,524 | — | Keep-a-Changelog style; latest section `[0.5.0] — 2026-11-02` | FACT |
| `ROADMAP.md` | 5,225 | 94 | "shipped in v0.3.0" list; **stale** (`v0.3.0` dated 2026-10-31) | FACT |
| `CONTRIBUTING.md` | 1,932 | 47 | contribution rules; cites issue tracking that is unused (0 issues) | FACT |
| `pyproject.toml` | 1,490 | — | setuptools build, `version = "0.5.0"`, zero hard deps, 4 optional extras, console script, data-files | FACT |
| `LICENSE` | 1,328 | 21 | MIT, "Copyright (c) 2026 MedRadar contributors" — GitHub metadata says "Other" (C2) | FACT |
| `MANIFEST.in`, `.gitignore`, `.gitattributes` | 975 | — | packaging/ignore hygiene | FACT |

---

### 2.2 Largest blobs on `main` (history and clone cost)

| Path | Bytes | Why it is large | Rec. |
|---|---:|---|---|
| `docs/dashboard.html` | 3,350,819 | generated single-file dashboard + inlined data | archive out of git |
| `docs/replay.html` | 1,014,957 | generated replay page | archive out of git |
| `docs/preview.png` | 488,736 | README hero | keep (compress) |
| `docs/metrics.json` | 468,561 | committed metrics snapshot | integrate as release asset |
| `config/universe_v1.json` | 1,711,167 | 9,412-entity universe | keep (dedupe on regen) |
| `config/product_catalog_zh.json` | 303,361 | generated catalogue | integrate |
| `config/product_families.json` | 167,635 | generated families | integrate |
| `docs/dashboard_cases.png` / `_replay.png` / `_preview.png` / `_overview.png` / `_mobile.png` | 171,942 / 131,416 / 89,219 / 75,312 / 54,624 | generated screenshots | archive |
| `papers/selftest_cycle17.log` / `cycle18.log` | 131,800 each | pytest tails | archive |
| `research/DECISIONS.md` | 185,056 | 74-decision ADR log | keep |
| `experiments/b027/snapshots/*` (336 files) | 3,390,498 | frozen quarterly snapshots | archive |

[INFERENCE] ~5.7 MB (19 %) of `main` is regenerable HTML/PNG/JSON; removing it from git would cut clone size materially without losing capability. [RECOMMENDATION] publish generated assets to Pages from CI, not from `main`.

### 2.3 `medradar/` package distribution (87 modules, 41,881 LOC)

| Sub-area | Modules | LOC | Share of pkg LOC |
|---|---:|---:|---:|
| top-level pipeline (collect→analyze→report→trade→replay) | 28 | ~25,900 | 62 % |
| `intelligence/` (sources, features, models, evaluation, forecasting) | 30 | ~10,300 | 25 % |
| `tkg/` (bitemporal store) | 7 | 1,486 | 3.5 % |
| `studies/` (S-026 pure logic) | 9 | 1,305 | 3.1 % |
| `dashboard.py` / `report.py` alone | 2 | 5,888 | 14 % (of total) |

[FACT] `report.py` (4,520 L) + `replay.py` (3,088 L) + `research_agent.py` (1,900 L) + `families.py` (1,439 L) = 10,947 L, **26 % of the package in four modules**. [RECOMMENDATION] these four are the refactor frontier: `report.py` and `dashboard.py` duplicate rendering concerns; `replay.py` is a 3k-line analysis monolith.

## 3. `medradar/` — the shipped Python package

**Shape.** 87 modules, 1,853,319 B, 41,881 LOC, **standard-library only** at runtime (`medradar/__init__.py:6-17`; `pyproject.toml` has `dependencies = []`). Optional extras only: `openpyxl` (excel), `pypdf` (pdf), `ijson` (bulk), `pytest` (dev). The only external service calls are `urllib`-based public APIs plus an **opt-in** LLM judge (`MEDRADAR_LLM_API_KEY`, `MEDRADAR_LLM_BASE_URL` default `https://api.deepseek.com`, `MEDRADAR_LLM_MODEL`).

**Column legend.** *Impl.* = implementation status on `main`; *Rec.* = keep / integrate / refactor / archive / pending.

### 3.1 Foundation and CLI

| Module | Location | Purpose | Branch/PR | Dependencies | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| Package metadata | `medradar/__init__.py` (21 L) | package docstring + `__version__ = "0.5.0"` | main | none | shipped | `test_release` | n/a | repo MIT | keep |
| CLI entry | `medradar/__main__.py` (972 L) | 20 subcommands; `collect→analyze→report→trade`, resumable stages (`:1-9`) | main | argparse, all modules | shipped, used weekly | `test_release`, `test_check_layout` | operational | MIT | **refactor** (972-L god-CLI; split per subcommand) |
| Config/registries | `medradar/config.py` (337 L) | project paths, JSON config, fuzzy `CompanyRegistry`/`TrackRegistry` | main | stdlib JSON, `util` | shipped | `test_foundation`, `test_universe` | used by all studies | MIT; curated values, provenance in `config/` | keep |
| Utilities | `medradar/util.py` (359 L) | dates, text, JSON, deterministic stats used everywhere | main | stdlib | shipped | `test_foundation` | n/a | MIT | keep |
| Polite HTTP | `medradar/http.py` (296 L) | rate limit, retries, disk cache, offline replay | main | urllib, json, cache dir | shipped | `test_foundation`, `test_device` | collection reproducibility | MIT; endpoints from `config/sources.json` | keep |
| Storage/schema | `medradar/db.py` (625 L) | one unified `events` table + registry + trading tables | main | sqlite3 | shipped | `test_foundation`, `test_quant` | backbone of every study | MIT | keep |

### 3.2 Collectors and data layer

| Module | Location | Purpose | Branch/PR | Dependencies | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| openFDA device | `medradar/collect_device.py` (1,064 L) | product-code→track dictionary, 510(k)/PMA/recall events | main | `http`, `db`, `config` | shipped | `test_device` (36) | primary event source | public FDA data; `config/sources.json:5-15`; terms review pending [UNVERIFIED] | keep |
| Drugs@FDA | `medradar/collect_drug.py` (323 L) | original NDA/BLA approvals → `drug_approval` | main | `http`, `db` | shipped | `test_drug` (16) | secondary source | public FDA | keep |
| ClinicalTrials.gov v2 | `medradar/clinical.py` (511 L) | interventional registrations; uses `StudyFirstPostDate` as knowledge time (`:1-9`) | main | `http`, `db` | shipped | `test_device` | knowledge-time discipline | public CT.gov | keep |
| NMPA adapter | `medradar/nmpa.py` (401 L) | China NMPA adapter; documents HTTP 412 block honestly (`:1-8`) | main | `http` | shipped but **blocked** by upstream | `test_nmpa` (15) | honest null-result | public site, blocked; no scraping workaround | keep |
| AdCom calendar | `medradar/adcom.py` (369 L) | FDA Advisory Committee calendar + briefing materials (pre-decision) | main (also PR #1) | `http`, fixtures | shipped | `test_frontier` | frontier pre-decision signal | public FDA | keep |
| Frontier feed | `medradar/frontier.py` (223 L) | front-edge device intelligence across public pre-decision signals | main (also PR #1) | `adcom`, `db` | shipped | `test_frontier` (8) | frontier layer | public sources | keep |
| Product families | `medradar/families.py` (1,439 L) | FDA product code → 产品族 taxonomy | main | `config/product_*` | shipped | `test_products` | taxonomy for studies | config generated by `scripts/build_product_catalog.py` | refactor (1,439 L, generated-config coupling) |
| Product intelligence | `medradar/products.py` (665 L) | read-only product-level API over facts + 2 generated files (`:1-6`) | main | `families`, `db`, config | shipped | `test_products` (14) | product lane | MIT | keep |
| Prices | `medradar/prices.py` (356 L) | daily US bars from Yahoo chart endpoint | main | `http` | shipped | `test_quant` | trading studies only | Yahoo ToS — **not** a research-data licence [UNVERIFIED] | pending (legal) |

### 3.3 Analysis, reporting, trading

| Module | Location | Purpose | Branch/PR | Dependencies | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| Metrics engine | `medradar/analyze.py` (1,142 L) | SQLite facts → `out/metrics.json` (contract `docs/SCHEMA.md`) | main | `db`, `stats` | shipped | `test_quant`, `test_stats` | produces every headline metric | MIT | keep |
| Chinese report + HTML | `medradar/report.py` (4,520 L) | read-only report/dashboard from `metrics.json`; stdlib only (`:1-7`) | main | `metrics.json` | shipped | `test_report` (25) | publication surface | MIT | **refactor/split** (largest module) |
| Dashboard SPA | `medradar/dashboard.py` (1,368 L) | single-file dependency-free dashboard | main | JSON only | shipped | `test_dashboard` (11) | demo surface | MIT | keep |
| Research statistics | `medradar/stats.py` (1,391 L) | dependency-free, documented inference (bootstrap etc.) | main | stdlib | shipped | `test_stats` (61) | methods core | MIT | keep |
| Stats CLI | `medradar/stats_cmd.py` (827 L) | data-scale/distribution report for `medradar stats` | main | `db` | shipped | `test_stats_cmd` (33) | dataset audit | MIT | keep |
| Data-quality audit | `medradar/audit.py` (244 L) | missing dates, unmatched companies, price gaps, future timestamps (`:1-6`) | main | `db` | shipped | `test_audit` (5) | quality gate | MIT | keep |
| Onboarding | `medradar/onboarding.py` (502 L) | offline demo, `doctor`, watchlist | main | `dashboard`, config | shipped | `test_onboarding` (27) | demo only | MIT | keep |
| Event study | `medradar/eventstudy.py` (436 L) | look-ahead-free abnormal returns; entry next open (`:1-9`) | main | `prices`, `stats` | shipped | `test_quant` (19) | inferential lane | Yahoo prices [UNVERIFIED] | pending |
| Paper trading | `medradar/paper.py` (717 L) | long-only simulation over signals | main | `eventstudy` | shipped | `test_quant` | **simulation, not alpha** | MIT | keep (relabel) |
| Live lane | `medradar/live.py` (1,183 L) | event-driven paper trading on real US bars | main | `prices`, `db` | shipped, opt-in | `test_live` (22) | simulation | Yahoo [UNVERIFIED] | pending |
| Replay | `medradar/replay.py` (3,088 L) | 事件→判定→成交→后续 1/5/20 日 timeline | main | `db`, `prices` | shipped | `test_replay` (44) | replay evidence | MIT + Yahoo | refactor (3,088 L) |
| EDGAR corpus | `medradar/corpus.py` (1,242 L) | 8-K catalyst parsing/classification/corpus utils | main | `http`, `db` | shipped | `test_corpus` (61) | catalyst corpus | SEC public filings | keep |
| Case library | `medradar/cases.py` (668 L) | one traceable record per notable event (`:1-6`) | main | `db`, `corpus` | shipped | `test_cases` (13) | qualitative evidence | SEC/FDA quotes — **quote-only** reuse | keep |
| Calibration | `medradar/calibration.py` (1,090 L) | reproducible LLM-vs-human judge calibration | main | `llm`, labels | shipped | `test_llm` (12) | methods evidence | MIT; labels are internal | keep |
| LLM judge | `medradar/llm.py` (320 L) | 8-K position-sizing judge; **opt-in**, DeepSeek-compatible API | main | urllib + env keys | shipped, optional | `test_llm` (12) | calibration only | third-party LLM ToS; no data sent in CI [INFERENCE] | pending (vendor/ToS) |

### 3.4 Research foundation on `main`

| Module | Location | Purpose | Branch/PR | Dependencies | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| Forecast registry | `medradar/forecast_registry.py` (1,271 L) | immutable registry; server-assigned `generated_at`; SQL triggers reject UPDATE/DELETE (`:1-8`) | main (PR #2/#4) | sqlite3 | shipped, audited | `test_forecast_registry` (55) | **core scientific asset** | MIT | keep |
| Research agent | `medradar/research_agent.py` (1,900 L) | deterministic, evidence-grounded workflow; **no model calls** (`:1-8`) | main (PR #3/#4) | `db`, `forecast_registry` | shipped | `test_research_agent` (20) | Market-to-R&D lane | MIT | refactor (1,900 L, CLI in module) |
| `intelligence.pipeline` | `medradar/intelligence/pipeline.py` (167 L) | reproducible Market-to-R&D ingestion pipeline | main (PR #4) | sources, features | shipped | `test_intelligence` | orchestration | MIT | keep |
| `intelligence.evalstats` | `…/evalstats.py` (1,455 L) | cluster-aware evaluation statistics on non-independent rows (`:1-8`) | main (PR #4) | stdlib math | shipped | `test_evalstats` (37) | **methods core** | MIT | keep |
| `intelligence.universe` | `…/universe.py` (849 L) | deterministic applicant-entity universe (9,412 entities, `research/ROADMAP.md:12`) | main (PR #4) | config, db | shipped | `test_universe` (35) | entity foundation | `config/universe_v1.json` (1.71 MB) | keep |
| `intelligence.changepoint` | `…/changepoint.py` (536 L) | change-point detectors for the OBSERVE layer | main (PR #5) | stdlib | shipped | `test_changepoint` (44) | **core science** | MIT | keep |
| `intelligence.profile` | `…/profile.py` (630 L) | seven-field company technology profiles incl. mandatory contradictory evidence | main (PR #5) | db, stores | shipped | `test_profile` (46) | **core science** | MIT | keep |
| `intelligence.promotion` | `…/promotion.py` (221 L) | policy-as-code promotion of a change to "technology change" (`:1-6`) | main (PR #5) | changepoint | shipped | `test_promotion` (28) | **core science** (D-043/D-048) | MIT | keep |
| `intelligence.snapshot` | `…/snapshot.py` (97 L) | snapshot manifests: per-artifact SHA-256 + as-of date | main (PR #5) | stdlib hashlib | shipped | `test_snapshot` (23) | reproducibility | MIT | keep |
| `intelligence.graph_context` | `…/graph_context.py` (391 L) | read-only TKG graph context ("what was known at T") | main (PR #4) | `tkg` | shipped | `test_tkg_integration` (11) | TKG consumer | MIT | keep |
| `intelligence.storage` | `…/storage.py` (257 L) | Market-Intelligence storage; valid/knowledge time on every fact (`:1-6`) | main (PR #4) | sqlite3 | shipped | `test_market_intelligence` | bitemporal lane | MIT | keep |
| `intelligence.taxonomy` | `…/taxonomy.py` (82 L) | versioned technology taxonomy so remaps are visible | main (PR #4) | config | shipped | `test_taxonomy` (10) | noise control | MIT | keep |
| `intelligence.forecasts` | `…/forecasts.py` (141 L) | frozen prospective forecasts: register now, score later | main (PR #4) | registry | shipped | `test_forecasts` (18) | **prospective discipline** | MIT | keep |
| `evaluation.backtesting` | `…/evaluation/backtesting.py` (518 L) | expanding-window rolling origin + final time holdout, purged labels | main (PR #4) | stdlib | shipped | `test_market_intelligence` | **methods core** | MIT | keep |
| `evaluation.leakage_audit` | `…/evaluation/leakage_audit.py` (408 L) | independently replays available_at; catches injected future features (`:1-8`) | main (PR #4) | stdlib | shipped | `test_research_integrity` (10) | **methods core** | MIT | keep |
| `evaluation.metrics` | `…/evaluation/metrics.py` (130 L) | probability/ranking/error/lead-time metrics, explicit empty cases | main (PR #4) | stdlib | shipped | `test_evalstats` | methods | MIT | keep |
| `forecasting.cycle` | `…/forecasting/cycle.py` (301 L) | train→score→register→verify→export, idempotent | main (PR #4) | registry, models | shipped | `test_forecast_cycle` (5) | forecast lane | MIT | keep |
| `forecasting.horizon` | `…/forecasting/horizon.py` (159 L) | horizon forecasts anchored on quarterly cutoff | main (PR #3/#4) | models | shipped | `test_forecasts` | forecast lane | MIT | keep |
| `forecasting.registry_adapter` | `…/forecasting/registry_adapter.py` (395 L) | Horizon rows → canonical Forecast Registry | main (PR #4) | registry | shipped | `test_registry_adapter` (11) | integration seam | MIT | keep |
| `forecasting.calibration` | `…/forecasting/calibration.py` (22 L) | future forecast calibration from verified registry rows | main (PR #4) | registry | **stub** (22 L) | `test_forecasts` | not implemented | MIT | pending |
| `sources.market_data` | `…/sources/market_data.py` (315 L) | PIT daily bars imported offline from price table | main (PR #4) | prices | shipped | `test_market_intelligence` | PIT market input | Yahoo [UNVERIFIED] | pending |
| `sources.openfda_bulk` | `…/sources/openfda_bulk.py` (121 L) | streaming bulk collector (`ijson`) | main (PR #4) | `ijson` extra | shipped, optional | `test_intelligence` | scale path | public FDA | keep |
| `sources.patents` | `…/sources/patents.py` (237 L) | USPTO Open Data Portal; **honest blocked path** without key (`:1-10`) | main (PR #4) | key env | shipped, blocked | `test_intelligence` | not usable without key | USPTO terms | pending |
| `sources.procurement_us` | `…/sources/procurement_us.py` (126 L) | USAspending awards; `pit_usable=0` snapshot (`:1-5`) | main (PR #4) | `http` | shipped | `test_quant` | descriptive only | US gov public | keep |
| `sources.publications` | `…/sources/publications.py` (268 L) | OpenAlex counts, keyless | main (PR #4) | `http` | shipped | `test_publication_intelligence` | publication features | OpenAlex CC0 [FACT: `data_expansion` licence audit] | keep |
| `sources.sec_financials` | `…/sources/sec_financials.py` (119 L) | EDGAR XBRL with filing-time semantics (`:1-5`) | main (PR #4) | `http` | shipped | `test_intelligence` | financial features | SEC public | keep |
| `features.*` (5 modules) | `…/features/` (335+432+121+162+43 L) | PIT market / research / financial / publication / demand features | main (PR #4) | sources | shipped | `test_market_intelligence`, `test_intelligence` | **PIT discipline** | MIT | keep |
| `models.baseline` | `…/models/baseline.py` (135 L) | deterministic logistic baseline, train-only imputation | main (PR #4) | stdlib math | shipped | `test_intelligence` | baseline only | MIT | keep |
| `entities.technology_mapping` | `…/entities/technology_mapping.py` (26 L) | evidence-backed product/technology edges | main | config | **minimal** (26 L) | `test_intelligence` | seed | MIT | pending |

### 3.5 Temporal knowledge graph (`medradar/tkg/`)

| Module | Location | Purpose | Branch/PR | Dependencies | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| TKG package | `medradar/tkg/__init__.py` (44 L) | append-only bitemporal store, as-of queries, deterministic PIT export | main (PR #2, authored by Kimi; `docs/ATTRIBUTION.md:10`) | sqlite3 | shipped | `test_tkg` (50) | foundation | MIT | keep |
| TKG CLI | `medradar/tkg/__main__.py` (260 L) | `python -m medradar.tkg demo|import|export` (`:1-6`) | main | store/query | shipped | `test_tkg` | operator tool | MIT | keep |
| TKG store | `medradar/tkg/store.py` (675 L) | assertion revisions; append-only invariants (`:1-8`) | main | sqlite3 | shipped | `test_tkg` | **core** | MIT | keep |
| TKG query | `medradar/tkg/query.py` (168 L) | `known_at`/`valid_at` as-of semantics (`:1-8`) | main | store | shipped | `test_tkg` | **core** | MIT | keep |
| TKG adapter | `medradar/tkg/adapter.py` (232 L) | read-only `events`→assertions (`mode=ro`, `query_only`) (`:1-6`) | main | db | shipped | `test_tkg_integration` | integration seam | MIT | keep |
| TKG export | `medradar/tkg/export.py` (122 L) | byte-stable point-in-time dataset export | main | store | shipped | `test_tkg` | reproducibility | MIT | keep |
| TKG time | `medradar/tkg/_time.py` (55 L) | strict UTC ISO-8601 primitives (Py3.10 parser gap) | main | stdlib | shipped | `test_tkg` | internal | MIT | keep |

### 3.6 Study logic (`medradar/studies/`) — pure functions behind the S-026 early-signal study

| Module | Location | Purpose | Branch/PR | Dependencies | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| pairing | `medradar/studies/pairing.py` (81 L) | earlier-source → first later regulatory event; ambiguity reported | main (PR #6) | none | shipped | `test_study_pairing` (14) | study method | MIT | keep |
| coverage | `medradar/studies/coverage.py` (204 L) | Tier-A/B source tiering + coverage measurement | main (PR #6) | none | shipped | `test_study_coverage` (18) | study method | MIT | keep |
| concurrent | `medradar/studies/concurrent.py` (226 L) | concurrent multi-source change detection (study O1) | main (PR #6) | none | shipped | `test_study_concurrent` (27) | study method | MIT | keep |
| pointprocess | `medradar/studies/pointprocess.py` (211 L) | point-process rate-change LR under controlled truth | main (PR #6) | none | shipped | `test_study_pointprocess` (20) | study method | MIT | keep |
| thirdsource | `medradar/studies/thirdsource.py` (118 L) | Europe PMC third-source classification | main (PR #8) | none | shipped | `test_study_thirdsource` (15) | study method | Europe PMC terms | keep |
| adjudication | `medradar/studies/adjudication.py` (132 L) | deterministic agent pre-adjudication rubric | main (PR #9) | none | shipped | `test_study_adjudication` (19) | **non-human tier** | MIT | keep |
| humanreview | `medradar/studies/humanreview.py` (102 L) | validates filled human worksheet; agreement diagnostic | main (PR #10/#11) | none | shipped | `test_study_humanreview` (15) | human-review gate | MIT | keep |
| crosswalk | `medradar/studies/crosswalk.py` (87 L) | therapy-area → device-track text join | main (PR #6) | none | shipped | `test_study_crosswalk` (11) | study method | MIT | keep |
| leadtimedesc | `medradar/studies/leadtimedesc.py` (94 L) | independence + representative selection for lead-time | main (PR #6) | none | shipped | `test_study_leadtimedesc` (7) | study method | MIT | keep |

### 3.7 CLI entry-point catalogue

**Primary console script.** `medradar = "medradar.__main__:main"` (`pyproject.toml`, `[project.scripts]`); equivalent `python -m medradar <cmd>`.

| # | Subcommand | Help text (verbatim from parser) | Category |
|---:|---|---|---|
| 1 | `collect` | fetch public data into SQLite | ingest |
| 2 | `analyze` | compute metrics JSON | transform |
| 3 | `frontier` | build the domain-aware pre-decision device intelligence feed | product |
| 4 | `report` | render Chinese report + HTML dashboard | publish |
| 5 | `trade` | run the simulated equity study | simulation |
| 6 | `run` | collect + analyze + report (+ trade) | orchestration |
| 7 | `status` | show what has been collected | ops |
| 8 | `demo` | offline demo report from the committed snapshot | demo |
| 9 | `doctor` | environment self-check (config, data dir, DB, network) | ops |
| 10 | `watchlist` | manage the device watchlist without editing JSON | config |
| 11 | `live` | event alerts + simulated real-time US paper trading | simulation |
| 12 | `judge` | score one 8-K filing text with the LLM judge | optional LLM |
| 13 | `replay` | build the event-to-fill replay timeline | analysis |
| 14 | `products` | product-family intelligence for medical devices | product |
| 15 | `cases` | build the traceable case library from the EDGAR corpus | evidence |
| 16 | `corpus` | inspect or ingest the EDGAR historical catalyst corpus | evidence |
| 17 | `dashboard` | build the interactive zero-dependency dashboard | publish |
| 18 | `audit` | data-quality audit (dates, matches, prices, freshness) | quality |
| 19 | `stats` | dataset scale and distribution report | quality |
| 20 | `selftest` | run the offline test suite | QA |

**Secondary entry points on `main`.** `python -m medradar.tkg {demo,import,export}` (`medradar/tkg/__main__.py:1-6`); `scripts/forecast_cycle.py` (offline forecast CLI, `:1-6`); `scripts/nightly.ps1` (collect→trade→replay→analyze→report→stats, `:1-4`).

**Branch-only entry points (NOT ON MAIN).** `medradar.web.__main__` and `medradar/web/app.py` (#12), `medradar.atlas.__main__` + `atlas/cli.py` (#28), `medradar.integration.__main__` + `integration/cli.py` (#30), `research/horizon` CLI (`python -m hz.cli`, #29) — all absent from `main` [FACT].

---

## 4. `config/` — curated knowledge (2,283,315 B, 10 files)

| Path | Bytes | Purpose | Provenance | Rec. |
|---|---:|---|---|---|
| `config/universe_v1.json` | 1,711,167 | deterministic entity universe (9,412 entities; `research/ROADMAP.md:12`) | generated deterministically; no fuzzy matching | keep |
| `config/product_catalog_zh.json` | 303,361 | Chinese product catalogue | generated by `scripts/build_product_catalog.py` | integrate |
| `config/product_families.json` | 167,635 | product-family taxonomy (150–220 families; `medradar/families.py:1-5`) | same generator | integrate |
| `config/product_code_tracks.json` | 39,233 | ~2k product codes → 38 investment tracks (`medradar/families.py:4-6`) | curated | keep |
| `config/tracks_device.json` | 24,668 | device track dictionary + keywords | curated | keep |
| `config/companies_device.json` | 13,786 | device company/ticker aliases | curated | keep |
| `config/companies_drug.json` | 9,197 | drug company aliases | curated | keep |
| `config/nmpa_demo_seed.csv` | 6,951 | demo seed rows for NMPA lane | curated demo | archive (demo-only) |
| `config/tracks_drug.json` | 5,149 | drug track dictionary | curated | keep |
| `config/sources.json` | 2,168 | 47-line source registry: base URLs, free/credentialed posture, notes | curated 2026-10-31 | keep; **licence fields absent on main** — a real gap vs branch `research/data_expansion` which has a per-source licence register |

**FACT:** `config/sources.json:5` states "Everything here is free and requires no credentials." **INFERENCE:** that is a *cost/access* statement, not a licence statement; 13 of the sources later audited on `research/data-expansion-001` are "free but redistribution-restricted" and 3 are `UNKNOWN` (§14.9). `main` carries **no** per-source `redistribution_allowed` field. [RECOMMENDATION] adopt the branch's licence-register schema into `config/` before any data is republished.

---

## 5. `experiments/` — 657 files, 15.05 MiB, 34 directories

**Shape.** 29 `b0xx` "cycle" directories (b026…b098) plus 5 named benchmark directories. Each is a self-contained record of one research iteration: scripts (`*.py`), committed outputs (`*.json`), logs (`*.log`), and occasionally a `REPORT.md`. 154 `.py` and 331 `.md` across the tree; 657 files total.

**FACT (structure):** `experiments/b027` alone holds 391 files / 5,156,935 B, of which `experiments/b027/snapshots` is 336 files / 3,390,498 B and `experiments/b027/profiles` is 5 files. `experiments/detect_v1` holds 60 files / 5,220,240 B.

| Family directory | Files | Bytes | What it contains (observed) | Linked research record | Rec. |
|---|---:|---:|---|---|---|
| `experiments/b027/` | 391 | 5,156,935 | freeze/snapshot pipeline, `snapshots/` 336, `profiles/` 5, promotion logging | `research/ROADMAP.md:17-18` (profiles + promotion policy) | archive (frozen evidence) |
| `experiments/detect_v1/` | 60 | 5,220,240 | change-detection benchmark: `benchmark.json`, `bin_sweep`, `comovement`, `entries*`, `realdetect` | `research/ROADMAP.md:13` (winner not identifiable — D-018) | archive |
| `experiments/b026/` | 41 | 1,212,954 | confirm-window / density-confirm scripts + outputs | cycle 20/23 confirmations | archive |
| `experiments/reverse_rd_v2/` | 17 | 883,635 | ablation metrics: market/publication/entry/continuation, provenance | PR #3/#4 lineage | archive |
| `experiments/detect_v1_verify/` | 3 | 880,529 | independent verification artefacts for `detect_v1` | verification | archive |
| `experiments/cycle2_coverage/` | 24 | 678,181 | cycle-2 coverage/power `panel_p1/p2`, backtests | `research/CYCLE2_DESIGN.md` | archive |
| `experiments/b030/` | 35 | 566,559 | hiring panel / ATS battery / lag analysis | cycle 10 hiring | archive |
| `experiments/reverse_rd_v1/` | 6 | 188,402 | first reverse-R&D forecast set + provenance | PR #3 precursor | archive |
| `experiments/b040/` | 12 | 187,363 | density experiment artefacts | cycles 30–31 | archive |
| `experiments/b039/` | 5 | 158,370 | deployment-resolution experiment | `research/ROADMAP.md:14` (D-044/D-045) | archive |
| `experiments/b050/` | 6 | 158,643 | cycle-? artefacts (logs/json) | see `research/RESULTS` | archive |
| `experiments/b083/` | 2 | 144,996 | large JSON artefact | cycles 33–42 range | archive |
| `experiments/b080/` | 7 | 71,700 | artefacts | cycles ~32–40 | archive |
| `b074` | 4 | 20,608 | **`experiments/b074/seasonality.json`** — cited as last completed cycle | `research/STATE.json:17`, `:1106` | archive (keep provenance) |
| `b067,b068,b073,b084–b098` | 1–7 each | 4.8–18.6 KB each | per-cycle scripts/outputs; small | mapped loosely to `research/RESULTS/cycleNN_*.md` | archive |
| **b0xx total** | 596 | **~12.4 MB** | 29 directories | — | archive |
| `reverse_rd_v1/v2`, `detect_v1`, `detect_v1_verify`, `cycle2_coverage` | 110 | ~7.5 MB | named benchmarks | — | archive |

### 5.1 Complete `b0xx` directory ledger (29 directories, 596 files)

File/byte counts measured with `git ls-tree -r -l`; purpose is **not** inferred from the number except where a cited artifact proves it.

| Dir | Files | Bytes | Observable artifact types | Evidence for purpose |
|---|---:|---:|---|---|
| `b026` | 41 | 1,212,954 | confirm-window/density scripts + json | cycle 20/23 in `research/RESULTS` |
| `b027` | 391 | 5,156,935 | freeze/snapshot pipeline, `snapshots/` 336, `profiles/` 5 | `research/ROADMAP.md:17-18` |
| `b030` | 35 | 566,559 | hiring panel, ATS battery, lag analysis | cycle 10 hiring |
| `b039` | 5 | 158,370 | deployment-resolution artefacts | `research/ROADMAP.md:14` |
| `b040` | 12 | 187,363 | density experiment artifacts | cycles 30–31 |
| `b050` | 6 | 158,643 | json/log artefacts | `research/RESULTS` |
| `b067` | 4 | 19,254 | json/log artefacts | `research/RESULTS` |
| `b068` | 7 | 18,591 | json/log artefacts | `research/RESULTS` |
| `b073` | 5 | 17,701 | json/log artefacts | `research/RESULTS` |
| `b074` | 4 | 20,608 | `seasonality.json`, `seasonality.py` | `research/STATE.json:17` (last completed cycle 41) |
| `b080` | 7 | 71,700 | json/log artefacts | `research/RESULTS` |
| `b081` | 2 | 10,340 | json/log artefacts | `research/RESULTS` |
| `b082` | 1 | 12,142 | json | `research/RESULTS` |
| `b083` | 2 | 144,996 | large json | `research/RESULTS` |
| `b084` | 2 | 17,011 | json | `research/RESULTS` |
| `b085` | 2 | 15,494 | json | `research/RESULTS` |
| `b086` | 1 | 17,063 | json | `research/RESULTS` |
| `b087` | 1 | 4,896 | json | `research/RESULTS` |
| `b088` | 2 | 18,815 | json | `research/RESULTS` |
| `b089` | 1 | 6,672 | json | `research/RESULTS` |
| `b090` | 1 | 4,832 | json | `research/RESULTS` |
| `b091` | 1 | 14,362 | json | `research/RESULTS` |
| `b092` | 3 | 12,613 | json | `research/RESULTS` |
| `b093` | 3 | 5,985 | json | `research/RESULTS` |
| `b094` | 1 | 8,776 | json | `research/RESULTS` |
| `b095` | 2 | 11,123 | json | `research/RESULTS` |
| `b096` | 1 | 8,625 | json | `research/RESULTS` |
| `b097` | 2 | 16,189 | json | `research/RESULTS` |
| `b098` | 2 | 9,172 | json | `research/RESULTS` |
| **total** | **596** | **~12.4 MB** | | |

[INFERENCE] the `b0xx` numbering is a **work-batch id**, not a cycle id: 29 directories cover 42 narrative cycles, and the only hard mapping (`b074`→cycle 41) is explicit in `STATE.json`. Any future use must join through `research/RESULTS/` or the decisions log.

**INFERENCE (cycle mapping):** directory numbers are **not** 1:1 with cycle numbers (`STATE.json:17` pairs *cycle 41* with `b074`); `research/RESULTS/cycleNN_*.md` (46 files) is the authoritative narrative index. Do not infer purpose from directory name alone.

**Data rights (experiments).** Mostly derived aggregates. Two carry explicit provenance sidecars: `experiments/reverse_rd_v1/data_provenance.json`, `experiments/reverse_rd_v2/data_provenance.json`, `experiments/reverse_rd_v2/publication_provenance.json` [FACT: paths]. [RECOMMENDATION] these three are the pattern every frozen experiment should have; most `b0xx` dirs lack one.

---

## 6. `research/` — 116 files, 1.33 MiB (programme state, not code)

| Asset | Path | Size | Purpose | Status | Rec. |
|---|---|---:|---|---|---|
| Machine state | `research/STATE.json` | 66,700 B | `schema=medradar.foresight.state.v2`, `phase="complete_verified"`, `cycle=44`, `last_completed_cycle={cycle:41,name:"seasonality"}` (`:11-18`) | **cycle 44 vs last-completed 41** — internally inconsistent | refactor (single source of truth) |
| Objective audit | `research/AUDIT.json` | 2,931 B | `objective_audit_v1`; 11 PASS / 0 FAIL / 1 N/A (`:108`) | audit output, regenerable by `tools/audit_objectives.py` | keep |
| Final audit | `research/FINAL_AUDIT.json` | 3,633 B | `final_audit_v1`; records `git.branch="research/change-detection-v1"`, `head=c39e3f8…`, dirty files | **not about `main`** — branch-scoped record | archive after pinning |
| Backlog | `research/BACKLOG.yaml` | 40,089 B | 833-line task ledger, `schema medradar.foresight.backlog.v2`, 63 tasks | living | keep |
| Decisions | `research/DECISIONS.md` | 185,056 B | ADR-style decision record (D-011 realignment, D-043/D-048, 74 decisions per `FINAL_AUDIT.json`) | **authoritative research log** | keep |
| Mission/charter | `research/MISSION.md` | 15,244 B | "Observe → Understand → Anticipate"; realigned 2026-11-02 | authoritative | keep |
| Protocols | `research/PREDICTION_PROTOCOL.md` (8,294), `HYPOTHESES*.md`, `LITERATURE*.md`, `EXPERIMENTS.md`, `LAYERS.md` | ~200 KB | pre-registration and literature | mixed freshness | keep |
| Committee docs | `research/DATA_PROVENANCE.md` (6,751), `COMPLETION_REPORT.md` (7,279), `AUDIT.md` (1,339), `ROADMAP.md` (7,215) | ~23 KB | narrative reporting | narrative, not machine state | keep |
| Results | `research/RESULTS/` (46 files) | 194,509 B | `cycle1…cycle42` reports + `PROMOTIONS.md` + `README.md` | historical record | archive (frozen) |
| Study | `research/studies/early_signal_5firms/` (50 files) | 687,709 B | S-026 study: protocols, packets, `HUMAN_REVIEW_WORKSHEET.csv`, adjudication, lead/lag | **only research study on `main`** | keep (provenance) |
| Forecasts | `research/forecasts/FORECAST_SET_2026-11-03(.json,_prospective.json)` | 37,044 B | frozen prospective forecast sets | evidence | keep |

### 6.1 Competing state sources (contradiction C8)

[FACT] Four artifacts claim to describe programme state and **disagree**:

| Source | Claims | Scoped to |
|---|---|---|
| `research/STATE.json:11-12` | `phase="complete_verified"`, `cycle=44`, last completed **41** | unclear |
| `research/AUDIT.json:108` | 11/12 objective checks pass | audit run at unknown commit |
| `research/FINAL_AUDIT.json` | branch `research/change-detection-v1` @ `c39e3f8`, dirty tree, 74 decisions / 44 results | **a branch, not `main`** |
| `research/BACKLOG.yaml:9-11` | `phase: observe_change_detection`, 63 tasks | living backlog |

[INFERENCE] `STATE.json` is written by `tools/update_state_*.py` scripts that appear in `tools/` (10 files, §9); the "cycle" counters are agent-workflow bookkeeping, not release versions. **They must not be used as a release signal.** [RECOMMENDATION] freeze all four into `research/archive/` at refoundation and adopt one machine-readable status file owned by the target architecture.

**Data rights (research).** [FACT] `research/studies/early_signal_5firms/` contains derived case packets and a `HUMAN_REVIEW_WORKSHEET.csv` with firm names and public regulatory events — no patient data observed in the study directory listing. [UNVERIFIED] whether any worksheet row embeds personal contact data; the branch `integration/convergence-001` audit found 248 UK procurement contacts in vendored snapshots (§14.11) — the main study predates that lane.

---

## 7. `papers/` — 32 files, 0.51 MiB

| Asset | Path | Size | Purpose | Status | Rec. |
|---|---|---:|---|---|---|
| Empirical paper | `papers/PAPER_v1.md` | 35,261 B | Can tech change be anticipated from filings? | draft, not submitted (`papers/README.md:3`) | keep |
| Methods paper | `papers/PAPER_METHODS_v1.md` | 10,467 B | what a year of self-audit produced | draft | keep |
| Negative-results paper | `papers/PAPER_NEGATIVE_v1.md` | 11,802 B | what public filings cannot tell us | draft | keep |
| Claim maps | `papers/CLAIMS.json` (16,677), `CLAIMS_METHODS.json` (4,752), `CLAIMS_NEGATIVE.json` (5,848) | — | every quantitative claim + exact source substring | **machine-verified** | keep |
| Claim builders/verifiers | `build_claims.py` (183 L), `build_claims_methods.py`, `build_claims_negative.py`, `verify_claims.py` (55 L), `verify_figures.py`, `check_layout.py`, `rules_map.py` | — | regenerate/verify claim maps | shipped | keep |
| Figures | `papers/figures/` (6 files), `figures.py` (20,669 B) | 99,798 B | fig1–fig5 SVG + `figures_data.json` | generated | keep |
| One-shot state fixers | `update_state_cycle*.py` (17/18/23/36), `fix_*_claims.py`, `add_*_claims.py`, `fix_x4_claim.py`, `fix_deployment_claims.py` | ~40 KB | historical repair scripts | **one-shot, superseded** | archive |
| Selftest logs | `selftest_cycle17.log`, `selftest_cycle18.log` | 263,600 B | pytest tails | historical | archive |

[FACT] `papers/README.md:7-9` lists three papers each with a claim map and verifier. [INFERENCE] the claim-map mechanism (`CLAIMS.json` + `verify_claims.py`) is the strongest reproducibility asset in the repository and should survive refoundation.

---

## 8. `verifier/` — 22 files, 34,482 B

| Asset | Path | Purpose | Status | Rec. |
|---|---|---|---|---|
| Acceptance spec | `verifier/v1/criteria.md` (18 lines) | 10 behavioural acceptance criteria for the Market-to-R&D layer | FACT: criteria 1–10 enumerated | keep |
| Verifier | `verifier/v1/verify.py` | runs full offline suite in subprocess, parses committed artifacts, recomputes numbers — "not a self-certification checklist" (`:1-8`) | runnable | keep |
| Run record | `verifier/runs/` (19 files: `001-baseline-tests` … `013-v1-final-delivery`, `.txt` + `.meta`) | committed evidence of each verification run | historical | archive (pin) |
| Index | `verifier/README.md` (3 lines) | points at v1 | thin | refactor |

[INFERENCE] `verifier/` is a *manual* CI substitute: 13 numbered runs were committed because workflow CI is not trusted/available for these checks (`_FACTS.md:240-241` marks main's CI health UNVERIFIED). This is valuable archaeological evidence but not automation.

---

## 9. `tools/` — 15 files, 63,663 B (round plumbing)

| Asset | Path | Purpose | Status | Rec. |
|---|---|---|---|---|
| Objective audit | `tools/audit_objectives.py` (270 L) | checks mission requirements mechanically → `research/AUDIT.json`/`.md` (`:1-6`) | runnable | integrate |
| Final audit | `tools/final_audit.py` (155 L) | re-runs load-bearing scripts, compares JSON byte-for-byte (`:1-7`) | runnable | integrate |
| Round-end gate | `tools/round_end.py` (122 L) | runs every verifier in order, writes summary (`:1-6`) | runnable | **integrate** (this is the missing CI gate) |
| State updaters | `update_state_cycle33/37/38/39.py`, `update_state_final.py` (3.7–4.7 KB each) | one-shot edits to `STATE.json` per cycle | **superseded, one-shot** | archive |
| GitHub helper | `tools/github_api.py` (4,860 B) | API helper | unclear use | archive |
| Logs | `audit.log`, `final_audit.log`, `round_end*.log/json` | run evidence | historical | archive |
| Claim fixer | `tools/fix_claim_p2.py` | one-shot | archive |

---

## 10. `scripts/` — 13 files, 0.38 MiB

| Asset | Path | Purpose | Status | Rec. |
|---|---|---|---|---|
| Catalogue generator | `scripts/build_product_catalog.py` (3,026 L, 227,444 B) | one-shot generator for `config/product_families.json` + `product_catalog_zh.json` (`:1-5`) | runnable but **one-shot** | integrate (make repeatable) |
| Corpus build | `scripts/build_corpus.py` (44,174 B) | builds EDGAR corpus | runnable | keep |
| Ablation (market) | `scripts/run_market_ablation.py` (460 L) | offline incremental-value ablation | runnable | keep |
| Ablation (publication) | `scripts/run_publication_ablation.py` | offline ablation | runnable | keep |
| Backfills | `scripts/backfill_device.py` (19,518), `backfill_trials.py` (10,947), `backfill_drug.py` (9,413), `backfill_case_prices.py` (1,839) | historical backfills | runnable | keep |
| TKG import | `scripts/tkg_import_research.py` (15,115) | import research DB into TKG | runnable | keep |
| Forecast cycle | `scripts/forecast_cycle.py` (79 L) | offline forecast CLI (`:1-5`) | runnable | keep |
| Install proof | `scripts/check_install.py` (267 L) | proves installed wheel self-sufficient (`:1-5`) | runnable, used by CI | **keep** |
| Agent demo | `scripts/run_agent_demo.py` | offline research-agent demo | runnable | keep |
| Nightly | `scripts/nightly.ps1` (293 L) | collect→trade→replay→analyze→report→stats (`:1-4`) | operational, Windows-only | refactor (portable) |

---

## 11. `tests/` — 105 files, 47 test modules, 57 fixtures; **1,074 tests, exit 0**

**Measured baseline on `b2a14c0` [FACT, reproduced 2026-11-12]:**

```
python -B -m pytest -p no:cacheprovider -q          -> exit 0
python -B -m pytest -p no:cacheprovider --collect-only -q  -> 1,074 tests in 47 modules
```

**FACT:** the suite needs **no network and no database** (fixtures are committed); `pyproject.toml` sets `testpaths=["tests"]`, `addopts="-q"`. This matches the README's "678 tests" claim only loosely — 678 is stale (C4, `_FACTS.md:252`).

### 11.1 Test-module → capability map

| Capability | Test modules (tests) |
|---|---|
| Data-quality / metrics contract | `test_audit` (5), `test_stats` (61), `test_stats_cmd` (33), `test_report` (25) |
| Collectors & knowledge | `test_device` (36), `test_drug` (16), `test_nmpa` (15), `test_universe` (35), `test_foundation` (15), `test_taxonomy` (10) |
| Product/family lane | `test_products` (14), `test_families` via `test_products` |
| Quant / event study / trading | `test_quant` (19), `test_live` (22), `test_replay` (44), `test_snapshot` (23) |
| EDGAR corpus / cases / calibration | `test_corpus` (61), `test_cases` (13), `test_llm` (12) |
| Market-to-R&D intelligence | `test_intelligence` (28), `test_market_intelligence` (23), `test_publication_intelligence` (12), `test_evalstats` (37), `test_changepoint` (44), `test_profile` (46), `test_promotion` (28), `test_forecasts` (18) |
| Forecast registry | `test_forecast_registry` (55), `test_forecast_cycle` (5), `test_registry_adapter` (11) |
| Temporal knowledge graph | `test_tkg` (50), `test_tkg_integration` (11) |
| Research agent / integrity | `test_research_agent` (20), `test_research_integrity` (10) |
| Early-signal study (S-026) | `test_study_adjudication` (19), `test_study_concurrent` (27), `test_study_coverage` (18), `test_study_crosswalk` (11), `test_study_humanreview` (15), `test_study_leadtimedesc` (7), `test_study_pairing` (14), `test_study_pointprocess` (20), `test_study_thirdsource` (15) |
| Onboarding / dashboard / release | `test_onboarding` (27), `test_dashboard` (11), `test_release` (8), `test_check_layout` (8) |
| Frontier (now on main) | `test_frontier` (8) |

[FACT] `tests/test_phoenix_001.py` and branch-only tests (`test_atlas_*`, `test_extsrc_*`, `test_llm_research_*`, `test_hist_eval`, `test_product_*`, `test_convergence*`) are **not** on `main`.

### 11.2 Fixtures (57 files, 505,046 B)

`tests/fixtures/calibration` (29), `device` (12), `dashboard` (5), `prices` (2), `drug` (2), `replay` (2), `stats` (1) — all committed so the suite is offline.

---

### 11.3 Fixture inventory (57 files, 505,046 B — why the suite is offline)

| Fixture dir | Files | Bytes | Feeds |
|---|---:|---:|---|
| `tests/fixtures/calibration` | 29 | 406,813 | `test_llm`, `test_quant` (LLM verdicts, ground truth) |
| `tests/fixtures/device` | 12 | 22,538 | `test_device`, `test_frontier`, `test_products` |
| `tests/fixtures/dashboard` | 5 | 16,106 | `test_dashboard` |
| `tests/fixtures/stats` | 1 | 8,118 | `test_stats` (mini event table) |
| `tests/fixtures/prices` | 2 | 7,320 | `test_quant`, `test_replay` |
| `tests/fixtures/drug` | 2 | 4,508 | `test_drug` |
| `tests/fixtures/replay` | 2 | 1,247 | `test_replay` |
| `tests/fixtures/_generate.py` (device) | 1 | 8,232 | regeneration helper |

[INFERENCE] fixture size (0.5 MB) vs test code (0.85 MB) is healthy; the offline property is a genuine asset and should be a hard constraint for the target architecture.

## 12. `docs/` — 60 files, 6.39 MiB (contracts + generated site)

| Group | Files | Bytes | Contents | Rec. |
|---|---:|---:|---|---|
| Contract docs (root `*.md`) | 24 | ~350 KB | `SCHEMA.md` (336 L, data contract v1), `METHODS.md` (208), `DATA.md` (287), `RESEARCH.md` (330, protocol v1.1), `TKG.md` (118), `FORECAST_REGISTRY.md` (246), `CALIBRATION.md`, `CASES.md`, `ASSUMPTIONS.md`, `REVERSE_RD.md`, `PHASE1/2/3*.md`, `MARKET_DATA.md`, `PUBLICATION_PATENT_DATA.md`, `TKG_INTEGRATION.md`, `FORECAST_REGISTRY`, `ATTRIBUTION.md`, `GOOD_FIRST_ISSUES.md`, `AUDIT_MARKET_TO_RD.md`, `report_en.md` | keep (contracts) / archive (phase logs) |
| Generated Pages assets | 4 HTML + 5 PNG | 5.7 MB | `dashboard.html` (3,350,819 B), `replay.html` (1,014,957), `preview.png` (488,736), `dashboard_cases/replay/mobile/overview(_preview).png`, `index.html` (112,129), `replay_intraday.html` (80,976) | **archive out of git** (3.35 MB generated HTML; rebuild in CI) |
| Generated data | `metrics.json` (468,561), `summary.csv` (68,460), `report_zh.md` (55,768) | 592,789 B | committed snapshots | integrate as release artifact |
| `docs/research/` | 18 files | 237,107 B | ADRs (`TKG_ADR.md`, `FORECAST_REGISTRY_ADR.md`), acceptance logs (`FOUNDATION_ACCEPTANCE.md`), audits (`KIMI_AUDIT.md`, `AUDIT_CYCLE2.md`), bench (`tkg_bench_synthetic.json`), probe (`foundation_probe.py`) | keep (ADRs are real design evidence) |
| `docs/calibration/` | 5 files | 30,115 B | `ground_truth.csv`, `heuristic_verdicts.json`, `llm_verdicts.json`, `metrics.json`, `score.py` | keep |
| `docs/.nojekyll` | 1 | 0 | Pages marker | keep |

[FACT] `docs/ATTRIBUTION.md:5` credits the v0.2.2 core to a DeepSeek Harness agent team on `deepseek-flash`, and lists Kimi Code as TKG author. [INFERENCE] this is the only place agent authorship is recorded; it is material for the "who owns what" question.

---

### 12.1 Contract documents at `docs/` root (24 Markdown files)

| Document | Bytes | Class | What it governs | Rec. |
|---|---:|---|---|---|
| `report_zh.md` | 55,768 | **generated** | Chinese report snapshot | archive (regenerate) |
| `ASSUMPTIONS.md` | 26,377 | contract | modelling assumptions | keep |
| `RESEARCH.md` | 19,710 | contract (v1.1) | pre-registration rules for every published number (`:1-5`) | keep |
| `REVERSE_RD.md` | 19,642 | method | reverse-R&D lane | keep |
| `DATA.md` | 16,886 | generated + hand | data inventory/scale, auto-generated region | keep (split) |
| `SCHEMA.md` | 16,329 | contract | `metrics.json` data contract v1 | **keep (authoritative)** |
| `CASES.md` | 16,174 | method | case-library rules | keep |
| `FORECAST_REGISTRY.md` | 14,309 | contract | immutable registry semantics | keep |
| `PHASE3_AGENT.md` | 13,904 | phase log | research-agent phase 3 | archive |
| `PHASE3_REGISTRY.md` | 13,813 | phase log | registry phase 3 | archive |
| `TKG_INTEGRATION.md` | 11,860 | phase log | TKG integration | keep (design) |
| `METHODS.md` | 11,559 | contract | "the contract behind the numbers" | **keep** |
| `MARKET_DATA.md` | 11,491 | contract | market data semantics | keep |
| `PUBLICATION_PATENT_DATA.md` | 10,230 | contract | publication/patent semantics | keep |
| `PHASE3.md` | 10,157 | phase log | phase 3 overview | archive |
| `CALIBRATION.md` | 9,562 | method | LLM-judge calibration | keep |
| `INTEGRATION_2026-11-02.md` | 9,215 | log | v0.3.0 integration record | keep (historical) |
| `ATTRIBUTION.md` | 8,854 | provenance | agent authorship record | **keep** |
| `PHASE1.md` | 8,505 | phase log | phase 1 | archive |
| `TKG.md` | 7,813 | contract | TKG usage | keep |
| `report_en.md` | 6,869 | generated | English one-pager | archive (regenerate) |
| `PHASE2.md` | 5,458 | phase log | phase 2 | archive |
| `GOOD_FIRST_ISSUES.md` | 3,849 | stale | onboarding list with 0 issues tracked | archive |
| `AUDIT_MARKET_TO_RD.md` | 1,687 | audit | Market-to-R&D audit note | keep |

[INFERENCE] the contract set (`SCHEMA`, `METHODS`, `RESEARCH`, `FORECAST_REGISTRY`, `TKG`, `CALIBRATION`, `ASSUMPTIONS`) is the repository's real specification and should be treated as the migration source of truth — not `README.md`.

### 12.2 `docs/research/` design records (18 files)

`TKG_ADR.md`, `FORECAST_REGISTRY_ADR.md` (architecture decisions); `FOUNDATION_ACCEPTANCE.md`, `TKG_ACCEPTANCE.md` (acceptance); `KIMI_AUDIT.md`, `AUDIT_CYCLE2.md`, `TKG_HARDENING_REPORT.md`, `INTEGRATION_FIXES.md`, `DETECTION_DESIGN_REVIEW.md` (audits); `CHANGEPOINT.md`, `EVALSTATS.md`, `UNIVERSE.md` (method notes); `FOUNDATION_INTEGRATION_LOG.txt`, `FORECAST_REGISTRY_LOG.txt`, `FOUNDATION_WHEEL_SMOKE.txt`, `selftest_tail.txt` (logs); `foundation_probe.py`, `tkg_bench_synthetic.json` (bench). [RECOMMENDATION] promote the two ADRs and the acceptance notes; archive the logs.

## 13. `.github/` — 8 files (4 workflows, 3 issue templates, PR template)

| Workflow | Lines | Trigger / purpose (verbatim comments) | Status |
|---|---:|---|---|
| `.github/workflows/ci.yml` | 88 | `on: push: branches: [main]` — test/lint | [UNVERIFIED] green on `main` (no runs inspected) |
| `.github/workflows/weekly.yml` | 59 | "Rebuilds the radar every Monday 05:00 Asia/Shanghai … deploys dashboard with official Pages actions" | active by definition of Pages build (`_FACTS.md:239`) |
| `.github/workflows/live.yml` | 57 | "Event-driven paper trading is OPT-IN and not a reliable scheduler" | opt-in |
| `.github/workflows/forecast-cycle.yml` | 107 | "Weekly continuous forecasting cycle … committed and reviewable, but it was **not executed**" | **committed but never run** |

Templates: `bug_report.md` (747 B), `data_correction.md` (947 B), `feature_request.md` (659 B), `pull_request_template.md` (850 B) — [FACT] 0 issues ever opened (`_FACTS.md:49`), so the issue templates are unused.

---

## 14. Branch-only asset families — **NOT ON MAIN**

> **Read this first.** Every row in §14 is a module or directory that exists **only** on a non-`main` branch. None of it is a shipped capability. Membership was proven with `git merge-base --is-ancestor`, not by diff similarity (`_evidence/inventory/ancestry_extra.py`). "Clean merge" values come from `git merge-tree --write-tree` and mean *textually* clean, never *safe* (`BRANCH_PR_AUDIT.md` §4).

### 14.1 Product stack (#12 → #13 → #14)

| Module / asset | Branch(es) | New paths (count) | Purpose | Deps | Impl. | Tests | Research status | Data rights | Rec. |
|---|---|---|---|---|---|---|---|---|---|
| `medradar/product/` | #12 `feat/medradar-2.0-mvp` | 9 files (+`entity_aliases.json`) | company/catalog/analyst/evidence product API | sqlite, config | branch-only, acceptance docs present | `tests/test_product_{store,analyst,api,statistics}.py` + `product_fixture.py` | product lane | MIT; data from existing facts | integrate |
| `medradar/web/` + `web/` | #12 | 5 + 14 JS/HTML | web app + zero-dep frontend (`web/CONTRACT.md`) | product | branch-only | `test_product_api` | product surface | MIT | integrate |
| `docs/PRODUCT_*` | #12 | 6 docs + 8 PNG | product vision/architecture/acceptance/audit/user guide | — | branch-only | n/a | narrative | MIT | integrate (after prune) |
| `medradar/observatory/` | #13 `feat/live-observatory-v1` | 13 files | append-only observation ledger, mapping, scheduler, prospective registry | sqlite, product | branch-only | branch tests | observatory lane | MIT; observation data provenance in docs | integrate |
| `docs/LIVE_OBSERVATORY*`, `PROSPECTIVE_OBSERVATION_REGISTRY.md` | #13 | 13 docs | design/acceptance | — | branch-only | n/a | narrative | MIT | integrate |
| `medradar/observatory/` (extended) + `deploy/` | #14 `feat/observatory-reliability-v1` | 19 py + `deploy/systemd/*`(3) + `deploy/windows/*` | durable persistence, verified backups, health, lock, audit | observatory | branch-only | branch tests | reliability lane | MIT | integrate |
| `docs/reliability/*`, `docs/BACKUP_AND_RECOVERY.md`, `DEPLOYMENT.md`, `HEALTH_AND_VALIDATION.md` | #14 | 9 + 4 docs | operations contracts | — | branch-only | n/a | narrative | MIT | integrate |

### 14.2 Research studies stacked on the unmerged product code

| Module / asset | Branch (PR) | Added files vs `main` | Purpose | Tests | Research status | Data rights | Rec. |
|---|---|---:|---|---|---|---|---|
| S-028 temporal graph early signal | `research/s028-temporal-graph-early-signal` (#15) | 220 (+ inheritance of #12–#14) | temporal company–technology graph early-signal study | branch tests | **DRAFT, negative result per PR title**; **its tip is an ancestor of phase4-base/#21/#22** | MIT code; study inputs derived from main sources | pending (depends on #14) → becomes `integrate` only if the whole chain merges |
| S-029 evidence-based relations | `research/s029-evidence-based-relations` (#16) | 339 (+ #12–#14) | evidence-based temporal relation reconstruction | branch tests | DRAFT, measured evidence; **sibling of S-028, not contained in phase4-base** | MIT; relation evidence from public sources | pending |
| S-031 hiring capability | `research/s031-hiring-capability-study` (#22) | 592 | 100 AI preliminary labels, hiring capability & R&D evidence | branch tests | DRAFT; **contains #15 and #21 and phase4-base** (verified ancestors) | MIT; recruitment data licence not verified [UNVERIFIED] | pending → split (33 genuine files, §14.10) |

**FACT (verified ancestry):** `origin/research/innovation-signals-observatory` **is an ancestor of** `origin/research/s031-hiring-capability-study`; `s028` and `s029` are **siblings** (neither contains the other) and both inherit the full #12→#14 stack. **Additionally — and not stated in `_FACTS.md` — the *S-028 branch tip itself* (`4c6686f`) is an ancestor of `integration/phase4-base`, of #21 and of #22**: `git rev-list --count origin/research/s028… ^origin/integration/phase4-base` = **0**. `integration/phase4-base` therefore contains the whole S-028 study (`research/studies/graph_early_signal_s028/`), and merging #21 or #22 imports S-028 (#15) as well as the product stack. [FACT: `merge-base --is-ancestor`, `rev-list`; `BRANCH_PR_AUDIT.md` §4.1]

### 14.3 Hidden stack membership (ancestry, verified)

`git merge-base --is-ancestor` results (`ancestry_verify.json`, `phoenix_chain.py`):

| Branch | #12 `2.0-mvp` | #13 `live-obs` | #14 `reliability` | #15 `s028` | `phase4-base` | #21 `innovation` | #28 `atlas` | #29 `horizon` |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `feat/live-observatory-v1` (#13) | YES | — | . | . | . | . | . | . |
| `feat/observatory-reliability-v1` (#14) | YES | YES | — | . | . | . | . | . |
| `research/s028…` (#15) | YES | YES | YES | — | . | . | . | . |
| `research/s029…` (#16) | YES | YES | YES | **no** | . | . | . | . |
| `integration/phase4-base` (no PR) | YES | YES | YES | **YES** | — | . | . | . |
| `research/innovation-signals-observatory` (#21) | YES | YES | YES | **YES** | YES | — | . | . |
| `research/s031-hiring-capability-study` (#22) | YES | YES | YES | **YES** | YES | YES | . | . |
| `integration/convergence-001` (#30) | . | . | . | . | . | . | **YES** | **no** |
| `foundation/atlas-001` (#28) | . | . | . | . | . | . | — | . |

[FACT] `integration/phase4-base` is built on **#15 (S-028)**, which itself sits on #12→#14: it is 39 commits ahead = 26 commits of the product+S-028 stack + 13 phase-4 commits. It has **no PR of its own**, yet is the declared base of #21 (`_FACTS.md:141-149`, `BRANCH_PR_AUDIT.md` §2). [INFERENCE] the correct mental model is a 5-deep chain `#12→#13→#14→#15→phase4-base→#21→#22`, not two independent stacks — which is why #21/#22 reviewability is near zero.

### 14.4 PHOENIX program

| Module / asset | Branch (PR) | Added files | Purpose | Tests | Research status | Data rights | Rec. |
|---|---|---:|---|---|---|---|---|
| `experiments/phoenix_001/` (24) + `docs/PHOENIX_*.md` (10) + `verifier/v2/*` | `research/phoenix-001-external-methods` (#23) | 39 | external-methods audit: NIH iSearch, Lens, PTNS, FDA AI panel; RAEA prototype | `tests/test_phoenix_001.py` | DRAFT; **local branch diverged: 33 commits ahead of `main`, 16 behind its remote twin** (§15.4) | **FACT** `docs/PHOENIX_LICENSE_AUDIT.md`: no third-party code copied; SciTrends has **no licence** → methods only, code reuse forbidden | pending (see #23) |
| `experiments/phoenix/` (141) + `docs/phoenix/` (22) | `research/phoenix-001-round2` (#24) | 166 | frozen protocol, 10 pre-registered experiments, 13-project register | branch tests | DRAFT | same licence audit | pending |
| `experiments/phoenix/` (196) + `docs/phoenix/` (26) | `research/phoenix-002-h8-validation` (#25) | 225 | independent H8 re-validation; NO-GO conclusion | branch tests | DRAFT; round-2 is its ancestor | same | pending |
| `experiments/phoenix003/` (97) + `docs/phoenix003/` (6) | `research/phoenix-003-early-evidence` (#26) | 103 | regulatory-anchored early-evidence discovery; NO-GO | branch tests | DRAFT | regulators' public data | pending |

### 14.5 ATLAS / HORIZON / CONVERGENCE

| Module / asset | Branch (PR) | Added files | Purpose | Tests | Research status | Data rights | Rec. |
|---|---|---:|---|---|---|---|---|
| `medradar/atlas/` (31) + `research/atlas/` (16) + `docs/atlas/` (10) + `config/atlas_*` + `tools/run_atlas_pipeline.py`, `tools/verify_atlas.py` | `foundation/atlas-001` (#28) | 68 | identity, evidence and knowledge-graph foundation; identity pilot | `tests/test_atlas_*` (5 modules) + `run_atlas_ci_verifier.py` | DRAFT | public data; `config/atlas_sources.json` | integrate (foundation) |
| `research/horizon/` (688) | `research/horizon-001` (#29) | 691 | global data frontier: two credential-free patent channels, real evidence export, three measured experiments | branch tests | DRAFT; **51-source register, 24 `OPEN_DOCUMENTED`, 2 `BLOCKED_LEGAL`** (`research/horizon/GLOBAL_SOURCE_DEEP_AUDIT.md:1-20`) | **licence per-source register exists; UN Comtrade restriction flagged on this branch (§14.11)** | pending → split |
| `medradar/atlas/` + `medradar/integration/` (11) + `research/convergence/` (31) + `tools/convergence/` (28) + `docs/convergence/` (10) + `tests/convergence/` (5) | `integration/convergence-001` (#30) | 813 | ATLAS × HORIZON end-to-end integration; P0 reconciliation | branch tests + convergence tests | DRAFT | includes `docs/convergence/LICENCE_AND_SECURITY_REVIEW.md` | pending → split; **remove 654 duplicated horizon files** |

### 14.6 Data-expansion

| Module / asset | Branch (PR) | Added files | Purpose | Tests | Research status | Data rights | Rec. |
|---|---|---:|---|---|---|---|---|
| `medradar/external_sources/` (46) + `research/data_expansion/` (863) | `research/data-expansion-001` (#27) | 916 | global data-source discovery, live access verification, licence/cost audit | `tests/test_extsrc_{postmarket,procurement,regulatory,scholarly,trade}.py` + `test_external_sources_foundation.py` | DRAFT (largest single-branch line count, +260,389) | **best licence evidence in repo**: `research/data_expansion/LICENCE_AND_COST_AUDIT.md` — 16 redistribute-allowed, 13 partial, 3 unknown, 4 paid-only | pending → split (adopt licence schema) |

### 14.7 Local-LLM / QLoRA lane

| Module / asset | Branch (PR) | Added files | Purpose | Tests | Research status | Data rights | Rec. |
|---|---|---:|---|---|---|---|---|
| `experiments/local_llm_event_extraction/` (97) | `research/local-llm-foundation` (#19) | 109 | Phase-2 local GPU run (Qwen3-4B) event extraction | `tests/test_llm_research_*` (12 modules) | DRAFT "first real local GPU run" | no model weights committed [FACT: PR body]; HF model licences must be checked [UNVERIFIED] | pending |
| `experiments/local_llm_event_extraction/` (233) + `OVERNIGHT_RESEARCH_REPORT.zh-CN.md` | `research/overnight-qlora-s030` (#20) | 247 | overnight exploratory QLoRA, four-arm evaluation | branch tests | DRAFT "不合并" (do not merge) | same | **archive** |

### 14.8 Maintenance / AI-review / historical

| Module / asset | Branch (PR) | Added files | Purpose | Status | Rec. |
|---|---|---:|---|---|---|
| `docs/DATA_ASSET_REGISTER.md`, `docs/PROJECT_STATUS.md`, `docs/REPOSITORY_AUDIT.md` | `maintenance/repository-consolidation` (#17) | 3 added, 3 modified (+947/−805) | documentation consolidation, research index, data asset register | DRAFT | integrate (cheap, useful) |
| `research/studies/` (4) | `research/ai-evidence-review` (#18) | 4 | independent AI review of 69 packets (machine review, explicitly not human) | DRAFT | integrate after provenance check |
| `experiments/hist_v1/` (11), `hist_v2/` (9), `b099–b105`, `research/protocols/` (5), `papers/PAPER_UPDATE_v1.md` | `research/early-signal-ai-review` | 85 | full-history entry benchmark, cohort sensitivity, lead-lag — **no PR exists for this branch** | remote-only, 11 ahead | pending (§15.5) |
| `experiments/hist_v1/` (11) | `research/full-history-v1` | 19 | full-history 1976–2026 entry benchmark — **no PR exists** | remote-only, 1 ahead, **ancestor of `early-signal-ai-review`** | superseded by `early-signal-ai-review` |
| phase1/2/3 local branches (`phase1/entry-multiwindow`, `phase2/market-features`, `phase2/publications-patents`, `phase3/registry-cycle`, `phase3/research-agent`, `phase3/tkg-integration`) | local only | — | pre-merge development lineage; all fully contained in `main`/remote merged branches | 0 ahead, 78–102 behind | archive |

### 14.9 Family totals (added-vs-`main`, from `git diff --numstat`)

| Family | Representative branch | Added code/data | Notes |
|---|---|---:|---|
| Product + observatory + reliability | #12/#13/#14 | +17,646 / +31,301 / +22,899 | 3-deep clean stack |
| S-028 / S-029 | #15 / #16 | +114,442 / +133,237 | inherit product stack |
| PHOENIX 001/002/003 | #23/#24/#25/#26 | +6,075 / +158,731 / +58,438 / +197,464 | independent lineages |
| ATLAS | #28 | +18,648 | foundation |
| HORIZON | #29 | +692,975 | 691 files, mostly `research/horizon/` |
| CONVERGENCE | #30 | +690,079 | 80 % duplicated from HORIZON |
| Data-expansion | #27 | +260,389 | 916 files |
| Local-LLM / QLoRA | #19/#20 | +32,464 / +16,826 | GPU, no weights |
| S-031 / Phase-4 | #22/#21 | +303,926 / +64,441 | #22 contains #21 |
| Repository consolidation | #17 | +947/−805 | docs only |
| AI review | #18 | +575 | 4 files |

### 14.10 Duplication (copy-paste, not inheritance)

[FACT] Measured by comparing blob SHAs of files added vs `main` (`_evidence/inventory/ancestry_verify.json` `copy_identity`):

| Target branch (PR) | Added vs main | Files byte-identical to another branch | Share |
|---|---:|---|---:|
| `integration/convergence-001` (#30) | 813 | **654 identical to `research/horizon-001`** (80.4 %) + 67 to `foundation/atlas-001` | 80.4 % |
| `research/s031-hiring-capability-study` (#22) | 592 | 560 identical to `research/innovation-signals-observatory` (94.6 %) | 94.6 % |
| `research/innovation-signals-observatory` (#21) | 560 | 247 identical to `research/overnight-qlora-s030` (44.1 %) | 44.1 % |
| `research/s029-evidence-based-relations` (#16) | 339 | 134 identical to #14 (39.5 %) | 39.5 % |
| `research/horizon-001` (#29) | 691 | 654 identical to #30 (94.6 %) — reciprocal pair | 94.6 % |
| `research/phoenix-002-h8-validation` (#25) | 225 | 166 identical to round-2 (73.8 %) — **but round-2 is its ancestor** | expected |
| `feat/medradar-2.0-mvp` (#12) | 53 | 43 identical to #13–#16/#21/#22 (81.1 %) — **descendants** | expected |

[FACT] `foundation/atlas-001` **is** an ancestor of `integration/convergence-001`; `research/horizon-001` **is not** (`ancestry_extra.py`). **Therefore #30's horizon content is copied, while its atlas content is inherited.** [INFERENCE] merging #29 and #30 as-is duplicates 654 files / ~2.5 MB of tree. The Lead's independent count was 651/813 (80.1 %); my count is 654/813 (80.4 %); the 3-file delta is a counting convention on files present in both but modified in one — both agree the duplication is genuine and large.

### 14.11 Data-rights flags found in branch-only material

These are **not** my authoritative judgement; they are committed declarations a data-governance auditor must reconcile. [FACT: file existence and headline claims]

| Flag | Where | What it says | Implication |
|---|---|---|---|
| Restricted payload reachable from a public branch | `origin/integration/convergence-001:docs/convergence/LICENCE_AND_SECURITY_REVIEW.md:12-22` | UN Comtrade is redistribution-blocked (608 of 6,492 records); "the restricted payload **is** on PR #29's public branch: 30 paths, 29 distinct blobs, 6,234,301 B, commit `18a7580`" | Potential licence violation already pushed to a public remote — **escalate before any merge** |
| PII in vendored snapshots | same doc | "248 distinct UK procurement contacts" (name + work email/phone) in published source snapshots | Redaction required; relates to `sources/procurement_us` on `main` too |
| Per-source licence register | `origin/research/data-expansion-001:research/data_expansion/LICENCE_AND_COST_AUDIT.md:1-30` | 16 redistribute-allowed / 13 partial / 2 CC0 / 3 unknown / 4 paid-only; "free ≠ redistributable" | Adopt as the repo-wide schema |
| No third-party code copied | `origin/research/phoenix-001-round2:docs/PHOENIX_LICENSE_AUDIT.md:1-20` | SciTrends has **no licence** → method-only; Lens/PTNS study-only | Fine, but must stay documented |
| 51-source access/licence posture | `origin/research/horizon-001:research/horizon/GLOBAL_SOURCE_DEEP_AUDIT.md:1-20` | 24 `OPEN_DOCUMENTED`, 8 `BLOCKED_TECHNICAL`, 2 `BLOCKED_LEGAL`, 2 `REQUIRES_LICENCE` | Feeds the licence register |

[RECOMMENDATION] The convergence branch's own licence audit says the restricted blob set is reachable from **`origin/research/horizon-001` (PR #29)** — which is a *pushed, public* remote. This is the highest-severity item in my inventory and belongs to `DATA_GOVERNANCE_AUDIT`, not to a merge decision.

---

## 15. Cross-cutting inventory findings

### 15.1 Duplication is structural, not incidental

[FACT] 654 files are byte-identical between #29 and #30; 560 between #21 and #22; 133–134 product-stack files appear identically in #15/#16/#21/#22. [INFERENCE] contributors branched from each other and committed the inherited tree, so every "study" diff against `main` is dominated by other people's code. **This is the root cause of the 2.8 M added-line figure** — it is largely re-counted duplicates, not new work.

### 15.2 Documentation is not a reliable description of state

[FACT] `README.md` exists in **7 distinct blobs** across `main` + 20 open-PR heads; `pyproject.toml` in **5**; `CHANGELOG.md` in **3** (`_evidence/inventory/blob_variants_check.py`). [FACT] The Lead's earlier figure (README in 2 blobs, pyproject in 3) is **not reproducible** by my ref set; I report the recomputed 7/5/3 with the exact ref list. [INFERENCE] whichever branch merges last wins the root docs; there is no single source of project identity.

### 15.3 Version truth is broken in three places

`pyproject.toml:3` = `0.5.0`; `medradar/__init__.py:21` = `0.5.0`; README says "stable core through v0.2.2 / v0.3.0 consolidates"; ROADMAP says "Shipped in v0.3.0 (2026-10-31)"; CHANGELOG's latest is `[0.5.0] — 2026-11-02`. [INFERENCE] the only consistent pair is code (`0.5.0`); all prose is stale by at least two minor versions.

### 15.4 Local work that exists nowhere on a remote

[FACT] Measured with `git log --not --remotes`:

| Local branch | Ahead of `main` | Behind its remote twin | Commits on **no** remote | Meaning |
|---|---:|---:|---:|---|
| `research/phoenix-001-external-methods` | **33** | **16** (twin `origin/…` = `bd2f839`) | **7** | **diverged**, not just ahead: local and remote share only `main`; `merge-base` = `b2a14c0` |
| `research/forecast-registry` | 2 | n/a (no twin) | 2 | truly local |
| `research/temporal-knowledge-graph` | 2 | n/a | 2 | truly local |
| `phase3/registry-cycle` | 1 | n/a | 1 | truly local |
| `integration/audit-dryrun` | 1 | n/a | 1 | truly local |

[FACT] `_FACTS.md:189-195` calls the 33 "commits not on any remote"; that label is imprecise — **33 is the divergence from its remote twin, while exactly 7 commits are on no remote at all** (26 are already in `origin/research/phoenix-001-round2`). Both numbers are true under different definitions; the Lead's brief repeats the 33. [RECOMMENDATION] before any cleanup, create a preservation branch/archive for the 7 unique commits and reconcile the 16-commit remote twin.

### 15.5 Remote branches with no PR

[FACT] `remote_branches_without_pr = [integration/phase4-base, research/cycle2-coverage-power, research/early-signal-ai-review, research/full-history-v1]`:

- `integration/phase4-base` — 39 ahead, 472-file tree, the hidden base of #21 (§14.3).
- `research/early-signal-ai-review` — **11 ahead, 85 new files, no PR**: a substantive unreviewed line of work (hist_v1/v2, b099–b105). [INFERENCE] it supersedes `research/full-history-v1` (verified ancestor relationship).
- `research/full-history-v1` — 1 ahead, contained in `early-signal-ai-review`.
- `research/cycle2-coverage-power` — 0 ahead (fully merged content), no PR record; historical.

### 15.6 Structural hazards for refoundation

| Hazard | Evidence | Severity |
|---|---|---|
| 2.8 M unmerged lines, 19 drafts, no reviews | `_FACTS.md:68-73`, `pull_request_summary` | High |
| Studies physically depend on unmerged product code | ancestry matrix §14.3 | High |
| **S-028 tip is an ancestor of `phase4-base`, #21 and #22** — a study branch became the base of a product lane | `merge-base --is-ancestor`; `rev-list --count s028 ^phase4-base` = 0 | **High** |
| 654-file copy duplication between #29/#30 | §14.10 | High |
| Restricted Comtrade payload on a public branch | §14.11 | **Critical (legal)** |
| 7 README / 5 pyproject variants | §15.2 | Medium |
| Four competing `research/` state files | §6.1 | Medium |
| `main` CI health unverified | `_FACTS.md:240-241` | Medium |
| 3.35 MB generated HTML committed | §12 | Low/Medium |
| 88 MB repo for 29 MB tree (history bloat) | `_FACTS.md:44` | Low |

---

## 16. Reproducible command appendix

All commands run from `<REDACTED_LOCAL_PATH> Read-only; nothing fetches, checks out, or writes to git.

```bash
# A. Main footprint (what this document's tables are built from)
git ls-tree -r -l origin/main | wc -l                      # 1135
git ls-tree -r -l origin/main | awk '{s+=$4} END{print s}' # 30474497
python docs/refoundation/_evidence/inventory/metrics.py    # per-root files/bytes/LOC
python docs/refoundation/_evidence/inventory/dirs_inventory.py

# B. Module inventory / purposes
python docs/refoundation/_evidence/inventory/read_heads.py medradar/analyze.py medradar/report.py
git show origin/main:medradar/__main__.py | grep -n "add_parser"
git show origin/main:medradar/__main__.py | grep -n "^def cmd_"

# C. Test baseline (no cache / no byte-code written)
python -B -m pytest -p no:cacheprovider -q                                  # exit 0
python -B -m pytest -p no:cacheprovider --collect-only -q | tail -1        # 1074

# D. Branch divergence and PR stack
python docs/refoundation/_evidence/inventory/collect_inventory.py          # rebuilds inventory_facts.json
python docs/refoundation/_evidence/inventory/summarize_inventory.py prs branches local
git rev-list --left-right --count origin/main...origin/research/horizon-001

# E. Ancestry vs diff similarity (the hidden-stack test)
git merge-base --is-ancestor origin/feat/observatory-reliability-v1 origin/integration/phase4-base; echo $?
python docs/refoundation/_evidence/inventory/ancestry_extra.py
python docs/refoundation/_evidence/inventory/verify_ancestry.py            # writes ancestry_verify.json

# F. Merge probes (read-only; does not touch the index)
git merge-tree --write-tree origin/main origin/feat/frontier-device-radar   # exit 1 = conflicts
git merge-tree --write-tree origin/main origin/research/horizon-001         # exit 0 = clean

# G. Copy-paste volume
python docs/refoundation/_evidence/inventory/summarize_ancestry.py

# H. Doc/version drift
python docs/refoundation/_evidence/inventory/blob_variants_check.py

# I. Local-only commit accounting (two different definitions — report both)
git rev-list --count origin/research/phoenix-001-external-methods..research/phoenix-001-external-methods  # 33
git log --oneline research/phoenix-001-external-methods --not --remotes | wc -l                           # 7
git merge-base research/phoenix-001-external-methods origin/research/phoenix-001-external-methods        # b2a14c0
```

**Scripts written for this audit** (all under `_evidence/inventory/`, all read-only): `collect_inventory.py`, `summarize_inventory.py`, `summarize_more.py`, `dirs_inventory.py`, `metrics.py`, `read_heads.py`, `probe_state.py`, `probe_deps.py`, `verify_ancestry.py`, `summarize_ancestry.py`, `ancestry_extra.py`, `branch_families.py`, `blob_variants_check.py`, `probe_facts.py`.

---

## 17. Open questions for the owner

1. **What is the intended product?** `main` ships an FDA/device intelligence + simulated-trading tool (`README`, `ROADMAP`, CLI), while `research/MISSION.md` declares "Global MedTech Intelligence & Foresight — Observe/Understand/Anticipate" and the unmerged branches build a product web app + observatory. Which is the refoundation target?
2. **Which product stack owns `medradar/`?** #12–#14 add `medradar/product/`, `observatory/`, `web/`; #28 adds `medradar/atlas/`; #30 adds `medradar/integration/`. Do these become top-level packages, or is `medradar/` frozen at `main` and new code lives elsewhere?
3. **Is the duplicate horizon tree in #30 intentional?** 654 identical files; should #30 be rebased to drop them and depend on #29?
4. **What is the fate of `research/` state files?** Which of `STATE.json` / `AUDIT.json` / `FINAL_AUDIT.json` / `BACKLOG.yaml` is authoritative, and should the other three be archived read-only?
5. **What should happen to the 3.35 MB committed `docs/dashboard.html` and 1 MB `replay.html`?** Keep as Pages artifact (history cost) or generate in CI and stop tracking?
6. **Yahoo Finance price data:** is redistributing derived CSVs/JSON in `docs/` acceptable under Yahoo's terms? This affects `paper`, `live`, `eventstudy`, `replay`, `docs/summary.csv`.
7. **LLM judge:** is `MEDRADAR_LLM_API_KEY`-based judging in scope for the refoundation, and is sending 8-K text to a third-party API acceptable?
8. **Which branch-only family is funded?** PHOENIX/ATLAS/HORIZON/CONVERGENCE/S-028/S-029/S-031/data-expansion/local-LLM are mutually independent; inventory alone cannot rank them. The PR audit gives a merge-order recommendation, but priority is an owner decision.
9. **The 7 unique local PHOENIX commits:** who owns them, and can they be pushed to a preservation branch before cleanup?
10. **Issue tracking is unused (0 issues).** Should the refoundation keep the GitHub-native workflow, or is an external tracker assumed?
