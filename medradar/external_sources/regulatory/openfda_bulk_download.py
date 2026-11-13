"""openFDA bulk export connector (``api.fda.gov/download.json``).

The manifest is the only openFDA artefact that carries a **snapshot clock**:
each endpoint lists an ``export_date`` plus per-partition record counts.  That
``export_date`` describes the whole export, so it is *not* a publication date for
individual records - it is recorded in ``normalized.export_date`` and
``provenance.source_time_quality`` and kept out of the two record clocks.

Partitions are served as ``.json.zip`` from ``download.open.fda.gov``.  Sizes are
hostile (device/510k is a 238.55 MB single file), so this connector refuses to
pull anything above ``max_zip_bytes`` and says so instead of silently
truncating a zip.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Mapping, Sequence

from .. import schema
from . import _common, openfda_device_510k, openfda_device_pma, openfda_device_classification

SOURCE_ID = "openfda_bulk_download"
KIND = "device_registration"
LICENCE_STATUS = "public_domain"

MANIFEST_URL = "https://api.fda.gov/download.json"
SOURCE_URL = "https://open.fda.gov/apis/downloads/"

#: endpoint -> (normalizer module, evidence kind)
_NORMALIZERS: dict[str, Any] = {
    "510k": openfda_device_510k,
    "pma": openfda_device_pma,
    "classification": openfda_device_classification,
}


def device_exports(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Project the manifest onto the ``device`` endpoint exports."""
    results = manifest.get("results") or {}
    device = results.get("device") or {}
    out: dict[str, Any] = {}
    for name, block in device.items():
        if not isinstance(block, Mapping):
            continue
        out[str(name)] = {
            "export_date": _common.clean(block.get("export_date")),
            "total_records": block.get("total_records"),
            "partitions": [
                {
                    "file": _common.clean(part.get("file")),
                    "size_mb": part.get("size_mb"),
                    "records": part.get("records"),
                }
                for part in block.get("partitions") or []
                if isinstance(part, Mapping)
            ],
        }
    return out


def manifest(client: Any) -> dict[str, Any]:
    """Fetch and project the official export manifest (one request)."""
    result = client.get(MANIFEST_URL)
    if not result.ok:
        raise RuntimeError(f"download.json returned HTTP {result.status}: {result.error}")
    return device_exports(result.json())


def fetch_partition(
    client: Any, url: str, *, max_zip_bytes: int = 6 * 1024 * 1024
) -> list[dict[str, Any]]:
    """Download one export zip and return its records, refusing oversized files."""
    result = client.get(url, accept="application/zip")
    if not result.ok:
        raise RuntimeError(f"partition {url} returned HTTP {result.status}: {result.error}")
    if len(result.body) > max_zip_bytes:
        raise ValueError(
            f"partition {url} is {len(result.body)} bytes, above the {max_zip_bytes}-byte connector cap"
        )
    with zipfile.ZipFile(io.BytesIO(result.body)) as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith(".json"):
                continue
            with archive.open(info) as handle:
                payload = json.loads(handle.read().decode("utf-8", "replace"))
            if isinstance(payload, Mapping):
                return [row for row in payload.get("results") or [] if isinstance(row, Mapping)]
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, Mapping)]
    return []


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    endpoint: str,
    export_date: str = "",
    fetched_at: str = "",
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One record from an export partition -> one evidence record.

    Delegated to the per-endpoint connector so a bulk record and an API record
    for the same submission produce the *same* ``evidence_id``; only the
    snapshot metadata differs.
    """
    module = _NORMALIZERS.get(endpoint)
    if module is None:
        raise ValueError(f"no bulk normalizer for endpoint {endpoint!r}")
    record = module.to_evidence(
        raw_item, fetched_at=fetched_at, collection_run_id=collection_run_id
    )
    record["normalized"]["export_date"] = export_date
    record["normalized"]["acquisition_mode"] = "bulk_export"
    # The export date is a snapshot clock, not a publication date: keep it out of
    # the record clocks and re-derive content hashes the schema depends on.
    record["content_hash"] = schema.sha256_json(record["normalized"])
    record["provenance"]["normalized_content_hash"] = record["content_hash"]
    record["provenance"]["evidence_reference"] = SOURCE_URL
    return record


def collect(
    client: Any,
    *,
    endpoint: str = "classification",
    limit: int = 50,
    max_pages: int = 1,
    max_zip_bytes: int = 6 * 1024 * 1024,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Download ``max_pages`` export partitions of ``endpoint`` and normalise them."""
    exports = manifest(client)
    block = exports.get(endpoint)
    if not block:
        raise KeyError(f"endpoint {endpoint!r} not present in the export manifest")
    export_date = block.get("export_date", "")
    out: list[dict[str, Any]] = []
    for part in block.get("partitions", [])[: max(0, int(max_pages))]:
        url = str(part.get("file", ""))
        if not url.startswith("https://"):
            continue
        for item in fetch_partition(client, url, max_zip_bytes=max_zip_bytes):
            out.append(
                to_evidence(
                    item,
                    endpoint=endpoint,
                    export_date=export_date,
                    fetched_at=fetched_at,
                    collection_run_id=collection_run_id,
                )
            )
            if len(out) >= limit:
                return out
    return out


__all__: Sequence[str] = [
    "SOURCE_ID",
    "KIND",
    "LICENCE_STATUS",
    "MANIFEST_URL",
    "collect",
    "device_exports",
    "fetch_partition",
    "manifest",
    "to_evidence",
]
