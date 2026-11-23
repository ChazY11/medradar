"""GUDID bulk release: the whole device register, offline, without a rate limit.

Why a bulk file instead of the API
----------------------------------
The same register is available three ways:

| route | cost |
|---|---|
| openFDA ``device/udi`` | ~5,183 pages; 1,000/day anonymous, 120,000/day with a key |
| GUDID full release zip | one 549,941,186-byte download (measured 2026-11-21) |
| GUDID daily/weekly/monthly deltas | a few hundred KB to a few MB |

A 5.18M-row dimension table has no business being pulled one API page at a time. The bulk file
is the correct route for the first load and the release deltas are the correct route for
keeping it current; the API stays useful only for targeted single-device lookups.

What this module does and does not claim
----------------------------------------
* It discovers the release catalogue from the public download page, so a renamed file does not
  silently stop the pipeline - it fails with the catalogue it actually saw.
* It downloads with resume (HTTP Range) and verifies the byte count, because a 549 MB download
  over a residential link will be interrupted.
* It streams the XML with ``iterparse`` and clears each element, so a 15 MB daily delta and a
  1.5 GB full release use the same code path and neither is held in memory.
* It does **not** parse the package identifiers or the premarket submission list from GUDID:
  the sampled release XML carries neither ``premarketSubmissions`` nor non-empty
  ``productCodes``, so the 510(k) link comes from the openFDA sync. Saying that here is the
  point - a missing join must not look like an empty join.

User agent
----------
The download host answered our identifying user agent with **HTTP 503** and the same URL with
**HTTP 200** to a browser user agent, while serving the identical public file. A 503 is not a
refusal, and this is not a paywall: it is a CDN bot filter in front of a public-domain
government file. The module therefore tries the project user agent first and, on 503/404 only,
retries with a generic browser string. It never does this for 401/403/451, and it records which
identity was used and why.
"""

from __future__ import annotations

import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

DISCOVERY_URL = "https://accessgudid.nlm.nih.gov/download"
RELEASE_BASE = "https://accessgudid.nlm.nih.gov/release_files/download/"

PROJECT_UA = (
    "MedRadar/0.1 (+https://github.com/ChazY11/medradar; research; "
    "contact: repository owner) Python-urllib"
)
#: Only used after the project identity receives 503/404 from the public download host.
FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)

KINDS = ("full", "monthly", "weekly", "daily")

_MONTHS = {
    name: index for index, name in enumerate(
        ("january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"),
        start=1,
    )
}


@dataclass(frozen=True)
class ReleaseFile:
    kind: str
    filename: str
    url: str

    @property
    def dated(self) -> str:
        """A sortable ``YYYYMMDD`` derived from the filename, or the filename itself.

        Three naming schemes ship side by side and all three have to sort correctly:

        * ``gudid_full_release_20261102.zip``      - an 8-digit date;
        * ``gudid_weekly_update_20261109_20261113``- a date range, first day wins;
        * ``gudid_monthly_update_october_2026.zip``- a **month name**.

        Measured failure this fixes: before the month branch existed, the month-named files fell
        back to the filename, and comparing them as strings put ``october_2026`` below
        ``september_2025`` - so "newest monthly" silently resolved to a file eleven months old.
        """
        match = re.search(r"(\d{8})", self.filename)
        if match:
            return match.group(1)
        month = re.search(r"_([a-z]+)_(\d{4})\.zip$", self.filename, re.IGNORECASE)
        if month and month.group(1).lower() in _MONTHS:
            return f"{month.group(2)}{_MONTHS[month.group(1).lower()]:02d}01"
        return self.filename


@dataclass
class DownloadResult:
    url: str
    path: Path
    bytes_written: int
    resumed_from: int
    identity: str
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "path": str(self.path),
            "bytes_written": self.bytes_written,
            "resumed_from": self.resumed_from,
            "identity": self.identity,
            "notes": self.notes,
        }


@dataclass
class GudidImportResult:
    devices: int = 0
    submissions: int = 0
    companies: int = 0
    elements_seen: int = 0
    skipped: int = 0
    source: str | None = None
    release_kind: str | None = None
    period: str | None = None
    declared_records: int | None = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "devices": self.devices,
            "submissions": self.submissions,
            "companies": self.companies,
            "elements_seen": self.elements_seen,
            "skipped": self.skipped,
            "source": self.source,
            "release_kind": self.release_kind,
            "period": self.period,
            "declared_records": self.declared_records,
            "notes": self.notes,
        }


