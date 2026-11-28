"""Break each materialised table in turn and record what the reader-facing path does with it.

Audit 14 ran this by hand: a copy of the store, one column renamed, every page loaded. It found two pages that
lost most of their content and explained it with a false sentence. This tool is that experiment, repeatable, on a
synthetic store small enough to run in seconds.

For each table it builds a good store, checks the path answers, then renames a column and checks the path again.
The verdict per path is one of:

    honest     the failure reaches the page as a gap code or a state flag
    silent     the path returns the same "empty" answer a healthy-but-empty store would give
    crash      the path raises (fine only where the caller is documented to catch it)

Usage::

    python3 tools/store_probe.py            # prints the table
    python3 tools/store_probe.py --json     # machine-readable

The synthetic store is deliberately minimal: this measures the *shape* of a failure, not the data.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _build_store(path: Path) -> None:
    """The smallest store the probes need: one field, one code, one paper, one leader row."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE store_stats (key TEXT, value TEXT, updated_at TEXT);
        CREATE TABLE specialty_stats (specialty TEXT, codes INT, devices INT, companies INT,
                                      top_companies TEXT, updated_at TEXT);
        CREATE TABLE field_trend (specialty TEXT, term TEXT, recent INT, baseline INT, lift REAL,
                                  computed_at TEXT, recent_total INT, baseline_total INT);
        CREATE TABLE paper_field (paper_id TEXT, specialty TEXT, added_at TEXT);
        CREATE TABLE code_leader (code TEXT, rank INT, company_name TEXT, devices INT,
                                  computed_at TEXT);
        CREATE TABLE paper_meta (paper_id TEXT, title TEXT, journal TEXT, published_at TEXT);
        CREATE TABLE product_code_class (product_code TEXT, device_name TEXT, medical_specialty TEXT,
                                         regulation_number TEXT, device_class TEXT, fetched_at TEXT);
        CREATE TABLE udi_device (device_key TEXT, di TEXT, brand_name TEXT, company_name TEXT,
                                 labeler_duns TEXT, version_or_model TEXT, catalog_number TEXT,
                                 product_codes TEXT, gmdn_name TEXT, publish_date TEXT);
        CREATE TABLE udi_premarket (device_key TEXT, submission_number TEXT);
        """
    )
    conn.executemany("INSERT INTO store_stats VALUES (?,?,?)",
                     [("devices", "1", "2026-11-28T09:00:00")])
    conn.execute("INSERT INTO specialty_stats VALUES ('Dental',1,10,2,'ACME',"
                 "'2026-11-28T09:00:00')")
    conn.execute("INSERT INTO field_trend VALUES ('Dental','gingival',17,1,14.5,'2026-11-28',62,53)")
    conn.execute("INSERT INTO paper_field VALUES ('PMC1','Dental','2026-11-28')")
    conn.execute("INSERT INTO paper_meta VALUES ('PMC1','t','j','2026-11-27')")
    conn.execute("INSERT INTO code_leader VALUES ('DZE',1,'Acme',26,'2026-11-28')")
    conn.execute("INSERT INTO product_code_class VALUES ('DZE','n','Dental','r','2','x')")
    conn.execute("INSERT INTO udi_device VALUES ('k1','d1','b','Acme','l','m','c','[\"DZE\"]',"
                 "'g','2026-01-01')")
    conn.execute("INSERT INTO udi_premarket VALUES ('k1','K1')")
    conn.commit()
    conn.close()


class _Store:
    """The two attributes the reader-facing helpers use."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(path, timeout=30)


def _paths() -> dict[str, Callable[[Any], Any]]:
    """The reader-facing derivations, each returning something a page could print."""
    from medradar.radar.code_leaders import leaders_for
    from medradar.radar.paper_passes import field_trends, recent_publications
    from medradar.radar.specialty import read as read_specialties

    return {
        "areas:sizes": lambda store: read_specialties(store),
        "areas:trends": lambda store: field_trends(store),
        "areas:trends(page)": lambda store: _trends_as_the_page_does(store, field_trends),
        "device:peers": lambda store: leaders_for(store, ["DZE"]),
        # What the device page actually does: read, then ask the table its state when the answer is empty.
        # Kept separate from the raw read so the difference is visible rather than assumed.
        "device:peers(page)": lambda store: _peers_as_the_page_does(store, leaders_for),
        "radar:recent": lambda store: recent_publications(store, days=14, today="2026-11-28"),
    }


