#!/usr/bin/env python3
"""Structural probe for every evidence/history store candidate in MEDRADAR.

What it does
------------
1. Builds each *main-branch* store through its real Python class in a throw-away
   directory, then reads its physical schema back from SQLite itself
   (``sqlite_master`` + ``PRAGMA``), never from the source text.
2. Builds each *branch-only* store by extracting its DDL constant with ``ast``
   from ``git show <ref>:<path>`` and executing that DDL in an in-memory
   database. Branch code is never imported and never executed.
3. Applies each main-branch module's DDL in isolation and reports index /
   table name collisions between modules that all write into the same
   ``data/medradar.sqlite`` file.
4. Runs a small, explicitly separated set of *behavioural* probes (mutability,
   append-only triggers, timestamp rendering) that show what the structures do,
   not merely how they are declared.

Everything is offline and read-only with respect to the repository: the only
files written are the ``--json-out`` / ``--text-out`` paths you pass.

Usage
-----
    python docs/refoundation/phase0/_evidence/evidence/probe_store_structure.py \
        --json-out docs/refoundation/phase0/_evidence/evidence/store_structure.json \
        --text-out docs/refoundation/phase0/_evidence/evidence/store_structure.txt

Exit codes: 0 success, 2 a store could not be probed (report still written).
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[5]  # .../docs/refoundation/phase0/_evidence/evidence
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# --------------------------------------------------------------------------- time
_TIME_COLUMN = re.compile(
    r"(^|_)(at|date|dates|time|times|window|cutoff|seen|observed|fetched|published|"
    r"recorded|valid|ingested|resolved|verified|generated|applied|checked|started|"
    r"finished|logged|retrieved|matures)(_|$)",
    re.IGNORECASE,
)
_ID_COLUMN = re.compile(
    r"(^|_)(id|key|identifier|scheme|value|hash|sha256|locator|source|ref|type)($|_)",
    re.IGNORECASE,
)


def kind_columns(columns: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Heuristically split columns into time-bearing and identity-bearing."""
    time_cols, id_cols = [], []
    for column in columns:
        name = column["name"]
        if _TIME_COLUMN.search(name):
            time_cols.append(name)
        if _ID_COLUMN.search(name):
            id_cols.append(name)
    return {"time_bearing": time_cols, "identity_bearing": id_cols}


# --------------------------------------------------------------------- introspection
def introspect(conn: sqlite3.Connection) -> dict[str, Any]:
    """Read tables, columns, keys, indexes, triggers and FKs out of a live connection."""
    tables: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for (name,) in rows:
        columns = [
            {
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
                "default": row[4],
                "pk_position": row[5],
            }
            for row in conn.execute(f'PRAGMA table_info("{name}")')
        ]
        fks = [
            {"from": row[3], "table": row[2], "to": row[4]}
            for row in conn.execute(f'PRAGMA foreign_key_list("{name}")')
        ]
        indexes = []
        for index in conn.execute(f'PRAGMA index_list("{name}")').fetchall():
            index_name, unique, origin = index[1], bool(index[2]), index[3]
            index_columns = [
                row[2] for row in conn.execute(f'PRAGMA index_info("{index_name}")')
            ]
            ddl_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
            ).fetchone()
            indexes.append(
                {
                    "name": index_name,
                    "unique": unique,
                    "origin": origin,
                    "columns": index_columns,
                    "ddl": ddl_row[0] if ddl_row and ddl_row[0] else "",
                }
            )
        triggers = [
            {"name": trigger, "ddl": ddl or ""}
            for (trigger, ddl) in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name",
                (name,),
            ).fetchall()
        ]
        tables.append(
            {
                "name": name,
                "columns": columns,
                "primary_key": [c["name"] for c in columns if c["pk_position"]],
                "foreign_keys": fks,
                "indexes": indexes,
                "triggers": triggers,
                **kind_columns(columns),
            }
        )
    standalone_triggers = [
        name
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ).fetchall()
        if not any(name == t["name"] for table in tables for t in table["triggers"])
    ]
    return {
        "table_count": len(tables),
        "index_count": sum(len(t["indexes"]) for t in tables),
        "trigger_count": sum(len(t["triggers"]) for t in tables) + len(standalone_triggers),
        "foreign_key_count": sum(len(t["foreign_keys"]) for t in tables),
        "tables": tables,
        "standalone_triggers": standalone_triggers,
    }