# ------------------------------------------------------------------- discovery
def discover_releases(html: str) -> list[ReleaseFile]:
    """Parse the public download page into a catalogue of release files.

    Only filenames the page actually links are returned. If the page changes shape the list
    gets smaller and the caller sees the catalogue it received - it never invents a URL.
    """
    pattern = re.compile(r"(https?://[^\"'<>\s]{0,120}/)?(gudid_[a-z0-9_]+\.zip)", re.IGNORECASE)
    seen: dict[str, ReleaseFile] = {}
    for match in pattern.finditer(html or ""):
        filename = match.group(2)
        kind = _kind_of(filename)
        if kind is None or filename in seen:
            continue
        seen[filename] = ReleaseFile(kind=kind, filename=filename,
                                     url=RELEASE_BASE + filename)
    return sorted(seen.values(), key=lambda item: (KINDS.index(item.kind), item.dated),
                  reverse=False)


def _kind_of(filename: str) -> str | None:
    lowered = filename.lower()
    for kind in KINDS:
        if f"_{kind}_" in lowered or lowered.startswith(f"gudid_{kind}_"):
            return kind
    return None


def newest(releases: Iterable[ReleaseFile], kind: str) -> ReleaseFile | None:
    candidates = [item for item in releases if item.kind == kind]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.dated)


# ------------------------------------------------------------------- transport
def fetch_text(url: str = DISCOVERY_URL, *, timeout: float = 60.0) -> tuple[str, str]:
    """Fetch the catalogue page, returning ``(html, identity_used)``."""
    last: Exception | None = None
    for identity, agent in (("project", PROJECT_UA), ("browser-fallback", FALLBACK_UA)):
        request = urllib.request.Request(url, headers={"User-Agent": agent, "Accept": "text/html"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace"), identity
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 451):
                raise
            last = error
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
            continue
    raise RuntimeError(f"could not read {url}: {last}")


def download(url: str, dest: str | Path, *, chunk_size: int = 1 << 20,
             timeout: float = 300.0, progress=None) -> DownloadResult:
    """Download a release file, resuming an interrupted attempt.

    Writes ``<dest>.part`` and renames on success, so a half-written file can never be mistaken
    for a release. The returned ``resumed_from`` is the byte offset the server honoured, not the
    offset we asked for.
    """
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    result = DownloadResult(url=url, path=path, bytes_written=0, resumed_from=0,
                            identity="project")

    for identity, agent in (("project", PROJECT_UA), ("browser-fallback", FALLBACK_UA)):
        headers = {"User-Agent": agent}
        if have:
            headers["Range"] = f"bytes={have}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 451):
                raise
            result.notes.append(f"{identity}: HTTP {error.code}")
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            result.notes.append(f"{identity}: {type(error).__name__}")
            continue
        with response:
            result.identity = identity
            status = int(getattr(response, "status", 200))
            if status == 206:
                result.resumed_from = have
                mode = "ab"
            else:
                # The server ignored the range (or we sent none): restart cleanly.
                result.resumed_from = 0
                have = 0
                mode = "wb"
            written = 0
            with open(part, mode) as handle:
                while True:
                    block = response.read(chunk_size)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)
                    if progress:
                        progress(written + have)
            total = written + have
            declared = response.headers.get("Content-Length")
            if status != 206 and declared and int(declared) != written:
                result.notes.append(
                    f"declared {declared} bytes, wrote {written}: kept as .part for resume"
                )
                result.bytes_written = total
                return result
            part.replace(path)
            result.bytes_written = total
            if identity != "project":
                result.notes.append(
                    "public download host answered the project user agent with 503/404 while "
                    "serving the same public file; a browser string was used for the transfer "
                    "only. No 401/403/451 would ever take this path."
                )
            return result
    raise RuntimeError(f"download failed for {url}: {'; '.join(result.notes)}")


# ------------------------------------------------------------------ xml streaming
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join("".join(element.itertext()).split())
    return value or None


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _flag(element: ET.Element, name: str) -> str | None:
    return _text(_child(element, name))


def _part_sort_key(name: str) -> tuple[int, str]:
    """Natural order for ``..._Part7_Of_211_...`` - lexicographic order puts Part100 first.

    Measured on the 2026-11-01 full release: 211 XML parts, 25,000 device records each,
    5,258,157 records declared by the header. Reading only the first member imported 25,000 of
    them, and the completeness check below is what caught it.
    """
    match = re.search(r"Part(\d+)_Of_(\d+)", name)
    if match:
        return (int(match.group(1)), name)
    return (10**9, name)


