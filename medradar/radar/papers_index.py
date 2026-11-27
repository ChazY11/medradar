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
import os
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

-- Title, journal and publication date per paper.
--
-- The date lived only inside the corpus JSON, so a field page could not answer "what has been published
-- here lately" without opening 3,500 files. Papers are indexed per field, which makes recency the one
-- question the index could not answer about its own contents.
CREATE TABLE IF NOT EXISTS paper_meta (
    paper_id     TEXT PRIMARY KEY,
    title        TEXT,
    journal      TEXT,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_paper_meta_date ON paper_meta(published_at);

-- How many *distinct brands* in the register contain this word.
--
-- The corpus-side document frequency is not enough to decide whether a word identifies a device.
-- Measured 2026-11-25: a "1.5MM SYSTEM TWIST DRILL" matched fifteen papers through the words
-- "twist" and "drill", which are ordinary instrument nouns, because they are rare in a 3,287-paper
-- corpus while being useless for identification. The register is the right judge: "drill" appears
-- in 2,906 distinct brand names, "system" in 5,198, "screw" in 6,392 - while "arum" appears in 4
-- and "arumnb1safixture" in none. A word that names thousands of different products cannot name one.
CREATE TABLE IF NOT EXISTS brand_token_df (
  term   TEXT PRIMARY KEY,
  brands INTEGER NOT NULL
);

-- The reverse direction: which registered brand names carry this word.
--
-- A reader who arrives with a paper needs to know who makes the thing it studies, and there was no
-- way to ask that - the index only ran device -> paper. Distinct brands number about 200,000, so
-- their tokens fit in a small table, while indexing tokens for all 5.2M device rows would not.
CREATE TABLE IF NOT EXISTS brand_token (
  term       TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  PRIMARY KEY (term, brand_name)
);
CREATE INDEX IF NOT EXISTS idx_brand_token_term ON brand_token(term);
"""

#: Shortest token worth indexing. Three letters match too much ("aaa", "inc"), five misses real
#: model numbers ("X120"), so four.
MIN_TOKEN = 4

#: Words that label a field in the register rather than name a product. They appear in brand strings
#: because registrants paste structured text into them - "Alphatec (Manufacturer:Tsunami)" - and
#: matching on them measured 349 papers for one device. Never identifying, at any frequency.
STRUCTURAL_WORDS = frozenset({
    "manufacturer", "manufacturers", "model", "models", "part", "parts", "number", "numbers",
    "ref", "reference", "reorder", "catalog", "catalogue", "item", "items", "product", "products",
    "device", "devices", "with", "without", "and", "the", "for", "from", "per", "pro",
    "set", "sets", "kit", "kits", "pack", "packs", "box", "boxes", "case", "cases",
    "size", "sizes", "length", "width", "diameter", "series", "line", "type", "types",
    "plus", "basic", "standard", "premium", "universal", "complete", "sterile", "single", "double",
    "left", "right", "small", "medium", "large", "extra", "mini", "micro", "nano",
    "made", "inc", "llc", "ltd", "gmbh", "corp", "corporation", "company", "co",
    "mm", "cm", "inch", "inches", "pcs", "pc", "unit", "units", "package",
})

#: English function words and research-report filler that survive the register vocabulary check.
#
# The index keeps only tokens that appear somewhere in the 318k-term register vocabulary, which is the
# right filter for "is this a device name". It is not a stopword list: brand names contain "with",
# "that", "this" and "figure", so a paper's term table filled with them. Measured on PMC13739605, the
# first eight rows were lung/pressure/with/cmh2o/surgery/volume/that/driving - half noise, and the words
# that mean something were pushed down.
FUNCTION_WORDS = STRUCTURAL_WORDS | {
    "that", "this", "these", "those", "which", "than", "then", "there", "their", "they",
    "have", "has", "had", "was", "were", "are", "been", "being", "does", "did", "doing",
    "into", "between", "during", "after", "before", "within", "without", "among", "under",
    "also", "such", "more", "most", "less", "least", "very", "much", "many", "some", "any",
    "can", "could", "may", "might", "must", "shall", "should", "will", "would",
    "not", "but", "however", "therefore", "thus", "hence", "while", "whereas", "because",
    "using", "used", "use", "uses", "based", "according", "respectively", "including",
    "show", "shows", "shown", "showing", "found", "observed", "reported", "suggest",
    "study", "studies", "result", "results", "group", "groups", "patient", "patients",
    "table", "tables", "figure", "figures", "data", "method", "methods", "conclusion",
    "introduction", "background", "objective", "objectives", "purpose", "aim", "aims",
    "total", "mean", "median", "value", "values", "level", "levels", "type", "types",
}

#: Counters that stay valid until the index is rebuilt, keyed by (database path, mtime).
#:
#: Not keyed by id(reference): CPython reuses ids after garbage collection, which made a fresh store
#: inherit a closed one's counts. Not attached to the store object either: the web app builds a new
#: store per request, so an object-attached cache is recomputed on every page - measured as a 19 s
#: first device page whose paper section alone cost 4 s. A path plus its mtime is stable across
#: requests and changes the moment index_corpus writes.
_COUNTERS: dict[tuple[str, float], dict[str, Any]] = {}


def _store_key(reference) -> tuple[str, float] | None:
    try:
        path = getattr(getattr(reference, "path", None), "__str__", lambda: "")()
        if not path:
            return None
        return (str(path), float(os.stat(path).st_mtime))
    except (OSError, AttributeError, TypeError):
        return None
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


def brand_token_frequencies(reference, *, limit: int = 200_000,
                            with_pairs: bool = False):
    """Register-side document frequency: how many distinct brand names contain each word."""
    counts: dict[str, int] = {}
    pairs: list[tuple[str, str]] = []
    try:
        rows = reference.conn.execute(
            "SELECT DISTINCT brand_name FROM udi_device "
            "WHERE brand_name IS NOT NULL AND brand_name <> '' LIMIT ?", (limit,)).fetchall()
    except Exception:  # noqa: BLE001 - a store without the device table simply has no signal
        return (counts, pairs) if with_pairs else counts
    for row in rows:
        brand = str(row[0] or "")
        for token in set(tokens(brand)):
            counts[token] = counts.get(token, 0) + 1
            if with_pairs:
                pairs.append((token, brand))
    return (counts, pairs) if with_pairs else counts


def rebuild_brand_token_df(reference, *, limit: int = 200_000) -> int:
    """Persist the register-side frequency and the term -> brand reverse map.

    Both come from the same pass over distinct brand names, so building them together costs one scan.
    """
    ensure_tables(reference)
    counts, pairs = brand_token_frequencies(reference, limit=limit, with_pairs=True)
    reference.conn.execute("DELETE FROM brand_token_df")
    reference.conn.executemany("INSERT OR REPLACE INTO brand_token_df (term, brands) VALUES (?,?)",
                               list(counts.items()))
    reference.conn.execute("DELETE FROM brand_token")
    reference.conn.executemany(
        "INSERT OR REPLACE INTO brand_token (term, brand_name) VALUES (?,?)", pairs)
    reference.conn.commit()
    return len(counts)


def brands_for_terms(reference, terms: Sequence[str], *, limit: int = 30,
                     max_shared_brand_df: int = 5) -> list[dict[str, Any]]:
    """Brand names sharing a *very* specific term with these terms, with the terms they share.

    Sharing any word is not a lead. Measured on a paper about machined implant abutments: the loose
    version returned thirty brands of "bite registration" material and "standardized probe", because
    those words pass a 50-brand threshold - while the one genuinely relevant hit, "Angled MU abutment
    - Machining", shared the word "machining", which appears in exactly one brand name in the entire
    register.

    So a brand qualifies only when it shares a term carried by ``max_shared_brand_df`` brands or
    fewer. The caller is told which term qualified, because that term is the whole reason to look.
    """
    usable = [t for t in dict.fromkeys(terms) if t]
    if not usable:
        return []
    rare = []
    for term in usable:
        # A four-digit number is a year in this corpus, not a model: "2018" pulled three PROPHYflex
        # sets into a paper about abutment machining.
        if len(term) == 4 and term.isdigit():
            continue
        brands = _brand_df(reference, term)
        if brands is not None and brands <= max_shared_brand_df:
            rare.append(term)
        elif any(ch.isdigit() for ch in term):
            rare.append(term)
    if not rare:
        return []
    placeholders = ",".join("?" for _ in rare)
    try:
        rows = reference.conn.execute(
            f"SELECT brand_name, GROUP_CONCAT(term) AS shared, COUNT(*) AS n "
            f"FROM brand_token WHERE term IN ({placeholders}) "
            f"GROUP BY brand_name ORDER BY n DESC, brand_name LIMIT ?",
            (*rare, limit)).fetchall()
    except Exception:  # noqa: BLE001 - an unbuilt reverse map is an absent answer, not a crash
        return []
    out = []
    for row in rows:
        shared = sorted(set(str(row[1] or "").split(",")) - {""})
        out.append({"brand_name": str(row[0]), "shared_terms": shared, "shared": int(row[2] or 0)})
    return out


def paper_terms(reference, paper_id: str, *, limit: int = 40,
                skip_function_words: bool = True) -> list[dict[str, Any]]:
    """The terms a paper was indexed under, most frequent first.

    Function words are dropped by default. They reach the table because the register vocabulary happens
    to contain them inside brand names ("with", "that", "figure"), so the filter that decides "is this
    a device name" also lets them through. Measured on PMC13739605: of the first eight rows, four were
    function words, and the terms that carry meaning were pushed off the top of the page.
    """
    try:
        # Ask for more than `limit` so the filter does not shorten the visible list.
        rows = reference.conn.execute(
            "SELECT term, hits FROM paper_term WHERE paper_id = ? ORDER BY hits DESC LIMIT ?",
            (paper_id, limit * 4 if skip_function_words else limit)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    kept: list[dict[str, Any]] = []
    for row in rows:
        term = str(row[0])
        if skip_function_words and term in FUNCTION_WORDS:
            continue
        kept.append({"term": term, "hits": int(row[1] or 0)})
        if len(kept) >= limit:
            break
    return kept


def paper_record(reference, paper_id: str) -> dict[str, Any] | None:
    try:
        row = reference.conn.execute(
            "SELECT title, year FROM paper_term WHERE paper_id = ? LIMIT 1", (paper_id,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    return {"paper_id": paper_id, "title": str(row[0] or ""), "year": str(row[1] or "")}


def _brand_df(reference, term: str) -> int | None:
    """Brands containing this term, or ``None`` when the table has never been built."""
    cached = _cache_for(reference)["df"]
    key = f"brand:{term}"
    if key in cached:
        value = cached[key]
        return None if value is None else int(value)
    try:
        row = reference.conn.execute(
            "SELECT brands FROM brand_token_df WHERE term = ?", (term,)).fetchone()
        value = int(row[0]) if row else None
    except Exception:  # noqa: BLE001
        value = None
    cached[key] = value
    return value


def brand_df_available(reference) -> bool:
    try:
        ensure_tables(reference)
        return bool(reference.conn.execute("SELECT COUNT(*) FROM brand_token_df").fetchone()[0])
    except Exception:  # noqa: BLE001
        return False


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
        try:
            reference.conn.execute(
                "INSERT OR REPLACE INTO paper_meta (paper_id, title, journal, published_at)"
                " VALUES (?,?,?,?)",
                (paper_id, title,
                 str(payload.get("journal") or "")[:200],
                 str(payload.get("published_at") or year or "")[:10]))
        except Exception:  # noqa: BLE001 - metadata must never stop the index
            pass
        reference.conn.executemany(
            "INSERT OR REPLACE INTO paper_term (term, paper_id, title, year, hits) "
            "VALUES (?,?,?,?,?)",
            [(term, paper_id, title, year, n) for term, n in counts.items()])
        rows += len(counts)
    reference.conn.commit()
    invalidate_cache(reference)  # the counts just changed; anything cached describes the old index
    brand_df_rows = rebuild_brand_token_df(reference)
    invalidate_cache(reference)  # the brand frequencies are cached too
    return {"papers_indexed": papers, "term_rows": rows, "vocabulary": len(vocab),
            "files_seen": len(files), "brand_terms": brand_df_rows}


def _cache_for(reference) -> dict[str, Any]:
    """Per-database counters that cannot change until the index is rebuilt.

    Measured: `SELECT COUNT(DISTINCT paper_id) FROM paper_term` is a full scan of 785,612 rows. It
    was called once per device, so a company query resolving 25 devices spent 13 s of a 15 s page
    repeating the same count. The index only changes when index_corpus() runs, which rewrites the
    file and therefore changes the mtime this cache is keyed on.
    """
    key = _store_key(reference)
    if key is None:
        return {"total": None, "df": {}}
    cached = _COUNTERS.get(key)
    if cached is None:
        cached = {"total": None, "df": {}}
        _COUNTERS[key] = cached
        # A rebuilt index leaves older entries behind; keep the map from growing without bound.
        if len(_COUNTERS) > 8:
            for stale in list(_COUNTERS)[:-8]:
                _COUNTERS.pop(stale, None)
    return cached


def invalidate_cache(reference=None) -> None:
    """Forget cached document frequencies. Call after rebuilding the index."""
    if reference is None:
        _COUNTERS.clear()
        return
    key = _store_key(reference)
    if key is not None:
        _COUNTERS.pop(key, None)
    else:
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
    # The nightly job already materialises this exact count, from this exact SQL. Measured: the scan
    # is 367 ms of a 1.55 s company page, for a number that changes once a night. The stored value is
    # used when present and the scan stays as the answer for a store that has never been refreshed.
    try:
        from .store_stats import peek as peek_stats

        stored = peek_stats(reference)
        if stored.get("available") and "papers" in (stored.get("counts") or {}):
            cached["total"] = int(stored["counts"]["papers"])
            return int(cached["total"])
    except Exception:  # noqa: BLE001 - a store without the materialised table scans instead
        pass
    row = reference.conn.execute(
        "SELECT COUNT(DISTINCT paper_id) FROM paper_term").fetchone()
    value = int(row[0]) if row and row[0] is not None else 0
    cached["total"] = value
    return value


def distinctive_terms(reference, terms: Sequence[str], *, max_df_ratio: float = 0.02,
                      max_brand_df: int = 50) -> tuple[list[str], list[str]]:
    """Split terms into those that can identify a device and those that cannot.

    Two independent filters, because each catches what the other misses.

    1. Corpus frequency (measured failure: a spinal implant returned 1,759 of 2,552 papers, because
       "spinal" and "system" are ordinary clinical vocabulary).
    2. Register frequency (measured failure: "1.5MM SYSTEM TWIST DRILL" matched fifteen papers
       through "twist" and "drill", which are rare in a small corpus and still name thousands of
       different products). A word carried by more than ``max_brand_df`` distinct brand names in the
       register cannot identify one product, however rare it is in the papers.

    A term carrying a digit is a model or catalog number and is always kept: "nb13810sp" occurs in
    no brand name at all and is exactly the kind of string that identifies a device when it appears.
    """
    total = _total_papers(reference)
    if not total:
        return [], list(terms)
    ceiling = max(3, int(total * max_df_ratio))
    kept: list[str] = []
    generic: list[str] = []
    for term in terms:
        # Order matters. A structural word is rejected first: "manufacturer" is twelve characters,
        # so the length shortcut below would keep it and it measured 349 papers for one device.
        if term in STRUCTURAL_WORDS:
            generic.append(term)
            continue
        if any(ch.isdigit() for ch in term) or len(term) >= 12:
            kept.append(term)
            continue
        brands = _brand_df(reference, term)
        if brands is not None and brands > max_brand_df:
            generic.append(term)
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
