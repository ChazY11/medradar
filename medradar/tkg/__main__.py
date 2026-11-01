"""CLI for the temporal knowledge graph: ``python -m medradar.tkg``.

    python -m medradar.tkg demo     [--out-dir DIR]
    python -m medradar.tkg import   --db SRC.sqlite --tkg TKG.sqlite [--kind K,...] [--limit N]
    python -m medradar.tkg export   --tkg TKG.sqlite --known-at ISO [--valid-at ISO] --out-dir DIR [--jsonl]
    python -m medradar.tkg bench    [--n N] [--out-dir DIR]

Everything runs offline on synthetic or local SQLite data; no network, no API
keys. ``demo`` and ``bench`` are fully synthetic and deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adapter import ADAPTER_VERSION, import_events
from .export import export_snapshot, write_export
from .store import TKGStore


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))


class _step_clock:
    """Deterministic injected clock for the in-memory demo store only."""

    def __init__(self, start: datetime, step: timedelta = timedelta(seconds=10)) -> None:
        self.current = start
        self.step = step

    def __call__(self) -> datetime:
        value = self.current
        self.current += self.step
        return value


def _demo_store() -> tuple[TKGStore, dict[str, str]]:
    """Build a synthetic two-company history illustrating late arrival,
    correction and retraction. Fully synthetic; no real data."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    store = TKGStore(":memory:", clock=_step_clock(start))
    t = lambda d: (start + timedelta(days=d)).strftime("%Y-%m-%d")

    evidence = {
        "source_locator": "synthetic://demo",
        "evidence_kind": "source_observed",
        "confidence": 1.0,
    }

    def node(company: str, stage: str, day: int, key: str, valid_to: str | None = None,
             public_time: str | None = None) -> None:
        store.add_node(
            "company", company, {"stage": stage}, valid_from=t(day), valid_to=valid_to,
            idempotency_key=key, public_time=public_time, public_time_basis="observed" if public_time else None,
            **evidence,
        )

    # Day 0: ACME observed as private (recorded at T0).
    node("ACME", "private", 0, "demo:acme:r1")
    # Day 0: GLOBEX observed as private; its public record appeared *before*
    # we ingested it (public_time < recorded_at is legal source metadata).
    node("GLOBEX", "private", 0, "demo:globex:r1", public_time="2023-12-30T00:00:00Z")
    # Day 5: ACME files to go public (correction: new revision).
    node("ACME", "ipo-filed", 5, "demo:acme:r2")
    # Day 8: GLOBEX report retracted (validity closed by the new revision).
    node("GLOBEX", "private", 0, "demo:globex:r2", valid_to=t(8))
    # Late arrival: SPINE-X clearance valid from day 0, only recorded later.
    node("SPINE-X", "cleared", 0, "demo:spinex:r1")

    store.add_edge(
        "supplies", "company", "ACME", "company", "GLOBEX",
        attrs={"note": "synthetic demo relation"},
        valid_from=t(0), idempotency_key="demo:edge:1", **evidence,
    )

    anchors = {
        "early": (start + timedelta(seconds=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "final": (start + timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return store, anchors


def cmd_demo(args: argparse.Namespace) -> int:
    from ..config import OUT_DIR

    out_dir = Path(args.out_dir) if args.out_dir else Path(OUT_DIR) / "tkg_demo"
    store, anchors = _demo_store()
    t = lambda d: f"2024-01-{1 + d:02d}T00:00:00Z" if d < 31 else None
    summary: dict[str, object] = {
        "synthetic": True,
        "anchors": anchors,
        "exports": {},
        "queries": {},
    }
    # Early view: knowledge at T+15s. Final view: full knowledge (T+120s) with
    # an explicit validity date ten days out - the two cutoffs are independent.
    for label, known_at, valid_at in (
        ("early", anchors["early"], None),
        ("final", anchors["final"], t(10)),
    ):
        document = export_snapshot(store, known_at=known_at, valid_at=valid_at,
                                   adapter_version=ADAPTER_VERSION)
        written = write_export(document, out_dir / label, jsonl=args.jsonl)
        summary["exports"][label] = {
            "snapshot_sha256": document["manifest"]["snapshot_sha256"],
            "counts": document["manifest"]["counts"],
            "files": sorted(str(p) for p in written.values()),
        }
    # Query views at the early cutoff: corrections/retractions must not leak.
    from .query import TKGQuery

    early = TKGQuery(store).snapshot(known_at=anchors["early"])
    summary["queries"]["asof_early_companies"] = {
        n["node_id"]: n["attrs"].get("stage") for n in early["nodes"] if n["node_type"] == "company"
    }
    _emit(summary)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    kinds = [k.strip() for k in (args.kind or "").split(",") if k.strip()] or None
    with TKGStore(args.tkg) as store:
        report = import_events(args.db, store, kinds=kinds, limit=args.limit or None)
        report["tkg_store"] = str(Path(args.tkg).resolve())
        report["tkg_counts"] = {t: store.count(t) for t in ("nodes", "edges", "entities")}
    _emit(report)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with TKGStore(args.tkg) as store:
        document = export_snapshot(
            store, known_at=args.known_at, valid_at=args.valid_at or None,
            adapter_version=ADAPTER_VERSION,
        )
    written = write_export(document, args.out_dir, jsonl=args.jsonl)
    _emit(
        {
            "files": {name: str(path) for name, path in written.items()},
            "snapshot_sha256": document["manifest"]["snapshot_sha256"],
            "counts": document["manifest"]["counts"],
            "known_at": document["manifest"]["known_at"],
            "valid_at": document["manifest"]["valid_at"],
        }
    )
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """Compact reproducibility/performance smoke on **synthetic** data only.

    Results are labelled synthetic; they are not real-data measurements.
    """
    from ..config import OUT_DIR

    out_dir = Path(args.out_dir) if args.out_dir else Path(OUT_DIR) / "tkg_bench"
    n = max(1, int(args.n))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    store = TKGStore(":memory:", clock=_step_clock(start, timedelta(microseconds=1)))
    evidence = {
        "source_locator": "synthetic://bench",
        "evidence_kind": "source_observed",
        "confidence": 1.0,
    }

    t0 = time.perf_counter()
    specs: list[dict[str, object]] = []
    for i in range(n):
        specs.append({
            "record": "node", "node_type": "company", "node_id": f"BENCH-{i:05d}",
            "attrs": {"index": i}, "valid_from": "2024-01-01",
            "idempotency_key": f"bench:node:{i}", **evidence,
        })
        if i:
            specs.append({
                "record": "edge", "edge_type": "bench_link",
                "src_type": "company", "src_id": f"BENCH-{i - 1:05d}",
                "dst_type": "company", "dst_id": f"BENCH-{i:05d}",
                "attrs": {}, "valid_from": "2024-01-01",
                "idempotency_key": f"bench:edge:{i}", **evidence,
            })
    store.apply(specs)
    write_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    document = export_snapshot(store, known_at="2024-01-02T00:00:00Z")
    export_s = time.perf_counter() - t0
    again = export_snapshot(store, known_at="2024-01-02T00:00:00Z")
    reproducible = (
        again["manifest"]["snapshot_sha256"] == document["manifest"]["snapshot_sha256"]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "label": "SYNTHETIC BENCH - not a real-data result",
        "n_nodes": n,
        "n_edges": max(0, n - 1),
        "write_seconds": round(write_s, 4),
        "export_seconds": round(export_s, 4),
        "deterministic_repeat_export": reproducible,
        "snapshot_sha256": document["manifest"]["snapshot_sha256"],
        "python": sys.version.split()[0],
    }
    (out_dir / "bench.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _emit(report)
    return 0 if reproducible else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="medradar.tkg",
        description="Temporal knowledge graph: append-only bitemporal store + deterministic PIT export.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="offline synthetic demo: build history, query, export")
    demo.add_argument("--out-dir", default=None)
    demo.add_argument("--jsonl", action="store_true", help="write JSONL instead of snapshot.json")
    demo.set_defaults(func=cmd_demo)

    imp = sub.add_parser("import", help="import events from a read-only source DB into a TKG store")
    imp.add_argument("--db", required=True, help="source events SQLite (opened mode=ro)")
    imp.add_argument("--tkg", required=True, help="target TKG SQLite store")
    imp.add_argument("--kind", default=None, help="comma separated event kinds to import")
    imp.add_argument("--limit", type=int, default=0, help="max source rows (0 = all)")
    imp.set_defaults(func=cmd_import)

    exp = sub.add_parser("export", help="deterministic point-in-time export")
    exp.add_argument("--tkg", required=True, help="TKG SQLite store")
    exp.add_argument("--known-at", required=True, help="knowledge cutoff (tz-aware ISO)")
    exp.add_argument("--valid-at", default=None, help="optional independent validity cutoff")
    exp.add_argument("--out-dir", required=True)
    exp.add_argument("--jsonl", action="store_true", help="write nodes.jsonl/edges.jsonl/manifest.json")
    exp.set_defaults(func=cmd_export)

    bench = sub.add_parser("bench", help="synthetic reproducibility/performance smoke")
    bench.add_argument("--n", type=int, default=2000, help="synthetic node count")
    bench.add_argument("--out-dir", default=None)
    bench.set_defaults(func=cmd_bench)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
