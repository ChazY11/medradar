"""FastAPI application for the MedRadar workbench.

Thin projection of medradar.product.dataset: routing, query parsing, HTTP semantics and static
file serving. All measurement lives in the dataset / compare / export modules so that the tests
can exercise the same code the API uses.

Run:

    python -m medradar web --port 8787
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from . import dataset as dataset_module
from .compare import build_compare
from .dataset import (
    EVENT_TYPE_ORDER,
    PRODUCT_NAME,
    PRODUCT_VERSION,
    Dataset,
    load_dataset,
)
from .export import (
    compare_markdown,
    compare_markdown_filename,
    csv_filename,
    events_csv,
    organization_markdown,
    organization_markdown_filename,
    provenance_header,
)

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


class DatasetHolder:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self._dataset: Dataset | None = None
        self._error: str | None = None
        self._lock = threading.Lock()

    def get(self) -> Dataset:
        with self._lock:
            if self._dataset is not None:
                return self._dataset
            if self._error is not None:
                raise FileNotFoundError(self._error)
            try:
                self._dataset = load_dataset(self.data_dir)
                return self._dataset
            except Exception as error:  # surfaced as 503, never as a silent empty dataset
                self._error = str(error)
                raise

    def status(self) -> tuple[str, str | None]:
        try:
            dataset = self.get()
        except Exception as error:
            return "degraded", str(error)
        return "ok", None


def _error(status_code: int, code: str, message: str, hint: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if hint:
        body["error"]["hint"] = hint
    return JSONResponse(status_code=status_code, content=body)


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_event_types(value: str | None) -> list[str]:
    items = _parse_csv(value)
    invalid = [item for item in items if item not in EVENT_TYPE_ORDER]
    if invalid:
        raise ValueError("unknown event type(s): " + ", ".join(invalid) + "; expected " + ", ".join(EVENT_TYPE_ORDER))
    return items


def _parse_int(value: str | None, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError("invalid integer for " + name) from error
    if parsed < minimum or parsed > maximum:
        raise ValueError(name + " must be between " + str(minimum) + " and " + str(maximum))
    return parsed


def _events_payload(dataset: Dataset, applied: dict[str, str], org_keys: list[str], event_types: list[str],
                    date_from: str | None, date_to: str | None, categories: list[str], query: str | None,
                    review: str | None, sort: str, page: int, page_size: int) -> dict[str, Any]:
    filtered = dataset.filter_events(
        org_keys=org_keys or None,
        event_types=event_types or None,
        date_from=date_from,
        date_to=date_to,
        categories=categories or None,
        query=query,
        review=review,
    )
    ordered = dataset.sort_events(filtered, sort)
    total = len(ordered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    items = ordered[start:start + page_size]
    window = {"from": date_from, "to": date_to}
    return {
        "items": [event.to_public() for event in items],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "applied_filters": applied,
        "aggregations": dataset_module.aggregate(ordered),
        "counts": dataset.counts(ordered),
        "basis": dataset.basis(ordered, event_types=event_types or list(EVENT_TYPE_ORDER), window=window),
        "snapshot": dataset.snapshot_ref(),
    }


def create_app(data_dir: Path | str | None = None, web_dir: Path | str | None = None) -> FastAPI:
    holder = DatasetHolder(Path(data_dir) if data_dir else None)
    resolved_web = Path(web_dir) if web_dir else _default_web_dir()

    app = FastAPI(
        title="MedRadar workbench API",
        version=PRODUCT_VERSION,
        description="Medical technology intelligence over an immutable openFDA snapshot.",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.holder = holder
    app.state.web_dir = resolved_web

    @app.middleware("http")
    async def timing(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Time-ms"] = format((time.perf_counter() - started) * 1000.0, ".1f")
        return response

    def dataset() -> Dataset:
        try:
            return holder.get()
        except FileNotFoundError as error:
            raise HTTPExceptionCompat(503, "dataset_unavailable", str(error), "collect the snapshot with: python scripts/product_collect.py")
        except Exception as error:
            raise HTTPExceptionCompat(503, "dataset_error", str(error))

    # ---------------------------------------------------------------- health & meta
    @app.get("/api/health")
    def health() -> Any:
        try:
            data = holder.get()
        except Exception as error:
            return {"status": "degraded", "snapshot": None, "version": PRODUCT_VERSION, "store": str(error)}
        return {"status": "ok", "snapshot": data.snapshot_ref(), "version": PRODUCT_VERSION, "store": str(data.data_dir)}

    @app.get("/api/meta")
    def meta() -> Any:
        return dataset().meta()

    # ---------------------------------------------------------------- search
    @app.get("/api/search")
    def search(q: str = Query(default=""), limit: int = Query(default=8)) -> Any:
        if not q.strip():
            raise HTTPExceptionCompat(400, "empty_query", "q is required")
        data = dataset()
        return data.search(q.strip(), max(1, min(int(limit), 20)))

    # ---------------------------------------------------------------- organizations
    @app.get("/api/organizations")
    def organizations() -> Any:
        return dataset().organizations_payload()

    @app.get("/api/organizations/{key}")
    def organization(key: str) -> Any:
        data = dataset()
        if data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        return data.organization_profile(key)

    @app.get("/api/organizations/{key}/events")
    def organization_events(key: str, types: str | None = None, date_from: str | None = Query(default=None, alias="from"),
                            date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
                            q: str | None = None, review: str | None = None, sort: str = "event_date_desc",
                            page: str | None = None, page_size: str | None = None) -> Any:
        data = dataset()
        if data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        return _event_response(data, [key], types, date_from, date_to, category, q, review, sort, page, page_size)

    # ---------------------------------------------------------------- events
    @app.get("/api/events")
    def events(org: str | None = None, types: str | None = None, date_from: str | None = Query(default=None, alias="from"),
               date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
               q: str | None = None, review: str | None = None, sort: str = "event_date_desc",
               page: str | None = None, page_size: str | None = None) -> Any:
        data = dataset()
        org_keys = _parse_csv(org)
        unknown = [key for key in org_keys if data.organization(key) is None]
        if unknown:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key(s): " + ", ".join(unknown))
        return _event_response(data, org_keys, types, date_from, date_to, category, q, review, sort, page, page_size)

    def _event_response(data: Dataset, org_keys: list[str], types: str | None, date_from: str | None, date_to: str | None,
                        category: str | None, q: str | None, review: str | None, sort: str,
                        page: str | None, page_size: str | None) -> Any:
        try:
            event_types = _parse_event_types(types)
            categories = _parse_csv(category)
            page_number = _parse_int(page, "page", 1, 1, 100000)
            size = _parse_int(page_size, "page_size", DEFAULT_PAGE_SIZE, 10, MAX_PAGE_SIZE)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        if sort not in ("event_date_desc", "event_date_asc", "official_id_asc"):
            raise HTTPExceptionCompat(400, "bad_sort", "sort must be one of event_date_desc, event_date_asc, official_id_asc")
        if review and review not in ("curated", "pending_review", "any"):
            raise HTTPExceptionCompat(400, "bad_review", "review must be curated, pending_review or any")
        applied = {
            "org": ",".join(org_keys),
            "types": ",".join(event_types),
            "from": date_from or "",
            "to": date_to or "",
            "category": ",".join(categories),
            "q": q or "",
            "review": review or "",
            "sort": sort,
        }
        return _events_payload(data, applied, org_keys, event_types, date_from, date_to, categories, q,
                               None if review in (None, "", "any") else review, sort, page_number, size)

    @app.get("/api/events/{event_id:path}")
    def event_detail(event_id: str) -> Any:
        data = dataset()
        event = data.resolve_event(event_id)
        if event is None:
            raise HTTPExceptionCompat(404, "event_not_found", "unknown event identifier: " + event_id + " (expected a full event id such as openfda_510k:K231234, or a unique official FDA identifier)")
        source = next((row for row in data.sources() if row["source_id"] == event.source_id), None)
        queried = None
        for entry in data.manifest.get("organizations") or []:
            for query in entry.get("queries") or []:
                if query.get("source_id") == event.source_id and query.get("urls"):
                    queried = query["urls"][0]
                    break
            if queried:
                break
        return {
            "event": event.to_public(),
            "provenance": {
                "source_id": event.source_id,
                "source_name": source["name"] if source else event.source_id,
                "official_url": event.official_url,
                "queried_endpoint": queried,
                "collected_at": data.collected_at,
                "official_identifier_label": {
                    "openfda_510k": "510(k) number",
                    "openfda_pma": "PMA number (and supplement)",
                    "openfda_recall": "FDA recall product reference",
                }.get(event.source_id, "official identifier"),
                "raw": event.raw,
            },
            "freshness": data.freshness(),
        }

    # ---------------------------------------------------------------- compare
    @app.get("/api/compare")
    def compare(orgs: str = Query(default=""), date_from: str | None = Query(default=None, alias="from"),
                date_to: str | None = Query(default=None, alias="to"), types: str | None = None) -> Any:
        data = dataset()
        keys = _parse_csv(orgs)
        if not keys:
            raise HTTPExceptionCompat(400, "missing_orgs", "orgs is required (comma separated organization keys)")
        try:
            event_types = _parse_event_types(types)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        try:
            return build_compare(data, keys, date_from, date_to, event_types or None)
        except KeyError as error:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + str(error).strip("'"))
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))

    # ---------------------------------------------------------------- exports
    @app.get("/api/export/events.csv")
    def export_events_csv(org: str | None = None, types: str | None = None,
                          date_from: str | None = Query(default=None, alias="from"),
                          date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
                          q: str | None = None, review: str | None = None, sort: str = "event_date_desc") -> Any:
        data = dataset()
        try:
            event_types = _parse_event_types(types)
            categories = _parse_csv(category)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        org_keys = _parse_csv(org)
        unknown = [key for key in org_keys if data.organization(key) is None]
        if unknown:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key(s): " + ", ".join(unknown))
        filtered = data.filter_events(org_keys=org_keys or None, event_types=event_types or None, date_from=date_from,
                                      date_to=date_to, categories=categories or None, query=q,
                                      review=None if review in (None, "", "any") else review)
        ordered = data.sort_events(filtered, sort)
        body = events_csv(data, ordered)
        filters = {"org": org_keys, "types": event_types, "from": date_from, "to": date_to, "category": categories, "q": q, "review": review}
        headers = {
            "Content-Disposition": 'attachment; filename="' + csv_filename(data) + '"',
            "X-MedRadar-Provenance": provenance_header(data, filters),
            "X-MedRadar-Records": str(len(ordered)),
        }
        return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/export/compare.md")
    def export_compare_md(orgs: str = Query(default=""), date_from: str | None = Query(default=None, alias="from"),
                          date_to: str | None = Query(default=None, alias="to"), types: str | None = None) -> Any:
        data = dataset()
        keys = _parse_csv(orgs)
        if not keys:
            raise HTTPExceptionCompat(400, "missing_orgs", "orgs is required")
        try:
            event_types = _parse_event_types(types)
            body = compare_markdown(data, keys, date_from, date_to, event_types or None)
        except KeyError as error:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + str(error).strip("'"))
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        headers = {"Content-Disposition": 'attachment; filename="' + compare_markdown_filename(keys, data) + '"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    @app.get("/api/export/organization.md")
    def export_organization_md(key: str = Query(default="")) -> Any:
        data = dataset()
        if not key or data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        body = organization_markdown(data, key)
        headers = {"Content-Disposition": 'attachment; filename="' + organization_markdown_filename(key, data) + '"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    # ---------------------------------------------------------------- transparency
    @app.get("/api/coverage")
    def coverage() -> Any:
        data = dataset()
        organizations = []
        for org in sorted(data.registry.organizations, key=lambda item: item.display_name.casefold()):
            stats = data.org_stats.get(org.key)
            organizations.append({
                "key": org.key,
                "display_name": org.display_name,
                "records": stats.counts["records"] if stats else 0,
                "sources": [
                    {"source_id": row["source_id"], "records": row["records"],
                     "min_event_date": row["min_event_date"], "max_event_date": row["max_event_date"]}
                    for row in (stats.sources if stats else [])
                ],
                "pending_review_spellings": len([item for item in data.registry.accepted_spellings_by_org.get(org.key, ()) if item.review == "pending_review"]),
            })
        audit = _collection_audit(data)
        counts = data.manifest.get("counts") or {}
        files = data.manifest.get("files") or {}
        return {
            "snapshot": data.snapshot_ref(),
            "freshness": data.freshness(),
            "sources": data.sources(),
            "organizations": organizations,
            "collection_audit": audit,
            "out_of_scope": dataset_module.OUT_OF_SCOPE,
            "time_semantics": dataset_module.TIME_SEMANTICS,
            "manifest": {
                "id": data.snapshot_id,
                "collected_at": data.collected_at,
                "collection_started_at": data.manifest.get("collection_started_at"),
                "openfda_last_updated": (data.manifest.get("openfda") or {}).get("last_updated"),
                "request_count": data.manifest.get("request_count"),
                "response_bytes": data.manifest.get("response_bytes"),
                "organization_count": data.manifest.get("organization_count"),
                "counts": counts,
                "data_quality": data.manifest.get("data_quality") or {},
                "errors": data.manifest.get("errors") or [],
                "files": [
                    {"name": name, "sha256": meta.get("sha256"), "bytes": meta.get("bytes"), "records": meta.get("records")}
                    for name, meta in files.items()
                ],
                "notes": data.manifest.get("notes") or [],
            },
            "limitations": data.limitations(),
            "attribution_summary": {
                "curated_spellings": sum(1 for org in data.registry.organizations for item in data.registry.accepted_spellings_by_org.get(org.key, ()) if item.review == "curated"),
                "pending_review_spellings": sum(1 for org in data.registry.organizations for item in data.registry.accepted_spellings_by_org.get(org.key, ()) if item.review == "pending_review"),
                "rejected_spellings": sum(len(org.reject_exact) for org in data.registry.organizations),
                "unattributed_applicant_strings": len(audit["unattributed"]),
                "unattributed_records": len(data.events) - data.global_counts["records"],
            },
            "reproduce": {
                "collect": "python scripts/product_collect.py",
                "curate": "python scripts/product_curate_aliases.py --apply",
                "serve": "python -m medradar web --port 8787",
                "test": "python -m pytest tests/product -q",
            },
        };

    def _collection_audit(data: Dataset) -> dict[str, Any]:
        tokens = []
        for entry in data.manifest.get("organizations") or []:
            for query in entry.get("queries") or []:
                tokens.append({
                    "token": entry.get("key") or "",
                    "org_key": entry.get("key") or "",
                    "endpoint": query.get("source_id") or "",
                    "records_retrieved": int(query.get("records") or 0),
                    "pages": int(query.get("pages") or 0),
                    "urls": (query.get("urls") or [])[:3],
                })
        unattributed = []
        rejected = []
        for row in data.applicants:
            name = str(row.get("applicant_name") or "")
            decision, rejection = data.registry.decide(name)
            if decision is not None:
                continue
            if rejection is not None:
                rejected.append({"applicant_name": name, "org_key": rejection.organization_key, "reason": rejection.reason})
            else:
                unattributed.append({
                    "applicant_name": name,
                    "records": int(row.get("records") or 0),
                    "endpoints": sorted((row.get("by_source") or {}).keys()),
                })
        unattributed.sort(key=lambda item: -item["records"])
        return {"tokens": tokens, "unattributed": unattributed, "rejected": rejected}

    @app.get("/api/attribution")
    def attribution() -> Any:
        data = dataset()
        decisions = []
        for org in data.registry.organizations:
            for decision in data.registry.accepted_spellings_by_org.get(org.key, ()):
                row = data.applicant_by_name.get(decision.applicant_name) or {}
                decisions.append({
                    "organization_key": org.key,
                    "organization_display": org.display_name,
                    "applicant_name": decision.applicant_name,
                    "basis": decision.basis,
                    "review": decision.review,
                    "confidence": "high" if decision.review == "curated" else "medium",
                    "record_count": int(row.get("records") or 0),
                    "evidence": decision.source or "registry",
                })
        decisions.sort(key=lambda item: (-item["record_count"], item["organization_key"], item["applicant_name"]))
        rejected = []
        unmatched = []
        for row in data.applicants:
            name = str(row.get("applicant_name") or "")
            decision, rejection = data.registry.decide(name)
            if decision is not None:
                continue
            if rejection is not None:
                rejected.append({"applicant_name": name, "organization_key": rejection.organization_key, "reason": rejection.reason})
            else:
                unmatched.append({
                    "applicant_name": name,
                    "records": int(row.get("records") or 0),
                    "endpoints": sorted((row.get("by_source") or {}).keys()),
                    "seen_with_tokens": sorted((row.get("by_org_scope") or {}).keys()),
                })
        unmatched.sort(key=lambda item: -item["records"])
        return {
            "decisions": decisions,
            "rejected": rejected,
            "unmatched": unmatched,
            "policy": [
                "Attribution is exact applicant-name matching after case folding and whitespace collapse; the verbatim string is preserved.",
                "No fuzzy, prefix or substring matching is used for attribution.",
                "Strings not in the registry stay unattributed and are counted in the audit, never folded into an organization.",
                "Attribution decisions marked pending_review are provisional; the product labels them as such.",
            ],
            "snapshot": data.snapshot_ref(),
        }

    # ---------------------------------------------------------------- static UI
    @app.get("/")
    def index() -> Any:
        return _serve_index(resolved_web)

    @app.get("/favicon.svg")
    def favicon() -> Any:
        candidate = resolved_web / "favicon.svg"
        if candidate.is_file():
            return FileResponse(candidate, media_type="image/svg+xml")
        raise HTTPExceptionCompat(404, "not_found", "favicon not built")

    @app.get("/{path:path}")
    def spa(path: str) -> Any:
        if path.startswith("api/"):
            raise HTTPExceptionCompat(404, "not_found", "unknown API route: /" + path)
        candidate = resolved_web / path
        if candidate.is_file() and resolved_web in candidate.resolve().parents:
            return FileResponse(candidate)
        return _serve_index(resolved_web)

    @app.exception_handler(HTTPExceptionCompat)
    async def handle_http_error(request: Request, exc: "HTTPExceptionCompat") -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.hint)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return _error(500, "internal_error", "unexpected server error: " + str(exc))

    return app


def _default_web_dir() -> Path:
    candidates = []
    env = os.environ.get("MEDRADAR_WEB_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path(__file__).resolve().parents[2] / "web" / "dist")
    candidates.append(Path(__file__).resolve().parents[2] / "web")
    candidates.append(Path(sys.prefix) / "share" / "medradar" / "web")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[-1]


def _serve_index(web_dir: Path) -> Any:
    index = web_dir / "index.html"
    if not index.is_file():
        return _error(503, "ui_not_built", "the web workbench has not been built",
                      "run: cd web && npm install && npm run build")
    return FileResponse(index)


class HTTPExceptionCompat(Exception):
    def __init__(self, status_code: int, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint
