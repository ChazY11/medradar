"""Cross-module contracts: validation, datasets, run manifests and metrics.

``schema.py`` defines *what an extraction looks like*.  This module defines *how
the experiment talks about it*: what counts as a valid label, what a validation
verdict means, what a run must record, and what a metric report may claim.

The single most important rule in this file is the label tier.  MedRadar already
has AI pre-annotation on 69 evidence packets, and that annotation is **not** human
ground truth (the separate AI review tier lives on branch
``research/ai-evidence-review``; ``labels.py`` reads it only if it is present in the
checkout).  A machine score computed against machine labels is circular, so a tier
is attached to every label and to every run:

    human_confirmed / expert_adjudicated  -> research grade
    ai_preliminary / synthetic_fixture / unlabelled -> never research grade

A run whose dataset contains only synthetic fixtures is allowed to exist and is
useful for testing the *harness*; every artifact it produces is stamped
``SYNTHETIC_FIXTURE_ONLY`` and no document may quote its numbers as a result.

Module shape
------------
The validator entry point is frozen as::

    from experiments.local_llm_event_extraction.validation.validator import (
        EntityRoster, Taxonomy, validate_extraction,
    )
    validate_extraction(result, document=doc, roster=roster, taxonomy=taxonomy,
                        config=ValidationConfig()) -> ValidationResult

The benchmark entry point is frozen as::

    from experiments.local_llm_event_extraction.benchmark.runner import run_benchmark
    run_benchmark(dataset, adapters, output_dir=..., seeds=(...)) -> BenchmarkRun

Nothing here imports a model library, torch, a database, or the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .schema import SCHEMA_VERSION, ExtractionResult, SourceDocument

SCORING_PROTOCOL_VERSION = "v1"
RUN_MANIFEST_VERSION = "v1"

# ------------------------------------------------------------------- label tiers
LABEL_TIERS: tuple[str, ...] = (
    "human_confirmed",
    "expert_adjudicated",
    "ai_preliminary",
    "synthetic_fixture",
    "unlabelled",
    "source_record_derived",
)
RESEARCH_GRADE_TIERS: tuple[str, ...] = ("human_confirmed", "expert_adjudicated")

TIER_MEANING: Mapping[str, str] = {
    "human_confirmed": "a named human reviewed the evidence and recorded the label",
    "expert_adjudicated": "a domain expert adjudicated the label with a recorded rationale",
    "ai_preliminary": "machine pre-annotation; useful as a weak prior, never as ground truth",
    "synthetic_fixture": "hand-built fixture for exercising the harness; never an empirical result",
    "unlabelled": "no label yet; excluded from any scored metric",
    "source_record_derived": "value copied from the source's own structured record; independent of any model, not independent of the document, and never a human label",
}

RUN_STATUSES: tuple[str, ...] = (
    "SYNTHETIC_FIXTURE_ONLY",
    "REAL_DOCUMENT_UNLABELLED",
    "RESEARCH_GRADE",
    "NOT_RUN",
    "FAILED",
)

"""Why ``REAL_DOCUMENT_UNLABELLED`` exists.

The two original statuses could not describe the middle case that this project
actually reached: **real public documents, no human event labels**.  Stamping such a
run ``SYNTHETIC_FIXTURE_ONLY`` is false (the documents are real) and calling it
``RESEARCH_GRADE`` is worse (there is nothing to score accuracy against).  The third
status means exactly: the extraction pipeline ran on real documents, harness-level
facts (parse rate, schema pass rate, verbatim-quote location, abstention, latency,
resources) are measurable, and **no accuracy claim is possible**.
"""


def is_research_grade(tiers: Any) -> bool:
    """True only if every tier present is a human/expert label."""
    tiers = tuple(tiers)
    return bool(tiers) and all(tier in RESEARCH_GRADE_TIERS for tier in tiers)


def is_synthetic(tiers: Any) -> bool:
    """True when any tier present is the hand-built fixture tier."""
    return "synthetic_fixture" in tuple(tiers)


def default_run_status(tiers: Any) -> str:
    """The most favourable status a dataset's label tiers can honestly support."""
    tiers = tuple(tiers)
    if is_research_grade(tiers):
        return "RESEARCH_GRADE"
    if is_synthetic(tiers) or not tiers:
        return "SYNTHETIC_FIXTURE_ONLY"
    return "REAL_DOCUMENT_UNLABELLED"


