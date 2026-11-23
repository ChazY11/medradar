"""The 510(k) -> device bridge: close the loop between a document and a registered device.

Why this is the hinge
---------------------
Three corpora exist and none of them is joined to the others by anything better than a name:

* a **510(k) Summary** states what a device does and how equivalence was argued (a document);
* the **UDI register** states the labeler DUNS and the model number (an identity);
* **MAUDE** states which model failed, in what way (an outcome).

String-matching an applicant name across those three resolves 35.2 % of events, which is the
defect the DUNS spine was introduced to fix. The bridge is a field, not a guess: openFDA UDI
records carry ``premarket_submissions[].submission_number``, the clearance number itself. So

    510(k) document (K number) -> UDI device (submission_number) -> labeler DUNS + model
        -> MAUDE event (model_number) -> failure narrative

is a chain of equality joins.

Why the sweep is restricted
---------------------------
Sweeping all 5,182,695 UDI records to find 1,584,610 of them would waste two thirds of a
rate-limited budget. openFDA accepts a range query on the same field, so the bridge set is
reachable directly:

    premarket_submissions.submission_number:[K000000 TO K999999]   -> 1,584,610 records

measured 2026-11-21, against 5,182,695 for the unfiltered dataset. That is the difference
between ~1,586 pages and ~5,187 pages for the same information.

Partial sweeps are reported as partial
--------------------------------------
Anonymous openFDA allows roughly a thousand requests a day, so a 1,586-page sweep will not
finish in one sitting. The cursor lives in ``reference_kv`` and the result says
``complete=False`` with the reason - the alternative, silently claiming the bridge is whole,
would put a fake zero in front of a user.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ENDPOINT = "https://api.fda.gov/device/udi.json"
#: Only records that actually declare a 510(k)/PMA number.
BRIDGE_SEARCH = "premarket_submissions.submission_number:[K000000 TO K999999]"
#: Measured 2026-11-21 with an unfiltered dataset total of 5,182,695.
BRIDGE_TOTAL_MEASURED = 1_584_610
PAGE_SIZE = 999
STATE_KEY = "premarket_bridge"


@dataclass
class BridgeStats:
    pages: int = 0
    rows_seen: int = 0
    devices_written: int = 0
    submissions_written: int = 0
    companies: int = 0
    skipped_rows: int = 0
    total_available: int | None = None
    cursor: int = 0
    complete: bool = False
    elapsed_seconds: float = 0.0
    stop_reason: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "rows_seen": self.rows_seen,
            "devices_written": self.devices_written,
            "submissions_written": self.submissions_written,
            "companies": self.companies,
            "skipped_rows": self.skipped_rows,
            "total_available": self.total_available,
            "cursor": self.cursor,
            "complete": self.complete,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "stop_reason": self.stop_reason,
        }


def sync_bridge(fetcher, reference, *, max_pages: int | None = None,
                page_size: int = PAGE_SIZE, reset: bool = False,
                progress: Callable[[BridgeStats], None] | None = None) -> BridgeStats:
    """Page the bridge set into ``udi_device`` / ``udi_premarket``, resuming from the cursor."""
    from .http import with_openfda_key

    state = {} if reset else (reference.kv_get(STATE_KEY, {}) or {})
    stats = BridgeStats(cursor=int(state.get("cursor") or 0))
    started = time.perf_counter()
    limit = min(int(page_size), PAGE_SIZE)

    while True:
        if max_pages is not None and stats.pages >= max_pages:
            stats.stop_reason = f"page cap {max_pages} reached"
            break
        params = with_openfda_key({"search": BRIDGE_SEARCH, "limit": limit,
                                   "skip": stats.cursor})
        data = fetcher.get_json(ENDPOINT, params=params, allow_not_found=True)
        if not data:
            stats.complete = True
            stats.stop_reason = "source returned no further pages"
            break
        meta = (data.get("meta") or {}).get("results") or {}
        stats.total_available = int(meta.get("total") or 0) or stats.total_available
        rows = [row for row in (data.get("results") or []) if isinstance(row, dict)]
        if not rows:
            stats.complete = True
            break

        devices, submissions, companies, skipped = reference.write_udi_rows(rows)
        stats.devices_written += devices
        stats.submissions_written += submissions
        stats.companies = max(stats.companies, companies)
        stats.skipped_rows += skipped
        stats.rows_seen += len(rows)
        stats.pages += 1
        stats.cursor += len(rows)
        reference.kv_set(STATE_KEY, {"cursor": stats.cursor,
                                     "total": stats.total_available})
        if progress:
            progress(stats)
        if stats.total_available and stats.cursor >= stats.total_available:
            stats.complete = True
            break
        if len(rows) < limit:
            stats.complete = True
            break

    stats.elapsed_seconds = time.perf_counter() - started
    return stats


@dataclass
class AlignmentReport:
    documents: int = 0
    documents_with_text: int = 0
    aligned: int = 0
    aligned_with_text: int = 0
    with_duns: int = 0
    devices: int = 0
    distinct_labelers: int = 0
    by_labeler: dict[str, int] = field(default_factory=dict)
    samples: list[dict[str, Any]] = field(default_factory=list)
    missing_k: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return round(self.aligned / self.documents, 4) if self.documents else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "documents": self.documents,
            "documents_with_text": self.documents_with_text,
            "aligned": self.aligned,
            "align_rate": self.rate,
            "aligned_with_text": self.aligned_with_text,
            "with_duns": self.with_duns,
            "devices": self.devices,
            "distinct_labelers": self.distinct_labelers,
            "top_labelers": sorted(self.by_labeler.items(), key=lambda kv: -kv[1])[:12],
            "samples": self.samples[:8],
            "unaligned_examples": self.missing_k[:8],
        }


def document_k_numbers(store_root: str | Path) -> list[str]:
    """Every K number in a DocumentStore, from its JSON sidecars.

    The sidecar calls the field ``identifier`` (that is the store's own vocabulary: the same
    file could describe a PMA number later), so reading ``k_number`` here silently produced an
    empty list. Kept tolerant of both names rather than renaming the store's schema for one
    caller.
    """
    return [entry["k_number"] for entry in document_entries(store_root)]


def document_entries(store_root: str | Path) -> list[dict[str, Any]]:
    """Sidecar metadata for every stored document: K number, status and text length."""
    entries: list[dict[str, Any]] = []
    for path in sorted(Path(store_root).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        k_number = str(payload.get("k_number") or payload.get("identifier") or "").strip().upper()
        if not k_number:
            continue
        entries.append({
            "k_number": k_number,
            "status": payload.get("status"),
            "text_chars": int(payload.get("text_chars") or payload.get("char_count") or 0),
            "sections": len(payload.get("sections") or {}),
        })
    return entries


def align_corpus(store_root: str | Path, reference, *,
                 limit: int | None = None) -> AlignmentReport:
    """Join each stored 510(k) document to the devices its clearance number names."""
    report = AlignmentReport()
    entries = document_entries(store_root)
    if limit is not None:
        entries = entries[:limit]
    distinct_duns: set[str] = set()
    for entry in entries:
        k_number = entry["k_number"]
        has_text = entry.get("status") == "text" and int(entry.get("text_chars") or 0) > 0
        report.documents += 1
        if has_text:
            report.documents_with_text += 1
        devices = reference.devices_for_submission(k_number)
        if not devices:
            if len(report.missing_k) < 40:
                report.missing_k.append(k_number)
            continue
        report.aligned += 1
        if has_text:
            report.aligned_with_text += 1
        report.devices += len(devices)
        for device in devices:
            duns = device.get("labeler_duns")
            if not duns:
                continue
            report.with_duns += 1
            distinct_duns.add(str(duns))
            name = str(device.get("company_name") or "?")
            report.by_labeler[name] = report.by_labeler.get(name, 0) + 1
        if len(report.samples) < 8:
            first = devices[0]
            report.samples.append({
                "k_number": k_number,
                "has_text": has_text,
                "text_chars": entry.get("text_chars"),
                "sections": entry.get("sections"),
                "device_key": first.get("device_key"),
                "di": first.get("di"),
                "brand_name": first.get("brand_name"),
                "company_name": first.get("company_name"),
                "labeler_duns": first.get("labeler_duns"),
                "version_or_model": first.get("version_or_model"),
                "catalog_number": first.get("catalog_number"),
                "devices_for_submission": len(devices),
            })
    report.distinct_labelers = len(distinct_duns)
    return report


def link_submissions(fetcher, reference, k_numbers: Iterable[str], *,
                     batch: int = 25, progress: Callable[[int, int], None] | None = None
                     ) -> dict[str, Any]:
    """Write the bridge for **specific** clearance numbers, by batched OR query.

    Two modes, and they answer different questions:

    * :func:`sync_bridge` sweeps the whole bridge set (~1,586 pages) so any future document
      joins locally;
    * this one asks about the numbers already in hand, so a corpus of 960 documents is fully
      aligned in seconds instead of waiting two hours.

    The measured reason this matters: after a 15-page sweep the cursor covered 0.9 % of the
    bridge set and only **1 of 960** documents aligned. The chain was proven, the coverage was
    not - and those are different claims.
    """
    from .http import with_openfda_key

    wanted = sorted({str(k).strip().upper() for k in k_numbers if str(k).strip()})
    found: set[str] = set()
    devices = submissions = 0
    queries = 0
    for start in range(0, len(wanted), batch):
        chunk = wanted[start:start + batch]
        clause = "(" + " OR ".join(f'"{number}"' for number in chunk) + ")"
        params = with_openfda_key({
            "search": f"premarket_submissions.submission_number:{clause}",
            "limit": PAGE_SIZE, "skip": 0,
        })
        queries += 1
        data = fetcher.get_json(ENDPOINT, params=params, allow_not_found=True)
        rows = [row for row in ((data or {}).get("results") or []) if isinstance(row, dict)]
        if rows:
            written, links, _companies, _skipped = reference.write_udi_rows(rows)
            devices += written
            submissions += links
            for row in rows:
                for submission in (row.get("premarket_submissions") or []):
                    number = str(submission.get("submission_number") or "").strip().upper()
                    if number in chunk:
                        found.add(number)
        if progress:
            progress(start + len(chunk), len(wanted))
    return {
        "requested": len(wanted),
        "queries": queries,
        "resolved": len(found),
        "devices_written": devices,
        "submissions_written": submissions,
    }


def bridge_coverage(reference) -> dict[str, Any]:
    def scalar(sql: str) -> int:
        row = reference.conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    total_available = (reference.kv_get(STATE_KEY, {}) or {}).get("total")
    return {
        "premarket_links": scalar("SELECT COUNT(*) FROM udi_premarket"),
        "distinct_submissions": scalar(
            "SELECT COUNT(DISTINCT submission_number) FROM udi_premarket"),
        "distinct_labelers_linked": scalar(
            "SELECT COUNT(DISTINCT labeler_duns) FROM udi_premarket "
            "WHERE labeler_duns IS NOT NULL"),
        "bridge_cursor": (reference.kv_get(STATE_KEY, {}) or {}).get("cursor", 0),
        "bridge_total_available": total_available,
        "bridge_complete": bool(
            total_available
            and (reference.kv_get(STATE_KEY, {}) or {}).get("cursor", 0) >= int(total_available)
        ),
    }


__all__ = [
    "AlignmentReport",
    "BRIDGE_SEARCH",
    "BRIDGE_TOTAL_MEASURED",
    "BridgeStats",
    "align_corpus",
    "bridge_coverage",
    "document_entries",
    "link_submissions",
    "document_k_numbers",
    "sync_bridge",
]
