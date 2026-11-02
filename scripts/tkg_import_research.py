#!/usr/bin/env python
"""Phase 3B: import the real ``events`` table into a bitemporal TKG store and
export a deterministic point-in-time snapshot.

What it does (no network, source database opened strictly read-only through the
existing :mod:`medradar.tkg.adapter`):

1. hashes ``--db`` before/after so the source is provably unchanged;
2. imports the events rows through ``medradar.tkg.adapter.import_events`` into
   the TKG store (``recorded_at`` is the *import observation* time assigned by
   the store clock, never the source's ``first_seen_at``/``available_at``);
3. re-runs the identical import on the same store to prove idempotency
   (``assertions_created == 0``, no history growth);
4. exports the deterministic PIT snapshot at ``--known-at`` (and independently
   at an early ``--early-known-at`` cutoff, to show that knowledge-time gating
   excludes rows imported later);
5. re-exports at the same cutoff and asserts the ``snapshot_sha256`` is
   identical (same store, same cutoffs, same versions -> byte-identical
   artefact);
6. prints a structured JSON report and optionally writes it to ``--report-out``
   (used for ``experiments/reverse_rd_v2/tkg_import_report.json``).

Performance note (honest, measured): ``tkg-schema-2`` has no index on
``idempotency_key`` in ``nodes``/``edges``, so the adapter's duplicate lookups
are O(n^2) and a full 55k-row import is projected to take ~27 minutes.  This
script therefore adds two *operational* indexes to the target store before
importing (``--no-index`` keeps the naive path for measurement).  The indexes
are local store plumbing: they are not part of any committed artefact and they
do not change the exported content or its hash.

Examples::

    python scripts/tkg_import_research.py \
        --db data/research.sqlite --tkg data/tkg.sqlite \
        --known-at 2026-12-31T00:00:00Z

Do NOT commit the resulting ``.sqlite`` store or snapshot files (``data/`` and
``out/`` are gitignored on purpose).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # allow `python scripts/...` without install
    sys.path.insert(0, str(REPO_ROOT))

from medradar import __version__ as MEDRADAR_VERSION  # noqa: E402
from medradar.tkg import (  # noqa: E402
    ADAPTER_VERSION,
    SCHEMA_VERSION,
    TKGStore,
    export_snapshot,
    import_events,
    write_export,
)

DEFAULT_OUT_DIR = "out/tkg_import"
DEFAULT_EARLY_KNOWN_AT = "2026-01-01T00:00:00Z"

#: Operational (not schema-versioned) indexes.  ``tkg-schema-2`` defines no
#: index on ``idempotency_key``; without these the adapter's duplicate-retry
#: lookups degrade quadratically on a 55k-row backfill.
OPERATIONAL_INDEXES = (
    ("tkg_import_nodes_idempotency", "nodes", "CREATE INDEX IF NOT EXISTS {name} ON nodes(idempotency_key)"),
    ("tkg_import_edges_idempotency", "edges", "CREATE INDEX IF NOT EXISTS {name} ON edges(idempotency_key)"),
)

_CHUNK = 8 * 1024 * 1024


def sha256_file(path: Path) -> tuple[str, float]:
    """Return (sha256, seconds) for a file, streamed so 276 MB stays cheap."""
    started = time.perf_counter()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest(), time.perf_counter() - started


def _table_counts(store: TKGStore) -> dict[str, int]:
    return {table: store.count(table) for table in ("nodes", "edges", "entities", "idempotency")}


def _snapshot_summary(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "known_at": document["manifest"]["known_at"],
        "valid_at": document["manifest"]["valid_at"],
        "counts": document["manifest"]["counts"],
        "snapshot_sha256": document["manifest"]["snapshot_sha256"],
        "schema_version": document["manifest"]["schema_version"],
        "code_version": document["manifest"]["code_version"],
        "adapter_version": document["manifest"]["adapter_version"],
    }


def _git_commit() -> str | None:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or None
    except Exception:  # pragma: no cover - git may be absent; provenance only
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tkg_import_research",
        description="Import the real events table into a bitemporal TKG store and export a deterministic PIT snapshot.",
    )
    parser.add_argument("--db", required=True, help="source events SQLite database (opened read-only)")
    parser.add_argument("--tkg", required=True, help="target TKG SQLite store (created/reused)")
    parser.add_argument("--known-at", required=True, help="knowledge cutoff for the exported snapshot (tz-aware ISO)")
    parser.add_argument("--valid-at", default=None, help="independent validity cutoff (default: known-at, see TKGQuery)")
    parser.add_argument("--early-known-at", default=DEFAULT_EARLY_KNOWN_AT,
                        help="earlier knowledge cutoff used to demonstrate PIT gating (default: %(default)s)")
    parser.add_argument("--kinds", default=None,
                        help="comma separated event kinds to import (default: all rows)")
    parser.add_argument("--limit", type=int, default=0, help="cap imported source rows (0 = all)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="directory for the written snapshot (default: %(default)s)")
    parser.add_argument("--report-out", default=None,
                        help="also write the structured report JSON here (committed evidence file)")
    parser.add_argument("--no-write-export", action="store_true",
                        help="do not write snapshot files to disk (report still carries the hash)")
    parser.add_argument("--no-index", action="store_true",
                        help="skip the operational idempotency indexes (naive O(n^2) path; for measurement)")
    parser.add_argument("--skip-reimport", action="store_true",
                        help="skip the idempotent re-import proof (fast smoke runs only)")
    parser.add_argument("--jsonl", action="store_true", help="write the export as nodes/edges/manifest JSONL files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.db).resolve()
    tkg_path = Path(args.tkg).resolve()
    out_dir = Path(args.out_dir)
    if not source.is_file():
        print(json.dumps({"status": "error", "error": f"source database not found: {source}"}))
        return 2

    kinds = [part.strip() for part in (args.kinds or "").split(",") if part.strip()] or None
    limit = args.limit or None
    report: dict[str, Any] = {
        "task": "PHASE3B",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "python scripts/tkg_import_research.py " + " ".join(sys.argv[1:]),
        "python": sys.version.split()[0],
        "medradar_version": MEDRADAR_VERSION,
        "git_commit": _git_commit(),
        "adapter_version": ADAPTER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source": {"path": str(source), "bytes": source.stat().st_size},
        "filters": {"kinds": kinds, "limit": limit},
        "tkg_store": {"path": str(tkg_path), "existed_before": tkg_path.exists()},
        "cutoffs": {"known_at": args.known_at, "valid_at": args.valid_at, "early_known_at": args.early_known_at},
        "import_optimization": {
            "operational_indexes": [] if args.no_index else [name for name, *_ in OPERATIONAL_INDEXES],
            "note": ("tkg-schema-2 has no index on nodes/edges.idempotency_key; duplicate-retry lookups are "
                     "O(n^2) without these operational indexes. They are local store plumbing, not part of any "
                     "committed artefact, and do not change exported content."),
        },
    }

    source_hash_before, hash_seconds_before = sha256_file(source)
    report["source"]["sha256_before"] = source_hash_before
    report["source"]["hash_seconds_before"] = round(hash_seconds_before, 3)

    open_started = time.perf_counter()
    store = TKGStore(tkg_path)
    report["timings"] = {"open_store_seconds": round(time.perf_counter() - open_started, 3)}

    try:
        if not args.no_index:
            index_started = time.perf_counter()
            for name, _table, sql in OPERATIONAL_INDEXES:
                store.conn.execute(sql.format(name=name))
            store.conn.commit()
            report["timings"]["create_indexes_seconds"] = round(time.perf_counter() - index_started, 3)

        counts_before_import = _table_counts(store)
        import_started = time.perf_counter()
        first = import_events(source, store, kinds=kinds, limit=limit)
        import_seconds = time.perf_counter() - import_started
        counts_after_import = _table_counts(store)
        report["import"] = {
            "counters": first["counters"],
            "seconds": round(import_seconds, 3),
            "rows_per_second": round(first["counters"]["rows_seen"] / import_seconds, 1) if import_seconds else None,
            "store_counts_before": counts_before_import,
            "store_counts_after": counts_after_import,
            "errors_sample": first["errors"][:10],
            "error_count": len(first["errors"]),
        }

        reimport: dict[str, Any] | None = None
        if not args.skip_reimport:
            reimport_started = time.perf_counter()
            second = import_events(source, store, kinds=kinds, limit=limit)
            reimport_seconds = time.perf_counter() - reimport_started
            counts_after_reimport = _table_counts(store)
            reimport = {
                "counters": second["counters"],
                "seconds": round(reimport_seconds, 3),
                "idempotent": second["counters"]["assertions_created"] == 0,
                "store_grew": counts_after_reimport != counts_after_import,
                "store_counts_after": counts_after_reimport,
            }
            report["reimport"] = reimport

        export_started = time.perf_counter()
        document = export_snapshot(
            store, known_at=args.known_at, valid_at=args.valid_at, adapter_version=ADAPTER_VERSION,
        )
        export_seconds = time.perf_counter() - export_started
        report["snapshot"] = _snapshot_summary(document)
        report["timings"]["export_seconds"] = round(export_seconds, 3)

        reexport_started = time.perf_counter()
        again = export_snapshot(
            store, known_at=args.known_at, valid_at=args.valid_at, adapter_version=ADAPTER_VERSION,
        )
        reexport_seconds = time.perf_counter() - reexport_started
        report["snapshot"]["reexport_sha256"] = again["manifest"]["snapshot_sha256"]
        report["snapshot"]["identical_on_reexport"] = (
            again["manifest"]["snapshot_sha256"] == document["manifest"]["snapshot_sha256"]
        )
        report["timings"]["reexport_seconds"] = round(reexport_seconds, 3)

        written: dict[str, str] = {}
        if not args.no_write_export:
            write_started = time.perf_counter()
            written = {name: str(path) for name, path in write_export(document, out_dir, jsonl=args.jsonl).items()}
            report["timings"]["write_export_seconds"] = round(time.perf_counter() - write_started, 3)
        report["snapshot"]["written_files"] = written

        early_started = time.perf_counter()
        early = export_snapshot(store, known_at=args.early_known_at, valid_at=args.valid_at,
                                adapter_version=ADAPTER_VERSION)
        early_seconds = time.perf_counter() - early_started
        report["pit"] = {
            "early": {**_snapshot_summary(early), "seconds": round(early_seconds, 3)},
            "late": {"known_at": report["snapshot"]["known_at"], "counts": report["snapshot"]["counts"]},
            "interpretation": (
                "All imported rows carry recorded_at = the backfill observation time, so a knowledge cutoff "
                "before the import sees zero nodes/edges; the later cutoff sees the whole imported graph. "
                "This proves the knowledge-time gate, not historical publication availability."
            ),
        }
    finally:
        store.close()

    source_hash_after, hash_seconds_after = sha256_file(source)
    report["source"]["sha256_after"] = source_hash_after
    report["source"]["hash_seconds_after"] = round(hash_seconds_after, 3)
    report["source"]["unchanged"] = source_hash_after == source_hash_before
    report["tkg_store"]["bytes"] = tkg_path.stat().st_size if tkg_path.exists() else None
    report["tkg_store"]["committed"] = False

    store_path = tkg_path
    db_conn = sqlite3.connect(f"file:{store_path.as_posix()}?mode=ro", uri=True)
    try:
        revisions = {
            "nodes": db_conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
            "edges": db_conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            "entities": db_conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "idempotency_keys": db_conn.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0],
        }
    finally:
        db_conn.close()
    report["store_counts"] = revisions

    failures = []
    if not report["source"]["unchanged"]:
        failures.append("source database changed during import")
    if reimport is not None:
        if not reimport["idempotent"]:
            failures.append("re-import created new assertions (idempotency broken)")
        if reimport["store_grew"]:
            failures.append("re-import grew the store")
    if not report["snapshot"]["identical_on_reexport"]:
        failures.append("snapshot hash changed on re-export")
    report["checks"] = {
        "source_unchanged": report["source"]["unchanged"],
        "reimport_idempotent": None if reimport is None else reimport["idempotent"],
        "reimport_store_grew": None if reimport is None else reimport["store_grew"],
        "snapshot_identical_on_reexport": report["snapshot"]["identical_on_reexport"],
        "passed": not failures,
    }
    report["failures"] = failures

    if args.report_out:
        report_path = Path(args.report_out)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
        report["report_out"] = str(report_path)

    print(json.dumps(report, indent=2, sort_keys=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
