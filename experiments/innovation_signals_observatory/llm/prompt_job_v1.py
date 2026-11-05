"""The single versioned prompt family for the job-text extraction (arm B).

Why one prompt family
---------------------
Arm B (untuned Qwen3-4B) is the only model arm that runs here; arm C is NOT_RUN
because the only existing QLoRA adapter was trained on regulatory-event text with
an incompatible schema (see ``docs/LLM_EXPERIMENT.md`` §Arms).  Even so the prompt
is versioned and hashed, because prompt wording is an experimental input: a later
run that uses different wording must not be compared to this one silently.

The prompt is rendered from the closed vocabularies, not retyped
--------------------------------------------------------------
* Function classes and their definitions come from
  ``config/recruitment_function_classes.json`` (the same data the deterministic A
  arm uses), so the model and the rules see one label set.
* Technology tracks and their keyword families come from
  ``config/tracks_device.json`` (the existing device taxonomy).  The prompt lists
  the ids and signature keywords; an id outside that list is a schema error.
* Class/track block text and both configuration file SHA-256s are recorded in the
  prompt fingerprint and in every run manifest.  If the vocabulary changes, the
  fingerprint changes and the run is visibly a different input.

Design rules stated in the prompt (each one exists because of a measured failure)
---------------------------------------------------------------------------------
1. JSON only, exact shape, no markdown (the harness still strips one fence, but a
   model that produces fenced prose is being measured, not accommodated).
2. **Every claim carries a verbatim quote.**  The quote is copied
   character-for-character from the posting; paraphrases fail the locatability
   check.  A label without a quote cannot be represented by the schema.
3. **Abstention is explicitly correct** for postings with no technical content,
   and UNCLASSIFIED is explicitly correct when no track is evidenced.  This is
   the negative-control defence: PR #20 measured negative-control false positives
   *rising* from 0.000 (B) to 0.667 (C) after fine-tuning because abstention was
   not in the training data.  The untuned model is told abstention exists.
4. **No technology invention.**  The track list is closed; the model may not name
   a technology that is not in the list or not in the posting.  A device keyword
   belonging to the company's product line is not evidence for a commercial role.
5. **The track gate**: a technical track may only accompany an R&D/engineering
   function class; commercial/administrative postings must emit UNCLASSIFIED track.
6. Long postings are truncated at a declared character budget with an explicit
   ``[TRUNCATED: ...]`` marker inside the text, and a model that reports something
   from the omitted part is mismeasuring; truncation is recorded per item.

Nothing here calls a model, opens a socket or writes a file at import time.
"""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from experiments.local_llm_event_extraction.adapters.base import Prompt

from .job_text_schema import (
    ABSTAIN_REASONS,
    DEFAULT_TRACKS_CONFIG,
    FUNCTION_CLASSES,
    MAX_CAPABILITY_PHRASES,
    MAX_QUOTE_CHARS,
    TRACK_FIELD_UNCLASSIFIED,
    UNCLASSIFIED,
    load_track_registry,
)

PROMPT_VERSION = "job-extract-v2"
PROMPT_MAX_CAPABILITY_PHRASES = 2
"""Prompt family version.  ``v1 -> v2`` is a pre-recorded amendment made *before*
the delivered run, after a measured output-budget failure: with up to 4 capability
phrases the model's JSON regularly exceeded a 280-token output cap and was cut
mid-array (3 of the first 3 items). v2 asks for at most **2** capability phrases
and explicitly instructs the model to drop optional phrases rather than truncate
the JSON; the schema still accepts up to 4, so the contract is unchanged."""
DEFAULT_MAX_INPUT_CHARS = 3_000
"""Declared description-character budget, applied identically to both arms.

Postings in the snapshot are 2.5k-18k characters (median 5 722).  The budget was
reduced twice for a *measured* deployment reason, and both reductions are
disclosed rather than presented as a design choice:

* 8 000 chars (~5.2k-token prompt): PyTorch's SDPA path allocated quadratic
  attention buffers, the Windows/WDDM driver began paging, and one item did not
  finish in 15 minutes.
* 5 000 chars: worked (median ~25 s, peak ~12.2 GB of 16.3 GB) but the per-item
  tail exploded — measured 26 s, 60 s, 133 s, 204 s, 185 s across nine items,
  unrelated to output length.  The card could not deliver 42 items in a usable
  window; the 4B model under this stack is not a predictable-latency component.
* **3 000 chars** (final, declared): chosen so the full run finishes inside the
  delivery window.  The latency tail is itself reported as a finding, not hidden.

Arm A receives exactly the same truncated description text (with the same in-band
marker) so the A/B comparison is on identical visible input.  Truncation and any
per-item TIMEOUT are recorded per item in the manifest and predictions."""

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FUNCTION_CLASSES_CONFIG = _REPO_ROOT / "config" / "recruitment_function_classes.json"

