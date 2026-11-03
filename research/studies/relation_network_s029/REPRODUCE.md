# S-029 复现指南 / Reproduce

Everything in this study is produced by the numbered scripts in `code/`. No step depends on a manual
edit, a notebook cell, or a stored intermediate that cannot be regenerated.

## 0. Environment

| item | value |
|---|---|
| Python | 3.12.10 (CPython, Windows 11) |
| Third-party packages | `requests` 2.34.2 only (plus the standard library: `json`, `csv`, `hashlib`, `sqlite3`, `gzip`, `re`, `unicodedata`) |
| Database | SQLite (read-only access to `D:/DEPPSKK/medradar/data/observatory/observatory.sqlite` for the clock audit) |
| Hardware | one laptop; no GPU, no cloud, no paid API, no always-on service |
| Network | ClinicalTrials.gov API v2, Europe PMC REST, OpenAlex (shared free budget), Crossref, ROR |

Reproduce the environment:

```powershell
python -m venv .venv ; .venv\Scripts\activate
pip install requests==2.34.2
```

## 1. Where the work happens

The study was run in a git worktree so the S-028 branch and its frozen artefacts were never touched:

```
D:\DEPPSKK\worktrees\s029-relations        # branch research/s029-evidence-based-relations
  research/studies/relation_network_s029/  # everything below is relative to this folder
```

## 2. Full pipeline (order matters for the first run only; each step is idempotent)

```powershell
cd research\studies\relation_network_s029

# Phase 0 — feasibility
python code\s029_01_query_recall_probe.py     # name-variant search recall (RQ1), ~90 requests
python code\s029_clock_audit.py               # four-clock audit of the live APIs (temporal auditor)
python code\s029_lit_verify.py                # verifies every literature citation via Crossref/EPMC/OpenAlex
python code\s029_company_register.py          # builds/validates the corporate entity register from primary sources

# Phase 1 — reconstruction
python code\s029_02_collect_ctgov.py          # ClinicalTrials.gov, 5 companies + variants, sites sub-sample
python code\s029_03_collect_epmc.py           # Europe PMC, year-stratified + variant samples
python code\s029_04_extract.py                # raw payloads -> source-stated tables (no identity inference)
python code\s029_05_company_map.py            # string -> company identity with date-validity tests
python code\s029_06_institutions.py           # institution extraction + ROR resolution (cached in data/ror_cache.json.gz)
python code\s029_11_crosssource.py            # OpenAlex/Crossref cross-source agreement (bounded request budget)
python code\s029_07_claims.py                 # Entity / Evidence / RelationClaim store
python code\s029_08_quality_metrics.py        # sections A-D + the pre-registered verdict
python code\s029_09_worksheet.py              # ~100 stratified human-review candidates
python code\s029_10_network.py                # section E under an explicit quality gate
python code\s029_12_verify_report.py          # independent audit of every reported number
```

`python code\s029_12_verify_report.py` must exit 0. It recomputes the evidence hashes from the
committed raw payloads, re-derives the claim counts, checks that the pre-registration file's sha256
matches the one recorded when the verdict was computed, and confirms that no S-028 artefact changed.

## 3. Cost and politeness

| source | requests (recorded in `data/request_log.jsonl`) | notes |
|---|---|---|
| ClinicalTrials.gov API v2 | ~250 | 0.35 s delay; paged with the API's own tokens; every stop reason recorded |
| Europe PMC REST | ~180 | 0.40 s delay; year-stratified, hit counts stored |
| ROR | ~4.3k | 0.25 s delay, cached in `data/ror_cache.json.gz` so re-runs are offline |
| OpenAlex | ≤16 batches | shared unauthenticated budget ($0.10/day at $0.001/request); DOIs batched 50 per request, request list stored in the artefact |
| Crossref | ~75 | polite pool with `mailto` |

No key, no account, no payment. The only credential used anywhere in this study is a GitHub login for
opening the draft PR.

## 4. Data products (all committed)

| file | content |
|---|---|
| `data/raw/*.json.gz` | every retrieved payload, exactly as received, one file per query; `data/request_log.jsonl` records URL, UTC timestamp, HTTP status and body sha256 for every call |
| `data/ctgov_trials.jsonl` | 2,498 unique ClinicalTrials.gov studies with role strings and all four registry date fields preserved |
| `data/ctgov_sites.jsonl` | 1,126 site-facility rows from the 209-study location sub-sample |
| `data/epmc_pubs.jsonl` | 770 Europe PMC records with per-author affiliations, MeSH terms, grants, and the Europe PMC date fields |
| `data/company_mentions.jsonl` | every company-string occurrence with its identity decision and rejection reason (including the rejected ones) |
| `data/institution_candidates.jsonl`, `data/institutions.jsonl` | institution strings and their ROR resolution attempts |
| `data/entities.jsonl`, `data/evidence.jsonl`, `data/claims.jsonl`, `data/claim_rejects.jsonl` | the relation store |
| `data/crosssource.jsonl` | per-publication OpenAlex/Crossref comparison |
| `artifacts/*.json` | every number used in the reports, machine-readable |

## 5. Known non-determinism (stated, not hidden)

1. **Live sources change.** Re-running today returns slightly different counts (the registries and
   indexes are updated continuously). All conclusions are dated to the collection window recorded in
   the artefacts, and the raw payloads are committed so the *retrieved state* is fixed.
2. **OpenAlex budget.** If the shared daily budget is exhausted, step 11 records the failure instead
   of inventing results; the cross-source section then reports a smaller n.
3. **ROR cache.** Resolution is served from `data/ror_cache.json.gz`; deleting it re-queries ROR and may
   produce new matches for organisations created after this run.
4. **Dictionary order.** All samplings use seeds recorded in the artefacts (`stable_seed`), so the
   worksheet rows and cross-source sample are reproducible.

## 6. Provenance chain for one claim

1. `data/claims.jsonl` → `claim_id`, `evidence_id`, `source_record_id`.
2. `data/evidence.jsonl` → `original_url`, `payload_hash`, `original_text_reference`.
3. `data/request_log.jsonl` → the exact HTTP retrieval (URL, UTC time, status, sha256).
4. `data/raw/<query>.json.gz` → the payload itself; its sha256 recomputed by step 12 equals
   `payload_hash` (check V1).
5. `artifacts/company_entity_register.json` → the identity of a company string, with the SEC/GLEIF
   URL and verbatim excerpt behind every date.

A reviewer can therefore go from any reported number to bytes.

## 7. Runtime

On the reference laptop: Phase 0 ≈ 6 min, collection ≈ 4 min, ROR resolution ≈ 18 min (first run;
cached afterwards), remaining analysis ≈ 2 min. Total under 40 minutes from a clean checkout.
