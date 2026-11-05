"""The synthetic fixture dataset: hand-written documents that exercise the harness.

What this dataset is
--------------------
Fourteen hand-written, invented medtech documents with gold events.  They exist to
prove that the *machinery* works end to end: registry, adapters, prompt rendering,
strict parsing, validation injection, scoring, reporting and resume.  They are
**not** a sample and **not** a benchmark: every case is labelled
``synthetic_fixture`` and every artifact built from them is stamped
``SYNTHETIC_FIXTURE_ONLY``.

No text is copied from, or derived from, any real press release, filing, paper or
database record.  Companies, products and dates are invented.

What the fixtures exercise deliberately
---------------------------------------
(i)   A press release published 2024-03-05 whose underlying trial started
      2023-09-12.  Copying the publication date into ``event_date`` is an error.
(ii)  A subsidiary alias (``NovaPulse Cardiac``) that must map to the parent
      canonical id (``novapulse-medical``).
(iii) A month-only date (``March 2025`` -> ``2025-03``, quality ``exact_month``).
(iv)  A competitor named in a document about a different company.
      Plus: a two-events-in-one-document case, three negative controls (no target
      event), and canned scripted outputs that include paraphrased quotes, an
      invented date, a refusal, invalid JSON and a duplicate event.

The gold quote of every event is checked to be a verbatim substring of its
document at load time; a fixture that cannot support its own label fails loudly
instead of silently producing an untestable case.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..contracts import DatasetCase, DatasetManifest, GoldEvent
from ..schema import SOURCE_TYPES, SourceDocument
from .splits import DEFAULT_RATIOS, DEFAULT_SEED, assign_grouped_splits

DATASET_NAME = "synthetic_event_extraction_v0"
DATASET_VERSION = "v0"
LABEL_TIER = "synthetic_fixture"

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
CASES_PATH = FIXTURE_DIR / "cases_v0.json"
RESPONSES_PATH = FIXTURE_DIR / "responses_v0.json"

ROSTER_ALIASES: Mapping[str, str] = {
    # Trap (ii): the subsidiary alias must resolve to the parent canonical id.
    "NovaPulse Cardiac": "novapulse-medical",
    "NovaPulse Medical": "novapulse-medical",
    "Asterion Surgical": "asterion-surgical",
    "Helixor Diagnostics": "helixor-diagnostics",
    "Tidewell Orthopedics": "tidewell-orthopedics",
    "Corvane Biosciences": "corvane-biosciences",
    "Marrowline Devices": "marrowline-devices",
    "Kestrel Endoscopy": "kestrel-endoscopy",
}
"""Alias text -> canonical company id for the synthetic fixtures.

