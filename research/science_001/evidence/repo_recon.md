# Repository-integration recon — SCIENCE-001 (EDGAR point-in-time study)

**Purpose.** What will break the SCIENCE-001 PR, what already exists to reuse, and the exact commands.
**Measured on:** worktree `D:\DEPPSKK\worktrees\science-001`, branch `research/science-001-edgar-pit`,
HEAD `e933051` (2026-11-13T05:12:15+08:00), `origin/main` = `b2a14c0a92332c004445de686daee97754cf94cb`,
Python 3.12.10, pytest 9.1.1, Windows. Every number below was produced by running the command cited.
**Worktree shape:** HEAD is **36 commits ahead** of `origin/main`; the diff is **182 paths** (82 docs,
17 tests, 11 tools, 4 medradar, 3 .github, 2 research, plus README/CHANGELOG/PROJECT_STATE/pyproject/README.zh-CN).
That diff already carries the Phase-3 governance merge-gate work, including **3 rule-change records**
(RC-0001..RC-0003) and the v2 PROJECT_STATE/FROZEN schema. Keep those commits: dropping them makes
`rule-audit` fail (§2.6).

---

## 1. The licence gate — `tools/governance/check_licence.py` (836 lines)

### 1.1 What it scans

| Surface | Code | Consequence |
| --- | --- | --- |
| Final git tree (`git ls-files`, i.e. committed **+ staged**) | `tracked_files()` :327-332, `check_tree()` :395-502 | every data file needs an inventory entry |
| Content read from the **worktree**, not from git | `read_content()` :363-369 | the bytes on disk are what gets classified |
| Untracked files (`git ls-files --others --exclude-standard`) | `untracked_files()` :335-339, `check_untracked()` :532-546 | **an untracked data file fails the gate** |
| PR diff vs `--base` (default `origin/main`) | `changed_paths()` :342-360, `check_diff()` :549-596 | added/modified/renamed data paths need entries |
| Legacy RED/AMBER source patterns over the tree | `check_whitelist_sources()` :505-529 | a RED path cannot be laundered by an inventory entry |

### 1.2 What a "data file" is (two independent triggers)

`_is_data_candidate()` :372-375 — a path is a data file if **either**:

1. its lower-case suffix is in `inventory.data_extensions` (`DATA_LICENSES.yaml:50-69`, 19 entries;
   defaults at `check_licence.py:69-89`):
   `.csv .tsv .json .jsonl .ndjson .parquet .arrow .feather .sqlite .db .duckdb .h5 .hdf5 .npy .npz .bin .gz .gzip .zip`
2. **or** its sniffed bytes are a restricted kind (:93):
   `sqlite parquet hdf5 gzip zip elf binary`. The magic-byte sniffer `detect_kind()` :104-170 recognises
   SQLite/Parquet/HDF5/gzip/zip/ELF/PDF/PNG/JPEG/GIF, then UTF-8/UTF-16 text, then json if it parses, csv if
   ≥2 of the first 5 non-empty lines share the same comma/semicolon/tab count, else text/binary.

Detection-only kinds that are **not** restricted: `MEDIA_KINDS = {png, jpeg, gif, pdf}` (:96).
Practical consequences for SCIENCE-001:

* `.md`, `.py`, `.html`, `.xml`, `.txt`, `.pdf`, `.png` are **not** data candidates → **no inventory
  entry needed** (verified on the WIP tree: every SEC HTML/TXT/PDF evidence file reports `candidate=False`).
* **every `.json`, `.jsonl`, `.csv`, `.bin`, `.gz`, `.zip` needs an entry, wherever it lives**, unless the
  path matches `inventory.exempt_patterns` — which is only `docs/refoundation/*/_evidence/*`
  (`DATA_LICENSES.yaml:48-49`, `check_licence.py:219-223, 390-392`). `research/science_001/evidence/...` is
  **not** exempt.
* a media/PDF file is fine, but a `.png` that is really a ZIP is caught as restricted.
* `.xlsx` is **gitignored** (`.gitignore:19`) so it silently never enters the PR — and if force-added it
  sniffs as `zip` → restricted → fail.

### 1.3 The pass/fail rule set (exhaustive, one row per real branch)

| # | Condition | check id | Code |
| --- | --- | --- | --- |
| 1 | tracked data file has no inventory entry | `inventory.coverage` | :431-436 |
| 2 | inventory entry `status: RED` and the file exists | `content.red_source` | :423-429 |
| 3 | declared `content` ≠ detected kind | `inventory.content_match` | :446-453 |
| 4 | restricted kind without a synthetic entry (`entry.synthetic` **and** `sources[source_id].synthetic`, :378-382) | `content.restricted_kind` | :455-461 |
| 5 | restricted kind under an exempt path | `content.restricted_kind` | :413-421 |
| 6 | declared db/archive extension whose bytes are another kind | `inventory.extension_masquerade` | :466-483 |
| 7 | inventory lists a path no longer tracked (rename/delete) | `inventory.stale_entry` | :491-501 |
| 8 | tracked path matches a RED `tracked_patterns` (AMBER needs a `policy_entries` record, :255-265) | `source.pattern` | :505-529 |
| 9 | **untracked data file in the worktree** | `untracked.data_file` | :532-546 |
| 10 | PR-diff data path with no inventory entry | `diff.changed_data_file` | :570-586 |
| 11 | PR-diff changes a declared file to another content kind | `diff.changed_content` | :584-590 |
| 12 | policy sanity: schema, non-empty `manual_review`, disclaimer must contain "legal guarantee", non-empty `data_extensions`, `raw_root == "data/"` and `data/` actually gitignored | `policy.*`, `policy.raw_root.gitignored` | :665-704 |

### 1.4 Valid statuses and "entry kinds" — read before hand-editing

* **Statuses are exactly `{GREEN, AMBER, RED}`** — `STATUSES` :65, validated on sources (:236-240) and on
  every inventory entry (:302-307); `STATUS_RANK` :66 fixes pattern precedence.
