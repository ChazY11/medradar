"""Load a real public-document corpus into the benchmark's dataset contract.

This is the bridge between a **real** corpus (collected from public APIs, with
provenance and content hashes -- see the corpus ``MANIFEST.json``) and the frozen
:class:`~..contracts.DatasetManifest` the benchmark consumes.

Two things it deliberately does *not* do:

1. **It does not invent labels.**  A document is labelled
   :data:`SILVER_TIER` only when its own source record carries the value being
   asserted (for example the ``decision_date`` an openFDA 510(k) record was fetched
   with).  That is a *silver* label: independent of any model, but **not**
   independent of the document, and it is not a human label.  Prose documents whose
   source record does not contain the fact in its text get no gold event at all.
2. **It does not assign training splits.**  Every real document is evaluation-only
   and marked ``split="test"``.  Nothing here may ever be used as training data
   without a separate, recorded decision.

Integrity: the ``content_sha256`` recorded at collection time is recomputed from the
document text at load time.  A corpus edited after collection therefore fails loudly
instead of silently changing what a run measured.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import DatasetCase, DatasetManifest
from ..schema import SOURCE_TYPES, SourceDocument
from ..contracts import GoldEvent

CORPUS_SCHEMA = "medradar.real_document_corpus"
DATASET_NAME = "real-medtech-documents-5firms"
DATASET_VERSION = "2026-11-04"
SILVER_TIER = "source_record_derived"
CORPUS_LABEL_TIER = "unlabelled"

#: Corpus company id -> the canonical id used by ``config/universe_v1.json``.
#: The corpus uses readable hyphenated ids; the roster (and therefore the stored
#: event contract) uses underscores.  This table is the single place they meet, and
#: an unknown id is a hard error rather than a silently unvalidated event.
COMPANY_CANONICAL_IDS: Mapping[str, str] = {
    "medtronic": "medtronic",
    "philips": "philips",
    "siemens-healthineers": "siemens_healthineers",
    "ge-healthcare": "ge_healthcare",
    "draeger": "draeger",
}

COMPANY_DISPLAY_NAMES: Mapping[str, str] = {
    "medtronic": "Medtronic",
    "philips": "Royal Philips / Philips Healthcare",
    "siemens-healthineers": "Siemens Healthineers",
    "ge-healthcare": "GE HealthCare",
    "draeger": "Drägerwerk / Draeger",
}

#: Corpus source type -> the frozen ``SOURCE_TYPES`` vocabulary.
SOURCE_TYPE_MAP: Mapping[str, str] = {
    "regulatory_clearance": "fda_510k",
    "regulatory_approval": "fda_pma",
    "recall": "fda_recall",
    "clinical_trial_registration": "clinical_trial_record",
    "company_announcement": "press_release",
    "press_release": "press_release",
    "peer_reviewed_abstract": "scientific_publication",
    "device_technical_document": "other",
}

#: Corpus source type -> the event category a silver label asserts.
SOURCE_TYPE_CATEGORY: Mapping[str, str] = {
    "regulatory_clearance": "regulatory_clearance",
    "regulatory_approval": "regulatory_approval",
    "recall": "safety_recall",
    "clinical_trial_registration": "clinical_trial_start",
}

#: Source types whose ``source_publication_date`` is the event date itself.
#: (For a 510(k) or PMA record, the record's date *is* the decision date; for a
#: trial registration it is the registration publication date, not the trial start,
#: so it is deliberately absent from this map.)
_DATE_IS_EVENT_DATE: Mapping[str, str] = {
    "regulatory_clearance": "source_publication_date == decision_date",
    "regulatory_approval": "source_publication_date == decision_date",
}


class CorpusError(ValueError):
    """The corpus is missing, malformed, or was edited after collection."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusError(f"corpus file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"corpus file is not valid JSON: {path}: {exc}") from exc


def corpus_manifest_path(corpus_dir: str | Path) -> Path:
    return Path(corpus_dir) / "MANIFEST.json"


def corpus_document_paths(corpus_dir: str | Path) -> tuple[Path, ...]:
    documents = Path(corpus_dir) / "documents"
    if not documents.is_dir():
        raise CorpusError(f"corpus has no documents/ directory: {corpus_dir}")
    return tuple(sorted(documents.glob("*.json")))


