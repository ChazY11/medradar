"""Prompt construction for the local enrichment worker.

The prompt is designed for one measurable property: **a parseable, checkable answer**. A small
model is not asked to decide anything - it is asked to propose topics and organisations *with a
verbatim quote*, and every proposal is then checked by the deterministic rule layer. A
proposal without a quote that appears in the source text is rejected, so a model cannot invent
a technology and have it appear in the graph.

The output contract is a single JSON object. ``PROMPT_VERSION`` is stored with every candidate,
so a prompt change is a visible version change and never a silent behaviour change.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

PROMPT_VERSION = "radar-ai-prompt-1"
MAX_SOURCE_CHARS = 1400

SYSTEM = (
    "You are a careful medical-technology evidence assistant. You answer with a single JSON "
    "object and nothing else. You never guess. If the text does not support a label, you leave "
    "it out. Every label you give must be accompanied by a short quote copied exactly from the "
    "text."
)


def build_prompt(
    *,
    title: str,
    body: str,
    record_type: str,
    source: str,
    allowed_topics: Iterable[Mapping[str, Any]],
    allowed_organizations: Iterable[Mapping[str, Any]],
) -> str:
    topic_lines = "\n".join(
        f"- {topic['id']}: {topic.get('label_en')} ({topic.get('family')})"
        for topic in allowed_topics
    )
    organization_lines = "\n".join(
        f"- {org['id']}: {org.get('canonical_name')}"
        for org in allowed_organizations
    )
    text = " ".join(str(body or "").split())[:MAX_SOURCE_CHARS]
    return (
        f"SOURCE: {source}\n"
        f"RECORD TYPE: {record_type}\n"
        f"TITLE: {title}\n"
        f"TEXT: {text}\n\n"
        "TASK: list the technology topics this record is about, and the organisations it names.\n\n"
        "ALLOWED TOPIC IDS:\n"
        f"{topic_lines}\n\n"
        "ALLOWED ORGANISATION IDS:\n"
        f"{organization_lines or '- (none)'}\n\n"
        "RULES:\n"
        "1. Use only the ids above. Do not invent an id.\n"
        "2. evidence_quote must be copied exactly, character for character, from TITLE or TEXT.\n"
        "3. At most 3 topics. If nothing fits, return an empty list for topics.\n"
        "4. Do not infer what a product can do from the fact that it was cleared or studied.\n"
        "5. Answer with ONE JSON object:\n"
        '{"topics":[{"id":"<topic id>","evidence_quote":"<quote>"}],'
        '"organizations":[{"name":"<published organisation name>","evidence_quote":"<quote>"}],'
        '"summary":"<one sentence, max 200 characters>"}\n'
        "6. No prose before or after the JSON. No markdown fence.\n"
    )


def build_messages(prompt: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]


def extract_json(text: str) -> tuple[Any, str | None]:
    """Return ``(parsed, error)``. Tolerates a model that wraps JSON in prose or a fence.

    Tolerance is bounded on purpose: the object is located by its outer braces and then
    parsed. If that fails the answer is a *measured* JSON failure, not silently repaired.
    """
    import json

    if not text:
        return None, "empty output"
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        return None, "no JSON object found in the output"
    fragment = candidate[start:end + 1]
    try:
        return json.loads(fragment), None
    except ValueError as error:
        return None, f"invalid JSON: {error}"
