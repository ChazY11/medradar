# Layer map — where every existing capability sits

Created 2026-11-02 as part of the strategic realignment (instruction step 2: map existing work to
Observe / Understand / Anticipate, keep what has research value, deprioritise what has drifted).

**Verdicts:** `CORE` = directly serves the layer and is on the critical path · `KEEP` = valid and
maintained but not the critical path · `DEPRIORITISED` = outside the realigned mission; maintain,
do not extend · `GAP` = required by the mission and absent.

| Capability | Module / artifact | Layer | Priority | Verdict |
|---|---|---|---|---|
| FDA 510(k)/PMA/recall collectors | `collect_device.py`, `clinical.py`, `adcom.py` | Observe | P0 | CORE |
| SEC EDGAR event corpus | `corpus.py` | Observe | P0 | CORE (16k 8-K events still CIK-unlinked) |
| SEC XBRL company facts | `intelligence/sources/sec_financials.py` | Observe | P1 | KEEP (consolidated only, never mapped to product families) |
| ClinicalTrials.gov v2 | `clinical.py` | Observe | P0 | CORE |
| Procurement (USAspending) | `intelligence/sources/procurement_us.py` | Observe | P1 | KEEP (`pit_usable=0`; descriptive only until a real snapshot history exists) |
| Market bars / prices | `prices.py`, `intelligence/sources/market_data.py` | Observe | P2 | DEPRIORITISED as a research signal (weak proxy, no product-family mapping) |
| OpenAlex publications | `intelligence/sources/publications.py` | Observe | P1 | KEEP |
| USPTO patents | `intelligence/sources/patents.py` | Observe | P1 | GAP in practice (adapter exists, no key ⇒ zero rows) |
| Hiring / job postings | — | Observe | P1 | GAP (mandated source class, not collected) |
| Entity resolution (curated) | `config/companies_device.json`, `config.py::CompanyRegistry` | Observe | P0 | KEEP (curated roster; still missing Dräger + Mindray) |
| Entity universe (deterministic) | `intelligence/universe.py`, `config/universe_v1.json` | Observe | P0 | CORE (new; 9,412 entities, no fuzzy matching) |
| Product-family / track taxonomy | `config/product_code_tracks.json`, `tracks_device.json`, `families.py`, `products.py` | Observe | P0 | CORE but **unversioned** — a known semantic-leakage channel |
| Bitemporal point-in-time store | `tkg/` | Observe + Anticipate | P0 | CORE (audited) |
| Publication-lag / PIT dataset builder | `intelligence/features/`, `tkg/export.py` | Observe + Anticipate | P0 | CORE |
| Leakage audit | `intelligence/evaluation/leakage_audit.py` | P0 across layers | P0 | CORE |
| **Technology-change detection** | `intelligence/changepoint.py` | **Observe** | **P1** | **CURRENT WORK** |
| Cross-company anomaly detection | — | Observe | P1 | GAP (next after the single-stream detector) |
| Portfolio-migration / first-entry identification | partially `features/research_features.py` (entry target) | Observe | P1 | PARTIAL (built for forecasting; not used as a detector) |
| Corporate technology knowledge graph | `tkg/`, `intelligence/graph_context.py` | Understand | P1 | PARTIAL (real-history import works; no research-grade QA) |
| Cross-source entity alignment benchmark | — | Understand | P0 | GAP (needs genuine labels; AI-created fixtures cannot count as human truth) |
| Evidence fusion / contradictory evidence | `research_agent.py` (5 conflict rules) | Understand | P1 | PARTIAL (prototype, citation-complete, not validated for research quality) |
| Company R&D profile | partial via `products.py`, `report.py` | Understand | P1 | GAP for the realigned use |
| Deterministic research agent | `research_agent.py` | Understand | P2 | KEEP (no-LLM path; LLM only for organisation) |
| Evaluation statistics (cluster bootstrap, MDE, matched-FAR lead time) | `intelligence/evalstats.py` | Anticipate + Observe | P0 | CORE (reusable for detection benchmarking) |
| Forecast registry (immutable, as-of scoring) | `forecast_registry.py`, `intelligence/forecasting/` | Anticipate (B) | P3 | KEEP (25 nowcasts, none matured) |
| Purged rolling-origin backtesting | `intelligence/evaluation/backtesting.py` | Anticipate (B) | P3 | KEEP |
| Entry/continuation benchmark | `features/research_features.py`, `experiments/reverse_rd_v*`, `experiments/cycle2_coverage/` | Anticipate (B) | P3 | KEEP (cycle-2 result recorded) |
| Event study (abnormal returns) | `eventstudy.py`, `cases.py`, `analyze.py` | outside mission | P4 | DEPRIORITISED — maintain, do not extend |
| Paper trading / live alerts | `live.py`, `paper.py` | outside mission | P4 | DEPRIORITISED — maintain only |
| HTML dashboards / replay UI | `dashboard.py`, `replay.py`, `report.py` | outside mission | P4 | DEPRIORITISED — no new pages |
| Drug lane / NMPA | `collect_drug.py`, `nmpa.py` | outside mission (device-first) | P4 | DEPRIORITISED — maintain |
| LLM verdict helper | `llm.py` | Understand (assist only) | P2 | KEEP with hard rule: never generates facts, citations or probabilities |

## What the map implies

1. **The Anticipate layer is the most mature part of the codebase**, and the mission has just moved
   it to P3. It is preserved, frozen, and continues on the entity panel — but it must not consume
   the next cycles.
2. **The Observe layer has a solid data spine but no detection capability.** That is the single
   biggest gap relative to the realigned mission, hence the current phase.
3. **The Understand layer has prototypes but no validated research-quality output**, and one P0
   blocker: there is still no benchmark for cross-source entity alignment built from genuine labels
   (audit finding: AI-created fixtures cannot stand in for human truth).
4. Outside-mission code (event study, trading, dashboards, drug lane) is **maintained but frozen**:
   no new features, no deletions, so the repository stays a working system without further drift.
