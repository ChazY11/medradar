"""One versioned prompt, shared by arms B (untuned) and C (QLoRA-tuned).

Why one prompt
--------------
Arms B and C are meant to differ in one declared way: the checkpoint.  If they
also used different prompts, a difference in score could be a difference in
wording rather than a difference in the model, and the comparison would be
uninterpretable.  So the prompt is built here, from the frozen schema
vocabularies, and both model arms call :func:`build_prompt`.

Why a sha256
------------
Prompt text is an experimental input.  ``TEMPLATE_SHA256`` is recorded alongside
every run so a reader can tell whether two runs that claim to be comparable
really used the same wording.  Editing the template is a protocol amendment and
changes the hash -- which is exactly the point.

Design rules encoded in the prompt
----------------------------------
* the event-category list is closed and comes from ``schema.EVENT_CATEGORIES``
  (it is rendered, not retyped, so it cannot drift from the schema);
* the three timestamps are named separately and the rule "a missing date is
  ``null`` with quality ``"absent"``, never copied from the publication date" is
  stated in so many words (``research/DATA_PROVENANCE.md`` §1);
* evidence is a verbatim quote, never a summary;
* abstention is allowed, with a closed reason list from ``schema.ABSTAIN_REASONS``;
* the answer is JSON and nothing else.

Nothing here calls a model, reads the network or touches a file.  The module is
deterministic and unit-testable.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .schema import (
    ABSTAIN_REASONS,
    EVENT_CATEGORIES,
    TIMESTAMP_FIELDS,
    TIMESTAMP_QUALITIES,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .adapters.base import Prompt
    from .schema import SourceDocument

PROMPT_VERSION = "extract-v1"
DEFAULT_MAX_INPUT_CHARS = 12_000

_TRUNCATION_TEMPLATE = (
    "\n[TRUNCATED: {omitted} characters of the source text were omitted because the "
    "document exceeded the {limit}-character budget. Do not infer anything about the "
    "omitted text; extract only what is visible above.]"
)

_CATEGORY_BLOCK = "\n".join(f"  - {category}" for category in EVENT_CATEGORIES)
_ABSTAIN_BLOCK = "\n".join(f"  - {reason}" for reason in ABSTAIN_REASONS)
_QUALITY_BLOCK = ", ".join(TIMESTAMP_QUALITIES)

SYSTEM_PROMPT = f"""You extract medtech technical-development events from public documents.

Return a single JSON object and nothing else: no prose, no markdown fences, no commentary.

Allowed event categories (this is a closed list; any other value is invalid):
{_CATEGORY_BLOCK}

Three different timestamps exist and they are NOT interchangeable:
- "event_date": the date on which the real-world event happened (for example the day a
  trial began, or the day a regulator granted clearance).
- "published_at": the date on which the source published the document.
- "first_seen_at": the date our own collector first observed the document. This is
  system metadata, not something you infer; use null unless it is supplied to you.

Rules for timestamps:
1. If the document does not state a date for a field, that field's value MUST be null and
   its quality MUST be "absent". Never guess a date.
2. Never copy published_at into event_date. A press release published on one date may
   describe an event that happened months earlier; report the event date the text states.
3. Each timestamp field has a companion quality in "timestamp_quality" whose values must
   be one of: {_QUALITY_BLOCK}. Use "exact_day" for YYYY-MM-DD, "exact_month" for
   YYYY-MM, "exact_year" for YYYY, and "absent" whenever the value is null.

Evidence:
- Every extracted event MUST carry at least one evidence span whose "quote" is copied
  character-for-character from the document text. Do not paraphrase, translate, shorten
  with ellipses, or merge sentences. The quote must support the category, the company and
  the event date you assert.
- If you cannot find a verbatim quote that supports an event, do not assert that event.

Abstention:
- If the document does not describe a target event, return exactly one event object with
  "status": "abstained" and an "abstain_reason" from this closed list:
{_ABSTAIN_BLOCK}

Company identity:
- Use the canonical company id supplied in the prompt metadata / roster hint when the
  document names that company or one of its aliases. Record the text you actually saw in
  "company.raw_text" and the canonical id in "company.canonical_id".
- Do not attribute a subsidiary's or a competitor's event to another company.