#: table -> the column the tool renames to simulate a schema that moved.
BREAKAGES: dict[str, tuple[str, str]] = {
    "specialty_stats": ("top_companies", "top_companies_moved"),
    "field_trend": ("recent_total", "recent_total_moved"),
    "code_leader": ("company_name", "company_name_moved"),
    "paper_field": ("added_at", "added_at_moved"),
}

#: Which path reads which table, so a breakage is only judged against the paths that use it.
READERS: dict[str, tuple[str, ...]] = {
    "specialty_stats": ("areas:sizes",),
    "field_trend": ("areas:trends", "areas:trends(page)"),
    "code_leader": ("device:peers", "device:peers(page)"),
    "paper_field": ("radar:recent",),
}


def _trends_as_the_page_does(store: Any, field_trends: Any) -> dict[str, Any]:
    """The /areas assembly: rows, plus the table's state when the rows came back empty (round 130)."""
    from medradar.radar.paper_passes import field_trends_status

    rows = field_trends(store)
    if rows:
        return dict(rows)
    state = field_trends_status(store)
    if state.get("present") and not state.get("readable"):
        return {"gap": str(state.get("error") or "field_trend_unreadable")}
    return {}


def _peers_as_the_page_does(store: Any, leaders_for: Any) -> dict[str, Any]:
    """The device page's assembly: peers, plus a gap when the table exists but cannot be read."""
    from medradar.radar.code_leaders import status

    peers = leaders_for(store, ["DZE"])
    if peers:
        return dict(peers)
    state = status(store)
    if state.get("present") and not state.get("readable"):
        return {"gap": str(state.get("error") or "code_leader_unreadable")}
    return {}


def _looks_empty(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("available") is False or value.get("present") is False:
            return True
        return not value
    return not value


def _mentions_gap(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("gap") or value.get("lookup_gap") or value.get("available") is False:
            return True
    return False


def probe() -> list[dict[str, Any]]:
    paths = _paths()
    out: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        good_path = Path(tmp) / "good.db"
        _build_store(good_path)
        good: dict[str, Any] = {}
        for name, fn in paths.items():
            store = _Store(good_path)
            try:
                good[name] = fn(store)
            except Exception as error:  # noqa: BLE001 - recorded as the healthy answer
                good[name] = f"raised:{type(error).__name__}"
            finally:
                store.conn.close()

        for index, (table, (column, renamed)) in enumerate(BREAKAGES.items()):
            broken_path = Path(tmp) / f"broken{index}.db"
            _build_store(broken_path)
            conn = sqlite3.connect(broken_path)
            conn.execute(f"ALTER TABLE {table} RENAME COLUMN {column} TO {renamed}")
            conn.commit()
            conn.close()
            for name in READERS.get(table, ()):
                fn = paths[name]
                store = _Store(broken_path)
                try:
                    value = fn(store)
                    raised = ""
                except Exception as error:  # noqa: BLE001 - a crash is a verdict, not a stop
                    value, raised = None, type(error).__name__
                finally:
                    store.conn.close()
                if raised:
                    verdict = "crash"
                elif _mentions_gap(value):
                    verdict = "honest"
                elif _looks_empty(value) and _looks_empty(good.get(name)):
                    verdict = "honest"          # it was empty before the breakage too
                elif _looks_empty(value):
                    verdict = "silent"          # content vanished with no explanation
                else:
                    verdict = "honest"
                out.append({"table": table, "path": name, "verdict": verdict,
                            "error": raised,
                            "before": _describe(good.get(name)),
                            "after": _describe(value)})
    return out


def _describe(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, dict):
        return f"dict[{len(value)}]"
    if isinstance(value, list):
        return f"list[{len(value)}]"
    return type(value).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    rows = probe()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"{'table':18} {'path':16} {'verdict':8} {'before':10} {'after':10} reason")
        for row in rows:
            print(f"{row['table']:18} {row['path']:16} {row['verdict']:8} "
                  f"{row['before']:10} {row['after']:10} {row['error']}")
    silent = [row for row in rows if row["verdict"] == "silent"]
    print(f"\n{silent.__len__()} silent of {len(rows)}", file=sys.stderr)
    return 1 if silent else 0


if __name__ == "__main__":
    raise SystemExit(main())