def load_corpus(corpus_dir: str | Path) -> tuple[dict[str, Any], ...]:
    """Load and integrity-check every document record in ``corpus_dir``.

    Raises :class:`CorpusError` when a record is missing a required field, when its
    company cannot be mapped to a canonical id, when its ``source_type`` is outside
    the known mapping, or when its stored ``content_sha256`` no longer matches the
    text (the corpus was edited after collection).
    """
    directory = Path(corpus_dir)
    paths = corpus_document_paths(directory)
    if not paths:
        raise CorpusError(f"corpus contains no document records: {directory}")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        payload = _read_json(path)
        if not isinstance(payload, Mapping):
            raise CorpusError(f"{path.name}: document record must be a JSON object")
        record = dict(payload)
        doc_id = str(record.get("doc_id") or "").strip()
        if not doc_id:
            raise CorpusError(f"{path.name}: missing doc_id")
        if doc_id in seen:
            raise CorpusError(f"duplicate doc_id {doc_id!r}")
        seen.add(doc_id)
        company = str(record.get("company_canonical_id") or "").strip()
        if company not in COMPANY_CANONICAL_IDS:
            raise CorpusError(f"{doc_id}: unmapped company_canonical_id {company!r}")
        source_type = str(record.get("source_type") or "").strip()
        if source_type not in SOURCE_TYPE_MAP:
            raise CorpusError(f"{doc_id}: unmapped source_type {source_type!r}")
        text = record.get("text")
        if not isinstance(text, str) or len(text) < 200:
            raise CorpusError(f"{doc_id}: text must be a string of at least 200 characters")
        expected_hash = str(record.get("content_sha256") or "").strip().lower()
        if not expected_hash:
            raise CorpusError(f"{doc_id}: missing content_sha256")
        actual_hash = _sha256_text(text)
        if actual_hash != expected_hash:
            raise CorpusError(
                f"{doc_id}: content_sha256 mismatch; the corpus text was edited after "
                f"collection (stored {expected_hash[:12]}..., recomputed {actual_hash[:12]}...)"
            )
        text_style = str(record.get("text_style") or "field_value_rendering").strip()
        if text_style not in ("prose", "field_value_rendering"):
            raise CorpusError(f"{doc_id}: unknown text_style {text_style!r}")
        records.append(record)
    return tuple(records)


def _silver_event(record: Mapping[str, Any]) -> GoldEvent | None:
    """The one event the document's own source record can support, if any."""
    source_type = str(record["source_type"])
    category = SOURCE_TYPE_CATEGORY.get(source_type)
    if category is None:
        return None
    date_basis = _DATE_IS_EVENT_DATE.get(source_type)
    if date_basis is None:
        return None
    event_date = record.get("event_date") or record.get("decision_date") or record.get("source_publication_date")
    if not event_date:
        return None
    product = record.get("product_or_technology") or None
    return GoldEvent(
        event_id=f"{record['doc_id']}-silver",
        company_canonical_id=COMPANY_CANONICAL_IDS[str(record["company_canonical_id"])],
        event_category=category,
        event_date=str(event_date),
        published_at=record.get("source_publication_date"),
        product_or_technology=product,
        technology_domains=(),
        evidence_quote=None,
        label_tier=SILVER_TIER,
        label_source=f"source record field ({date_basis})",
    )


