# MedRadar

**An open-source radar for FDA device & drug industry direction — built for people who need to know
what US majors are actually building next, not what they said in an earnings call.**

MedRadar turns free public FDA data into a weekly, quantified, Chinese-language intelligence
brief: which technology tracks are heating up, which majors are quietly re-allocating their
portfolio, what appeared for the first time, and where China still has a gap.

> 中文文档 → [README.zh-CN.md](README.zh-CN.md) · Methodology → [docs/METHODS.md](docs/METHODS.md)

---

## What it answers

| Question | Metric | Output |
|---|---|---|
| Which device tracks are accelerating? | `THI` — shrinkage-adjusted recent rate ÷ baseline rate | Track heat table |
| Is a specific major changing direction? | Jensen-Shannon divergence of its product-code mix | Migration table ("who is re-allocating") |
| What is genuinely new? | First-ever `(company, product_code)` occurrences | "First seen" weekly list |
| Is pharma shifting therapeutic focus? | Trial-start rates + phase mix per area | Drug radar |
| Where is the China gap? | US activity share vs loaded NMPA registrations | `cn_gap` table (honest `unavailable` when no CN data) |
| Does any of it predict equity returns? | Event study: AR vs SPY at +1/+5/+20/+60 trading days | `out/trading.json` (simulation only) |

## Quickstart

```bash
git clone https://github.com/OWNER/medradar.git
cd medradar

# no API key, no dependencies beyond Python 3.10+
python -m medradar run --months 60 --with-trade

# open the dashboard
#   out/index.html          (also copied to docs/index.html for GitHub Pages)
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