def summarize(structure: dict[str, Any]) -> dict[str, Any]:
    """Small printable projection of :func:`introspect`."""
    return {
        "table_count": structure["table_count"],
        "index_count": structure["index_count"],
        "trigger_count": structure["trigger_count"],
        "foreign_key_count": structure["foreign_key_count"],
        "tables": [
            {
                "name": table["name"],
                "columns": len(table["columns"]),
                "primary_key": table["primary_key"],
                "indexes": [index["name"] for index in table["indexes"]],
                "triggers": [trigger["name"] for trigger in table["triggers"]],
                "foreign_keys": len(table["foreign_keys"]),
                "time_bearing": table["time_bearing"],
                "identity_bearing": table["identity_bearing"],
            }
            for table in structure["tables"]
        ],
    }


def counted(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


# ------------------------------------------------------------------- main stores
def probe_events(tmp: Path) -> dict[str, Any]:
    from medradar.db import DB

    path = tmp / "events.sqlite"
    db = DB(path)
    db.commit()
    db.close()
    conn = sqlite3.connect(str(path))
    try:
        structure = introspect(conn)
    finally:
        conn.close()
    return {
        "store": "events (medradar/db.py)",
        "on_main": True,
        "build": "runtime class medradar.db.DB",
        "file": "data/medradar.sqlite (this probe: temp copy)",
        "file_bytes": path.stat().st_size,
        "schema_structure": structure,
    }


def probe_tkg(tmp: Path) -> dict[str, Any]:
    from medradar.tkg.store import SCHEMA_VERSION, TKGStore

    path = tmp / "tkg.sqlite"
    store = TKGStore(path)
    store.close()
    conn = sqlite3.connect(str(path))
    try:
        structure = introspect(conn)
    finally:
        conn.close()
    return {
        "store": "TKG append-only assertion store (medradar/tkg/store.py)",
        "on_main": True,
        "build": "runtime class medradar.tkg.store.TKGStore",
        "declared_schema_version": SCHEMA_VERSION,
        "schema_structure": structure,
    }


def probe_forecast_registry(tmp: Path) -> dict[str, Any]:
    from medradar.forecast_registry import SCHEMA_VERSION, ForecastRegistry

    path = tmp / "forecast.sqlite"
    registry = ForecastRegistry(path)
    registry.close()
    conn = sqlite3.connect(str(path))
    try:
        structure = introspect(conn)
    finally:
        conn.close()
    return {
        "store": "Forecast registry (medradar/forecast_registry.py)",
        "on_main": True,
        "build": "runtime class medradar.forecast_registry.ForecastRegistry",
        "declared_schema_version": SCHEMA_VERSION,
        "schema_structure": structure,
    }


def probe_intelligence(tmp: Path) -> dict[str, Any]:
    from medradar.intelligence.sources import market_data, patents, publications
    from medradar.intelligence.storage import IntelligenceStore

    path = tmp / "intelligence.sqlite"
    store = IntelligenceStore(path)
    market_data.ensure_schema(store)
    patents.ensure_patent_table(store)
    publications.ensure_publication_table(store)
    store.conn.commit()
    store.close()
    conn = sqlite3.connect(str(path))
    try:
        structure = introspect(conn)
    finally:
        conn.close()
    return {
        "store": "Intelligence store (medradar/intelligence/storage.py + sources/*)",
        "on_main": True,
        "build": "runtime classes IntelligenceStore + ensure_schema/ensure_*_table",
        "assembled_from": [
            "medradar/intelligence/storage.py:SCHEMA",
            "medradar/intelligence/sources/market_data.py:SCHEMA",
            "medradar/intelligence/sources/patents.py:PATENT_DDL",
            "medradar/intelligence/sources/publications.py:PUBLICATION_COUNTS_DDL",
        ],
        "schema_structure": structure,
    }


# ----------------------------------------------------------------- branch stores
BRANCH_DDL = (
    {
        "store": "ATLAS evidence store (medradar/atlas/store.py + db/migrations.py)",
        "on_main": False,
        "ref": "origin/foundation/atlas-001",
        "path": "medradar/atlas/db/migrations.py",
        "constant": "V1_SQL",
        "build": "static DDL constant, executed in :memory: (branch code not imported)",
    },
    {
        "store": "external_sources staging store (medradar/external_sources/store.py)",
        "on_main": False,
        "ref": "origin/research/data-expansion-001",
        "path": "medradar/external_sources/store.py",
        "constant": "DDL",
        "build": "static DDL constant, executed in :memory: (branch code not imported)",
    },
    {
        "store": "Observatory observation ledger (medradar/observatory/ledger.py)",
        "on_main": False,
        "ref": "origin/feat/observatory-reliability-v1",
        "path": "medradar/observatory/ledger.py",
        "constant": "SCHEMA",
        "build": "static DDL constant, executed in :memory: (branch code not imported)",
    },
)


def git_constant(ref: str, path: str, constant: str) -> str:
    """Extract one module-level string constant from a git ref without importing it."""
    shown = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for node in ast.parse(shown).body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if constant in targets:
                value = ast.literal_eval(node.value)
                if not isinstance(value, str):
                    raise TypeError(f"{path}:{constant} is not a string")
                return value
    raise KeyError(f"{path}: no module-level {constant!r}")


def probe_branch(spec: dict[str, Any]) -> dict[str, Any]:
    ddl = git_constant(spec["ref"], spec["path"], spec["constant"])
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ddl)
        structure = introspect(conn)
    finally:
        conn.close()
    return {
        **spec,
        "ddl_bytes": len(ddl.encode("utf-8")),
        "schema_structure": structure,
    }