_TRUNCATION_MARKER = (
    "\n[TRUNCATED: {omitted} characters of this job description were omitted because "
    "the posting exceeded the {limit}-character budget. Do not infer anything about the "
    "omitted text.]"
)

#: Fallback definitions used only when the committed function-class config cannot
#: be read (e.g. an isolated copy of this package).  Kept deliberately short; the
#: fingerprint records which source was used.
_FALLBACK_CLASS_NOTES: Mapping[str, str] = {
    "CORE_R&D": "Discovers/develops technology: research scientists and R&D engineers on new concepts, prototypes, materials, algorithms or processes.",
    "CLINICAL_R&D": "Generates clinical evidence: trial design/operations, clinical science, biostatistics, medical affairs.",
    "PRODUCT_ENGINEERING": "Turns technology into a released product: product/design/development, systems, test, verification, design assurance.",
    "ALGORITHM_SOFTWARE": "Writes and ships software: application/platform/cloud/DevOps, embedded/firmware, data and ML engineering, algorithms.",
    "HARDWARE_SYSTEMS": "Designs physical electronics and system hardware: electrical/electronic, PCB, sensors, power, optics, reliability.",
    "MANUFACTURING_PROCESS": "Runs and improves production: manufacturing/process/production, equipment and maintenance engineering, lean/Six Sigma, tooling.",
    "QUALITY_REGULATORY": "Assures quality and regulatory compliance: quality engineering/systems, regulatory affairs, audits, CAPA, post-market.",
    "SALES_ADMIN_OTHER": "Commercial, field clinical/technical support, marketing, training, finance, supply chain, administration, operators (not R&D).",
    "UNCLASSIFIED": "No rule/model decision: the evidence is absent or contradictory. A legitimate research outcome, counted, never filled in.",
}


# ------------------------------------------------------------------- rendering
def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _read_function_classes(
    config_path: str | Path | None = None,
) -> tuple[dict[str, dict[str, Any]], str, str | None]:
    """``(classes, source, sha256)`` for the function-class vocabulary."""
    path = Path(config_path) if config_path is not None else DEFAULT_FUNCTION_CLASSES_CONFIG
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        classes = dict(payload.get("classes") or {})
    except (OSError, json.JSONDecodeError):
        classes = {}
    if not classes:
        return (
            {name: {"name_en": name, "definition_en": _FALLBACK_CLASS_NOTES.get(name, "")} for name in FUNCTION_CLASSES},
            "embedded_fallback",
            None,
        )
    return classes, f"config/{path.name}", _sha256_file(path)


def _first_sentence(text: str, *, max_chars: int = 150) -> str:
    stripped = " ".join(str(text or "").split())
    if not stripped:
        return ""
    for marker in (". ", "; "):
        index = stripped.find(marker)
        if 0 < index < max_chars:
            return stripped[: index + 1]
    return stripped[:max_chars]


