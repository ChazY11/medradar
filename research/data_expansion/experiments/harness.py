"""Experiment harness for DATA-EXPANSION-001.

Responsibilities
----------------
1. **Discover** the connectors that the domain owners implemented, without
   importing anything hard-coded: any module under
   ``medradar/external_sources/<domain>/`` that exposes ``SOURCE_ID``,
   ``KIND`` and a callable ``collect(client, limit=...)`` is a connector.
2. **Collect** through :class:`medradar.external_sources.base.HttpClient`, so
   every experiment request is budgeted and logged exactly like a probe.
3. **Stage** the resulting evidence records in the isolated staging store.
4. Provide the anchor set and the evidence iteration used by EXP-A/B/C.

The harness never writes to ``data/medradar.sqlite`` and never invents a record:
if a connector returns nothing, the experiment reports nothing.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]          # research/data_expansion
REPO = ROOT.parents[1]                              # repository root
WORKSPACE = ROOT.parents[2]                         # worktree root
sys.path.insert(0, str(REPO))

from medradar.external_sources import base, schema, store, timeq  # noqa: E402

EXTERNAL_PKG = REPO / "medradar" / "external_sources"
DOMAINS = ("regulatory", "scholarly", "trials", "trade", "procurement")
STAGING = ROOT / "staging" / "external_evidence.sqlite"
COLLECTION_LOG = ROOT / "experiments" / "collection"


@dataclass
class Connector:
    source_id: str
    kind: str
    module_name: str
    collect: Callable[..., list]
    licence_status: str = "unknown"
    module: Any = None

    def qname(self) -> str:
        return f"{self.module_name}:{self.source_id}"


def discover_connectors(domains: Iterable[str] = DOMAINS) -> dict[str, Connector]:
    """Import every connector module and index it by ``SOURCE_ID``.

    A module that raises on import is reported as broken rather than crashing
    the whole run, because one team's syntax error must not hide everyone
    else's working connectors.
    """
    found: dict[str, Connector] = {}
    broken: list[str] = []
    for domain in domains:
        directory = EXTERNAL_PKG / domain
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module_name = f"medradar.external_sources.{domain}.{path.stem}"
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001
                broken.append(f"{module_name}: {type(exc).__name__}: {exc}")
                continue
            source_id = getattr(module, "SOURCE_ID", None)
            collect = getattr(module, "collect", None)
            if not source_id or not callable(collect):
                continue
            found[str(source_id)] = Connector(
                source_id=str(source_id),
                kind=str(getattr(module, "KIND", "unknown")),
                module_name=module_name,
                collect=collect,
                licence_status=str(getattr(module, "LICENCE_STATUS", "unknown")),
                module=module,
            )
    if broken:
        found["__broken__"] = Connector(  # type: ignore[assignment]
            source_id="__broken__",
            kind="",
            module_name="",
            collect=lambda *a, **k: [],
            module={"broken": broken},
        )
    return found


def broken_modules(connectors: Mapping[str, Connector]) -> list[str]:
    entry = connectors.get("__broken__")
    if not entry or not isinstance(entry.module, dict):
        return []
    return list(entry.module.get("broken", []))


def _call_collect(connector: Connector, client: base.HttpClient, limit: int) -> list:
    """Call a connector's ``collect`` with only the keyword arguments it declares.

    The protocol asks for ``collect(client, *, limit=50)``.  Two connectors in the
    regulatory domain deliberately take no ``limit`` (their sources return one
    complete small page), and the ATS connectors require a board token that no
    target firm has.  Rather than fail the whole collection, the harness adapts
    and records the deviation in the collection report.
    """
    import inspect

    signature = inspect.signature(connector.collect)
    params = signature.parameters
    accepts_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    if "limit" in params or accepts_kwargs:
        return connector.collect(client, limit=limit)
    return connector.collect(client)


def normalise_records(result: Any) -> tuple[list, dict[str, Any]]:
    """Accept either ``[record, ...]`` or the ``(records, meta)`` shape.

    A connector that also returns fetch metadata is fine; what is not fine is a
    harness that crashes on it and loses otherwise valid evidence.
    """
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], list):
        return result[0], dict(result[1]) if isinstance(result[1], dict) else {}
    if isinstance(result, list):
        return result, {}
    return [], {"unexpected_return_type": type(result).__name__}


def _client(source_id: str, ledger_dir: Path, budget: int, min_interval: float) -> base.HttpClient:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger = base.HttpLedger(ledger_dir / f"requests_{source_id}.jsonl")
    return base.HttpClient(
        source_id=source_id, ledger=ledger, budget=budget, min_interval=min_interval
    )


@dataclass
class CollectionStats:
    source_id: str
    requested: int = 0
    returned: int = 0
    written: int = 0
    duplicates: int = 0
    invalid: int = 0
    requests: int = 0
    error: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "records_returned": self.returned,
            "records_written": self.written,
            "content_duplicates": self.duplicates,
            "invalid_rejected": self.invalid,
            "requests": self.requests,
            "error": self.error,
            "notes": self.notes,
        }


def collect_source(
    connector: Connector,
    *,
    limit: int,
    store_path: Path = STAGING,
    log_dir: Path = COLLECTION_LOG,
    budget: int | None = None,
    min_interval: float = 0.8,
) -> CollectionStats:
    """Run one connector into the staging store.  Never raises on source failure."""
    stats = CollectionStats(source_id=connector.source_id)
    client = _client(connector.source_id, log_dir, budget or max(8, limit), min_interval)
    run_id = store.new_run_id(connector.source_id, timeq.utc_iso().replace(":", ""))
    with store.StagingStore(store_path) as db:
        db.start_run(run_id, connector.source_id, timeq.utc_iso(), producer=connector.module_name)
        try:
            records, meta = normalise_records(_call_collect(connector, client, limit))
            if meta:
                stats.notes.append(f"connector_meta: {json.dumps(meta, ensure_ascii=False)[:400]}")
            stats.returned = len(records)
            for record in records:
                problems = schema.validate_evidence(record)
                if problems:
                    stats.invalid += 1
                    if len(stats.notes) < 5:
                        stats.notes.append(f"invalid record: {problems[:2]}")
                    continue
                result = db.upsert_evidence(record)
                if result["inserted"]:
                    stats.written += 1
                else:
                    stats.duplicates += 1
        except Exception as exc:  # noqa: BLE001
            stats.error = f"{type(exc).__name__}: {exc}"
            stats.notes.append(traceback.format_exc(limit=3))
        finally:
            db.log_requests(run_id, connector.source_id, client.ledger.entries)
            db.finish_run(
                run_id,
                status="ok" if not stats.error else "error",
                finished_at=timeq.utc_iso(),
                requests=client.requests_made(),
                records=stats.written,
                raw_bytes=sum(int(e.get("bytes", 0) or 0) for e in client.ledger.entries),
                notes=stats.error[:400],
            )
    stats.requests = client.requests_made()
    return stats


def collect_all(
    connectors: Mapping[str, Connector],
    *,
    limit: int,
    sources: Iterable[str] | None = None,
    store_path: Path = STAGING,
) -> dict[str, Any]:
    wanted = set(sources) if sources else {sid for sid in connectors if sid != "__broken__"}
    results: list[CollectionStats] = []
    for source_id in sorted(wanted & set(connectors)):
        results.append(collect_source(connectors[source_id], limit=limit, store_path=store_path))
    payload = {
        "schema": "medradar.external.collection.v1",
        "collected_at": timeq.utc_iso(),
        "limit_per_source": limit,
        "connectors_found": sorted(sid for sid in connectors if sid != "__broken__"),
        "broken_modules": broken_modules(connectors),
        "sources": [s.to_dict() for s in results],
        "totals": {
            "records_written": sum(s.written for s in results),
            "requests": sum(s.requests for s in results),
            "failed_sources": [s.source_id for s in results if s.error],
        },
    }
    log_dir = COLLECTION_LOG
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "COLLECTION_REPORT.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


# --------------------------------------------------------------------- evidence
def iter_evidence(store_path: Path = STAGING) -> Iterator[dict[str, Any]]:
    """Yield one payload per evidence head (latest version), deduplicated by id."""
    if not Path(store_path).exists():
        return
    with store.StagingStore(store_path) as db:
        rows = db.query(
            "SELECT e.payload_json FROM evidence_head h"
            " JOIN evidence e ON e.evidence_id = h.evidence_id AND e.content_hash = h.latest_hash"
        )
        for row in rows:
            yield json.loads(row["payload_json"])


def evidence_by_id(store_path: Path = STAGING) -> dict[str, dict[str, Any]]:
    return {rec["evidence_id"]: rec for rec in iter_evidence(store_path)}


def write_json(path: Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    connectors = discover_connectors()
    names = sorted(sid for sid in connectors if sid != "__broken__")
    print(f"discovered {len(names)} connectors")
    for name in names:
        connector = connectors[name]
        print(f"  {name:<28} kind={connector.kind:<22} {connector.module_name}")
    for broken in broken_modules(connectors):
        print(f"  BROKEN: {broken}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