# ------------------------------------------------------- main-module DDL collision
MAIN_DDL_MODULES = (
    ("medradar.db", "SCHEMA"),
    ("medradar.intelligence.storage", "SCHEMA"),
    ("medradar.intelligence.sources.market_data", "SCHEMA"),
    ("medradar.intelligence.sources.patents", "PATENT_DDL"),
    ("medradar.intelligence.sources.publications", "PUBLICATION_COUNTS_DDL"),
    ("medradar.tkg.store", "SCHEMA"),
    ("medradar.forecast_registry", "SCHEMA"),
)


def probe_main_ddl_collisions() -> dict[str, Any]:
    """Apply each main-branch DDL module alone and find names defined more than once."""
    per_module: dict[str, dict[str, Any]] = {}
    index_owners: dict[str, list[dict[str, str]]] = {}
    table_owners: dict[str, list[str]] = {}
    for module_name, constant in MAIN_DDL_MODULES:
        module = importlib.import_module(module_name)
        ddl = getattr(module, constant)
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(ddl)
            structure = introspect(conn)
        finally:
            conn.close()
        per_module[f"{module_name}:{constant}"] = {
            "tables": [t["name"] for t in structure["tables"]],
            "indexes": [
                {"name": i["name"], "table": t["name"], "columns": i["columns"], "ddl": i["ddl"]}
                for t in structure["tables"]
                for i in t["indexes"]
            ],
            "triggers": [
                trigger["name"] for t in structure["tables"] for trigger in t["triggers"]
            ],
        }
        for table in structure["tables"]:
            for index in table["indexes"]:
                index_owners.setdefault(index["name"], []).append(
                    {
                        "module": f"{module_name}:{constant}",
                        "table": table["name"],
                        "columns": ",".join(index["columns"]),
                        "ddl": index["ddl"],
                    }
                )
        for table in structure["tables"]:
            table_owners.setdefault(table["name"], []).append(f"{module_name}:{constant}")

    def collisions(names: dict[str, list[Any]]) -> dict[str, list[Any]]:
        return {name: owners for name, owners in names.items() if len(owners) > 1}

    duplicate_indexes = collisions(index_owners)
    duplicate_tables = collisions(table_owners)
    contradictory = {
        name: owners
        for name, owners in duplicate_indexes.items()
        if len({owner["ddl"] for owner in owners}) > 1
    }
    return {
        "per_module": per_module,
        "duplicate_index_names": duplicate_indexes,
        "contradictory_index_names": contradictory,
        "duplicate_table_names": duplicate_tables,
    }


