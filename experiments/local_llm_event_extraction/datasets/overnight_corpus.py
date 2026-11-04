"""Turn the overnight public-regulatory corpus into a benchmark-ready dataset.

What makes this dataset's labels what they are
---------------------------------------------
Every gold event here is a **SOURCE_DERIVED_SILVER** label: the value was copied
from the same structured public record the document text was rendered from.  It is
independent of any model, which is what makes it usable for training at all, but
it is *not* independent of the document and it is *not* a human annotation.  So:

* precision / recall / F1 against it are **not** research-grade metrics and are
  never reported as such;
* agreement with it measures *reading fidelity* of a structured record, and for
  the ``synthetic_narrative`` stratum it additionally measures generalisation
  across surface form, because the narrative prose is generated from the record
  and the label is not copied from that prose.

Text provenance is a separate axis and is recorded per case:

``structural_rendering``
    the document text is a deterministic rendering of the record's own fields;
``synthetic_narrative``
    the document text is template-generated prose over the same fields.

Both are captured in ``SourceDocument.metadata["text_origin"]`` so every report
can stratify by them, which the phase-2 protocol requires.

Splits
------
Grouped by company, seeded, and never overlapping: a company's documents appear
in exactly one split, so the test split measures transfer to companies the model
never saw.  Negative-control records (FDA device classifications, which contain
no company action at all) are kept as their own group so they cannot leak.

The builder refuses instead of degrading: an integrity hash mismatch, an unmapped
company, an unknown date kind or a group crossing splits is an error, not a
skipped row.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..contracts import DatasetCase, DatasetManifest, GoldEvent
from ..schema import SOURCE_TYPES, SourceDocument

CORPUS_SCHEMA = "medradar.overnight_corpus.v1"
DATASET_NAME = "medradar-overnight-public-regulatory"
DATASET_VERSION = "v1"
SILVER_TIER = "source_record_derived"
DEFAULT_SEED = 20261104

#: corpus source type -> the frozen ``SOURCE_TYPES`` value.
SOURCE_TYPE_MAP: Mapping[str, str] = {
    "regulatory_clearance": "fda_510k",
    "regulatory_approval": "fda_pma",
    "recall": "fda_recall",
    "clinical_trial_registration": "clinical_trial_record",
    "regulatory_notice": "regulatory_notice",
}

#: corpus source type -> (event category, event-date kind) for silver events.
SILVER_SPEC: Mapping[str, tuple[str, str]] = {
    "regulatory_clearance": ("regulatory_clearance", "decision"),
    "regulatory_approval": ("regulatory_approval", "decision"),
    "recall": ("safety_recall", "recall_initiation"),
    # clinical trial rows carry their own kind in the silver block: a start date can
    # be ACTUAL or ANTICIPATED, and the completion / results-posting dates are
    # future-tolerant by nature.  That per-row kind is what the A3 fix consumes.
    "clinical_trial_registration": ("clinical_trial_start", "trial_start_actual"),
    "regulatory_notice": ("other", "unspecified"),
}

COMPANY_DISPLAY: Mapping[str, str] = {
    "medtronic": "Medtronic",
    "philips": "Royal Philips / Philips Healthcare",
    "siemens_healthineers": "Siemens Healthineers",
    "ge_healthcare": "GE HealthCare",
    "abbott": "Abbott",
    "baxter": "Baxter",
    "bd": "Becton Dickinson",
    "boston_scientific": "Boston Scientific",
    "stryker": "Stryker",
    "zimmer_biomet": "Zimmer Biomet",
    "edwards_lifesciences": "Edwards Lifesciences",
    "hologic": "Hologic",
}


class CorpusError(ValueError):
    """The overnight corpus is missing, malformed, or was edited after collection."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_corpus(corpus_dir: str | Path) -> tuple[dict[str, Any], ...]:
    directory = Path(corpus_dir)
    manifest_path = directory / "MANIFEST.json"
    if not manifest_path.is_file():
        raise CorpusError(f"corpus manifest not found: {manifest_path}")
    documents_dir = directory / "documents"
    if not documents_dir.is_dir():
        raise CorpusError(f"corpus has no documents/ directory: {directory}")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(documents_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise CorpusError(f"{path.name}: record must be an object")
        record = dict(payload)
        doc_id = str(record.get("doc_id") or "").strip()
        if not doc_id:
            raise CorpusError(f"{path.name}: missing doc_id")
        if doc_id in seen:
            raise CorpusError(f"duplicate doc_id {doc_id!r}")
        seen.add(doc_id)
        if str(record.get("source_type")) not in SOURCE_TYPE_MAP:
            raise CorpusError(f"{doc_id}: unmapped source_type {record.get('source_type')!r}")
        text = record.get("text")
        if not isinstance(text, str) or len(text) < 200:
            raise CorpusError(f"{doc_id}: text must be a string of at least 200 characters")
        expected = str(record.get("content_sha256") or "").lower()
        actual = _sha256_text(text)
        if expected != actual:
            raise CorpusError(
                f"{doc_id}: content_sha256 mismatch; the corpus was edited after collection"
            )
        locale = str(record.get("date_locale") or "").strip().lower()
        if locale not in ("iso", "us", "uk"):
            raise CorpusError(f"{doc_id}: undeclared or unknown date_locale {locale!r}")
        records.append(record)
    if not records:
        raise CorpusError(f"corpus contains no documents: {directory}")
    return tuple(records)


def corpus_fingerprint(corpus_dir: str | Path) -> dict[str, Any]:
    directory = Path(corpus_dir)
    manifest_bytes = (directory / "MANIFEST.json").read_bytes()
    document_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((directory / "documents").glob("*.json"))
    }
    combined = hashlib.sha256(
        manifest_bytes + b"\x00" + "".join(document_hashes[name] for name in sorted(document_hashes)).encode()
    ).hexdigest()
    manifest = json.loads(manifest_bytes)
    return {
        "corpus_dir": str(directory),
        "corpus_version": manifest.get("version"),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "document_file_hashes": document_hashes,
        "corpus_sha256": combined,
        "document_count": len(document_hashes),
    }


