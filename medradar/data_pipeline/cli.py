"""Command line entry point for operators and systemd.

Examples:

    python -m medradar.data_pipeline bootstrap --from medradar/product/snapshot --root data/data_pipeline
    python -m medradar.data_pipeline check --due --json
    python -m medradar.data_pipeline run --json
    python -m medradar.data_pipeline status --json
    python -m medradar.data_pipeline rollback fda-snapshot-... --actor operator
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .backup import BackupError, backup, restore
from .config import Settings
from .pipeline import Pipeline, PipelineError
from .status_service import changes_feed, data_status

COMMANDS = ("bootstrap", "check", "run", "sync", "status", "changes", "rollback", "prune", "backup", "restore")


def _split_sources(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _pipeline(args: argparse.Namespace) -> Pipeline:
    settings = Settings.from_env(args.root)
    if args.review_db:
        settings.review_db = Path(args.review_db)
    return Pipeline(settings)


def _command_bootstrap(args: argparse.Namespace) -> int:
    result = _pipeline(args).bootstrap(args.source, actor=args.actor)
    if args.json:
        _print_json(result)
    else:
        print("bootstrapped " + str(result["snapshot_id"]))
        print("path: " + result["path"])
    return 0


def _command_check(args: argparse.Namespace) -> int:
    result = _pipeline(args).check(sources=_split_sources(args.sources), due_only=args.due)
    if args.json:
        _print_json(result)
    else:
        for row in result["results"]:
            print(
                row.get("source_id"),
                row.get("status"),
                "official=" + str(row.get("official_last_updated")),
                "total=" + str(row.get("official_total")),
                "|",
                row.get("message"),
            )
    return 0


def _command_sync(args: argparse.Namespace) -> int:
    result = _pipeline(args).sync(
        sources=_split_sources(args.sources),
        force=args.force,
        allow_record_drop=args.allow_record_drop,
        allow_degraded=args.allow_degraded,
        dry_run=args.dry_run,
        actor=args.actor,
    )
    if args.json:
        _print_json(result)
    else:
        print(result.get("status"), "snapshot=" + str(result.get("active_snapshot_id") or result.get("candidate_snapshot_id")))
        if result.get("counts"):
            print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in ("SUCCEEDED", "PARTIAL", "NO_CHANGE", "DRY_RUN_VALIDATED") else 1


def _command_run(args: argparse.Namespace) -> int:
    result = _pipeline(args).run(
        force=args.force,
        allow_record_drop=args.allow_record_drop,
        allow_degraded=args.allow_degraded,
        actor=args.actor,
    )
    if args.json:
        _print_json(result)
    else:
        print(result.get("status"))
        sync = result.get("sync")
        if sync:
            print("snapshot=" + str(sync.get("active_snapshot_id") or sync.get("candidate_snapshot_id")))
            if sync.get("counts"):
                print(json.dumps(sync["counts"], ensure_ascii=False, sort_keys=True))
        else:
            for row in result.get("checks") or []:
                print(row.get("source_id"), row.get("status"))
    return 0 if result.get("status") in ("SUCCEEDED", "PARTIAL", "NO_CHANGE") else 1


def _command_status(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    payload = pipeline.status()
    payload["public"] = data_status(data_dir=args.data_dir, pipeline_db=pipeline.settings.state_db if Path(pipeline.settings.state_db).is_file() else None)
    if args.json:
        _print_json(payload)
    else:
        active = payload.get("active") or {}
        print("pipeline: " + str(pipeline.settings.root))
        print("active snapshot: " + str(active.get("snapshot_id")))
        for row in payload.get("sources") or []:
            print(
                row.get("source_id"),
                row.get("last_check_status"),
                "official=" + str(row.get("official_last_updated")),
                "update=" + ("yes" if row.get("update_available") else "no"),
                "failures=" + str(row.get("consecutive_failures")),
            )
    return 0


def _command_changes(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    payload = changes_feed(
        source_id=args.source,
        change_type=args.change_type,
        organization_key=args.org,
        limit=args.limit,
        offset=args.offset,
        pipeline_db=pipeline.settings.state_db,
        data_dir=args.data_dir,
    )
    if args.json:
        _print_json(payload)
    else:
        for row in payload.get("items") or []:
            print(row.get("detected_at"), row.get("source_id"), row.get("change_type"), row.get("official_record_id"))
        print("total=" + str(payload.get("total")))
    return 0


def _command_rollback(args: argparse.Namespace) -> int:
    result = _pipeline(args).rollback(args.snapshot_id, actor=args.actor)
    if args.json:
        _print_json(result)
    else:
        print("rollback active snapshot=" + result["snapshot_id"])
    return 0


def _command_prune(args: argparse.Namespace) -> int:
    result = _pipeline(args).prune(args.keep)
    if args.json:
        _print_json(result)
    else:
        print("removed: " + (", ".join(result["removed"]) or "none"))
    return 0


def _command_backup(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args)
    result = backup(
        pipeline.settings, args.destination,
        review_db=args.review_db or pipeline.settings.review_db,
        include_all_snapshots=not args.active_only,
    )
    if args.json:
        _print_json(result)
    else:
        print("backup: " + result["backup"])
    return 0


def _command_restore(args: argparse.Namespace) -> int:
    result = restore(
        args.archive, args.destination,
        review_db_destination=args.review_db_destination,
    )
    if args.json:
        _print_json(result)
    else:
        print("restored: " + result["active_snapshot_id"] + " -> " + result["restored_to"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medradar.data_pipeline", description="MedRadar continuous FDA data pipeline")
    parser.add_argument("--root", default=None, help="pipeline state root (default: MEDRADAR_PIPELINE_ROOT or data/data_pipeline)")
    parser.add_argument("--review-db", default=None, help="identity review SQLite path; read-only during validation")
    parser.add_argument("--data-dir", default=None, help="active product data root for read-only status commands")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="adopt a legacy immutable snapshot as the initial baseline")
    bootstrap.add_argument("--from", dest="source", required=True, help="legacy snapshot directory")
    bootstrap.add_argument("--actor", default="bootstrap")
    bootstrap.set_defaults(func=_command_bootstrap)

    check = sub.add_parser("check", help="probe official source versions without collecting records")
    check.add_argument("--sources", default=None, help="comma-separated source ids (default: all)")
    check.add_argument("--due", action="store_true", help="skip sources whose per-source interval is not due")
    check.set_defaults(func=_command_check)

    run = sub.add_parser("run", help="run due checks and synchronise any available update")
    run.add_argument("--force", action="store_true", help="reconcile even if the detector says no change")
    run.add_argument("--allow-record-drop", action="store_true", help="explicitly allow a validated record-count drop")
    run.add_argument("--allow-degraded", action="store_true", help="manual override for degraded source checks")
    run.add_argument("--actor", default="systemd")
    run.set_defaults(func=_command_run)

    sync = sub.add_parser("sync", help="check then collect, validate and publish")
    sync.add_argument("--sources", default=None, help="comma-separated source ids (default: all)")
    sync.add_argument("--force", action="store_true")
    sync.add_argument("--allow-record-drop", action="store_true")
    sync.add_argument("--allow-degraded", action="store_true")
    sync.add_argument("--dry-run", action="store_true", help="build and validate a candidate without publishing")
    sync.add_argument("--actor", default="operator")
    sync.set_defaults(func=_command_sync)

    status = sub.add_parser("status", help="show source state and active snapshot")
    status.set_defaults(func=_command_status)

    changes = sub.add_parser("changes", help="read the published change ledger")
    changes.add_argument("--source", default=None)
    changes.add_argument("--type", dest="change_type", default=None)
    changes.add_argument("--org", default=None)
    changes.add_argument("--limit", type=int, default=50)
    changes.add_argument("--offset", type=int, default=0)
    changes.set_defaults(func=_command_changes)

    rollback = sub.add_parser("rollback", help="atomically switch back to a validated prior snapshot")
    rollback.add_argument("snapshot_id")
    rollback.add_argument("--actor", default="operator")
    rollback.set_defaults(func=_command_rollback)

    prune = sub.add_parser("prune", help="remove old full snapshots while retaining the change ledger")
    prune.add_argument("--keep", type=int, default=None)
    prune.set_defaults(func=_command_prune)

    backup_parser = sub.add_parser("backup", help="create a consistent same-host state backup")
    backup_parser.add_argument("--destination", required=True, help="backup directory")
    backup_parser.add_argument("--review-db", default=None)
    backup_parser.add_argument("--active-only", action="store_true", help="copy only the active snapshot")
    backup_parser.set_defaults(func=_command_backup)

    restore_parser = sub.add_parser("restore", help="restore a backup into an empty isolated directory")
    restore_parser.add_argument("--archive", required=True, help="backup directory")
    restore_parser.add_argument("--destination", required=True, help="empty directory to restore into")
    restore_parser.add_argument("--review-db-destination", default=None)
    restore_parser.set_defaults(func=_command_restore)
    # Accept --json on either side of the subcommand for systemd/operator ergonomics.
    for command_parser in (bootstrap, check, run, sync, status, changes, rollback, prune, backup_parser, restore_parser):
        command_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (PipelineError, BackupError, ValueError, FileNotFoundError) as error:
        if args.json:
            _print_json({"status": "ERROR", "error": str(error)})
        else:
            print("error: " + str(error), file=sys.stderr)
        return 2