# ------------------------------------------------------------- behavioural probes
def behavioural_probes(tmp: Path) -> dict[str, Any]:
    from medradar.db import DB
    from medradar.forecast_registry import ForecastRegistry
    from medradar.tkg.store import TKGStore

    results: dict[str, Any] = {}

    # 1. events: same event_id + different content silently replaces the row.
    path = tmp / "mutability.sqlite"
    db = DB(path)
    first = {
        "event_id": "probe-event-1",
        "source": "probe",
        "kind": "510k",
        "event_date": "2024-01-01",
        "title": "first version",
        "available_at": "2024-01-02T00:00:00",
    }
    db.upsert_events([first])
    second = dict(first, title="second version")
    db.upsert_events([second])
    row = db.query("SELECT title FROM events WHERE event_id = ?", ("probe-event-1",))
    results["events_upsert_same_id"] = {
        "rows_after_two_writes": db.scalar("SELECT COUNT(*) FROM events"),
        "title_after_second_write": row[0]["title"] if row else None,
        "replaced_in_place": bool(row and row[0]["title"] == "second version"),
        "revision_history_table": db.scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE '%revision%'"
        ),
    }
    db.close()

    # 2. TKG: UPDATE / DELETE / INSERT OR REPLACE must be physically rejected.
    path = tmp / "append_only_tkg.sqlite"
    store = TKGStore(path)
    store.add_node("company", "c1", {"name": "x"}, idempotency_key="probe:tkg:1",
                   source_locator="probe://", evidence_kind="source_observed",
                   confidence=1.0, valid_from="2024-01-01")
    tkg_attempts: dict[str, str] = {}
    for label, sql in (
        ("update", "UPDATE nodes SET attrs='{}'"),
        ("delete", "DELETE FROM nodes"),
        ("insert_or_replace", "INSERT OR REPLACE INTO nodes SELECT * FROM nodes"),
    ):
        try:
            store.conn.execute(sql)
            store.conn.commit()
            tkg_attempts[label] = "ACCEPTED (invariant broken)"
        except sqlite3.Error as exc:
            tkg_attempts[label] = f"rejected: {exc}"
    results["tkg_append_only"] = tkg_attempts
    store.close()

    # 3. Forecast registry: UPDATE / DELETE / INSERT OR REPLACE must be rejected.
    path = tmp / "append_only_forecast.sqlite"
    registry = ForecastRegistry(path)
    registry.register(
        {
            "idempotency_key": "probe:forecast:1",
            "record_kind": "forecast",
            "target": {"type": "track", "id": "probe", "attrs": {}},
            "horizon_months": 3,
            "p": 0.5,
            "information_cutoff": "2024-01-01T00:00:00Z",
            "model_version": "probe-model",
            "feature_version": "probe-features",
            "evidence": {
                "source_locator": "probe://forecast",
                "evidence_kind": "inferred",
                "evidence_sha256": "0" * 64,
                "provenance": [
                    {"source_locator": "probe://forecast/source", "evidence_sha256": "1" * 64}
                ],
            },
        }
    )
    forecast_attempts: dict[str, str] = {}
    for label, sql in (
        ("update", "UPDATE forecasts SET p=0.9"),
        ("delete", "DELETE FROM forecasts"),
        ("insert_or_replace", "INSERT OR REPLACE INTO forecasts SELECT * FROM forecasts"),
    ):
        try:
            registry.conn.execute(sql)
            registry.conn.commit()
            forecast_attempts[label] = "ACCEPTED (invariant broken)"
        except sqlite3.Error as exc:
            forecast_attempts[label] = f"rejected: {exc}"
    results["forecast_registry_append_only"] = forecast_attempts
    registry.close()

    # 4. Four timestamp renderers on the same calendar day.
    from medradar import replay, util
    from medradar.tkg.store import normalize_moment

    tkg_moment, tkg_precision = normalize_moment("2024-03-05", "probe")
    replay_moment, replay_quality = replay._resolve_available_at(
        {"available_at": "2024-03-05", "timestamp_quality": "date"}
    )
    # Report the *shape* of the wall-clock renderer, not the current time, so this
    # committed artefact is byte-identical between runs.
    now_sample = util.utc_now_iso()
    results["timestamp_rendering"] = {
        "medradar.util.iso": util.iso("2024-03-05"),
        "medradar.util.iso_moment": util.iso_moment("2024-03-05"),
        "medradar.util.utc_now_iso_shape": {
            "shape": re.sub(r"\d", "d", now_sample),
            "matches_second_precision_utc": bool(
                re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", now_sample)
            ),
        },
        "medradar.tkg.store.normalize_moment": {
            "value": tkg_moment,
            "precision": tkg_precision,
        },
        "medradar.replay._resolve_available_at": {
            "value": replay_moment.isoformat() if replay_moment else None,
            "quality": replay_quality,
        },
        "same_instant": (
            tkg_moment
            == (replay_moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if replay_moment else "")
        ),
    }

    # 5. Legacy events.available_at (naive, with a time component) is rejected by
    #    the only implemented events -> TKG importer.
    legacy_value = util.iso_moment("2024-03-05")  # what db.upsert_events stores for a date-only input
    try:
        normalize_moment(legacy_value, "available_at")
        legacy_verdict = "accepted"
    except Exception as exc:  # noqa: BLE001 - probe reports the exact error class
        legacy_verdict = f"rejected: {type(exc).__name__}: {exc}"
    results["legacy_available_at_to_tkg"] = {
        "stored_by_db_upsert_events": legacy_value,
        "tkg_normalize_moment": legacy_verdict,
    }

    return results