def _company_hint(canonical_id: str) -> str:
    display = COMPANY_DISPLAY.get(canonical_id)
    if display is None:
        raise CorpusError(f"unmapped company_canonical_id {canonical_id!r}")
    return f"{display} [canonical_id: {canonical_id}]"


def _to_case(record: Mapping[str, Any]) -> DatasetCase:
    doc_id = str(record["doc_id"])
    source_type = SOURCE_TYPE_MAP[str(record["source_type"])]
    if source_type not in SOURCE_TYPES:  # pragma: no cover - guarded by SOURCE_TYPE_MAP
        raise CorpusError(f"{doc_id}: mapped source_type {source_type!r} is not declared")
    negative = bool(record.get("negative_control"))
    canonical_id = str(record.get("company_canonical_id") or "").strip()
    if not negative and not canonical_id:
        raise CorpusError(f"{doc_id}: a labelled record must carry a company_canonical_id")
    metadata: dict[str, str] = {
        "company_canonical_id": canonical_id,
        "company_hint": _company_hint(canonical_id) if canonical_id else "",
        "date_locale": str(record["date_locale"]),
        "text_style": str(record.get("text_style") or "field_value_rendering"),
        "text_origin": str(record.get("text_origin") or "structural_rendering"),
        "corpus_doc_id": doc_id,
        "corpus_source_type": str(record["source_type"]),
        "content_sha256": str(record["content_sha256"]),
        "record_type": str(record.get("record_type") or ""),
        "retrieved_at": str(record.get("retrieved_at") or ""),
        "api_endpoint": str(record.get("api_endpoint") or ""),
    }
    document = SourceDocument(
        doc_id=doc_id,
        source_type=source_type,
        text=str(record["text"]),
        title=record.get("title"),
        published_at=record.get("source_publication_date") or None,
        first_seen_at=None,
        retrieved_at=record.get("retrieved_at"),
        url=record.get("url"),
        publisher=record.get("publisher"),
        metadata=metadata,
    )

    gold: tuple[GoldEvent, ...] = ()
    tier = "unlabelled"
    if not negative:
        silver = record.get("silver")
        if not isinstance(silver, Mapping):
            raise CorpusError(f"{doc_id}: a non-negative record must carry a silver block")
        spec_category, spec_kind = SILVER_SPEC[str(record["source_type"])]
        category = str(silver.get("event_category") or spec_category)
        kind = str(silver.get("event_date_kind") or spec_kind)
        quote = str(silver.get("evidence_quote") or "")
        if not quote or quote not in str(record["text"]):
            raise CorpusError(
                f"{doc_id}: silver evidence_quote is not a verbatim substring of the document"
            )
        event_date = str(silver.get("event_date") or "")
        if len(event_date) != 10:
            raise CorpusError(f"{doc_id}: silver event_date must be YYYY-MM-DD")
        gold = (
            GoldEvent(
                event_id=f"{doc_id}-silver",
                company_canonical_id=canonical_id,
                event_category=category,
                event_date=event_date,
                published_at=record.get("source_publication_date") or None,
                product_or_technology=(str(silver.get("product_or_technology") or "") or None),
                technology_domains=(),
                evidence_quote=quote,
                label_tier=SILVER_TIER,
                label_source=str(silver.get("label_source") or "source record field"),
            ),
        )
        tier = SILVER_TIER

    group = canonical_id if canonical_id else "negative_controls"
    case = DatasetCase(
        case_id=doc_id,
        document=document,
        gold_events=gold,
        expected_abstain=negative,
        label_tier=tier,
        group=group,
        split="unassigned",
    )
    # The per-row date kind is not part of GoldEvent (the contract is frozen), so it
    # is carried on the document metadata where the validator and the trainer read it.
    metadata["event_date_kind"] = str((record.get("silver") or {}).get("event_date_kind") or "")
    return case


