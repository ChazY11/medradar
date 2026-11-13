# DATA GOVERNANCE, LICENSING & PROVENANCE AUDIT

**Audit:** REFOUNDATION-001 · `task-4`
**Auditor:** `data-governance`
**Worktree:** `<REDACTED_LOCAL_PATH> @ `audit/refoundation-001` (fork of `origin/main` @ `b2a14c0`)
**Date:** 2026-11-12 (Asia/Shanghai)
**Status:** complete; **no branch, PR, ref, remote or frozen artefact was modified.** All Git use was read-only (`ls-tree`, `show`, `cat-file`, `grep`, `log`, `rev-list`, `diff --numstat`). **No network request was made to any data provider or to GitHub.** Every claim below is grounded in committed bytes on some `origin/*` ref.

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** (1) every data source used or proposed across all 24 audited refs; (2) the alleged UN Comtrade exposure in PR #29 `research/horizon-001` and its inheritance by PR #30 `integration/convergence-001`; (3) committed raw/derived/cache artefacts and their redistribution status; (4) provenance and traceability of published numbers; (5) credentials, secrets and personal data; (6) data-quality/validation controls; (7) repository licensing and third-party notice completeness; (8) a data-asset register, a do-not-merge list and an explicit merge-safety statement.

**Method.** `git ls-tree -r -l` across 24 refs (32,232 tree entries → 4,199 distinct blobs); blob bytes read via `git cat-file --batch`; per-source registries extracted from three machine-readable registers committed on different branches and reconciled; licence strings read from the bytes actually committed (including archived terms pages); PII counted by regex with **values never emitted**; byte totals recomputed from object sizes, not from PR prose. Scripts and raw outputs are preserved under `docs/refoundation/_evidence/data/` (`ls_tree_all_branches.tsv`, `branch_data_totals.tsv`, `data_files_ge_100k.tsv`, `data_not_on_main.tsv`, `source_registers.json`, `secrets_scan.json`, and four Python collectors).

**Evidence base.** `docs/refoundation/_FACTS.md` and `_evidence/repo_facts.json` (charter and PR ledger); committed bytes on `origin/*`; three in-repo governance registers — `config/convergence/licence_policy.json` (51 sources, `integration/convergence-001`), `research/data_expansion/GLOBAL_DATA_SOURCE_REGISTER.json` (59 sources, `research/data-expansion-001`), `research/horizon/registry/sources/*.json` (51 sources, `research/horizon-001`); and `docs/convergence/LICENCE_AND_SECURITY_REVIEW.md` (549 lines, in-repo, **treated as a claim to be re-verified, not as authority**).

**Limits.** Publisher terms were read only from pages **already archived in the repository**; no live re-fetch was made, so every licence verdict is as-of the archived capture date, not as-of today (§9, R5). GitHub-side retention of unreachable objects, caches, forks and third-party clones is unobservable locally. Whether the PR #29 payload has already been fetched by a third party is unknowable from a local clone. File-count arithmetic used a fork-and-BOM-normalised listing: totals are ±1 path where noted. This is a rights-and-provenance audit, **not legal advice**; the three largest questions are routed to the owner in §9.

---

## 1. Verdict in one page

| # | Question | Verdict | Basis |
|---|---|---|---|
| 1 | Is UN Comtrade historical data committed on PR #29? | **YES — RED** | 30 paths, 29 distinct blobs, **6,234,301 B**, introduced by `18a7580`; recomputed independently (§2.2) |
| 2 | Was the "+692,975 lines" figure Comtrade-specific? | **No — the total is correct, the attribution is not** | `git diff --numstat origin/main...origin/research/horizon-001` sums to exactly 692,975; Comtrade-touching paths account for **72,979** of those lines (§2.1) |
| 3 | Is the payload present on PR #30 `integration/convergence-001`? | **No — payload absent; AMBER residue remains** | 0 of the 30 paths; but the same restricted **derived** cell is republished in 5 files on that branch (§2.5) |
| 4 | Is there a *second* Comtrade redistribution elsewhere? | **YES — RED, previously unreported** | `research/data-expansion-001` commits 4 Comtrade preview payloads, 255,265 B, with `primaryValue`/`cifvalue` populated (§3.4) |
| 5 | Do branches other than PR #29/#30 redistribute restricted content? | **YES** | Europe PMC abstract corpora on `research/phoenix-003-early-evidence` (36,644 records, 22,622 non-OA) and raw caches on `research/s029-evidence-based-relations` (§3.5, §3.6) |
| 6 | Any real credentials, tokens or private keys committed? | **No** | 4,199 blobs / 3,896 text blobs scanned across **all 24 refs**; 9 raw hits, **9 triaged as false positives** (§5) |
| 7 | Any personal data? | **YES — low sensitivity, remediable** | ≥417 distinct author emails (s029), 248 named UK procurement buyers, ClinicalTrials.gov contacts, author emails in Europe PMC records (§5.3) |
| 8 | Can published numbers be traced to a snapshot hash and commit? | **Partly** | Strong on `horizon`/`convergence` (per-file SHA-256 + manifest), **absent on `main`** for `docs/metrics.json` / `docs/summary.csv` (§4) |
| 9 | Is `LICENSE` MIT compatible with the committed data? | **No — the data is not MIT-licensed, and the file's own data notice is falsified by branch content** | `LICENSE:24-28` claims "does not redistribute bulk source data"; three branches do (§7) |
| 10 | Is any branch safe to merge from a rights standpoint? | **Only `main`. No open research branch is merge-ready as-is** | §8.4 |

**RAG roll-up (detail in §8):** on the **24 materialised sources** the split is **14 GREEN, 8 AMBER, 1 RED, 1 dual** (Europe PMC: metadata GREEN / abstract corpora RED), plus three source classes that are not in the 24 — Yahoo prices (AMBER), job-posting text (AMBER), ROR/NMPA-demo (GREEN). Across the **24 audited refs**: **3 RED** (`horizon-001`, `data-expansion-001`, `phoenix-003-early-evidence`), **4 AMBER-conditional** (`s029`, `s031`, `innovation-signals-observatory`, `convergence-001`), and **17 that only inherit `main`** (16 with no new third-party data at all, plus `main` itself which is safe with two cosmetic fixes).

---

## 2. UN Comtrade — deep dive on PR #29 (`research/horizon-001`)

### 2.1 What the PR actually adds, by bytes and lines

**[FACT]** `git diff --numstat origin/main...origin/research/horizon-001` sums to **692,975 added lines / 0 deleted**, matching the PR ledger in `_FACTS.md` §3 exactly. The PR adds **1,826 files** (`git ls-tree -r | wc -l`).

**[FACT]** The 692,975-line figure is **not** attributable to UN Comtrade. Ranked by added lines, the top contributors are:

| Added lines | Path | Source |
|---:|---|---|
| 102,843 | `research/horizon/DATASETS/scholarly/clinicaltrials_gov/CTGOV_INDEX.json` | ClinicalTrials.gov (public domain) |
| 66,104 | `research/horizon/DATASETS/industry/un_comtrade/raw/hs.json` | UN Comtrade (restricted) |
| 40,283 | `research/horizon/DATASETS/patents/epo_publication_server/COLLECT.json` | EPO |
| 36,689 | `research/horizon/DATASETS/scholarly/crossref/CROSSREF_INDEX.json` | Crossref |
| 29,524 / 29,480 / 28,481 | `.../uk_find_a_tender/raw/award_packages_p1..p3.json` | UK FTS (OGL) + **PII** |

**[FACT]** Summing every `numstat` row whose path contains `un_comtrade` gives **72,979 added lines (10.5 % of the PR)**, including 339 lines of connector code and 344 lines of `PROVENANCE.json`. **[INFERENCE]** The "+692,975 lines of Comtrade data" framing in the brief is therefore a misattribution of the PR's total size to its single most sensitive source; the restricted *bytes* are 6.2 MB, not 693 k lines of trade records. Both numbers matter, but for different reasons — the line count is a review-load problem, the byte count is a rights problem.

### 2.2 The exact restricted set — recomputed from object bytes

**[FACT]** Tree-diffing `research/horizon-001` (1,826 files) against `integration/convergence-001` (1,948 files) yields **33 paths present only on the PR #29 branch**, totalling **10,146,648 B** and **32 distinct blobs**. Thirty of those 33 are the UN Comtrade set; the other three are the UK Find-a-Tender raw OCDS packages (§5.3). The 30 Comtrade paths total **6,234,301 B** — arithmetic: 10,146,648 − 3,912,347 = 6,234,301, which reproduces the figure asserted in the in-repo review to the byte.

| Path (relative to repo root, ref `origin/research/horizon-001`) | Bytes | Blob (short) |
|---|---:|---|
| `research/horizon/DATASETS/industry/un_comtrade/raw/hs.json` | 1,886,837 | `7808cc6d` |
| `research/horizon/experiments/industry/evidence/un_comtrade.jsonl` | 1,832,311 | `f5111f62` |
| `research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl` | 1,832,311 | `f5111f62` *(same blob)* |
| `research/horizon/DATASETS/industry/un_comtrade/raw/reporters.json` | 81,177 | `e41f1deb` |
| `.../raw/annual_2015.json` … `annual_2024.json` (10 files) | 507,235 total | `608a7294`, `b6de7fee`, `a98f942e`, `0f0d8a1b`, `54907c43`, `19eddc3c`, `0a5a3e28`, `54038454`, `ce2f8f28`, `737f15ea` |
| `.../raw/comtradeplus_home.html` | 49,414 | `e54abf39` |
| `.../raw/monthly_202501.json` … `monthly_202512.json` (12 files) | 44,088 total | 12 blobs `4fe967d8`…`ddcce131` |
| `.../un_comtrade/summary.json` | 790 | `06785d36` |
| `research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl.sha256` | 84 | `15ce2f8a` |
| `.../raw/api_root.html` | 54 | `3c494092` |
| **Total** | **6,234,301** | **29 distinct blobs** |

**[FACT]** All 30 paths are introduced by the single commit **`18a7580`** ("research(horizon-001): global data-frontier acquisition…", 2026-11-10T07:34:17+08:00): `git rev-list origin/research/horizon-001 -- <path>` returns `18a7580` as the earliest commit for every one of them. **[FACT]** The branch tip is `2dcdc99` and `_FACTS.md` §5 records that `origin/research/horizon-001` is pushed to the public remote. **[INFERENCE]** The payload is therefore published, not merely staged locally; deleting the branch later cannot un-publish it.

### 2.3 Structure of the committed records (redacted sample)

**[FACT]** `un_comtrade.jsonl` is line-delimited `horizon.evidence.v1`. One record per trade cell; fields observed on a representative row: `source_id`, `source_record_id` (`comtrade:A:<reporter>:<partner>:<hs4>:<flow>:<period>`), `attributes.{reporter_code, hs_code, hs_description, flow_code, period, primary_value_usd, cif_value_usd, net_weight_kg, is_aggregate, legacy_estimation_flag}`, `event_at`, `source_public_at: null`, `first_observed_at`, `source_url`, `content_hash`, `licence_status: "terms_restricted"`, `licence_note`, `quality_flags: ["MISSING_PUBLICATION_DATE"]`. 608 records total (`summary.json`: 560 annual + 48 monthly; 22 requests).

**[FACT]** The raw preview files are unmodified API envelopes: `{"elapsedTime": "0.04 secs", "count": 56, "data": [ … ], "error": ""}` with numeric values populated for `primaryValue`, `cifvalue`, `netWgt` and descriptive fields returned as `null` (a documented property of the keyless preview path). **[FACT]** `hs.json` (1,886,837 B) and `reporters.json` (81,177 B) are the UN's HS nomenclature and reporter-code reference tables — reference material rather than trade values, but fetched under the same instrument and **not** excepted by the repo's own review.

**[FACT — evidence-integrity defect]** `research/horizon/DATASETS/industry/un_comtrade/raw/terms_of_use.html` (36,681 B) is **not** a terms page: `LICENCE_EVIDENCE.json` registers the `/TermsOfUse` URL at **HTTP 404** with `"sentences": []`, and the archived bytes are an error page. Likewise `api_root.html` is a 54-byte 404 body. **[FACT]** `LICENCE_EVIDENCE.json → by_source.un_comtrade` registers only those two 404 pages and **does not register `comtrade_license.html`** — the one committed file (50,778 B, 622 lines) that actually contains §5. **[INFERENCE]** A reviewer trusting the machine-readable evidence index would find zero quoted licence clauses for the only restricted source in the repository, while the branch ships a 404 page as if it were the terms of use.

### 2.4 The licence question, read from the committed bytes

**[FACT]** The repository's own registry entry (`research/horizon/registry/sources/un_comtrade.json`, 3,135 B) classifies the source as `licence_status: "terms_restricted"` and records:

- `blockers[0]`: `"TERMS_PROHIBIT_AUTOMATED_DOWNLOAD: Usage Agreement §5 reserves all rights; written permission from UNSD is required for anything beyond this bounded research sample."`
- `licence_note`: quotes §5 — "*any copying, automated browsing or downloading, redistribution, publication, or commercial exploitation of any material … is strictly prohibited without the prior written permission of the United Nations*" — and correctly names the instrument conflict: the keyless preview API invites programmatic access, the Usage Agreement forbids redistribution.
- `unlock_route`: written permission from the Director, UNSD, or a licensed Comtrade subscription.

**[FACT]** The same repository also commits the primary text: `raw/comtrade_license.html` (50,778 B) contains the §5 language quoted above. **[FACT]** A second, more permissive reading exists on another branch (§3.4): `research/data-expansion-001` records `"licence": "UN Comtrade terms of use; free for non-commercial use with attribution, bulk redistribution restricted"` and `"redistribution_allowed": "PARTIAL"`.

**[FACT]** The two readings conflict. **[INFERENCE]** The `horizon`/`convergence` reading is the defensible one, for three reasons: (a) it quotes §5 verbatim from a committed page rather than paraphrasing; (b) §5 names *redistribution* and *publication* explicitly, and a committed record set is both; (c) "free for non-commercial use with attribution" is not a clause that appears in the committed §5 text, so the permissive reading is unsourced. **[RECOMMENDATION]** Treat `terms_restricted` as authoritative and delete the permissive wording from the data-expansion register.

**Rights verdict for the 30 paths: RED.** Redistribution of UN Comtrade material without prior written permission. Attribution does not cure it (the instrument separately forbids removing authorship/copyright identification). The bounded-sample argument does not cure it: 608 cells is a small dataset but still a published mirror. The only curing paths are (i) written permission from UNSD, or (ii) removal of the material from every published ref.

### 2.5 PR #30 inheritance — quarantined payload, un-quarantined derivative

**[FACT]** `integration/convergence-001` contains **0 of the 30 paths**. Its 5 comtrade-matching paths are `CONNECTORS/industry/un_comtrade.py`, `DATASETS/industry/un_comtrade/PROVENANCE.json`, `raw/comtrade_license.html`, `raw/terms_of_use.html`, `registry/sources/un_comtrade.json` — i.e. code, provenance metadata and licence evidence, with no trade values. The intent is recorded in commit **`3c3a295`**, whose message states 30 paths were "deliberately NOT introduced" because `un_comtrade` is "the one source HORIZON itself records as licence_status=terms_restricted", and that this "does NOT remove them from PR #29 history". **[FACT]** Verified independently: the tree difference is real, not merely asserted in a commit message.

**[FACT — new finding, not in the in-repo review]** The quarantine did **not** remove the restricted **derived figure**. The exact Germany-2023 Comtrade cell (value deliberately **withheld from this document**; locators only) is still present on `integration/convergence-001` in **5 files / 7 occurrences**:

| File on `integration/convergence-001` | Occurrences | Why it matters |
|---|---:|---|
| `config/convergence/licence_policy.json` | 2 | the **machine-readable** quarantine register literally contains the value it quarantines |
| `tools/convergence/licence/build_policy.py` | 2 | the generator hard-codes it, so regeneration re-emits it |
| `docs/convergence/LICENCE_AND_SECURITY_REVIEW.md` | 2 | the remediation report republishes it |
| `docs/convergence/EXECUTIVE_SUMMARY_ZH.md` | 1 | the executive summary republishes it |

**[FACT]** By contrast, `research/horizon/reports/INDUSTRY_DATA_REPORT.md` on `convergence` **was** corrected to `"Comtrade: withheld — the exact value is not published here (UN Comtrade §5)"`, and `experiments/industry/EXP_H4_INDUSTRY.json` on `convergence` now carries `"comtrade_usd": null` with `"comtrade_usd__redacted": "UN Comtrade Terms section 5"`. **[INFERENCE]** The remediation was applied to the two files the reviewer thought of and *not* to the tooling and prose that describe them — i.e. the restricted value leaked through the remediation apparatus. That is the classic pattern: a quarantine list is itself a disclosure channel.

**[FACT]** On `research/horizon-001` the same value appears in 5 files: `raw/annual_2023.json`, `experiments/industry/evidence/un_comtrade.jsonl`, `exports/horizon-2026-11-10/un_comtrade.jsonl`, `experiments/industry/EXP_H4_INDUSTRY.json`, `reports/INDUSTRY_DATA_REPORT.md`.

**[RECOMMENDATION]** Before #30 merges: replace the value in those 4 files with a pointer to the already-correct report language, and make `build_policy.py` emit a redaction marker instead of the literal. This is a docs+tooling change, no history rewrite, and it removes the last Comtrade-derived bytes from the only branch that is otherwise clean.

### 2.6 Exposure timeline — how fast this happened

**[FACT]** Reading the four commits unique to `origin/research/horizon-001` in order:

| # | Commit | Date (Asia/Shanghai) | Effect on restricted material |
|---|---|---|---|
| 1 | `18a7580` | 2026-11-10 07:34:17 | introduces **all 30 Comtrade paths** + 1,826-file acquisition in a single commit |
| 2 | `4c8d8f9` | 2026-11-11 01:36:37 | amends reports/numbers; the derived Comtrade cell remains in `INDUSTRY_DATA_REPORT.md:127` and `EXP_H4_INDUSTRY.json:140` |
| 3 | `dd79693` | 2026-11-11 01:37:26 | drops a transient commit-message file (housekeeping only) |
| 4 | `2dcdc99` | 2026-11-11 01:37:46 | restores the root `.gitignore` to `main`'s version (declared out of write scope) |

**[FACT]** The restricted payload was therefore published in **one** commit, and the following three commits did not touch it. **[INFERENCE]** The exposure window is not "one reckless commit followed by a fix": there was never a remediation commit on this branch. The only remediation in the repository exists on a *different* branch (`3c3a295`, §2.5) and explicitly declines to modify the source branch ("No source branch is modified by this commit"). **[FACT]** The in-repo review states the branch is "already pushed to the public remote" and that "deleting history cannot un-publish what has been published". **[UNVERIFIED]** Whether any third party has cloned or forked in that window: unknowable locally.

**[INFERENCE]** Sequencing matters for the owner decision: because the payload predates the quarantine by one day and the quarantine is on a sibling branch, merging #30 **today** would not import the bytes, but leaving #29 open keeps them continuously fetchable. The cheapest correct action is to stop treating #29 as mergeable and treat #30 (post-redaction) as the delivery vehicle.

---

## 3. Committed-data inventory across `main` and open branches

### 3.1 Method and scale

**[FACT]** Listing 24 refs produced 32,232 tree entries. By extension: 6,320 `.json` (400.6 MB aggregate across refs), 270 `.jsonl` (175.9 MB), 138 `.gz` (43.9 MB), 110 `.csv` (12.1 MB), 12 `.pkl` (48.2 MB), 4 `.xml` (6.1 MB), 2 `.sqlite` (24 KB), 2 `.zip` (1.0 MB). **960 data files exceed 100 KiB; 3,093 data files exist on some branch but not on `main`.** Sizes below are Git **blob** sizes (what a clone transfers), not CRLF-expanded worktree sizes.

**[FACT]** Per-branch committed-data footprint (`data` = the extension set above; duplicates across branches are the same blobs):

| Branch | Files | Data files | Data bytes |
|---|---:|---:|---:|
| `research/horizon-001` | 1,826 | 647 | 82.8 MB |
| `integration/convergence-001` | 1,948 | 653 | 78.7 MB |
| `research/s029-evidence-based-relations` | 1,474 | 348 | 77.3 MB |
| `research/phoenix-003-early-evidence` | 1,238 | 188 | 61.9 MB |
| `research/phoenix-002-h8-validation` | 1,360 | 246 | 47.3 MB |
| `research/phoenix-001-round2` | 1,301 | 221 | 43.8 MB |
| `research/s031-hiring-capability-study` | 1,727 | 408 | 35.8 MB |
| `research/innovation-signals-observatory` | 1,695 | 401 | 35.3 MB |
| `research/data-expansion-001` | 2,050 | 887 | 23.6 MB |
| `integration/phase4-base` | 1,602 | 363 | 20.2 MB |
| `main` | **1,135** | **162** | **12.5 MB** |
| *(remaining 14 branches: 11.2–17.6 MB each)* | | | |

**[FACT]** `main` carries **no `raw/`, `DATASETS/` or `samples/` raw-payload tree**. Its 162 data-extension files are `config/*.json` (curated catalogues), `experiments/*/**.json` (derived experiment outputs), `docs/{metrics,summary}` (derived publication artefacts) and one 7,198 B test fixture of Yahoo price bars. **[INFERENCE]** The `research/DATA_PROVENANCE.md` §5 claim that "redistribution of raw bulk downloads and the SQLite stores is not committed" holds **for `main`** and is falsified **for three branches** (§3.4–3.6).

### 3.1a What is deliberately **not** committed (the absence inventory)

Absence matters as much as presence for a rights audit, because the unsafe option is usually to "just commit the snapshot so it reproduces".

| Asset | Route referenced in committed docs | Committed? | Consequence |
|---|---|---|---|
| `data/research.sqlite` — **289,443,840 B** (`db_sha256` recorded) | `config/universe_v1.json → source.db_path` | **No** | `universe_v1.json` is unreproducible from a clone; only row counts survive (§4.2 P3) |
| `medradar/data/medradar.sqlite` — 375,378 events, ~1.2 GiB claimed | `research/DATA_PROVENANCE.md` §3 | **No** | README headline counts unverifiable (C4) |
| EDGAR 8-K corpus — 20,976 filings | `README.md:28`, `DATA_PROVENANCE.md` §3 | **No** | only classified/derived artefacts committed |
| Yahoo full price series — 95,725 bars | `DATA_PROVENANCE.md` §2 | **No** (only the 60-bar fixture) | correct rights posture, poor reproducibility |
| USPTO patent corpus | `DATA_PROVENANCE.md` §2 — "0 rows, NOT COLLECTED" | **No** | declared gap; no key obtained |
| Hiring corpus | `DATA_PROVENANCE.md` §2 — "0 rows, NOT COLLECTED" | **No** on `main`; **35.8 MB** on #21/#22 | contradiction between `main` docs and branches (§4.2 P6) |
| Qwen3-4B model weights | `research/local-llm-foundation` | **No** | correct: no model-licence question arises |
| `.env` / credential stores | — | **No** (§5.2) | correct |

**[FACT]** The extension census across all 24 refs found **0** model-weight files (`*.safetensors|gguf|bin|pt|ckpt|onnx`), **0** `.env`-class files, **2** `.sqlite` files (both 12,288 B fixtures under `experiments/phoenix/rea/fixtures/`) and **2** `.zip` files (both exactly 524,288 B, truncated sample downloads on `data-expansion-001`). **[INFERENCE]** The repository's instinct is to keep bulk stores out of Git; the failures are not "we committed our database" but "we committed somebody else's payload as evidence". That is the cheaper failure to remediate — delete payloads, keep provenance — but only if a gate enforces it.

### 3.2 Raw vs derived vs cache — how to tell them apart in this repo

**[FACT]** Three shapes recur and are distinguishable by path convention:

| Shape | Convention | Redistributable as committed? |
|---|---|---|
| **Raw upstream payload** | `DATASETS/<workstream>/<source>/raw/*`, `samples/<source>/*`, `data/raw/*.json.gz` | Only if the source licence allows redistribution of the material itself |
| **Derived record export** | `exports/<id>/*.jsonl` + `MANIFEST.json` + `*.sha256` | Often yes, but a derived record that reproduces the source's values is still redistribution (§2.4) |
| **Computation cache** | `**/_chunks/*.pkl`, `**/cache/*.pkl`, `track_panel_*.pkl` | Yes — no third-party expression survives, but provenance is lost |

**[FACT]** The largest cache artefacts are 12 `.pkl` files (48.2 MB aggregate) under `experiments/phoenix/hypotheses/{cell,track}/…` on `phoenix-001-round2` / `phoenix-002-h8-validation`; they are derived model inputs/outputs, not source data.

### 3.3 Does each artefact carry its own rights metadata?

**[FACT]** Yes on `horizon`/`convergence`, no elsewhere. `DATASETS/**/PROVENANCE.json` records per-file `bytes`, `sha256`, `requested_url`, `final_url`, `status`, `content_type`, `fetched_at`; the export `MANIFEST.json` records per-source `sha256`, `bytes`, `records` plus `reproduce_command`; each export line carries `licence_status`. **[FACT]** By contrast, `docs/metrics.json` and `docs/summary.csv` on `main` carry **no** per-artefact hash and no licence field (§4.2).

### 3.4 RED — `research/data-expansion-001` (PR #27): a second UN Comtrade redistribution

**[FACT]** This branch commits **4 UN Comtrade preview payloads totalling 255,265 B** under `research/data_expansion/samples/un_comtrade/`:

| Path | Bytes | Content |
|---|---:|---|
| `preview_9018.json` | 114,128 | 127 partner-level trade records, `primaryValue`/`cifvalue` populated |
| `preview_9022.json` | 72,705 | trade records |
| `preview_9402.json` | 63,029 | trade records |
| `developer_portal.html` | 5,403 | scraped portal page |

**[FACT]** Structure of `preview_9018.json`: `{"elapsedTime":"0.03 secs","count":127,"data":[…],"error":""}`, each row carrying `reporterCode`, `cmdCode`, `flowCode`, `period`, `cifvalue`, `fobvalue`, `primaryValue`, `netWgt`. This is the same class of material as §2.2, obtained from the same keyless endpoint, published on a different branch.

**[FACT]** The branch's own policy (`research/data_expansion/LICENCE_AND_COST_AUDIT.md`) admits sample slices to Git under a `PARTIAL` heading, with the stated rule "只提交极小切片 + 哈希 + 获取脚本" ("commit only a very small slice + hash + fetch script") and a per-file cap of 512 KiB. **[FACT]** The branch also commits payloads from other sources its sibling branch classifies as non-redistributable: `samples/epo_ops/official_docs.html` 524,287 B (exactly at the stated cap), `samples/eu_ctis/ctis_retrieve.json` 137,298 B, `samples/us_census_trade/trade_api_docs.html` 319,982 B, `samples/google_patents_bigquery/bigquery_public_data.html` 141,451 B.

**[FACT]** Cross-branch register disagreement on the same sources (`docs/refoundation/_evidence/data/source_registers.tsv`): `un_comtrade`, `epo_ops`, `eu_ctis`, `usitc_dataweb` read `PARTIAL` on data-expansion but `may_redistribute=false` on convergence; `brazil_anvisa` reads `UNKNOWN` vs `may_redistribute=true`; `importgenius` reads `requires_licence` (horizon) vs `terms_restricted` (convergence). **[INFERENCE]** There is no single authoritative rights decision in this repository: the most permissive register sits on the branch with the second-largest sample payload count (887 data files), and it has no gate.

**Verdict: RED.**

### 3.5 RED — `research/phoenix-003-early-evidence` (PR #26): Europe PMC abstracts, mostly non-OA

**[FACT]** Two committed corpora:

| Path | Compressed | Uncompressed | Records | `is_open_access=false` | With abstract | Email occurrences |
|---|---:|---:|---:|---:|---:|---:|
| `experiments/phoenix003/dataset/epmc_compact.jsonl.gz` | 11.3 MB | 40.6 MB | 13,980 | **8,383** | 13,119 | 1,659 |
| `experiments/phoenix003/dataset/epmc_ext_compact.jsonl.gz` | 17.7 MB | (extended) | 22,664 | **14,239** | 20,652 | 6,323 |

**[FACT]** Record fields include `abstract` (full abstract text), `author_string`, `firm_affiliations` (e.g. an author affiliation string containing a corporate e-mail address), `journal_title`, `is_open_access`, `doi`, `pmid`. **[FACT]** 22,622 of 36,644 records (61.7 %) are flagged non-open-access, yet their abstracts are committed in full. **[INFERENCE]** Europe PMC aggregates publisher content under per-record licences; the repo's own convergence register lists `europepmc` as `open_licence` *with* the note "per-record `license` preserved", but these corpora preserve no per-record licence field and include non-OA records. Wholesale republication of non-OA abstract text is not licensed by the aggregator's terms. **Verdict: RED** (remediable by dropping `abstract` and keeping metadata, or by filtering to `is_open_access=true`).

### 3.6 AMBER — `research/s029-evidence-based-relations` (PR #16): bounded version of the same problem

**[FACT]** 77.3 MB of data, including ~130 `data/raw/ctgov_*.json.gz` and ~150 `data/raw/epmc_*.json.gz` API caches, plus `data/request_log.jsonl` (3,175,137 B) and `data/ror_cache.json.gz` (2,389,752 B). **[FACT]** Sampled raw files contain `abstractText` for records with `isOpenAccess: "N"` (verified on `epmc_medtronic_y2024.json.gz` and `epmc_philips_y2023.json.gz`), 10 records per file. **[FACT]** The **derived** export is cleaner: `data/epmc_pubs.jsonl` (770 records) carries bibliographic metadata, authors and affiliations but **no `abstract` field**. **[FACT]** `data/request_log.jsonl` records URL/status/bytes/sha256/timings with no header, cookie or token fields.

**[FACT]** `ctgov_trials.jsonl` (8.36 MB), `ctgov_sites.jsonl` and the ctgov raw caches are ClinicalTrials.gov material — US public domain, redistributable. ROR (`ror_cache.json.gz`) is CC0.

**[INFERENCE]** The exposure is bounded (≈1,300 cached records vs 36,644 on phoenix-003) and the derived layer already strips abstracts; deleting `data/raw/` would remove it with no analytical loss, since `REPRODUCE.md` and `request_log.jsonl` allow re-fetch. **Verdict: AMBER — merge only after either (a) `data/raw/` is dropped, or (b) the owner accepts the bounded non-OA cache.**

### 3.7 AMBER — job-posting text (#21 `research/innovation-signals-observatory`, #22 `research/s031-hiring-capability-study`)

**[FACT]** `jobs_medtronic.jsonl` = **9,483,509 B** (994 postings), plus `jobs_ge_healthcare.jsonl` 600,059 B, and equivalents for Philips, Dräger, Mindray; ~35.8 MB of data on the branch. Each record carries the **full** `job_description` (one sampled record is 15,070 characters) plus `content_sha256`, `source_url`, `source_platform`, `source_posted_at`. **[FACT]** `docs/SOURCE_DISCOVERY.md` documents the access route per host (Workday, Phenom sitemaps, Beisen JSON API), including robots.txt status and a stated rule never to bypass access controls; the probe totals 23 + 35 requests. **[FACT]** `config/nmpa_demo_seed.csv` on `main` is explicitly fictional ("虚构演示数据 … 非NMPA真实记录"), so NMPA contributes no real data anywhere.

**[INFERENCE]** robots.txt permission establishes the right to *fetch*, not the right to *republish* an employer's copyrighted recruitment copy. No licence or terms analysis for job text exists on either branch (a content grep for licence/terms hits only the postings' own text). Volume is large and the text is expressive, not merely factual. **Verdict: AMBER.** Recommended remediation: keep structured fields (title, ids, dates, location, `content_sha256`) + short excerpts + a re-fetch script; do not ship 9.5 MB of verbatim employer copy.

### 3.8 AMBER — Yahoo price series on `main`

**[FACT]** `tests/fixtures/prices/yahoo_chart_MDT_1y_trimmed.json` (7,198 B) contains a trimmed Yahoo `chart` response: `result[0].timestamp` with **60 daily bars**, `meta.{symbol,currency,exchangeName,instrumentType,timezone}`, `exchangeTimezoneName`. **[FACT]** `research/DATA_PROVENANCE.md` §2 records "Market bars (Yahoo adjusted) 95,725" used as a weak signal; the SQLite store holding them is not committed. **[INFERENCE]** Exchange-derived price series are licensed to the vendor and redistribution is not granted; 60 bars for one symbol is de-minimis in volume but is still the same rights class. **Verdict: AMBER (low volume).** Remediation: replace with a synthetic series or keep only the schema.

### 3.9 GREEN — sources whose committed artefacts are redistributable

**[FACT]** `openfda_*` (public domain / CC0, 560 records across four device endpoints), `accessgudid` (320), `clinicaltrials_gov` (164), `nih_reporter` (64), `openalex` (60, CC0), `openaire` (59, CC-BY 4.0), `europepmc` metadata-only use (37), `eurostat_comext` (1,400, CC BY / Commission Decision 2011/833/EU), `uk_hmrc_trade` (100, OGL v3.0), `canada_mdall` (174, OGL-Canada 2.0), `cipo_canada` (2,000, OGL-Canada 2.0). Attribution is mandatory for the OGL/CC-BY set and is **not** currently emitted anywhere in the repository (§7.3).

---

## 4. Provenance and traceability — can a published number be traced?

### 4.1 What exists (strong)

**[FACT]** On `horizon`/`convergence`, each raw file has `PROVENANCE.json` entries with `path`, `bytes`, `sha256`, `requested_url`, `final_url`, `status`, `content_type`, `fetched_at` (verified on the Comtrade set: 22 request URLs, 200s, timestamps to the second). **[FACT]** Each evidence record carries `content_hash`, `first_observed_at`, `fetched_at`, `source_url`, and an explicit `source_public_at: null` where the publisher exposes no publication date (with `quality_flags: ["MISSING_PUBLICATION_DATE"]`). **[FACT]** The export directory carries `MANIFEST.json` (`export_id: horizon-2026-11-10`, `schema_version: horizon.evidence.v1`, `generated_at`, `generator`, `reproduce_command`) listing per source `sha256`, `bytes`, `records` — plus a `.sha256` sidecar per `.jsonl`. **[FACT]** `research/DATA_PROVENANCE.md` on `main` is an unusually honest timing document: it distinguishes event time, publication time, first-seen, available-at, knowledge cutoff, and marks USAspending `pit_usable=0`, USPTO `0 rows — NOT COLLECTED`, hiring `0 rows — NOT COLLECTED`.

**[INFERENCE]** For `horizon`/`convergence`, a published number can in principle be traced: value → `source_url` + `content_hash` → `PROVENANCE.json` sha256 → export `MANIFEST.json` sha256 → commit. That is a better chain than most research repositories achieve.

### 4.2 What is missing (gaps)

| # | Gap | Evidence | Severity |
|---|---|---|---|
| P1 | `docs/metrics.json` has `generated_at: 2026-10-31T05:31:22Z` but **no** commit, snapshot hash, schema version or dataset hash | top-level keys: `meta, device, drug, cn_gap, signals, alerts, timestamps, research, replay, products, cases, trading` — no provenance block | high |
| P2 | `docs/summary.csv` has **no** header metadata at all (first column is `section`) | 68,460 B, 25 columns, no `# generated` line | high |
| P3 | `config/universe_v1.json` embeds the *source* pointer as an **absolute local path** (`<REDACTED_LOCAL_PATH>) plus `db_path=data\research.sqlite` and `db_sha256`, but **the 289,443,840-byte SQLite store is not committed** | `config/universe_v1.json` → `source` object | high |
| P4 | README's headline counts (375,378 events, 20,976 8-K filings, 678/625 tests, 1.2 GiB SQLite) cannot be reproduced from a clean clone: the DB and the EDGAR corpus are absent | `_FACTS.md` C4; `research/DATA_PROVENANCE.md` §3 | high |
| P5 | `research/STATE.json`, `research/AUDIT.json`, `research/FINAL_AUDIT.json`, `research/BACKLOG.yaml` are four competing state sources with no stated precedence | `_FACTS.md` C8 | medium |
| P6 | `research/DATA_PROVENANCE.md` §2 says hiring and USPTO were "NOT COLLECTED", but branches #21/#22 collect hiring and `horizon`/`data-expansion` collect patents — no cross-branch provenance reconciliation exists | compare §2 table with branch content | medium |
| P7 | Export `.sha256` sidecars exist but no CI job or test verifies them (`manifest` files exist on 10 branches; a verifying test exists only on `convergence`) | `tests/` inventory per branch | medium |

**[RECOMMENDATION]** Add a mandatory `provenance` block to any published artefact (`{generated_at, git_commit, snapshot_id, dataset_sha256, source_list, reproduce_command}`), and a CI check that `docs/metrics.json`/`docs/summary.csv` carry it. Add `config/universe_v1.json`'s derivation as a committed **recipe + row hashes**, never an absolute path.

---

## 5. Privacy, credential and secret scan

### 5.1 Method

**[FACT]** Scanned **all 24 audited refs**, not the 4 refs used by the in-repo review: 4,199 distinct blobs (deduplicated across refs), 3,896 text blobs read byte-exact through `git cat-file --batch`, 296 binary skipped by extension/magic, 7 skipped as >6 MiB. 8 path rules (`.env`, `.netrc`, `.pypirc`, `.npmrc`, SSH private keys, `*.pem|key|p12|pfx|jks|kdbx|ppk`, `.git-credentials`, credential/secret stores) and 9 content rules (PEM private-key blocks, AWS `AKIA…`, GitHub `gh[pousr]_…`, OpenAI-style `sk-…`, Slack `xox…`, Google `AIza…`, JWT triples, `Authorization: Bearer`, hard-coded credential assignments). **Matched values were never written to output**: the triage report prints masked context only.

### 5.2 Result — no credentials, 9 raw hits, 9 false positives

**[FACT]** 0 critical/0 high findings survive triage; 4 medium hits are also false positives.

| Rule | Path | Triage |
|---|---|---|
| `private_key_block` | `tools/convergence/licence/secrets_scan.py` | **FP** — the scanner's own regex literal for the PEM header |
| `openai_style_key` | `research/horizon/DATASETS/regulatory/_discovery/mhra_devices.html` | **FP** — `sk-` inside a gov.uk SVG asset filename (`…icon-mask-c…svg`) |
| `google_api_key` | `research/data_expansion/samples/google_patents_bigquery/bigquery_public_data.html` | **FP** — third-party public docs page; key is Google's, public-by-construction |
| `openai_style_key` | `config/universe_v1.json` (23 refs) | **FP** — `sk-` inside opaque entity keys (`…tsk-l…`) |
| `openai_style_key` | `experiments/detect_v1/entries.json` (23 refs) | **FP** — same entity-key pattern |
| `hardcoded_credential_assignment` | `research/horizon/DATASETS/industry/eu_ted/raw/api_docs_index.html` | **FP** — TED's own Algolia **search-only client-side** key (`data-api-key`), shipped to every browser |
| `hardcoded_credential_assignment` | `research/horizon/DATASETS/industry/importgenius/raw/terms_of_use.html` | **FP** — third-party Optibase analytics public key inside the vendor's page |
| `hardcoded_credential_assignment` | `tests/test_llm_research_adapters.py` (2 variants) | **FP** — dummy literal in a test |

**[FACT]** No `.env`, `.netrc`, `.pypirc`, `.npmrc`, private key, keystore or credential store exists on any of the 24 refs (path-rule counts: zero). **[FACT]** Query strings in probe logs carry only documented placeholders (`api_key=DEMO_KEY`, `api_key=test`). **[FACT]** The only project-owned identifier published is the deliberate alias `[EMAIL_REDACTED]`; commit identity `ChazY11 <[EMAIL_REDACTED]>` is public institutional metadata present on every branch.

**[INFERENCE]** This corroborates the in-repo review's secrets conclusion while extending its scope from 4 refs to 24. **No credential rotation is required.**

### 5.3 Personal data — present, low sensitivity, unevenly mitigated

**[FACT]** Occurrence counts (distinct strings counted per file; a global union was not materialised, so totals are lower bounds):

| Concentration | Occurrences | Distinct | Nature | Assessment |
|---|---:|---:|---|---|
| `research/convergence/licence/secrets_scan.json` | 608 | 211 | the **scanner's own report** lists the e-mail strings it found as evidence | republishes the PII it catalogues — a self-inflicted copy |
| `research/studies/relation_network_s029/data/epmc_pubs.jsonl` | 504 | **417** | author e-mails inside affiliation strings (Europe PMC) | real PII, low sensitivity, already published upstream |
| `research/horizon/DATASETS/scholarly/clinicaltrials_gov/CTGOV_INDEX.json` | 180 | 154 | `centralContacts[]` names/phones/e-mails | deliberate recruitment contact data |
| `.../uk_find_a_tender/raw/award_packages_p1..p3.json` | 415 (133+139+143) | **248** | OCDS `parties[].contactPoint` — named buyers' work e-mails | largest single concentration; **the 3 raw packages are not on `convergence`** |
| `.../pubmed_eutils/raw/efetch_trial_referenced_pmids.xml` | 111 | 99 | corresponding-author e-mails | published bibliographic data |
| `research/studies/.../s029/data/company_mentions.jsonl`, `entities.jsonl` | 180 / 118 | 96 / 99 | institution/author contacts | low sensitivity |
| `data-expansion-001` `samples/eu_ctis/ctis_retrieve.json` | 78 | 40 | trial sponsor contacts | low sensitivity |

**[FACT]** 7,982 e-mail occurrences appear inside the phoenix-003 Europe PMC corpora (§3.5). **[FACT]** No patient data, medical record number, national ID or health record was found; the `MRN` and "medical record" hits are product-catalogue abbreviations and device descriptions. **[INFERENCE]** The privacy exposure is republication of already-public *professional* contact data — a second processing operation, not a breach. It is nonetheless a governance defect on a public repository, and it is concentrated in exactly the files recommended for removal on rights grounds anyway.

**[RECOMMENDATION]** (i) strip the contact blocks when dropping the 3 UK FTS raw packages; (ii) delete `research/convergence/licence/secrets_scan.json` from the merge set or replace e-mail strings with hashes — a scanner that prints what it finds is a disclosure channel; (iii) if non-OA abstract handling is fixed per §3.5, 7,982 of the e-mail occurrences disappear with it.

---

## 6. Data quality and validation — what exists, what is missing

### 6.1 Existing controls

**[FACT]** By artefact count per branch (`docs/refoundation/_evidence/data/` inventory): `integration/convergence-001` 101 governance artefacts (6 schema, 7 validator, 3 contract, 11 manifest, 43 provenance, **3 gate**, 5 quality, 26 licence); `research/horizon-001` 77; `research/phoenix-002-h8-validation` 85 (63 validator files); `research/s031-hiring-capability-study` 61; `main` 25 (3 schema, 6 validator, 10 manifest, 4 provenance).

**[FACT]** The strongest control is on `integration/convergence-001`: `tools/convergence/licence/licence_gate.py` classifies **every file declared in `MANIFEST.json`**, re-verifies its declared SHA-256 against bytes on disk, lists undeclared files (so a payload cannot be smuggled in uninventoried), and returns distinct exit codes — `VIOLATION`=1 (restricted payload present), `MISSING-EXPECTED`=2 (declared file absent), `UNKNOWN-SOURCE`=3. `config/convergence/licence_policy.json` holds per-source `may_query` / `may_ingest` / `may_analyse_locally` / `may_redistribute` / `redistribution_condition` / `attribution_text` / `checked_at` / `verification`, plus the 30-path quarantine list. `docs/convergence/EVIDENCE_CONTRACT.md` states the evidence schema contract.

**[FACT]** On `main`: `docs/SCHEMA.md`; `experiments/b026/validate_{hiring,track}_domain.py` + logs (domain validation); `experiments/b027/snapshots/*/manifest.json` (6 snapshot manifests); `experiments/reverse_rd_v1|v2/data_provenance.json`; `research/DATA_PROVENANCE.md`; `tests/` includes offline contract tests. **[FACT]** `horizon` adds per-source `PROVENANCE.json` and export manifests; `s029` adds `DATA_QUALITY_REPORT.md`; `phoenix-003` adds `verify_attribution.py` + console logs.

### 6.2 Missing controls

| # | Missing control | Consequence | Label |
|---|---|---|---|
| Q1 | **No repository-wide rights policy.** Three registers disagree (§3.4); the gate exists only on `convergence` | a new branch can ingest a `may_redistribute=false` source with no failing check | FACT |
| Q2 | No licence gate wired into CI on `main` or on any research branch except `convergence` (3 gate artefacts exist on 1 branch of 24) | the #29 payload was committed without any check firing | FACT |
| Q3 | No schema/contract for the **evidence record** shared across branches: `horizon.evidence.v1` exists on `horizon`/`convergence`; S-029/S-031/phoenix use different shapes | cross-branch joins silently degrade | FACT |
| Q4 | **No provenance requirement** on published artefacts (§4.2 P1–P2) | headline numbers untraceable from a clean clone | FACT |
| Q5 | **No PII rule or test** anywhere; the only PII scanner lives on one branch and its report is itself a PII file | contact data can be re-vendored freely | FACT |
| Q6 | No per-record licence field preserved for Crossref/Europe PMC, despite the registers claiming record-level licences are respected | the claim is unverifiable at record level | FACT |
| Q7 | No retention/volume budget: single blobs up to 20 MB (`claims.jsonl`) and per-branch data up to 82.8 MB with no cap or LFS policy | clone size and irreversible content growth | FACT |
| Q8 | No "rights status" field on the data assets themselves; status lives in branch-local docs | a merge carries the bytes but not the verdict | FACT |

**[RECOMMENDATION]** Promote `config/convergence/licence_policy.json` + `licence_gate.py` to repository-wide, inherit them on `main`, and require the gate to pass in CI for every branch that commits data. Add a PII rule class and a per-artefact `rights_status` field. Cap committed data per PR and route bulk payloads to a release artefact or a re-fetch recipe.

---

## 7. Repository licensing

### 7.1 `LICENSE` file vs GitHub classification

**[FACT]** `LICENSE` (1,328 B, blob `df6209cc…` — **identical on all 24 refs**) is the standard MIT text with `Copyright (c) 2026 MedRadar contributors`, **followed by an appended "Data notice" paragraph**: "*MedRadar consumes public-domain FDA openFDA endpoints, ClinicalTrials.gov, and (optionally) SEC EDGAR. Those datasets carry their own terms; MedRadar does not redistribute bulk source data. Nothing in this project is investment advice.*"

**[FACT]** `pyproject.toml` declares `license = { text = "MIT" }` and `version = "0.5.0"`. **[FACT]** `_FACTS.md` §1 records GitHub's licence detection as `other` / "Other" while the file is MIT — contradiction C2.

**[INFERENCE — candidate explanation, not verified]** The most likely cause is the appended non-MIT paragraph inside `LICENSE`, which breaks a whole-file licence match, compounded by a non-canonical copyright line. **[UNVERIFIED]** The GitHub-side classifier cannot be re-run from here; the `other` reading is taken from `_FACTS.md`'s recorded API response, not re-fetched.

**[RECOMMENDATION]** Split the data notice out of `LICENSE` into `NOTICE`/`DATA_LICENCES.md`, set `license = "MIT"` (PEP 639) and add `license-files`, then re-check the badge. This is metadata-only and does not change rights.

### 7.2 The appended data notice is factually false on three branches

**[FACT]** "MedRadar does not redistribute bulk source data" is true of `main` (§3.1) and false of `research/horizon-001` (82.8 MB, incl. 24 raw source trees), `research/data-expansion-001` (887 data files, 59-source sample registry) and `research/s031-hiring-capability-study` (35.8 MB incl. 9.5 MB of verbatim job text). **[FACT]** `research/DATA_PROVENANCE.md` §5 repeats a narrower and accurate version ("redistribution of raw bulk downloads and the SQLite stores is not committed; only small aggregates, config and reproduction commands are") — accurate for `main`, not for branches.

**[INFERENCE]** Because `LICENSE` travels with every branch, merging any of the three branches makes the shipped `LICENSE` a false statement about the shipped repository. That is a governance defect independent of whether any publisher complains.

### 7.3 Third-party notices: `docs/ATTRIBUTION.md` is a *development* attribution, not a data attribution

**[FACT]** `docs/ATTRIBUTION.md` exists on all 24 refs and documents **who wrote the code** (agent team, models, per-phase contributions) and explicitly records that "专利/招聘仍是明确的证据缺口" (patents/hiring remain declared evidence gaps). It contains **no** per-source licence text, no OGL/CC-BY/CC0 attribution statement and no third-party data notice. **[FACT]** No `NOTICE`, `THIRD_PARTY_NOTICES`, `COPYING` or `DATA_LICENCES` file exists on any ref (`git ls-tree -r` filename search returns only `LICENSE` and `docs/ATTRIBUTION.md`).

**[FACT]** Attribution is nonetheless *required* by several licences the repo relies on: OGL-Canada v2.0 (Canada MDALL, CIPO — 2,174 records), OGL v3.0 (UK HMRC, UK FTS), CC-BY 4.0 (OpenAIRE, EU CORDIS), Eurostat reuse decision (1,400 records). **[FACT]** The only branch that emits attribution text is `convergence`, and only inside machine-readable policy (`attribution_text` per source) plus `research/convergence/identity/COVERAGE_AND_ATTRIBUTION.json` and `phoenix-003`'s `verify_attribution.py`. **[FACT]** Nothing in the rendered README, dashboard or reports carries the required attribution.

**[INFERENCE]** The repository is therefore in breach of the attribution condition of several otherwise-permissive licences, on every branch including `main`, wherever those records are surfaced.

### 7.4 Is the data licence-compatible with MIT code?

**[INFERENCE]** MIT covers the *code*. It does not, and cannot, relicense third-party data. The correct model is a split licence: MIT for code, per-source terms for data, with a machine-readable data manifest. The repository already contains the building blocks for this on one branch (`licence_policy.json` + gate) and nowhere else. **[FACT]** MIT contains no patent grant; the data-expansion branch's own audit correctly notes this and adds that "若将来引入专利敏感方法需单独处理" (patent-sensitive methods would need separate handling).

---

## 8. Data-asset register and merge safety

### 8.1 Source register (rights verdict per source)

**Verdict key:** **GREEN** = explicit public-domain/open licence, redistribution permitted (attribution conditions noted) · **AMBER** = redistribution permitted only on an unaffirmed/caveat basis, or a bounded volume exists whose licence is unclear · **RED** = committed material that must not be redistributed.

| # | Source | What is fetched | Licence / ToS (as committed) | Redistribution | Committed here? | Verdict |
|---:|---|---|---|---|---|---|
| 1 | openFDA device (510k/PMA/classification/registration) | Device clearances, classifications, listings | US public domain; openFDA data licensed **CC0 1.0**; GMDN carved out | Permitted, courtesy attribution | 560 records + raw JSON on `horizon` | **GREEN** |
| 2 | accessGUDID (NLM) | UDI/device identification | US federal dataset, no restriction stated | Permitted | 320 records + raw | **GREEN** |
| 3 | ClinicalTrials.gov v2 | Studies, sponsors, sites, contacts | Public domain, "not subject to copyright restrictions in the US" | Permitted | 164 + `CTGOV_INDEX` 102,843 lines + raw | **GREEN** (PII note) |
| 4 | NIH RePORTER | Awards | US federal, not copyrighted | Permitted | 64 | **GREEN** |
| 5 | openFDA bulk download | Bulk export catalogue | Public domain | Permitted | catalogue only | **GREEN** |
| 6 | USAspending | Contract awards | US federal contract data; **no reuse sentence found** | Permitted, caveat | 245 | **AMBER** |
| 7 | SEC EDGAR (Company Facts XBRL, 8-K) | Financial facts, filings | US public filings; SEC fair-access policy | Permitted | Derived only on `main`; **no raw corpus committed** | **GREEN** |
| 8 | Europe PMC | Bibliographic records + abstracts | ELIXIR Core Data Resource; per-record licence; abstracts remain publisher copyright | Metadata: permitted w/ attribution. **Non-OA abstracts: not licensed** | 36,644 records w/ abstracts (phoenix-003); 770 metadata (s029) | **RED** (abstract corpora) / **GREEN** (metadata) |
| 9 | PubMed E-utilities | Citations, affiliations XML | NLM public use; **no blanket licence**; abstract rights stay with publisher | Citation metadata only | 37 + raw XML (801,946 B) | **AMBER** |
| 10 | OpenAlex | Works, counts | **CC0 1.0** | Permitted | 60 + raw | **GREEN** |
| 11 | OpenAIRE | Research graph | **CC-BY 4.0** | Permitted w/ attribution | 59 | **GREEN** |
| 12 | Crossref | Work metadata | Metadata openly available; **no blanket licence**; per-record `license[]` governs | Caveat; preserve per-record licence | 59 + `CROSSREF_INDEX` | **AMBER** |
| 13 | Semantic Scholar | Graph API records | API terms; corpus ODC-BY; bulk redistribution restricted | Caveat, bounded sample | 56 + raw | **AMBER** |
| 14 | EU CORDIS | Project metadata | Commission reuse permitted; endpoint undocumented, no machine licence | Caveat | 60 | **AMBER** |
| 15 | EU TED | Procurement notices | Docs address "reusers"; **no formal licence sentence** | Caveat | 299 + raw search JSON | **AMBER** |
| 16 | Eurostat Comext | Trade in goods (HS) | **CC BY 4.0** / Decision 2011/833/EU, reuse authorised with acknowledgement | Permitted w/ "Source: Eurostat" | 1,400 + raw | **GREEN** |
| 17 | UK HMRC uktradeinfo | Trade statistics | **OGL v3.0** | Permitted w/ attribution | 100 + raw | **GREEN** |
| 18 | UK Find a Tender (OCDS) | Award notices | **OGL v3.0** declared in payload | Permitted w/ attribution; **raw carries 248 named buyers** | 62 derived + **3 raw pkgs (3,912,347 B)** on `horizon` only | **GREEN rights / AMBER PII** |
| 19 | Canada MDALL | Device licences | **OGL-Canada 2.0**, commercial use allowed | Permitted w/ attribution | 174 + raw | **GREEN** |
| 20 | CIPO Canada | Patent bibliographic records | **OGL-Canada 2.0** | Permitted w/ attribution | 2,000 (6.4 MB) | **GREEN** |
| 21 | EPO Publication Server | Patent bibliographic records | EPO terms; **no explicit reuse licence** | Derived records only, caveat | 228 + `COLLECT.json` 40,283 lines | **AMBER** |
| 22 | Brazil ANVISA | Device registrations | Open data, **no licence statement** | Caveat | 120 | **AMBER** |
| 23 | **UN Comtrade** | 608 country-total medical-HS4 trade cells + reference tables | **Usage Agreement §5** forbids copying, redistribution, publication, commercial exploitation w/o written permission | **PROHIBITED** | **30 paths / 6,234,301 B on `horizon`; 4 preview payloads / 255,265 B on `data-expansion`** | **RED** |
| 24 | Yahoo Finance | Daily/minute OHLCV bars | Vendor/exchange terms; redistribution not granted | Not licensed | 60-bar test fixture (7,198 B) on `main`; 95,725 rows in uncommitted SQLite | **AMBER** |
| 25 | Company career sites (Workday / Phenom / Beisen / Dräger portal) | Job titles, ids, dates, **full descriptions** | robots.txt permission to fetch; **no licence to republish** | Not established | 9.5 MB Medtronic + ~26 MB others (#21, #22) | **AMBER** |
| 26 | ROR | Institution registry | **CC0 1.0** | Permitted | `ror_cache.json.gz` 2.4 MB (s029) | **GREEN** |
| 27 | USPTO bulk data | Patent full text/bulk | US Government work, public domain | Permitted | **not materialised** (declared gap) | **GREEN** (proposed) |
| 28 | USPTO Open Data Portal | Patent search API | Free `X-API-KEY` registration required | Permitted w/ key; terms unread | **not materialised** | **AMBER** (key-gated) |
| 29 | PatentsView | Patent disambiguation | Key/registration; terms unread | Unknown | **not materialised** | **AMBER** |
| 30 | EPO OPS | Patent family/citations | Contract + OAuth consumer key | Requires licence | **not materialised**; docs page 524,287 B on `data-expansion` | **AMBER** |
| 31 | Google Patents BigQuery | Patent public dataset | GCP billing + OAuth; scraping contrary to terms | Requires account | docs HTML 141,451 B on `data-expansion` | **AMBER** |
| 32 | Lens.org | Scholarly–patent links | Terms v2026.06.01 + API approval; not blanket CC0 | Requires approval | not materialised (probe only) | **AMBER** |
| 33 | ImportGenius / ImportYeti / Panjiva / Descartes Datamyne | Bill-of-lading trade data | Commercial terms; ImportYeti robots disallows endpoints; Panjiva terms **403, unread** | Commercial licence only | terms pages + robots only (metadata) | **AMBER** |
| 34 | EU CTIS | Clinical trial records | Terms unread; convergence classes it non-redistributable | Unknown | `ctis_retrieve.json` 137,298 B on `data-expansion` | **AMBER** |
| 35 | US Census trade API | US trade statistics | Free key; **no reuse sentence found** | Caveat | docs HTML 319,982 B on `data-expansion` | **AMBER** |
| 36 | SAM.gov | Entity/opportunity data | Free key; account required | Unknown | docs page only | **AMBER** |
| 37 | NMPA (China) | Device registrations/UDI | 412 anti-automation; no public interface | Not obtained | **only fictional demo seed** (`config/nmpa_demo_seed.csv`) | **GREEN** (no real data) |
| 38 | Health Canada (MDALL) | Device licences | OGL-Canada 2.0 (same as #19) | Permitted w/ attribution | 174 | **GREEN** |
| 39 | MHRA / TGA / PMDA / MFDS / WHO ICTRP / EUDAMED / DPMA / JPO / EU CTIS / ISRCTN-class | Device/trial registers | Blocked, SPA/JSF shells, WAF, or no public register | Unknown — **silence not treated as permission** | registry-only, not materialised | **AMBER/UNVERIFIED** |
| 40 | Qwen3-4B-Instruct (local LLM) | Model used for labelling | Apache-2.0 upstream (not vendored) | n/a — **no weight file committed** | results/predictions only | **GREEN** |
| 41 | External research software (REA, SciTrends, PubTrends, CatBoost, pytest) | Methods reference | Isolated; MIT / Apache-2.0 / **none stated** (SciTrends) | Not vendored into repo | isolated worktree only | **GREEN** (not redistributed) |

**[FACT]** 40+ sources classified (the task asked for ≥10); the three registers together cover 69 distinct source ids (`source_registers.tsv`). **[FACT]** Verdict distribution on the 24 **materialised** sources: **14 GREEN, 8 AMBER, 1 RED, 1 dual** (Europe PMC — bibliographic metadata GREEN, abstract corpora RED). Five sources are **key-gated but not materialised**, so their terms were never exercised (§8.1a).

### 8.1a The key-gated patent paths (task item 1: "USPTO and any key-gated patent path")

**[FACT]** Eight distinct patent routes appear in the registers. **None** was ever authenticated: `research/data_expansion/LICENCE_AND_COST_AUDIT.md` §3 records that no account was created and no credential used ("本轮一个都没注册"), and `docs/ATTRIBUTION.md` records the USPTO adapter as "需 API key …（未评估）". **[FACT]** The only patent bytes actually committed come from two **anonymous** routes: EPO Publication Server (228 records + `COLLECT.json`, 40,283 lines) and CIPO Canada (2,000 records, 6,679,212 B) — plus one archived BigQuery documentation page (141,451 B) on `data-expansion-001`.

| Route | Gate | Terms status | Materialised? | Rights verdict |
|---|---|---|---|---|
| `uspto_bulkdata` | none (bulk files) | US Government work / public domain | no | **GREEN (proposed)** |
| `uspto_open_data_portal` | free `X-API-KEY` | terms not read | no | **AMBER** — key-gated, unexercised |
| `patentsview` | API key | terms not read | no | **AMBER/UNVERIFIED** |
| `epo_ops` | OAuth2 consumer key + secret, contract | contractual | no (docs page only) | **AMBER** — contract, not licence |
| `epo_publication_server` | anonymous | EPO terms; no explicit reuse licence | **yes** (derived records) | **AMBER** (derived-only mitigation already applied) |
| `google_patents_bigquery` | GCP project + OAuth + billing | scraping contrary to terms | no (docs page only) | **AMBER** |
| `lens_org` | institutional subscription / API approval | not blanket CC0 | no (probe only) | **AMBER** |
| `wipo_patentscope` | registered web services | not verified | no | **AMBER/UNVERIFIED** |
| `espacenet` | — | WAF anti-automation | no | **RED if forced** |
| `cipo_canada` (not USPTO) | anonymous | **OGL-Canada 2.0** | **yes** | **GREEN** (attribution required) |

**[INFERENCE]** The key-gated routes are arguably the *safer* ones from a rights standpoint — a subscription contract usually states permitted reuse, which anonymity never does — but they are also the routes on which the repository has **no first-hand terms evidence**. The honest status is **UNVERIFIED**, not GREEN, until someone reads the contract. **[RECOMMENDATION]** If USPTO coverage is required, prefer `uspto_bulkdata` (public domain, no gate, no contract) over the key-gated APIs, and record the terms text at time of first use.

### 8.2 Data-asset register (committed artefacts)

| Artefact | Branch | Bytes | Type | Rights status | Action |
|---|---|---:|---|---|---|
| `un_comtrade/raw/*.json` (24 files) | `horizon-001` | 2,437,673 | **raw** | **RED** — §5 prohibited | **remove / permission** |
| `un_comtrade.jsonl` (×2 copies) | `horizon-001` | 3,664,622 | derived (value-level) | **RED** | **remove / permission** |
| `un_comtrade` derived cell (5 files) | `horizon-001` | — | derived | **RED** | **remove** |
| Comtrade previews (3 files) | `data-expansion-001` | 249,862 | **raw** | **RED** | **remove** |
| `epmc_compact.jsonl.gz` + `epmc_ext_compact.jsonl.gz` | `phoenix-003` | 29.0 MB compressed | **raw (abstracts)** | **RED** for 22,622 non-OA records | **strip abstracts** |
| `data/raw/epmc_*.json.gz` (~150) | `s029` | ≈3 MB | raw cache (abstracts) | **AMBER** | drop `data/raw/` |
| `jobs_*.jsonl` | `s031`, `#21` | 9.5 MB + ~26 MB | **raw (full text)** | **AMBER** | keep structured fields only |
| `uk_find_a_tender/raw/award_packages_p1..p3` | `horizon-001` | 3,912,347 | **raw** | GREEN rights / **AMBER PII** | drop (not consumed) |
| `cipo_canada.jsonl` | `horizon`, `convergence` | 6,679,212 | derived | GREEN (OGL-Canada, attribution required) | add attribution |
| `eurostat_comext.jsonl` | `horizon`, `convergence` | 4,096,452 | derived | GREEN (CC BY, attribution required) | add attribution |
| `CTGOV_INDEX.json` | `horizon`, `convergence` | 4,249,609 | raw/derived | GREEN (public domain), PII contacts | redact contacts |
| `yahoo_chart_MDT_1y_trimmed.json` | `main` + 23 | 7,198 | **raw vendor series** | **AMBER** | synthetic replacement |
| `*.pkl` caches (12) | phoenix | 48.2 MB | cache | GREEN | keep (add hash) |
| `claims.jsonl` | `s029` | 20,947,367 | derived | GREEN (authored analysis) | keep |
| `docs/metrics.json`, `docs/summary.csv` | `main` | 468,561 / 68,460 | derived publication | GREEN rights / **AMBER provenance** | add provenance block |
| `config/universe_v1.json` | `main` + 23 | 1,711,167 | derived config | GREEN rights / **AMBER path leak** | remove absolute path |
| `config/nmpa_demo_seed.csv` | all | small | **synthetic** | GREEN (explicitly fictional) | keep |
| `research/convergence/licence/secrets_scan.json` | `convergence` | small | **PII report** | **AMBER** (republishes 211 addresses) | hash the addresses |

### 8.3 Do-not-merge list (rights standpoint)

**RED — do not merge until the named remediation lands:**

1. **`research/horizon-001` (PR #29).** 30 paths / 6,234,301 B of UN Comtrade under an explicit redistribution prohibition, **already pushed to the public remote**; plus the restricted derived cell in 2 additional files; plus 3 raw OCDS packages carrying 248 named individuals' work e-mails. Remediation: written permission from UNSD, or remove the 30 paths + the derived cell + the 3 OCDS packages and re-cut the branch.
2. **`research/data-expansion-001` (PR #27).** 4 Comtrade preview payloads (255,265 B) with trade values, on a branch whose own register unilaterally softens `terms_restricted` to `PARTIAL`; plus payloads from `epo_ops`, `eu_ctis`, `google_patents`, `us_census_trade` whose sibling policy classes them non-redistributable. Remediation: delete the 4 Comtrade files, reconcile the register to `licence_policy.json`, and add the gate.
3. **`research/phoenix-003-early-evidence` (PR #26).** 36,644 Europe PMC records of which 22,622 are non-open-access, with 33,771 abstracts committed verbatim (+7,982 author e-mail occurrences). Remediation: drop `abstract`, or filter to `is_open_access=true`, or cite by identifier only.

**AMBER — merge only with the stated condition:**

4. **`research/s029-evidence-based-relations` (PR #16).** ~150 raw Europe PMC caches containing non-OA abstract text. Condition: drop `data/raw/` (derived exports already clean) or obtain a written basis.
5. **`research/s031-hiring-capability-study` (PR #22)** and **`research/innovation-signals-observatory` (PR #21).** 9.5 MB + ~26 MB of verbatim employer job descriptions with no licence analysis. Condition: keep structured fields + excerpts + re-fetch recipe.
6. **`integration/convergence-001` (PR #30).** Payload verified absent, but the restricted derived cell survives in 5 files (incl. the machine-readable policy and its generator) and 248 named buyers remain in… **not** on this branch (the OCDS raws are absent) — PII is limited to ClinicalTrials/Europe PMC contacts. Condition: redact the 5-file leak first; then it is the only research branch close to mergeable.
7. **`main` + the 20 branches that only inherit `main`.** One 60-bar Yahoo price fixture and one absolute-path leak in `config/universe_v1.json`. Condition: replace the fixture with synthetic data; strip the path.

### 8.4 Explicit merge-safety statement

**[INFERENCE, from the register and the artefacts]** From a **data-rights** standpoint:

- **`main` is the only ref that is safe to merge/publish as-is**, and even it needs two cosmetic fixes (Yahoo fixture, absolute path) to be fully clean.
- **No open research branch is merge-ready as-is.** Three are RED (#29, #27, #26); four are AMBER-conditional (#16, #22, #21, #30).
- **The 16 branches that only inherit `main`** (#1, #12, #13, #14, #17–#20, #23–#25, #28, plus phase4-base, full-history-v1 and early-signal-ai-review) **add no new third-party data** — verified by listing their largest data files (all `main`-derived: `docs/dashboard.html`, `config/universe_v1.json`, `experiments/detect_v1/*`, derived S-028 prediction files). They are **GREEN on rights** and should not be blocked on data-governance grounds.
- **PR #30 is the correct destination** for #29's content *only after* the 5-file derived-value redaction; it already demonstrates that a data-bearing branch can be made clean.

**[RECOMMENDATION]** Adopt a three-state merge gate: (1) no file may be added unless a `licence_policy.json` entry exists with `may_redistribute` resolved; (2) `licence_gate.py` must exit 0 in CI; (3) any branch with a `RED` asset is labelled `do-not-merge` in the PR until remediated. That is the difference between a policy and a document.

### 8.5 Per-branch RAG, all 24 audited refs

**[FACT]** Verdicts below are *data-rights only* (they do not speak to code quality, test status or scientific validity). "Inherit" = largest committed data files are all `main`-derived; verified by listing each branch's top data files.

| Ref | PR | Data footprint | Rights verdict | Blocking item |
|---|---|---:|---|---|
| `main` | — | 12.5 MB | **GREEN, 2 cosmetic fixes** | 60-bar Yahoo fixture; absolute path in `universe_v1.json` |
| `feat/frontier-device-radar` | #1 | 1.2 MB | **GREEN (inherit)** | none |
| `feat/medradar-2.0-mvp` | #12 | 11.9 MB | **GREEN (inherit)** | none |
| `feat/live-observatory-v1` | #13 | 12.5 MB | **GREEN (inherit)** | none |
| `feat/observatory-reliability-v1` | #14 | 12.9 MB | **GREEN (inherit)** | none |
| `maintenance/repository-consolidation` | #17 | 11.9 MB | **GREEN (inherit)** | none |
| `research/ai-evidence-review` | #18 | 12.1 MB | **GREEN (inherit)** | none |
| `research/local-llm-foundation` | #19 | 12.3 MB | **GREEN (inherit)** | no model weights committed |
| `research/overnight-qlora-s030` | #20 | 13.6 MB | **GREEN (inherit)** | no model weights committed |
| `research/innovation-signals-observatory` | #21 | 35.3 MB | **AMBER** | 9.5 MB verbatim job text (§3.7) |
| `integration/phase4-base` | *(no PR)* | 20.2 MB | **GREEN (inherit)** | derived S-028 artefacts only |
| `research/s031-hiring-capability-study` | #22 | 35.8 MB | **AMBER** | verbatim job text (§3.7) |
| `research/s028-temporal-graph-early-signal` | #15 | 17.6 MB | **GREEN (inherit)** | derived predictions only |
| `research/s029-evidence-based-relations` | #16 | 77.3 MB | **AMBER** | ~150 raw Europe PMC caches w/ non-OA abstracts (§3.6) |
| `research/phoenix-001-external-methods` | #23 | 12.1 MB | **GREEN** | third-party software isolated, not vendored |
| `research/phoenix-001-round2` | #24 | 43.8 MB | **GREEN** | `.pkl` derived caches only (+1 EPMC crosscheck script) |
| `research/phoenix-002-h8-validation` | #25 | 47.3 MB | **GREEN** | `.pkl` derived caches only |
| `research/phoenix-003-early-evidence` | #26 | 61.9 MB | **RED** | 22,622 non-OA Europe PMC records with abstracts (§3.5) |
| `research/data-expansion-001` | #27 | 23.6 MB | **RED** | 4 Comtrade preview payloads + restricted-source samples (§3.4) |
| `foundation/atlas-001` | #28 | 12.3 MB | **GREEN (inherit)** | none |
| `research/horizon-001` | #29 | **82.8 MB** | **RED** | 30 Comtrade paths / 6,234,301 B (§2.2) |
| `integration/convergence-001` | #30 | 78.7 MB | **AMBER** | payload quarantined; derived cell in 5 files (§2.5) |
| `research/full-history-v1` | — | 13.7 MB | **GREEN (inherit)** | none |
| `research/early-signal-ai-review` | — | 16.5 MB | **GREEN (inherit)** | none |

**[INFERENCE]** Merge order that is both rights-safe and dependency-safe:

1. **Now:** `main` with the two cosmetic fixes; the 16 inheriting branches are unblocked on data-rights grounds wherever their code is ready.
2. **After redaction (§2.5), in this order:** `integration/convergence-001` (#30) → then any branch stacked on it. #30 is the only data-bearing research branch that has already done the hard part.
3. **After remediation, individually:** #16 (drop `data/raw/`), #21/#22 (drop full job text), #26 (strip abstracts), #27 (drop Comtrade previews, reconcile register), #29 (withdraw or obtain permission).
4. **Never as-is:** #29, #27, #26.

**[RECOMMENDATION]** Record this table in the DECISION_REGISTER so that merge approvals cite a rights verdict rather than an impression. A branch's RED/AMBER status should be a required field on the PR, not a paragraph in an audit file that reviewers may never open.

---

## 9. Open questions for the owner

1. **UN Comtrade (highest).** Do you intend to seek written permission from the UN Statistics Division (`[EMAIL_REDACTED]`), or to remove the 30 paths from PR #29? Note the branch is already public: removal limits future exposure but cannot un-publish. This decision also settles the **derived** cell in 5 files on #30 and the 4 previews on #27. *Owner-only; irreversible options exist (§2.5).*
2. **Europe PMC abstracts.** Is the phoenix-003 corpus intended as a publication artefact or as a local cache? If publication, will you strip `abstract` (keeping identifiers + metadata) or restrict to `is_open_access=true`? This single decision removes 61.7 % of the records from the rights question and 7,982 e-mail occurrences with them.
3. **Attribution.** Who authors the required OGL-Canada / OGL-v3 / CC-BY / Eurostat attribution notices, and where should they render (README, dashboard footer, per-export README)? The licences permit the use; only the notice is missing.
4. **A single rights policy.** Which register becomes authoritative — `config/convergence/licence_policy.json` (51 sources, gate-backed) or `GLOBAL_DATA_SOURCE_REGISTER.json` (59 sources, no gate)? They disagree on six sources today. Merging both without reconciliation will re-create the #27 ambiguity on `main`.
5. **Job text.** Is verbatim employer copy required, or are structured fields + short excerpts sufficient for S-031's inference? The analytical result does not obviously need 9.5 MB of marketing prose.
6. **PII posture.** The repo republishes professional contact data that is already public upstream. Do you want a stated rule (drop contact blocks on ingest; hash e-mails in audit reports), or is "already public" an accepted basis? A GDPR/UK-GDPR lawful-basis assessment is a lawyer's task and was **not** performed here.
7. **Licence metadata.** Approve moving the data notice out of `LICENSE` into a dedicated notice and setting PEP 639 `license = "MIT"`, so GitHub stops reporting `other` and the split between code and data rights becomes explicit.
8. **Historical retention.** GitHub-side retention of unreachable objects, caches and forks is unobservable from this clone. Do you want a GitHub Support request in scope if #29 is rewritten? *[UNVERIFIED from local evidence.]*
9. **Re-verification cadence.** Only three licence verdicts were ever checked against a live page (per the in-repo review); the remaining are as-of the archived capture dates in `PROVENANCE.json` (2026-11-09/11). What is the re-verification interval before new ingestion?

---

## 10. Method reproducibility

All collectors are committed under `docs/refoundation/_evidence/data/` and are read-only against Git and the network:

```powershell
# full tree listing for the 24 audited refs (writes ls_tree_all_branches.tsv)
#   -- see the loop in this audit's method; reproduce with:
git ls-tree -r -l origin/main        # per ref
python docs\refoundation\_evidence\data\analyse_trees.py
python docs\refoundation\_evidence\data\verify_pr29_exposure.py
python docs\refoundation\_evidence\data\census_data_expansion.py
python docs\refoundation\_evidence\data\extract_source_registers.py
python docs\refoundation\_evidence\data\scan_secrets_all_branches.py
python docs\refoundation\_evidence\data\triage_secrets.py
python docs\refoundation\_evidence\data\triage_medium.py
python docs\refoundation\_evidence\data\inventory_governance_artefacts.py
```

**Outputs:** `ls_tree_all_branches.tsv` (32,232 rows), `branch_data_totals.tsv`, `data_files_ge_100k.tsv` (960 rows), `data_not_on_main.tsv` (3,093 rows), `data_ext_histogram.tsv`, `source_registers.json` / `.tsv` (69 sources), `secrets_scan.json` (4,199 blobs), `LICENCE_AND_SECURITY_REVIEW.md.txt` (the in-repo review, extracted verbatim for cross-checking).

**Cross-check note.** Where this audit and the in-repo `docs/convergence/LICENCE_AND_SECURITY_REVIEW.md` agree, the agreement was reached independently from the same bytes; where they differ, this audit adds: the second Comtrade redistribution on #27; the 5-file derived-value leak on #30; the phoenix-003 abstract corpora; the full 24-ref scan; and the register-vs-register contradictions. The in-repo review's 6,234,301 B and 30-path figures were **confirmed to the byte**, and its own §10.4 remediation was found to be **incomplete**.
