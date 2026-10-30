"""LLM judge for 8-K catalysts - the part that decides *position size*, not just direction.

A keyword classifier can tell you "this looks positive". It cannot tell you whether
an FDA approval is the company's first $2B drug or a label tweak for a $30M
product. That distinction is exactly what should scale a position from 1% to 5%.

Design constraints for a research tool
--------------------------------------
* **Structured, not prose.** The model returns a fixed JSON verdict.
* **Evidence required.** ``evidence_quotes`` must be verbatim spans from the
  filing; a verdict without evidence is down-weighted, never trusted.
* **Cached by content hash.** Re-running the same filing costs zero tokens.
* **Budgeted.** A hard per-cycle call cap so a cron loop cannot burn an account.
* **Provider-agnostic.** Any OpenAI-compatible ``/chat/completions`` endpoint -
  DeepSeek, OpenAI, Ollama, vLLM, an internal gateway.
* **Degrades honestly.** With no key configured it falls back to the
  deterministic heuristic and says so in the alert payload (``judge: heuristic``).

Environment
-----------
``MEDRADAR_LLM_BASE_URL``  default ``https://api.deepseek.com``
``MEDRADAR_LLM_API_KEY``   required to enable the HTTP judge
``MEDRADAR_LLM_MODEL``     default ``deepseek-chat``
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from .util import sha1, truncate, utc_now_iso

PROMPT_VERSION = "8k-v1"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
MAX_INPUT_CHARS = 24_000

CATALYST_TYPES = {
    "approval",
    "crl",
    "trial_result",
    "label_expansion",
    "safety",
    "deal",
    "earnings",
    "guidance",
    "other",
}

SYSTEM_PROMPT = """You are a buyside analyst judging the materiality of an SEC 8-K filing for a US-listed
healthcare company. Return ONLY a JSON object with exactly these keys:

{
  "direction": 1 | 0 | -1,          // +1 positive for equity value, -1 negative, 0 neutral/unclear
  "materiality": 0.0-1.0,           // how much this could move revenue/enterprise value
  "confidence": 0.0-1.0,            // your confidence in this judgement
  "catalyst_type": one of ["approval","crl","trial_result","label_expansion","safety","deal","earnings","guidance","other"],
  "asset": "drug or device name, or empty string",
  "indication": "medical indication, or empty string",
  "is_pivotal": true | false,       // pivotal trial / major label expansion / first approval in class
  "revenue_relevance": "high" | "medium" | "low" | "unknown",
  "evidence_quotes": ["verbatim span 1", "verbatim span 2"],
  "rationale_zh": "one or two sentences in Chinese explaining the position-size implication"
}

Materiality rubric:
  0.8-1.0  first-in-class approval, pivotal Phase 3 hit, major label expansion, large deal
  0.5-0.79 meaningful clinical/regulatory win on a commercially relevant asset
  0.2-0.49 incremental label change, small indication, routine partnership
  0.0-0.19 administrative, earnings calendar, immaterial

