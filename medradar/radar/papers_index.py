"""Link the harvested full-text corpus to devices, by building a small inverted index.

Why an index and not a scan
--------------------------
The corpus is 2,643 papers and about 70 million characters. Searching it per request would make
the device view wait on a linear pass, and the view's contract is that nothing is fetched or
scanned while a reader waits.

The vocabulary is the interesting part. Papers are harvested by topic, so nothing in a paper says
which device it is about; the only reliable join is a name that appears in both. Those names come
from the device register - brand names, model numbers and company names - and are indexed only
where they actually occur in a paper. A term nobody wrote costs nothing.

What this cannot do, and says so
--------------------------------
A mention is not evidence that the paper studies this device: a brand word can appear in a
reference list, an exclusion criterion, or a competitor comparison. The count is therefore reported
as "papers whose text contains this name", the sample carries the paper id and title so a reader
can check, and an absent index is reported as `paper_index_absent` - never as "no research exists".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TERMS_TABLE = """
CREATE TABLE IF NOT EXISTS paper_term (
    term    TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    title   TEXT,
    year    TEXT,
    hits    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (term, paper_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_term_term ON paper_term(term);
"""

#: Shortest token worth indexing. Three letters match too much ("aaa", "inc"), five misses real
#: model numbers ("X120"), so four.
MIN_TOKEN = 4

#: Counters that stay valid until the index is rebuilt, keyed by the store object's identity.
_COUNTERS: dict[int, dict[str, Any]] = {}
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-]{2,}", re.IGNORECASE)


def tokens(text: str) -> list[str]:
    """Lower-cased alphanumeric tokens of length >= MIN_TOKEN, de-duplicated in order."""
    seen: dict[str, None] = {}
    for match in _TOKEN.finditer(str(text or "")):
        token = match.group(0).lower().strip("-")
        if len(token) >= MIN_TOKEN:
            seen.setdefault(token, None)
    return list(seen)


def ensure_tables(reference) -> None:
    reference.conn.executescript(TERMS_TABLE)


def tables_present(reference) -> bool:
    """An empty table is not an imported one: it would answer "no papers" to every device."""
    try:
        ensure_tables(reference)
        row = reference.conn.execute("SELECT COUNT(*) FROM paper_term").fetchone()
    except Exception:  # noqa: BLE001 - a missing table is a "not imported", not a crash
        return False
    return bool(row and int(row[0]) > 0)


def compact(value: str) -> str:
    """The run-together form of a name: "Galaxy Star" and "GalaxyStar" are the same product.

    Measured need: the register writes brand names with spaces, papers write them without, and a
    vocabulary built only from space-separated tokens indexed nothing at all.
    """
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def vocabulary(reference, *, limit: int = 200_000) -> set[str]:
    """Every name in the register that could plausibly appear in a paper.

    Brand names and model numbers are the discriminators; company names are included because a
    paper often names the manufacturer without the product. Each value contributes both its
    space-separated tokens and its run-together form.
    """
    words: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "")
        for token in tokens(text):
            if len(token) >= MIN_TOKEN:
                words.add(token)
        joined = compact(text)
        if len(joined) >= MIN_TOKEN:
            words.add(joined)

    queries = (
        ("SELECT brand_name AS v FROM udi_device WHERE brand_name IS NOT NULL LIMIT ?", limit),
        ("SELECT version_or_model AS v FROM udi_device WHERE version_or_model IS NOT NULL LIMIT ?",
         limit),
        ("SELECT company_name AS v FROM udi_company WHERE company_name IS NOT NULL LIMIT ?", limit),
    )
    for sql, cap in queries:
        try:
            for row in reference.conn.execute(sql, (cap,)):
                add(row[0])
        except Exception:  # noqa: BLE001 - a partial vocabulary still indexes something useful
            continue
    return words


def _paper_files(corpus_root: str | Path) -> Iterable[Path]:
    root = Path(corpus_root)
    if not root.exists():
        return []
    return sorted(root.glob("*.json"))


def index_corpus(reference, corpus_root: str | Path, *, vocab: set[str] | None = None,
                 limit: int | None = None) -> dict[str, Any]:
    """Scan the corpus once and record which vocabulary terms each paper contains."""
    ensure_tables(reference)
    vocab = vocab if vocab is not None else vocabulary(reference)
    if not vocab:
        raise ValueError("the vocabulary is empty; index the device register first")
    files = list(_paper_files(corpus_root))
    if limit:
        files = files[:limit]
    papers = 0
    rows = 0
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        paper_id = str(payload.get("identifier") or path.stem)
        title = str(payload.get("title") or "")[:400]
        year = str(payload.get("year") or payload.get("published_at") or "")[:10]
        body = " ".join([
            title,
            str(payload.get("abstract") or ""),
            " ".join(str(v) for v in (payload.get("sections") or {}).values()),
        ])
        counts: dict[str, int] = {}
        for token in _TOKEN.finditer(body):
            lowered = token.group(0).lower().strip("-")
            if lowered in vocab:
                counts[lowered] = counts.get(lowered, 0) + 1
        if not counts:
            continue
        papers += 1
        reference.conn.executemany(
            "INSERT OR REPLACE INTO paper_term (term, paper_id, title, year, hits) "
            "VALUES (?,?,?,?,?)",
            [(term, paper_id, title, year, n) for term, n in counts.items()])
        rows += len(counts)
    reference.conn.commit()
    invalidate_cache()  # the counts just changed; anything cached describes the old index
    return {"papers_indexed": papers, "term_rows": rows, "vocabulary": len(vocab),
            "files_seen": len(files)}


def _cache_for(reference) -> dict[str, Any]:
    """Per-store counters that cannot change until the index is rebuilt.

    Measured: `SELECT COUNT(DISTINCT paper_id) FROM paper_term` is a full scan of 637,318 rows and
    took ~0.5 s. It was called once per device, so a company query resolving 25 devices spent 13 s
    of a 15 s page repeating the same count. The index only changes when index_corpus() runs, and
    that clears this cache.
    """
    key = id(reference)
    cached = _COUNTERS.get(key)
    if cached is None:
        cached = {"total": None, "df": {}}
        _COUNTERS[key] = cached
    return cached


def invalidate_cache() -> None:
    """Forget cached document frequencies. Call after rebuilding the index."""
    _COUNTERS.clear()


def _document_frequency(reference, term: str) -> int:
    cached = _cache_for(reference)["df"]
    if term in cached:
        return int(cached[term])
    row = reference.conn.execute(
        "SELECT COUNT(DISTINCT paper_id) FROM paper_term WHERE term = ?", (term,)).fetchone()
    value = int(row[0]) if row and row[0] is not None else 0
    cached[term] = value
    return value


def _total_papers(reference) -> int:
    cached = _cache_for(reference)
    if cached["total"] is not None:
        return int(cached["total"])
    row = reference.conn.execute(
        "SELECT COUNT(DISTINCT paper_id) FROM paper_term").fetchone()
    value = int(row[0]) if row and row[0] is not None else 0
    cached["total"] = value
    return value


def distinctive_terms(reference, terms: Sequence[str], *, max_df_ratio: float = 0.02
                      ) -> tuple[list[str], list[str]]:
    """Split terms into those that can identify a device and those that cannot.

    Measured failure: querying the index for a spinal implant returned 1,759 of 2,552 papers,
    because "spinal" and "system" are in the register as brand words and in most clinical text as
    ordinary vocabulary. A term is kept when it is rare enough to discriminate, or when it carries a
    digit (a model number), or when it is long enough to be a run-together product name.
    """
    total = _total_papers(reference)
    if not total:
        return [], list(terms)
    ceiling = max(3, int(total * max_df_ratio))
    kept: list[str] = []
    generic: list[str] = []
    for term in terms:
        if any(ch.isdigit() for ch in term) or len(term) >= 12:
            kept.append(term)
            continue
        if _document_frequency(reference, term) <= ceiling:
            kept.append(term)
        else:
            generic.append(term)
    return kept, generic


def papers_for_tokens(reference, terms: Sequence[str], *, limit: int = 5,
                      max_df_ratio: float = 0.02) -> dict[str, Any]:
    """Papers whose text contains any of these *discriminating* terms, most mentions first."""
    if not tables_present(reference):
        return {"available": False, "papers": 0, "recent": [], "terms": [],
                "generic_terms": []}
    cleaned = [t for t in dict.fromkeys(tokens(" ".join(terms))) if t]
    if not cleaned:
        return {"available": True, "papers": 0, "recent": [], "terms": [], "generic_terms": []}
    usable, generic = distinctive_terms(reference, cleaned, max_df_ratio=max_df_ratio)
    if not usable:
        # Every term was ordinary vocabulary. Saying "no discriminating name" is the honest answer;
        # matching anyway would return most of the corpus and call it evidence.
        return {"available": True, "papers": 0, "recent": [], "terms": [],
                "generic_terms": generic}
    placeholders = ",".join("?" for _ in usable)
    total = reference.conn.execute(
        f"SELECT COUNT(DISTINCT paper_id) FROM paper_term WHERE term IN ({placeholders})",
        usable).fetchone()[0]
    recent = [
        {"paper_id": row[0], "title": row[1], "year": row[2], "hits": row[3],
         "matched_terms": row[4]}
        for row in reference.conn.execute(
            f"SELECT paper_id, MAX(title), MAX(year), SUM(hits), GROUP_CONCAT(term) "
            f"FROM paper_term WHERE term IN ({placeholders}) "
            f"GROUP BY paper_id ORDER BY SUM(hits) DESC LIMIT ?",
            (*usable, max(1, limit)))
    ]
    return {"available": True, "papers": int(total), "recent": recent, "terms": usable,
            "generic_terms": generic}


def summary(reference) -> dict[str, Any]:
    if not tables_present(reference):
        return {"available": False, "papers": 0, "terms": 0}
    papers = reference.conn.execute(
        "SELECT COUNT(DISTINCT paper_id) FROM paper_term").fetchone()[0]
    terms = reference.conn.execute("SELECT COUNT(DISTINCT term) FROM paper_term").fetchone()[0]
    return {"available": True, "papers": int(papers), "terms": int(terms)}


__all__ = [
    "MIN_TOKEN",
    "ensure_tables",
    "index_corpus",
    "papers_for_tokens",
    "summary",
    "tables_present",
    "tokens",
    "vocabulary",
]