* **`ENTRY_KINDS = {"derived-aggregate","derived-report","metadata","claims","index"}`** (:67) is **dead
  code**: a repo-wide grep finds only that definition, and the inventory schema has no `kind` field (grep for a
  line-level `kind:` in `DATA_INVENTORY.yaml` → no match). The `kind:` values that exist live in
  `DATA_LICENSES.yaml policy_entries` (:195-211: `derived-aggregate`, `derived-report`) and are **never
  validated**. Treat `ENTRY_KINDS` as the vocabulary for policy entries, not a constraint on
  `DATA_INVENTORY.yaml`.
* Inventory fields actually enforced (`load_inventory()` :268-310 + `check_tree()`): `path` (non-empty
  string, unique), `status` (GREEN/AMBER/RED), and `content` must equal the sniffed kind. `source_id` is
  used (to look up `synthetic`) but need not exist in `sources`; `synthetic` matters only for restricted
  kinds.
* Editing the inventory **cannot** rescue a RED path: `check_whitelist_sources()` re-derives the status from
  `tracked_patterns` regardless of what the entry says.
* The file must stay inside the `yamlmini` subset (`common.read_yaml` → `tools/governance/yamlmini.py`;
  no flow `{...}`/`[...]` collections, no anchors/tags, no tabs — `GOVERNANCE.md:113-121`).

### 1.5 Where the policy lives, and what it says about SEC / images / JSON

Policy file: **`docs/governance/DATA_LICENSES.yaml`** (schema `medradar.data_licenses.v2`, :31); default
status `RED` for unlisted sources (:35, :217); `raw_root: data/` (:36). Key source records:

| source_id | status | tracked_patterns | line |
| --- | --- | --- | --- |
| `sec_edgar` | **GREEN**, `may_redistribute: true`, "SEC EDGAR 8-K filings. U.S. Government work; no endorsement by the SEC." | *(none — no path pattern)* | :103-109 |
| `medradar_derived_artifacts` | **GREEN** — "derived aggregates and research artifacts generated by this repository from GREEN public sources … no third-party raw content is redistributed" | `experiments/**`, **`research/**`**, `papers/**`, `docs/*.json`, `docs/*.csv`, `docs/research/**`, `docs/refoundation/**`, `tools/*.json` | :139-152 |
| `synthetic_fixtures` | GREEN, `synthetic: true` | `tests/**` | :160-167 |
| `yahoo_chart_bars` | **RED** | `**/prices_*.csv`, `**/prices_*.json`, `**/raw_bars_*.json`, `**/yahoo_bars_*.json` | :168-180 |
| `internet_archive_cdx` | **AMBER** (needs `policy_entries`) | `experiments/b030/*`, `experiments/b026/validate_hiring_domain.json` | :181-193 |

**Implication: no change to `DATA_LICENSES.yaml` is needed for SCIENCE-001.** Everything under
`research/**` already resolves to `medradar_derived_artifacts` / GREEN. Verified directly against the
policy object:

```text
research/science_001/evidence/foo.json              -> ('medradar_derived_artifacts', 'GREEN', 'research/**')
research/science_001/evidence/sec_docs/raw/x.jsonl  -> ('medradar_derived_artifacts', 'GREEN', 'research/**')
research/science_001/evidence/prices_2020.json      -> ('yahoo_chart_bars', 'RED', '**/prices_*.json')
science_001/evidence/foo.json                       -> None   # UNCLASSIFIED
```

Two hard consequences:

* **Keep every artifact under `research/`.** An unclassified path is written into the inventory as
  `source_id: unclassified, status: RED` (`generate_inventory()` :606-619) and then fails
  `content.red_source` (:423-429).
* **Never name a file `prices_*.json/csv`, `raw_bars_*.json`, `yahoo_bars_*.json`** anywhere — the RED
  pattern matches on path, so a file such as `prices_monthly.json` fails even though it is our own aggregate.
  Raw price *bars* must stay in gitignored `data/`; only coverage counts and evaluation metrics may be
  committed (`DATA_LICENSES.yaml:168-180, 214-215`).

About **images**: there is no image-specific rule requiring an inventory entry. Images/PDFs are detected only so
a restricted binary cannot masquerade as one; committed PNG/JPEG/GIF/PDF are neither inventoried nor restricted,
because they are not in `data_extensions`.
About **JSON**: `.json` is the strictest case — *every* tracked JSON anywhere needs an entry (or an exempt
path). The inventory currently declares **167** data files while the tree has **177** data-like files; the
10-file gap is exactly the exempt `docs/refoundation/*/_evidence/*` set (measured: gate output
`tree.data_files` + `inventory.entries.count`).

### 1.6 `--write-inventory`: the exact procedure

`write_inventory()` :634-657 → `generate_inventory()` :599-631, which iterates **`tracked_files()` only**.
Therefore:

```powershell
# 0) the files must be in the INDEX first, or --write-inventory will not see them
git add research/science_001
# 1) regenerate (the only supported way; never hand-sort or hand-patch the header)
python tools/governance/check_licence.py --write-inventory
# 2) review the diff: every added entry must carry the right source_id/status/content
git diff docs/governance/DATA_INVENTORY.yaml
# 3) human review list (prints per-source counts)
python tools/governance/check_licence.py --summary
# 4) verify, including the PR-diff layer
python tools/governance/check_licence.py --base origin/main
```

The writer emits a 3-line header comment + `yamlmini.dumps(document)` with
`schema: medradar.data_inventory.v1` and entries in `sorted(path)` order (:622-630, :636-643). Keep the file
generator-shaped: hand insertions that change ordering/formatting get re-shuffled by the next
`--write-inventory` (noisy diff), and flow-style YAML is rejected by `yamlmini`.

**Minimal correct entry — real template already in the repo** (`DATA_INVENTORY.yaml:568-572`):

```yaml
  - path: research/forecasts/FORECAST_SET_2026-11-03.json
    source_id: medradar_derived_artifacts
    status: GREEN
    content: json
    synthetic: false
```

A `.csv` entry is identical with `content: csv`. **Careful with `.bin`/`.csv`:** the WIP `*.bin` files **and** the two `artifacts/*.csv`
files sniff as **`text`** (measured; see §1.8), not `binary`/`csv`. Writing `content: binary` or
`content: csv` fails `inventory.content_match` (and, if a file really were binary, `content.restricted_kind`).
Use the value the gate detects.

