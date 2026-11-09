# FOUNDATION_AUDIT — MedRadar / ATLAS-001

**Audit date:** 2026-11-10
**Audited baseline:** `main` at `b2a14c0a92332c004445de686daee97754cf94cb`
("Merge pull request #11 from ChazY11/research/early-signal-review-workbench", 2026-11-03)
**Auditor:** ATLAS-001 engineering pass
**Method:** direct inspection of the remote Git tree (`git ls-tree`, `git show`), the GitHub PR
inventory (`gh pr list --state all`), a full test run on a clean worktree, and a bounded
secret/large-file scan of the tracked tree. No PR was merged and no branch was rewritten.

---

## 1. What the repository actually is

| Measure | Value |
|---|---|
| Tracked files on `main` | 1,135 |
| Total tracked size | 29.1 MB |
| Largest tracked file | `docs/dashboard.html`, 3.2 MB |
| Files > 1 MB | 2 (`docs/dashboard.html`, `config/universe_v1.json`) |
| Tracked files under `data/` | 0 (runtime data is generated and git-ignored) |
| Remote branches | 33 |
| Open pull requests | 17 (16 drafts) |
| Merged pull requests | 10 |
| Offline test suite on `main` | 1,122 tests, exit 0 (no failures) |

Code distribution on `main`:

| Area | Files | Reading |
|---|---:|---|
| `experiments/` | 657 | Per-experiment scripts, logs, frozen JSON. Historical record, not a library. |
| `research/` | 116 | Study protocols, registers, review worksheets. Evidence assets. |
| `tests/` | 105 | Real offline tests; the suite is green. |
| `medradar/` | 87 | The actual installable package (collectors, TKG, forecasting, studies). |
| `docs/` | 60 | Methods, schemas, dashboards, report pages. |
| `papers/` | 32 | Write-ups. |
| `verifier/` | 22 | Independent checks for earlier rounds. |
| `tools/`, `scripts/`, `config/`, `.github/` | 48 | Operational glue + 4 workflows. |

**Verdict:** `main` is a working research pipeline with a green offline suite. It is *not* a
product-identity system: it has no canonical company/manufacturer/device model, no
cross-registry identifier store, and no append-only evidence database outside the TKG module.
Those are the gaps ATLAS-001 fills.

---

## 2. Pull-request inventory and dependency graph

27 PRs total: 10 merged, 17 open, 16 of the open ones are drafts. The important structural
fact is that **most open PRs are stacked**, so their "mergeable" flag says nothing about
whether their content is integrated.

| PR | Branch | Base | Size | State | What it is | ATLAS-001 decision |
|---:|---|---|---|---|---|---|
| #1 | `feat/frontier-device-radar` | main | +2,709/−234 | open, CONFLICTING | frontier device intelligence | **do not touch** (conflicts with main's later schema) |
| #2–#5 | research/integration branches | main | +6k…+444k | merged | TKG bitemporal store, forecast registry, market→R&D | **already in main**; studied as prior art |
| #6–#11 | early-signal studies | main | +28…+24k | merged | five-firm audit, third source, adjudication, workbench | **already in main**; the negative result is preserved |
| #12 | `feat/medradar-2.0-mvp` | main | +17,646/−1 | draft | 2.0 product UI | out of scope this round |
| #13 | `feat/live-observatory-v1` | #12 | +31,301/−7 | draft | append-only observation ledger, live adapters | **selectively studied**; ledger idea informs ATLAS evidence versions |
| #14 | `feat/observatory-reliability-v1` | #13 | +22,899/−71 | draft | durable persistence, backups, 7-day validation | backup discipline adopted conceptually |
| #15–#16 | S-028/S-029 | #14 | +114k/+133k | draft, negative | temporal graph & evidence relations, NO-GO | **research assets, not production**; kept frozen |
| #17 | `maintenance/repository-consolidation` | main | +947/−805 | draft | docs/index/governance | not merged; ATLAS writes new `docs/atlas/` instead of reopening it |
| #18 | `research/ai-evidence-review` | main | +575 | draft | machine review of 69 packets | research tier only |
| #19–#20 | local LLM / QLoRA | main | +32k/+17k | draft | local model experiments | **out of scope**; no model training this round |
| #21–#22 | hiring/R&D evidence | phase4 / main | +64k/+304k | draft | hiring-as-signal studies | research assets |
| #23–#25 | PHOENIX-001/002 | main / #24 | +6k/+159k/+58k | draft | external methods, 10 pre-registered experiments, H8 NO-GO | **frozen results preserved**; ATLAS encodes the lesson, does not retune |
| #26 | PHOENIX-003 | main | +197,464 | draft | regulatory-anchored early evidence, NO-GO, 28 cases | **frozen**; its control battery is the model for ATLAS negative controls |
| #27 | `research/data-expansion-001` | main | +260,389 (916 files) | draft | 59 sources surveyed, 31 verified, 17 connectors | **selective port only** (see §3) |

