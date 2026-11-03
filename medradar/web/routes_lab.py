"""Research Lab API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..product import lab

router = APIRouter(prefix="/api/lab", tags=["lab"])


@router.get("")
def overview() -> dict[str, Any]:
    return lab.lab_overview()


@router.get("/{study_id}")
def detail(study_id: str) -> dict[str, Any]:
    return lab.study_detail(study_id)
