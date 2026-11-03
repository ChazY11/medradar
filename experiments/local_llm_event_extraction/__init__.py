"""Local small-language-model research harness for medtech event extraction.

Status: **experimental, offline, not yet executed on a model.**  This package is
the engineering substrate for a research question that has *not* been answered:

    Can a locally hosted 1B-8B open model extract time- and evidence-grounded
    medtech technical-development events from public documents more reliably than
    MedRadar's existing rule-based extraction?

Nothing in this package asserts that answer.  The three comparison arms (rules,
untuned model, QLoRA-tuned model) share one interface, one schema and one scorer so
that, when the real labels exist, the comparison is pre-registered rather than
narrated afterwards.

What is deliberately absent
---------------------------
* No model weights, no downloads, no tokeniser assumptions.
* No GPU requirement: every offline test runs on CPU with no model at all.
* No writes to ``research/studies/``, ``data/`` or any other agent's output.
* No training run: ``training/`` builds the configuration and refuses to execute.
* No fabricated score: fixtures are labelled ``SYNTHETIC_FIXTURE_ONLY`` throughout.

Layout
------
``schema.py``      the frozen event contract + JSON Schema
``contracts.py``   validation/dataset/manifest/metric contracts and label tiers
``safety.py``      the four default-closed run gates
``adapters/``      rule-based baseline, gated local HF backend, gated remote API, scripted fixture backend
``prompting.py``   one prompt builder, versioned, shared by arms B and C
``parsing.py``     model text -> structured payload, with refusal detection
``validation/``    schema checks, verbatim evidence location, entity and time checks, dedup, quarantine
``benchmark/``     the arm-agnostic runner, scorer and report writer
``datasets/``      synthetic fixtures, grouped splits, leakage guards
``training/``      QLoRA configuration, dataset readiness, resume/logging and hard refusals
``scripts/``       read-only environment probe
``docs/``          protocol, hardware compatibility, install guide, readiness and risk registers
"""

from __future__ import annotations

__version__ = "0.1.0"

from .contracts import (  # noqa: E402,F401  (re-exported for convenience)
    DatasetCase,
    DatasetManifest,
    GoldEvent,
    MetricReport,
    RunManifest,
    ValidationConfig,
    ValidationResult,
    Verdict,
    is_research_grade,
    require_consistent_run_status,
)
from .safety import (  # noqa: E402,F401
    ENV_MODEL_LOAD,
    ENV_NETWORK,
    ENV_REMOTE_API,
    ENV_TRAINING,
    GATE_MODEL_LOAD,
    GATE_NETWORK,
    GATE_REMOTE_API,
    GATE_TRAINING,
    GateClosed,
    all_gates_closed,
    gate_open,
    gate_report,
    require_gate,
)
from .schema import (  # noqa: E402,F401
    ABSTAIN_REASONS,
    EVENT_CATEGORIES,
    SCHEMA_VERSION,
    SOURCE_TYPES,
    ContractError,
    EntityClaim,
    EventExtraction,
    EvidenceSpan,
    ExtractionResult,
    ExtractorProvenance,
    SourceDocument,
    TimestampQuality,
    event_from_dict,
    result_from_dict,
    schema_document,
)

__all__ = [
    "__version__",
    "ABSTAIN_REASONS",
    "EVENT_CATEGORIES",
    "SCHEMA_VERSION",
    "SOURCE_TYPES",
    "ContractError",
    "EntityClaim",
    "EventExtraction",
    "EvidenceSpan",
    "ExtractionResult",
    "ExtractorProvenance",
    "SourceDocument",
    "TimestampQuality",
    "event_from_dict",
    "result_from_dict",
    "schema_document",
    "DatasetCase",
    "DatasetManifest",
    "GoldEvent",
    "MetricReport",
    "RunManifest",
    "ValidationConfig",
    "ValidationResult",
    "Verdict",
    "is_research_grade",
    "require_consistent_run_status",
    "ENV_MODEL_LOAD",
    "ENV_NETWORK",
    "ENV_REMOTE_API",
    "ENV_TRAINING",
    "GATE_MODEL_LOAD",
    "GATE_NETWORK",
    "GATE_REMOTE_API",
    "GATE_TRAINING",
    "GateClosed",
    "all_gates_closed",
    "gate_open",
    "gate_report",
    "require_gate",
]
