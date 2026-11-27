"""Rotate the paper crawl across the specialties the register actually contains.

Measured: the nightly job ran one fixed query, `orthopedic implant AND open access`, and on
2026-11-27 it drew 120 candidates of which 112 were already cached. The lane was saturated and it
only ever covered one field, while the register holds devices in twenty-one.

This module decides what tonight's queries are, and remembers what each pass produced, so coverage
can be reported per field instead of as one number that means "some papers about orthopaedics".
"""

from __future__ import annotations

from typing import Any

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
"""


def ensure_table(reference) -> None:
    reference.conn.executescript(PASS_SCHEMA)


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
    """Field name -> what its literature pass last produced, for the pages to read.

    The number this returns is *how many papers that field's query brought in*, not how many papers
    exist about the field. The distinction has to survive into the page: a field that has never been
    crawled and a field with nothing to find are different states, and only one of them is our fault.
    """
    return {row["specialty"]: row for row in read_passes(reference)}


__all__ = ["QUERIES", "by_specialty", "ensure_table", "next_queries", "read_passes", "record_pass"]