def _render_function_block(classes: Mapping[str, Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for name in FUNCTION_CLASSES:
        spec = classes.get(name) or {}
        definition = _first_sentence(str(spec.get("definition_en") or spec.get("name_en") or ""))
        if name == UNCLASSIFIED:
            definition = str(spec.get("definition_en") or _FALLBACK_CLASS_NOTES[name])
            definition = _first_sentence(definition)
        lines.append(f"  - {name}: {definition}")
    return "\n".join(lines)


def _render_track_block(tracks: Mapping[str, Mapping[str, Any]]) -> str:
    if not tracks:
        return (
            "  (the technology-track vocabulary is unavailable in this run: always emit "
            f"{TRACK_FIELD_UNCLASSIFIED!r} for technology_track)"
        )
    lines: list[str] = []
    for track_id in sorted(tracks):
        spec = tracks[track_id]
        name = str(spec.get("name_en") or track_id)
        keywords = list(spec.get("keywords") or ()) + list(spec.get("frontier_keywords") or ())
        # Two signature keywords only: enough to anchor the id, bounded prompt size
        # (the full 50-track keyword table tripled the system prompt and caused the
        # measured VRAM/latency problem documented at DEFAULT_MAX_INPUT_CHARS).
        shown = ", ".join(keywords[:2])
        lines.append(f"  - {track_id} ({name}; e.g. {shown})" if shown else f"  - {track_id} ({name})")
    return "\n".join(lines)


@functools.lru_cache(maxsize=8)
def _system_prompt_cached(
    function_config: str | None, tracks_config: str | None
) -> tuple[str, dict[str, Any]]:
    classes, class_source, class_sha = _read_function_classes(function_config)
    tracks = load_track_registry(tracks_config)
    track_ids = sorted(tracks)
    track_sha = _sha256_file(Path(tracks_config)) if tracks_config else _sha256_file(DEFAULT_TRACKS_CONFIG)

    abstain_block = "\n".join(f"  - {reason}" for reason in ABSTAIN_REASONS)
    system = f"""You are a deterministic information extractor for medical-technology job postings.
You read ONE public job posting and return ONE JSON object and nothing else: no prose, no
markdown fences, no commentary.

TASK
Classify the posting's job function, name the technology track it evidences (using ONLY the
closed list below), list up to {PROMPT_MAX_CAPABILITY_PHRASES} capability phrases, and say whether the
posting shows actual research/development work. Every label you assert must be backed by a
verbatim quote copied from the posting text.

FUNCTION CLASSES (closed list; any other value is invalid):
{_render_function_block(classes)}

TECHNOLOGY TRACKS (closed list; any other value is invalid):
{_render_track_block(tracks)}

RULES
1. function_class must be one value from the closed function list. A role that performs
   research/engineering work gets an R&D/engineering class; a commercial, marketing, sales,
   field-clinical-support, financial, supply-chain, administrative or production-operator role
   gets SALES_ADMIN_OTHER. If the text does not let you decide, use {UNCLASSIFIED}.
2. technology_track must be one of the listed ids, or {TRACK_FIELD_UNCLASSIFIED!r}. Use a track
   only when the posting's own text names the technology (a product area the company merely
   sells is NOT evidence: a sales advert's product names are commercial context, not a
   technology direction). If function_class is SALES_ADMIN_OTHER or {UNCLASSIFIED}, or if no
   listed track is clearly evidenced, emit {TRACK_FIELD_UNCLASSIFIED!r}.
3. EVIDENCE IS A QUOTE, NOT A SUMMARY. For every asserted function_class, technology_track and
   r_and_d_evidence=true, copy the supporting sentence or phrase character-for-character from
   the posting text into the matching *_evidence_quote field. Do not paraphrase, translate,
   shorten with "...", merge non-adjacent sentences, or invent a quote. A quote must be
   {MAX_QUOTE_CHARS} characters or fewer.
4. If the posting contains no technical content at all (for example a Buyer/Planner, customer
   service, warehouse, administrative or non-technical co-op posting), set "abstain": true,
   "abstain_reason": "no_technical_content", function_class {UNCLASSIFIED!r},
   technology_track {TRACK_FIELD_UNCLASSIFIED!r}, an empty capability_phrases list, and
   "r_and_d_evidence": false. Do not force a technical story onto a non-technical advert.
   If the posting is clearly non-technical but its commercial function is explicit, you may
   instead answer with function_class "SALES_ADMIN_OTHER" (quoting the commercial phrase) and
   technology_track {TRACK_FIELD_UNCLASSIFIED!r}. Never emit an R&D function class or a
   technology track for such a posting.
5. abstain_reason is one of these values when abstain is true, and null otherwise:
{abstain_block}
6. capability_phrases: 0 to {PROMPT_MAX_CAPABILITY_PHRASES} items, each {{"text": "<short
   capability label, at most 160 chars>", "evidence_quote": "<verbatim supporting span>"}}. Only
   include a capability the posting actually requires; an empty list is correct when nothing is
   named. Keep the whole JSON answer compact (about 200 tokens): if you run out of room, DROP
   optional capability phrases rather than leaving the JSON incomplete. A complete short answer
   is required; a truncated object is a failure.
7. r_and_d_evidence is true only when the posting describes actual development work (e.g.
   designing, prototyping, validating, testing new devices, algorithms or processes), and then
   r_and_d_evidence_quote must quote it. Routine sales, quality or production support is not R&D.
8. uncertainty_note: one short sentence (or null) if the evidence is genuinely ambiguous. It is
   NOT a confidence score; do not emit any numeric probability or confidence field.
9. If the description contains a [TRUNCATED: ...] marker, extract only what is visible above the
   marker; never infer content from the omitted part.
10. Output exactly this JSON shape (null where a field does not apply):
{{
  "abstain": false,
  "abstain_reason": null,
  "function_class": "PRODUCT_ENGINEERING",
  "function_evidence_quote": "<verbatim span>",
  "technology_track": "structural_heart",
  "track_evidence_quote": "<verbatim span>",
  "capability_phrases": [{{"text": "<label>", "evidence_quote": "<verbatim span>"}}],
  "r_and_d_evidence": true,
  "r_and_d_evidence_quote": "<verbatim span>",
  "uncertainty_note": null
}}
"""
    fingerprint = {
        "prompt_version": PROMPT_VERSION,
        "system_chars": len(system),
        "function_classes_source": class_source,
        "function_classes_sha256": class_sha,
        "tracks_source": f"config/{Path(tracks_config or DEFAULT_TRACKS_CONFIG).name}",
        "tracks_sha256": track_sha,
        "n_function_classes": len(FUNCTION_CLASSES),
        "n_tracks": len(track_ids),
        "track_ids": track_ids,
    }
    return system, fingerprint


def system_prompt(
    *,
    function_config: str | Path | None = None,
    tracks_config: str | Path | None = None,
) -> str:
    """The rendered system prompt for the declared vocabulary (deterministic given inputs)."""
    return _system_prompt_cached(
        str(function_config) if function_config is not None else None,
        str(tracks_config) if tracks_config is not None else None,
    )[0]


USER_TEMPLATE = """JOB POSTING METADATA
posting_id: {{POSTING_ID}}
job_title: {{JOB_TITLE}}
location: {{LOCATION}}
source_posted_at: {{SOURCE_POSTED_AT}}

JOB DESCRIPTION
{{TEXT}}

Return the single JSON object for the job posting above. JSON only.
"""


def truncate_description(
    text: str, max_input_chars: int = DEFAULT_MAX_INPUT_CHARS
) -> tuple[str, bool, int]:
    """Cut the description at the declared budget and mark the cut in-band.

    Returns ``(text, was_truncated, omitted_chars)``.  The marker is *inside* the
    text the model sees: silently feeding half a posting and then scoring the
    result would measure the harness, not the model.
    """
    if max_input_chars <= 0:
        raise ValueError("max_input_chars must be positive")
    if len(text) <= max_input_chars:
        return text, False, 0
    omitted = len(text) - max_input_chars
    return (
        text[:max_input_chars] + _TRUNCATION_MARKER.format(omitted=omitted, limit=max_input_chars),
        True,
        omitted,
    )


def _hash_parts(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def template_sha256(
    *,
    function_config: str | Path | None = None,
    tracks_config: str | Path | None = None,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
) -> str:
    """Hash of the exact rendered template a run uses (system + user + budget)."""
    system, fingerprint = _system_prompt_cached(
        str(function_config) if function_config is not None else None,
        str(tracks_config) if tracks_config is not None else None,
    )
    return _hash_parts(
        PROMPT_VERSION,
        system,
        USER_TEMPLATE,
        str(int(max_input_chars)),
        str(fingerprint.get("tracks_sha256")),
        str(fingerprint.get("function_classes_sha256")),
    )


def build_job_prompt(
    posting: Mapping[str, Any],
    *,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    function_config: str | Path | None = None,
    tracks_config: str | Path | None = None,
) -> tuple[Prompt, dict[str, Any]]:
    """Render the prompt for one posting.

    Returns ``(prompt, item_meta)`` where ``item_meta`` records the declared
    budget, whether truncation happened and how many characters were omitted --
    all of which the manifest and every prediction carry.
    """
    description = str(posting.get("job_description") or "")
    text, truncated, omitted = truncate_description(description, max_input_chars)
    shown = lambda value: "null" if value in (None, "") else str(value)  # noqa: E731
    user = (
        USER_TEMPLATE.replace("{{POSTING_ID}}", shown(posting.get("posting_id")))
        .replace("{{JOB_TITLE}}", shown(posting.get("job_title")))
        .replace("{{LOCATION}}", shown(posting.get("job_location")))
        .replace("{{SOURCE_POSTED_AT}}", shown(posting.get("source_posted_at")))
        .replace("{{TEXT}}", text)
    )
    system, _fingerprint = _system_prompt_cached(
        str(function_config) if function_config is not None else None,
        str(tracks_config) if tracks_config is not None else None,
    )
    prompt = Prompt(
        system=system,
        user=user,
        prompt_version=PROMPT_VERSION,
        template_sha256=template_sha256(
            function_config=function_config,
            tracks_config=tracks_config,
            max_input_chars=max_input_chars,
        ),
    )
    return prompt, {
        "max_input_chars": int(max_input_chars),
        "description_chars": len(description),
        "prompt_description_chars": len(text),
        "truncated": bool(truncated),
        "omitted_chars": int(omitted),
    }


def prompt_fingerprint(
    *,
    function_config: str | Path | None = None,
    tracks_config: str | Path | None = None,
) -> dict[str, Any]:
    """Identity of the prompt input, for manifests."""
    _system, fingerprint = _system_prompt_cached(
        str(function_config) if function_config is not None else None,
        str(tracks_config) if tracks_config is not None else None,
    )
    payload = dict(fingerprint)
    payload["default_max_input_chars"] = DEFAULT_MAX_INPUT_CHARS
    payload["template_sha256"] = template_sha256(
        function_config=function_config, tracks_config=tracks_config
    )
    payload["user_template_sha256"] = hashlib.sha256(USER_TEMPLATE.encode("utf-8")).hexdigest()
    return payload


__all__ = [
    "DEFAULT_MAX_INPUT_CHARS",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "USER_TEMPLATE",
    "build_job_prompt",
    "prompt_fingerprint",
    "system_prompt",
    "template_sha256",
    "truncate_description",
]

#: Backwards-friendly lazy constant for readers who expect it (the existing event
#: harness exposes ``SYSTEM_PROMPT`` similarly).  Rendering the vocabulary costs a
#: file read, so it is computed on first access rather than at import time.
def __getattr__(name: str) -> Any:  # pragma: no cover - trivial lazy accessor
    if name == "SYSTEM_PROMPT":
        return system_prompt()
    raise AttributeError(name)
