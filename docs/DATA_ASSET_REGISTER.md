# Data Asset Register — MedRadar

What data exists, where it lives, which copy is authoritative, and what may be deleted.
Measured **2026-11-04** during the repository-consolidation pass. All sizes are bytes measured on disk
or, for branch-only assets, bytes in that git branch. Nothing here was deleted, moved or migrated.

**Rules for this register**

1. Default for every data asset is **not deletable**. Deletion requires a named human decision.
2. Runtime data (`data/`, `out/`, `logs/`) is **not** in git. Do not fix that by committing it.
3. Frozen research artifacts are never rewritten. Corrections are new files, linked from the study.
4. Regeneration is only claimed when the script **and** its inputs are reachable from a clone.

**Path note:** this register covers assets of the whole project, so some owner modules and study paths
live on **draft branches only** (the observatory/reliability layer, the 2.0 product layer, S-028, S-029)
and will not be found in a `main` checkout. Branch-only paths are named as such; see
[PROJECT_STATUS.md](PROJECT_STATUS.md) §3 for the branch of every research line.

---

## 1. Which database is authoritative

Five different things are called "the database" in this repository. They are not interchangeable and
must never be merged.

| Class | File | Authority |
|---|---|---|
| **Operational Database** | `data/medradar.sqlite` (1,368,469,504 B, sha256 `445807ca…`, 375,378 events, PRAGMA 30) | The official runtime store. Written by every collector and by `scripts/nightly.ps1`. This is the "主库" in [DATA.md](DATA.md). Device/company/track/product views are valid **only** against this file. |
| **Historical Research Dataset** | `research.sqlite` (289,443,840 B, sha256 `dd241bfe…`, 55,090 events, 95,725 market bars, PRAGMA 38) | The curated research lane used by Market-to-R&D, TKG, the research agent and S-028. **It is absent from the repository `data/` directory**; the only copy found on this machine is under a sibling worktree. |
| **Frozen Experimental Dataset** | the same 289 MB `research.sqlite`, pinned by SHA-256 | S-028's experimental input (`verify_frozen_db`). The pin is the contract: a different hash is a different study. Plus S-028's committed per-row predictions (`artifacts/predictions_H{2,4}q.json.gz`). |
| **Observation Ledger** | `data/observatory/observatory.sqlite` (1,957,888 B, sha256 `15a0a943…`, 400 observations, `obs-ledger-v1`) | The only append-only "observed-as-of" record. `first_seen_at` is immutable by trigger and is copied — never regenerated — into backups. |
| **Backup Archive** | `data/observatory/backups/observatory-20261103T201701Z/` (6,823,060 B, 40 files) | A verified, manifest-hashed snapshot of the ledger (`MANIFEST.json` sha256 `6ce37f43…`, matches the ledger's `runtime_state["last_backup"]`). One bundle only; see §6. |

Everything else in `data/` is a dev, smoke, derived or generated artifact. **No database file is
tracked on any branch.**

---

## 2. Asset inventory

| Asset | Path | Type | Size | Source / provenance | Owner | Regenerable | Referenced by | Deletable | Sensitive | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Operational DB | `data/medradar.sqlite` (+`-shm`,`-wal`) | production | 1,368,469,504 B | openFDA + ClinicalTrials.gov + SEC EDGAR via `medradar run/collect`, `scripts/backfill_*.py` | `medradar/db.py` | yes (re-crawl; not byte-identical) | docs/DATA.md, SCHEMA.md, README, study provenance | **No** | no | `ACTIVE` |
| Research-lane DB | `research.sqlite` (not in repo; sibling worktree) | research / frozen experimental | 289,443,840 B | openFDA bulk, CT.gov, SEC XBRL, USAspending, Yahoo bars, OpenAlex via `medradar/intelligence/*` | `medradar/intelligence/storage.py` | yes (expensive; needs live sources + credentials-free APIs) | S-028 input, Market-to-R&D, TKG import, research agent | **No** | no | `FROZEN` |
| SEC 8-K corpus | `data/edgar_corpus/*.jsonl` (19 files) | raw → processed | 924,225,558 B | EDGAR full-text search + Archives via `scripts/build_corpus.py` | `medradar/corpus.py` | yes (re-crawl; cleaned text only, raw HTML deliberately not stored) | case library, replay, backfill | **No** | third-party filing text | `ACTIVE` |
| HTTP response cache | `data/cache/*` (30,469 files) | raw | 7,195,894,964 B | every fetcher response, keyed by URL (`medradar/http.py`) | `medradar/http.py` | yes (re-fetch) | resumability of every stage | **No** | third-party payloads | `ACTIVE` |
| Observation ledger | `data/observatory/observatory.sqlite` | production | 1,957,888 B | ctgov / europepmc / sec adapters via `medradar observatory sync` / `observatory watch` (branch) | `medradar/observatory/ledger.py` | **no** (append-only) | S-029 clock audit; reliability evidence | **No** | low (host/PID in `runtime_state`) | `ACTIVE` |
| Observatory raw cache | `data/observatory/cache/*` (37 files) | raw | 4,861,673 B | observatory fetches | `medradar/http.py` | yes (re-fetch) | backup bundle copies it | **No** | third-party payloads | `GENERATED` |
| Backup archive | `data/observatory/backups/observatory-20261103T201701Z/` | backup | 6,823,060 B | `observatory backup --verify --prune` (daily scheduled task) | `medradar/observatory/backup.py` | no (point-in-time) | BACKUP_AND_RECOVERY.md §2–§9 | **No** | low | `FROZEN` |
| Calibration dataset | `data/calibration/**` (133 files) | research | 1,092,979 B | 25 real 8-K filings + human labels + LLM/heuristic verdicts | `medradar/calibration.py` | partly (filings re-fetch; labels are human) | CALIBRATION.md, calibration tests | **No** | no | `HISTORICAL` |
| Dev-lane DBs | `data/dev_{device,drug,nmpa,nmpa_demo}.sqlite` | processed | 88,977,664 B | ad-hoc dev runs of collectors | `medradar/*` CLI | yes | DATA.md §6 only | **No** | no | `HISTORICAL` |
| Smoke DBs | `data/_itest.sqlite`, `_sanity.sqlite`, `_synthetic.sqlite` | generated | 7,512,064 B | ad-hoc smoke runs 2026-10-30; **no committed writer** | none | yes | none found | **No** (candidate) | no | `OBSOLETE_CANDIDATE` |
| Derived product index | `data/product_entity_map.sqlite`, `data/medradar.product_entity_map.sqlite` | generated | 102,400 B each | materialised 591-row index (branch code) | `medradar/product/store.py` | yes | branch docs only | **No** (candidate) | no | `DUPLICATED` |
| Manual sample filing | `data/samples/merck_8k_q3_2026_ex991.txt` | raw | 484,611 B | one 8-K exhibit; **no code or doc reference found** | none found | unknown | none found | **No** | filing text | `UNKNOWN` |
| Runtime outputs | `out/**` (964 files) | generated | 469,378,155 B | report/replay/nightly/drill runs | `medradar/report.py`, `replay.py` | yes | DATA.md §5 | **No** | no | `GENERATED` |
| Ops logs | `logs/**` (3 files) | generated | 65,663 B | collector/backup tasks | scripts | yes | ops only | **No** | low | `GENERATED` |
| Tracked study | `research/studies/early_signal_5firms/**` (50 files) | research | 687,709 B | derived from the 1.37 GB store | `experiments/b08*` | no from clone | self, RESULTS index | **No** | no | `FROZEN` |
| Tracked results | `research/RESULTS/**` (46 files) | research | 194,509 B | cycle reports from experiment artifacts | research lane | no from clone | RESULTS index | **No** | no | `FROZEN` |
| Tracked experiment artifacts | `experiments/**` (657 files) | research | 15,778,771 B | frozen benchmarks, snapshots, detection rounds | experiments | no from clone | papers, docs/research | **No** | no | `FROZEN` |
| Knowledge base | `config/*.json` (10 files) | processed | 2,283,315 B | human curation + universe build | `medradar/config.py` | no (human) | every collector | **No** | no | `ACTIVE` |
| Site snapshot | `docs/**` (60 files) | generated | 6,704,394 B | report/dashboard renderers; GitHub Pages | `medradar/report.py` | partly | README, Pages | **No** | no | `GENERATED` |
| S-028 study | `research/studies/graph_early_signal_s028/**` (86 files) | research | 6,146,604 B | frozen DB + seeds → `code/s028_*.py` | study code | no from clone (needs 289 MB DB) | own docs | **No** | no | `FROZEN` |
| S-028 artifacts | `…/s028/artifacts/**` (33 files) | research | 5,044,467 B | producers in `code/` | study code | no from clone | own docs | **No** | no | `FROZEN` |
| S-029 study | `research/studies/relation_network_s029/**` (205 files) | research + raw | 65,037,899 B | CT.gov v2, Europe PMC, ROR, OpenAlex, Crossref → `code/s029_*.py` | study code | partly (see §7) | own docs | **No** | third-party payloads | `FROZEN` |
| S-029 raw payloads | `…/s029/data/raw/*.json.gz` (130 files) | raw | 2,758,683 B compressed / 13,085,431 B uncompressed | verbatim per-query API responses | study code | partly | `request_log.jsonl` hashes | **No** | third-party payloads | `FROZEN` |

Totals: `data/` = **9,600,480,526 B / 30,719 files** (cache 6.70 GiB, EDGAR corpus 881 MiB, SQLite
1.37 GB); `out/` = 448 MiB; `.git` = 32.4 MiB packed. Working tree excluding `.git` ≈ 10.1 GB.

---

## 3. Duplicates and redundancy (hash-verified)

| Group | Where | Verdict |
|---|---|---|
| 6 exact duplicate groups / 4,572 B | `main`: two `experiments/b027` snapshot `summary.json`, four identical selfcheck logs, one duplicated tiny device fixture JSON, 9 empty files | Harmless; git stores one blob. **Keep** — logs are run evidence. |
| 0 duplicate groups | 776 files > 1 MB in `data/` (7.5 GB hashed) | Cache is not silently duplicating payloads. |
| `product_entity_map.sqlite` ≡ `medradar.product_entity_map.sqlite` | `data/` | Same 102,400 B file under two names; derived. Cleanup candidate, not deleted. |
| 31 byte-identical files / 4,645,341 B | observatory live cache vs backup bundle `raw-cache/` | **Intentional** (the backup copies raw cache). Keep. |
| 25 identical files / 356,656 B | `tests/fixtures/calibration/filings/*.txt` vs `data/calibration/filings/*.txt` | Test fixture deliberately mirrors the dataset. Keep. |
| 11 cross-branch identical groups / 98,967 B | e.g. `docs/ASSUMPTIONS.md` ≡ `docs/docs/ASSUMPTIONS.md` (nested-copy defect, only on PR #1's branch), `config/hist_entity_aliases.json` ≡ product entity aliases | Recorded; none is on `main`. |

No duplicate group justifies deleting anything on `main` in this pass.

---

## 4. Large-file and repository-weight governance

- `.git` = 33,967,584 B (32.4 MiB); `size-pack` 27.82 MiB; 4,254 in-pack objects; **no Git LFS**
  (`.gitattributes` has only text/eol/binary markers). At this size LFS is unnecessary.
- Largest tracked blobs in history are all on the **S-029 draft branch**: four versions of
  `data/claims.jsonl` (20.9 / 20.5 / 19.8 / 18.4 MB), `ctgov_trials.jsonl` 8.4 MB,
  `company_mentions.jsonl` 5.2 MB, four versions of `evidence.jsonl` 4.0 MB each, plus
  `docs/dashboard.html` 3.35 MB (main).
- **What the draft branches add:** S-029 **+69,293,248 B / 339 files** (10× `main`'s study footprint),
  of which the study directory is 65.0 MB / 205 files; 14 files >1 MB totalling 64.2 MB. S-028
  **+10,401,953 B / 220 files** (artifacts 5.0 MB, including 1.79 MB of gzipped predictions).
- **Recommendation (not executed):** before S-029 is ever merged, move the large derived JSONL corpora
  and raw payloads to an external archive or a GitHub Release asset and keep only the
  manifests/hashes plus the scripts; if they must stay in git, use Git LFS for the `.jsonl`/`.json.gz`
  classes. This requires a human decision because it changes the evidence's location — the hashes must
  be re-recorded if it is done.
- Nothing in `.gitignore` (which correctly excludes `data/`) prevents a future accidental commit of
  gigabytes, and no CI size check or hook enforces it. Any change to that would be a new control, not a
  cleanup; recorded as a candidate only.

---

## 5. Redistribution and licensing posture

- `LICENSE` states MIT for the code **and** that "MedRadar does not redistribute bulk source data";
  [DATA_PROVENANCE.md](../research/DATA_PROVENANCE.md) §5 says raw bulk downloads and the SQLite stores
  are not committed.
- Sources and their status: openFDA (US public domain), ClinicalTrials.gov (public domain / its terms),
  SEC EDGAR (fair-access, declared User-Agent), Europe PMC and Crossref (per-record publisher terms),
  OpenAlex/ROR (CC0), Yahoo-derived price bars (vendor-derived — explicitly **not** redistributable as a
  product, see [MARKET_DATA.md](MARKET_DATA.md)).
- **Known inconsistency:** the S-029 draft branch commits 130 per-query raw CT.gov / Europe PMC payloads
  (2.76 MB compressed). That is not a bulk dump and it is traceability-critical, but the repository's
  blanket statement is narrower than the fact. `SOURCE_AUDIT.md` names the sources but quotes no
  precise redistribution terms. Recorded as open human decision #9 in
  [PROJECT_STATUS.md](PROJECT_STATUS.md). Do not merge that branch without resolving it.
- Untracked local corpora (cache, EDGAR corpus, calibration filings) are licence-covered but outside the
  redistribution claim because they are outside git.

---

## 6. Backup and recovery

**Verified without running a restore** (destructive recovery was out of scope by instruction):

- Design exists and uses the SQLite online backup API (`Connection.backup()`), a SHA-256 manifest per
  artifact, `PRAGMA integrity_check` re-verification, GFS retention (7 daily / 4 weekly / 6 monthly),
  quarantine instead of deletion for unverifiable bundles, and a restore command that refuses
  unverified manifests. Windows scheduled task `MedRadarObservatoryBackup` (daily 04:17 local) last
  returned `Last Result = 0`.
- The surviving bundle's hash chain was independently re-verified: manifest sha256 == ledger
  `runtime_state["last_backup"].sha256_manifest`, ledger sha256 == manifest entry, `integrity_check` ok.
- **Gaps:** (i) the last *restore drill* (11/11 checks OK) verified bundles that have since been pruned —
  the surviving bundle has never been drill-restored; (ii) **no offsite copy** exists and backups are
  unencrypted; (iii) there is **no backup at all** for `medradar.sqlite` (1.37 GB), `research.sqlite`
  (289 MB), `data/cache` (7.2 GB) or `edgar_corpus` (924 MB).
- **Retention policy for this pass:** keep every bundle and every SQLite file; prune nothing; do not run
  `restore`, `--prune` or any destructive command in a maintenance pass.

---

## 7. Regeneration honesty

| Frozen asset | Script in repo | Inputs in repo | Needs local `data/` | Honest verdict |
|---|---|---|---|---|
| ES-5F study (main) | yes (`experiments/b08*`) | no | yes (1.37 GB store) | **Not reproducible from a clone**; self-declared in `REPRODUCIBILITY.md` §6 |
| S-028 study | yes (28 scripts) | no (289 MB pinned DB outside repo) | yes | **Not reproducible from a clone**; scripts also hard-code absolute local paths |
| S-029 evidence chain | yes (17 scripts) | mostly (raw payloads + per-call hash log committed) | clock-audit step only (1.9 MB ledger) | **Half reproducible**: claims→evidence→raw hashes yes; clock audit and verify script no |
| S-028 predictions | yes | no (needs frozen DB) | no (only 289 MB DB) | artifacts committed, re-derivation needs the external DB |
| Frozen detection benchmark | drift guard yes; producer yes | no | yes | guard is reproducible; regeneration is not |
| `docs/metrics.json` / dashboard / replay | renderers yes | no | yes | committed snapshot, cannot be rebuilt from a clone |
| Calibration snapshot | harness yes | labels are human | no | not byte-reproducible; tracked copy and runtime copy already diverge |

**Consequence to state plainly in the README:** a third party can verify this project's *test suite,
claims and evidence chain*, but cannot re-derive its *study numbers* without the uncommitted stores.
Closing that gap (Release asset, archive with hash, or a documented data request) is a future task, not
something this pass performs.

---

## 8. Verification boundary

- Sizes and hashes measured on this machine; the observation ledger changes while its collector runs
  (last run 2026-11-04 05:50 +08), so its byte size is a snapshot.
- Backup/restore code was **read**, not executed; "it works" rests on the committed evidence JSON and on
  the manifest hash chain re-verified here.
- Absence of offsite backups is asserted from the absence of scripts and on-disk copies; a copy kept
  outside this machine cannot be ruled out.
