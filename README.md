# MedRadar

[![Built with DeepSeek Harness · deepseek-flash](https://img.shields.io/badge/built%20with-DeepSeek%20Harness%20%C2%B7%20deepseek--flash-4D6BFE)](https://github.com/ChazY11/medradar/blob/main/docs/ATTRIBUTION.md)


**An open-source radar for FDA device & drug industry direction — built for people who need to know
what US majors are actually building next, not what they said in an earnings call.**

MedRadar turns free public FDA data into a weekly, quantified, Chinese-language intelligence
brief: which technology tracks are heating up, which majors are quietly re-allocating their
portfolio, what appeared for the first time, and where China still has a gap.

> **Built entirely with DeepSeek Harness using Chinese domestic models (`deepseek-flash`).**
> Every line of code, every data pull and every commit in this repository was produced by the
> DeepSeek Harness agent team (1 Lead + 8 specialist agents) — no other model was used.
> Details: [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md).

> 中文文档 → [README.zh-CN.md](README.zh-CN.md) · Methodology → [docs/METHODS.md](docs/METHODS.md)

![MedRadar dashboard](docs/preview.png)

### What one run produces (snapshot, 2026‑10‑31)

| | |
|---|---|
| Events ingested | **375,378** (510(k) 176,466 · PMA 57,372 · recalls 59,646 · trials 55,592 · drug approvals 5,326 · EDGAR catalysts 20,976) |
| Coverage | 89 companies, 60 tracks, **204 device product families**, 7,097 product codes, **1.2 GiB SQLite** |
| Strongest track right now | 心脏节律 THI 1.94 (P=98.2%) · 可穿戴监测 1.80 · 结构性心脏病 1.57 · 手术机器人 1.54 |
| Signals emitted | 281 (→ tradable subset) |
| Case library | **2,384 traceable cases** (verbatim evidence + 1/5/20/60-day reactions): 943 approvals · 379 CRLs · 1,062 trial readouts, 3,700+ evidence quotes |
| Replay | **400-step, 7-year timeline** (2019–2026) with 10/25/50 bps cost tiers; 1-minute fills for the last 7 days |
| Event study (20d, direction-aligned, winsorised, **Holm over the 12-test family**) | approval +2.8% (CI 0.9–4.8, **Holm p=0.007 → significant**) · CRL −3.8% (CI −6.7–−0.8, Holm p=0.060 → borderline, not significant) · trial −0.3% (n.s.) |
| Simulated book | in-sample, long-only, not investment advice |
| Tests | **440 offline tests**, no network, no API key |
| Report | 19 chapters, self-contained HTML dashboard (no CDN, no external assets) |
| Products | 204 families, **2,740 Chinese product names** |
| Research | event-time model, point-in-time signals, block bootstrap, Holm correction |
| Timing scope | **all 375k events are date-level** (`timestamp_quality=date`); minute-level timing exists only for the live EDGAR lane / last-7-day replay, so minute-level studies are explicitly out of scope |
| Database | 1.2 GiB SQLite, 1966–2026 drug approvals, 1999–2026 trials |
| Calibration | 25 hand-labelled real 8‑Ks: type accuracy **1.00 vs 0.60**, direction **0.92 vs 0.72** for the LLM judge |

> Numbers move every week; every one of them is reproducible from `medradar run`.

---

## Try it in 60 seconds

```bash
# 1) clone the repository (or download the Release ZIP) and enter its root
# 2) install and run the offline demo
pip install -e .
medradar demo           # offline, uses the committed snapshot, no API key, <60s
# open out/demo/index.html (interactive dashboard: out/demo/dashboard.html)
```

Or open the **interactive dashboard** directly: [`docs/dashboard.html`](docs/dashboard.html) — 7 views
(overview, tracks, companies, products, cases, replay, data), live search, sortable tables,
case-evidence drawer, replay cost-tier switch and URL routing. It is a single self-contained HTML
file (3.3 MB, zero external requests), so it also works offline and on GitHub Pages.

Then, for a live data run:

```bash
medradar run --months 24 --with-trade    # ~3 min, free public data only
medradar replay --days 30                # event-to-fill timeline with cost tiers
medradar replay --start 2019-01-01 --end 2026-10-31 --source events   # 7-year, 400 steps
medradar cases --limit 20                # traceable case library with evidence quotes
medradar products --limit 10             # product families + new-product radar, in Chinese
medradar dashboard                       # rebuild docs/dashboard.html from the latest metrics
```

## What it answers

| Question | Metric | Output |
|---|---|---|
| Which device tracks are accelerating? | `THI` — shrinkage-adjusted recent rate ÷ baseline rate | Track heat table |
| Is a specific major changing direction? | Jensen-Shannon divergence of its product-code mix | Migration table ("who is re-allocating") |
| What is genuinely new? | First-ever `(company, product_code)` occurrences | "First seen" weekly list + product-family radar |
| Which device product families are rising? | 204 families, 2,000 Chinese product names | Product radar chapter |
| Is pharma shifting therapeutic focus? | Trial-start rates + phase mix per area | Drug radar |
| Where is the China gap? | US activity share vs loaded NMPA registrations | `cn_gap` table (honest `unavailable` when no CN data) |
| Does any of it predict equity returns? | Event study: direction-aligned abnormal returns at +1/+5/+20/+60, block bootstrap + Holm | [Case library](docs/CASES.md) + `out/trading.json` (simulation only) |

## Live lane: event alerts + simulated trading (5–15 min)

The batch radar answers *"what is the industry doing"*. The live lane answers *"what just happened"*.

```bash
python -m medradar live --once --since-hours 2              # one cycle (cron / DSH automation)
python -m medradar live --interval 600                      # loop every 10 minutes
python -m medradar live --once --backfill-days 7 --no-trade # seed recent catalysts (never traded)
python -m medradar live --reset                             # wipe the simulated book
```

Each cycle: SEC EDGAR 8-K feed (seconds) → EDGAR full-text backfill → FDA press RSS →
ClinicalTrials.gov status changes → keyword classifier → **simulated order at the latest real
Yahoo quote plus 10 bps slippage** → mark-to-market → alert (console + `out/live_alerts.jsonl` +
optional `MEDRADAR_WEBHOOK_URL`).

Honest latency, measured 2026‑10‑31:

| Source | Latency | Tradable? |
|---|---|---|
| SEC 8-K filings | seconds | ✅ |
| FDA press RSS | ~8 days stale at the time of writing | ❌ informational |
| ClinicalTrials.gov updates | hours | terminations only |
| openFDA 510(k)/PMA | 12 days | ❌ slow lane only |
| FDA submissions under review | **not public** | physically impossible |

Long-only, ≤5% per name, ≤25% per track, −20% stop, 60‑trading‑day exit. Shorts are **alerted but
not traded**: borrow fees and squeeze-outs would turn the P&L into fiction. This is a simulation —
no broker, no orders, no money at risk.

**Execution guards** (added after a pre‑release review):

* only the fresh EDGAR feed can open a position — backfill, FDA RSS and trial updates are alert‑only;
* a quote older than 30 minutes may mark the book but never fills an order;
* position size is computed on the *slipped fill price*, so cash cannot go negative;
* `--no-trade` freezes exits as well as entries;
* duplicate alerts for the same `(ticker, day, kind)` are collapsed across sources.

**Timing honesty**: `signal_date = event_date + 1`, and the fill is the open of the next trading day —
roughly **two trading days after the event**. Conservative, not same‑day. Alerts whose public
timestamp is only date‑level are excluded from the trading study.

### LLM judgement of the filing text (decides position size)

A keyword classifier can say "positive". It cannot tell a first‑in‑class approval from a label
tweak — and that difference is exactly what should scale a position from 1% to 5%. So the live lane
sends the 8‑K text to an LLM and asks for a **structured, evidence‑quoted verdict**:

```json
{"direction": 1, "materiality": 0.82, "confidence": 0.9, "catalyst_type": "approval",
 "asset": "Keytruda", "indication": "first-line NSCLC", "is_pivotal": true,
 "revenue_relevance": "high", "evidence_quotes": ["..."], "rationale_zh": "..."}
```

* **Provider-agnostic**: any OpenAI-compatible endpoint.
  `MEDRADAR_LLM_BASE_URL` (default `https://api.deepseek.com`), `MEDRADAR_LLM_API_KEY`,
  `MEDRADAR_LLM_MODEL` (default `deepseek-chat`).
* **Cached** by content hash — the same filing never costs tokens twice.
* **Budgeted** — `--llm-budget 4` calls per cycle; over budget it falls back to the keyword judge.
* **Evidence-first** — a verdict without a verbatim quote is down-weighted to half confidence.
* **Sizing** — `position = 5% × clamp(materiality, 20%, 100%)`, so a routine earnings 8-K gets ~1%
  and a first-in-class approval gets the full 5%.

```bash
# without a key it uses the deterministic fallback and says so ("judge": "heuristic(no-llm-key)")
python -m medradar judge --file filing.txt --headline "Company 8-K"

# with a key
export MEDRADAR_LLM_API_KEY=sk-...
python -m medradar judge --url https://www.sec.gov/Archives/... --headline "Company 8-K"
```

Calibrated on **25 hand-labelled real 8‑Ks** (approvals / CRLs / trial readouts / earnings) —
full report in [docs/CALIBRATION.md](docs/CALIBRATION.md):

| metric | LLM judge | keyword baseline |
|---|---|---|
| catalyst_type accuracy | **1.00** | 0.60 |
| direction accuracy | **0.92** | 0.72 |
| materiality Spearman ρ | **0.80** | 0.58 |
| high-materiality F1 (≥0.5) | **0.94** | 0.67 |
| buys a CRL (should short) | **0** | 2 of 5 |

The baseline labels 4/9 trial readouts and 5/5 earnings as "approval" — and `earnings` is the
"do not trade" switch, so that error matters. Materiality runs ~+0.15 high versus human labels;
use it for ranking, or shrink by 0.85 before sizing.

## Quickstart

```bash
# from the repository root (clone it or unpack the Release ZIP first)
# no API key, no dependencies beyond Python 3.10+

medradar demo                 # 60-second offline demo (snapshot, no network)
# open out/demo/index.html

# 24 months is the quick start (~2-3 min); use --months 120 for ten years
python -m medradar run --months 24 --with-trade --with-dashboard

# outputs
#   out/index.html          (also copied to docs/index.html for GitHub Pages)
#   docs/dashboard.html     (interactive 7-view dashboard)
#   out/report_zh.md        (Chinese research report)
#   out/summary.csv         (flat metrics for Excel)
```

Everything is resumable: every HTTP response is cached under `data/cache/`, every stage can be
re-run on its own.

```bash
python -m medradar collect --sources device,drug,trials --months 120
python -m medradar analyze --window-quarters 8 --baseline-quarters 20
python -m medradar report
python -m medradar trade --capital 100000
python -m medradar status
python -m medradar selftest        # offline, no network
```

## Data sources (all free, no credentials)

| Source | Content | Freshness (measured 2026‑10‑31) |
|---|---|---|
| openFDA `device/510k` | 510(k) clearances, 176k records | updated 2026‑10‑19 (T−12d) |
| openFDA `device/pma` | PMA & supplements, 57k | T−12d |
| openFDA `device/recall` | device recalls, 60k | T−2d |
| openFDA `device/classification` | ~6.5k product codes → regulated definitions | static |
| openFDA `drug/drugsfda` | NDA/BLA/ANDA review & approvals, 29k | T−2d |
| ClinicalTrials.gov API v2 | trial registrations (drug **and** device) | posted ≤21 days after enrollment starts |
| SEC EDGAR full-text search | 8-K / CRL event stream (optional) | near real time |

**NMPA (China) is deliberately not scraped.** `www.nmpa.gov.cn` answers HTTP 412 and `www.cmde.org.cn`
HTTP 202 behind a JavaScript WAF. MedRadar ships an honest adapter instead: drop a CSV export at
`data/nmpa_registrations.csv` and the China-gap table lights up; without it every CN value is `null`
and the report says *"不可用（NMPA 数据未加载）"*. It never fabricates a zero.

## How the numbers are computed (short version)

* **Shrinkage first.** A company with 2 clearances this quarter has an infinite growth rate and no
  information. Every rate is a Gamma–Poisson posterior with the entity's own baseline as prior
  (strength: 3 quarters). `THI = posterior mean ÷ baseline rate`; `prob_up` is the posterior
  probability that the true rate beats the baseline.
* **Direction = mix, not volume.** A company can clear fewer devices while decisively moving into a
  new category. We measure the product-code mix shift with Jensen–Shannon divergence and report the
  tracks that moved ≥8 percentage points.
* **Novelty = first occurrence.** A new `product_code` for a given company is the earliest visible
  trace of a new product line.
* **Signals carry an explicit `signal_date`** (event date + 1 day) so the trading study cannot peek
  at the future.

Full definitions, assumptions and threats to validity: [docs/METHODS.md](docs/METHODS.md).

## Research-grade guarantees

| Guarantee | How it is enforced |
|---|---|
| **No lookahead** | every event carries `available_at` + `timestamp_quality`; backtests only read `available_at`, and `unknown` timestamps never trade |
| **Point-in-time features** | the "is this new?" test and the track-popularity boost use only history published before the event |
| **Honest latency** | EDGAR seconds, FDA RSS days, openFDA 12 days — each source is labelled with what it can actually support |
| **Cost sensitivity** | replay reports 10 / 25 / 50 bps tiers instead of a single flattering number |
| **Multiple testing** | track claims are Holm-corrected; sample splits (dev / validation / holdout) are reported |
| **Survivorship** | tickers without price coverage are flagged, not silently dropped |
| **Reproducible calibration** | `medradar.calibration` replays recorded LLM responses by content fingerprint; drift makes the score script fail |
| **Assumption registry** | every modelling assumption is listed with status in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) |

## Simulated US-equity study (not investment advice)

`medradar trade` runs a **paper** portfolio on the generated signals: next-open entry, 60-day hold,
−20% stop, ≤5% per name, ≤25% per track, 20 bps + \$1 per fill, long only. It reports an event study
(abnormal return vs SPY) with t-statistics and bootstrap confidence intervals rather than a
decorative equity curve.

Deliberately **not** modelled in v1: short borrow fees, merger squeeze-outs, delisting returns.
Long-only v1 therefore overstates what a real strategy could do. The report says so on every page.

## Repository layout

```
config/         curated knowledge: parent→subsidiary aliases, Chinese track dictionary, source notes
medradar/       standard-library-only package
  util.py       dates, text normalisation, Gamma–Poisson / bootstrap / JS-divergence
  http.py       polite HTTP: rate limit, retries, response cache, offline replay
  db.py         one unified `events` table + registries + prices + signals + paper tables
  config.py     CompanyRegistry / TrackRegistry fuzzy matching
  collect_*     openFDA / ClinicalTrials.gov collectors
  nmpa.py       honest pluggable China adapter (CSV / demo / off)
  analyze.py    metrics engine → out/metrics.json (contract: docs/SCHEMA.md)
  products.py   device product families, Chinese catalog, new-product radar
  families.py   keyword-based family builder (regenerates config/product_families.json)
  replay.py     event-to-fill replay: 1m (last ~7d) or daily, 3 cost tiers, standalone HTML
  stats.py      block bootstrap, Holm/Bonferroni, time splits, survivorship, power
  calibration.py reproducible LLM-judge calibration (recorded fixtures, no key needed in CI)
  onboarding.py demo / doctor / watchlist
  report.py     Chinese report + self-contained HTML dashboard
  prices.py     Yahoo daily bars (research use)
  eventstudy.py abnormal-return study
  paper.py      simulate-only portfolio with frictions
docs/           schema contract, methodology, GitHub Pages demo
tests/          offline tests (synthetic fixtures, no network)
```

## Extending it

* **Add a company** → `config/companies_device.json` (parent key + subsidiary aliases). Measured
  impact: J&J resolves from 2 to 100+ 510(k) per two years once Ethicon/DePuy/Biosense Webster are
  listed.
* **Add a track** → `config/tracks_device.json` with Chinese name + English keywords. Product-code
  mapping is generated from openFDA classification on the next collect run.
* **Add a data source** → write `collect_<name>(db, fetcher, months, limit)` that only touches the
  `events` table. Analysis, report and trading need no changes.

## Roadmap

- [ ] NMPA CSV importer UI + province-level gap analysis
- [ ] FDA statistical-review PDF mining (trial-design red flags straight from FDA reviewers)
- [ ] SHAP-style attribution for "why did this track's THI move"
- [ ] Short-side event study once borrow-fee data is available

## License & disclaimer

MIT. Source data belongs to its publishers (openFDA is public domain; ClinicalTrials.gov and SEC
EDGAR have their own terms). Nothing here is investment advice. This is a research and
education project.