Rules:
- evidence_quotes must be copied verbatim from the filing (max 3 quotes, each <= 25 words).
- If the filing is an earnings release, catalyst_type="earnings" and materiality <= 0.2.
- Never invent an asset name; use "" when unsure.
- Output JSON only. No markdown fences, no commentary."""


@dataclass
class JudgeConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "JudgeConfig":
        return cls(
            base_url=os.environ.get("MEDRADAR_LLM_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("MEDRADAR_LLM_API_KEY", ""),
            model=os.environ.get("MEDRADAR_LLM_MODEL", DEFAULT_MODEL),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


# ----------------------------------------------------------------------- parsing
def build_prompt(headline: str, text: str) -> tuple[str, str]:
    body = truncate(re.sub(r"\s+", " ", text or ""), MAX_INPUT_CHARS)
    user = f"Headline: {headline}\n\nFiling text:\n{body}"
    return SYSTEM_PROMPT, user


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_verdict(raw: str) -> dict[str, Any]:
    """Extract and validate the JSON verdict; raises ``ValueError`` when unusable."""
    text = _FENCE_RE.sub("", (raw or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("verdict is not an object")

    direction = int(payload.get("direction", 0))
    verdict = {
        "direction": 1 if direction > 0 else (-1 if direction < 0 else 0),
        "materiality": _clamp(payload.get("materiality"), 0.0, 1.0),
        "confidence": _clamp(payload.get("confidence"), 0.0, 1.0),
        "catalyst_type": (
            payload.get("catalyst_type")
            if payload.get("catalyst_type") in CATALYST_TYPES
            else "other"
        ),
        "asset": truncate(payload.get("asset", ""), 120),
        "indication": truncate(payload.get("indication", ""), 120),
        "is_pivotal": bool(payload.get("is_pivotal", False)),
        "revenue_relevance": (
            payload.get("revenue_relevance")
            if payload.get("revenue_relevance") in ("high", "medium", "low", "unknown")
            else "unknown"
        ),
        "evidence_quotes": [
            truncate(quote, 300)
            for quote in (payload.get("evidence_quotes") or [])
            if isinstance(quote, str) and quote.strip()
        ][:3],
        "rationale_zh": truncate(payload.get("rationale_zh", ""), 400),
    }
    # Evidence is the anti-hallucination guard: no quote, no trust.
    if not verdict["evidence_quotes"]:
        verdict["confidence"] = round(verdict["confidence"] * 0.5, 3)
        verdict["unverified"] = True
    return verdict


def _clamp(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return round(max(low, min(high, number)), 3)


# ------------------------------------------------------------------------ judges
class HeuristicJudge:
    """Deterministic fallback: keyword direction + rubric materiality."""

    name = "heuristic"

    def judge(self, headline: str, text: str) -> dict[str, Any]:
        from .live import classify_text

        direction, score, matched = classify_text(text)
        lower = (text or "").lower()
        materiality = 0.25 if direction else 0.1
        if "phase 3" in lower or "phase iii" in lower:
            materiality += 0.15
        if "primary endpoint" in lower:
            materiality += 0.1
        if "pivotal" in lower:
            materiality += 0.1
        if "first-line" in lower or "first line" in lower:
            materiality += 0.05
        if "earnings" in lower or "financial results" in lower:
            materiality = min(materiality, 0.2)
            direction = 0
        evidence = _sentence_around(text, matched[0]) if matched else []
        return {
            "direction": direction,
            "materiality": round(min(0.75, materiality), 3),
            "confidence": round(min(0.6, 0.35 + 0.1 * len(matched)), 3),
            "catalyst_type": _guess_type(lower),
            "asset": "",
            "indication": "",
            "is_pivotal": "pivotal" in lower,
            "revenue_relevance": "unknown",
            "evidence_quotes": evidence,
            "rationale_zh": "关键词回退判定（未配置 LLM）：" + ("、".join(matched) or "无匹配信号"),
            "judge": "heuristic",
        }


class HttpJudge:
    """Any OpenAI-compatible chat endpoint."""

    name = "http"

    def __init__(self, config: JudgeConfig) -> None:
        self.config = config

    def judge(self, headline: str, text: str) -> dict[str, Any]:
        system, user = build_prompt(headline, text)
        body = {
            "model": self.config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "User-Agent": "medradar-judge/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        raw = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        verdict = parse_verdict(raw)
        verdict["judge"] = f"llm:{self.config.model}"
        return verdict


# ------------------------------------------------------------------ cached facade
class CachedJudge:
    """Wraps a judge with a DB cache and a per-process call budget."""

    def __init__(self, db, judge, budget: int = 4, model: str = "heuristic") -> None:
        self.db = db
        self.judge = judge
        self.model = model
        self.remaining = max(0, budget)
        self.calls = 0
        self.cache_hits = 0

    def judge_filing(self, headline: str, text: str) -> dict[str, Any]:
        key = sha1(f"{PROMPT_VERSION}|{self.model}|{headline}|{(text or '')[:MAX_INPUT_CHARS]}")
        row = self.db.scalar(
            "SELECT verdict FROM llm_verdicts WHERE content_hash = ?", (key,)
        )
        if row:
            self.cache_hits += 1
            return json.loads(row)
        if self.remaining <= 0:
            verdict = HeuristicJudge().judge(headline, text)
            verdict["judge"] = (
                "heuristic(no-llm-key)" if self.model == "heuristic" else "heuristic(budget-exhausted)"
            )
            return verdict
        self.remaining -= 1
        self.calls += 1
        verdict = self.judge.judge(headline, text)
        self.db.execute(
            "INSERT OR REPLACE INTO llm_verdicts(content_hash, model, verdict, created_at)"
            " VALUES (?,?,?,?)",
            (key, self.model, json.dumps(verdict, ensure_ascii=False), utc_now_iso()),
        )
        self.db.conn.commit()
        return verdict


def make_judge(db, use_llm: bool = True, budget: int = 4) -> CachedJudge:
    """Pick the best available judge and wrap it with caching + budget."""
    config = JudgeConfig.from_env()
    if use_llm and config.enabled:
        return CachedJudge(db, HttpJudge(config), budget=budget, model=config.model)
    return CachedJudge(db, HeuristicJudge(), budget=0, model="heuristic")


# ------------------------------------------------------------------------ helpers
def _sentence_around(text: str, needle: str) -> list[str]:
    """Return the full sentence containing ``needle`` (evidence must read cleanly)."""
    haystack = text or ""
    index = haystack.lower().find(needle.lower())
    if index < 0:
        return []
    for sentence in re.split(r"(?<=[.!?])\s+", haystack):
        if needle.lower() in sentence.lower():
            cleaned = re.sub(r"\s+", " ", sentence).strip()
            if cleaned:
                return [truncate(cleaned, 300)]
    window = re.sub(r"\s+", " ", haystack[max(0, index - 160) : index + 200]).strip()
    return [truncate(window, 300)]


def _guess_type(lower: str) -> str:
    if "complete response" in lower:
        return "crl"
    if "fda approval" in lower or "approved" in lower:
        return "approval"
    if "topline" in lower or "primary endpoint" in lower:
        return "trial_result"
    if "label" in lower and "expand" in lower:
        return "label_expansion"
    if "recall" in lower or "safety" in lower:
        return "safety"
    if "acquisition" in lower or "merger" in lower:
        return "deal"
    if "financial results" in lower or "earnings" in lower:
        return "earnings"
    return "other"