def _hash_fraction(seed: int, group: str) -> float:
    digest = hashlib.sha256(f"{seed}|{group}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


@dataclass(frozen=True)
class SplitPlan:
    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "train": list(self.train),
            "validation": list(self.validation),
            "test": list(self.test),
        }


def plan_splits(groups: Sequence[str], *, seed: int = DEFAULT_SEED) -> SplitPlan:
    """Assign whole companies to splits by a seeded hash order.

    ``negative_controls`` is always test-only: those records exist to measure
    false assertion / abstention, and mixing them into training would make the
    abstention metric a memorisation check rather than a behaviour check.  That
    limitation is recorded in the dataset notes instead of being hidden.
    """
    companies = sorted({group for group in groups if group != "negative_controls"})
    if len(companies) < 3:
        raise CorpusError(
            f"need at least 3 companies for a grouped three-way split, got {companies}"
        )
    ordered = sorted(companies, key=lambda group: (_hash_fraction(seed, group), group))
    total = len(ordered)
    n_test = max(1, round(total * 0.2))
    n_val = max(1, round(total * 0.2))
    n_train = total - n_val - n_test
    if n_train < 1:
        raise CorpusError(f"{total} companies cannot fill three non-empty splits")
    return SplitPlan(
        train=tuple(ordered[:n_train]),
        validation=tuple(ordered[n_train : n_train + n_val]),
        test=tuple(ordered[n_train + n_val :]),
    )


