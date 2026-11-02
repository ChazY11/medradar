"""Harness validation: does the parametric panel builder reproduce cycle 1?

If this fails, cycle-2 results are meaningless (the comparison would confound a
builder difference with the entity-universe change). Run:

    python experiments/cycle2_coverage/selfcheck_p1.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.features.research_features import (  # noqa: E402
    build_entry_examples,
)
from experiments.cycle2_coverage.panel import (  # noqa: E402
    P1_DATASET_VERSION,
    build_entry_panel,
    load_regulatory_events,
    self_check_p1,
    write_json,
)


class _Store:
    """Minimal store shim: the frozen builder only needs ``.conn``."""

    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/cycle2_coverage/selfcheck_p1.json")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    events = load_regulatory_events(db_path)
    print(f"loaded {len(events)} material regulatory events")

    panel = build_entry_panel(
        events, entity_field="company_key", dataset_version=P1_DATASET_VERSION,
        coverage_end_reference="2026-10-15")
    print(f"P1 panel: {panel['n_examples']} examples, {panel['n_positives']} positives, "
          f"{len(panel['cutoffs'])} origins")

    store = _Store(db_path)
    try:
        frozen = build_entry_examples(store)
    finally:
        store.close()
    print(f"frozen  : {len(frozen['examples'])} examples, "
          f"{sum(int(r['label']) for r in frozen['examples'])} positives, "
          f"{len(frozen['cutoffs'])} origins")

    result = self_check_p1(panel, frozen)
    write_json(Path(args.out), result)
    for entry in result["checks"]:
        status = "PASS" if entry["ok"] else "FAIL"
        print(f"  [{status}] {entry['check']}: expected={entry['expected']} "
              f"observed={entry['observed']}")
    if result["mismatch_sample"]:
        print("  sample mismatches:", json.dumps(result["mismatch_sample"], indent=2)[:1200])
    print("OVERALL:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
