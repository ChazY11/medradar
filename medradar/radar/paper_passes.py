"""Rotate the paper crawl across the specialties the register actually contains.

Measured: the nightly job ran one fixed query, `orthopedic implant AND open access`, and on
2026-11-27 it drew 120 candidates of which 112 were already cached. The lane was saturated and it
only ever covered one field, while the register holds devices in twenty-one.

This module decides what tonight's queries are, and remembers what each pass produced, so coverage
can be reported per field instead of as one number that means "some papers about orthopaedics".
"""

from __future__ import annotations

from typing import Any, Sequence

#: One query per specialty the classification table uses. Deliberately narrow: a broad query returns
#: the same famous papers for every field and adds nothing after the first night.
QUERIES: tuple[tuple[str, str], ...] = (
    ("Orthopedic", 'orthopedic implant AND ("open access"[filter])'),
    ("Dental", 'dental implant OR endosseous implant'),
    ("Cardiovascular", 'cardiac implant OR vascular stent'),
    ("Ophthalmic", 'intraocular lens OR retinal implant'),
    ("General, Plastic Surgery", 'surgical mesh OR wound closure device'),
    ("Gastroenterology, Urology", 'endoscopic device OR urology implant'),
    ("Anesthesiology", 'airway device OR anesthesia delivery system'),
    ("Ear, Nose, Throat", 'cochlear implant OR hearing device'),
    ("Radiology", 'imaging device OR radiology system evaluation'),
    ("Neurology", 'deep brain stimulation OR neurostimulation'),
    ("General Hospital", 'infusion pump OR patient monitoring device'),
    ("Immunology", 'immunoassay OR in vitro diagnostic device'),
)

