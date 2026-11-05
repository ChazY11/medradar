#!/usr/bin/env python
"""Run the Observatory backup/restore drill end-to-end and print its report.

The drill is implemented in ``medradar.observatory.restore.run_restore_drill``:
it takes a consistent backup of the ledger, verifies the bundle hashes, restores
the bundle into an isolated temporary directory, verifies the restored content
against the manifest, then writes one synthetic observation into the restored
copy to prove that ``first_seen_at`` continuity survives a restore.

The production ledger is only *read*; the drill writes its artifacts under
``--work-dir`` plus the operational ``runtime_state["last_restore_drill"]``
record (and the backup step's ``runtime_state["last_backup"]`` record) in the
real ledger — that is the intended operational journal.

Exit code: 0 when the drill status is OK, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the checkout importable when run as `python scripts/observatory_backup_drill.py`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.observatory.ledger import default_ledger_path  # noqa: E402
from medradar.observatory.restore import run_restore_drill  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="observatory_backup_drill",
        description=(
            "Backup -> hash-verify -> isolated restore -> verify -> continuity drill "
            "for the MedRadar observation ledger."
        ),
    )
    parser.add_argument(
        "--ledger",
        default=None,
        help="observation ledger path (default: MEDRADAR_OBSERVATORY_DB or data/observatory/observatory.sqlite)",
    )
    parser.add_argument(
        "--work-dir",
        default="out/reliability_drill",
        help="directory for the drill's isolated backups/restores (default: out/reliability_drill)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the full machine-readable report as JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ledger = Path(args.ledger).expanduser() if args.ledger else default_ledger_path()
    work_dir = Path(args.work_dir).expanduser()
    report = run_restore_drill(ledger_path=ledger, work_dir=work_dir)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(f"restore drill: {report.get('status')}  ok={report.get('ok')}")
        print(f"  ledger      : {report.get('ledger')}")
        print(f"  bundle      : {report.get('bundle_path')}")
        print(f"  restored    : {report.get('restored_ledger')}")
        print(f"  first_seen_max: {report.get('first_seen_max')}")
        print(f"  counts      : {report.get('counts')}")
        print(f"  duration_ms : {report.get('duration_ms')}")
        if report.get("error"):
            print(f"  error       : {report['error']}")
        for item in report.get("checks") or []:
            flag = "ok" if item.get("ok") else "FAIL"
            print(f"  [{flag}] {item.get('id')}: {item.get('detail')}")
        if report.get("runtime_state_error"):
            print(f"  runtime_state note error: {report['runtime_state_error']}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