def require_consistent_run_status(status: str, tiers: Any) -> str:
    """Refuse to let a run claim a status its labels cannot support.

    Returns the status to record (``status`` when consistent) and raises
    ``ValueError`` when asked to label fixture output as an empirical result or to
    describe synthetic fixtures as real documents.
    """
    if status not in RUN_STATUSES:
        raise ValueError(f"unknown run status {status!r}")
    tiers = tuple(tiers)
    if status == "RESEARCH_GRADE" and not is_research_grade(tiers):
        raise ValueError(
            "refusing to mark a run RESEARCH_GRADE: dataset label tiers "
            f"{sorted(set(tiers))} are not all in {sorted(RESEARCH_GRADE_TIERS)}"
        )
    if status == "REAL_DOCUMENT_UNLABELLED" and is_synthetic(tiers):
        raise ValueError(
            "refusing to mark a run REAL_DOCUMENT_UNLABELLED: dataset label tiers "
            f"{sorted(set(tiers))} include synthetic fixture data"
        )
    return status


# --------------------------------------------------------------------- validation
class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Verdict(str, Enum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ValidationIssue:
    """One finding about one event.  Findings never mutate the event."""

    code: str
    severity: Severity
    field: str
    detail: str
    event_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "field": self.field,
            "detail": self.detail,
            "event_index": self.event_index,
        }