def to_cases(
    records: Sequence[Mapping[str, Any]],
    *,
    silver: bool = True,
) -> tuple[DatasetCase, ...]:
    """Turn corpus records into ``DatasetCase`` objects (all evaluation-only)."""
    cases: list[DatasetCase] = []
    for record in records:
        doc_id = str(record["doc_id"])
        company = str(record["company_canonical_id"])
        canonical_id = COMPANY_CANONICAL_IDS[company]
        display_name = COMPANY_DISPLAY_NAMES[company]
        source_type = SOURCE_TYPE_MAP[str(record["source_type"])]
        if source_type not in SOURCE_TYPES:  # pragma: no cover - guarded by SOURCE_TYPE_MAP test
            raise CorpusError(f"{doc_id}: mapped source_type {source_type!r} is not in SOURCE_TYPES")
        # The roster hint gives the model the canonical id it must use.  This is a
        # closed-roster extraction task, not open-set entity linking, and the
        # limitation is recorded in the run manifest.
        company_hint = f"{display_name} [canonical_id: {canonical_id}]"
        metadata = {
            "company_hint": company_hint,
            "company_canonical_id": canonical_id,
            "company_display_name": display_name,
            "corpus_doc_id": doc_id,
            "corpus_source_type": str(record["source_type"]),
            "text_style": str(record.get("text_style") or "field_value_rendering"),
            "content_sha256": str(record["content_sha256"]),
            "api_endpoint": str(record.get("api_endpoint") or ""),
            "retrieved_at": str(record.get("retrieved_at") or ""),
        }
        if record.get("raw_sha256"):
            metadata["raw_sha256"] = str(record["raw_sha256"])
        if record.get("text_truncated") is not None:
            metadata["text_truncated"] = str(bool(record.get("text_truncated"))).lower()
        document = SourceDocument(
            doc_id=doc_id,
            source_type=source_type,
            text=str(record["text"]),
            title=record.get("title"),
            published_at=record.get("source_publication_date"),
            first_seen_at=None,
            retrieved_at=record.get("retrieved_at"),
            url=record.get("url"),
            publisher=record.get("publisher"),
            metadata=metadata,
        )
        gold: tuple[GoldEvent, ...] = ()
        tier = CORPUS_LABEL_TIER
        if silver:
            event = _silver_event(record)
            if event is not None:
                gold = (event,)
                tier = SILVER_TIER
        cases.append(
            DatasetCase(
                case_id=doc_id,
                document=document,
                gold_events=gold,
                expected_abstain=False,
                label_tier=tier,
                group=company,
                split="test",
            )
        )
    return tuple(cases)


def build_real_document_dataset(
    corpus_dir: str | Path,
    *,
    silver: bool = True,
) -> DatasetManifest:
    """Load the real corpus as a benchmark-ready :class:`DatasetManifest`."""
    directory = Path(corpus_dir)
    records = load_corpus(directory)
    cases = to_cases(records, silver=silver)
    manifest_path = corpus_manifest_path(directory)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.exists() else None
    return DatasetManifest(
        name=DATASET_NAME,
        version=DATASET_VERSION,
        cases=cases,
        source_paths=(str(manifest_path), str(directory / "documents")),
        source_sha256=manifest_sha,
        notes=(
            "REAL public documents from openFDA and ClinicalTrials.gov, collected with "
            "provenance and content hashes. Evaluation-only (every case split='test'); never "
            "training data. Silver labels (tier 'source_record_derived') exist only where the "
            "source record itself carries the asserted value; no human labels exist. "
            "Harness-level metrics are measurable; accuracy is not."
        ),
    )


def describe_corpus(
    corpus_dir: str | Path,
    *,
    silver: bool = True,
) -> dict[str, Any]:
    """Machine-readable corpus description for manifests and reports."""
    directory = Path(corpus_dir)
    records = load_corpus(directory)
    cases = to_cases(records, silver=silver)
    per_company: dict[str, int] = {}
    per_source: dict[str, int] = {}
    per_style: dict[str, int] = {}
    for record in records:
        per_company[str(record["company_canonical_id"])] = per_company.get(str(record["company_canonical_id"]), 0) + 1
        per_source[str(record["source_type"])] = per_source.get(str(record["source_type"]), 0) + 1
        style = str(record.get("text_style") or "field_value_rendering")
        per_style[style] = per_style.get(style, 0) + 1
    return {
        "dataset": DATASET_NAME,
        "version": DATASET_VERSION,
        "corpus_dir": str(directory),
        "document_count": len(records),
        "silver_labelled_count": sum(1 for case in cases if case.gold_events),
        "companies": sorted(per_company),
        "documents_per_company": dict(sorted(per_company.items())),
        "documents_per_source_type": dict(sorted(per_source.items())),
        "documents_per_text_style": dict(sorted(per_style.items())),
        "splits": {"test": len(cases)},
        "label_tiers": sorted({case.label_tier for case in cases}),
    }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


__all__ = [
    "COMPANY_CANONICAL_IDS",
    "COMPANY_DISPLAY_NAMES",
    "CORPUS_LABEL_TIER",
    "CORPUS_SCHEMA",
    "CorpusError",
    "DATASET_NAME",
    "DATASET_VERSION",
    "SILVER_TIER",
    "SOURCE_TYPE_CATEGORY",
    "SOURCE_TYPE_MAP",
    "build_real_document_dataset",
    "corpus_document_paths",
    "corpus_manifest_path",
    "describe_corpus",
    "load_corpus",
    "sha256_file",
    "to_cases",
]
