"""GUDID release-file connector (NLM daily / weekly / monthly / full releases).

The release files are the only GUDID artefact that yields a reproducible snapshot
*plus* change stream, and the only device source that states the change window it
covers (``header/period/@start`` to ``@end``, declared by the source itself).

Date semantics
--------------
``devicePublishDate`` (per record) is a real first-publication date -> clock.
``publicVersionDate`` is a version stamp -> kept in ``normalized``, never used as
a clock.
``header/creationDate`` dates the *file*, not the record.

The XML is namespaced; records are matched namespace-agnostically.  A plain
``b"<device>"`` count returns 0 on real files (verified: 0 vs 5,548), which is
exactly the kind of silent under-count this parser must avoid.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Iterator, Mapping, Sequence
from xml.etree import ElementTree

from .. import identity
from . import _common

SOURCE_ID = "fda_gudid_download"
KIND = "device_registration"
LICENCE_STATUS = "open_licence"

DOWNLOAD_ROOT = "https://accessgudid.nlm.nih.gov/release_files/download/"
SOURCE_URL = "https://accessgudid.nlm.nih.gov/download"

PROVENANCE: dict[str, Any] = {
    "source_name": "GUDID release files (U.S. FDA / NLM AccessGUDID)",
    "licence_status": "open_licence",
    "redistribution": "allowed",
    "attribution": "GUDID data, U.S. Food and Drug Administration / NLM AccessGUDID",
    "evidence_reference": SOURCE_URL,
    "source_time_quality": "day",
}


def _local(tag: str) -> str:
    """Namespace-agnostic local name of an ElementTree tag."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(element: ElementTree.Element, name: str) -> str:
    for child in element:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def release_header(xml_bytes: bytes) -> dict[str, Any]:
    """Read the ``<header>`` block of a release file without loading every record."""
    head = xml_bytes[:8000].decode("utf-8", "replace")
    import re

    def first(pattern: str) -> str:
        match = re.search(pattern, head)
        return match.group(1) if match else ""

    return {
        "frequency": first(r'frequency="([^"]+)"'),
        "database_type": first(r'type="([^"]+)"'),
        "database_id": first(r'<database[^>]*id="([^"]+)"'),
        "creation_date": first(r"<creationDate>([^<]+)</creationDate>"),
        "period_start": first(r'<period[^>]*start="([^"]+)"'),
        "period_end": first(r'<period[^>]*end="([^"]+)"'),
        "declared_records": first(r"<numberRecordXML>(\d+)</numberRecordXML>"),
    }


def iter_devices(xml_bytes: bytes) -> Iterator[ElementTree.Element]:
    """Yield every ``<device>`` element regardless of XML namespace."""
    for _event, element in ElementTree.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if _local(element.tag) == "device":
            yield element
            element.clear()