### 1.7 Untracked data files: they fail, and they also fail pytest

`check_untracked()` :532-546 reports `untracked.data_file` for any untracked, non-ignored data candidate.
Because it runs `git ls-files --others --exclude-standard`, files under `data/` (raw downloads) and
`experiments/**/pred_*.json` are invisible to the gate — that is the intended home for raw SEC bytes.

This is not only a gate concern: `tests/governance/test_check_licence.py:148-161`
(`RealRepositoryBaselineTests.test_current_repository_is_clean`) runs the **full** check (tree + untracked,
`base=None`) against the real repo, so **leaving untracked data files in the working tree fails pytest**.
Measured today: that is the single failing test (§4.4).

### 1.8 Live measurement on the current WIP tree (2026-11-14)

`python tools/governance/check_licence.py --base origin/main` → **FAIL** (53 checks, 40 failures = 20 distinct
files × {untracked, diff}). **The set is a moving target** — it grew from 9 to 20 files between two runs while
the package was being built, so re-run the gate immediately before regenerating the inventory. The 20 files
measured at this snapshot:

```text
research/science_001/artifacts/issuer_identity.json                      json
research/science_001/artifacts/sample_report.json                        json
research/science_001/artifacts/panel_filings.csv                         text   <-- not csv
research/science_001/artifacts/verification_sample.csv                   text   <-- not csv
research/science_001/evidence/sec_docs/_tools/manifest_q1.json           json
research/science_001/evidence/sec_docs/_tools/manifest_q2.json           json
research/science_001/evidence/sec_docs/_tools/manifest_q3.json           json
research/science_001/evidence/sec_docs/_tools/manifest_q4.json           json
research/science_001/evidence/sec_docs/_tools/manifest_q5.json           json
research/science_001/evidence/sec_docs/_tools/manifest_q6.json           json
research/science_001/evidence/sec_docs/_tools/manifest_q7.json           json
research/science_001/evidence/sec_docs/raw/_meta.json                    json
research/science_001/evidence/sec_docs/raw/daily-index-2024-q4-json.json json
research/science_001/evidence/sec_docs/raw/fts-api.json                  json
research/science_001/evidence/sec_docs/raw/submissions-json-CIK0000064670.json json
research/science_001/evidence/sec_docs/raw/company-idx-sample.bin        text   <-- not binary
research/science_001/evidence/sec_docs/raw/form-idx-sample.bin           text   <-- not binary
research/science_001/evidence/sec_docs/raw/hdr-0000064670-13-000009.bin  text   <-- not binary
research/science_001/evidence/sec_docs/raw/hdr-0000064670-14-000008.bin  text   <-- not binary
research/science_001/evidence/sec_docs/raw/hdr-sgml-medtronic-8k.bin     text   <-- not binary
```

**Do not guess `content:` from the extension.** Measured: both `artifacts/*.csv` sniff as `text`, and all five
`.bin`/`.hdr` files sniff as `text`. `detect_kind()` only calls a file `csv` when ≥2 of its first five non-empty
lines share an identical delimiter count (so quoted/irregular CSVs classify as text). Writing `content: csv` or
`content: binary` for these fails `inventory.content_match` (:446-453). The authoritative value is what
`--write-inventory` writes.

Everything else in that tree carries no inventory obligation: `.html`/`.txt`/`.xml`/`.py`/`.md` are text and
not data extensions; `.pdf` sniffs as pdf (a non-restricted media kind). So the PDF/HTML/TXT evidence — the
bulk of the raw SEC corpus — is free to commit; only JSON/CSV/BIN need entries.

---

## 2. What runs on a PR, exactly

Only **two** workflows trigger on `pull_request`: `ci.yml` (:3-6: `push: main` + `pull_request`) and
`governance.yml` (:22-24: `pull_request` + `workflow_dispatch`). `live.yml`, `weekly.yml` and
`forecast-cycle.yml` are schedule/dispatch-only (verified in their `on:` blocks) — they will **not** judge the PR.

### 2.1 `governance / state` — `python tools/governance/check_state.py`

Command: `governance.yml:46-47` (fetch-depth 0 so `origin/main` exists). Validates `PROJECT_STATE.yaml`
against git and the measured test artifact. Relevant failure conditions:

* `git.head` must be **an ancestor of `origin/main`** — stale-but-ancestor is only a WARNING
  (`check_state.py:306-337`); wrong lineage is a failure.
* `git.tracked_files` / `committed_at` / `commit_subject` / `workflows` are validated **against the recorded
  observed commit**, not the branch (:338-386). **So adding files to the PR branch does not make
  `tracked_files: 1135` wrong** (`PROJECT_STATE.yaml:36`). Do not "fix" it.
* `tests.collected/passed/skipped/failed` must agree with
  `docs/refoundation/phase0/_evidence/governance/pytest_count.json` (strict; mismatch is a FAIL — :623-647),
  with `passed+skipped+failed == collected` and `failed == 0` (:521-528).
* every string under keys `artifact|evidence|pages_source|path|plan|source|version_source` must be a **relative
  path that exists** (`PATH_KEYS` :56-64, `_walk_paths` / `_check_path` :172-199, called at :996-997).
* `research_studies[]`: unique `id`, required `title|verdict|evidence|public_claim`, and `freeze_ref` must be an
  existing `FZ-nnn` in `FROZEN.yaml` (:708-732).
