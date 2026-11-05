"""Gold dataset -> supervised fine-tuning records, with refusals instead of quiet filtering.

What this module refuses to do
------------------------------
A dataset builder is where a project can cheat without noticing: drop the cases
whose label tier is weak, keep the convenient ones, and report a clean harness.
This builder never drops a case silently.  If any case's label tier is not in
``allowed_tiers`` (default: the research-grade tiers), the whole build is refused
and the per-tier counts are reported so a reader can see exactly what would have
been discarded.  The same applies to an empty split, an unassigned case, a case
without a leakage group, or a group that crosses splits.

The record format
-----------------
One record = one document::

    {"case_id": ..., "system": ..., "user": ...,
     "target_json": "<compact JSON of the expected ExtractionResult>",
     "meta": {"label_tier": ..., "group": ..., "split": ...}}

``target_json`` is produced by constructing the *real* contract objects
(``schema.ExtractionResult`` / ``EventExtraction`` / ``EvidenceSpan``) from the
gold events, then serialising with sorted keys and no whitespace.  Reusing the
frozen constructors means a target that could never be scored cannot be built in
the first place.

Two documented conventions
--------------------------
1. ``extractor`` in the target is ``{"system": "human_gold", "adapter_id":
   "gold-label"}``: the target is a label, not a model output.  It is a constant so
   the field cannot be mistaken for a measured model version.
2. ``company.match_basis`` is ``roster_alias_in_document`` when a canonical id is
   present, ``none`` otherwise.  This is a *target-construction convention* (the
   human label was reached from the document and the roster), not a measured claim
   about how any matcher behaved.  The convention is recorded here once instead of
   being re-invented per script.

Prompt source
-------------
The prompt is deliberately owned by ``prompting.py`` (one versioned prompt shared
by arms B and C).  This module imports ``build_extraction_prompt`` lazily and falls
back to a *clearly labelled provisional* prompt only when that module or function
is unavailable (the fallback's system text says so).  A ``TypeError`` from a
signature change also falls back rather than crashing a dataset build.  No model
library is imported anywhere on this path.

Never imported here: ``torch``, ``transformers``, ``peft``, ``bitsandbytes``,
``datasets``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import RESEARCH_GRADE_TIERS
from ..schema import (
    EVENT_CATEGORIES,
    SCHEMA_VERSION,
    ContractError,
    EntityClaim,
    EventExtraction,
    EvidenceSpan,
    ExtractionResult,
    ExtractorProvenance,
    SourceDocument,
    TimestampQuality,
)

GOLD_SYSTEM = "human_gold"
GOLD_ADAPTER_ID = "gold-label"

SPLITS: tuple[str, ...] = ("train", "validation", "test")

FALLBACK_PROMPT_VERSION = "provisional-fallback-v0-not-preregistered"


class DataNotReady(RuntimeError):
    """The dataset cannot be turned into a training bundle, and here is why."""

    def __init__(self, reasons: tuple[str, ...], *, rejected: Mapping[str, int] | None = None) -> None:
        self.reasons = tuple(reasons)
        self.rejected = dict(rejected or {})
        super().__init__("dataset is not ready for training: " + "; ".join(self.reasons))


class _CaseDefect(ValueError):
    """One case cannot be converted to a record; collected into a DataNotReady."""


@dataclass(frozen=True)
class SFTBundle:
    """Deterministic bundle of training records plus the accounting of what was excluded."""

    train: tuple[dict, ...]
    validation: tuple[dict, ...]
    test: tuple[dict, ...]
    counts: Mapping[str, int]
    sha256: str
    rejected: Mapping[str, int]
    allowed_tiers: tuple[str, ...]
    label_tiers: tuple[str, ...]
    manifest_name: str
    manifest_version: str

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": dict(self.counts),
            "sha256": self.sha256,
            "rejected": dict(self.rejected),
            "allowed_tiers": list(self.allowed_tiers),
            "label_tiers": list(self.label_tiers),
            "manifest": {"name": self.manifest_name, "version": self.manifest_version},
        }


# ------------------------------------------------------------------------- prompts
def _provisional_prompt(document: SourceDocument) -> dict[str, str]:
    """Documented fallback used only when ``prompting.build_extraction_prompt`` is unavailable."""
    system = (
        "You extract structured medtech technical-development events from one public document. "
        "Reply with one JSON object only: the MedRadar event_extraction v1 ExtractionResult for "
        "this document. Quote evidence verbatim from the document. Never invent a company, a "
        "date, or an event; use status 'abstained' with an abstain_reason when the document does "
        "not assert an event. This is a PROVISIONAL FALLBACK PROMPT "
        f"({FALLBACK_PROMPT_VERSION}); it is not the pre-registered prompt."
    )
    lines = [
        f"doc_id: {document.doc_id}",
        f"source_type: {document.source_type}",
        f"title: {document.title or ''}",
        f"published_at: {document.published_at or ''}",
        "",
        "DOCUMENT TEXT:",
        document.text,
    ]
    return {"system": system, "user": "\n".join(lines)}


def _import_prompt_builder() -> Callable[..., Any] | None:
    """Lazily import the shared prompt builder; ``None`` when it does not exist yet.

    The name this module was written against is ``build_extraction_prompt``; the
    prompt module shipped with the benchmark calls it ``build_prompt``, so both are
    tried in that order and the mismatch is reported rather than papered over.
    Nothing here imports a model library.
    """
    try:
        from .. import prompting  # noqa: PLC0415  (deliberate lazy import)
    except ImportError:
        return None
    for name in ("build_extraction_prompt", "build_prompt"):
        candidate = getattr(prompting, name, None)
        if callable(candidate):
            return candidate
    return None


def _coerce_prompt(rendered: Any) -> tuple[str, str]:
    """Accept the shapes a prompt builder may return: ``.system``/``.user``, mapping, or pair."""
    if hasattr(rendered, "system") and hasattr(rendered, "user"):
        return str(rendered.system), str(rendered.user)
    if isinstance(rendered, Mapping) and "system" in rendered and "user" in rendered:
        return str(rendered["system"]), str(rendered["user"])
    if isinstance(rendered, (tuple, list)) and len(rendered) == 2:
        return str(rendered[0]), str(rendered[1])
    raise TypeError(f"prompt builder returned an unsupported shape: {type(rendered).__name__}")


def _render_prompt(
    document: SourceDocument, prompt_builder: Callable[..., Any] | None
) -> tuple[str, str]:
    builder = prompt_builder if prompt_builder is not None else _import_prompt_builder()
    if builder is not None:
        try:
            return _coerce_prompt(builder(document))
        except TypeError:
            # Signature drift in prompting.py must not break a dataset build; the
            # fallback is labelled as provisional in its own system text.
            pass
    fallback = _provisional_prompt(document)
    return fallback["system"], fallback["user"]


# -------------------------------------------------------------------- target build
def _quality_for_date(value: str | None) -> str:
    """Timestamp quality from the *shape* of a stored value (never guesses a missing one)."""
    if value is None:
        return "absent"
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return "exact_day"
    if len(text) == 7 and text[4] == "-":
        return "exact_month"
    if len(text) == 4 and text.isdigit():
        return "exact_year"
    return "approximate"


def _build_target(case: Any) -> dict:
    """Build the expected ``ExtractionResult.to_dict()`` payload for one case."""
    channel = []
    for index, gold in enumerate(getattr(case, "gold_events", ()) or ()):
        category = getattr(gold, "event_category", None)
        if category not in EVENT_CATEGORIES:
            raise _CaseDefect(
                f"case {getattr(case, 'case_id', '?')!r} gold event {index} has event_category "
                f"{category!r} which is not in the pre-registered vocabulary"
            )
        quote = getattr(gold, "evidence_quote", None)
        if not quote or not str(quote).strip():
            raise _CaseDefect(
                f"case {getattr(case, 'case_id', '?')!r} gold event {index} has no evidence_quote; "
                "an extracted event must carry a verbatim span, so the target cannot be built"
            )
        event_date = getattr(gold, "event_date", None)
        published_at = getattr(gold, "published_at", None)
        canonical_id = getattr(gold, "company_canonical_id", None)
        try:
            event = EventExtraction(
                client_ref=f"{getattr(case, 'case_id', '?')}-{index}",
                status="extracted",
                company=EntityClaim(
                    raw_text=canonical_id,
                    canonical_id=canonical_id,
                    match_basis="roster_alias_in_document" if canonical_id else "none",
                ),
                event_category=category,
                technology_domains=tuple(getattr(gold, "technology_domains", ()) or ()),
                product_or_technology=getattr(gold, "product_or_technology", None),
                event_date=event_date,
                published_at=published_at,
                first_seen_at=None,
                timestamp_quality=TimestampQuality(
                    event_date=_quality_for_date(event_date),
                    published_at=_quality_for_date(published_at),
                    first_seen_at="absent",
                ),
                evidence=(EvidenceSpan(quote=str(quote), field="event"),),
            )
        except ContractError as exc:
            raise _CaseDefect(
                f"case {getattr(case, 'case_id', '?')!r} gold event {index} violates the event "
                f"contract: {exc}"
            ) from exc
        channel.append(event)

    result = ExtractionResult(
        doc_id=str(getattr(getattr(case, "document", None), "doc_id", getattr(case, "case_id", "?"))),
        parse_status="ok",
        extractor=ExtractorProvenance(system=GOLD_SYSTEM, adapter_id=GOLD_ADAPTER_ID),
        events=tuple(channel),
    )
    return result.to_dict()


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bundle_sha256(splits: Mapping[str, tuple[dict, ...]]) -> str:
    digest = hashlib.sha256()
    digest.update(
        _compact_json(
            {split: [dict(record) for record in records] for split, records in splits.items()}
        ).encode("utf-8")
    )
    return digest.hexdigest()


# ------------------------------------------------------------------------ builder
def build_sft_records(
    manifest: Any,
    *,
    allowed_tiers: tuple[str, ...] | list[str] = RESEARCH_GRADE_TIERS,
    prompt_builder: Callable[..., Any] | None = None,
) -> SFTBundle:
    """Turn a :class:`contracts.DatasetManifest`-shaped object into an SFT bundle.

    Refuses (raises :class:`DataNotReady` with every reason found, not just the
    first) when: there is no manifest, no cases, a case tier is not allowed, a
    split is empty, a case is unassigned, a case has no leakage group, a group
    crosses splits, or a gold event cannot form a contracted target.
    """
    if manifest is None:
        raise DataNotReady(("no dataset manifest supplied",))

    allowed = tuple(allowed_tiers)
    cases = tuple(getattr(manifest, "cases", ()) or ())
    reasons: list[str] = []
    if not cases:
        raise DataNotReady(("the dataset contains no cases",))

    tier_counts: dict[str, int] = {}
    for case in cases:
        tier = str(getattr(case, "label_tier", "unlabelled"))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    rejected = {tier: count for tier, count in sorted(tier_counts.items()) if tier not in allowed}
    for tier, count in rejected.items():
        reasons.append(
            f"{count} case(s) have label tier {tier!r}, which is not in the allowed tiers "
            f"{list(allowed)}; they were rejected rather than silently dropped"
        )

    by_split: dict[str, list[Any]] = {split: [] for split in SPLITS}
    for case in cases:
        split = str(getattr(case, "split", ""))
        if split not in SPLITS:
            reasons.append(
                f"case {getattr(case, 'case_id', '?')!r} has split {split!r}; only {list(SPLITS)} "
                "may appear in a training bundle (unassigned cases are not guessable)"
            )
            continue
        by_split[split].append(case)

    for split in SPLITS:
        if not by_split[split]:
            reasons.append(f"the {split!r} split is empty; every split must carry cases")

    group_splits: dict[str, set[str]] = {}
    cases_without_group: list[str] = []
    for case in cases:
        group = str(getattr(case, "group", "") or "").strip()
        split = str(getattr(case, "split", ""))
        if not group:
            cases_without_group.append(str(getattr(case, "case_id", "?")))
            continue
        group_splits.setdefault(group, set()).add(split)
    if cases_without_group:
        reasons.append(
            f"{len(cases_without_group)} case(s) have no leakage group (e.g. "
            f"{cases_without_group[0]!r}); grouped splitting is required, so leakage cannot be excluded"
        )
    crossing = {group: sorted(splits) for group, splits in group_splits.items() if len(splits) > 1}
    if crossing:
        sample = ", ".join(f"{group!r} in {splits}" for group, splits in sorted(crossing.items())[:3])
        reasons.append(
            f"{len(crossing)} leakage group(s) cross splits ({sample}); a group must live in exactly one split"
        )

    if reasons:
        raise DataNotReady(tuple(reasons), rejected=rejected)

    rendered_splits: dict[str, list[dict]] = {split: [] for split in SPLITS}
    for split in SPLITS:
        for case in by_split[split]:
            try:
                target = _build_target(case)
                system, user = _render_prompt(case.document, prompt_builder)
            except _CaseDefect as exc:
                raise DataNotReady((str(exc),), rejected=rejected) from exc
            rendered_splits[split].append(
                {
                    "case_id": str(getattr(case, "case_id", "?")),
                    "system": system,
                    "user": user,
                    "target_json": _compact_json(target),
                    "meta": {
                        "label_tier": str(getattr(case, "label_tier", "unlabelled")),
                        "group": str(getattr(case, "group", "")),
                        "split": split,
                    },
                }
            )

    frozen = {split: tuple(records) for split, records in rendered_splits.items()}
    return SFTBundle(
        train=frozen["train"],
        validation=frozen["validation"],
        test=frozen["test"],
        counts={split: len(frozen[split]) for split in SPLITS},
        sha256=_bundle_sha256(frozen),
        rejected=rejected,
        allowed_tiers=allowed,
        label_tiers=tuple(sorted(tier_counts)),
        manifest_name=str(getattr(manifest, "name", "unnamed")),
        manifest_version=str(getattr(manifest, "version", "unversioned")),
    )


# ------------------------------------------------------- development manifest loader
def manifest_from_dict(payload: Any) -> Any:
    """Build a :class:`contracts.DatasetManifest` from JSON for CLI use.

    This is a *development* loader for hand-built fixtures.  A production dataset
    loader belongs in ``datasets/`` (WP4) and must hash its sources; nothing here
    fabricates a source hash -- an absent ``source_sha256`` stays absent.
    """
    from ..contracts import DatasetCase, DatasetManifest, GoldEvent  # local: keeps import surface small

    if not isinstance(payload, Mapping):
        raise DataNotReady((f"dataset manifest must be a JSON object, got {type(payload).__name__}",))
    reasons: list[str] = []
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise DataNotReady(("dataset manifest has no 'cases' list",))

    cases: list[Any] = []
    for index, raw_case in enumerate(raw_cases):
        where = f"cases[{index}]"
        if not isinstance(raw_case, Mapping):
            reasons.append(f"{where} must be an object")
            continue
        try:
            document = SourceDocument(**_document_kwargs(raw_case.get("document"), where))
        except (ContractError, TypeError, KeyError) as exc:
            reasons.append(f"{where}.document is invalid: {exc}")
            continue
        gold_events: list[Any] = []
        raw_events = raw_case.get("gold_events") or []
        if not isinstance(raw_events, list):
            reasons.append(f"{where}.gold_events must be a list")
            continue
        for event_index, raw_event in enumerate(raw_events):
            if not isinstance(raw_event, Mapping):
                reasons.append(f"{where}.gold_events[{event_index}] must be an object")
                continue
            try:
                gold_events.append(
                    GoldEvent(
                        event_id=str(raw_event["event_id"]),
                        company_canonical_id=raw_event.get("company_canonical_id"),
                        event_category=str(raw_event["event_category"]),
                        event_date=raw_event.get("event_date"),
                        published_at=raw_event.get("published_at"),
                        product_or_technology=raw_event.get("product_or_technology"),
                        technology_domains=tuple(raw_event.get("technology_domains") or ()),
                        evidence_quote=raw_event.get("evidence_quote"),
                        label_tier=raw_event.get("label_tier", raw_case.get("label_tier", "unlabelled")),
                        label_source=raw_event.get("label_source"),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                reasons.append(f"{where}.gold_events[{event_index}] is invalid: {exc}")
        try:
            cases.append(
                DatasetCase(
                    case_id=str(raw_case["case_id"]),
                    document=document,
                    gold_events=tuple(gold_events),
                    expected_abstain=bool(raw_case.get("expected_abstain", False)),
                    label_tier=str(raw_case.get("label_tier", "unlabelled")),
                    group=str(raw_case.get("group", "")),
                    split=str(raw_case.get("split", "unassigned")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(f"{where} is invalid: {exc}")

    if reasons:
        raise DataNotReady(tuple(reasons))
    source_paths = tuple(str(path) for path in payload.get("source_paths") or ())
    return DatasetManifest(
        name=str(payload.get("name", "unnamed")),
        version=str(payload.get("version", "unversioned")),
        cases=tuple(cases),
        source_paths=source_paths,
        source_sha256=payload.get("source_sha256"),
        notes=payload.get("notes"),
    )


def _document_kwargs(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}.document must be an object")
    known = {
        "doc_id",
        "source_type",
        "text",
        "title",
        "published_at",
        "first_seen_at",
        "retrieved_at",
        "url",
        "publisher",
    }
    kwargs = {key: raw[key] for key in known if key in raw}
    kwargs["metadata"] = dict(raw.get("metadata") or {})
    return kwargs


def load_manifest(path: str | Path) -> Any:
    """Read a manifest JSON file; raises :class:`DataNotReady` with a readable reason."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise DataNotReady((f"cannot read dataset manifest {str(source)!r}: {exc}",)) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataNotReady((f"dataset manifest {str(source)!r} is not valid UTF-8 JSON: {exc}",)) from exc
    return manifest_from_dict(payload)


__all__ = [
    "FALLBACK_PROMPT_VERSION",
    "GOLD_ADAPTER_ID",
    "GOLD_SYSTEM",
    "SPLITS",
    "DataNotReady",
    "SFTBundle",
    "build_sft_records",
    "load_manifest",
    "manifest_from_dict",
]