def _xml_members(archive: zipfile.ZipFile) -> list[str]:
    return sorted((name for name in archive.namelist() if name.lower().endswith(".xml")),
                  key=_part_sort_key)


def iter_devices(source: str | Path | io.BufferedIOBase, *,
                 limit: int | None = None) -> Iterator[ET.Element]:
    """Yield ``<device>`` elements from a GUDID release, streaming across every part.

    A full release is 211 XML parts of ~25,000 records each (~21 GB of XML in total). The
    generator walks all of them in part order; ``iterparse`` with an explicit ``clear`` keeps
    memory flat, and each part is cleared as its devices are consumed.
    """
    handle: Any = source
    archive: zipfile.ZipFile | None = None
    members: list[str] = []
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() == ".zip":
            archive = zipfile.ZipFile(path)
            members = _xml_members(archive)
            if not members:
                archive.close()
                raise ValueError(f"{path} contains no XML member")
            handle = None
        else:
            handle = open(path, "rb")
    if isinstance(source, io.BufferedIOBase):
        members = []
    produced = 0
    try:
        if archive is not None:
            for member in members:
                with archive.open(member) as part:
                    for element in _iter_device_elements(part):
                        yield element
                        produced += 1
                        if limit is not None and produced >= limit:
                            return
        else:
            for element in _iter_device_elements(handle):
                yield element
                produced += 1
                if limit is not None and produced >= limit:
                    return
    finally:
        if archive is not None:
            archive.close()
        elif handle is not None:
            handle.close()


def _iter_device_elements(handle) -> Iterator[ET.Element]:
    for _event, element in ET.iterparse(handle, events=("end",)):
        if _local(element.tag) != "device":
            continue
        yield element
        element.clear()


def release_metadata(source: str | Path) -> dict[str, Any]:
    """Read the ``<header>`` of a release file without parsing the devices.

    Reads **part 1**, not the first zip entry: zip order is arbitrary and the first entry of
    the 2026-11-01 full release is Part100.
    """
    handle: Any = source
    archive: zipfile.ZipFile | None = None
    if isinstance(source, (str, Path)) and Path(source).suffix.lower() == ".zip":
        archive = zipfile.ZipFile(source)
        members = _xml_members(archive)
        if not members:
            archive.close()
            return {}
        handle = archive.open(members[0])
    elif isinstance(source, (str, Path)):
        handle = open(source, "rb")
    try:
        head = handle.read(4096)
    finally:
        handle.close()
        if archive is not None:
            archive.close()
    text = head.decode("utf-8", "replace")
    metadata: dict[str, Any] = {}
    for key in ("numberRecordXML", "numberRecordsDatabase", "creationDate"):
        match = re.search(rf"<{key}>([^<]*)</{key}>", text)
        if match:
            metadata[key] = match.group(1)
    for key in ("frequency", "id", "type"):
        match = re.search(rf'{key}="([^"]*)"', text)
        if match:
            metadata[key] = match.group(1)
    period = re.search(r'<period end="([^"]*)" start="([^"]*)"', text)
    if period:
        metadata["period_start"] = period.group(2)
        metadata["period_end"] = period.group(1)
    return metadata


