"""Command line for the internal identity-review workspace.

Two supported operating modes (both keep writes off the public API):

    python -m medradar.product.review serve --port 8788        # loopback admin UI + API
    python -m medradar.product.review decide --applicant "..." --org medtronic ...

The offline mode (decide/revoke/export/import) exists for reviewers who work from a terminal or
who must review without a browser; it appends to the same ledger, so both paths are auditable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..dataset import PRODUCT_VERSION, load_dataset
from .admin import create_admin_app, load_or_create_token, token_path
from .service import attribution_impact, build_case, build_queue, queue_summary
from .store import ReviewError, ReviewStore

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _store(args: argparse.Namespace) -> ReviewStore:
    return ReviewStore(Path(args.review_db) if getattr(args, "review_db", None) else None)


def _dataset(args: argparse.Namespace, store: ReviewStore):
    from ..api import DatasetHolder

    holder = DatasetHolder(Path(args.data_dir) if getattr(args, "data_dir", None) else None)
    holder.fingerprint_fn = store.fingerprint
    holder.review_db = store.path
    return holder.get()


def _evidence(raw: list[str] | None) -> list[dict[str, Any]]:
    items = []
    for value in raw or []:
        try:
            items.append(json.loads(value))
        except json.JSONDecodeError as error:
            raise SystemExit("evidence must be JSON: " + str(error))
    return items


def cmd_serve(args: argparse.Namespace) -> int:
    if args.host not in LOOPBACK and not args.allow_remote:
        print(
            "refusing to bind the identity-review service to " + args.host + ": it is loopback-only. "
            "Pass --allow-remote only if you have put it behind your own authentication boundary.",
            file=sys.stderr,
        )
        return 2
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn", file=sys.stderr)
        return 2
    token = load_or_create_token()
    app = create_admin_app(
        data_dir=args.data_dir,
        web_dir=args.web_dir,
        review_db=args.review_db,
        token=token,
    )
    url = "http://" + args.host + ":" + str(args.port)
    print("MedRadar identity review: " + url + "/review")
    print("Review token file: " + str(token_path()))
    print("Send the token as header X-MedRadar-Review-Token; the browser asks for it once.")
    if args.open:
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(url + "/review")).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_token(args: argparse.Namespace) -> int:
    value = load_or_create_token()
    if args.show:
        print(value)
    else:
        print(str(token_path()))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    store = _store(args)
    dataset = _dataset(args, store)
    payload = build_queue(
        dataset,
        store,
        status=args.status,
        organization=args.org,
        risk=args.risk,
        query=args.query,
        sort=args.sort,
        page=args.page,
        page_size=args.page_size,
        include_verified=args.include_verified,
    )
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    return 0


def cmd_case(args: argparse.Namespace) -> int:
    store = _store(args)
    dataset = _dataset(args, store)
    print(json.dumps(build_case(dataset, store, args.applicant), indent=1, ensure_ascii=False))
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        decision = store.append(
            applicant_name=args.applicant,
            action=args.action,
            status=args.status,
            organization_key=args.org,
            reviewer=args.reviewer,
            reviewer_kind=args.reviewer_kind,
            basis=args.basis,
            evidence_type=args.evidence_type,
            evidence=_evidence(args.evidence),
            note=args.note,
            source="cli",
        )
    except ReviewError as error:
        print("rejected: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(decision.to_public(), indent=1, ensure_ascii=False))
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        decision = store.append(
            applicant_name=args.applicant,
            action="revoke",
            status="unresolved",
            organization_key=None,
            reviewer=args.reviewer,
            reviewer_kind=args.reviewer_kind,
            note=args.note or "revoked from the CLI",
            supersedes_uid=args.uid,
            source="cli",
        )
    except ReviewError as error:
        print("rejected: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(decision.to_public(), indent=1, ensure_ascii=False))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = _store(args)
    dataset = _dataset(args, store)
    payload = queue_summary(dataset, store)
    payload["metrics"] = dataset.metrics_summary()
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    return 0


def cmd_impact(args: argparse.Namespace) -> int:
    store = _store(args)
    current = _dataset(args, store)
    from ..api import DatasetHolder

    baseline_holder = DatasetHolder(Path(args.data_dir) if args.data_dir else None)
    baseline_holder.review_db = Path(args.review_db) if args.review_db else Path("/nonexistent/review.db")
    baseline = baseline_holder.get()
    print(json.dumps(attribution_impact(baseline, current), indent=1, ensure_ascii=False))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = _store(args)
    payload = {
        "schema": "medradar.review_export.v1",
        "product_version": PRODUCT_VERSION,
        "decisions": [item.to_public() for item in store.all_decisions()],
    }
    path = Path(args.out) if args.out else None
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print("wrote " + str(path) + " (" + str(len(payload["decisions"])) + " decision(s))")
    else:
        print(text)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    store = _store(args)
    document = json.loads(Path(args.file).read_text(encoding="utf-8"))
    decisions = document.get("decisions") if isinstance(document, dict) else document
    if not isinstance(decisions, list):
        print("expected a decisions list", file=sys.stderr)
        return 2
    imported = 0
    errors = []
    for item in decisions:
        if not isinstance(item, dict) or item.get("action") == "revoke":
            continue
        try:
            store.append(
                applicant_name=str(item.get("applicant_name") or ""),
                action=str(item.get("action") or "approve"),
                status=str(item.get("status") or "evidence_verified"),
                organization_key=item.get("organization_key"),
                reviewer=str(item.get("reviewer") or ""),
                reviewer_kind=str(item.get("reviewer_kind") or "human"),
                basis=item.get("basis"),
                evidence=item.get("evidence"),
                note=item.get("note"),
                source="cli_import",
            )
            imported += 1
        except ReviewError as error:
            errors.append({"applicant_name": item.get("applicant_name"), "error": str(error)})
    print(json.dumps({"imported": imported, "errors": errors}, indent=1, ensure_ascii=False))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m medradar.product.review",
        description="MedRadar internal identity-review workspace (loopback only).",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=None, help="product snapshot directory")
    common.add_argument("--review-db", default=None, help="review ledger path (default: data/identity/review.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", parents=[common], help="run the loopback admin UI and API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8788)
    serve.add_argument("--web-dir", default=None)
    serve.add_argument("--open", action="store_true")
    serve.add_argument("--allow-remote", action="store_true")
    serve.set_defaults(func=cmd_serve)

    token = sub.add_parser("token", help="print the review token path (or value with --show)")
    token.add_argument("--show", action="store_true")
    token.set_defaults(func=cmd_token)

    queue = sub.add_parser("queue", parents=[common], help="print the review queue")
    queue.add_argument("--status", default=None)
    queue.add_argument("--org", default=None)
    queue.add_argument("--risk", default=None)
    queue.add_argument("--query", default=None)
    queue.add_argument("--sort", default="records_desc")
    queue.add_argument("--page", type=int, default=1)
    queue.add_argument("--page-size", type=int, default=25)
    queue.add_argument("--include-verified", action="store_true")
    queue.set_defaults(func=cmd_queue)

    case = sub.add_parser("case", parents=[common], help="print one review case with its evidence")
    case.add_argument("--applicant", required=True)
    case.set_defaults(func=cmd_case)

    decide = sub.add_parser("decide", parents=[common], help="append a review decision")
    decide.add_argument("--applicant", required=True)
    decide.add_argument("--action", required=True, choices=["approve", "reassign", "reject", "unresolved"])
    decide.add_argument("--status", required=True)
    decide.add_argument("--org", default=None)
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--reviewer-kind", default="human", choices=["human", "agent"])
    decide.add_argument("--basis", default=None)
    decide.add_argument("--evidence-type", default=None)
    decide.add_argument("--evidence", action="append", default=None, help="JSON evidence reference (repeatable)")
    decide.add_argument("--note", default=None)
    decide.set_defaults(func=cmd_decide)

    revoke = sub.add_parser("revoke", parents=[common], help="withdraw a decision (append-only)")
    revoke.add_argument("--uid", required=True)
    revoke.add_argument("--applicant", required=True)
    revoke.add_argument("--reviewer", required=True)
    revoke.add_argument("--reviewer-kind", default="human", choices=["human", "agent"])
    revoke.add_argument("--note", default=None)
    revoke.set_defaults(func=cmd_revoke)

    stats = sub.add_parser("stats", parents=[common], help="queue and ledger statistics")
    stats.set_defaults(func=cmd_stats)

    impact = sub.add_parser("impact", parents=[common], help="which organizations changed after review")
    impact.set_defaults(func=cmd_impact)

    export = sub.add_parser("export", parents=[common], help="export decisions as JSON")
    export.add_argument("--out", default=None)
    export.set_defaults(func=cmd_export)

    import_cmd = sub.add_parser("import", parents=[common], help="import an offline review file")
    import_cmd.add_argument("file")
    import_cmd.set_defaults(func=cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    destination = getattr(args, "data_dir", None)
    if destination and not Path(destination).is_dir():
        print("data dir not found: " + destination, file=sys.stderr)
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
