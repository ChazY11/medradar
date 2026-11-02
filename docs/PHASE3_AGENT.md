# Phase 3C — evidence-grounded research agent

`medradar/research_agent.py` is a deterministic, multi-step research workflow for
the Market-to-R&D layer. It is **not** a chatbot: it contains no model calls, no
network access and no free-text generation path. Every factual claim in its output
is traceable to a stored row, a registered forecast or a frozen artifact id, and
the only probabilities it reports are ones produced by the trained model or the
canonical registry.

Real-run artifact: [`experiments/reverse_rd_v2/agent_demo.json`](../experiments/reverse_rd_v2/agent_demo.json)
(5 questions, 55 claims, 224 unique cited ids, 314 citation checks, 0 missing).

## What it does

For one question (company, track, template, as-of date) the agent runs a fixed
plan:

```
question template → plan (ordered tools) → retrieval → evidence table →
conflict detection → hypothesis (labelled "not a causal finding") →
counter-evidence → statistical validation → cited synthesis → uncertainty →
research log → explicit stop condition + failure reporting
```

The output is one JSON document (`{question, template, as_of, plan, steps,
evidence, conflicts, hypothesis, counter_evidence, statistical_validation,
template_focus, uncertainty, synthesis, citations, limitations, log,
stop_condition, degraded, failures}`) plus a Markdown renderer.

## Tool contracts

Every tool is a plain function returning a structured, cited dict; all database
reads open the research database **read-only** (`sqlite3` URI `mode=ro`). No tool
writes, migrates or creates a database.

| Tool | What it returns | Point-in-time rule | Citation kind |
|---|---|---|---|
| `forecast_evidence(registry_path, company, track, as_of=None)` | registered canonical forecasts: `prediction_id`, `p`, `record_kind`, horizon, window, `information_cutoff`, `model_version`, `feature_version`, evidence locator/hash, status, resolutions; explicit `no_registry` / `registry_missing` / `registry_unreadable` / `no_registered_forecast` outcomes | a forecast is `visible_at_as_of` only when its server-assigned `generated_at` is at or before the as-of moment (day resolution for date-only as-of) | `registry_forecast` |
| `event_history(db, company, track, as_of)` | material 510(k)/PMA counts, first/last event, months since last event, dormancy flag, per-year counts, timestamp-quality mix, event ids | `event_date <= as_of` **and** `available_at <= as_of` (date level); material rules identical to v1 (any 510(k); PMA original/panel-track only) | `event` |
| `financial_context(db, company, as_of)` | the eleven consolidated SEC features, latest annual R&D and revenue facts with period end and filed date | `available_at <= as_of` and `period_end <= as_of`; annual flow facts must span 300–450 days | `financial_fact` |
| `market_context(db, company, as_of)` | 12m return/volatility/drawdown, SPY/XBI relative returns, volume z, SPY-above-200d regime, days since 12m high; ticker and last bar date | bars dated at or before the as-of calendar day only (a daily close is known at its own day end) | `market_bar` |
| `publication_context(db, company, as_of)` | complete-year OpenAlex counts, 3-year total, prior-year growth and intensity, knowledge date | a year `y` is usable only when `date(y+1, 2, 15) <= as_of`; the current calendar year is never used | `publication_count` |
| `graph_context(tkg_path, company, track, as_of)` | optional TKG nodes/edges mentioning the company or track | `recorded_at <= as_of` moment | `tkg_assertion` |
| `counter_evidence(db, company, track, as_of)` | four alternative explanations: track activity by other companies, company activity in other tracks, SPY/XBI regime, peer revenue-growth median | same PIT rules as the underlying tables | mixed |
| `baseline_comparison(db, company, track, as_of, target=...)` | purged per-pair base rate (continuation or entry dataset), global base rate, and the model/registry probability with a delta and a cautious interpretation | matured label window only: `cutoff + 12m <= as_of`; probability visibility as in `forecast_evidence` | `example`, plus the probability's own citation |

**Soft dependency.** The sibling Phase-3 task owns
`medradar/intelligence/graph_context.py`. It is imported lazily *inside*
`graph_context`, never at module import time. If it is absent the tool falls back
to a read-only raw query over the TKG schema when a TKG file is supplied;
otherwise it returns `unavailable` / `not_requested` and the workflow records the
gap. The agent never fabricates graph edges.

