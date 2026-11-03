"""Live Observatory API routes (``/api/observatory/*``).

Read-only JSON over the observation ledger. Every endpoint returns HTTP 200 with
an honest empty state when the ledger file does not exist (the CI wheel/demo has
no ledger); a missing observation id raises ``KeyError`` which the application
maps to a 404 JSON response.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..product import observatory

router = APIRouter(prefix="/api/observatory", tags=["observatory"])


@router.get("/summary")
def summary() -> dict[str, Any]:
    """Ledger health plus per-window, per-source, per-company and per-track counts."""
    return observatory.summary()


@router.get("/events")
def events(
    window: str = Query("7d", description="24h | 7d | 30d"),
    change: str = Query("all", description="all | new | updated | removed | failed"),
    source: str | None = Query(None, max_length=64),
    company: str | None = Query(None, max_length=120, description="entity_id or __unmapped__"),
    track: str | None = Query(None, max_length=120, description="track_id or __unmapped__"),
    q: str | None = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Observed changes in the requested window, with window-scoped facets."""
    return observatory.events(
        window=window,
        change=change,
        source=source,
        company=company,
        track=track,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{observation_id}")
def event_detail(observation_id: str) -> dict[str, Any]:
    """One observation: version chain, changes, mapping/status history, sync context."""
    return observatory.event_detail(observation_id)


@router.get("/sources")
def sources() -> dict[str, Any]:
    """Per-source sync status, measured lag, recent runs/failures, entity coverage."""
    return observatory.sources()


@router.get("/replay")
def replay(
    as_of: str = Query(..., description="ISO 8601 instant, e.g. 2026-11-03T10:00:00Z"),
    source: str | None = Query(None, max_length=64),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """The ledger as a reader actually knew it at ``as_of``."""
    return observatory.replay(as_of=as_of, source=source, limit=limit)
