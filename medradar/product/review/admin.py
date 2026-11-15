"""Loopback-only internal admin service for identity review.

Security boundary (do not weaken)
--------------------------------
Identity review writes change what the product counts. They are therefore reachable ONLY from this
admin application, which:

* refuses to bind to a non-loopback host unless the operator explicitly passes --allow-remote;
* rejects any request whose client address is not loopback (defence in depth against a reverse
  proxy or port-forward misconfiguration);
* requires a shared token on every /api/review/* request (X-MedRadar-Review-Token). The token is a
  file under the gitignored data/ directory, generated on first start with 32 bytes of entropy. The
  browser client keeps it in sessionStorage after the operator pastes it: there is no cookie, so a
  cross-site request cannot carry it;
* rejects write requests that carry an Origin header other than the served origin (CSRF guard);
* never mounts these routes on the public application - medradar.product.api.create_app does not
  contain a single write route.

Deployment: the public workbench and the review service can share one process (python -m
medradar.product.review serve) or run separately; in both cases review writes exist only in the
process started by the review CLI.
"""
from __future__ import annotations

import datetime as _dt
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ..api import HTTPExceptionCompat, create_app
from ..dataset import PRODUCT_VERSION, load_dataset
from .service import attribution_impact, build_case, build_queue, queue_summary
from .store import ReviewError, ReviewStore

TOKEN_HEADER = "X-MedRadar-Review-Token"
TOKEN_FILE = Path("data") / "identity" / "review.token"

#: Loopback client addresses. "testclient" is Starlette's in-process TestClient, which never
#: touches a socket; keeping it here lets the boundary be tested without weakening the network rule.
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1", "testclient"}


def token_path() -> Path:
    override = os.environ.get("MEDRADAR_REVIEW_TOKEN_FILE")
    return Path(override) if override else TOKEN_FILE