Output shape (illustrative; every event object is validated strictly, and unknown keys are
rejected rather than ignored):
{{
  "events": [
    {{
      "client_ref": null,
      "status": "extracted",
      "abstain_reason": null,
      "company": {{"raw_text": "<text seen>", "canonical_id": "<canonical id or null>", "match_basis": "roster_alias_verbatim"}},
      "event_category": "<one value from the closed list>",
      "technology_domains": [],
      "product_or_technology": "<product or null>",
      "event_date": "<YYYY-MM-DD | YYYY-MM | YYYY | null>",
      "published_at": "<YYYY-MM-DD | null>",
      "first_seen_at": null,
      "timestamp_quality": {{"event_date": "exact_day", "published_at": "absent", "first_seen_at": "absent"}},
      "evidence": [{{"quote": "<verbatim substring>", "field": "event_category"}}],
      "rationale": null
    }}
  ]
}}
"""

USER_TEMPLATE = """DOCUMENT METADATA
doc_id: {{DOC_ID}}
source_type: {{SOURCE_TYPE}}
title: {{TITLE}}
publisher: {{PUBLISHER}}
url: {{URL}}
published_at: {{PUBLISHED_AT}}
first_seen_at: {{FIRST_SEEN_AT}}
retrieved_at: {{RETRIEVED_AT}}
company_hint: {{COMPANY_HINT}}

DOCUMENT TEXT
{{TEXT}}

Extract the target events from the document text above. JSON only.
"""

TEMPLATE_SHA256 = hashlib.sha256(
    (SYSTEM_PROMPT + "\x00" + USER_TEMPLATE).encode("utf-8")
).hexdigest()


def truncate_text(text: str, max_input_chars: int = DEFAULT_MAX_INPUT_CHARS) -> tuple[str, bool, int]:
    """Cut ``text`` at the character budget and mark the cut explicitly.

    Returns ``(possibly_truncated_text, was_truncated, omitted_chars)``.  The
    marker is deliberately part of the text handed to the model: a model that is
    silently fed half a document will happily confabulate the rest, and the run
    manifest must be able to show that truncation happened.
    """
    if max_input_chars <= 0:
        raise ValueError("max_input_chars must be positive")
    if len(text) <= max_input_chars:
        return text, False, 0
    omitted = len(text) - max_input_chars
    marker = _TRUNCATION_TEMPLATE.format(omitted=omitted, limit=max_input_chars)
    return text[:max_input_chars] + marker, True, omitted


def _show(value: object) -> str:
    if value is None or value == "":
        return "null"
    return str(value)


def build_prompt(
    document: "SourceDocument",
    *,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    company_hint: str | None = None,
) -> Prompt:
    """Render the one prompt both model arms use, for one document.

    Deterministic: the same document and budget always produce the same Prompt.
    ``max_input_chars`` bounds the *document text*; the truncation marker makes
    the prompt slightly longer than the budget, which is recorded in the
    manifest rather than hidden.
    """
    # Imported here, not at module scope: ``adapters`` imports this module for the
    # prompt version, so a top-level import would be circular.
    from .adapters.base import Prompt

    text, truncated, _omitted = truncate_text(document.text, max_input_chars)
    metadata = dict(document.metadata or {})
    user = (
        USER_TEMPLATE.replace("{{DOC_ID}}", _show(document.doc_id))
        .replace("{{SOURCE_TYPE}}", _show(document.source_type))
        .replace("{{TITLE}}", _show(document.title))
        .replace("{{PUBLISHER}}", _show(document.publisher))
        .replace("{{URL}}", _show(document.url))
        .replace("{{PUBLISHED_AT}}", _show(document.published_at))
        .replace("{{FIRST_SEEN_AT}}", _show(document.first_seen_at))
        .replace("{{RETRIEVED_AT}}", _show(document.retrieved_at))
        .replace("{{COMPANY_HINT}}", _show(company_hint or metadata.get("company_hint")))
        .replace("{{TEXT}}", text)
    )
    return Prompt(
        system=SYSTEM_PROMPT,
        user=user,
        prompt_version=PROMPT_VERSION,
        template_sha256=TEMPLATE_SHA256,
    )


def prompt_fingerprint() -> dict[str, object]:
    """Identity of this prompt, for manifests and reports."""
    return {
        "prompt_version": PROMPT_VERSION,
        "template_sha256": TEMPLATE_SHA256,
        "system_chars": len(SYSTEM_PROMPT),
        "categories": list(EVENT_CATEGORIES),
        "abstain_reasons": list(ABSTAIN_REASONS),
        "timestamp_fields": list(TIMESTAMP_FIELDS),
        "truncation_marker": True,
    }


# The frozen architecture documents refer to the prompt builder as
# ``build_extraction_prompt``; keep that name working so a caller written against
# the contract does not have to know the shorter implementation name.
build_extraction_prompt = build_prompt


__all__ = [
    "DEFAULT_MAX_INPUT_CHARS",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "TEMPLATE_SHA256",
    "USER_TEMPLATE",
    "build_extraction_prompt",
    "build_prompt",
    "prompt_fingerprint",
    "truncate_text",
]
