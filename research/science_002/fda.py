"""openFDA device sources: bulk 510(k) export, normalisation, and the applicant index.

Why the bulk export and not paged API calls
-------------------------------------------
The study needs (a) every distinct 510(k) applicant string and its filing count,
to do entity resolution once and auditably, and (b) the complete clearance
record of the firms that survive resolution. Paged API access cannot produce (a)
because of the `skip` cap, so the official bulk export is downloaded once,
hashed, and streamed. Everything after the download is offline.

What openFDA does and does not give (see TIME_SEMANTICS.md)
-----------------------------------------------------------
`decision_date` is the day FDA decided the submission. It is *not* a
publication timestamp: FDA's public 510(k) database is refreshed by an
undocumented batch process, and openFDA exposes only a dataset-level
`last_updated` date. `decision_date` is therefore used as the earliest possible
public-availability bound (a conservative lower bound), never as "the world knew
it then". `date_received` is the day FDA received the submission and is a
different event entirely.

Fields consumed (all as published, none derived):
    k_number, applicant, decision_date, date_received, product_code,
    device_name, advisory_committee, decision_code, clearance_type,
    country_code, state, city, third_party_flag, statement_or_summary
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from .sources import Cache, SourceError, sha256_bytes

MANIFEST_URL = "https://api.fda.gov/download.json"
BULK_KEY = "510k"
PMA_BULK_KEY = "pma"

RECORD_FIELDS = (
    "k_number", "applicant", "decision_date", "date_received", "product_code",
    "device_name", "advisory_committee", "decision_code", "clearance_type",
    "country_code", "state", "city", "third_party_flag",
)

#: A 510(k) whose decision code marks it as *not* cleared must not be counted as
#: a clearance event. openFDA uses SESE for "substantially equivalent" (cleared).
#: We keep the published code and let the analysis decide, but the primary event
#: definition is clearance_type/decision_code == cleared.
CLEARED_DECISION_CODES = ("SESE",)


def manifest(cache: Cache) -> dict[str, Any]:
    return cache.get_json(MANIFEST_URL)


def bulk_partitions(manifest_payload: dict[str, Any], key: str = BULK_KEY) -> list[dict[str, Any]]:
    try:
        return list(manifest_payload["results"]["device"][key]["partitions"])
    except (KeyError, TypeError) as exc:  # pragma: no cover - manifest shape drift
        raise SourceError(f"unexpected openFDA manifest shape for {key}") from exc


def download_bulk(cache: Cache, target_dir: Path, key: str = BULK_KEY,
                  manifest_payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    payload = manifest_payload if manifest_payload is not None else manifest(cache)
    out = []
    for part in bulk_partitions(payload, key):
        url = part["file"]
        target = target_dir / url.rsplit("/", 1)[-1]
        meta = cache.download(url, target)
        out.append({"url": url, "path": str(target), "records": part.get("records"),
                    "export_date": part.get("export_date"), **meta})
    return out


def _member(zf: zipfile.ZipFile) -> str:
    names = [n for n in zf.namelist() if n.lower().endswith(".json")]
    if not names:
        raise SourceError("openFDA archive has no JSON member")
    return names[0]


def iter_json_records(path: Path, chunk: int = 1 << 22) -> Iterator[dict[str, Any]]:
    """Yield objects from the `results` array of a large JSON file, streaming.

    openFDA's bulk files are `{"meta": ..., "results": [...], ...}`. Loading one
    into memory costs > 1 GB, so the array is decoded one element at a time with
    a rolling buffer. Only the `results` array is read.
    """
    decoder = json.JSONDecoder()
    with zipfile.ZipFile(path) as zf:
        with zf.open(_member(zf)) as handle:
            buffer = ""
            consumed = 0
            started = False
            while True:
                block = handle.read(chunk)
                if not block:
                    break
                buffer += block.decode("utf-8", errors="replace")
                if not started:
                    marker = buffer.find('"results"')
                    if marker < 0:
                        if len(buffer) > 40_000_000:
                            raise SourceError("results key not found in first 40 MB")
                        continue
                    bracket = buffer.find("[", marker)
                    if bracket < 0:
                        continue
                    consumed = bracket + 1
                    started = True
                while True:
                    while consumed < len(buffer) and buffer[consumed] in " \t\r\n,":
                        consumed += 1
                    if consumed >= len(buffer):
                        break
                    if buffer[consumed] == "]":
                        return
                    try:
                        obj, end = decoder.raw_decode(buffer, consumed)
                    except ValueError:
                        break  # need more bytes
                    consumed = end
                    if isinstance(obj, dict):
                        yield obj
                    # drop the consumed prefix to keep the buffer small
                    if consumed > 8_000_000:
                        buffer = buffer[consumed:]
                        consumed = 0


def normalise_record(raw: dict[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for field in RECORD_FIELDS:
        value = raw.get(field)
        row[field] = "" if value is None else str(value).strip()
    return row


def write_records_csv(records: Iterable[dict[str, Any]], target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(RECORD_FIELDS), lineterminator="\n")
    writer.writeheader()
    n = 0
    for raw in records:
        writer.writerow(normalise_record(raw))
        n += 1
    data = buffer.getvalue().encode("utf-8")
    target.write_bytes(data)
    return {"path": str(target), "rows": n, "sha256": sha256_bytes(data)}


def read_records_csv(path: "Path | str") -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_day(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def applicant_index(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate 510(k) records by the raw published applicant string."""
    index: dict[str, dict[str, Any]] = {}
    for raw in records:
        name = (raw.get("applicant") or "").strip()
        if not name:
            continue
        key = name.upper()
        entry = index.setdefault(key, {
            "applicant": name, "n": 0, "first_decision": None, "last_decision": None,
            "cleared_n": 0, "product_codes": set(), "k_numbers": 0,
        })
        entry["n"] += 1
        day = raw.get("decision_date") or ""
        if day:
            if entry["first_decision"] is None or day < entry["first_decision"]:
                entry["first_decision"] = day
            if entry["last_decision"] is None or day > entry["last_decision"]:
                entry["last_decision"] = day
        if (raw.get("decision_code") or "") in CLEARED_DECISION_CODES:
            entry["cleared_n"] += 1
        if raw.get("product_code"):
            entry["product_codes"].add(raw["product_code"])
        if raw.get("k_number"):
            entry["k_numbers"] += 1
    return index
