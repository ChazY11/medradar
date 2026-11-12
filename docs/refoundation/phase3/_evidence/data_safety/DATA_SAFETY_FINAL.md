# DATA SAFETY — FINAL MERGE GATE (PR #38, `origin/main..integration/ref003`)

**Task:** `task-22` · final data-safety review before merge
**Target:** `origin/main` (`b2a14c0`) … `integration/ref003` (`cfa685c3`) — PR #38
**Mode:** read-only git; **no history rewrite, no push, no deletion**; the integration worktree was used for `git` commands only.
**Output location:** `<EVIDENCE_OUT>\` (outside every git worktree, per the isolation instruction). A pre-existing untracked copy under the worktree at `docs/refoundation/phase3/_evidence/data_safety/` was **left in place** for the Lead to relocate; nothing else was touched.
**Artefacts:** `scan_history.py` (reproducible), `data_safety_final.json` (masked, 18,197 B).
**Finding-set SHA-256:** `f3c7d208143760abe0416abbcb985bc2b8f88ac0622306776269863c3246bc04`

---

## 0. VERDICT: **PASS**

No restricted value, no credential, and no personal-data list exists in **any reachable commit or blob** of the PR #38 range. Merge is not blocked on data safety.

| Category | Result | Blocks? |
|---|---|---|
| **Restricted Comtrade-derived value** (salted-hash scheme) | **0 blobs / 0 occurrences** | no |
| **Restricted third-party payload records** (Comtrade/UKE/EPMC/Job text markers) | **0 blobs** | no |
| **Credentials** (private keys, `ghp_`, `AKIA`, `sk-`, `xox`, `AIza`, JWT, bearer, credential assignments, `.env`/key paths) | **0 blobs / 0 occurrences** | no |
| **Personal data** — personal e-mails | **0** | no |
| — institutional/alias e-mails | **0** | no |
| — documentation-fixture e-mails (`@example.invalid`) | 1 (test fixture, not PII) | no |
| — phone numbers in contact context | **0** | no |
| — `contactPoint` names / named-person lists | **0 / 0** | no |
| **Absolute local paths / machine identifiers** | **8 occurrences in 5 blobs** (advisory, masked) | no |
| **Large binaries > 1 MiB** | **0** | no |
| Binary blobs (any size) | 2 synthetic fixtures (62 B SQLite header, 51 B gzip fixture) | no |

---

## 1. Scan scope (all commits, all blobs — not just the final tree)

**[FACT]** Method: `git rev-list origin/main..integration/ref003` for the commit set; `git diff-tree -r -m --root --raw <commit>` **per commit** to enumerate every added / modified / **replaced** / deleted blob (merge commits diffed against each parent); `git rev-list --objects base..tip` for the complete object inventory (this is what keeps blobs that were **later replaced** in scope); `git cat-file --batch-check` for type/size; `git cat-file --batch` for byte-exact content; binary blobs sniffed by header only.

| Metric | Count |
|---|---:|
| Commits in range | **24** (19 non-merge + **5 merges**) |
| Objects reachable from tip but not base | **315** |
| In-range blob objects | **151** |
| Blobs referenced by `diff-tree` that already exist on `main` (base-side old blobs) | **6** |
| **Blobs content-scanned** | **157** |
| File-change events (sum of per-commit A/M/D) | **589** |
| Commits with zero files changed | **0** (no skipped commit) |
| Blobs with any finding | **11** |

**[FACT] Replaced-blob coverage is real, not assumed.** The range contains multiple versions of the same path, all scanned: `README.md` **7** blob versions, `docs/governance/DATA_LICENSES.yaml` **4**, `docs/RESEARCH_INDEX.md` **4**, `PROJECT_STATE.yaml` **3**, `README.zh-CN.md` **3**, `docs/governance/DECISION_LOG.yaml` **2**, `PR_TRIAGE.md` **2** (31,724 B → 31,728 B), `governance.yml` **2**, `DATA_INVENTORY.yaml` **2**, plus directory-tree versions. A scan of the final tree alone would have missed these.

**[FACT] No bulk data blob exists in the range.** Largest in-range blob is 170,039 B (`docs/refoundation/phase3/_evidence/pr_metadata_raw.json`, PR metadata); **no blob exceeds 200 KB**, and none is a `.jsonl`/`.csv`/`.parquet`/`.gz` data dump. The two binaries are synthetic test fixtures under `tests/governance/fixtures/` (`fake_market.sqlite` 62 B, `fake_archive.gz` 51 B — header `SQLite format 3` / gzip magic with `SYNTHETIC-RE` payload).

---

## 2. Restricted-value scan (never reproduces the digits)

**[FACT]** The known UN Comtrade-derived cell was searched in three surface forms (plain digits, thousands-separated, decimal suffix) across all 157 blobs **and** independently across the full patch text (`git log -p`, 30,944 lines).

| Surface | Hits |
|---|---:|
| Blob content (157 blobs) | **0** |
| `git log -p` added/removed/context lines (30,944) | **0** |
| Salted-hash records emitted | **0** (scheme ready: `sha256("ref003-data-safety-v1|"+digits)`, first/last 2 chars, count — nothing to store) |

**[FACT]** No other restricted numeric series is present: a payload-marker scan for `"primaryValue"`, `"cifvalue"`, `"hs_description"`, long `"abstractText"`, long `"job_description"`, and `"comtrade_usd"` returned **0** payload blobs.

---

## 3. Masked findings (advisory only — nothing blocking)

### 3.1 Restricted-source *path references* in triage documentation — 4 blobs, 74 matches

These are **documents that name restricted file paths** (they contain no trade values and no record payloads). They are the PR-triage's job: describing which restricted artefacts exist on other branches.

| Path | Rule matches (counts only) | Nature |
|---|---|---|
| `docs/refoundation/phase3/PR_TRIAGE.md` (blob v1, 31,724 B) | comtrade path refs 58, UK-tender path refs 16 | markdown triage table listing file paths |
| `docs/refoundation/phase3/PR_TRIAGE.md` (blob v2, 31,728 B) | same | sanitized re-issue of the same table |
| `docs/refoundation/phase3/_evidence/pr_metadata_raw.json` (170,039 B) | comtrade path refs; UK-tender refs | PR metadata: changed-path lists from the GitHub API |
| `docs/refoundation/phase3/_evidence/pr_triage.json` (57,391 B) | comtrade path refs; UK-tender refs | triage JSON with `risk_path_hits.examples` |

**[INFERENCE]** Naming a restricted file path is not redistributing restricted data; the earlier REFOUNDATION-001 audit's own gate treats path references as informational. **No action required for merge**; if the owner wants a strict "no restricted source named" posture, these four documents would need rewording — that is a policy choice, not a data-safety blocker.

### 3.2 Absolute local paths — 8 occurrences in 5 blobs (masked classes)

| File | Occurrences | Masked class |
|---|---:|---|
| `docs/refoundation/phase2/_evidence/governance/01_environment.txt` (435 B) | 2 | 1 × Windows drive path, **1 × Windows user-profile path** |
| `docs/refoundation/phase3/PR_TRIAGE.md` (31,724 B) | 2 | Windows drive paths |
| `docs/refoundation/phase3/EVIDENCE_CORE_ACCEPTANCE.md` (12,950 B) | 2 | Windows drive paths |
| `docs/refoundation/phase3/_evidence/core_acceptance/run_acceptance.py` (44,078 B) | 1 | Windows drive path |
| `docs/refoundation/phase3/_evidence/core_acceptance/acceptance.json` (27,473 B) | 1 | Windows drive path |

**[FACT]** One occurrence is a **machine identifier class** (user-profile path) inside a Phase-2 environment capture; the rest are worktree drive paths. No values are reproduced here. **[RECOMMENDATION]** Sanitize these five files (replace drive/user segments with `<LOCAL_PATH>`) before or immediately after merge — cheap, and consistent with the Phase-0/Phase-1 sanitization already applied elsewhere. **This does not block the data-safety gate** under the task rule (only restricted value / credential / personal-data list block), but it is the one item that leaves a machine identifier in the public tree.

### 3.3 Documentation-fixture e-mail — 1 occurrence, not PII

`tests/governance/gitfix.py` sets `git config user.email` to an address on the reserved `example.invalid` domain inside a throw-away test repository. **[FACT]** This is a fixture by construction (`example.invalid` is reserved for documentation/testing, RFC 2606) and is **not** personal data. Classified separately from PII; no action required.

### 3.4 Binary blobs — 2, both synthetic, both tiny

`tests/governance/fixtures/fake_market.sqlite` (62 B, header `SQLite format 3`) and `tests/governance/fixtures/fake_archive.gz` (51 B, gzip header, `SYNTHETIC-RE` content). **[FACT]** 62 B / 51 B cannot embed a restricted dataset or a credential list; headers confirm the declared formats. No large binary (> 1 MiB) exists anywhere in the range.

---

## 4. Independent cross-checks (beyond the scanner)

| Check | Result |
|---|---|
| `git log -p` full patch text: restricted value | **0** |
| `git log -p`: `ghp_` tokens | **0** |
| `git log -p`: `AKIA` access-key ids | **0** |
| `git log -p`: PEM private-key headers | **0** |
| Object inventory by `cat-file -t`: blob count | 151 in-range blobs (+6 base-side) = 157 scanned |
| In-range blobs > 200 KB | **0** |
| Source names referenced (not values) | `comtrade` 105, `uk_find_a_tender` 41, `europepmc` 3 — in 5 documentation blobs only; `marketscan`/`iqvia`/`job_description` **0** |

---

## 5. Disposal recommendation

**None required.** No restricted value, credential, or personal-data list was found in any reachable commit or blob, so the history is safe to merge as-is from a data-safety standpoint. Do **not** rewrite history on account of this review; no credential rotation is indicated.

Advisory cleanups (optional, can land after merge):
1. Sanitize the 5 files carrying absolute paths (§3.2), especially the one user-profile occurrence.
2. If policy requires it, reword the 4 triage documents that name restricted source paths (§3.1) — they contain no restricted data.

---

## 6. Limits

- Content scanning is byte/regex-based over **text blobs**; binary blobs are judged by **header + size only** (both are synthetic fixtures under `tests/`).
- Path-reference detection relies on known source names; an unknown restricted source could only be caught by the payload-marker rules, which returned zero.
- Base-side blobs (6) were scanned for completeness but already exist on published `main`; findings there would not be attributable to PR #38.
- No network was used; no repository file was modified; no history or ref was rewritten; no push.

---

## 7. Reproduce

```powershell
python <EVIDENCE_OUT>\scan_history.py `
  --repo <WORKTREE> `
  --base origin/main --tip integration/ref003 `
  --out <EVIDENCE_OUT>
```

Outputs `data_safety_final.json` (masked findings, per-commit file counts, category summary, large-binary list, finding-set hash). The script never emits a sensitive literal: the restricted value is represented only by a salted SHA-256 plus first/last two characters, and PII/credentials are counts only.

**Labels:** `[FACT]` measured; `[INFERENCE]` reasoned; `[RECOMMENDATION]` proposed.
