# Methodology — how MedRadar turns filings into direction

This document is the contract behind the numbers. If a metric changes meaning, this file changes
first. Everything here is computed with the Python standard library only, deterministically (fixed
bootstrap seeds), from public data snapshots you can regenerate.

The Market-to-R&D lane has a separate contract for SEC financial facts, procurement semantics,
rolling-origin evaluation and Horizon forecasts: [docs/REVERSE_RD.md](REVERSE_RD.md).

---

## 1. The observation model

Every public act becomes one row in the `events` table:

| Column | Meaning |
|---|---|
| `kind` | `510k` / `pma` / `device_recall` / `drug_approval` / `trial` / `advisory_committee` / `8k_catalyst` / `nmpa_registration` |
| `event_date` | date the act happened (decision date, approval date, trial first-posted date) |
| `published_at` | when the source made it public; an openFDA decision date is **not** assumed to be public |
| `first_seen_at` | when MedRadar first ingested it |
| `available_at` | **the only timestamp a backtest may use** (defaults to a real `published_at`, never to `event_date`) |
| `timestamp_quality` | `datetime` / `date` / `estimated` / `unknown`; only `datetime`/`date` with a real timestamp can trade |
| `as_of` | when MedRadar fetched it (point-in-time marker) |
| `company_key` | resolved parent company (may be `NULL` — never guessed) |
| `track_id` | resolved technology track (may be `NULL` for unmapped product codes) |

Approximations that are documented rather than hidden:

* openFDA publishes after the FDA decision, so `event_date` is the decision date but our *knowledge*
  lags. Without a genuine publication field, 510(k)/PMA rows get `timestamp_quality=unknown` and no
  `available_at`; they remain in industry counts but cannot enter return studies.
* Trial registration may be posted up to 21 days after first enrollment. `event_date` uses
  `studyFirstPostDate`, i.e. when the record became public — not when the trial started. Device and
  diagnostic-test interventions use the device taxonomy; drug-only trials stay out of the device frontier.
* Signal dates add one calendar day to a real `available_at` (`available_at + 1`), modelling "you could act the
  next day". Missing, `estimated` and `unknown` public times never generate trading signals.

## 2. Company resolution (the make-or-break step)

openFDA stores the applicant string exactly as typed. Measured on 24 months of 510(k):

| Company | Naive name match | Reality |
|---|---|---|
| Johnson & Johnson | **2** | 100+ via Ethicon / DePuy Synthes / Biosense Webster / Cerenovus |
| GE HealthCare | **6** | files as GE Medical Systems and other entities |
| Medtronic | 68 | 5+ distinct legal entities in a single year |

`CompanyRegistry.resolve()` tries, in order:

1. exact normalised alias match → confidence `1.0`;
2. all alias tokens contained in the applicant string → `0.95 + small bonus` (longest alias wins);
3. Jaccard token similarity ≥ `0.82` → that score.

Anything below the floor stays **unmatched** and is reported (`coverage.unmapped_company_events`,
`stats.top_unmatched`). False negatives are visible and fixable; false positives silently poison
every downstream number, so we prefer them.

## 3. Track heat: THI and `prob_up`

For an entity (company or track) with `c` events in a window of `q` quarters, and baseline rate
`λ₀` (events per quarter over the preceding 20 quarters):

```
posterior  ~ Gamma(λ₀·k + c,  k + q)        # Gamma–Poisson conjugate, k = 3
THI         = posterior_mean / λ₀
prob_up     = P(posterior_rate > λ₀)
ci          = [posterior 2.5%, 97.5%] / λ₀
```

Why shrinkage: a company with 0 → 2 clearances has an infinite raw ratio. With `k = 3` quarters of
prior weight, that same company lands around `THI ≈ 1.6`, which is honest.

`THI = 1` means "no evidence of change". `THI = 2` with `prob_up = 0.98` means "even after assuming
no change, the data insists on doubling".

When a track has **zero** baseline events (new category), `THI` is computed against the mean baseline
rate of all active tracks and the row is flagged `emerging: true` — never silently dropped.

**Point-in-time rule for signals.** An earlier version boosted a signal's score with the track's THI
computed over the current window, which quietly used data published *after* the event. Signals now
use only "how many events did this track already have in the 180 days before this one became
public" (`prior_track_count`), computed from `available_at` with a bisect over sorted history.

## 4. Direction = portfolio mix shift

Volume alone confuses "more regulatory activity" with "different bets". For each company with ≥4
recent and ≥2 baseline events:

```
p_recent = normalised product-code / track shares in window
p_base   = normalised shares in baseline
JS       = Jensen–Shannon divergence (nats, 0 = identical mix)
delta    = p_recent[t] − p_base[t]   for tracks with |delta| ≥ 0.08
```

Reported as the migration table, sorted by `JS`. This is how "Medtronic is quietly moving from spine
towards cardiac rhythm" appears as a number instead of an anecdote.

## 5. Novelty

`first occurrence` of a `(company_key, product_code)` pair across the entire collected history.
Events inside the last 90 days that are first occurrences feed the "first seen" list and the
`device_novel_code` signal. Rationale: a new product code is the earliest public trace of a new
product line — the 510(k) itself is a lagging confirmation of R&D that started years earlier.

## 6. China gap (`cn_gap`)

```
us_share[t] = recent US device events in track t / all recent US device events
cn_share[t] = loaded NMPA registrations in track t / all loaded NMPA registrations
gap_index   = us_share[t] − cn_share[t]
```

