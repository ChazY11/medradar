# Phase 2 — new data sources and the feature-group ablation

This documents the Phase 2 work (v0.4.0): point-in-time market features, OpenAlex
publication features, a key-gated patent adapter, and the frozen A–G ablation on both
prediction targets. Cold numbers live in
`experiments/reverse_rd_v2/ablation_metrics.json` and the narrative in
`experiments/reverse_rd_v2/REPORT.md` §C; this file records the design and the
reproduction path.

## What was added

| Source | Status in v0.4.0 | Provenance / PIT rule | Doc |
|---|---|---|---|
| Equity market bars (company + SPY/XBI) | **collected and evaluated** | offline read-only import of the base repo's Yahoo daily `prices` lane (adjusted closes); knowledge time = trading date; no new network calls | [MARKET_DATA.md](MARKET_DATA.md) |
| OpenAlex publications | **collected and evaluated** (weak signal) | keyless API, one grouped request per company, annual counts; only complete years with a 15-Feb knowledge lag | [PUBLICATION_PATENT_DATA.md](PUBLICATION_PATENT_DATA.md) |
| USPTO patents | adapter only — **not evaluated** | Open Data Portal requires `USPTO_ODP_API_KEY`; without it the collector returns `unavailable_missing_api_key` and writes zero rows; JSONL import path documented | [PUBLICATION_PATENT_DATA.md](PUBLICATION_PATENT_DATA.md) |
| USAspending procurement | **excluded from historical gain claims** | current snapshot is not point-in-time usable (`pit_usable=0`); amounts are obligations, not revenue | [REVERSE_RD.md](REVERSE_RD.md) |
| Hiring signals | deferred | no stable legal point-in-time source evaluated | — |

Coverage actually observed: 38 of 44 mapped tickers (44/51 companies have a ticker;
6 tickers absent from the local price lane, 7 companies have no listed ticker), 95,725
bars 2016-10-31..2026-10-30; market features complete on 5,206/6,701 continuation
examples (77.7%, holdout 245/307). OpenAlex: 51/51 companies matched, 150,087 works
2014–2026, 616 annual rows, 53 live requests total (cached; offline replay reproduces
the artifacts).

## Ablation design

Same rows, same purged multi-window protocol (`holdouts=3`, origins 2025-04-01,
2025-07-01, 2025-10-01), same dependency-free logistic model and hyperparameters for
every specification. One specification per process so cells can be computed in parallel
and merged deterministically.

- Continuation: A `rd_only` (reference), B `+financial`, C `+market`, D `+publication`,
  E `+financial+market+publication`.
- Entry: A shared-only and B shared+financial (Phase 1 parity), C shared+entry-specific,
  D shared+entry+financial (reference), E D+market, F D+publication, G D+market+publication.
- Procurement is **not** an ablation arm: its current snapshot cannot be used for
  historical gain claims. Patents are **not** an ablation arm: no API key, no rows.
  The "all available" arm is therefore financial + market + publication.

## Result in one paragraph

No added source produces a statistically detectable ranking improvement on either
target. On continuation, every marginal AP delta is negative (financial −0.0013,
market −0.0015, publication −0.0001, all −0.0068) while the all-source model improves
calibration (ECE −0.0183) and FPR (−0.0281) without improving ranking. On entry, the
final holdout favours the Phase 1 shared-only cells (AP 0.1139 / 0.1163) over every
specification that uses the entry-specific or new features, while the three-window mean
favours D/E/G; the differences are small relative to the 0.014–0.026 window std and are
not a stable effect. Publications are the least harmful addition (entry AP +0.0029 vs
the corrected entry baseline) but are alias-matched annual counts, not R&D evidence.

## Reproduce

```bash
# 1) one-time data collection (network; ~6 min for FDA/SEC, ~1 min market import, 51 OpenAlex requests)
pip install -e '.[bulk]'
python -m medradar.intelligence.pipeline collect --source fda --months 120 --db data/medradar.sqlite
python -m medradar.intelligence.pipeline collect --source sec --db data/medradar.sqlite
python -m medradar.intelligence.pipeline collect --source procurement --start-date 2016-01-01 --db data/medradar.sqlite
python -m medradar.intelligence.pipeline collect --source market --prices-db <base MedRadar>/data/medradar.sqlite --db data/medradar.sqlite
python -m medradar.intelligence.pipeline collect --source publications --db data/medradar.sqlite

# 2) Phase 1 datasets + multi-window metrics
python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite --holdouts 3

# 3) one ablation cell per invocation (parallelisable), then merge
python experiments/reverse_rd_v2/run_ablation.py --db data/medradar.sqlite --target continuation --spec C --out cells/continuation_C.json
python experiments/reverse_rd_v2/merge_ablation.py --cells cells --out experiments/reverse_rd_v2/ablation_metrics.json

# 4) behavioural acceptance (offline suite + artefact checks)
python verifier/v1/verify.py
```

## Boundaries that must not be blurred

- A stock return is not technological capability; a paper count is not an approved
  development project; a patent application is not a product.
- No causal claim: this phase measures incremental *prediction*, not a market→R&D
  mechanism.
- Three overlapping holdout windows are not three independent replications.
- Market-feature survivorship: delisted/acquired tickers and non-US listings are absent;
  the Yahoo-derived lane is not a licensed market-data feed.