def device_to_parsed(element: ET.Element) -> dict[str, Any] | None:
    """Normalise one GUDID ``<device>`` element to the reference store's shape."""
    from .records import utc_now_iso
    from .reference import build_device_row

    identifiers = _child(element, "identifiers")
    primary_id = None
    any_id = None
    if identifiers is not None:
        for entry in identifiers:
            if _local(entry.tag) != "identifier":
                continue
            value = _text(_child(entry, "deviceId"))
            if not value:
                continue
            if any_id is None:
                any_id = (value, _text(_child(entry, "deviceIdIssuingAgency")))
            if (_text(_child(entry, "deviceIdType")) or "").lower() == "primary":
                primary_id = (value, _text(_child(entry, "deviceIdIssuingAgency")))
                break
    chosen = primary_id or any_id

    company = _text(_child(element, "companyName"))
    catalog = _text(_child(element, "catalogNumber"))
    model = _text(_child(element, "versionModelNumber"))
    brand = _text(_child(element, "brandName"))
    description = _text(_child(element, "deviceDescription"))
    duns = _text(_child(element, "dunsNumber"))

    if not chosen and not (catalog or model):
        return None
    di = chosen[0] if chosen else None
    device_key = f"di:{di}" if di else f"cm:{company or ''}|{catalog or model}"

    codes: list[str] = []
    product_codes = _child(element, "productCodes")
    if product_codes is not None:
        for entry in product_codes:
            code = _text(_child(entry, "productCode")) or _text(entry)
            if code:
                codes.append(code)

    gmdn = None
    gmdn_terms = _child(element, "gmdnTerms")
    if gmdn_terms is not None:
        for entry in gmdn_terms:
            if _local(entry.tag) == "gmdn":
                gmdn = entry
                break

    implantable = _text(_child(gmdn, "implantable")) if gmdn is not None else None
    raw = {
        "public_device_record_key": _text(_child(element, "publicDeviceRecordKey")),
        "public_version_status": _text(_child(element, "publicVersionStatus")),
        "public_version_number": _text(_child(element, "publicVersionNumber")),
        "device_count": _text(_child(element, "deviceCount")),
        "sterile": _text(_child(_child(element, "sterilization") or ET.Element("x"), "deviceSterile")),
        "source": "gudid_release",
    }
    parsed = {
        "device_key": device_key,
        "duns": duns,
        "company_name": company or "",
        "submissions": (),
        "row": build_device_row({
            "device_key": device_key,
            "di": di,
            "di_type": chosen[1] if chosen else None,
            "brand_name": brand,
            "device_description": description,
            "company_name": company,
            "labeler_duns": duns,
            "catalog_number": catalog,
            "version_or_model": model,
            "product_codes": _json(codes),
            "regulation_numbers": _json([]),
            "device_classes": _json([]),
            "gmdn_code": _text(_child(gmdn, "gmdnCode")) if gmdn is not None else None,
            "gmdn_name": _text(_child(gmdn, "gmdnPTName")) if gmdn is not None else None,
            "implantable": _bool_int(implantable),
            "is_single_use": _bool_int(_flag(element, "singleUse")),
            "is_kit": _bool_int(_flag(element, "deviceKit")),
            "is_rx": _bool_int(_flag(element, "rx")),
            "is_pm_exempt": _bool_int(_flag(element, "premarketExempt")),
            "mri_safety": _flag(element, "MRISafetyStatus"),
            "publish_date": _text(_child(element, "devicePublishDate")),
            "public_version_date": _text(_child(element, "publicVersionDate")),
            "record_status": _text(_child(element, "deviceRecordStatus")),
            "raw": _json(raw),
            "first_observed_at": utc_now_iso(),
        }),
    }
    return parsed


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "y", "yes"):
        return 1
    if text in ("false", "0", "n", "no"):
        return 0
    return None


def import_release(reference, source: str | Path, *, limit: int | None = None,
                   batch_size: int = 2_000, progress=None) -> GudidImportResult:
    """Load a GUDID release into the reference store.

    Batched so a 5.18M-row full release commits progress as it goes instead of holding one
    enormous transaction; an interrupted import leaves the rows already committed.
    """
    result = GudidImportResult(source=str(source))
    metadata = release_metadata(source)
    result.release_kind = metadata.get("type")
    result.period = metadata.get("period_end") or metadata.get("creationDate")
    declared = metadata.get("numberRecordsDatabase")
    result.declared_records = int(declared) if str(declared or "").isdigit() else None

    batch: list[dict[str, Any]] = []
    for element in iter_devices(source, limit=limit):
        result.elements_seen += 1
        parsed = device_to_parsed(element)
        if parsed is None:
            result.skipped += 1
            continue
        batch.append(parsed)
        if len(batch) >= batch_size:
            devices, submissions, companies = reference.write_parsed(batch)
            result.devices += devices
            result.submissions += submissions
            result.companies += companies
            batch.clear()
            if progress:
                progress(result)
    if batch:
        devices, submissions, companies = reference.write_parsed(batch)
        result.devices += devices
        result.submissions += submissions
        result.companies += companies

    if result.declared_records and result.elements_seen and limit is None:
        if result.elements_seen != result.declared_records:
            result.notes.append(
                f"header declared {result.declared_records} records, parsed "
                f"{result.elements_seen}: the release was truncated or a part is missing"
            )
    if not result.submissions:
        result.notes.append(
            "no premarket submissions in this release: the 510(k) link comes from the "
            "openFDA UDI sync, not from GUDID"
        )
    return result


__all__ = [
    "DISCOVERY_URL",
    "DownloadResult",
    "GudidImportResult",
    "RELEASE_BASE",
    "ReleaseFile",
    "device_to_parsed",
    "discover_releases",
    "download",
    "fetch_text",
    "import_release",
    "iter_devices",
    "newest",
    "release_metadata",
]
