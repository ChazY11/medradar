"""Supervised fine-tuning records for the overnight exploratory QLoRA run.

What this builder will not do
-----------------------------
* It will not call a model to label data.  Every target is constructed from the
  dataset's own silver events.
* It will not ship a target that the *evaluation validator* would reject.  Each
  constructed target is run through :func:`validation.validator.validate_extraction`
  at build time; a target that comes back quarantined is a builder bug and the
  case is refused, with the reason counted.  A training target that could not be
  scored would teach the model exactly the behaviour the metric penalises.
* It will not silently drop a case.  Refusals are returned as a per-reason count.

Target shape
------------
The target is the object the prompt asks for::

    {"events": [ { ... one or more event objects ... } ]}

with sorted keys and no whitespace, so the same fixture always tokenises to the
same completion.  ``extractor``/``doc_id``/``schema_version`` are deliberately
*not* in the target: the prompt's illustrative output shape does not contain
them, and a model that produced them would be imitating a harness artefact
rather than performing the task.

Label provenance
----------------
Every record carries ``label_tier`` (``source_record_derived``) and
``text_origin`` (``structural_rendering`` | ``synthetic_narrative``) plus the
prompt/template hashes, so a trained adapter can be traced to the exact data and
prompt that produced it.  The bundle is stamped
``EXPLORATORY_WEAK_SUPERVISION`` -- not ``RESEARCH_GRADE``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import DatasetCase, DatasetManifest
from ..prompting import PROMPT_VERSION, build_prompt, render_template_sha256
from ..schema import (
    EntityClaim,
    EventExtraction,
    EvidenceSpan,
    ExtractionResult,
    ExtractorProvenance,
    SCHEMA_VERSION,
    TimestampQuality,
)
from ..validation.entities import EntityRoster, Taxonomy
from ..validation.validator import validate_extraction

BUNDLE_TIER = "EXPLORATORY_WEAK_SUPERVISION"
GOLD_SYSTEM = "source_record_silver"
GOLD_ADAPTER_ID = "silver-label"


@dataclass(frozen=True)
class SFTRecord:
    case_id: str
    split: str
    prompt_version: str
    template_sha256: str
    system: str
    user: str
    target_json: str
    label_tier: str
    text_origin: str
    source_type: str
    group: str
    event_date_kind: str
    abstained: bool

    def to_meta(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "split": self.split,
            "prompt_version": self.prompt_version,
            "template_sha256": self.template_sha256,
            "label_tier": self.label_tier,
            "text_origin": self.text_origin,
            "source_type": self.source_type,
            "group": self.group,
            "event_date_kind": self.event_date_kind,
            "abstained": self.abstained,
            "target_json_sha256": hashlib.sha256(self.target_json.encode("utf-8")).hexdigest(),
        }


@dataclass(frozen=True)
class SFTBundle:
    train: tuple[SFTRecord, ...]
    validation: tuple[SFTRecord, ...]
    refused: Mapping[str, int]
    tier: str = BUNDLE_TIER

    @property
    def bundle_sha256(self) -> str:
        payload = [record.to_meta() for record in self.train + self.validation]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def summary(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "train": len(self.train),
            "validation": len(self.validation),
            "refused": dict(sorted(self.refused.items())),
            "bundle_sha256": self.bundle_sha256,
            "prompt_version": PROMPT_VERSION,
            "train_text_origin": _count(record.text_origin for record in self.train),
            "validation_text_origin": _count(record.text_origin for record in self.validation),
            "train_event_date_kind": _count(record.event_date_kind for record in self.train),
            "train_source_type": _count(record.source_type for record in self.train),
        }


def _count(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _company_raw_text(case: DatasetCase) -> str | None:
    """The company string a *reader* would see, for ``company.raw_text``.

    It is taken from the document metadata (the display name used by the agency
    that published the record), not from any model.  ``None`` when the document
    does not name a company (a negative control).
    """
    metadata = case.document.metadata or {}
    if metadata.get("company_hint"):
        return str(metadata["company_hint"]).split("[canonical_id")[0].strip() or None
    return None


def build_target(
    case: DatasetCase,
    *,
    document_published_at: str | None,
) -> ExtractionResult:
    """Construct the target extraction for one case from its silver events."""
    if case.expected_abstain and not case.gold_events:
        event = EventExtraction(
            status="abstained",
            abstain_reason="no_event",
            company=EntityClaim(raw_text=None, canonical_id=None, match_basis="none"),
            technology_domains=(),
        )
        return ExtractionResult(
            doc_id=case.document.doc_id,
            parse_status="ok",
            extractor=ExtractorProvenance(system=GOLD_SYSTEM, adapter_id=GOLD_ADAPTER_ID),
            events=(event,),
        )
    events: list[EventExtraction] = []
    raw_text = _company_raw_text(case)
    for gold in case.gold_events:
        published = document_published_at or gold.published_at
        events.append(
            EventExtraction(
                status="extracted",
                company=EntityClaim(
                    raw_text=raw_text,
                    canonical_id=gold.company_canonical_id,
                    match_basis="roster_alias_in_document",
                ),
                event_category=gold.event_category,
                technology_domains=tuple(gold.technology_domains),
                product_or_technology=gold.product_or_technology,
                event_date=gold.event_date,
                event_date_kind=str(
                    (case.document.metadata or {}).get("event_date_kind")
                    or ("decision" if gold.event_category.startswith("regulatory") else "unspecified")
                ),
                published_at=published if published else None,
                first_seen_at=None,
                timestamp_quality=TimestampQuality(
                    event_date="exact_day" if gold.event_date else "absent",
                    published_at="exact_day" if published else "absent",
                    first_seen_at="absent",
                ),
                evidence=(
                    (
                        EvidenceSpan(
                            quote=str(gold.evidence_quote),
                            field="event_category",
                        ),
                    )
                    if gold.evidence_quote
                    else ()
                ),
            )
        )
    return ExtractionResult(
        doc_id=case.document.doc_id,
        parse_status="ok",
        extractor=ExtractorProvenance(system=GOLD_SYSTEM, adapter_id=GOLD_ADAPTER_ID),
        events=tuple(events),
    )


def _target_json(result: ExtractionResult) -> str:
    payload = {"events": [event.to_dict() for event in result.events]}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_sft_records(
    dataset: DatasetManifest,
    *,
    roster: EntityRoster | None = None,
    taxonomy: Taxonomy | None = None,
    domains: Sequence[str] | None = None,
    domain_track_map: Mapping[str, str] | None = None,
    prompt_version: str = PROMPT_VERSION,
    include_canonical_id_hint: bool = True,
    max_input_chars: int = 12_000,
    verify_with_validator: bool = True,
) -> SFTBundle:
    """Turn a split-assigned manifest into prompt/target pairs.

    Every target is validated with the *evaluation* validator unless
    ``verify_with_validator=False`` (never do that for a run you will report).
    """
    roster = roster or EntityRoster.from_config()
    taxonomy = taxonomy or Taxonomy.from_config()
    domains = tuple(domains) if domains is not None else tuple(taxonomy.domain_ids)
    if domain_track_map is None:
        domain_track_map = {track.track_id: track.domain for track in taxonomy.tracks}

    train: list[SFTRecord] = []
    validation: list[SFTRecord] = []
    refused: dict[str, int] = {}
    template_sha = render_template_sha256(
        prompt_version=prompt_version,
        domains=domains,
        domain_track_map=domain_track_map,
        include_canonical_id_hint=include_canonical_id_hint,
    )

    def refuse(reason: str) -> None:
        refused[reason] = refused.get(reason, 0) + 1

    for case in dataset.cases:
        if case.split not in ("train", "validation"):
            continue
        result = build_target(case, document_published_at=case.document.published_at)
        if verify_with_validator:
            verdict = validate_extraction(
                result, document=case.document, roster=roster, taxonomy=taxonomy
            )
            if verdict.verdict.value != "accepted":
                for judgement in verdict.judgements:
                    for code in judgement.reason_codes:
                        refuse(f"validator:{code}")
                if not any(judgement.reason_codes for judgement in verdict.judgements):
                    refuse("validator:rejected_without_code")
                continue
            if verdict.judgements and any(
                judgement.verdict.value != "accepted" for judgement in verdict.judgements
            ):
                refuse("validator:partially_quarantined")
                continue
        prompt = build_prompt(
            case.document,
            max_input_chars=max_input_chars,
            technology_domains=domains,
            domain_track_map=domain_track_map,
            prompt_version=prompt_version,
            include_canonical_id_hint=include_canonical_id_hint,
        )
        record = SFTRecord(
            case_id=case.case_id,
            split=case.split,
            prompt_version=prompt.prompt_version,
            template_sha256=prompt.template_sha256 or template_sha,
            system=prompt.system,
            user=prompt.user,
            target_json=_target_json(result),
            label_tier=case.label_tier,
            text_origin=str((case.document.metadata or {}).get("text_origin") or "unknown"),
            source_type=case.document.source_type,
            group=case.group,
            event_date_kind=str((case.document.metadata or {}).get("event_date_kind") or ""),
            abstained=bool(case.expected_abstain and not case.gold_events),
        )
        if case.split == "train":
            train.append(record)
        else:
            validation.append(record)

    if not train:
        raise RuntimeError(
            f"no training record survived validation (refused={dict(sorted(refused.items()))})"
        )
    if not validation:
        raise RuntimeError(
            f"no validation record survived validation (refused={dict(sorted(refused.items()))})"
        )
    return SFTBundle(train=tuple(train), validation=tuple(validation), refused=refused)


__all__ = [
    "BUNDLE_TIER",
    "GOLD_ADAPTER_ID",
    "GOLD_SYSTEM",
    "SFTBundle",
    "SFTRecord",
    "build_sft_records",
    "build_target",
]
