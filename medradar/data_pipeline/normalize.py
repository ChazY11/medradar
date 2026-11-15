"""Deterministic normalisation and hashing of official openFDA device records.

The full normalised record (including every non-``openfda`` source field) is hashed before
display compaction. A correction to a long free-text field is therefore detected even when
the product snapshot truncates that field for display.

Four times remain distinct:

* ``event_date``: the regulatory event date stated by FDA (decision date / recall initiation);
* ``published_at``: a source publication date, only where the source states one;
* ``first_observed_at``: when MedRadar first saw the record, preserved across snapshots;
* ``last_synced_at``: the most recent successful reconciliation, not an event date.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from typing import Any, Iterable, Sequence

from .model import SOURCES

METADATA_FIELDS = {
    "first_observed_at",
    "last_synced_at",
    "source_updated_at",
    "record_state",
    "missing_count",
    "collection_scopes",
    "content_hash",
    "snapshot_hash",
}

RAW_LIMITS = {
    "action": 300,
    "distribution_pattern": 200,
    "code_info": 200,
    "product_quantity": 80,
    "product_description": 300,
    "reason_for_recall": 400,
    "statement_or_summary": 200,
    "ao_statement": 240,
    "trade_name": 160,
    "generic_name": 160,
    "supplement_reason": 140,
    "supplement_type": 80,
    "decision_description": 120,
    "advisory_committee_description": 80,
    "additional_info_contact": 200,
}
SUMMARY_LIMIT = 400
DEVICE_NAME_LIMIT = 220
MIN_PLAUSIBLE_YEAR = 1900


def clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value if item not in (None, ""))
    text = " ".join(str(value).split())
    return text or None


def multiline(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\r", " ").split("\n"))
    text = " ".join(text.split())
    return text or None


def _raw_fields(record: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for key, value in record.items():
        if key == "openfda" or value in (None, ""):
            continue
        if key == "k_numbers":
            if isinstance(value, list):
                raw[key] = sorted({str(item).strip() for item in value if str(item).strip()})
            continue
        if isinstance(value, list):
            raw[key] = [clean(item) for item in value if clean(item) is not None]
            continue
        if isinstance(value, str) and ("\n" in value or "\r" in value):
            raw[key] = multiline(value)
        else:
            raw[key] = clean(value)
    return {key: value for key, value in raw.items() if value not in (None, "", [])}


def normalise_510k(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw_fields(record)
    k_number = str(raw.get("k_number") or "").strip().upper()
    decision = raw.get("decision_date")
    device = str(raw.get("device_name") or "")
    source = SOURCES["openfda_510k"]
    return {
        "event_id": "openfda_510k:" + k_number,
        "source_id": "openfda_510k",
        "event_type": "510k",
        "official_id": k_number,
        "event_date": decision,
        "published_at": None,
        "published_at_status": "not_published_by_source",
        "time_quality": "date_from_source" if decision else "unknown",
        "applicant_name": str(raw.get("applicant") or ""),
        "product_code": raw.get("product_code"),
        "device_name": raw.get("device_name"),
        "summary": raw.get("statement_or_summary"),
        "title": (k_number + " " + device).strip(),
        "official_url": source.official_url(k_number, raw),
        "raw": raw,
    }


def normalise_pma(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw_fields(record)
    pma_number = str(raw.get("pma_number") or "").strip().upper()
    supplement = str(raw.get("supplement_number") or "").strip().upper()
    is_original = supplement in ("", "0", "-", "S000")
    official_id = pma_number if is_original else pma_number + ":" + supplement
    decision = raw.get("decision_date")
    summary = raw.get("generic_name")
    if raw.get("trade_name"):
        summary = (str(summary) + " - " + str(raw["trade_name"])) if summary else str(raw["trade_name"])
    if not is_original and raw.get("supplement_type"):
        summary = (str(summary) + " (" + str(raw["supplement_type"]) + ")") if summary else str(raw["supplement_type"])
    device = raw.get("generic_name") or raw.get("trade_name") or ""
    label = pma_number if is_original else pma_number + " " + supplement
    source = SOURCES["openfda_pma"]
    return {
        "event_id": "openfda_pma:" + official_id,
        "source_id": "openfda_pma",
        "event_type": "pma" if is_original else "pma_supplement",
        "official_id": official_id,
        "event_date": decision,
        "published_at": None,
        "published_at_status": "not_published_by_source",
        "time_quality": "date_from_source" if decision else "unknown",
        "applicant_name": str(raw.get("applicant") or ""),
        "product_code": raw.get("product_code"),
        "device_name": device or None,
        "summary": summary,
        "title": (label + " " + str(device)).strip(),
        "official_url": source.official_url(official_id, raw),
        "raw": raw,
    }


def normalise_recall(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw_fields(record)
    product_res = str(raw.get("product_res_number") or "").strip()
    event_number = str(raw.get("res_event_number") or "").strip()
    cfres = str(raw.get("cfres_id") or "").strip()
    official_id = product_res or cfres or event_number
    initiated = raw.get("event_date_initiated")
    posted = raw.get("event_date_posted")
    if initiated:
        event_date, time_quality = initiated, "date_from_source"
    elif posted:
        event_date, time_quality = posted, "date_derived_from_source"
    else:
        event_date, time_quality = None, "unknown"
    device = raw.get("product_description") or ""
    source = SOURCES["openfda_recall"]
    return {
        "event_id": "openfda_recall:" + official_id,
        "source_id": "openfda_recall",
        "event_type": "recall",
        "official_id": official_id,
        "event_date": event_date,
        "published_at": posted,
        "published_at_status": "from_source" if posted else "not_published_by_source",
        "time_quality": time_quality,
        "applicant_name": str(raw.get("recalling_firm") or ""),
        "product_code": raw.get("product_code"),
        "device_name": raw.get("product_description"),
        "summary": raw.get("reason_for_recall"),
        "title": (official_id + " " + str(device)).strip(),
        "official_url": source.official_url(official_id, raw),
        "raw": raw,
    }


NORMALISERS = {
    "openfda_510k": normalise_510k,
    "openfda_pma": normalise_pma,
    "openfda_recall": normalise_recall,
}

SOURCE_FOR_EVENT = {
    "510k": "openfda_510k",
    "pma": "openfda_pma",
    "pma_supplement": "openfda_pma",
    "recall": "openfda_recall",
}


def normalise_record(source_id: str, record: dict[str, Any]) -> dict[str, Any]:
    try:
        normaliser = NORMALISERS[source_id]
    except KeyError as error:
        raise ValueError("unknown source_id: " + source_id) from error
    return normaliser(record)


def canonical_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in METADATA_FIELDS}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(canonical_payload(event)).encode("utf-8")).hexdigest()


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _plausible_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        year = int(str(value)[:4])
    except ValueError:
        return False
    return MIN_PLAUSIBLE_YEAR <= year <= 2100


def compact_event(event: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return the product-facing event and quality flags.

    The source content hash is preserved from the full record; only displayed text is
    bounded. Nothing is added to the raw source fields.
    """
    flags: list[str] = []
    result = dict(event)
    raw = dict(result.get("raw") or {})
    for key, limit in RAW_LIMITS.items():
        if key in raw:
            raw[key] = _truncate(raw.get(key) if isinstance(raw.get(key), str) else clean(raw.get(key)), limit)
    for key in list(raw.keys()):
        if raw[key] in (None, ""):
            raw.pop(key)
    if not _plausible_date(result.get("event_date")):
        if result.get("event_date"):
            flags.append("implausible_event_date")
            raw["event_date_as_published"] = result.get("event_date")
        result["event_date"] = None
        result["time_quality"] = "unknown"
    result["device_name"] = _truncate(result.get("device_name"), DEVICE_NAME_LIMIT)
    result["summary"] = _truncate(result.get("summary"), SUMMARY_LIMIT)
    result.pop("title", None)
    result["raw"] = raw
    return result, flags