# -------------------------------------------------------------------------- main
def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "probe": "medradar evidence-store structure probe",
        "repo": ".",
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "stores": [],
        "main_ddl_collisions": None,
        "behavioural": None,
        "errors": [],
    }
    with tempfile.TemporaryDirectory(prefix="medradar-probe-") as raw_tmp:
        tmp = Path(raw_tmp)
        temp_probes = (
            ("events", probe_events),
            ("tkg", probe_tkg),
            ("forecast_registry", probe_forecast_registry),
            ("intelligence", probe_intelligence),
        )
        for label, probe in temp_probes:
            try:
                report["stores"].append(probe(tmp / label))
            except Exception as exc:  # noqa: BLE001 - the report keeps going
                report["errors"].append(f"{label}: {type(exc).__name__}: {exc}")

    for spec in BRANCH_DDL:
        try:
            report["stores"].append(probe_branch(spec))
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"{spec['store']}: {type(exc).__name__}: {exc}")

    try:
        report["main_ddl_collisions"] = probe_main_ddl_collisions()
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"ddl_collisions: {type(exc).__name__}: {exc}")

    with tempfile.TemporaryDirectory(prefix="medradar-probe-behaviour-") as raw_tmp:
        try:
            report["behavioural"] = behavioural_probes(Path(raw_tmp))
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"behavioural: {type(exc).__name__}: {exc}")

    return report


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"MedRadar evidence-store structure probe  (python {report['python']}, sqlite {report['sqlite']})")
    lines.append("")
    for store in report["stores"]:
        structure = store["schema_structure"]
        lines.append("=" * 100)
        lines.append(f"{store['store']}")
        lines.append(f"  on_main={store['on_main']}  build={store['build']}")
        if store.get("declared_schema_version"):
            lines.append(f"  declared_schema_version={store['declared_schema_version']!r}")
        lines.append(
            f"  tables={structure['table_count']}  indexes={structure['index_count']}"
            f"  triggers={structure['trigger_count']}  foreign_keys={structure['foreign_key_count']}"
        )
        if store.get("file_bytes") is not None:
            lines.append(f"  file_bytes={store['file_bytes']} (build-dependent)")
        for table in structure["tables"]:
            key = ", ".join(table["primary_key"]) or "(none)"
            lines.append(f"    - {table['name']}  pk=({key})  columns={len(table['columns'])}")
            if table["indexes"]:
                lines.append(
                    "        indexes: "
                    + "; ".join(
                        f"{i['name']}({','.join(i['columns'])})" for i in table["indexes"]
                    )
                )
            if table["triggers"]:
                lines.append("        triggers: " + ", ".join(t["name"] for t in table["triggers"]))
            lines.append("        time: " + (", ".join(table["time_bearing"]) or "(none)"))
    collisions = report.get("main_ddl_collisions") or {}
    lines.append("")
    lines.append("=" * 100)
    lines.append("Main-branch DDL name collisions (all modules write data/medradar.sqlite)")
    lines.append(f"  duplicate_table_names={sorted(collisions.get('duplicate_table_names', {}))}")
    lines.append(f"  duplicate_index_names={sorted(collisions.get('duplicate_index_names', {}))}")
    for name, owners in sorted((collisions.get("contradictory_index_names") or {}).items()):
        lines.append(f"  CONTRADICTORY {name}:")
        for owner in owners:
            lines.append(f"    - {owner['module']}  ddl={owner['ddl']}")
    lines.append("")
    lines.append("=" * 100)
    lines.append("Behavioural probes")
    behavioural = report.get("behavioural") or {}
    for key, value in behavioural.items():
        lines.append(f"  {key}:")
        for inner_key, inner_value in value.items():
            lines.append(f"    {inner_key} = {inner_value}")
    if report["errors"]:
        lines.append("")
        lines.append("ERRORS")
        for error in report["errors"]:
            lines.append(f"  {error}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--text-out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_report()
    text = render_text(report)
    sys.stdout.write(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.text_out:
        args.text_out.parent.mkdir(parents=True, exist_ok=True)
        args.text_out.write_text(text, encoding="utf-8", newline="\n")
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