## Templates

| Template | Question shape | Target dataset used for the base rate |
|---|---|---|
| `entry_forecast` | will an active company register a first material event in a dormant track? | `first_entry_v1` (dormancy 36 months) |
| `market_leading_indicator` | does point-in-time market evidence add information beyond R&D history? | `reverse_rd_v1` continuation |
| `early_signal` | is there early multi-source evidence that a track is becoming active? | continuation |
| `strategic_shift` | is a company's observed activity mix shifting toward a track? | continuation |
| `cross_source_validation` | do independent sources agree or conflict for a pair? | continuation |

Each template has a fixed ordered tool plan (recorded verbatim in
`document["plan"]`) and a template-specific `template_focus` block:
`dormancy`, `market_vs_rd_history`, `signal_density`, `track_shift` or
`source_agreement`. The base rate is computed only from **matured** examples whose
label window closed at or before the as-of date; no example is used before its
label could be known.

## Conflict detection

Conflicts are reported, never "resolved" by the agent. The rules are fixed and
deterministic:

| Rule | Trigger |
|---|---|
| `model_high_vs_base_rate_low` | model/registry `p >= 0.75` and `p - pair base rate >= 0.15` |
| `registry_vs_frozen_artifact_mismatch` | a visible registry probability and a visible frozen model probability for the same pair differ by more than 0.05 |
| `market_positive_vs_fundamentals_negative` | 12m market return > 0 while consolidated revenue and/or R&D growth < 0 |
| `market_positive_vs_publication_negative` | 12m market return > 0 while complete-year publication growth < 0 |
| `track_activity_vs_company_dormancy` | ≥ 10 other-company events in the track in the trailing 12 months while the pair has been dormant for 36 months |

Each conflict carries the claim ids and citations of both sides.

## Citation, probability and uncertainty rules

- A claim whose `evidence_status` is `observed` or `derived` **must** carry at
  least one citation to an id that exists in the database or registry; the demo
  script and the test suite verify the ids by querying them. `not_available`,
  `unavailable` and `insufficient` claims state what is missing instead.
- Probabilities come only from (a) canonical-registry rows, or (b) frozen
  `horizon_forecasts` rows for the continuation target. A missing probability is
  `null` with an explicit reason; it is never estimated by the agent.
- The uncertainty block records the model's temporal-ensemble spread when it is
  stored (and states that it is not a causal confidence interval), the data-quality
  flags (event availability is decision date + 14 days; financial facts are
  consolidated; market knowledge time is the trading date; publications are
  annual with a 15-February knowledge lag), and the missing sources (patents —
  no USPTO key; hiring — not collected; market cap/valuation — no shares data;
  canonical registry/TKG when absent).
- The hypothesis is always labelled `"hypothesis, not a causal finding"` and has
  an explicit falsification condition.
- The stop condition is explicit: the fixed plan is exhausted; remaining
  uncertainty needs sources that do not exist in this environment. Failed tool
  steps are listed in `failures` and `degraded` is set.

## CLI

```bash
# list templates
python -m medradar.research_agent --list-templates

# one question (JSON document)
python -m medradar.research_agent ask \
  --company medtronic --track spine --template market_leading_indicator \
  --as-of 2026-11-02 --db data/research.sqlite

# Markdown rendering, written to a file
python -m medradar.research_agent ask \
  --company alcon --track ophthalmology --template cross_source_validation \
  --as-of 2026-11-02 --db data/research.sqlite --format markdown --out agent.md
```

`--registry` defaults to `data/registry.sqlite` when that file exists, `--tkg` is
optional, and `--as-of` defaults to the latest stored example cutoff. The
canonical registry is produced by a sibling Phase-3 task; in this checkout it is
absent, so registry-backed claims report `no_registry` and the documents are
marked degraded.

## Reproduce the real demo

```bash
# requires the research DB + canonical registry + TKG store (see docs/PHASE3.md §Reproduce)
python scripts/run_agent_demo.py --db data/research.sqlite --registry data/registry.sqlite \
  --tkg data/tkg.sqlite --out experiments/reverse_rd_v2/agent_demo.json --as-of 2026-11-02
# writes the artifact and prints a compact summary
```

The script opens `data/research.sqlite` read-only, runs the five real questions
below at a fixed `as-of` of 2026-11-02, verifies **every** citation against the
database/registry, and exits non-zero if any id is missing.