def snapshot_hash(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "snapshot_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_applicants(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    applicants: dict[str, dict[str, Any]] = {}
    for event in events:
        name = str(event.get("applicant_name") or "")
        if not name:
            continue
        bucket = applicants.setdefault(
            name,
            {"applicant_name": name, "records": 0, "by_source": {}, "by_org_scope": {}},
        )
        bucket["records"] += 1
        source = str(event["source_id"])
        bucket["by_source"][source] = bucket["by_source"].get(source, 0) + 1
        scopes = event.get("collection_scopes") or []
        for scope in scopes:
            if scope:
                bucket["by_org_scope"][scope] = bucket["by_org_scope"].get(scope, 0) + 1
    return [applicants[name] for name in sorted(applicants)]


def normalise_classification(record: dict[str, Any]) -> dict[str, Any] | None:
    code = clean(record.get("product_code"))
    if not code:
        return None
    return {
        "product_code": code,
        "device_name": clean(record.get("device_name")),
        "specialty": clean(record.get("medical_specialty_description")) or clean(record.get("review_panel")),
        "device_class": clean(record.get("device_class")),
        "regulation_number": clean(record.get("regulation_number")),
        "implant_flag": clean(record.get("implant_flag")),
        "life_sustaining": clean(record.get("life_sustain_support_flag")),
    }


def build_classifications(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        row = normalise_classification(record)
        if row is None or row["product_code"] in seen:
            continue
        seen.add(row["product_code"])
        rows.append(row)
    return sorted(rows, key=lambda item: str(item["product_code"]))