PASS_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_pass (
    specialty   TEXT PRIMARY KEY,
    query_text  TEXT NOT NULL,
    ran_at      TEXT NOT NULL,
    candidates  INTEGER NOT NULL DEFAULT 0,
    stored      INTEGER NOT NULL DEFAULT 0,
    skipped     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_field (
    paper_id   TEXT NOT NULL,
    specialty  TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (paper_id, specialty)
);
"""


def ensure_table(reference) -> None:
    reference.conn.executescript(PASS_SCHEMA)


def record_field(reference, specialty: str, paper_ids: Sequence[str],
                 *, at: str | None = None) -> int:
    """Tie the papers a field's query actually brought in to that field.

    Without this, /area can say how many papers a field's crawl produced but not what they are
    about - the number would be a claim with no substance behind it.
    """
    from .records import utc_now_iso

    ensure_table(reference)
    stamp = at or utc_now_iso()
    written = 0
    for paper_id in paper_ids:
        text = str(paper_id).strip()
        if not text:
            continue
        reference.conn.execute(
            "INSERT OR REPLACE INTO paper_field (paper_id, specialty, added_at) VALUES (?,?,?)",
            (text, specialty, stamp))
        written += 1
    reference.conn.commit()
    return written


def papers_for(reference, specialty: str, *, limit: int = 5000) -> list[str]:
    try:
        ensure_table(reference)
        rows = reference.conn.execute(
            "SELECT paper_id FROM paper_field WHERE specialty = ? LIMIT ?",
            (specialty, int(limit))).fetchall()
    except Exception:  # noqa: BLE001 - no table yet
        return []
    return [str(row[0]) for row in rows]


def record_pass(reference, specialty: str, query: str, stats: dict[str, Any],
                *, at: str | None = None) -> None:
    from .records import utc_now_iso

    ensure_table(reference)
    reference.conn.execute(
        "INSERT OR REPLACE INTO paper_pass (specialty, query_text, ran_at, candidates, stored,"
        " skipped) VALUES (?,?,?,?,?,?)",
        (specialty, query, at or utc_now_iso(), int(stats.get("candidates") or 0),
         int(stats.get("stored") or 0), int(stats.get("skipped_cached") or 0)))
    reference.conn.commit()


def read_passes(reference) -> list[dict[str, Any]]:
    try:
        ensure_table(reference)
        rows = reference.conn.execute(
            "SELECT specialty, query_text, ran_at, candidates, stored, skipped"
            " FROM paper_pass ORDER BY ran_at DESC").fetchall()
    except Exception:  # noqa: BLE001 - no table yet
        return []
    return [{"specialty": r[0], "query": r[1], "ran_at": r[2], "candidates": int(r[3] or 0),
             "stored": int(r[4] or 0), "skipped": int(r[5] or 0)} for r in rows]


def next_queries(reference, *, count: int = 2) -> list[tuple[str, str]]:
    """The specialties due a pass: never-run first, then the ones whose last pass yielded least.

    Yield is the honest signal for "is this field exhausted" - a specialty that returns 120
    candidates with 112 cached is done, and one that has never run is not.
    """
    done = {row["specialty"]: row for row in read_passes(reference)}
    never = [(name, query) for name, query in QUERIES if name not in done]
    if never:
        return never[:count]
    # Everything has run at least once: prefer the lowest yield per candidate last time.
    ranked = sorted(
        QUERIES,
        key=lambda item: (
            (done[item[0]]["stored"] / done[item[0]]["candidates"])
            if done[item[0]]["candidates"] else 1.0,
            done[item[0]]["ran_at"],
        ))
    return ranked[:count]


def by_specialty(reference) -> dict[str, dict[str, Any]]:
    """Field name -> what its literature lane holds now, plus what its last pass did.

    Two numbers, because one overwrote the other: `stored` is the last run's yield, and a re-run that
    found everything already cached wrote 0 over the 66 the field had actually produced. The page now
    reports the linked total from paper_field, and keeps the pass record as "what the last run did".
    """
    passes = {row["specialty"]: row for row in read_passes(reference)}
    linked: dict[str, int] = {}
    archived: dict[str, int] = {}
    try:
        ensure_table(reference)
        for specialty, count in reference.conn.execute(
                "SELECT specialty, COUNT(*) FROM paper_field GROUP BY specialty"):
            linked[str(specialty)] = int(count or 0)
        # A query matches more papers than we end up holding: measured on the live store, Dental
        # matched 120 and archived 117, Cardiovascular 117 and 115. The page says "篇已归档", so the
        # number next to that word must be the archived count, not the match count.
        for specialty, count in reference.conn.execute(
                "SELECT f.specialty, COUNT(*) FROM paper_field f"
                " JOIN paper_meta m ON m.paper_id = f.paper_id GROUP BY f.specialty"):
            archived[str(specialty)] = int(count or 0)
    except Exception:  # noqa: BLE001 - no table yet
        linked, archived = {}, {}
    for specialty, row in passes.items():
        # `papers` is the stable answer to "how many of this field's papers do we actually hold";
        # `matched` is what its query returned; `stored` stays the last pass's yield.
        row["papers"] = archived.get(specialty, 0)
        row["matched"] = linked.get(specialty, 0)
    return passes


def field_topics(reference, specialty: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """What the papers fetched for a field talk about, by term frequency inside that field.

    Restricted to the papers this field's own query brought in, so the answer is about the field and
    not about the corpus. Words that appear in most fields are filtered out: "implant" says nothing
    when every field's papers say it.
    """
    from .papers_index import STRUCTURAL_WORDS, tokens

    ids = papers_for(reference, specialty)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids[:900])
    try:
        rows = reference.conn.execute(
            f"SELECT term, SUM(hits) AS n FROM paper_term WHERE paper_id IN ({placeholders})"
            f" GROUP BY term ORDER BY n DESC LIMIT 400", tuple(ids[:900])).fetchall()
    except Exception:  # noqa: BLE001 - no term table yet
        return []
    total = sum(int(row[1] or 0) for row in rows) or 1
    kept: list[dict[str, Any]] = []
    for term, count in rows:
        text = str(term or "")
        if len(text) < MIN_TOPIC_LENGTH or text in STRUCTURAL_WORDS:
            continue
        share = 100.0 * int(count or 0) / total
        if share < 0.4:
            continue
        kept.append({"term": text, "count": int(count or 0), "share": round(share, 1)})
        if len(kept) >= limit:
            break
    return kept


MIN_TOPIC_LENGTH = 5


def recent_for(reference, specialty: str, *, limit: int = 10,
               today: str | None = None) -> list[dict[str, Any]]:
    """The newest papers this field's lane holds, with the date each was published.

    Only papers actually linked to the field are eligible, so this answers "what has been published in
    this field among what we hold" - not "everything published in this field". The page says which.
    """
    # Forward-dated records are excluded. Measured in the live corpus: 14 of 3,366 carry a date after
    # today (three at 2027-01-01, eleven at 2026-12-01) because journals pre-fill an upcoming issue. A
    # list headed "recently published" that opens with next January is wrong in the one way this
    # product cannot afford.
    from .watermark import utc_today

    cutoff = str(today or utc_today())
    ids = papers_for(reference, specialty, limit=5000)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids[:900])
    try:
        rows = reference.conn.execute(
            f"SELECT paper_id, title, journal, published_at FROM paper_meta"
            f" WHERE paper_id IN ({placeholders}) AND COALESCE(published_at,'') <> ''"
            f"   AND published_at <= ?"
            f" ORDER BY published_at DESC LIMIT ?",
            tuple(ids[:900]) + (cutoff, int(limit))).fetchall()
    except Exception:  # noqa: BLE001 - no meta table yet
        return []
    return [{"paper_id": row[0], "title": row[1] or "", "journal": row[2] or "",
             "published_at": str(row[3] or "")[:10]} for row in rows]


def recent_any(reference, *, limit: int = 8, today: str | None = None) -> list[dict[str, Any]]:
    """The newest papers across every field we track, with the field attached.

    The landing page could describe the product but not show it moving. Forward-dated records are
    excluded for the same reason as recent_for: journals pre-fill an upcoming issue and a "latest"
    strip that opens with next January is wrong.
    """
    from .watermark import utc_today

    cutoff = str(today or utc_today())
    try:
        ensure_table(reference)
        rows = reference.conn.execute(
            "SELECT m.paper_id, m.title, m.journal, m.published_at, f.specialty"
            " FROM paper_meta m JOIN paper_field f ON f.paper_id = m.paper_id"
            " WHERE COALESCE(m.published_at,'') <> '' AND m.published_at <= ?"
            " GROUP BY m.paper_id"
            " ORDER BY m.published_at DESC LIMIT ?", (cutoff, int(limit))).fetchall()
    except Exception:  # noqa: BLE001 - no literature yet
        return []
    return [{"paper_id": row[0], "title": row[1] or "", "journal": row[2] or "",
             "published_at": str(row[3] or "")[:10], "specialty": row[4] or ""} for row in rows]


__all__ = ["QUERIES", "by_specialty", "recent_any", "ensure_table", "field_topics", "next_queries", "papers_for",
           "read_passes", "record_field", "record_pass", "recent_for"]
