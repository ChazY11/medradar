"""Research Lab API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..product import lab
from ..product import prospective as prospective_product

router = APIRouter(prefix="/api/lab", tags=["lab"])


@router.get("")
def overview() -> dict[str, Any]:
    return lab.lab_overview()


# NOTE: the prospective routes MUST stay above the "/{study_id}" catch-all,
# otherwise FastAPI matches "prospective" as a study id and shadows them.
@router.get("/prospective")
def prospective_overview() -> dict[str, Any]:
    """Frozen prospective observation registry (honest empty state when empty)."""
    return prospective_product.overview()


@router.get("/prospective/{entry_id}")
def prospective_entry(entry_id: str) -> dict[str, Any]:
    """One frozen entry, its append-only evaluation history and tamper check."""
    return prospective_product.entry(entry_id)


@router.get("/{study_id}")
def detail(study_id: str) -> dict[str, Any]:
    return lab.study_detail(study_id)