This is *not* a production entity roster: the rules adapter accepts a plain
mapping so that a real run can inject the validator's roster instead.
"""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - fixtures are committed
        raise FileNotFoundError(f"synthetic fixture missing: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"fixture {path} must contain a JSON object")
    return payload


def case_fixture_path() -> Path:
    return CASES_PATH


def responses_fixture_path() -> Path:
    return RESPONSES_PATH


def dataset_sha256(path: Path | None = None) -> str:
    """sha256 of the cases fixture file (recorded in every run manifest)."""
    target = Path(path) if path is not None else CASES_PATH
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _case_from_payload(payload: Mapping[str, Any], index: int) -> DatasetCase:
    try:
        case_id = str(payload["case_id"])
        document_payload = dict(payload["document"])
    except KeyError as exc:
        raise ValueError(f"case fixtures[{index}] is missing {exc}") from exc
    if document_payload.get("source_type") not in SOURCE_TYPES:
        raise ValueError(
            f"case {case_id!r} has unknown source_type {document_payload.get('source_type')!r}"
        )
    document = SourceDocument(
        doc_id=str(document_payload["doc_id"]),
        source_type=str(document_payload["source_type"]),
        text=str(document_payload["text"]),
        title=document_payload.get("title"),
        published_at=document_payload.get("published_at"),
        first_seen_at=document_payload.get("first_seen_at"),
        retrieved_at=document_payload.get("retrieved_at"),
        url=document_payload.get("url"),
        publisher=document_payload.get("publisher"),
        metadata=dict(document_payload.get("metadata") or {}),
    )
    gold_events: list[GoldEvent] = []
    for event_payload in payload.get("gold_events") or []:
        event = GoldEvent(
            event_id=str(event_payload["event_id"]),
            company_canonical_id=event_payload.get("company_canonical_id"),
            event_category=str(event_payload["event_category"]),
            event_date=event_payload.get("event_date"),
            published_at=event_payload.get("published_at"),
            product_or_technology=event_payload.get("product_or_technology"),
            technology_domains=tuple(event_payload.get("technology_domains") or ()),
            evidence_quote=event_payload.get("evidence_quote"),
            label_tier=str(event_payload.get("label_tier") or LABEL_TIER),
            label_source=event_payload.get("label_source"),
        )
        if event.evidence_quote is not None and event.evidence_quote not in document.text:
            raise ValueError(
                f"case {case_id!r}: gold quote for {event.event_id!r} is not a verbatim "
                "substring of its document; the fixture would not be scoreable"
            )
        gold_events.append(event)
    expected_abstain = bool(payload.get("expected_abstain", not gold_events))
    if expected_abstain and gold_events:
        raise ValueError(f"case {case_id!r} claims expected_abstain but has gold events")
    return DatasetCase(
        case_id=case_id,
        document=document,
        gold_events=tuple(gold_events),
        expected_abstain=expected_abstain,
        label_tier=str(payload.get("label_tier") or LABEL_TIER),
        group=str(payload.get("group") or ""),
        split="unassigned",
    )


def load_cases(path: str | Path | None = None) -> tuple[DatasetCase, ...]:
    """Load the 14 synthetic cases (split ``unassigned``)."""
    fixture_path = Path(path) if path is not None else CASES_PATH
    payload = _read_json(fixture_path)
    cases_raw = payload.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError(f"fixture {fixture_path} has no cases")
    cases = tuple(_case_from_payload(item, index) for index, item in enumerate(cases_raw))
    doc_ids = [case.document.doc_id for case in cases]
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("synthetic fixture has duplicate doc_id values")
    return cases


def load_responses(path: str | Path | None = None) -> dict[str, str]:
    """Canned response text for the ``scripted-fixture`` harness test double."""
    fixture_path = Path(path) if path is not None else RESPONSES_PATH
    payload = _read_json(fixture_path)
    responses = payload.get("responses")
    if not isinstance(responses, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in responses.items()
    ):
        raise ValueError(f"fixture {fixture_path} must contain a string->string 'responses' object")
    return dict(responses)


def build_dataset(
    cases: Sequence[DatasetCase] | None = None,
    *,
    seed: int = DEFAULT_SEED,
    ratios: Sequence[float] = DEFAULT_RATIOS,
) -> DatasetManifest:
    """The synthetic dataset with deterministic grouped splits and its file hash."""
    materialised = tuple(cases) if cases is not None else load_cases()
    split_manifest = assign_grouped_splits(materialised, ratios=ratios, seed=seed)
    repo_root = Path(__file__).resolve().parents[3]
    try:
        source_path = str(CASES_PATH.relative_to(repo_root))
    except ValueError:  # pragma: no cover - checkout layouts without repo root
        source_path = str(CASES_PATH)
    return DatasetManifest(
        name=DATASET_NAME,
        version=DATASET_VERSION,
        cases=split_manifest.cases,
        source_paths=(source_path,),
        source_sha256=dataset_sha256(),
        notes=(
            "SYNTHETIC_FIXTURE_ONLY: 14 hand-authored invented documents for harness "
            f"validation; grouped split seed={seed}. Numbers computed here are not an "
            "empirical result and must never be quoted as one."
        ),
    )


def describe_fixture() -> dict[str, Any]:
    """Small machine-readable description for a report/readme."""
    cases = load_cases()
    gold_events = sum(len(case.gold_events) for case in cases)
    groups = sorted({case.group for case in cases})
    return {
        "dataset": DATASET_NAME,
        "version": DATASET_VERSION,
        "label_tier": LABEL_TIER,
        "case_count": len(cases),
        "gold_event_count": gold_events,
        "negative_controls": sum(1 for case in cases if case.is_negative_control),
        "groups": groups,
        "source_type_counts": _counts(case.document.source_type for case in cases),
        "category_counts": _counts(
            event.event_category for case in cases for event in case.gold_events
        ),
        "notes": "hand-authored synthetic fixtures; not copied from any real document",
    }


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


__all__ = [
    "CASES_PATH",
    "DATASET_NAME",
    "DATASET_VERSION",
    "FIXTURE_DIR",
    "LABEL_TIER",
    "RESPONSES_PATH",
    "ROSTER_ALIASES",
    "build_dataset",
    "case_fixture_path",
    "dataset_sha256",
    "describe_fixture",
    "load_cases",
    "load_responses",
    "responses_fixture_path",
]
