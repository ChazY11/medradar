# SCIENCE-001 - EDGAR historical point-in-time evidence study

This directory is the first *empirical* study in MedRadar. It does not build
infrastructure; it asks one question of one source and reports what came back.

## The question

MedRadar's long-run question is whether publicly observable evidence gives
reliable early signals of meaningful change in medical technology. Before any
predictive claim is possible, two things must hold:

1. the *time* at which a signal became public must be reconstructible, and
2. the *outcome* must be definable independently of the signal.

This study tests both on SEC EDGAR, for twelve listed medical-technology
issuers, over 2021-2026, and then runs one small, pre-registered exploratory
experiment.

## Reproduce from a clean checkout

Requirements: Python 3.10+, no third-party package for fetch/verify/build/
experiment; matplotlib only for the figures.

```
python research/science_001/cli.py fetch       # network: submissions + full 8-K filings
python research/science_001/cli.py verify      # offline: parse headers, grade time, extract features
python research/science_001/cli.py build       # offline: dataset + 90-day forward labels
python research/science_001/cli.py experiment  # offline: baselines, permutation null, power
python research/science_001/cli.py figures     # offline: figures/figure1_*.png, figure2_*.png
```

Or the whole chain: `python research/science_001/cli.py all`.

Every step is resumable. `fetch` caches each response under
`research/science_001/data/cache/` (git-ignored) together with a provenance
sidecar holding the HTTP status, `Last-Modified`, collection timestamp and
SHA-256; re-running `fetch` re-uses the cache and never re-downloads.
`--offline` forbids network access entirely and replays the cache.

Tests (offline, synthetic fixtures, no network):

```
python -m pytest tests/test_science_001.py -q
```

## What is committed, and what is not

SEC filings are public records, but the repository keeps only what is needed for
reproduction and audit:

| committed | not committed |
|---|---|
| `artifacts/panel_filings.csv` - accession, CIK, form, dates, items | the full-submission `.txt` bodies (~300 MB) |
| `artifacts/time_verification.csv` - raw header value, UTC instant, DST offset, grade, SHA-256, `Last-Modified` | the response cache |
| `artifacts/dataset.csv` - one row per event, features + labels | the raw captured SEC documentation pages |
| `artifacts/experiment_results.json`, `figures/*.png` | |
| `evidence/sec_docs/sources.json` - URL + verbatim quote + SHA-256 of every cached source | |

Every non-committed byte has a committed SHA-256 and URL, so any claim can be
re-derived by re-fetching. The policy rationale is in
`docs/governance/DATA_INVENTORY.yaml` - sec.gov is classified GREEN and this
directory is classified `medradar_derived_artifacts`.

## File map

| file | role |
|---|---|
| `PROTOCOL.md` | pre-registration, frozen before any label was computed |
| `TIME_SEMANTICS.md` | phase-1 result: what each EDGAR time field can and cannot support |
| `RESULTS.md` | phase 3-5 result: the experiment, its numbers and its limits |
| `edgar.py` | issuer registry, polite client with per-response provenance, archive parser |
| `timesemantics.py` | US DST rule, raw-header -> UTC, evidence grades, availability bounds |
| `sample.py` | filing frame, exclusions ledger, stratified verification sample |
| `features.py` | fixed lexicons and per-1,000-word rates |
| `dataset.py` | forward labels, censoring, 8-K/A amendment linking |
| `experiment.py` | model ladder, AUC, ridge logistic, cluster bootstrap, permutation test, power |
| `figures.py` | the two figures, rendered from committed artifacts only |
| `cli.py` | the command chain above |
| `evidence/sec_docs/` | SEC primary-source documentation layer (28 sources, verbatim quotes) |
| `evidence/repo_recon.md` | governance-gate and reuse map produced for this study |

## Science discipline enforced in code

* Acceptance time, public availability, event time and collection time are four
  separate fields in four separate files. Nothing is copied between them.
* No time field is filled by estimate. A filing that cannot be graded gets a
  grade that says so, and is excluded from timed analysis.
* Outcome labels come from later filings only, and from SEC-assigned item codes
  rather than from any text model.
* Censored forward windows are dropped, never labelled 0.
* A negative or null result is a result. The hypothesis in `PROTOCOL.md` is not
  revised after seeing the numbers; deviations would be appended there.