@dataclass(frozen=True)
class EventJudgement:
    """The verdict for a single event, addressed by its index in the result.

    The judgement does not carry the event object: the validator never copies,
    rewrites or "cleans" an extraction, so the only authoritative copy of the event
    remains the caller's :class:`~experiments.local_llm_event_extraction.schema.EventExtraction`
    at ``index``.
    """

    index: int
    verdict: Verdict
    issues: tuple[ValidationIssue, ...] = ()
    dedup_key: str | None = None

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted({issue.code for issue in self.issues if issue.severity is Severity.ERROR}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "verdict": self.verdict.value,
            "reason_codes": list(self.reason_codes),
            "dedup_key": self.dedup_key,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class ValidationResult:
    """Document-level validation outcome.

    ``quarantined`` events are kept and reported, never dropped silently: the
    error taxonomies of the benchmark are computed from them.  ``normalizations``
    records formatting-only changes (whitespace, unicode) so a reader can see that
    no semantic value was repaired.
    """

    doc_id: str
    verdict: Verdict
    judgements: tuple[EventJudgement, ...] = ()
    normalizations: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    @property
    def accepted_indices(self) -> tuple[int, ...]:
        return tuple(j.index for j in self.judgements if j.verdict is Verdict.ACCEPTED)

    @property
    def quarantined_indices(self) -> tuple[int, ...]:
        return tuple(j.index for j in self.judgements if j.verdict is Verdict.QUARANTINED)

    @property
    def error_codes(self) -> tuple[str, ...]:
        return tuple(sorted({code for j in self.judgements for code in j.reason_codes}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "verdict": self.verdict.value,
            "schema_version": self.schema_version,
            "normalizations": list(self.normalizations),
            "error_codes": list(self.error_codes),
            "judgements": [judgement.to_dict() for judgement in self.judgements],
        }


@dataclass(frozen=True)
class ValidationConfig:
    """Pre-registered validation thresholds.

    Values are part of the protocol, not of a model run: changing one is a
    protocol amendment, not a tuning knob.
    """

    require_evidence_for_extracted: bool = True
    require_verbatim_quote: bool = True
    require_date_supported_by_quote: bool = True
    require_entity_alias_in_document: bool = True
    reject_model_inference_entity: bool = True
    reject_model_invented_first_seen: bool = True
    reject_future_dates: bool = True
    allow_empty_evidence_for_abstained: bool = True
    min_quote_chars: int = 8
    duplicate_jaccard_threshold: float = 0.85
    max_events_per_document: int = 20


# ------------------------------------------------------------------------ datasets
@dataclass(frozen=True)
class GoldEvent:
    """A labelled event used for scoring.

    ``evidence_quote`` is the human-selected support span.  A predicted event's
    citation is "correct" when its quote genuinely appears in the document *and*
    overlaps this span's text; that keeps the metric about evidence rather than
    about string luck.
    """

    event_id: str
    company_canonical_id: str | None
    event_category: str
    event_date: str | None = None
    published_at: str | None = None
    product_or_technology: str | None = None
    technology_domains: tuple[str, ...] = ()
    evidence_quote: str | None = None
    label_tier: str = "unlabelled"
    label_source: str | None = None

    def __post_init__(self) -> None:
        if self.label_tier not in LABEL_TIERS:
            raise ValueError(f"unknown label_tier {self.label_tier!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "company_canonical_id": self.company_canonical_id,
            "event_category": self.event_category,
            "event_date": self.event_date,
            "published_at": self.published_at,
            "product_or_technology": self.product_or_technology,
            "technology_domains": list(self.technology_domains),
            "evidence_quote": self.evidence_quote,
            "label_tier": self.label_tier,
            "label_source": self.label_source,
        }


@dataclass(frozen=True)
class DatasetCase:
    """One scored unit: a document, its gold events, and its split membership.

    ``group`` is the leakage-prevention key (company or document family).  Splits
    are assigned by group, never by case, so the same company cannot appear in
    both train and test.
    """

    case_id: str
    document: SourceDocument
    gold_events: tuple[GoldEvent, ...] = ()
    expected_abstain: bool = False
    label_tier: str = "unlabelled"
    group: str = ""
    split: str = "unassigned"

    def __post_init__(self) -> None:
        if self.label_tier not in LABEL_TIERS:
            raise ValueError(f"unknown label_tier {self.label_tier!r}")
        if self.split not in ("train", "validation", "test", "unassigned"):
            raise ValueError(f"unknown split {self.split!r}")

    @property
    def is_negative_control(self) -> bool:
        return self.expected_abstain and not self.gold_events

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "document": self.document.to_dict(),
            "gold_events": [event.to_dict() for event in self.gold_events],
            "expected_abstain": self.expected_abstain,
            "label_tier": self.label_tier,
            "group": self.group,
            "split": self.split,
        }


@dataclass(frozen=True)
class DatasetManifest:
    """What a scored run was actually scored against."""

    name: str
    version: str
    cases: tuple[DatasetCase, ...]
    source_paths: tuple[str, ...] = ()
    source_sha256: str | None = None
    notes: str | None = None

    @property
    def label_tiers(self) -> tuple[str, ...]:
        return tuple(sorted({case.label_tier for case in self.cases}))

    @property
    def case_count(self) -> int:
        return len(self.cases)

    def by_split(self, split: str) -> tuple[DatasetCase, ...]:
        return tuple(case for case in self.cases if case.split == split)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable form; the benchmark hashes this for its dataset id."""
        return {
            "name": self.name,
            "version": self.version,
            "case_count": self.case_count,
            "label_tiers": list(self.label_tiers),
            "source_paths": list(self.source_paths),
            "source_sha256": self.source_sha256,
            "notes": self.notes,
            "cases": [case.to_dict() for case in self.cases],
        }


# ------------------------------------------------------------------- measurements
@dataclass(frozen=True)
class ResourceMeasurement:
    """Measured cost of one benchmark run.

    A field left ``None`` means *not measured*, with the reason recorded in
    ``notes``.  ``None`` is never rendered as ``0`` in a report.
    """

    wall_time_s: float | None = None
    per_case_wall_time_s: tuple[float, ...] = ()
    cpu_time_s: float | None = None
    peak_rss_mb: float | None = None
    peak_vram_mb: float | None = None
    vram_measurement_method: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    estimated_cost_usd: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "wall_time_s": self.wall_time_s,
            "per_case_wall_time_s": list(self.per_case_wall_time_s),
            "cpu_time_s": self.cpu_time_s,
            "peak_rss_mb": self.peak_rss_mb,
            "peak_vram_mb": self.peak_vram_mb,
            "vram_measurement_method": self.vram_measurement_method,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "estimated_cost_usd": self.estimated_cost_usd,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MetricReport:
    """Event-level and field-level metrics with an explicit matching protocol."""

    matching_protocol: Mapping[str, Any]
    support: int
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    entity_match_accuracy: float | None = None
    event_date_accuracy: float | None = None
    published_at_accuracy: float | None = None
    citation_correctness_rate: float | None = None
    abstention_rate: float | None = None
    wrong_abstention_rate: float | None = None
    false_assertion_rate: float | None = None
    parse_failure_rate: float | None = None
    per_category: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    per_source_type: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    error_taxonomy: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matching_protocol": dict(self.matching_protocol),
            "support": self.support,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "entity_match_accuracy": self.entity_match_accuracy,
            "event_date_accuracy": self.event_date_accuracy,
            "published_at_accuracy": self.published_at_accuracy,
            "citation_correctness_rate": self.citation_correctness_rate,
            "abstention_rate": self.abstention_rate,
            "wrong_abstention_rate": self.wrong_abstention_rate,
            "false_assertion_rate": self.false_assertion_rate,
            "parse_failure_rate": self.parse_failure_rate,
            "per_category": {k: dict(v) for k, v in self.per_category.items()},
            "per_source_type": {k: dict(v) for k, v in self.per_source_type.items()},
            "error_taxonomy": dict(self.error_taxonomy),
        }


@dataclass(frozen=True)
class RunManifest:
    """Everything needed to re-run and to judge what a number means."""

    run_id: str
    created_at: str
    status: str
    adapter: Mapping[str, Any]
    dataset: Mapping[str, Any]
    metrics: Mapping[str, Any]
    resources: Mapping[str, Any]
    config: Mapping[str, Any]
    config_sha256: str
    seeds: tuple[int, ...] = ()
    git_commit: str | None = None
    git_branch: str | None = None
    git_dirty: bool | None = None
    environment: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    scoring_protocol_version: str = SCORING_PROTOCOL_VERSION
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_manifest_version": RUN_MANIFEST_VERSION,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "status": self.status,
            "schema_version": self.schema_version,
            "scoring_protocol_version": self.scoring_protocol_version,
            "adapter": dict(self.adapter),
            "dataset": dict(self.dataset),
            "metrics": dict(self.metrics),
            "resources": dict(self.resources),
            "config": dict(self.config),
            "config_sha256": self.config_sha256,
            "seeds": list(self.seeds),
            "git": {
                "commit": self.git_commit,
                "branch": self.git_branch,
                "dirty": self.git_dirty,
            },
            "environment": dict(self.environment),
            "notes": list(self.notes),
        }


__all__ = [
    "LABEL_TIERS",
    "RESEARCH_GRADE_TIERS",
    "TIER_MEANING",
    "RUN_STATUSES",
    "SCORING_PROTOCOL_VERSION",
    "RUN_MANIFEST_VERSION",
    "Severity",
    "Verdict",
    "ValidationIssue",
    "EventJudgement",
    "ValidationResult",
    "ValidationConfig",
    "GoldEvent",
    "DatasetCase",
    "DatasetManifest",
    "ResourceMeasurement",
    "MetricReport",
    "RunManifest",
    "default_run_status",
    "is_research_grade",
    "is_synthetic",
    "require_consistent_run_status",
    "ExtractionResult",
    "SourceDocument",
]