## Real demo results (from the committed artifact, integrated run)

Five questions, 55 claims, 224 unique cited ids, 314 citation checks, **0 missing
citations**; 3 genuine cross-source conflicts; `degraded_questions = 0`. The
canonical registry and the bitemporal TKG are both reported `present`, and the
citation kinds include `registry_forecast` alongside events, financial facts,
market bars, publications and forecast examples. (An earlier run without those two
stores marked every question degraded and is superseded.)

| # | Template | Question | Candidates | Citations | Conflict |
|---|---|---|---|---|---|
| 1 | `entry_forecast` | intuitive_surgical → imaging_mr_ct | 1 material event ever (2019-02-22), 0 in trailing 12m | 58 | `track_activity_vs_company_dormancy` |
| 2 | `market_leading_indicator` | medtronic / spine | 62 material events (last 2026-07-17), 6 in trailing 12m | 68 | `market_positive_vs_publication_negative` |
| 3 | `early_signal` | boston_scientific / ep_pfa | 6 material events (last 2024-02-26), 0 in trailing 12m | 62 | none |
| 4 | `strategic_shift` | medtronic / ep_pfa | 13 material events (last 2024-10-24), 0 in trailing 12m | 69 | `market_positive_vs_publication_negative` |
| 5 | `cross_source_validation` | alcon / ophthalmology | 34 material events (last 2026-02-13), 1 in trailing 12m | 57 | none |

These are **evidence narrations at a retrospective as-of date**, not accuracy
claims. Model/registry probabilities are quoted from the stored rows; the agent did
not produce them and does not claim they are correct. Three of the five questions
were selected because the resulting evidence genuinely conflicts (entries 1, 2 and
4), which is the point of the conflict block.

## Integrated demo update (2026-11-02, v0.5.0)

The committed artifact was regenerated **after** the canonical registry (25 registered
nowcasts) and the real TKG store (57,381 nodes / 114,419 edges) existed, using the command
above. Re-running it reproduces the documents byte-for-byte except timestamps. The `.sqlite`
stores are gitignored, so a fresh checkout needs the Phase-3 reproduce steps in
[PHASE3.md](PHASE3.md) first.


## What is NOT claimed

- No causal inference: a market signal is not evidence that the market directs
  R&D, and a regulatory milestone is a lagging R&D proxy.
- No LLM judge, no chatbot, no generated narrative: the synthesis is assembled
  from evidence-table entries; an LLM hook does not exist in this module.
- No fabricated probabilities: a missing probability is null.
- No prospective accuracy claim: the demo is retrospective narration at a fixed
  as-of; forecast verification requires the registry's prospective resolutions.
- No graph or patent evidence is invented when those sources are absent.

## Limitations

- The canonical forecast registry and the TKG are sibling Phase-3 artifacts and
  are absent in this checkout; registry-backed claims are therefore all
  `no_registry`. The agent tolerates this but cannot demonstrate the registry
  path on real data here (the synthetic tests do).
- Only the frozen `horizon_forecasts` rows (25 continuation forecasts created
  2026-11-01) can supply a real probability, and only for the continuation
  target; the entry target has no stored model probability at all.
- Event availability is decision date + 14 days (`estimated`), the product-code
  → track mapping is the current curated version, and company resolution is the
  curated registry — all inherited limitations of the underlying data.
- Market data is an offline Yahoo Finance daily import (trading-date knowledge
  time, survivorship bias); publications are annual OpenAlex counts with a
  conservative 15-February knowledge lag.
- Patents and hiring are not implemented at all; the documents list them as
  missing sources.
- The conflict rules are hand-written heuristics with fixed thresholds; they flag
  disagreement but do not quantify it.

## Offline tests

`tests/test_research_agent.py` builds a synthetic research database and registry
and covers: every template runs and emits the required document; every
observed/derived claim has a citation that exists in the DB/registry; conflict
rules fire on a constructed conflict; empty registry degrades honestly; output is
deterministic excluding log timestamps; point-in-time filtering of events, market
bars and forecasts; graph-context soft-dependency states; unknown pairs degrade
without crashing; no network/LLM imports (source scan plus a patched socket); and
the CLI (`--list-templates`, `ask` JSON/Markdown).