def build_dataset(
    corpus_dir: str | Path,
    *,
    seed: int = DEFAULT_SEED,
    max_docs_per_split: Mapping[str, int] | None = None,
) -> tuple[DatasetManifest, dict[str, Any]]:
    """Build the manifest plus an audit record describing exactly how it was built."""
    records = load_corpus(corpus_dir)
    cases = [_to_case(record) for record in records]
    # Split over near-duplicate leakage components, not raw companies: templated
    # structural renderings of the same source type are >80% shingle-identical
    # across companies, so a company-only split would leak the template.
    from .components import assign_component_splits

    assigned, component_audit = assign_component_splits(cases, seed=seed)
    plan = SplitPlan(
        train=tuple(sorted({case.group for case in assigned if case.split == "train"})),
        validation=tuple(
            sorted({case.group for case in assigned if case.split == "validation"})
        ),
        test=tuple(sorted({case.group for case in assigned if case.split == "test"})),
    )

    caps = dict(max_docs_per_split or {})
    if caps:
        kept: list[DatasetCase] = []
        for split in ("train", "validation", "test"):
            pool = [case for case in assigned if case.split == split]
            cap = caps.get(split)
            if cap is None or len(pool) <= cap:
                kept.extend(pool)
                continue
            # Deterministic, stratified cap: keep the order of source types and text
            # styles so a cap never silently drops an entire stratum.
            pool.sort(
                key=lambda case: (
                    str(case.document.metadata.get("text_origin")),
                    case.document.source_type,
                    case.case_id,
                )
            )
            step = len(pool) / cap
            kept.extend(pool[min(int(index * step), len(pool) - 1)] for index in range(cap))
            kept = list({case.case_id: case for case in kept}.values())
        assigned = kept

    from .splits import assert_no_leakage

    manifest = DatasetManifest(
        name=DATASET_NAME,
        version=DATASET_VERSION,
        cases=tuple(assigned),
        source_paths=(str(Path(corpus_dir) / "MANIFEST.json"), str(Path(corpus_dir) / "documents")),
        source_sha256=corpus_fingerprint(corpus_dir)["corpus_sha256"],
        notes=(
            "Public regulatory records (openFDA 510(k)/PMA/recall, ClinicalTrials.gov), "
            "rendered deterministically. Labels are SOURCE_DERIVED_SILVER: copied from the "
            "records' own fields, independent of any model, NOT human labels. Accuracy "
            "against them is exploratory agreement, never precision/recall/F1. Splits are "
            "grouped by company; negative controls (device classifications with no company "
            "action) are test-only, so abstention there is a behaviour measurement."
        ),
    )
    leakage_error: str | None = None
    try:
        assert_no_leakage(manifest)
        leakage_status = "ok"
    except ValueError as exc:
        leakage_status = "FAILED"
        leakage_error = str(exc)
        if "group leakage" in str(exc):
            raise CorpusError(f"the split plan leaks a group: {exc}") from exc

    by_split: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}
    by_style: dict[str, dict[str, int]] = {}
    by_origin: dict[str, dict[str, int]] = {}
    by_kind: dict[str, dict[str, int]] = {}
    by_locale: dict[str, int] = {}
    by_format: dict[str, int] = {}
    for case in manifest.cases:
        by_split[case.split] = by_split.get(case.split, 0) + 1
        by_source.setdefault(case.split, {})
        key = case.document.source_type
        by_source[case.split][key] = by_source[case.split].get(key, 0) + 1
        style = str(case.document.metadata.get("text_style"))
        by_style.setdefault(case.split, {})
        by_style[case.split][style] = by_style[case.split].get(style, 0) + 1
        origin = str(case.document.metadata.get("text_origin"))
        by_origin.setdefault(case.split, {})
        by_origin[case.split][origin] = by_origin[case.split].get(origin, 0) + 1
        kind = str(case.document.metadata.get("event_date_kind") or "none")
        by_kind.setdefault(case.split, {})
        by_kind[case.split][kind] = by_kind[case.split].get(kind, 0) + 1
        locale = str(case.document.metadata.get("date_locale"))
        by_locale[locale] = by_locale.get(locale, 0) + 1
        for record in records:
            if record["doc_id"] == case.case_id and record.get("silver"):
                fmt = str((record.get("silver") or {}).get("date_text_format"))
                by_format[fmt] = by_format.get(fmt, 0) + 1
                break

    audit = {
        "corpus": corpus_fingerprint(corpus_dir),
        "seed": seed,
        "split_plan": plan.to_dict(),
        "split_method": component_audit,
        "negative_control_policy": "test-only",
        "label_tier": SILVER_TIER,
        "leakage_audit": {"status": leakage_status, "detail": leakage_error},
        "counts": {
            "total": manifest.case_count,
            "by_split": dict(sorted(by_split.items())),
            "by_source_type": {key: dict(sorted(value.items())) for key, value in sorted(by_source.items())},
            "by_text_style": {key: dict(sorted(value.items())) for key, value in sorted(by_style.items())},
            "by_text_origin": {key: dict(sorted(value.items())) for key, value in sorted(by_origin.items())},
            "by_event_date_kind": {key: dict(sorted(value.items())) for key, value in sorted(by_kind.items())},
            "by_date_locale": dict(sorted(by_locale.items())),
            "by_date_text_format": dict(sorted(by_format.items())),
        },
    }
    return manifest, audit


__all__ = [
    "CORPUS_SCHEMA",
    "DATASET_NAME",
    "DATASET_VERSION",
    "CorpusError",
    "SILVER_TIER",
    "SILVER_SPEC",
    "SOURCE_TYPE_MAP",
    "SplitPlan",
    "build_dataset",
    "corpus_fingerprint",
    "load_corpus",
    "plan_splits",
]
