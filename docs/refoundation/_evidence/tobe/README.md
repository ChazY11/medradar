# `_evidence/tobe/` — machine-checkable support for ARCHITECTURE_TO_BE / MIGRATION_PLAN

Owner: `target-architect` (REFOUNDATION-001, task-5). Write scope: this directory only.

| File | What it is | How it was produced |
|---|---|---|
| `verified_invariants.json` | Blob hashes, incremental-scope counts and merge-order facts cited by the two design documents | read-only `git rev-parse`, `git -c core.quotepath=false diff --name-only`, `git rev-list` over already-fetched refs. No fetch, no checkout, no network. |
| `README.md` | this file | — |

## What `verified_invariants.json` lets a reviewer check

1. **`duplicate_blobs`** — the claim that merging `#28` and `#30` duplicates ATLAS code, and that the
   product stack repeats one `product/store.py` blob five times. Each entry is a full 40-hex blob id, so
   `git cat-file -p <blob>` reproduces the file.
2. **`incremental_scope`** — the claim that `#15` and `#16` are *pure additions* once `#14` is on `main`
   (0 files outside their own `research/studies/<id>/` tree), which is what makes the merge order in
   `MIGRATION_PLAN.md` §2.2 safe.
3. **`non_ascii_paths` / `note_git_quoting`** — a concrete migration hazard: 5 of `#16`'s paths (and several
   of `#29`'s) contain German umlauts, so any scripted `git mv` must run with `core.quotepath=false`.
4. **`not_verified_here`** — the explicit list of things this evidence does **not** establish (test count,
   CI status, database sizes, availability of the frozen S-028 input database). Use it to avoid citing this
   file for claims it cannot support.

## Regenerating

```powershell
# from <REDACTED_LOCAL_PATH> (read-only; all refs already fetched)
git rev-parse origin/main
git rev-parse origin/feat/medradar-2.0-mvp:medradar/product/store.py
git rev-parse origin/foundation/atlas-001:medradar/atlas/evidence/schema.py
git rev-parse origin/integration/convergence-001:medradar/atlas/evidence/schema.py
git -c core.quotepath=false diff --name-only origin/feat/observatory-reliability-v1...origin/research/s029-evidence-based-relations
```

## Not stored here

No raw source data, no extracted database rows, no third-party payloads. Everything in this directory is a
hash or a count, which is why it is safe to commit.
