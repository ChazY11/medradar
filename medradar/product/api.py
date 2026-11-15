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
    OWNERSHIP_BASES,
    RETIRED_OWNERSHIP_BASES,
    PRODUCT_NAME,
    PRODUCT_VERSION,
    REVIEW_FILTERS,
    Dataset,
    default_data_dir,
    load_dataset,
)
from .attribution import ownership as ownership_module
from .attribution import status as status_module
from medradar.data_pipeline.status_service import changes_feed, data_status
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
    """Caches the dataset and reloads it when the identity-review ledger changes.

    The cache is the reason a review decision would otherwise appear to do nothing: the public app
    computes every count from one Dataset instance. fingerprint_fn() is provided by the admin
    service; when the ledger changes, the next request rebuilds the dataset, so a decision is
    visible on the very next page load without restarting the process.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self._dataset: Dataset | None = None
        self._error: str | None = None
        self._lock = threading.Lock()
        self.fingerprint_fn: Any = None
        self._fingerprint: Any = None
        self._snapshot_fingerprint: Any = None
        self.review_db: Path | None = None

    def _data_state(self) -> tuple[Any, Any]:
        review = None
        if self.fingerprint_fn is not None:
            try:
                review = self.fingerprint_fn()
            except Exception:
                review = None
        root = self.data_dir or default_data_dir()
        parts = []
        for name in ("active.json", "snapshot.json"):
            candidate = Path(root) / name
            try:
                stat = candidate.stat()
                parts.append((name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                parts.append((name, None, None))
        return tuple(parts), review

    def get(self) -> Dataset:
        with self._lock:
            snapshot_fingerprint, fingerprint = self._data_state()
            if (
                self._dataset is not None
                and (self.fingerprint_fn is None or fingerprint == self._fingerprint)
                and snapshot_fingerprint == self._snapshot_fingerprint
            ):
                return self._dataset
            changed = (
                self._dataset is None
                or snapshot_fingerprint != self._snapshot_fingerprint
                or (self.fingerprint_fn is not None and fingerprint != self._fingerprint)
            )
            previous_dataset = self._dataset
            if changed:
                # Keep the validated old dataset referenced until the new one has loaded
                # successfully. A bad pointer must degrade the service, not blank it.
                self._dataset = None
                self._error = None
            try:
                loaded = load_dataset(self.data_dir, review_db=self.review_db)
                self._dataset = loaded
                self._error = None
                self._fingerprint = fingerprint
                self._snapshot_fingerprint = snapshot_fingerprint
                return loaded
            except Exception as error:
                self._error = str(error)
                if previous_dataset is not None:
                    # The new pointer/review state is unusable. Keep serving the validated
                    # previous dataset and expose a degraded health state.
                    self._dataset = previous_dataset
                    self._fingerprint = fingerprint
                    self._snapshot_fingerprint = snapshot_fingerprint
                    return previous_dataset
                raise FileNotFoundError(str(error)) from error

    @property
    def degraded_error(self) -> str | None:
        return self._error

    def invalidate(self) -> None:
        with self._lock:
            self._dataset = None
            self._error = None
            self._snapshot_fingerprint = None

    def status(self) -> tuple[str, str | None]:
        try:
            self.get()
        except Exception as error:
            return "degraded", str(error)
        if self._error:
            return "degraded", self._error
        return "ok", None


def raise_for_basis(basis: str | None) -> None:
    if not basis:
        return
    if basis in RETIRED_OWNERSHIP_BASES:
        raise HTTPExceptionCompat(
            400,
            "retired_basis",
            "the basis " + basis + " was retired in PRODUCT-003",
            "it excluded predecessor applicant names, which is not the same as restoring the owner at event time; "
            "use " + RETIRED_OWNERSHIP_BASES[basis] + ", which requires a verified relation with an effective date and "
            "reports the excluded unknown records",
        )
    if basis not in OWNERSHIP_BASES:
        raise HTTPExceptionCompat(400, "bad_basis", "basis must be one of " + ", ".join(OWNERSHIP_BASES))


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
                    review: str | None, basis: str | None, sort: str, page: int, page_size: int) -> dict[str, Any]:
    filtered = dataset.filter_events(
        org_keys=org_keys or None,
        event_types=event_types or None,
        date_from=date_from,
        date_to=date_to,
        categories=categories or None,
        query=query,
        review=review,
        basis=basis,
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
        "basis": dataset.basis(
            ordered,
            event_types=event_types or list(EVENT_TYPE_ORDER),
            window=window,
            rule="Count of attributed regulatory records matching the filters; "
            + (
                "current-group attribution (records filed by an acquired predecessor are counted under the current group; owner at event time is reported per record)"
                if basis != "historical_owner_verified"
                else "historical-owner basis (only records where a verified relation with an effective date places control with this group at the event date)"
            ),
        ),
        "ownership_basis": basis or "current_group",
        "review_filter": review or "any",
        "snapshot": dataset.snapshot_ref(),
    }


def create_app(
    data_dir: Path | str | None = None,
    web_dir: Path | str | None = None,
    setup=None,
    pipeline_db: Path | str | None = None,
) -> FastAPI:
    """Build the read-only public application.

    setup(app) is invoked after the API routes and before the SPA static routes are registered.
    The internal review service uses it to mount write routes on its own application; the public
    application is this function without setup, so it contains no write route at all.
    """
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
    app.state.pipeline_db = Path(pipeline_db) if pipeline_db is not None else None

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
        if holder.degraded_error:
            return {
                "status": "degraded",
                "snapshot": data.snapshot_ref(),
                "version": PRODUCT_VERSION,
                "store": str(data.data_dir),
                "error": holder.degraded_error,
                "serving": "previous_validated_snapshot",
            }
        return {"status": "ok", "snapshot": data.snapshot_ref(), "version": PRODUCT_VERSION, "store": str(data.data_dir)}

    @app.get("/api/meta")
    def meta() -> Any:
        return dataset().meta()

    # ---------------------------------------------------------------- data lifecycle
    @app.get("/api/data-status")
    def pipeline_status() -> Any:
        status = data_status(
            data_dir=holder.data_dir or dataset_module.default_data_dir(),
            pipeline_db=app.state.pipeline_db,
        )
        try:
            data = dataset()
            status["data_snapshot"] = data.snapshot_ref()
            status["freshness"] = data.freshness()
            status["dataset_error"] = holder.degraded_error
        except Exception as error:
            # The lifecycle page must remain usable when the active snapshot is the thing
            # that failed to load. Do not replace it with a 503 and hide the pipeline state.
            status["data_snapshot"] = None
            status["freshness"] = None
            status["dataset_error"] = str(error)
        return status

    @app.get("/api/changes")
    def changes(
        source: str | None = None,
        type: str | None = None,
        org: str | None = None,
        limit: int = Query(default=50),
        offset: int = Query(default=0),
    ) -> Any:
        allowed_sources = {
            "openfda_510k", "openfda_pma", "openfda_recall", "openfda_classification",
        }
        allowed_types = {
            "ADDED", "UPDATED", "REMOVED_CONFIRMED", "UNCHANGED",
            "MISSING_ON_RECHECK", "UNRESOLVED",
        }
        if source and source not in allowed_sources:
            raise HTTPExceptionCompat(400, "bad_source", "source must be one of " + ", ".join(sorted(allowed_sources)))
        if type and type not in allowed_types:
            raise HTTPExceptionCompat(400, "bad_change_type", "type must be one of " + ", ".join(sorted(allowed_types)))
        if limit < 1 or limit > 200:
            raise HTTPExceptionCompat(400, "bad_limit", "limit must be between 1 and 200")
        if offset < 0:
            raise HTTPExceptionCompat(400, "bad_offset", "offset must be non-negative")
        return changes_feed(
            source_id=source, change_type=type, organization_key=org,
            limit=int(limit), offset=int(offset),
            pipeline_db=app.state.pipeline_db,
            data_dir=holder.data_dir or dataset_module.default_data_dir(),
        )

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
                            q: str | None = None, review: str | None = None, basis: str | None = None,
                            sort: str = "event_date_desc",
                            page: str | None = None, page_size: str | None = None) -> Any:
        data = dataset()
        if data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        return _event_response(data, [key], types, date_from, date_to, category, q, review, basis, sort, page, page_size)

    # ---------------------------------------------------------------- events
    @app.get("/api/events")
    def events(org: str | None = None, types: str | None = None, date_from: str | None = Query(default=None, alias="from"),
               date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
               q: str | None = None, review: str | None = None, basis: str | None = None,
               sort: str = "event_date_desc",
               page: str | None = None, page_size: str | None = None) -> Any:
        data = dataset()
        org_keys = _parse_csv(org)
        unknown = [key for key in org_keys if data.organization(key) is None]
        if unknown:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key(s): " + ", ".join(unknown))
        return _event_response(data, org_keys, types, date_from, date_to, category, q, review, basis, sort, page, page_size)

    def _event_response(data: Dataset, org_keys: list[str], types: str | None, date_from: str | None, date_to: str | None,
                        category: str | None, q: str | None, review: str | None, basis: str | None, sort: str,
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
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        raise_for_basis(basis)
        applied = {
            "org": ",".join(org_keys),
            "types": ",".join(event_types),
            "from": date_from or "",
            "to": date_to or "",
            "category": ",".join(categories),
            "q": q or "",
            "review": review or "",
            "basis": basis or "current_group",
            "sort": sort,
        }
        return _events_payload(data, applied, org_keys, event_types, date_from, date_to, categories, q,
                               None if review in (None, "", "any") else review,
                               None if basis in (None, "", "current_group") else basis, sort, page_number, size)

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

    # ---------------------------------------------------------------- device intelligence (PRODUCT-003)
    def _device_payloads():
        from .device import payloads

        return payloads

    @app.get("/api/devices")
    def devices(q: str | None = None, org: str | None = None, product_code: str | None = None,
                category: str | None = None, pathway: str | None = None, relation: str | None = None,
                sort: str = "relevance", page: int = 1, page_size: int = 25) -> Any:
        data = dataset()
        if org and data.organization(org) is None:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key: " + org)
        if pathway and pathway not in ("510k", "pma"):
            raise HTTPExceptionCompat(400, "bad_pathway", "pathway must be 510k or pma")
        if relation and relation not in ("confirmed", "candidate", "none", "any"):
            raise HTTPExceptionCompat(400, "bad_relation", "relation must be confirmed, candidate, none or any")
        return _device_payloads().explorer(
            data,
            q=q,
            organization=org,
            product_code=product_code,
            category=category,
            pathway=pathway,
            relation=None if relation in (None, "", "any") else relation,
            page=page,
            page_size=page_size,
            sort=sort,
        )

    @app.get("/api/devices/quality")
    def devices_quality() -> Any:
        data = dataset()
        from .device import quality_report

        payload = quality_report(data.device_index())
        payload["index_build_ms"] = round(data.device_index_build_ms or 0.0, 1)
        payload["snapshot"] = data.snapshot_ref()
        return payload

    @app.get("/api/devices/unlinked")
    def devices_unlinked(page: int = 1, page_size: int = 25) -> Any:
        return _device_payloads().unlinked_recalls(dataset(), page=page, page_size=page_size)

    @app.get("/api/devices/{device_id:path}")
    def device_detail(device_id: str) -> Any:
        payload = _device_payloads().detail(dataset(), device_id)
        if payload is None:
            raise HTTPExceptionCompat(
                404,
                "device_not_found",
                "unknown device identifier: " + device_id,
                "device identifiers look like device:openfda_510k:K123456 or an FDA identifier such as K123456",
            )
        return payload

    @app.get("/api/device-families/{family_id:path}")
    def device_family(family_id: str) -> Any:
        payload = _device_payloads().family_payload(dataset(), family_id)
        if payload is None:
            raise HTTPExceptionCompat(
                404,
                "family_not_found",
                "unknown device family: " + family_id,
                "family identifiers look like family:pma:P980016",
            )
        return payload

    # ---------------------------------------------------------------- compare
    @app.get("/api/compare")
    def compare(orgs: str = Query(default=""), date_from: str | None = Query(default=None, alias="from"),
                date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                basis: str | None = None, review: str | None = None) -> Any:
        data = dataset()
        keys = _parse_csv(orgs)
        if not keys:
            raise HTTPExceptionCompat(400, "missing_orgs", "orgs is required (comma separated organization keys)")
        try:
            event_types = _parse_event_types(types)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        raise_for_basis(basis)
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        try:
            return build_compare(
                data,
                keys,
                date_from,
                date_to,
                event_types or None,
                basis=None if basis in (None, "", "current_group") else basis,
                review=None if review in (None, "", "any") else review,
            )
        except KeyError as error:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + str(error).strip("'"))
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))

    # ---------------------------------------------------------------- exports
    @app.get("/api/export/events.csv")
    def export_events_csv(org: str | None = None, types: str | None = None,
                          date_from: str | None = Query(default=None, alias="from"),
                          date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
                          q: str | None = None, review: str | None = None, basis: str | None = None,
                          sort: str = "event_date_desc") -> Any:
        data = dataset()
        try:
            event_types = _parse_event_types(types)
            categories = _parse_csv(category)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        raise_for_basis(basis)
        org_keys = _parse_csv(org)
        unknown = [key for key in org_keys if data.organization(key) is None]
        if unknown:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key(s): " + ", ".join(unknown))
        filtered = data.filter_events(org_keys=org_keys or None, event_types=event_types or None, date_from=date_from,
                                      date_to=date_to, categories=categories or None, query=q,
                                      review=None if review in (None, "", "any") else review,
                                      basis=None if basis in (None, "", "current_group") else basis)
        ordered = data.sort_events(filtered, sort)
        body = events_csv(data, ordered, basis=basis or "current_group")
        filters = {"org": org_keys, "types": event_types, "from": date_from, "to": date_to, "category": categories,
                   "q": q, "review": review, "basis": basis or "current_group"}
        headers = {
            "Content-Disposition": 'attachment; filename="' + csv_filename(data) + '"',
            "X-MedRadar-Provenance": provenance_header(data, filters),
            "X-MedRadar-Records": str(len(ordered)),
        }
        return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/export/compare.md")
    def export_compare_md(orgs: str = Query(default=""), date_from: str | None = Query(default=None, alias="from"),
                          date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                          basis: str | None = None, review: str | None = None) -> Any:
        data = dataset()
        keys = _parse_csv(orgs)
        if not keys:
            raise HTTPExceptionCompat(400, "missing_orgs", "orgs is required")
        raise_for_basis(basis)
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        try:
            event_types = _parse_event_types(types)
            body = compare_markdown(
                data,
                keys,
                date_from,
                date_to,
                event_types or None,
                basis=None if basis in (None, "", "current_group") else basis,
                review=None if review in (None, "", "any") else review,
            )
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

    @app.get("/api/export/devices.csv")
    def export_devices_csv(q: str | None = None, org: str | None = None, product_code: str | None = None,
                           category: str | None = None, pathway: str | None = None, relation: str | None = None,
                           sort: str = "relevance") -> Any:
        data = dataset()
        payloads = _device_payloads()
        if org and data.organization(org) is None:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key: " + org)
        result = payloads.explorer(
            data,
            q=q,
            organization=org,
            product_code=product_code,
            category=category,
            pathway=pathway,
            relation=None if relation in (None, "", "any") else relation,
            page=1,
            page_size=100,
            sort=sort,
        )
        # CSV must contain every matching row, not the first page: rebuild without paging.
        all_rows = payloads.explorer(
            data,
            q=q,
            organization=org,
            product_code=product_code,
            category=category,
            pathway=pathway,
            relation=None if relation in (None, "", "any") else relation,
            page=1,
            page_size=result["total"] or 1,
            sort=sort,
        )
        rows = []
        index = data.device_index()
        for item in all_rows["items"]:
            device = index.devices.get(item["device_id"])
            if device is None:
                continue
            rows.append({"device": device, "counts": item["counts"], "organization_display": item.get("organization_display")})
        body = payloads.devices_csv(data, rows)
        filters = {"q": q, "org": org, "product_code": product_code, "category": category, "pathway": pathway, "relation": relation}
        headers = {
            "Content-Disposition": 'attachment; filename="medradar-devices-' + str(data.collected_at)[:10] + '.csv"',
            "X-MedRadar-Provenance": provenance_header(data, filters),
            "X-MedRadar-Records": str(len(rows)),
        }
        return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/export/device.md")
    def export_device_md(device: str = Query(default="")) -> Any:
        payloads = _device_payloads()
        data = dataset()
        if not device:
            raise HTTPExceptionCompat(400, "missing_device", "device is required (a device id or an FDA identifier)")
        body = payloads.device_markdown(data, device)
        if body is None:
            raise HTTPExceptionCompat(404, "device_not_found", "unknown device identifier: " + device)
        headers = {"Content-Disposition": 'attachment; filename="medradar-device-' + device.replace(":", "-") + '.md"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    # ---------------------------------------------------------------- transparency
    @app.get("/api/metrics")
    def metrics() -> Any:
        """Every attribution/coverage claim the product makes, with definitions and UNKNOWNs."""
        data = dataset()
        payload = data.metrics()
        payload["snapshot"] = data.snapshot_ref()
        payload["freshness"] = data.freshness()
        payload["metric_definitions"] = status_module.metric_definitions()
        return payload

    @app.get("/api/ownership")
    def ownership() -> Any:
        """Ownership relations: what is verified, with dates and sources, and what is UNKNOWN."""
        registry = ownership_module.ownership()
        return {
            "schema": "medradar.ownership.v1",
            "updated_at": registry.updated_at,
            "note": registry.note,
            "concepts": {
                "original_applicant": "The exact applicant string FDA recorded on the record.",
                "historical_owner": "Who controlled the filing entity when the event happened; stated only where an independent source with an effective date exists.",
                "current_group": "The tracked organization the entity belongs to today; this is what the product counts by default.",
            },
            "relations": [relation.to_public() for relation in registry.relations],
            "verified_count": sum(1 for relation in registry.relations if relation.verified),
            "unresolved_count": sum(1 for relation in registry.relations if not relation.verified),
            "organizations_with_verified_history": sorted(
                {relation.organization_key for relation in registry.relations if relation.verified}
            ),
        }

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
            "metrics": data.metrics_summary(),
            "status_vocabulary": status_module.status_summary(data.registry.status_counts()),
            "attribution_summary": {
                "accepted_spellings": len(data.registry.decisions),
                "verified_spellings": sum(1 for decision in data.registry.decisions.values() if decision.verified),
                "rule_verified_spellings": sum(1 for decision in data.registry.decisions.values() if decision.rule_verified),
                "proposed_spellings": sum(1 for decision in data.registry.decisions.values() if decision.provisional),
                "curated_spellings": sum(1 for decision in data.registry.decisions.values() if decision.verified),
                "pending_review_spellings": sum(1 for decision in data.registry.decisions.values() if decision.provisional),
                "rejected_spellings": sum(len(org.reject_exact) for org in data.registry.organizations),
                "unattributed_applicant_strings": len(audit["unattributed"]),
                "unattributed_records": len(data.events) - data.global_counts["records"],
                "review_ledger_decisions_applied": data.review_overlay_applied,
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
                    "status": decision.status,
                    "status_label_en": status_module.STATUS_LABELS_EN.get(decision.status, decision.status),
                    "status_label_zh": status_module.STATUS_LABELS_ZH.get(decision.status, decision.status),
                    "verified": decision.verified,
                    "rule_verified": decision.rule_verified,
                    "provisional": decision.provisional,
                    "rule": decision.rule,
                    "rule_detail": decision.rule_detail,
                    "evidence": [item.to_public() for item in decision.evidence] or [{"evidence_type": "registry_record", "note": decision.source or "registry"}],
                    "evidence_count": len(decision.evidence),
                    "reviewer": decision.reviewer,
                    "reviewer_kind": decision.reviewer_kind,
                    "decision_uid": decision.decision_uid,
                    "record_count": int(row.get("records") or 0),
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
                "Each mapping carries a verification status: proposed (no verification), rule_verified (deterministic rule), evidence_verified (independent document recorded) or human_reviewed (named human decision).",
                "Rule-verified is NOT human review and is reported separately from curated share.",
                "Only the internal review workspace can change a mapping; the public API is read-only.",
            ],
            "status_counts": data.registry.status_counts(),
            "snapshot": data.snapshot_ref(),
        }

    # ---------------------------------------------------------------- extension point
    # Anything registered here is matched before the SPA catch-all below.
    if setup is not None:
        setup(app)

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