### Dependency reality

- #13 → #12, #14 → #13, #15/#16 → #14, #21 → `integration/phase4-base`, #25 → #24, #20 → #19.
- #27 and #26 are based directly on `main` but are 197k–260k additions of research output; they
  were never meant to be merged wholesale.
- **No open PR is a production dependency of `main`.** Treating the set as an unmerged "system"
  overstates what exists.

---

## 3. What was reused, and what was deliberately not

ATLAS-001 ports a small, verified subset of PR #27 with provenance, then adds new layers.
Nothing was merged from the branch; files were copied into `medradar/atlas/` and adapted.

| Component | Source (commit path) | Reuse decision | Why |
|---|---|---|---|
| `evidence/http.py` | `research/data-expansion-001:medradar/external_sources/base.py` | **ported + trimmed** | Budget/retry/ledger design is sound and already tested. Probe-runner machinery was dropped because ATLAS records runs in SQLite. |
| `evidence/schema.py` | `.../external_sources/schema.py` | **ported + rewritten** | Kept content hashing, canonical keys, deterministic ids, candidate-confidence rule. Rewritten to the ATLAS required field set (four clocks, identity/relation/licence status). |
| `evidence/timeq.py` | `.../external_sources/timeq.py` | **ported + fixed** | Four-clock separation is correct. Fixed string/datetime coercion and added migration-safe validation. |
| `identity/normalize.py` | `.../external_sources/identity.py` | **ported + reduced** | Identifier normalisation reused. The duplicate company registry was removed; ATLAS has one registry (`config/atlas_firms.json`). Added German umlaut transliteration (see §5). |
| `connectors/accessgudid.py` | `.../regulatory/accessgudid.py` | **ported + adapted** | Same API semantics and date traps; adapted to ATLAS evidence constructor. |
| `connectors/canada_mdall.py` | `.../regulatory/canada_mdall.py` | **rewritten** | The original assumed `deviceidentifier` accepts a UDI-DI. Measured reality: 0.33 % of rows are GTIN-14 and the listing endpoints return whole tables. The ATLAS connector streams once and treats the field honestly. |
| `connectors/openfda_510k.py` | `.../regulatory/openfda_device_510k.py` | **ported + adapted** | Date semantics and evidence shape are correct. |
| `connectors/openfda_udi.py` | — | **new** | Needed a company-searchable UDI source and a batch identifier resolver. |
| `db/`, `store.py`, `graph/`, `quality/`, `research/`, `cli.py` | — | **new** | No prior PR provides a versioned migration system, graph queries, as-of semantics or a prospective registry. |
| `external_sources` scholarly/procurement/trade connectors | PR #27 | **not ported** | Out of ATLAS-001 scope; their licences and clocks are documented in `config/atlas_sources.json` for the next phase. |
| PHOENIX/S-028/S-029 research output | PRs #15, #16, #23–#26 | **not touched** | Frozen negative results. ATLAS reads the lessons, not the files. |

---

## 4. Duplication and technical debt found

1. **Two "evidence" concepts.** PR #27 has `external_sources/schema.py`; PR #13 has an
   append-only observation ledger; TKG in `main` has its own bitemporal tables. ATLAS defines
   one contract (`medradar.atlas.evidence.v1`) and leaves the older stores untouched.
2. **Two identifier normalisers.** PR #27's `identity.py` and `main`'s `medradar/tkg` both
   normalise ids differently. ATLAS keeps one (`identity/normalize.py`) and never imports the
   others.
3. **Company aliases in code, not config.** PR #27 embeds five firms' aliases inside a Python
   module. ATLAS moves them to `config/atlas_firms.json` so a reviewer can audit the registry
   without reading code.
4. **Statistics copied by hand.** The DATA-EXPANSION-001 review already flagged summary/log
   count drift. ATLAS generates every reported number from the database in one process
   (`identity_pilot.json`) and an independent verifier recomputes it (`tools/verify_atlas.py`).
5. **Large generated HTML in docs.** `docs/dashboard.html` is 3.2 MB; acceptable but not a
   data asset. ATLAS keeps generated outputs under git-ignored `research/atlas/` except a
   bounded, explicitly redistributable sample.
6. **No schema versioning on `main`.** `docs/SCHEMA.md` documents tables, but there is no
   migration runner. ATLAS adds `schema_migrations` + checksums + pre-migration backup.

---

## 5. Defects found and fixed during the audit (evidence, not assertion)

| Defect | Where found | Repair |
|---|---|---|
| Umlaut folding lost the `e` ("Drägerwerk" → `DRAGERWERK`), so the curated ASCII alias `DRAEGERWERK` never matched | `identity/normalize.py` port | explicit `ä→ae, ö→oe, ü→ue, ß→ss` transliteration before NFKD; regression test added |
| AccessGUDID duplicates were counted by `evidence_id`, which is source-scoped, so the same GUDID record read twice looked independent | pilot stage | dedupe by `canonical_key` across sources; report says "duplicate upstream observation" |
| MDALL `device_identifier` was being compared as a *model number* against GUDID models, turning every true UDI bridge into a contradiction | pilot bridge | MDALL view leaves model empty; identifier equality is the only claim |
| `as-of` applied the capture boundary to *public visibility*, hiding inferable history | `research/asof.py` | boundary applies only to the `observed` basis |
| `executescript` inside a transaction silently committed, defeating rollback | `db/migrations.py` | statement-by-statement execution inside one explicit transaction |
| Quality checks emitted one finding per row (7,595 findings) | `quality/checks.py` | aggregate per source/class; 53 findings now |

All six have tests or a verification check.

---

## 6. Licence, privacy and credential posture

- **Credential scan:** regex search for `api_key|secret|password|token` assignments over
  tracked text on `main` → **0 hits**. No `.env`, `credential` or `secret` files tracked.
- **Data in Git:** no `data/` files tracked; the only multi-MB files are HTML/JSON docs.
- **Restricted sources:** EPO OPS is registered in `config/atlas_sources.json` as
  `REQUIRES_REGISTRATION`; ATLAS does not create accounts, does not use borrowed credentials
  and does not store EPO payloads. The verifier asserts zero `licence_status='restricted'` rows.
- **Reused code:** same repository, MIT licence. Ported modules keep attribution headers.
- **Personal data:** the sources used (GUDID, openFDA, MDALL) contain company and device data,
  not patient data. No UCL credentials or subscriptions were used.

---

## 7. What should become the long-term core

**Keep and maintain as core libraries**
- `medradar/atlas/evidence` — record contract, clocks, bounded HTTP.
- `medradar/atlas/identity` — normalisation, models, resolver.
- `medradar/atlas/db` + `store` — migrations, append-only evidence, relations.
- `medradar/atlas/connectors` — the six-operation connector contract.
- `medradar/atlas/graph` + `research` — queries and historical semantics.

**Keep as frozen research assets (read-only)**
- PHOENIX-001/002/003 (#23–#26), S-028/S-029 (#15/#16), the early-signal workbench (#6–#11).

**Keep as prototype / product track (not core)**
- PR #12–#14 observatory UI and live adapters; PR #19–#20 local LLM work.

**Do not merge**
- The 197k–260k-line research branches (#26, #27) as-is. Extract interfaces, never bulk-merge.

---

## 8. Remaining audit unknowns

| Unknown | Why it remains |
|---|---|
| Whether PR #1 can be rebased onto current `main` | It is CONFLICTING; resolving it is a separate product decision. |
| EUDAMED / NMPA UDI access | Legal/registration preconditions; not attempted (see `DATA_SOURCE_INTEGRATION.md`). |
| Full GUDID/MDALL coverage | Requires bulk releases far beyond the bounded pilot; explicitly out of scope. |
| Human adjudication of candidate relations | No human labelling was performed this round; candidates remain candidates. |

---

*Every number in this audit is reproducible: `git rev-parse origin/main`, `gh pr list`,
`python -m pytest -q`, and the audit commands recorded in the ATLAS-001 PR description.*
