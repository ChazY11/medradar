"""AI Research Analyst API routes.

The analyst is a deterministic retrieval + statistics engine over the same
measurement layer as the rest of the product. It is not a free-form chatbot and
does not require an API key: a question is parsed into an intent, real queries
are executed, and the answer cites event ids that the Evidence Explorer can
open. Optional narration (if ever enabled) must be labelled separately.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..product import analyst, catalog

router = APIRouter(prefix="/api/analyst", tags=["analyst"])


@router.get("/examples")
def examples() -> dict[str, Any]:
    return {
        "examples": catalog.ANALYST_EXAMPLES,
        "capabilities": catalog.ANALYST_CAPABILITIES,
        "mode": "deterministic",
        "mode_zh": "确定性证据检索引擎：不使用大模型，不需要 API Key，所有结论来自数据库查询。",
    }


@router.post("/ask")
async def ask(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object with a question field")
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("question is required")
    if len(question) > 300:
        raise ValueError("question is too long (max 300 characters)")
    return analyst.answer(question)
