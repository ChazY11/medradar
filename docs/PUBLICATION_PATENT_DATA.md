# Publication and Patent Auxiliary Sources (Reverse R&D v2)

Status: OpenAlex publication counts were collected for all 51 curated device
companies and evaluated in a real ablation. The USPTO patent path is implemented
but **not evaluated** because the Open Data Portal requires an API key that is
not available in this environment; no patent numbers are reported anywhere.

Both sources are **weak signals**. A publication or patent is not an approved
R&D project, a product, revenue, or evidence that a company invested in a
technology track. Counts are annual, alias-based and noisy.

## Files

| Path | Role |
|---|---|
| `medradar/intelligence/sources/publications.py` | Keyless OpenAlex collector: one grouped request per company, disk cache, `publication_counts` table |
| `medradar/intelligence/features/publication_features.py` | Point-in-time publication features + patent features |
| `medradar/intelligence/sources/patents.py` | USPTO Open Data Portal adapter (key-gated, honest blocked path) + JSONL importer |
| `scripts/run_publication_ablation.py` | Collection + purged ablation, writes `experiments/reverse_rd_v2/*.json` |
| `tests/test_publication_intelligence.py` | Offline tests (synthetic fixtures only) |

## OpenAlex publications — provenance and licence

* Endpoint: `https://api.openalex.org/works`.
* One grouped request per company:
  `filter=raw_affiliation_strings.search:<alias>,from_publication_date:2014-01-01&group_by=publication_year`.
  The response's `group_by` list gives a count per publication year in a single
  request (verified during collection: the `group_by` shape is supported).
* Licence/terms: OpenAlex metadata is **CC0**; attribution is appreciated. No
  API key is required for this endpoint, but OpenAlex applies a small **shared
  free daily budget per IP** (~USD 0.001 per request) and asks for polite use.
  Requests are throttled (>=0.2 s apart), retried on 429/5xx, and every response
  is cached under `data/cache/openalex/` (gitignored). Live request budget for
  this task was respected: 2 shape probes + 3 alias-validation requests + 48
  requests in the collection run = **53 live requests total**, below the
  60-request cap; the committed artifact records the 48-request collection run
  (`request_stats {"requests": 48, "cache_hits": 3}`) and every later run replays
  the cache offline.
* Collected on the frozen 2026-11-01 database: **51/51 companies matched, 0
  failed, 150,087 total works across stored years 2014–2026**. "Matched" here
  only means the alias search returned at least one work; it is not entity
  validation (see below).

## Alias matching is noisy by construction

`raw_affiliation_strings.search` is a text search over free-text affiliations,
not an entity resolver. Consequences:

* A parent name over-collects. `JOHNSON & JOHNSON` (61,596 works) includes pharma
  and consumer research, not just J&J MedTech; `PHILIPS` (12,733) includes
  non-medical Philips research; `ABBOTT` (9,641) mixes diagnostics, nutrition and
  devices.
* Subsidiaries, acquired brands and alternate spellings are only partially
  covered (the collector uses the first curated alias per company, e.g.
  `BOSTON SCIENTIFIC`, `B BRAUN`, `W. L. GORE`).
* Small companies can look disproportionately quiet (`INVACARE` 4 works,
  `COOPER COMPANIES` 6) because papers use brand/subsidiary names instead.
* Token matching can over-match generic names (`MEDLINE INDUSTRIES`,
  `COOK MEDICAL`).

These are documented limitations, not bugs to be "fixed" by hand-tuning aliases;
any alias choice is a modelling decision that must be frozen before evaluation.
**All 51 matched** is therefore not evidence that matching is correct.

## Annual granularity and the 15-February knowledge lag

OpenAlex provides a publication **year**, not a publication timestamp. To avoid
using a year that is still accruing records (or even the current partial year),
the feature builder treats publication year `y` as known only from **15 February
of `y+1`** and uses only complete years:

```
usable years at cutoff t = { y : y <= t.year - 1 and date(y+1, 2, 15) <= t }
```

So a 2024 count never affects a 2024-10-01 cutoff, and even a 2025-01-01 cutoff
can only use data through 2023. Counts for 2025/2026 are stored as reported by
the API but are never used by the features.

Features appended to each example (missing data is flagged, never zero-filled):

| Feature | Definition |
|---|---|
| `pub_count_prev_year` | works in the most recent usable year |
| `pub_count_3y` | works in the three most recent usable years |
| `pub_growth_prev_year` | `(prev - prev_2) / prev_2`; `None` if the prior year is unknown or zero |
| `pub_intensity_vs_company` | `prev / max(3y_total/3, 1)`: latest year relative to the company's own 3-year annual mean |
| `pub_missing` | `1.0` when the company has no persisted counts or no usable year, else `0.0` |

## USPTO patents — key-gated adapter, not evaluated

* Endpoint: `POST https://api.uspto.gov/api/v1/patent/applications/search`.
  It answers **HTTP 401 without an API key**, so the key is required.
