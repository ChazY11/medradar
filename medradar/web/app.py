"""MedRadar 2.0 product web application.

A small FastAPI app that exposes the read-only measurement layer as JSON and
serves the static single-page product UI. It is intentionally dependency-light:
FastAPI + uvicorn only, no database migration, no external services.

Run::

    python -m medradar web --port 8787
    # then open http://127.0.0.1:8787
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..product import catalog, entities, store


def resolve_web_dir() -> Path:
    """Locate the static SPA.

    Order: ``MEDRADAR_WEB_DIR`` → repository ``web/`` → installed data-files
    ``<prefix>/share/medradar/web``. Running from a source checkout always wins
    so local edits are served immediately.
    """
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        Path(os.environ["MEDRADAR_WEB_DIR"]) if os.environ.get("MEDRADAR_WEB_DIR") else None,
        repo_root / "web",
        Path(sys.prefix) / "share" / "medradar" / "web",
    ]
    for candidate in candidates:
        if candidate and (candidate / "index.html").is_file():
            return candidate
    return repo_root / "web"


WEB_DIR = resolve_web_dir()


def _years(years: int) -> int:
    return max(1, min(int(years), 50))


def _parse_company_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    invalid = [key for key in keys if not entities.company_meta(key)]
    if invalid:
        raise ValueError(f"unknown company key(s): {', '.join(invalid)}")
    return tuple(dict.fromkeys(keys))


def create_app() -> FastAPI:
    app = FastAPI(
        title="MedRadar 2.0",
        version=catalog.PRODUCT_VERSION,
        description="Evidence-driven medical technology intelligence. Read-only over the research store.",
        docs_url="/api/docs",
        redoc_url=None,
    )

    @app.middleware("http")
    async def _timing(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response

    @app.exception_handler(KeyError)
    async def _key_error(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc).strip("'\"")})

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def _missing_store(request: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": "store_missing", "detail": str(exc)})

    # ------------------------------------------------------------------- meta
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        sig = store.dataset_signature()
        return {"status": "ok" if sig.get("exists") else "degraded", "dataset": sig, "product": catalog.PRODUCT_VERSION}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        payload = store.dataset_meta()
        payload["analyst_examples"] = catalog.ANALYST_EXAMPLES
        payload["analyst_capabilities"] = catalog.ANALYST_CAPABILITIES
        payload["comparability_notes"] = catalog.COMPARABILITY_NOTES
        payload["studies"] = catalog.STUDIES
        payload["window_choices"] = catalog.WINDOW_CHOICES
        payload["router"] = {
            "companies": [c["key"] for c in entities.roster().values() if c.get("featured")],
            "data_edge": store.data_edge(),
        }
        return payload

    # -------------------------------------------------------------- companies
    @app.get("/api/companies")
    def companies(include_all: bool = Query(True)) -> dict[str, Any]:
        rows = store.company_list(include_all=include_all)
        return {
            "companies": rows,
            "featured": [row for row in rows if row["featured"]],
            "total": len(rows),
            "method_zh": "每个企业的计数来自其归属事件（仓库 company_key，或补充的精确名称映射），按事件类型分组统计。",
        }

    @app.get("/api/companies/{key}")
    def company_profile(key: str, years: int = Query(5, ge=1, le=50)) -> dict[str, Any]:
        return store.company_profile(key, _years(years))

    @app.get("/api/compare")
    def compare(
        companies: str = Query(..., description="comma separated company keys (2-5)"),
        metric: str = Query("approvals"),
        years: int = Query(5, ge=1, le=50),
        granularity: str = Query("quarter"),
    ) -> dict[str, Any]:
        keys = _parse_company_list(companies)
        if len(keys) < 2:
            raise ValueError("select at least two companies")
        if len(keys) > 5:
            raise ValueError("at most five companies per comparison")
        return store.company_compare(keys, metric=metric, years=_years(years), granularity=granularity)

    # ------------------------------------------------------------------ radar
    @app.get("/api/radar")
    def radar(years: int = Query(3, ge=1, le=50)) -> dict[str, Any]:
        payload = store.radar_overview(_years(years))
        payload["domains"] = [{**domain, "members": domain.get("track_detail")} for domain in payload["domains"]]
        payload["catalog"] = {"domains": store.radar_domains(), "metrics": catalog.METRICS}
        return payload

    @app.get("/api/radar/{track}")
    def radar_track(track: str, years: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
        return store.radar_track(track, _years(years))

    # --------------------------------------------------------------- evidence
    @app.get("/api/evidence")
    def evidence(
        companies: str | None = Query(None),
        track: str | None = Query(None),
        metric: str | None = Query(None),
        source: str | None = Query(None),
        start: str | None = Query(None),
        end: str | None = Query(None),
        q: str | None = Query(None, max_length=120),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        keys = _parse_company_list(companies)
        return store.evidence_search(
            companies=keys,
            track=track or None,
            metric=metric or None,
            source=source or None,
            start=start or None,
            end=end or None,
            query=q or None,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/evidence/{event_id}")
    def evidence_event(event_id: str) -> dict[str, Any]:
        return store.event_detail(event_id)

    @app.post("/api/evidence/claim")
    async def evidence_claim(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("claim evidence expects a JSON object")
        return store.claim_evidence(payload)

    # ------------------------------------------------------- analyst and lab
    from . import routes_analyst, routes_lab

    app.include_router(routes_analyst.router)
    app.include_router(routes_lab.router)

    # ----------------------------------------------------------------- static
    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        @app.get("/favicon.svg")
        def favicon() -> FileResponse:
            return FileResponse(WEB_DIR / "favicon.svg")

    else:
        print(
            f"[medradar] static UI not found at {WEB_DIR}; API is available but '/' will 404. "
            "Set MEDRADAR_WEB_DIR or run from the repository checkout.",
            file=sys.stderr,
        )

    return app


app = create_app()