def normalize(element: ElementTree.Element, *, header: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Project one GUDID ``<device>`` element onto the fields we store."""
    identifiers: list[dict[str, Any]] = []
    brand = ""
    company = ""
    version_model = ""
    gmdn: list[str] = []
    premarket: list[str] = []
    for child in element:
        name = _local(child.tag)
        if name == "identifiers":
            for ident in child:
                if _local(ident.tag) != "identifier":
                    continue
                di = _child_text(ident, "deviceId")
                identifiers.append(
                    {
                        "device_id": di,
                        "device_id_type": _child_text(ident, "deviceIdType"),
                        "device_id_issuing_agency": _child_text(ident, "deviceIdIssuingAgency"),
                        "pkg_quantity": _child_text(ident, "pkgQuantity"),
                        "pkg_type": _child_text(ident, "pkgType"),
                    }
                )
        elif name == "brandName":
            brand = (child.text or "").strip()
        elif name == "companyName":
            company = (child.text or "").strip()
        elif name == "versionOrModelNumber":
            version_model = (child.text or "").strip()
        elif name == "gmdnTerms":
            for term in child.iter():
                if _local(term.tag) == "gmdnPTName" and (term.text or "").strip():
                    gmdn.append((term.text or "").strip())
        elif name == "premarketSubmissions":
            for submission in child:
                number = _child_text(submission, "submissionNumber")
                if number:
                    premarket.append(number)
    return {
        "public_device_record_key": _child_text(element, "publicDeviceRecordKey"),
        "public_version_status": _child_text(element, "publicVersionStatus"),
        "device_record_status": _child_text(element, "deviceRecordStatus"),
        "public_version_number": _child_text(element, "publicVersionNumber"),
        "public_version_date": _child_text(element, "publicVersionDate"),
        "device_publish_date": _child_text(element, "devicePublishDate"),
        "device_comm_distribution_status": _child_text(element, "deviceCommDistributionStatus"),
        "device_comm_distribution_end_date": _child_text(element, "deviceCommDistributionEndDate"),
        "brand_name": brand,
        "company_name": company,
        "version_or_model_number": version_model,
        "gmdn_terms": sorted(set(gmdn)),
        "premarket_submissions": sorted(set(premarket)),
        "identifier_count": len(identifiers),
        "identifiers": identifiers,
        "release_header": dict(header or {}),
    }


def record_key(normalized: Mapping[str, Any]) -> str:
    key = str(normalized.get("public_device_record_key", "")).strip()
    if key:
        return key
    ids = normalized.get("identifiers") or []
    if ids:
        return str(ids[0].get("device_id", "")).strip()
    raise ValueError("GUDID device record without publicDeviceRecordKey and without any DI")


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One normalised GUDID device -> one evidence record."""
    normalized = dict(raw_item)
    key = record_key(normalized)
    ids: list[dict[str, Any]] = []
    for row in normalized.get("identifiers") or []:
        ids.append(
            identity.build_identifier(
                "di",
                row.get("device_id"),
                is_primary=str(row.get("device_id_type", "")).lower() == "primary",
                note=_common.clean(row.get("device_id_issuing_agency")),
            )
        )
    for number in normalized.get("premarket_submissions") or []:
        scheme = "510k" if str(number).upper().startswith("K") else "pma"
        ids.append(identity.build_identifier(scheme, number))
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for ident in _common.identifiers(ids):
        unique[(ident["scheme"], ident["value"])] = ident
    idents = list(unique.values())
    if not idents:  # pragma: no cover - defensive
        raise ValueError(f"GUDID record {key} carries no usable identifier")
    time_block = _common.build_time(
        event_at=None,
        source_public_at=normalized.get("device_publish_date"),
        fetched_at=fetched_at,
        quality="day",
        note=(
            "devicePublishDate is GUDID's per-record first-publication date; publicVersionDate is "
            "a version stamp and release_header.creation_date dates the file, not the record"
        ),
    )
    return _common.openfda_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=key,
        source_url=DOWNLOAD_ROOT + str((normalized.get("release_header") or {}).get("file", "")),
        normalized=normalized,
        item=normalized,
        time_block=time_block,
        identifiers=idents,
        entity_refs=_common.company_refs(normalized.get("company_name")),
        fetched_at=fetched_at,
        collection_run_id=collection_run_id,
        provenance=PROVENANCE,
    )


def read_release(zip_bytes: bytes) -> tuple[dict[str, Any], bytes, str]:
    """Open a release zip; return ``(header, xml_bytes, member_name)``."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        member = next(
            (i for i in archive.infolist() if i.filename.lower().endswith(".xml")), None
        )
        if member is None:
            raise ValueError("GUDID release zip contains no XML member")
        with archive.open(member) as handle:
            xml_bytes = handle.read()
    header = release_header(xml_bytes)
    header["file"] = member.filename
    return header, xml_bytes, member.filename


def collect(
    client: Any,
    *,
    file_name: str = "",
    limit: int = 50,
    max_zip_bytes: int = 8 * 1024 * 1024,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Download one release file and normalise up to ``limit`` device records.

    ``file_name`` must be an explicit release file (e.g.
    ``gudid_daily_update_20261102.zip``): the download page lists them, and
    guessing a name would silently produce a 404-shaped "no data" answer.
    """
    if not file_name:
        raise ValueError("collect() needs an explicit GUDID release file_name")
    result = client.get(DOWNLOAD_ROOT + file_name, accept="application/zip")
    if not result.ok:
        raise RuntimeError(f"GUDID release {file_name} returned HTTP {result.status}: {result.error}")
    if len(result.body) > max_zip_bytes:
        raise ValueError(
            f"GUDID release {file_name} is {len(result.body)} bytes, above the "
            f"{max_zip_bytes}-byte connector cap"
        )
    header, xml_bytes, member = read_release(result.body)
    header["file"] = member
    out: list[dict[str, Any]] = []
    for element in iter_devices(xml_bytes):
        out.append(
            to_evidence(
                normalize(element, header=header),
                fetched_at=fetched_at,
                collection_run_id=collection_run_id,
            )
        )
        if len(out) >= limit:
            break
    return out


__all__: Sequence[str] = [
    "SOURCE_ID",
    "KIND",
    "LICENCE_STATUS",
    "DOWNLOAD_ROOT",
    "collect",
    "iter_devices",
    "normalize",
    "read_release",
    "release_header",
    "to_evidence",
]