def load_or_create_token(path: Path | None = None) -> str:
    target = path or token_path()
    if target.is_file():
        value = target.read_text(encoding="utf-8").strip()
        if value:
            return value
    target.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32)
    target.write_text(value + "\n", encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:  # pragma: no cover - platform dependent
        pass
    return value


def required_token() -> str:
    override = os.environ.get("MEDRADAR_REVIEW_TOKEN")
    if override:
        return override.strip()
    return load_or_create_token()


def _register_review_routes(app: FastAPI, store: ReviewStore, expected_token: str) -> None:
    holder = getattr(app.state, "holder")
    holder.fingerprint_fn = store.fingerprint
    holder.review_db = store.path

    def _client_is_loopback(request: Request) -> bool:
        host = request.client.host if request.client else ""
        return host in LOOPBACK_HOSTS

    def _authorize(request: Request) -> None:
        if not _client_is_loopback(request):
            raise HTTPExceptionCompat(403, "review_not_local", "identity review is only available from the local machine")
        supplied = request.headers.get(TOKEN_HEADER) or ""
        if not supplied or not hmac.compare_digest(supplied, expected_token):
            raise HTTPExceptionCompat(
                401,
                "review_token_required",
                "a valid identity-review token is required",
                "the token is written to " + str(token_path()) + " on first start; send it as " + TOKEN_HEADER,
            )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                base = str(request.base_url).rstrip("/")
                allowed = {base, "http://127.0.0.1", "http://localhost"}
                if origin.rstrip("/") not in allowed and not origin.startswith(base):
                    raise HTTPExceptionCompat(403, "review_cross_origin", "cross-origin writes are not accepted by the identity-review service")

    def _dataset() -> Any:
        try:
            return holder.get()
        except Exception as error:  # surfaced as 503, never as an empty dataset
            raise HTTPExceptionCompat(503, "dataset_unavailable", str(error))

    def _invalidate() -> None:
        holder.invalidate()

    # ---------------------------------------------------------------- read routes
    @app.get("/api/review/ping")
    def review_ping(request: Request) -> Any:
        _authorize(request)
        data = _dataset()
        return {
            "ok": True,
            "version": PRODUCT_VERSION,
            "review_db": str(store.path),
            "review_db_exists": store.path.exists(),
            "decisions_applied": data.review_overlay_applied,
            "reviewer_header": TOKEN_HEADER,
            "boundary": "loopback only; token required; decisions are appended to an append-only ledger",
        }

    @app.get("/api/review/queue")
    def review_queue(request: Request, status: str | None = None, org: str | None = None, risk: str | None = None,
                     q: str | None = None, sort: str = "records_desc", page: int = 1, page_size: int = 25,
                     include_verified: bool = False) -> Any:
        _authorize(request)
        return build_queue(
            _dataset(), store, status=status, organization=org, risk=risk, query=q, sort=sort,
            page=page, page_size=page_size, include_verified=include_verified,
        )

    @app.get("/api/review/summary")
    def review_summary(request: Request) -> Any:
        _authorize(request)
        data = _dataset()
        summary = queue_summary(data, store)
        summary["metrics"] = data.metrics_summary()
        return summary

    @app.get("/api/review/case/{applicant_key:path}")
    def review_case(request: Request, applicant_key: str) -> Any:
        _authorize(request)
        return build_case(_dataset(), store, applicant_key)

    @app.get("/api/review/history/{applicant_key:path}")
    def review_history(request: Request, applicant_key: str) -> Any:
        _authorize(request)
        return {"applicant_key": applicant_key, "history": [item.to_public() for item in store.history(applicant_key)]}

    @app.get("/api/review/stats")
    def review_stats(request: Request) -> Any:
        _authorize(request)
        return store.stats()

    @app.get("/api/review/audit")
    def review_audit(request: Request, limit: int = 100) -> Any:
        _authorize(request)
        return {"audit": store.audit_trail(limit)}

    @app.get("/api/review/impact")
    def review_impact(request: Request) -> Any:
        """Which organizations changed, and the count-level proof that every other one did not."""
        _authorize(request)
        current = _dataset()
        baseline = load_dataset(current.data_dir, review_db=Path(os.devnull) / "no-review.db")
        payload = attribution_impact(baseline, current)
        payload["applied_decisions"] = current.review_overlay_applied
        payload["review_db"] = str(store.path)
        return payload

    @app.get("/api/review/export")
    def review_export(request: Request) -> Any:
        _authorize(request)
        payload = {
            "schema": "medradar.review_export.v1",
            "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "decisions": [item.to_public() for item in store.all_decisions()],
        }
        headers = {"Content-Disposition": 'attachment; filename="medradar-review-decisions.json"'}
        return Response(content=json.dumps(payload, indent=1, ensure_ascii=False), media_type="application/json", headers=headers)

    # ---------------------------------------------------------------- write routes
    @app.post("/api/review/decisions")
    async def review_decide(request: Request) -> Any:
        _authorize(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPExceptionCompat(400, "bad_json", "request body must be JSON")
        if not isinstance(body, dict):
            raise HTTPExceptionCompat(400, "bad_json", "request body must be a JSON object")
        data = _dataset()
        applicant_name = str(body.get("applicant_name") or "").strip()
        if not applicant_name:
            raise HTTPExceptionCompat(400, "missing_applicant", "applicant_name is required")
        action = str(body.get("action") or "").strip()
        organization_key = body.get("organization_key")
        if organization_key is not None and data.organization(str(organization_key)) is None:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key: " + str(organization_key))
        current, _rejection = data.registry.decide(applicant_name)
        prior_organization = current.organization_key if current else None
        status = str(body.get("status") or "").strip()
        if action in ("approve", "reassign") and not status:
            status = "evidence_verified"
        if action == "reject":
            status = "rejected"
        if action == "unresolved":
            status = "unresolved"
        try:
            decision = store.append(
                applicant_name=applicant_name,
                action=action,
                status=status,
                organization_key=organization_key or prior_organization,
                prior_organization_key=prior_organization,
                reviewer=str(body.get("reviewer") or "").strip(),
                reviewer_kind=str(body.get("reviewer_kind") or "human").strip(),
                basis=body.get("basis"),
                evidence_type=body.get("evidence_type"),
                evidence=body.get("evidence"),
                note=body.get("note"),
                snapshot_id=data.snapshot_id,
                source="admin_api",
            )
        except ReviewError as error:
            raise HTTPExceptionCompat(400, "invalid_decision", str(error))
        _invalidate()
        return {
            "ok": True,
            "decision": decision.to_public(),
            "next": "GET /api/review/case/" + applicant_name,
            "note": "The decision is appended to the ledger; /api/review/impact shows which organizations changed.",
        }

    @app.post("/api/review/decisions/{decision_uid}/revoke")
    async def review_revoke(request: Request, decision_uid: str) -> Any:
        _authorize(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        decisions = {item.decision_uid: item for item in store.all_decisions()}
        target = decisions.get(decision_uid)
        if target is None:
            raise HTTPExceptionCompat(404, "decision_not_found", "no decision with uid " + decision_uid)
        try:
            decision = store.append(
                applicant_name=target.applicant_name,
                action="revoke",
                status="unresolved",
                organization_key=None,
                reviewer=str(body.get("reviewer") or "").strip() or target.reviewer,
                reviewer_kind=str(body.get("reviewer_kind") or "human").strip(),
                note=body.get("note") or "revoked",
                supersedes_uid=decision_uid,
                source="admin_api",
            )
        except ReviewError as error:
            raise HTTPExceptionCompat(400, "invalid_decision", str(error))
        _invalidate()
        return {"ok": True, "revocation": decision.to_public()}

    @app.post("/api/review/import")
    async def review_import(request: Request) -> Any:
        """Import an offline review file produced by GET /api/review/export (append-only)."""
        _authorize(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPExceptionCompat(400, "bad_json", "request body must be JSON")
        decisions = body.get("decisions") if isinstance(body, dict) else None
        if not isinstance(decisions, list):
            raise HTTPExceptionCompat(400, "bad_import", "expected a JSON object with a decisions list")
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
                    prior_organization_key=item.get("prior_organization_key"),
                    reviewer=str(item.get("reviewer") or ""),
                    reviewer_kind=str(item.get("reviewer_kind") or "human"),
                    basis=item.get("basis"),
                    evidence_type=item.get("evidence_type"),
                    evidence=item.get("evidence"),
                    note=item.get("note"),
                    source="offline_import",
                )
                imported += 1
            except ReviewError as error:
                errors.append({"applicant_name": item.get("applicant_name"), "error": str(error)})
        _invalidate()
        return {"ok": True, "imported": imported, "errors": errors}

    @app.exception_handler(HTTPExceptionCompat)
    async def handle_http_error(request: Request, exc: "HTTPExceptionCompat") -> JSONResponse:
        body: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
        if exc.hint:
            body["error"]["hint"] = exc.hint
        return JSONResponse(status_code=exc.status_code, content=body)


def create_admin_app(
    data_dir: Path | str | None = None,
    web_dir: Path | str | None = None,
    review_db: Path | str | None = None,
    token: str | None = None,
) -> FastAPI:
    store = ReviewStore(review_db)
    expected_token = (token or required_token()).strip()

    def setup(app: FastAPI) -> None:
        app.state.review_store = store
        app.state.review_token = expected_token
        _register_review_routes(app, store, expected_token)

    app = create_app(data_dir=data_dir, web_dir=web_dir, setup=setup)
    return app
