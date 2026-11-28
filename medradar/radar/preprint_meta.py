"""Records the corpus holds without a body - and why each one has none.

The harvest writes a sidecar for every fetch it attempts. Most carry text; some carry only a status and a
reason, because the source refused to serve the body (rate limiting, an operator that blocks automated clients)
or because the record was front matter only. Those files are not failures to hide: they are the list of papers
we know exist and could not read, and 131 of them sit in the production corpus (measured 2026-11-29).

Before round 148 a refused record did not even carry the title, so this list could not have been shown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

#: Statuses that mean "we know about it, we have no text". Anything else with text is not this list.
BODYLESS = ("rate_limited_block", "access_restricted", "empty_record", "no_fulltext", "failed")

#: The note is the part a reader needs; the rest is provenance.
_KEEP = ("title", "doi", "server", "published", "authors", "url", "status", "note")


def _files(corpus_dir: Path) -> Iterable[Path]:
    return sorted(Path(corpus_dir).glob("paper_*.json"))


def scan(corpus_dir: str | Path | None, *, limit: int = 0) -> dict[str, Any]:
    """Every bodyless record, with a per-status breakdown.

    ``limit`` caps the rows returned, not the count: the page prints "showing 20 of 131" rather than pretending
    the list is complete.
    """
    root = Path(corpus_dir) if corpus_dir else None
    if root is None or not root.is_dir():
        return {"available": False, "total": 0, "by_status": {}, "rows": [], "corpus": ""}
    rows: list[dict[str, Any]] = []
    by_status: dict[str, int] = {}
    scanned = 0
    for path in _files(root):
        scanned += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - an unreadable sidecar is counted as unknown, not skipped silently
            by_status["unreadable"] = by_status.get("unreadable", 0) + 1
            continue
        status = str(payload.get("status") or "")
        if status not in BODYLESS:
            continue
        by_status[status] = by_status.get(status, 0) + 1
        row = {key: payload.get(key) for key in _KEEP if payload.get(key) not in (None, "")}
        row.setdefault("status", status)
        row["file"] = path.name
        # The filename encodes what the identifier was; `_out_path` replaces the separators.
        row["identifier"] = path.stem[len("paper_"):]
        rows.append(row)
    # Titled records first: they are the ones a reader can act on.
    rows.sort(key=lambda item: (not item.get("title"), str(item.get("published") or ""), item["file"]))
    total = len(rows)
    if limit:
        rows = rows[:limit]
    # `scanned` is the difference between "no bodyless records" and "no records at all" - the first time this
    # page was wired it pointed at the 510(k) corpus and printed "0 条" about a directory that holds no papers.
    return {"available": True, "total": total, "by_status": by_status, "rows": rows,
            "corpus": str(root), "shown": len(rows), "scanned": scanned}