Interpretation: tracks with high `us_share` and low `cn_share` are where the US is investing and
China has little registered presence. This is *not* a market-size estimate and *not* a
recommendation.

**When no Chinese data is loaded**: `cn_count`, `cn_share`, `gap_index` are `null` and
`cn_data_status = "unavailable"`. Rendering `0` would claim "China has nothing here", which we cannot
know. The demo seed (`MEDRADAR_NMPA_DEMO=1`) is labelled `demo` and never mixed with real data.

## 7. Signals

| kind | direction | rule |
|---|---|---|
| `device_novel_code` | +1 | first-ever product code for a company within 180 days |
| `device_new_track` | +1 | first-ever track for a company within 180 days |
| `drug_approval` | +1 | ORIG NDA/BLA approval within 365 days |
| `trial_start` | +1 | Phase 3 trial registration within 180 days |
| `recall_cluster` | −1 | ≥2 recalls for one company within 90 days |

Scores are heuristic (0.5–0.9) and intentionally *not* tuned on returns. Tuning on the outcome after
seeing the backtest is how projects lie to themselves.

## 8. Event study and paper portfolio

**Event study** (`eventstudy.run_event_study`):

* signals are read from the `signals` table, which stores `available_at` and `timestamp_quality`;
  missing, `estimated` and `unknown` public times are excluded with separate counts in
  `skipped.missing_timestamp`, `skipped.estimated_timestamp` and `skipped.unknown_timestamp`;
* entry = open of the first trading day **after** `signal_date`, where
  `signal_date = available_at + 1 day` — i.e. roughly two trading days after the event;
* exit = close `h` trading days later, `h ∈ {1, 5, 20, 60}`;
* `AR = stock return − benchmark (SPY) return`, negated for `direction = −1`;
* per kind: n, mean, median, std, t, percentile-bootstrap 95% CI, hit rate.

Entries are never at the signal-day close. That single rule removes most of the accidental
"profitability" in naive FDA backtests.

**Case event-study audit (v0.3.0).** `clinical_hold`, `refuse_to_file`, `crl`, `pre_submission`
and `designation` are separate categories; pre-submission wording is explicitly excluded from
approval evidence. For each category × horizon, observations with absolute SPY-abnormal return
above 100% are listed in `audit.flagged_cases`, counted in `extreme_n`/`excluded_n`, and removed
before bootstrap inference. `raw_n`, `unfiltered_raw_mean`, the audited raw mean and winsorised
mean are all retained. This is an audit gate, not a claim that every large return is a data error:
each flagged ticker/date still requires split, adjustment and corporate-action review.

**Paper portfolio** (`paper.run_paper`, v1): long only, equal-weight budget per signal capped at 5%
per name and 25% per track, next-open entry, 60-trading-day hold, −20% close-based stop, 20 bps +
$1 per fill. Weekly-sampled equity curve; full daily series in `paper_equity.csv`.

Not modelled in v1: short borrow fees, merger squeeze-outs, delisting returns, market impact beyond
20 bps. A long-only book therefore **overstates** what a deployable strategy could do, and the report
says so.

## 9. Threats to validity (read this before quoting a number)

1. **Name-resolution coverage** is the dominant error source. Unmatched events are reported, not
   imputed, but big conglomerates are systematically under-counted until their subsidiary list is
   complete.
2. **Approval counts ≠ R&D spend.** Regulatory strategy (predicate choice, 510(k) vs De Novo vs PMA)
   and acquisitions distort the mapping from "clearances" to "investment".
3. **Small samples.** Majors clear ~1.5–3 devices/month. Monthly rankings are noise; the tool defaults
   to 8-quarter windows and shrinks explicitly.
4. **Survivorship and delisting bias** in free price data. Acquired/failed tickers are often missing,
   which flatters any long strategy.
5. **Multiple testing.** Five signal kinds × four horizons = 20 tests. A t of 2 is not significant
   after that many looks; treat the study as hypothesis generation, not proof.
6. **Publication lag.** openFDA is 2–12 days behind the decision; a real intraday strategy would need
   press releases / 8-K / AdCom feeds.
7. **NMPA data.** Absent by default (WAF). `cn_gap` is unavailable unless you supply a CSV.

## 10. Frontier device radar

`medradar frontier` reads public pre-decision events rather than inferring confidential status:

* FDA Advisory Committee calendar rows and linked agenda/briefing/slide documents;
* ClinicalTrials.gov `first_posted` registrations;
* SEC 8-K `pre_submission` and `designation` records.

`config/tracks_device.json` gives every track a `domain`, `domain_zh` and `frontier_keywords`.
The registry covers 50 tracks in 23 domains. The JSON feed groups events by stage, domain and track,
keeps source URLs and timestamp quality, and explicitly reports
`pending_510k_pma_monitoring=false`. AdCom page-update dates are `estimated`, so they inform
industry research but never enter a return study.

## 11. Reproducibility

* every HTTP response is cached by URL under `data/cache/` → re-runs are deterministic and offline;
* `build_metrics` is a pure function of the SQLite facts; bootstrap seeds are fixed;
* `--offline` replays cache only; CI runs the test suite with synthetic fixtures and zero network;
* `docs/metrics.json` is a committed snapshot so readers can inspect the exact numbers behind a
  published report. It is not a byte-for-byte reproduction kit for the full historical crawl: the
  1.2 GiB SQLite database and raw HTTP cache are not committed. Rebuilding from public endpoints
  can reflect later source revisions; a new research release must freeze its DB/cache manifest and
  recompute metrics under the current taxonomy.
