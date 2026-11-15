# DATA-001 — Snapshot Publication

## Publication pipeline

```text
source records
   │
   ▼
staging/pending-<uuid>/          private; never served
   │  deterministic gzip files + manifest
   ▼
snapshots/fda-snapshot-<ts>-<hash>/   immutable candidate
   │
   ├── manifest/file/record/coverage validation
   ├── product dataset load + device index build
   ├── identity review DB unchanged
   └── record-drop gate
   ▼
active.json (os.replace, fsync)
   ▼
database publication journal + ledger
   ▼
next API request rebuilds Dataset in-process
```

## Validation checks

`validator.py` fails closed. A candidate is not published when any of these fail:

* manifest exists, parses, has the required keys and schema;
* every required file exists and its uncompressed SHA-256, compressed byte size and
  uncompressed byte size match the manifest;
* file record counts and manifest `counts` agree;
* event ids are unique; `(source_id, official_id)` is unique;
* event type is valid for its source;
* applicant, content hash, snapshot hash, first-observed timestamp and event date are
  present/valid where required;
* `first_observed_at` is not in the future and has a timezone;
* manifest coverage dates and per-source/per-type counts agree with the records;
* every scoped query is complete and has no errors; classification coverage is complete;
* source version entries exist (unknown versions are visible, not fabricated);
* the product `load_dataset()` path reads the same record count;
* the device index builds; PMA supplements with a parent outside the tracked scope are
  counted as an explicit gap, not invented as confirmed relations;
* the identity review SQLite file hash is unchanged by validation;
* the record count has not fallen beyond the configured threshold. A drop triggers
  `BLOCKED` unless an operator explicitly passes `--allow-record-drop`.
* every `snapshot_hash` recomputes from the compacted record.

`--allow-record-drop` does not bypass file, identity, coverage or product checks. It only
allows the explicitly reviewed count drop.

## Atomic publish

`active.json` contains the schema, snapshot id, relative path, content hash, previous
snapshot id, publication time, actor and action. It is written to `active.json.tmp`, fsynced,
then `os.replace`d over the live pointer. On POSIX the directory is fsynced. A reader sees
either the old complete pointer or the new complete pointer.

`medradar.product.data_dir.resolve_snapshot_dir()` rejects:

* a pointer that escapes its data root;
* a missing target;
* a pointer whose snapshot id does not match the target manifest;
* malformed JSON.

This is the same resolution used by the dataset loader and the validator, so a path cannot
be validated one way and served another.

## Runtime reload

`DatasetHolder` fingerprints the pointer and resolved manifest. It reloads when the pointer
changes, the review ledger changes, or a failure is cleared. It holds the old dataset while
the new one loads; if the new pointer is unusable, it keeps serving the previous validated
dataset and reports `degraded` from `/api/health` with the error. This is a safe in-process
swap and avoids an intentional two-process memory peak. A controlled `systemctl restart` is
also possible, but only after the candidate has passed validation; the unit does not stop
the old service before validation.

## Rollback

`pipeline rollback <snapshot_id>`:

1. reads the target manifest and checks its id;
2. validates the target (files, product load, device index);
3. writes the active pointer to the target atomically;
4. records the publication action and marks the target active;
5. keeps the newer snapshot and all change evidence on disk.

Rollback is itself a publication; it does not delete history. The change ledger still shows
the changes that were published before the rollback.

## Retention

`pipeline prune --keep N` removes old full snapshot directories but never the active
snapshot. Change evidence lives in SQLite and survives snapshot pruning; review decisions
live in the separate identity-review database and are never touched by pruning.

## Cache note

The legacy PRODUCT-003 code documented a persistent pickle device-index cache, but the
cache was never implemented. DATA-001 does **not** introduce unsafe deserialization. The
device index is rebuilt deterministically from the active snapshot during validation and in
the web process. The environment variable `MEDRADAR_DEVICE_CACHE` is therefore not a
correctness or freshness key; it can be removed or ignored without changing data. This is
listed in `KNOWN_LIMITATIONS.md`.