* Measured now: **PASS** (253 checks, 0 failures, 2 warnings — both "tested_head 562521a is ahead of the
  observed head").

### 2.2 `governance / views` — `gen_views.py`, then `git diff --exit-code -- README.md CHANGELOG.md docs/RESEARCH_INDEX.md`

`governance.yml:59-67`. The three generated views are `README.md` (status block), `CHANGELOG.md` (unreleased
block) and `docs/RESEARCH_INDEX.md` (whole file) — `gen_views.py:568-580`. A hand-edited region is detected as
**tampered** (source/payload digest mismatch, :379-398); a stale one is rewritten and then fails `git diff`.
**If you add a `research_studies`/`capabilities` entry to PROJECT_STATE.yaml you must commit the regenerated
three files in the same commit.** If you do not touch the state file, this job is untouched.
Measured now: **PASS** (all three up to date).

### 2.3 `governance / frozen` — `python tools/governance/check_frozen.py --base origin/main`

`governance.yml:81-82`. Freeze coverage today (`FROZEN.yaml:20-180`): `research/forecasts/FORECAST_SET_*.json`
(FZ-001/002/011), six `early_signal_5firms` files (FZ-003..006), the **whole directory manifest** of
`research/studies/early_signal_5firms` with `no_new_files: true` (FZ-010), and `papers/CLAIMS.json` (FZ-012).
**`research/science_001` is not frozen** → adding files there cannot fail this gate.

Facts worth knowing:

* Adding a **new top-level** freeze entry is allowed without a rebalance ("new coverage = strengthening",
  `check_frozen.py:20-21, 390-398`); changing/removing a digest or adding a file inside a frozen directory
  requires a `rebalances:` record with `previous_sha256`/`new_sha256` and a `decision_id` that exists as `## D-nnn`
  in `research/DECISIONS.md` or as an id in `docs/governance/DECISION_LOG.yaml` (:254-331, 372-450).
* `FROZEN.yaml` **is a protected governance path** (`check_rule_audit.py:62-67`), so registering a freeze for
  SCIENCE-001 costs an RC-nnnn record + decision id (§2.6). Recommended shape if you do it: a single
  `kind: file` entry for the pre-registered protocol only — never a `kind: directory` with `no_new_files: true`
  over an active evidence directory, or every later artifact edit becomes a rebalance.
* Measured now: **PASS** (36 checks) with `[WARN] rebalance audit skipped: base 'origin/main' is missing or uses an
  older FROZEN.yaml schema` — `origin/main` predates the v2 freeze file. Current-state digests are still checked
  and pass. The audit **activates** the moment the base ref carries `medradar.frozen.v2`.

### 2.4 `governance / licence` — `python tools/governance/check_licence.py --base origin/main`

`governance.yml:97`. See §1. Measured now: **FAIL** (§1.8) — the only failing gate.

### 2.5 `governance / links` — `python tools/governance/check_links.py`

`governance.yml:110`. Scans **only `docs/**/*.md`** (`check_links.py:122`, `docs_dir.rglob("*.md")`), resolves every
relative link/image against the filesystem (:90-113), rejects absolute paths and links escaping the root, skips
external URLs, pure `#fragments` and fenced code (:76-89). A note at
`research/science_001/evidence/repo_recon.md` is **not** link-checked; but any link you add **inside `docs/`**
(including the generated `docs/RESEARCH_INDEX.md`) must resolve. Measured now: **PASS** (56 markdown files,
181 links).

### 2.6 `governance / rule-audit` — `python tools/governance/check_rule_audit.py --base origin/main`

`governance.yml:125`. Protected paths (`check_rule_audit.py:62-67`): `.github/workflows/governance.yml`,
`tools/governance/**`, `docs/governance/DATA_LICENSES.yaml`, `docs/governance/FROZEN.yaml`.
Excluded audit inputs (:68-72): `RULE_CHANGES.yaml`, `DECISION_LOG.yaml`, **`DATA_INVENTORY.yaml`** — so
regenerating the data inventory never trips this gate. Any protected-path change must be covered by a **new**
RC-nnnn record with `change_id`, existing `decision_id`, `approved_by`, `date`, `reason`, protected `paths`
(:173-253, 280-324). Measured now: **PASS** — 14 protected paths changed vs `origin/main`, all covered by
**3 new records** (RC-0001..RC-0003); **do not drop those commits.**

### 2.7 `ci` — tests and offline smoke

`ci.yml:11-88`:

| Job | Command | Code |
| --- | --- | --- |
| `test` (py 3.10/3.11/3.12 matrix) | `python -m medradar selftest` | :18-29 |
| same | `python -m medradar --help`, `python -m medradar status --db data/none.sqlite`, `python scripts/check_install.py`, `medradar demo` | :31-44 |
| same | installed-wheel config smoke: asserts `c.CONFIG_ORIGIN == "installed"` and `len(load_companies('device').all()) > 0` from a temp cwd | :34-37 |
| `data-stats` | `python -m unittest tests.test_stats_cmd -v` + `data_stats` JSON contract smoke | :57-60 |
| `windows-install` | selftest, install smoke, `scripts/nightly.ps1 -SkipCollect -SkipTrade -SkipReplay -SkipAnalyze -SkipReport -NoDataMd`, `medradar demo` | :63-88 |

`python -m medradar selftest` is **unittest discovery**, not pytest:
`unittest.TestLoader().discover(tests/, top_level_dir=<repo root>)` (`medradar/__main__.py:751-757`). New tests
must live in `unittest.TestCase` classes under `tests/` or CI silently will not run them (while local pytest
counts them → test-count drift, §2.8). Python floor is `>=3.10` (`pyproject.toml:6`) and the matrix really
runs 3.10 — the branch already needed a 3.10 `Z`-timestamp fix (`tools/governance/check_state.py:44-53`, commit
`6784043`).

### 2.8 The required update procedures (and what `bump_state.py` is *not*)

* **New/changed data file → `DATA_INVENTORY.yaml`.** `git add` → `check_licence.py --write-inventory` → review
  the diff → commit together (`GOVERNANCE.md:257-258`; §1.6).
* **`PROJECT_STATE.yaml` → regenerate the three views** in the same commit: `gen_views.py`
  (`GOVERNANCE.md:30-32`). `bump_state.py` refreshes **only** `git`/`verified`/`release.version` from a ref
  (:192-250) and then runs `gen_views.py` (:369-378). It never touches `tests`, `data_snapshot`, `capabilities`,
  `research_studies`, `decisions` or `not_claimed`. It is the post-merge tool
  (`GOVERNANCE.md:59-71`) — **do not run it to describe this branch**: the PR template requires that
  "PROJECT_STATE.yaml still describes `main` … not this branch" (`.github/pull_request_template.md:88-89`).
  If you must refresh, use `bump_state.py --ref origin/main --dry-run` first and keep `git.head` on `origin/main`.
* **Tests changed → `record_tests.py`.** It runs `python -m pytest -q -o addopts=` (`record_tests.py:33`),
  refuses to write while `tests/` has uncommitted/untracked changes vs HEAD (:107-125), and writes
  `docs/refoundation/phase0/_evidence/governance/pytest_count.json` with `schema: medradar.test_count.v1`,
  the counts, `tested_head` and `tests_unchanged_from_head: true` (:166-186). **Then** hand-update
  `PROJECT_STATE.yaml tests:` and re-run `gen_views.py`. Order: commit tests → `record_tests.py` → edit state →
  `gen_views.py` → commit.
* **Freeze / licence-rule / gate / workflow change → `RULE_CHANGES.yaml` RC-nnnn record** with a decision id
  (`GOVERNANCE.md:263-265`, `check_rule_audit.py`).

---

## 3. Reusable modules (import path, signature, example)

All stdlib-only, deterministic, no network unless noted. **Do not import `tools/governance/**` from research
code** — it is a gate toolkit, not a package dependency; only tests reach it via `tests/governance/gitfix.py`.

### 3.1 HTTP with throttle, disk cache and offline replay — `medradar.http`

```python
from medradar.http import Fetcher, HttpError, NotFound, OfflineMiss, BudgetExceeded
Fetcher(cache_dir=None, fixtures_dir=None, offline=False, min_interval=0.25,
        timeout=45.0, max_requests=1200, ua=DEFAULT_UA)              # http.py:53-63
.get_json(url, params=None, retries=3, backoff=2.0, refresh=False)   # :75-99
.get_text(url, params=None, retries=3, backoff=2.0, refresh=False)   # :133-158
.post_json(url, payload, retries=3, backoff=2.0, refresh=False)      # :101-131
```

* cache key = `sha1(full_url_with_params)[:24]` (:161-175); files `cache_dir/<key>.json|.txt` (:97-98,
  156-157); lookups try `fixtures_dir` first, then `cache_dir` (:177-184). POST keys carry a
  `#body=<sha1>` fragment for identity that is stripped before the request (:114-116, 216).
* `offline=True` replays cache/fixtures only and raises `OfflineMiss` on a miss (:85-90, 117-122, 148-154) —
  this is what makes the whole suite network-free.
* politeness: `min_interval` throttle (:186-192), hard `max_requests` budget → `BudgetExceeded` (:194-199),
  retries on 429/5xx honouring `Retry-After` with exponential backoff (:201-257), 404 → `NotFound`.
* **SEC needs a declarative User-Agent.** The module default (`http.py:27-30`) has no contact e-mail; pass
  `ua=SEC_UA` from `medradar.live` — `SEC_UA = os.environ.get("MEDRADAR_SEC_UA", "MedRadar research
  (open-source; contact: medradar@example.com)")` (`medradar/live.py:63-64`, already used by
  `scripts/build_corpus.py:89-97` and `medradar/intelligence/pipeline.py:37`).

```python
from medradar.http import Fetcher
from medradar.live import SEC_UA
from medradar.config import DATA_DIR
f = Fetcher(cache_dir=DATA_DIR / "cache" / "sec", min_interval=0.35, max_requests=900, ua=SEC_UA)
submissions = f.get_json("https://data.sec.gov/submissions/CIK0000064670.json")
```

### 3.2 ISO-8601 moment parsing/rendering — `medradar.tkg._time`

```python
from medradar.tkg._time import parse_iso8601, render_moment
parse_iso8601(text: str) -> datetime   # :42-50  Z -> +00:00; 1-9 fractional digits normalised to 6
render_moment(utc: datetime) -> str    # :53-55  %Y-%m-%dT%H:%M:%S.<microsecond:06d>Z
```

```python
from datetime import timezone
from medradar.tkg._time import parse_iso8601, render_moment
acceptance = parse_iso8601("2024-03-01T16:05:00.5Z").astimezone(timezone.utc)
stamp = render_moment(acceptance)      # '2024-03-01T16:05:00.500000Z'
```

**Trap:** `render_moment` formats the given datetime's own wall clock and appends `Z`; it does **not** convert
the zone. Rendering a `+08:00` value directly yields a wrong instant — always `.astimezone(timezone.utc)` first.
Use this pair (not `util.iso_moment`) when lexicographic order must equal chronological order (fixed-width µs,
:12-15). For *dates* prefer `medradar.util.parse_date / iso / iso_moment / month_key / quarter_index`
(`util.py:25-104`).

### 3.3 Hashing / canonical JSON — `medradar.evidence_core.ledger`

```python
from medradar.evidence_core.ledger import sha256_hex, canonical_json, content_hash
canonical_json(value) -> str           # :72-74  sorted keys, (",",":"), ensure_ascii=False, allow_nan=False
sha256_hex(text: str) -> str           # :77-78  takes a str, not bytes
content_hash(snapshot: Mapping) -> str # :89-92  event-schema-specific (EVENT_CONTENT_FIELDS, :34-62)
```

```python
from medradar.evidence_core.ledger import canonical_json, sha256_hex
digest = sha256_hex(canonical_json({"accession": "0001193125-24-000123", "filed": "2024-03-01"}))
```

`content_hash` is only correct for event rows (it strips `first_seen_at/fetched_at/as_of`, :56-62); do not
reuse it as a generic document hash. The repo's precedent for a content-addressed manifest is
`medradar.corpus.corpus_sha1(records)` (`corpus.py:857`) over sorted JSONL — sha1, matching `util.sha1`
(`util.py:167-168`). There is **no** generic `sha256_file`/`sha256_bytes` in `medradar`; the only byte-level
sha256 helpers are `tools/governance/common.py:145-158`, which research code should not import. If file digests
are needed, write six lines with `hashlib` inside the research package.

### 3.4 Statistics — what exists, what is missing

`medradar/stats.py` (stdlib, deterministic, seeded; `__all__` :55-89):

| Function | Signature (line) | Note |
| --- | --- | --- |
| `mean median stdev t_stat` | `(values, ddof=1)` :106-152 | `t_stat` returns `None` if n<2 or zero variance |
| `ranks pearson spearman mae` | :156-211 | average ranks, tie-safe |
| `normal_cdf normal_ppf student_t_sf t_p_value` | :215-322 | incomplete-beta t tail, no scipy |
| `bonferroni holm multiple_testing` | `(p_values, alpha=0.05, labels=None)` :397-457 | `multiple_testing(method="holm"|"bonferroni")` |
| `block_bootstrap_ci` | `(values, blocks=None, *, weights=None, stat_fn=None, stat_name="mean", n_boot=2000, alpha=0.05, seed=7)` :474-570 | **cluster** percentile CI; fewer than 2 blocks → `lo/hi=None` |
| `block_bootstrap_p_value` | `(values, blocks=None, *, stat_fn=None, n_boot=2000, seed=7)` :574+ | two-sided bootstrap p for H0: stat==0; **not in `__all__`** but public |
| `time_split / time_split_by_dates` | `(items, *, key="event_date", fractions=(0.6,0.2,0.2), labels=("dev","validation","holdout"), dev_end=None, validation_end=None, return_items=False)` :877-1031 | never splits an event day |
| `equal_weights market_cap_weights normalize_weights weighted_mean` | :1035-1121 | cap weights need *as-of* caps |
| `survivorship_flags` | :1125-1192 | `no_ticker / no_prices / delisted_before_window_end` |
| `mde required_n power_hint` | :1196-1291 | "no effect detectable at this power" wording |
| `aggregate_event_study / research_block` | :700+, :1295+ | full metrics block with Holm + survivorship |

`medradar/intelligence/evalstats.py`: `average_precision` (= `metrics.pr_auc`), `average_precision_weighted`,
`clustered_bootstrap_delta_ap(labels, probabilities_a, probabilities_b, clusters=None, *, resamples=2000,
seed=7, confidence=0.95)` (:297-393), `clustered_bootstrap_metric_ci(..., metric="brier"|"ece")` (:396-469),
`mde_from_se` (:524+), and `matched_far_lead_time(units, *, scores=("score_a","score_b"), label_key="label",
event_date_key="event_date", origin_date_key="origin_date", censor_date_key="censor_date", unit_id_key="unit_id",
far=0.10, curve_fars=(0.01,0.02,0.05,0.10,0.20))` (:1040+) — the matched-FAR lead-time machinery is directly
reusable for a point-in-time lead-time study.

`medradar/intelligence/evaluation/metrics.py`: `pr_auc(labels, probabilities)` (:10), `brier` (:36),
`ece(labels, probabilities, bins=10)` (:40), `paired_bootstrap_delta_ap(labels, a, b, *, resamples=2000,
seed=7, confidence=0.95)` (:77-120, **i.i.d. row bootstrap**, not cluster-robust).

**Missing and must be written** (verified by grep — no implementation anywhere in `medradar/`):

1. **ROC AUC.** Only PR-AUC / average precision exists (`metrics.pr_auc`, re-exported as
   `evalstats.average_precision`, `evalstats.py:44-45`). No `roc_auc`, no rank-sum AUC. If the study reports
   ROC AUC you must write it (tie-aware, ~20 lines).
2. **A permutation / randomisation test.** No `permutation`/`permute` symbol exists in `medradar/`.
   `block_bootstrap_p_value` (`stats.py:574`) and `evalstats`'s `p_delta_le_zero` are **bootstrap** tail
   proportions, not permutation tests under a sharp null — a different inferential object. This is the main
   genuinely-new statistics to write; reuse `stats.ranks`/`block_bootstrap_ci` mechanics and
   `random.Random(seed)` for determinism.
3. Exact/binomial tests (Fisher, McNemar), Wilcoxon/Mann-Whitney, survival/log-rank: absent.
4. BH (Benjamini-Hochberg) FDR: only Holm/Bonferroni exist, and `multiple_testing` raises `ValueError` on an
   unknown method (`stats.py:457`) — no silent fallback.
5. Any clustered regression: absent (no numpy/pandas anywhere — `pyproject.toml:11` dependencies = []).

**Explicit "do not reuse as-is" warnings**

* `medradar.util.bootstrap_ci(values, stat=None, n_boot=2000, alpha=0.05, seed=7)` (`util.py:234-255`) is an
  **i.i.d. row** percentile bootstrap. With overlapping/event-day-correlated observations it understates the
  interval — the repo says so itself (`stats.py:13-20`). Use `stats.block_bootstrap_ci`.
* `metrics.paired_bootstrap_delta_ap` (`metrics.py:77-120`) is i.i.d. row resampling; for clustered data use
  `evalstats.clustered_bootstrap_delta_ap`.
* `t_stat` is one-sample vs zero and returns `None` for zero variance; weighted means deliberately get no t/p
  (`docs/RESEARCH.md:131`).
* `evalstats` costs O(resamples × rows) in pure Python (`evalstats.py:324-326`) — fine for hundreds of EDGAR
  events, but do not point `clustered_bootstrap_*` at a 40k-row panel without a plan.

### 3.5 Company/config universe — `medradar.config` + `config/companies_device.json`

```python
from medradar.config import load_companies, load_tracks, load_config, CONFIG_DIR, DATA_DIR
load_companies(kind: str = "device") -> CompanyRegistry   # :314-316
load_tracks(kind: str = "device") -> TrackRegistry        # :319-337
load_config(name: str, default=None) -> Any               # :157-169
# CompanyRegistry: .get(key) -> dict|None, .all() -> list[dict], .keys() -> list[str],
#   .major_keys() -> list[str], .tickers() -> dict[str,str], .resolve(applicant, min_score=0.82)
#                                                        # :190-234
```

```python
from medradar.config import load_companies
reg = load_companies("device")
tickers = reg.tickers()                              # key -> ticker, 44 of 51 companies
key, conf, alias = reg.resolve("MEDTRONIC MINIMED")  # ('medtronic', 1.0, 'MEDTRONIC MINIMED')
```

`config/companies_device.json` structure: `{schema: 1, updated, currency, notes, companies: [{key, name_en,
name_zh, ticker, sector, is_major(0/1), aliases: [...]}]}` — **51 device companies**, 15 majors (`is_major: 1`).
Tickers: `MDT JNJ ABT BSX SYK ZBH EW ISRG SHL.DE PHG GEHC BDX BAX RMD MASI DXCM PODD TNDM PEN GMED HOLX TFX COO
ALC XRAY IART IRTC INSP PRCT ATRC NVRO OFIX MMSI ICUI AMBU-B.CO IVC SNN TRUMY FMS OCPNY FUJIY CAJ STE NVST`.
**7 have no ticker** (`cook_medical`, `wl_gore`, `biotronik`, `bbraun`, `medline`, `karl_storz`,
`pentax_medical`) → they can never enter a price-based sample; `stats.survivorship_flags` (`stats.py:1125`) is
the repo's mandated way to disclose that. Config resolution is a chain env → source `config/` → installed
`share/medradar/config` → in-package (`config.py:100-121`); the wheel ships `config/*.json|csv` as data-files
(`pyproject.toml:38-40`) and CI asserts `CONFIG_ORIGIN == "installed"` from a temp cwd (`ci.yml:34-37`).
Config JSON is "knowledge", covered by the `curated_configuration` GREEN source
(`DATA_LICENSES.yaml:153-159`).

### 3.6 EDGAR-specific reuse (highest-leverage finding)

* `medradar/corpus.py` — **pure functions, no network/SQLite**, built exactly for SEC 8-K point-in-time work:
  `clean_html` (:362), `truncate_text` (:396), `parse_display_name` (:412), `is_healthcare_company` (:435),
  `filing_url` (:454), `parse_fts_hit` (:466), `merge_candidates` (:518), `classify`/`classify_detail`
  (:689-766), `build_record` (:768), `read_jsonl`/`load_corpus` (:827-856), `corpus_sha1` (:857),
  `stratified_subset` (:873), `write_corpus` (:937), `merge_corpora` (:967), `build_manifest` (:1035),
  `summarize` (:1105), `to_events` (:1171). Constants: `CORPUS_VERSION`, `SOURCE = "sec_edgar_8k"`,
  `KIND = "8k_catalyst"`, `ARCHIVES_BASE`, `FTS_ENDPOINT`, `MAX_TEXT_CHARS = 24_000` (:53-60). Its stated
  PIT rule — "`event_date` is the 8-K `file_date` (the moment the announcement became public)"
  (`corpus.py:20-22, 1174`) — is exactly the anchor a point-in-time study needs; reuse the convention instead of
  re-deriving it.
* `scripts/build_corpus.py` — the crawler: `quarter_windows` (:101), `half_year_windows` (:131),
  `windows_for` (:162), `cmd_search` (FTS pagination, :332-380), `fetch_filing_text` (:533-563), `cmd_fetch`
  (resumable, :639), `cmd_build` (:775), and `_make_fetcher` binding `ua=SEC_UA` (:89-97).
* `medradar/live.py` — `SEC_UA` (:63-64), `EDGAR_TICKERS` (:54), `EDGAR_FTS` (:60), and the EDGAR archive URL
  builders (:351-396).
* `medradar/intelligence/sources/sec_financials.py` — XBRL `companyfacts` collector (ticker→CIK map :36-42,
  `collect(store, fetcher, *, companies=None, limit=0)` :80-119); it stores "consolidated entity facts, not
  reliable product/segment revenue" (:1-7) — a scope limit to carry into the new study.
* `medradar/eventstudy.py` — `run_event_study(db, horizons=DEFAULT_HORIZONS, benchmark="SPY", signal_kind=None,
  min_events=MIN_EVENTS)` (:286-292): SQLite-bound abnormal-return study with block-bootstrap CIs.
* `medradar/intelligence/evaluation/backtesting.py` — `run_backtest(examples, base_features, ...)` (:226),
  `eligible_training_rows` (:85), `matured_by` (:78), `label_window_end` (:56) — rolling-origin / maturity
  gates; `medradar/intelligence/evaluation/leakage_audit.py` `audit_examples(store, dataset_version)` (:298)
  replays features as-of a cutoff.

---

## 4. Test conventions and the real suite numbers

### 4.1 Layout and style

`tests/` is the only `testpaths` (`pyproject.toml:42-44`, `addopts = "-q"`): one `test_<module>.py` per
module, `tests/governance/` for the gate tests (with `tests/governance/gitfix.py` building throwaway fixture
repos and `tests/governance/fixtures/`), `tests/fixtures/` for static data. Style is `unittest.TestCase`
throughout (class per concern, `self.subTest`, `unittest.mock.patch`) — that is what CI's unittest discovery
runs.

### 4.2 How network is kept offline (three established idioms)

1. **Fixture replay through the real `Fetcher`** — `tests/test_device.py:470-471`:
   `Fetcher(fixtures_dir=FIXTURES_DIR, offline=True, min_interval=0)`. Fixture names are
   `sha1(full_url_with_params)[:24] + ".json"` (`http.py:161-163, 177-184`), generated by
   `tests/fixtures/device/_generate.py` (e.g. `tests/fixtures/device/3a567d2a37c43abeec665049.json`). A URL
   with no fixture raises `OfflineMiss` (asserted as a feature, `tests/test_device.py:593`).
2. **Scripted fake fetcher** — a per-test-module `class FakeFetcher` exposing exactly
   `get_json(url, params=None, refresh=False, **kwargs)` plus `.calls`/`.stats`, driven by a
   `handler(url, params, refresh, n)` closure (`tests/test_device.py:39-51`; same pattern in
   `tests/test_drug.py:25`, `tests/test_frontier.py:24`, `tests/test_quant.py:134`,
   `tests/test_replay.py:99`). There is **no shared base class** — copy the 12-line class.
3. **Patched transport** for the retry/POST path —
   `patch("medradar.http.urllib.request.urlopen", side_effect=...)` (`tests/test_intelligence.py:156-163`).

`_NoSleepMixin` (`tests/test_device.py:29-36`) patches the collector's sleep so retry tests never wait.

### 4.3 Exact commands

```powershell
# canonical recorded command (record_tests.py:33; PROJECT_STATE.yaml:55)
python -m pytest -q -o addopts=
# equivalent for humans (pyproject already sets -q and testpaths=tests)
python -m pytest
# what CI actually runs for tests (unittest discovery, medradar/__main__.py:751-757)
python -m medradar selftest
# CONTRIBUTING.md:34
python -m unittest discover -s tests -t .
```

### 4.4 Measured suite size and duration (real run, this machine)

`python -m pytest -q -o addopts=` on this worktree:
**1160 collected → 1 failed, 1156 passed, 3 skipped, 224 subtests passed in 81.13 s (0:01:21).** No network.
The single failure is **not** a code defect: it is
`tests/governance/test_check_licence.py::RealRepositoryBaselineTests::test_current_repository_is_clean`,
failing on the untracked `research/science_001/...` data files (§1.7/§1.8). With those files either absent
(raw data under gitignored `data/`) or added with inventory entries, the expected result is
**1157 passed / 3 skipped / 1160 collected ≈ 81 s**, matching `PROJECT_STATE.yaml:49-59`
(`collected: 1160, passed: 1157, skipped: 3`). Fast subset for a smoke signal:
`python -m pytest tests/governance -q` (gate tests) or
`python -m pytest tests/test_corpus.py tests/test_stats.py tests/test_evalstats.py -q` (seconds).

---

## 5. Constraints a research PR must respect

### 5.1 Repo-level rules

* **No `AGENTS.md` in this repository** (glob `**/AGENTS.md` → none). The binding documents are
  `CONTRIBUTING.md`, `docs/governance/GOVERNANCE.md`, `docs/RESEARCH.md`, `research/DECISIONS.md` and
  `.github/pull_request_template.md`.
* `CONTRIBUTING.md:38-42`: stdlib only, core must run on bare Python 3.10+; collectors only write `events`;
  **every new metric updates `docs/METHODS.md` AND `docs/SCHEMA.md` first**; no look-ahead (features use only
  data timestamped `<= event_date`); never invent data — return `unavailable` and say why.
* `docs/RESEARCH.md` is the pre-registered protocol: hypotheses must be registered in the §1 table before
  their p-values count as confirmatory (:33-45), sample split by event day (:61-101), block bootstrap
  (:107-123), Holm + Bonferroni (:144-164), MDE on nulls (:172-182), survivorship count shown (:196-207). A study
  whose numbers appear outside those rules is "exploratory" by policy.
* `research/DECISIONS.md:1-6`: ADR-style `## D-nnn — title`, append-only, superseded entries keep a pointer.
  A new decision id is the currency for freeze rebalances and rule-change records.
* `.gitignore`: `data/` and `out/` are ignored (:2-3) — raw SEC downloads belong there; `*.xlsx` is ignored
  (:19); `experiments/**/pred_*.json` is ignored (:29); `_evidence/` is **not** ignored (docs evidence is
  committed). `.gitattributes`: `* text=auto eol=lf` — write JSON/YAML/MD with LF newlines.
* `ci.yml:18` matrix `3.10/3.11/3.12`: no 3.11+-only syntax.

### 5.2 PR-template obligations (`.github/pull_request_template.md`)

Classification "Research artifact" (:17); an evidence table — every number needs a committed artifact **and a
reproducing command** (:36-48); paste gate exit codes (:50-59); a "not claimed" statement (:66-73); the freeze
checklist (:74-80); and the ancestry block requiring `PROJECT_STATE.yaml` to still describe `main`
(:82-89). "Nothing beyond the artifact above is claimed" is acceptable; an unbacked number is not.

### 5.3 Naming / placement

There is no formal study-directory naming rule. Precedent is `research/studies/<snake_case>/`
(`research/studies/early_signal_5firms/`) while `research/science_001/` is the name already chosen on this
branch. What is **load-bearing** is the root: `research/**` is the pattern that makes artifacts
`medradar_derived_artifacts`/GREEN (`DATA_LICENSES.yaml:144-151`) — keep every new artifact under
`research/` and never introduce a data file at the repository root (it would be `unclassified`/RED).

---

## 6. Bottom line (actionable)

1. **Only ONE non-code file is mandatory** for a research-only PR: `docs/governance/DATA_INVENTORY.yaml` (one
   entry per new tracked `.json`/`.jsonl`/`.csv`/`.bin`/etc.). `DATA_INVENTORY.yaml` is excluded from the rule
   audit (`check_rule_audit.py:68-72`), so it needs no RC record.
2. **The only gate that fails today is `licence`** (40 failures = 20 files × {untracked, diff} at the
   latest snapshot; the set is growing — re-check). Remedy: `git add research/science_001` →
   `python tools/governance/check_licence.py --write-inventory` → review → commit. Every entry will be
   `source_id: medradar_derived_artifacts`, `status: GREEN`, `synthetic: false`; `content` must be the
   **detected** kind (`json` for the `.json` files, `text` for the `.csv` and `.bin` files here — see §1.8).
   Re-run `--base origin/main` and the pytest licence baseline test afterwards.
3. **Do not** touch `DATA_LICENSES.yaml` (SEC and `research/**` are already GREEN) and **do not** touch
   `FROZEN.yaml` unless you deliberately want a freeze: that path is protected and costs RC-nnnn + a decision
   id. `research/science_001` is currently outside every freeze.
4. **Do not bump/modernise `PROJECT_STATE.yaml` to describe this branch** (PR template :88-89). Only if you
   register the study/capability or add tests: update the state, then `python tools/governance/gen_views.py`, and
   (for tests) `python tools/governance/record_tests.py` first.
5. **Keep the 36 governance commits** (3 RC records covering 14 protected paths) or `rule-audit` fails.
6. **Reuse, don't rewrite:** `medradar.http.Fetcher` (+ `medradar.live.SEC_UA`) for HTTP/cache/offline;
   `medradar.tkg._time` for moments; `medradar.evidence_core.ledger.sha256_hex/canonical_json` for hashing;
   `medradar.stats` (block bootstrap, Holm, time split, MDE, survivorship) + `evalstats` (clustered AP
   bootstrap, matched-FAR lead time); `medradar.corpus` + `scripts/build_corpus.py` for EDGAR 8-K retrieval.
   **Missing and to be written:** ROC AUC, a permutation test (the headline gap), BH-FDR, exact tests.
7. **Verification loop:** `python -m pytest -q -o addopts=` (1160 tests, ~81 s) plus the six gates; the CI
   mirror of the suite is `python -m medradar selftest` (unittest discovery), so keep tests as
   `unittest.TestCase`.
