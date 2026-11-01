"""Streaming openFDA bulk collector for slow/expensive paged API environments.

The official export manifest points to the same public 510(k)/PMA records as the
paged API. ``ijson`` keeps memory bounded while reading the large ZIP member.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from ...collect_device import (
    SOURCE_BY_KIND, _clean, _event_track, _keyword_index, normalize_510k, normalize_pma,
)
from ...config import DATA_DIR, load_companies, load_tracks
from ...util import add_months, iso, parse_date, read_json, today_utc, utc_now_iso
from ..storage import IntelligenceStore

MANIFEST = "https://api.fda.gov/download.json"
BULK_DIR = Path(os.environ.get("MEDRADAR_BULK_DIR", str(DATA_DIR / "bulk")))


def _download(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            with zipfile.ZipFile(target) as archive:
                if archive.testzip() is None:
                    return target
        except (OSError, zipfile.BadZipFile):
            pass
    partial = target.with_suffix(target.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "MedRadar research (https://github.com/ChazY11/medradar)"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        # A server ignoring Range must overwrite, not append a second full file.
        append = bool(offset and getattr(response, "status", None) == 206)
        with partial.open("ab" if append else "wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
    partial.replace(target)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"corrupt ZIP member in {target}")
    return target


def _manifest(fetcher: Any) -> dict[str, Any]:
    return fetcher.get_json(MANIFEST)


def collect(store: IntelligenceStore, fetcher: Any, *, months: int = 120,
            kinds: tuple[str, ...] = ("510k", "pma"), batch_size: int = 1000) -> dict[str, Any]:
    try:
        import ijson
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install the bulk extra: pip install -e '.[bulk]'") from exc
    end = today_utc()
    start = add_months(end, -max(1, months))
    registry = load_companies("device")
    tracks = load_tracks("device")
    store.db.upsert_companies(registry.all())
    store.db.upsert_tracks(tracks.all())
    code_map = read_json(Path("config/product_code_tracks.json"), {})
    keyword_index = _keyword_index(tracks)
    manifest = _manifest(fetcher)
    stats: dict[str, Any] = {"retrieved_at": utc_now_iso(), "start": iso(start), "end": iso(end),
                             "method": "official_openfda_bulk_stream", "kinds": {}, "warnings": [
        "Bulk exports do not reconstruct historical first-publication timestamps; available_at uses decision_date+14d and timestamp_quality=estimated."
    ]}
    for kind in kinds:
        source = manifest["results"]["device"][kind]
        partition = source["partitions"][0]
        archive_path = _download(partition["file"], BULK_DIR / Path(partition["file"]).name)
        seen = matched = mapped = 0
        batch = []
        started = time.monotonic()
        with zipfile.ZipFile(archive_path) as archive:
            member = next(name for name in archive.namelist() if name.endswith(".json"))
            with archive.open(member) as handle:
                for record in ijson.items(handle, "results.item"):
                    decision = parse_date(record.get("decision_date"))
                    if not decision or not start <= decision <= end:
                        continue
                    seen += 1
                    applicant = _clean(record.get("applicant"))
                    company_key, _confidence, _alias = registry.resolve(applicant)
                    track_id, _how = _event_track(kind, record, code_map, tracks, keyword_index)
                    normalizer = normalize_510k if kind == "510k" else normalize_pma
                    event = normalizer(record, company_key=company_key, track_id=track_id,
                                       track_zh=tracks.name_zh(track_id), as_of=iso(end))
                    if not event:
                        continue
                    available = iso(decision + timedelta(days=14))
                    event.update({"published_at": available, "available_at": available,
                                  "timestamp_quality": "estimated", "source": SOURCE_BY_KIND[kind] + "_bulk"})
                    batch.append(event)
                    matched += bool(company_key)
                    mapped += bool(track_id)
                    if len(batch) >= batch_size:
                        store.db.upsert_events(batch)
                        batch = []
        if batch:
            store.db.upsert_events(batch)
        stats["kinds"][kind] = {
            "export_date": source.get("export_date"), "source_records": source.get("total_records"),
            "in_window": seen, "company_resolved": matched, "track_mapped": mapped,
            "seconds": round(time.monotonic() - started, 2), "archive": str(archive_path),
        }
    return stats
