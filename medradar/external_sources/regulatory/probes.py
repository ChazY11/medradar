"""Live probe definitions for the regulatory (device market-access) sources.

One probe per ``source_id`` that the ``regulatory`` agent owns in
``research/data_expansion/registry/SOURCE_ID_INDEX.json``.  Each probe obeys the
collection protocol:

* bounded request budget and a polite minimum interval;
* every request goes through :class:`medradar.external_sources.base.HttpClient`,
  so successes *and* failures land in ``probes/<source_id>/requests.jsonl``;
* real response slices are written under ``samples/<source_id>/`` with the
  full-response sha256 recorded in ``SAMPLES.json``;
* a negative result is recorded exactly as observed.  ``UNAVAILABLE``,
  ``BLOCKED_BY_POLICY`` and ``REQUIRES_REGISTRATION`` are legitimate outcomes
  and are never promoted to ``VERIFIED_*``.

Usage::

    python -m medradar.external_sources.regulatory.probes openfda_device_510k
    python -m medradar.external_sources.regulatory.probes --all
    python -m medradar.external_sources.regulatory.probes --list
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .. import base, identity

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO_ROOT / "research" / "data_expansion"

OPENFDA = "https://api.fda.gov"
ACCESSGUDID = "https://accessgudid.nlm.nih.gov"
MDALL = "https://health-products.canada.ca/api/medical-devices"
GUDID_FILES = "https://accessgudid.nlm.nih.gov/release_files/download"

#: Real device identifiers taken from openFDA ``device/udi`` during
#: reconnaissance.  They are used to compare AccessGUDID with openFDA on the
#: *same* record (the ``publicDeviceRecordKey`` must agree).
KNOWN_DI: dict[str, str] = {
    "medtronic": "00643169718425",
    "draeger": "04049098054089",
    "mindray": "06944904092515",
    "ge_healthcare": "00840682146586",
    "philips": "03615040000681",
}

#: openFDA applicant search strings for the five target firms.  Several
#: candidates per firm because openFDA stores the *submitter* legal entity
#: ("GE MEDICAL SYSTEMS", "DRAEGER MEDICAL SYSTEMS, INC."), not the brand.
FIRM_SEARCHES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("medtronic", ('applicant:medtronic',)),
    ("ge_healthcare", ('applicant:"ge healthcare"', 'applicant:"ge medical systems"')),
    ("philips", ("applicant:philips",)),
    ("draeger", ("applicant:draeger",)),
    ("mindray", ("applicant:mindray",)),
)


# --------------------------------------------------------------------------- helpers
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _samples_dir(directory: Path, source_id: str) -> Path:
    """``probes/<id>`` → ``samples/<id>`` (sibling of ``probes`` under the root)."""
    root = Path(directory).resolve().parents[1]
    return root / "samples" / source_id


def _ext(result: base.HttpResult, payload: Any) -> str:
    if payload is not None:
        return ".json"
    ctype = str((result.headers or {}).get("content-type", "")).lower()
    if "html" in ctype:
        return ".html"
    if "zip" in ctype:
        return ".zip"
    if "xml" in ctype:
        return ".xml"
    return ".txt"


def _entry(
    name: str,
    result: base.HttpResult,
    directory: Path,
    source_id: str,
    *,
    store: bool = True,
    note: str = "",
) -> dict[str, Any]:
    """Describe one request outcome, persisting a bounded real sample when possible."""
    payload: Any = None
    parsed = False
    if result.ok:
        try:
            payload = result.json()
            parsed = True
        except (ValueError, UnicodeDecodeError):
            payload = None
    row: dict[str, Any] = {
        "name": name,
        "url": result.url,
        "status": result.status,
        "ok": result.ok,
        "bytes": len(result.body),
        "elapsed_ms": result.elapsed_ms,
        "attempts": result.attempts,
        "error": result.error,
        "note": note,
        "structure": base.json_shape(payload) if parsed else None,
        "sample": None,
    }
    if result.ok and store and result.body:
        row["sample"] = base.write_sample(
            _samples_dir(directory, source_id), name + _ext(result, payload), result.body
        )
    return row


def _records(payload: Any) -> list[dict[str, Any]]:
    """openFDA-style ``{"results": [...]}`` or a bare list."""
    if isinstance(payload, Mapping):
        items = payload.get("results")
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    return []


def _total(payload: Any) -> int | None:
    if isinstance(payload, Mapping):
        meta = payload.get("meta") or {}
        if isinstance(meta, Mapping):
            results = meta.get("results") or {}
            if isinstance(results, Mapping):
                try:
                    return int(results.get("total"))
                except (TypeError, ValueError):
                    return None
    return None


def _resolve_companies(applicants: Iterable[str]) -> list[dict[str, Any]]:
    """Run the real alias index over the applicants actually returned."""
    index = identity.CompanyIndex.from_config()
    out: list[dict[str, Any]] = []
    for raw in applicants:
        if not raw:
            continue
        res = index.resolve(raw)
        out.append(
            {
                "applicant_raw": raw,
                "method": res.get("method"),
                "resolved_key": res.get("resolved_key"),
                "confidence": res.get("confidence"),
            }
        )
    return out


def _status_from(probes: Sequence[Mapping[str, Any]], *, ok_status: str) -> str:
    return ok_status if any(p.get("ok") for p in probes) else "UNAVAILABLE"


def _first(pattern: str, text: str) -> str:
    """First capture group of ``pattern`` in ``text``, or ``""``."""
    match = re.search(pattern, text)
    return match.group(1) if match else ""


# ------------------------------------------------------------------ openFDA helpers
def _openfda_company_search(
    client: base.HttpClient,
    probes: list[dict[str, Any]],
    directory: Path,
    source_id: str,
    endpoint: str,
    candidates: Sequence[str],
    limit: int = 3,
) -> None:
    """Try each applicant variant until one returns records (bounded by budget)."""
    for candidate in candidates:
        if client.remaining() <= 0:
            return
        result = client.get(f"{OPENFDA}/{endpoint}", params={"search": candidate, "limit": limit})
        payload = None
        if result.ok:
            try:
                payload = result.json()
            except ValueError:
                payload = None
        entry = _entry(
            f"search_{candidate}",
            result,
            directory,
            source_id,
        )
        records = _records(payload)
        entry["records"] = len(records)
        entry["total"] = _total(payload)
        if records:
            entry["company_resolution"] = _resolve_companies(
                str(r.get("applicant", "")) for r in records
            )
        probes.append(entry)
        if records:
            return


def _probe_openfda_submissions(
    client: base.HttpClient,
    directory: Path,
    *,
    source_id: str,
    endpoint: str,
    date_field: str,
    window: str = "2024-01-01 TO 2024-12-31",
) -> base.ProbeOutcome:
    probes: list[dict[str, Any]] = []

    # 1) smoke: a bounded slice of one calendar year.
    r = client.get(f"{OPENFDA}/{endpoint}", params={"search": f"{date_field}:[{window}]", "limit": 2})
    entry = _entry("window_smoke_2024", r, directory, source_id)
    payload = None
    if r.ok:
        try:
            payload = r.json()
        except ValueError:
            payload = None
    entry["records"] = len(_records(payload))
    entry["total"] = _total(payload)
    entry["endpoint_last_updated"] = (
        ((payload or {}).get("meta") or {}).get("last_updated") if isinstance(payload, Mapping) else None
    )
    probes.append(entry)

    # 2) count probe: how many records the newest full year holds.  The
    #    connector must window pages because openFDA caps ``skip``.
    if client.remaining() > 0:
        r = client.get(
            f"{OPENFDA}/{endpoint}",
            params={"search": f"{date_field}:[2025-01-01 TO 2025-12-31]", "limit": 1},
        )
        entry = _entry("window_2025_count", r, directory, source_id)
        if r.ok:
            try:
                entry["total"] = _total(r.json())
            except ValueError:
                entry["total"] = None
        probes.append(entry)

    # 3) five target firms, through the real alias index.
    for _firm, candidates in FIRM_SEARCHES:
        _openfda_company_search(client, probes, directory, source_id, endpoint, candidates)

    # 4) deep-pagination behaviour at the documented 25k skip ceiling.
    if client.remaining() > 0:
        r = client.get(
            f"{OPENFDA}/{endpoint}",
            params={"search": f"{date_field}:[1990-01-01 TO 2026-12-31]", "skip": 25_000, "limit": 1},
        )
        probes.append(
            _entry(
                "skip_25000_behaviour",
                r,
                directory,
                source_id,
                note="documents whether openFDA still serves pages beyond skip=25000",
            )
        )

    ok = any(p.get("ok") for p in probes)
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_API" if ok else "UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes="",
    )


def probe_openfda_device_510k(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    outcome = _probe_openfda_submissions(
        client,
        directory,
        source_id="openfda_device_510k",
        endpoint="device/510k.json",
        date_field="decision_date",
    )
    outcome.notes = (
        "device/510k returns real records (JSON, meta.results.total present). "
        "No key needed. `decision_date` is the clearance decision date; FDA publishes no "
        "per-record first-publication timestamp, so source_public_at may only be derived "
        "from the decision date and must be flagged as coarse evidence, never used as a "
        "published-on date."
    )
    return outcome


def probe_openfda_device_pma(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    outcome = _probe_openfda_submissions(
        client,
        directory,
        source_id="openfda_device_pma",
        endpoint="device/pma.json",
        date_field="decision_date",
    )
    outcome.notes = (
        "device/pma returns PMA originals and supplements; a supplement is a distinct "
        "record (pma_number + supplement_number) under the same approval. Same date caveat "
        "as 510(k): decision_date is an event date, not a publication date."
    )
    return outcome


# ---------------------------------------------------------------------- bulk / UDI
def probe_openfda_bulk_download(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "openfda_bulk_download"
    probes: list[dict[str, Any]] = []

    r = client.get(f"{OPENFDA}/download.json")
    entry = _entry("download_manifest", r, directory, source_id)
    manifest: dict[str, Any] = {}
    if r.ok:
        try:
            manifest = ((r.json() or {}).get("results") or {}).get("device") or {}
        except ValueError:
            manifest = {}
        summary = {}
        for name, block in (manifest or {}).items():
            if not isinstance(block, Mapping):
                continue
            summary[str(name)] = {
                "total_records": block.get("total_records"),
                "export_date": block.get("export_date"),
                "partitions": len(block.get("partitions") or []),
            }
        entry["device_exports"] = summary
    probes.append(entry)

    # Download the smallest real export (device/classification, a few MB) and
    # parse it, so the "bulk" claim is byte-verified rather than documentation.
    target: Mapping[str, Any] | None = None
    sizes: dict[str, float] = {}
    for name, block in (manifest or {}).items():
        if not isinstance(block, Mapping):
            continue
        for part in block.get("partitions") or []:
            if not isinstance(part, Mapping):
                continue
            try:
                size = float(part.get("size_mb") or 0)
            except (TypeError, ValueError):
                size = 0.0
            sizes[str(part.get("file", ""))] = size
            if name == "classification" and target is None:
                target = part
    if target is None and sizes:
        smallest = min((u for u in sizes if u), key=lambda u: sizes[u], default="")
        if smallest:
            target = {"file": smallest, "size_mb": str(sizes[smallest])}
    entry["chosen_partition"] = dict(target) if target else None

    if target and str(target.get("file", "")).startswith("http") and client.remaining() > 0:
        url = str(target["file"])
        rz = client.get(url, accept="application/zip")
        zentry = _entry("classification_export_zip", rz, directory, source_id, note="raw export zip")
        parsed_records: int | None = None
        inner_names: list[str] = []
        if rz.ok and rz.body:
            try:
                with zipfile.ZipFile(io.BytesIO(rz.body)) as zf:
                    inner_names = zf.namelist()[:5]
                    for info in zf.infolist():
                        if not info.filename.lower().endswith(".json"):
                            continue
                        with zf.open(info) as fh:
                            payload = json.loads(fh.read().decode("utf-8", "replace"))
                        parsed_records = len(_records(payload))
                        break
            except (zipfile.BadZipFile, ValueError, OSError) as exc:
                zentry["parse_error"] = f"{type(exc).__name__}: {exc}"
        zentry["inner_files"] = inner_names
        zentry["parsed_records"] = parsed_records
        zentry["declared_records"] = target.get("records")
        probes.append(zentry)

    parsed = any(
        isinstance(p.get("parsed_records"), int) and p["parsed_records"] > 0 for p in probes
    )
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_BULK_DOWNLOAD" if parsed else _status_from(probes, ok_status="VERIFIED_API"),
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "api.fda.gov/download.json is the official export manifest: per-endpoint "
            "`total_records` and an `export_date` that is a genuine snapshot clock (unlike "
            "the API's per-endpoint `last_updated`). One export partition was downloaded "
            "and parsed, which is what distinguishes VERIFIED_BULK_DOWNLOAD from a doc claim."
        ),
    )


def probe_accessgudid(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "accessgudid"
    probes: list[dict[str, Any]] = []

    # 1..3) real DI lookups for three different target firms.
    for firm in ("medtronic", "draeger", "mindray"):
        di = KNOWN_DI[firm]
        r = client.get(f"{ACCESSGUDID}/api/v3/devices/lookup", params={"di": di})
        entry = _entry(f"lookup_{firm}_{di}", r, directory, source_id)
        if r.ok:
            try:
                doc = r.json()
            except ValueError:
                doc = {}
            dev = ((doc or {}).get("gudid") or {}).get("device") or {}
            entry["public_device_record_key"] = dev.get("publicDeviceRecordKey")
            entry["device_publish_date"] = dev.get("devicePublishDate")
            entry["public_version_date"] = dev.get("publicVersionDate")
            entry["brand_name"] = dev.get("brandName")
            entry["company_name"] = dev.get("companyName")
        probes.append(entry)

    # 4) the SAME DI through openFDA's UDI endpoint: proves the two interfaces
    #    publish the same upstream GUDID record (same publicDeviceRecordKey).
    if client.remaining() > 0:
        di = KNOWN_DI["medtronic"]
        r = client.get(
            f"{OPENFDA}/device/udi.json",
            params={"search": f'identifiers.id:"{di}"', "limit": 1},
        )
        entry = _entry("openfda_udi_same_di", r, directory, source_id)
        if r.ok:
            try:
                recs = _records(r.json())
            except ValueError:
                recs = []
            if recs:
                rec = recs[0]
                entry["public_device_record_key"] = rec.get("public_device_record_key")
                entry["publish_date"] = rec.get("publish_date")
                entry["public_version_date"] = rec.get("public_version_date")
                entry["premarket_submissions"] = rec.get("premarket_submissions")
        probes.append(entry)

    ok = any(p.get("ok") for p in probes)
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_API" if ok else "UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "AccessGUDID (NLM) /api/v3/devices/lookup?di= returns the GUDID record as JSON. "
            "GUDID is the upstream database that openFDA /device/udi.json re-publishes: the "
            "same DI yields the same publicDeviceRecordKey on both interfaces, so they are "
            "ONE evidence item, not two. GUDID publish_date is a real per-record "
            "first-publication date; public_version_date is a version stamp and must never "
            "be used as the first-publication date."
        ),
    )


def probe_fda_gudid_download(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "fda_gudid_download"
    probes: list[dict[str, Any]] = []

    r = client.get(f"{ACCESSGUDID}/download", accept="text/html")
    entry = _entry("download_page", r, directory, source_id)
    links: list[str] = []
    if r.ok:
        html = r.text
        links = sorted(set(re.findall(r"https://accessgudid\.nlm\.nih\.gov/release_files/download/[A-Za-z0-9_.\-]+\.zip", html)))
        entry["release_files"] = links[:12]
        entry["release_file_count"] = len(links)
        # record the advertised checksum/size lines for the newest daily file
        tail = html
        for fname in (u.rsplit("/", 1)[-1] for u in links[:3]):
            i = tail.find(fname)
            if i >= 0:
                entry.setdefault("release_metadata", {})[fname] = re.sub(
                    r"\s+", " ", re.sub(r"<[^>]+>", " ", tail[i : i + 700])
                ).strip()[:400]
        entry["daily_files"] = [u for u in links if "daily_update" in u][:3]
    probes.append(entry)

    daily = [u for u in links if "daily_update" in u]
    if daily and client.remaining() > 0:
        url = daily[0]
        rz = client.get(url, accept="application/zip")
        zentry = _entry("daily_release_zip", rz, directory, source_id, note="a real GUDID daily release")
        parsed_records: int | None = None
        inner: list[str] = []
        if rz.ok and rz.body:
            try:
                with zipfile.ZipFile(io.BytesIO(rz.body)) as zf:
                    inner = zf.namelist()[:5]
                    info = next(
                        (i for i in zf.infolist() if i.filename.lower().endswith((".xml", ".json"))),
                        None,
                    )
                    if info is not None:
                        with zf.open(info) as fh:
                            raw = fh.read()
                        if info.filename.lower().endswith(".json"):
                            parsed_records = len(_records(json.loads(raw.decode("utf-8", "replace"))))
                        else:
                            # GUDID release XML is namespaced; element opens carry
                            # xmlns attributes, so match the tag prefix, not "<device>".
                            parsed_records = raw.count(b"<device ") + raw.count(b"<device>")
                            head = raw[:4000].decode("utf-8", "replace")
                            zentry["header"] = {
                                "numberRecordXML": _first(r"<numberRecordXML>(\d+)</numberRecordXML>", head),
                                "creationDate": _first(r"<creationDate>([^<]+)</creationDate>", head),
                                "frequency": _first(r'frequency="([^"]+)"', head),
                                "database_type": _first(r'type="([^"]+)"', head),
                                "period_start": _first(r'<period[^>]*start="([^"]+)"', head),
                                "period_end": _first(r'<period[^>]*end="([^"]+)"', head),
                                "devicePublishDate_sample": _first(
                                    r"<devicePublishDate>([^<]+)</devicePublishDate>", raw[:200000].decode("utf-8", "replace")
                                ),
                                "publicVersionDate_sample": _first(
                                    r"<publicVersionDate>([^<]+)</publicVersionDate>", raw[:200000].decode("utf-8", "replace")
                                ),
                            }
            except (zipfile.BadZipFile, ValueError, OSError) as exc:
                zentry["parse_error"] = f"{type(exc).__name__}: {exc}"
        zentry["inner_files"] = inner
        zentry["parsed_records"] = parsed_records
        probes.append(zentry)

    parsed = any(
        isinstance(p.get("parsed_records"), int) and p["parsed_records"] > 0 for p in probes
    )
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_BULK_DOWNLOAD" if parsed else _status_from(probes, ok_status="VERIFIED_PUBLIC_QUERY"),
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "NLM publishes GUDID release files: daily / weekly / monthly change sets and a "
            "full release. Daily files are small enough to download inside the protocol "
            "budget and carry an explicit 'Date Created' + record count + MD5, which gives a "
            "true per-batch publication clock. The full release is far above the 8 MB cap."
        ),
    )


# ------------------------------------------------------------------ Canada / MDALL
def probe_canada_mdall(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "canada_mdall"
    probes: list[dict[str, Any]] = []

    # 1) documented API guide (evidence URL for the register record)
    r = client.get(
        "https://health-products.canada.ca/api/documentation/mdall-documentation-en.html",
        accept="text/html",
    )
    probes.append(_entry("api_documentation", r, directory, source_id))

    # 2) company search for the five target firms, through the alias index
    index = identity.CompanyIndex.from_config()
    for firm in ("medtronic", "ge_healthcare", "philips", "draeger", "mindray"):
        if client.remaining() <= 0:
            break
        company = index.company(firm) or {}
        needle = str(company.get("name_en") or firm).upper()
        # MDALL matches %NAME% case-insensitively; use a distinctive token
        token = {
            "ge_healthcare": "GE HEALTHCARE",
            "medtronic": "MEDTRONIC",
            "philips": "PHILIPS",
            "draeger": "DRAEGER",
            "mindray": "MINDRAY",
        }[firm]
        r = client.get(f"{MDALL}/company/", params={"company_name": token, "type": "json"})
        entry = _entry(f"company_search_{firm}", r, directory, source_id)
        entry["needle"] = needle
        if r.ok:
            try:
                payload = r.json()
            except ValueError:
                payload = None
            rows = _records(payload) if not isinstance(payload, Mapping) else [payload]
            entry["companies"] = len(rows)
            entry["company_ids"] = [
                {"company_id": row.get("company_id"), "company_name": row.get("company_name")}
                for row in rows[:6]
            ]
            entry["company_resolution"] = _resolve_companies(
                str(row.get("company_name", "")) for row in rows[:6]
            )
        probes.append(entry)

    # 3) licence detail for the first Medtronic company id (bounded by company)
    medtronic_entry = next(
        (p for p in probes if p.get("name") == "company_search_medtronic" and p.get("ok")), None
    )
    company_ids = [
        row.get("company_id")
        for row in (medtronic_entry or {}).get("company_ids", [])
        if row.get("company_id") is not None
    ]
    if company_ids and client.remaining() > 0:
        r = client.get(
            f"{MDALL}/licence/",
            params={"company_id": company_ids[0], "state": "active", "lang": "en", "type": "json"},
        )
        entry = _entry("licence_by_company", r, directory, source_id)
        if r.ok:
            try:
                payload = r.json()
            except ValueError:
                payload = None
            rows = _records(payload) if not isinstance(payload, list) else payload
            entry["licences"] = len(rows)
            entry["licence_numbers"] = [row.get("original_licence_no") for row in rows[:5]]
            entry["date_fields"] = sorted(
                {k for row in rows[:3] for k in row if k.endswith("_dt") or k == "end_date"}
            )
        probes.append(entry)

    # 4) the UDI bridge: does MDALL resolve a real GUDID device identifier?
    if client.remaining() > 0:
        di = KNOWN_DI["medtronic"]
        r = client.get(
            f"{MDALL}/deviceidentifier/",
            params={"device_identifier": di, "state": "active", "type": "json"},
        )
        entry = _entry(f"device_identifier_{di}", r, directory, source_id)
        if r.ok:
            try:
                payload = r.json()
            except ValueError:
                payload = None
            rows = payload if isinstance(payload, list) else [payload] if payload else []
            entry["rows"] = len(rows)
            entry["matched"] = rows[:3]
        probes.append(entry)

    ok = any(p.get("ok") for p in probes)
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_API" if ok else "UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "Health Canada publishes a documented JSON/XML API (no key) for MDALL: "
            "company / licence / device / deviceidentifier. `first_licence_status_dt` (licence) "
            "and `first_licence_dt` (device) are the only real dates; `last_refresh_dt` is a "
            "database refresh stamp and `end_date` is a cancellation date, so neither may be "
            "used as the first-publication date. The deviceidentifier endpoint takes a real "
            "UDI-DI, which is an official bridge to GUDID for devices sold in both markets."
        ),
    )


# ------------------------------------------------------------------------- EUDAMED
def probe_eudamed(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "eudamed"
    probes: list[dict[str, Any]] = []

    r = client.get("https://ec.europa.eu/tools/eudamed/", accept="text/html")
    probes.append(_entry("public_spa_shell", r, directory, source_id))

    r = client.get("https://ec.europa.eu/tools/eudamed/api/devices", params={"page": 0, "size": 2})
    entry = _entry("public_api_devices", r, directory, source_id)
    blocked_message = ""
    if not r.ok:
        try:
            body = r.json()
        except ValueError:
            body = {}
        if isinstance(body, Mapping):
            blocked_message = str(body.get("message", ""))
            entry["policy_message"] = blocked_message
            entry["machine_to_machine_api"] = body.get("machineToMachineApi")
    probes.append(entry)

    r = client.get(
        "https://developer.datalake.sante.service.ec.europa.eu/api-details"
        "#api=94b9e658-d721-4b58-8d96-022c490f7a17",
        accept="text/html",
    )
    probes.append(
        _entry(
            "official_machine_api_portal",
            r,
            directory,
            source_id,
            note="portal named by the EUDAMED public endpoint's own policy message",
        )
    )

    blocked = any(
        p.get("status") == 429 and "machine-to-machine" in str(p.get("policy_message", "")).lower()
        for p in probes
    )
    return base.ProbeOutcome(
        source_id=source_id,
        status="REQUIRES_REGISTRATION",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "EUDAMED's public SPA loads, but every public data endpoint answers HTTP 429 with an "
            "explicit policy message telling automated clients to use the official EUDAMED data "
            "API instead of scraping. That machine API lives on the DG SANTE developer portal "
            "and needs registered credentials, so the source is reachable only after "
            "registration; the public endpoints are off-limits to this study by the operator's "
            "own instruction (probe stores the exact message)."
        ),
    )


# --------------------------------------------------------------- openFDA P1 extras
def probe_openfda_device_classification(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "openfda_device_classification"
    probes: list[dict[str, Any]] = []

    r = client.get(f"{OPENFDA}/device/classification.json", params={"limit": 2})
    entry = _entry("page_smoke", r, directory, source_id)
    if r.ok:
        try:
            payload = r.json()
        except ValueError:
            payload = None
        entry["total"] = _total(payload)
    probes.append(entry)

    r = client.get(
        f"{OPENFDA}/device/classification.json",
        params={"search": 'product_code:"DQA"', "limit": 2},
    )
    entry = _entry("product_code_dqa", r, directory, source_id)
    if r.ok:
        try:
            payload = r.json()
        except ValueError:
            payload = None
        recs = _records(payload)
        entry["records"] = len(recs)
        entry["device_names"] = [rec.get("device_name") for rec in recs]
    probes.append(entry)

    ok = any(p.get("ok") for p in probes)
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_API" if ok else "UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "The product-code dictionary is small (~7k codes) and is the join key between a "
            "510(k)/PMA submission and a device family, so it is a cheap full pull (<=8 pages at "
            "limit=1000) rather than a windowed collection."
        ),
    )


def probe_openfda_device_registrationlisting(
    client: base.HttpClient, directory: Path
) -> base.ProbeOutcome:
    source_id = "openfda_device_registrationlisting"
    probes: list[dict[str, Any]] = []

    r = client.get(f"{OPENFDA}/device/registrationlisting.json", params={"limit": 2})
    entry = _entry("page_smoke", r, directory, source_id)
    if r.ok:
        try:
            entry["total"] = _total(r.json())
        except ValueError:
            pass
    probes.append(entry)

    # The establishment record carries k_number / pma_number / products, i.e. a
    # registrant-level bridge to clearances as well as the proprietary names.
    r = client.get(
        f"{OPENFDA}/device/registrationlisting.json",
        params={"search": 'registration.name:"Medtronic"', "limit": 2},
    )
    entry = _entry("search_registrant_medtronic", r, directory, source_id)
    if r.ok:
        try:
            payload = r.json()
        except ValueError:
            payload = None
        recs = _records(payload)
        entry["records"] = len(recs)
        entry["shape_keys"] = sorted(recs[0]) if recs else []
        entry["company_resolution"] = _resolve_companies(
            str((rec.get("registration") or {}).get("name", "")) for rec in recs
        )
    probes.append(entry)

    ok = any(p.get("ok") for p in probes)
    return base.ProbeOutcome(
        source_id=source_id,
        status="VERIFIED_API" if ok else "UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "Registration & listing is establishment-level (who may distribute what), not "
            "product-level; it carries k_number/pma_number per establishment which makes it a "
            "registrant bridge, but it must not be counted as a second clearance record."
        ),
    )


# ------------------------------------------------------------------ CN / AU blocks
def probe_china_nmpa_device(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "china_nmpa_device"
    probes: list[dict[str, Any]] = []

    r = client.get("https://www.nmpa.gov.cn/", accept="text/html")
    entry = _entry("portal_home", r, directory, source_id)
    if r.body:
        entry["challenge_markers"] = [
            marker
            for marker in ("meta id=", "r='m'", "acw_sc__v2", "arg1=", "captcha", "412")
            if marker in r.text[:4000]
        ]
    probes.append(entry)

    if client.remaining() > 0:
        r = client.get(
            "https://www.nmpa.gov.cn/datasearch/search-result.html",
            params={"q": "Medtronic"},
            accept="text/html",
        )
        probes.append(_entry("datasearch_query", r, directory, source_id))

    return base.ProbeOutcome(
        source_id=source_id,
        status="BLOCKED_BY_POLICY",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "NMPA answers HTTP 412 with a JavaScript anti-bot challenge (a dynamic <meta> token "
            "that must be solved by running obfuscated script) before any content is served. "
            "Solving or replaying that challenge is a WAF bypass, which the collection protocol "
            "forbids, so the source is recorded as blocked rather than retried."
        ),
    )


def probe_china_nmpa_udi(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "china_nmpa_udi"
    probes: list[dict[str, Any]] = []

    r = client.get("https://udi.nmpa.gov.cn/", accept="text/html")
    entry = _entry("udi_portal_home", r, directory, source_id)
    if r.ok:
        html = r.text
        entry["script_refs"] = re.findall(r'src="([^"]+\.js[^"]*)"', html)[:8]
        entry["has_search_form"] = ("search" in html.lower()) or ("query" in html.lower())
        entry["challenge_markers"] = [
            marker for marker in ("meta id=", "r='m'", "acw_sc__v2", "arg1=") if marker in html[:5000]
        ]
    probes.append(entry)

    # common device-query paths of the UDI portal's own front end
    for path in ("/udi/query", "/api/udi/search"):
        if client.remaining() <= 0:
            break
        r = client.get("https://udi.nmpa.gov.cn" + path, params={"di": KNOWN_DI["medtronic"]})
        probes.append(_entry("query_" + path.strip("/").replace("/", "_"), r, directory, source_id))

    return base.ProbeOutcome(
        source_id=source_id,
        status="UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "The NMPA UDI portal serves a JSP/JS shell whose data calls are session-bound and "
            "undocumented; no public machine interface was found and the documented paths did "
            "not return records. Recorded as unavailable rather than guessed at."
        ),
    )


def probe_australia_tga_artg(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "australia_tga_artg"
    probes: list[dict[str, Any]] = []

    r = client.get("https://www.tga.gov.au/", accept="text/html")
    probes.append(_entry("portal_home", r, directory, source_id))

    r = client.get("https://www.tga.gov.au/resources/artg", accept="text/html")
    entry = _entry("artg_search", r, directory, source_id)
    if r.body:
        text = r.text
        entry["challenge_markers"] = [
            marker
            for marker in ("bm-verify", "_sec/verify", "triggerInterstitialChallenge", "Akamai", "pow")
            if marker in text
        ]
        entry["bytes_served"] = len(r.body)
    probes.append(entry)

    r = client.get(
        "https://www.tga.gov.au/resources/artg", params={"search_api_fulltext": "Medtronic"}, accept="text/html"
    )
    probes.append(_entry("artg_query_medtronic", r, directory, source_id))

    return base.ProbeOutcome(
        source_id=source_id,
        status="BLOCKED_BY_POLICY",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "The TGA site root is reachable, but the ARTG search path answers with an Akamai "
            "Bot Manager interstitial that requires solving a proof-of-work challenge via "
            "`/_sec/verify`; completing it programmatically is exactly the WAF circumvention "
            "the protocol forbids. No official ARTG dataset is mirrored on data.gov.au either, "
            "so the Australian register is a documented but inaccessible source for this study."
        ),
    )


# ------------------------------------------------------------------ remaining P2
def probe_uk_mhra_device(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "uk_mhra_device"
    probes: list[dict[str, Any]] = []

    r = client.get(
        "https://www.gov.uk/api/search.json",
        params={
            "q": "medical device register",
            "filter_organisations": "medicines-and-healthcare-products-regulatory-agency",
            "count": 5,
            "fields": "title,link,description,public_timestamp",
        },
    )
    entry = _entry("govuk_search_medical_device_register", r, directory, source_id)
    if r.ok:
        try:
            payload = r.json()
        except ValueError:
            payload = {}
        entry["total"] = payload.get("total")
        entry["titles"] = [row.get("title") for row in payload.get("results", [])]
        entry["links"] = [row.get("link") for row in payload.get("results", [])]
    probes.append(entry)

    r = client.get(
        "https://www.gov.uk/api/search.json",
        params={
            "q": "public register medical devices searchable",
            "filter_organisations": "medicines-and-healthcare-products-regulatory-agency",
            "count": 3,
            "fields": "title,link,public_timestamp",
        },
    )
    entry = _entry("govuk_search_public_register", r, directory, source_id)
    if r.ok:
        try:
            payload = r.json()
        except ValueError:
            payload = {}
        entry["titles"] = [row.get("title") for row in payload.get("results", [])]
    probes.append(entry)

    return base.ProbeOutcome(
        source_id=source_id,
        status="UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "GOV.UK search for MHRA device material returns only *guidance* (how a manufacturer "
            "registers a device), not a public register of licensed products: the UK has no "
            "searchable public medical-device register equivalent to MDALL/EUDAMED/GUDID. There "
            "is therefore no product-level UK regulatory dataset to collect."
        ),
    )


def probe_japan_pmda(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "japan_pmda"
    probes: list[dict[str, Any]] = []

    r = client.get("https://www.pmda.go.jp/english/", accept="text/html")
    probes.append(_entry("english_portal", r, directory, source_id))

    r = client.get("https://www.pmda.go.jp/PmdaSearch/kikiSearch/", accept="text/html")
    entry = _entry("device_search_page", r, directory, source_id)
    if r.ok:
        html = r.text
        entry["form_action"] = (re.findall(r'<form[^>]*action="([^"]*)"', html) or [""])[0]
        entry["form_method"] = (re.findall(r'<form[^>]*method="([^"]*)"', html) or [""])[0]
        entry["field_names"] = re.findall(r'<input[^>]*name="([^"]+)"', html)[:12]
        entry["has_faces_viewstate"] = "javax.faces" in html
    probes.append(entry)

    r = client.get(
        "https://www.pmda.go.jp/PmdaSearch/kikiSearch/", params={"nameWord": "Medtronic"}, accept="text/html"
    )
    entry = _entry("get_with_query_rejected", r, directory, source_id, note="does a GET with query params return results?")
    if r.ok:
        entry["result_rows"] = r.text.count("<tr")
        entry["contains_query_term"] = "Medtronic" in r.text
    probes.append(entry)

    return base.ProbeOutcome(
        source_id=source_id,
        status="UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "PMDA's device database (kikiSearch) is a legacy servlet that renders an HTML form and "
            "only answers a form POST; a GET with query parameters returns the empty form again. "
            "No documented API and no bulk release exist, so there is no machine-readable path "
            "for this study. The pages themselves are reachable, so this is 'no machine "
            "interface', not 'no data'."
        ),
    )


def probe_brazil_anvisa(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    source_id = "brazil_anvisa"
    probes: list[dict[str, Any]] = []

    r = client.get("https://consultas.anvisa.gov.br/", accept="text/html")
    probes.append(_entry("consultas_spa", r, directory, source_id))

    r = client.get("https://consultas.anvisa.gov.br/api/consulta/produtos-saude")
    probes.append(_entry("api_produtos_saude_without_token", r, directory, source_id))

    r = client.get(
        "https://consultas.anvisa.gov.br/api/consulta/medicamentos",
        params={"page": 1},
        headers={"Accept": "application/json"},
    )
    probes.append(_entry("api_medicamentos_without_token", r, directory, source_id))

    return base.ProbeOutcome(
        source_id=source_id,
        status="REQUIRES_REGISTRATION",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p.get("ok")],
        notes=(
            "consultas.anvisa.gov.br is an Angular SPA; its JSON API answers 401/403 without a "
            "bearer token issued by the ANVISA login flow, so device registrations require a "
            "registered account. No anonymous machine interface was found."
        ),
    )


# ------------------------------------------------------------------------ registry
PROBES: dict[str, Callable[[base.HttpClient, Path], base.ProbeOutcome]] = {
    "openfda_device_510k": probe_openfda_device_510k,
    "openfda_device_pma": probe_openfda_device_pma,
    "openfda_bulk_download": probe_openfda_bulk_download,
    "accessgudid": probe_accessgudid,
    "fda_gudid_download": probe_fda_gudid_download,
    "openfda_device_classification": probe_openfda_device_classification,
    "openfda_device_registrationlisting": probe_openfda_device_registrationlisting,
    "eudamed": probe_eudamed,
    "canada_mdall": probe_canada_mdall,
    "china_nmpa_device": probe_china_nmpa_device,
    "china_nmpa_udi": probe_china_nmpa_udi,
    "australia_tga_artg": probe_australia_tga_artg,
    "uk_mhra_device": probe_uk_mhra_device,
    "japan_pmda": probe_japan_pmda,
    "brazil_anvisa": probe_brazil_anvisa,
}

#: source_id -> (budget, min_interval, timeout, max_retries)
PROBE_SPECS: dict[str, tuple[int, float, float, int]] = {
    "openfda_device_510k": (10, 0.9, 45.0, 1),
    "openfda_device_pma": (10, 0.9, 45.0, 1),
    "openfda_bulk_download": (5, 0.9, 120.0, 1),
    "accessgudid": (6, 1.0, 45.0, 1),
    "fda_gudid_download": (5, 1.0, 120.0, 1),
    "openfda_device_classification": (5, 0.9, 45.0, 1),
    "openfda_device_registrationlisting": (5, 0.9, 45.0, 1),
    "eudamed": (5, 1.2, 45.0, 1),
    "canada_mdall": (12, 1.0, 90.0, 1),
    "china_nmpa_device": (4, 1.2, 45.0, 1),
    "china_nmpa_udi": (4, 1.2, 45.0, 1),
    "australia_tga_artg": (4, 1.5, 90.0, 1),
    "uk_mhra_device": (4, 1.0, 45.0, 1),
    "japan_pmda": (5, 1.2, 60.0, 1),
    "brazil_anvisa": (5, 1.2, 45.0, 1),
}


def _write_samples_manifest(root: Path, source_id: str, outcome: base.ProbeOutcome) -> Path | None:
    """Write ``samples/<source_id>/SAMPLES.json`` from the descriptors actually stored."""
    rows: list[dict[str, Any]] = []
    fetched_at = outcome.verified_at or base.utc_iso()
    for probe in outcome.probes:
        sample = probe.get("sample")
        if not isinstance(sample, Mapping):
            continue
        rows.append(
            {
                "file": sample.get("name"),
                "path": sample.get("path"),
                "request_name": probe.get("name"),
                "request_url": probe.get("url"),
                "http_status": probe.get("status"),
                "fetched_at": fetched_at,
                "source_id": source_id,
                "total_bytes": sample.get("total_bytes"),
                "stored_bytes": sample.get("stored_bytes"),
                "truncated": sample.get("truncated"),
                "sha256_full": sample.get("sha256_full"),
                "sha256_stored": sample.get("sha256_stored"),
            }
        )
    if not rows:
        return None
    target = Path(root) / "samples" / source_id / "SAMPLES.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "medradar.external.samples.v1",
        "source_id": source_id,
        "generated_at": base.utc_iso(),
        "note": (
            "Every file below is a byte-for-byte slice of a live HTTP response captured by "
            "HttpClient. `sha256_full` is the digest of the complete response body; "
            "`sha256_stored` covers only the stored head when truncated is true."
        ),
        "samples": rows,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def run_one(source_id: str, root: Path = DEFAULT_ROOT) -> base.ProbeOutcome:
    if source_id not in PROBES:
        raise KeyError(f"no probe for {source_id!r}; known: {sorted(PROBES)}")
    budget, interval, timeout, retries = PROBE_SPECS[source_id]
    outcome = base.run_probe(
        source_id,
        Path(root),
        PROBES[source_id],
        budget=budget,
        min_interval=interval,
        timeout=timeout,
        max_retries=retries,
    )
    _write_samples_manifest(Path(root), source_id, outcome)
    return outcome


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        root = Path(args[i + 1])
        del args[i : i + 2]
    if "--list" in args:
        for source_id in PROBES:
            print(source_id)
        return 0
    targets = sorted(PROBES) if ("--all" in args or not args) else args
    failures = 0
    for source_id in targets:
        outcome = run_one(source_id, root)
        print(
            f"{source_id}: {outcome.status} requests={outcome.requests} "
            f"probes={len(outcome.probes)} error={outcome.error or '-'}"
        )
        if outcome.status == "UNAVAILABLE" and outcome.error:
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