* Exact environment variable: **`USPTO_ODP_API_KEY`**. With the key set,
  `patents.collect` queries by assignee alias (`X-API-KEY` header) and stores
  application id, assignee, filing date, publication date and title. The
  endpoint/body shape is documented here from the USPTO ODP description; the
  live response shape could not be verified in this environment because no key
  is available, so the parser accepts the documented `patentFileWrapperDataBag`
  collection and equivalent keys and stores only fields actually returned.
* Without the key, `patents.collect` returns
  `{"status": "unavailable_missing_api_key", "rows": 0, ...}` and writes no rows.
  It never fabricates patent counts.
* For a user-provided export, `patents.collect_from_jsonl(path)` imports one
  JSON object per line with columns `application_id` (required), `company_key`,
  `assignee`, `filing_date`, `publication_date`, `title`.
* Point-in-time rule: knowledge time is the **publication date**, never the
  filing date. Applications filed before a cutoff but published after it are
  ignored (`pat_apps_pub_12m`, `pat_apps_pub_3y`, `pat_missing`).
* **Patents are not evaluated here.** There is no live USPTO data without a key,
  so no patent ablation numbers exist in `publication_metrics.json`; the artifact
  records `"status": "not_evaluated_no_api_key"` / `unavailable_missing_api_key`
  with `rows: 0`.

## Real publication ablation (continuation target, purged single holdout)

Protocol identical to `experiments/reverse_rd_v1` (the `rd_only` anchor
reproduced v1 exactly, max absolute delta 0.0): 6,701 mature company–track
examples, 25 quarterly origins, purged expanding-window training
(`cutoff + 12m <= origin`), final chronological holdout **2025-10-01**
(307 rows / 129 positives). Feature coverage: 51/51 companies and 6,701/6,701
examples have publication data; all 307 holdout rows have it.

| Model | Dev PR-AUC | Holdout PR-AUC | Brier ↓ | ECE-10 ↓ | FPR@0.5 ↓ | P@10% |
|---|---:|---:|---:|---:|---:|---:|
| `rd_only` (10 features) | 0.797350 | **0.793476** | 0.172134 | 0.081120 | 0.275281 | 0.935484 |
| `rd_publications` (+5 pub) | 0.794082 | **0.793349** | 0.172047 | 0.086677 | 0.286517 | 0.935484 |
| `rd_financial_publications` (+5 pub, +11 fin) | 0.789162 | **0.790559** | 0.172428 | 0.071956 | 0.269663 | 0.935484 |

Deltas on the holdout (new minus old; positive PR-AUC/P@K and negative
Brier/ECE/FPR are improvements):

* `rd_publications − rd_only`: PR-AUC **−0.000128**, Brier −0.000087, ECE
  **+0.005556** (worse), FPR **+0.011236** (worse), P@10% 0; development PR-AUC
  **−0.003268**.
* `rd_financial_publications − rd_publications`: PR-AUC **−0.002789**, Brier
  +0.000381, ECE −0.014720, FPR −0.016854, P@10% 0; development PR-AUC
  **−0.004920**.

Deterministic paired bootstrap (2,000 resamples, seed 7) of PR-AUC delta:

* publications vs rd_only: mean −0.000147, 95% CI **[−0.003553, +0.003067]**,
  P(Δ≤0)=0.527.
* financial+publications vs publications: mean −0.002691, 95% CI
  **[−0.011470, +0.005973]**, P(Δ≤0)=0.731.

**Interpretation: negative / null result.** OpenAlex annual publication counts
add no detectable incremental ranking value on this holdout (the interval is
tight around zero and the point estimate is negative), and they slightly worsen
calibration and the fixed-threshold false-positive rate. Development PR-AUC also
falls. This is an honest negative: the signal is annual and alias-noisy, and the
continuation target is already dominated by per-pair persistence. No causal
market→R&D claim is made.

## Reproduce

```bash
# Once: live collection (<=60 requests for 51 companies), cached under data/cache/openalex/
python scripts/run_publication_ablation.py --live

# Re-run offline from the cache: identical numbers, no network calls
python scripts/run_publication_ablation.py

# Offline tests
python -m pytest tests/test_publication_intelligence.py
python -m medradar selftest
```

Artifacts written and committed: `experiments/reverse_rd_v2/publication_metrics.json`
(protocol, coverage, per-model metrics, deltas, bootstrap, patents status) and
`experiments/reverse_rd_v2/publication_provenance.json` (per-company alias,
query, annual counts, request/cost provenance, failures). The SQLite database
and OpenAlex HTTP cache are **not committed** (`data/` is gitignored); a fresh
checkout can reproduce the numbers by re-running with `--live` once, after which
the run is offline. The committed artifacts contain every number quoted above.

## Boundaries

* Publications and patents are weak auxiliary signals, not approved R&D projects,
  not product revenue and not a measure of internal research start dates.
* Publication counts are annual and alias-matched; patent counts would be
  publication-date-based and are not available here.
* Single 307-row holdout; a negative result is not proof that publications are
  useless everywhere, only that no incremental value is detectable in this
  protocol.
* OpenAlex affiliation coverage is itself incomplete and changes over time; the
  annual counts are a snapshot as of the collection date.
