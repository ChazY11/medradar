"""Rotate the paper crawl across the specialties the register actually contains.

Measured: the nightly job ran one fixed query, `orthopedic implant AND open access`, and on
2026-11-27 it drew 120 candidates of which 112 were already cached. The lane was saturated and it
only ever covered one field, while the register holds devices in twenty-one.

This module decides what tonight's queries are, and remembers what each pass produced, so coverage
can be reported per field instead of as one number that means "some papers about orthopaedics".
"""

from __future__ import annotations

import os

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
    # Fields the register classifies devices into that the first twelve missed. They are not all
    # implant-shaped - clinical chemistry and microbiology are IVD - but an engineer looking up a
    # reagent device lands in one of them, and a field with no literature is a hole in the product.
    ("Microbiology", 'culture medium OR microbial identification device'),
    ("Clinical Chemistry", 'point-of-care assay OR clinical chemistry analyser'),
    ("Hematology", 'blood cell analyser OR coagulation test'),
    ("Pathology", 'histopathology OR tissue processing device'),
    ("Clinical Toxicology", 'drug screening assay OR toxicology analyser'),
    ("Obstetrics/Gynecology", 'obstetric device OR gynaecological surgical device'),
    ("Physical Medicine", 'rehabilitation device OR prosthetic limb'),
    ("Medical Genetics", 'genetic sequencing assay OR molecular diagnostic test'),
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
    """The specialties due a pass: never-run first, then the ones that ran longest ago.

    This used to prefer the field whose last pass *yielded least*, on the theory that a thin field
    deserves another chance. Measured on the live store, that is a trap: a field whose papers are all
    cached stores 0 every time, so it becomes the permanent lowest yield and gets picked forever.
    Backfilling the remaining fields ran Dental five times in a row and never reached the fields that
    had never run at all - the opposite of a rotation.

    Oldest-first is a round robin: every field is refreshed, none starves, and an exhausted field comes
    back only when its turn comes again.
    """
    done = {row["specialty"]: row for row in read_passes(reference)}
    never = [(name, query) for name, query in QUERIES if name not in done]
    if never:
        return never[:count]
    ranked = sorted(QUERIES, key=lambda item: str(done[item[0]]["ran_at"]))
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


_COVERAGE_CACHE: dict[tuple[str, float], dict[str, int]] = {}


def field_coverage(reference) -> dict[str, int]:
    """How much of the indexed corpus is split into fields at all.

    Measured 2026-11-28: 5,485 papers indexed, 2,336 linked to a field - 43%. The rest matched no field's
    query, so a field page speaks for the papers its own query brought in, not for the whole corpus. That
    proportion is the reason a field page can say "120 papers" without it meaning "the field has 120".
    """
    try:
        path = str(reference.path)
        key = (path, os.path.getmtime(path))
        hit = _COVERAGE_CACHE.get(key)
        if hit is not None:
            return hit
    except Exception:  # noqa: BLE001 - no cache key, still answer
        key = None
    out: dict[str, int] = {}
    try:
        indexed = reference.conn.execute("SELECT COUNT(*) FROM paper_meta").fetchone()[0]
        linked = reference.conn.execute(
            "SELECT COUNT(DISTINCT paper_id) FROM paper_field").fetchone()[0]
        out = {"indexed": int(indexed or 0), "field_linked": int(linked or 0)}
    except Exception:  # noqa: BLE001 - no index yet
        return {}
    if key is not None and out:
        _COVERAGE_CACHE.clear()
        _COVERAGE_CACHE[key] = out
    return out


_TOPICS_CACHE: dict[tuple[str, float, str], list[dict[str, Any]]] = {}


def emerging_terms(reference, specialty: str, *, recent_days: int = 90, baseline_days: int = 365,
                   limit: int = 8, today: str | None = None) -> dict[str, Any]:
    """Which words the field's newest papers use more than its older ones do.

    This is the question the product exists for - what is being worked on now - answered without a model:
    for each term, the share of recent papers that use it against the share of older papers that do, and
    the terms whose share rose most.

    What it is not: a claim about the whole field. It counts the papers we hold for this field (a bounded
    sample), it is a word frequency and not a judgement about importance, and a term "rising" here means
    rising inside our corpus. The page says all three.

    Forward-dated records are excluded, because journals pre-fill upcoming issues and a term that "rose"
    on a 2027 paper is not a signal about today.
    """
    from .watermark import utc_today

    ids = papers_for(reference, specialty, limit=5000)
    if not ids:
        return {"terms": [], "recent": 0, "baseline": 0, "recent_days": recent_days,
                "baseline_days": baseline_days}
    placeholders = ",".join("?" for _ in ids[:900])
    stamp = str(today or utc_today())
    try:
        rows = reference.conn.execute(
            f"SELECT p.paper_id, p.published_at FROM paper_meta p WHERE p.paper_id IN ({placeholders})"
            f" AND p.published_at IS NOT NULL AND p.published_at <> '' AND p.published_at <= ?",
            tuple(ids[:900]) + (stamp,)).fetchall()
    except Exception:  # noqa: BLE001 - no meta table
        return {"terms": [], "recent": 0, "baseline": 0, "recent_days": recent_days,
                "baseline_days": baseline_days}
    from datetime import date, timedelta

    try:
        end = date.fromisoformat(stamp[:10])
    except ValueError:
        end = date.today()
    recent_start = (end - timedelta(days=recent_days)).isoformat()
    baseline_start = (end - timedelta(days=baseline_days)).isoformat()

    recent_ids: set[str] = set()
    baseline_ids: set[str] = set()
    for paper_id, published in rows:
        day = str(published)[:10]
        if day >= recent_start:
            recent_ids.add(str(paper_id))
        elif day >= baseline_start:
            baseline_ids.add(str(paper_id))
    if not recent_ids or not baseline_ids:
        return {"terms": [], "new": [], "recent": len(recent_ids), "baseline": len(baseline_ids),
                "recent_days": recent_days, "baseline_days": baseline_days, "until": end.isoformat()}

    def counts(ids_subset: set[str]) -> dict[str, int]:
        wanted = sorted(ids_subset)[:900]
        if not wanted:
            return {}
        marks = ",".join("?" for _ in wanted)
        found = reference.conn.execute(
            f"SELECT term, COUNT(DISTINCT paper_id) FROM paper_term WHERE paper_id IN ({marks})"
            f" GROUP BY term", tuple(wanted)).fetchall()
        return {str(term): int(n) for term, n in found}

    recent_counts = counts(recent_ids)
    baseline_counts = counts(baseline_ids)
    # The same two filters the topic chips use, for the same reason. Without them the top of this list is
    # "multiple 32x", "factors 30.8x", "effect 29x" - generic English that says nothing about the field, and
    # a reader would rightly stop trusting the block. Measured 2026-11-28 on Dental: those five words were
    # the entire first screen.
    from .papers_index import FUNCTION_WORDS, METHOD_WORDS, is_generic, term_field_spread

    spread = term_field_spread(reference)
    terms: list[dict[str, Any]] = []
    for term, recent_n in recent_counts.items():
        if recent_n < 3:
            continue
        if term in FUNCTION_WORDS or term in METHOD_WORDS or is_generic(term, spread):
            continue
        # "1272" is not a word, and a 3-of-40 term is noise rather than a direction. Measured 2026-11-28:
        # Orthopedic (40 recent papers) produced "1272 4.95x", "spark 4.95x", "quanta 4.95x" - all artefacts
        # of a small window. Digits are dropped outright; the threshold rises with the window so that a
        # small sample must clear a higher bar.
        if any(ch.isdigit() for ch in term) or len(term) < 4:
            continue
        if recent_n < max(3, round(0.06 * len(recent_ids))):
            continue
        # Share of the window's papers that use the term: a field with three times as many recent papers
        # must not win on volume alone.
        recent_share = recent_n / max(1, len(recent_ids))
        base_n = baseline_counts.get(term, 0)
        base_share = base_n / max(1, len(baseline_ids))
        lift = recent_share / base_share if base_share > 0 else float(recent_n)
        terms.append({"term": term, "recent": recent_n, "recent_share": round(recent_share, 4),
                      "baseline": base_n, "baseline_share": round(base_share, 4),
                      "lift": round(lift, 2)})
    # Two different claims, kept apart. A word that already existed and is now used more is a trend; a word
    # that never appeared before is a candidate, and one paper is enough to produce it. Measured 2026-11-28:
    # mixing them put "jeol 7/40" and "klein 3/40" - an instrument brand and an author - beside real signals,
    # ranked above them because their baseline was zero and their lift therefore infinite.
    rising = [item for item in terms if item["baseline"] > 0]
    fresh = [item for item in terms if item["baseline"] == 0]
    rising.sort(key=lambda item: (item["lift"], item["recent"]), reverse=True)
    # New words rank by how many recent papers use them, not by lift: lift is unbounded when the baseline is
    # empty, so it cannot order them.
    fresh.sort(key=lambda item: item["recent"], reverse=True)
    fresh = [item for item in fresh
             if item["recent"] >= 3 and item["recent_share"] >= 0.08]
    # The window has an end date and the page prints it: "近 90 天" means nothing without knowing which day
    # the window closed on, and this corpus grows every night.
    return {"terms": rising[:limit], "new": fresh[:max(3, limit // 2)],
            "recent": len(recent_ids), "baseline": len(baseline_ids),
            "recent_days": recent_days, "baseline_days": baseline_days,
            "until": end.isoformat()}


_EMERGING_CACHE: dict[tuple[str, float, str], dict[str, Any]] = {}


_TREND_TABLE = """
CREATE TABLE IF NOT EXISTS field_trend (
    specialty   TEXT PRIMARY KEY,
    term        TEXT,
    recent      INTEGER,
    baseline    INTEGER,
    lift        REAL,
    computed_at TEXT
)
"""


def store_field_trends(reference, *, limit: int = 1, at: str | None = None) -> dict[str, Any]:
    """Materialise the top rising term per field.

    Computed here rather than on the page because it is expensive: measured 2026-11-28, twenty fields cost
    3.27 s cold and 0.84 s warm, on a page that answers in 0.67 s. The same reasoning as `store_stats` - a
    number a page needs on every visit is computed when nobody is waiting, and the page prints when.

    Only fields with a rising term are written. A field whose window is empty keeps its row cleared, so the
    page can say "no signal" rather than showing yesterday's word.
    """
    from .watermark import utc_today

    stamp = str(at or utc_today())
    reference.conn.executescript(_TREND_TABLE)
    try:
        fields = [str(row[0]) for row in reference.conn.execute(
            "SELECT DISTINCT specialty FROM paper_field ORDER BY specialty")]
    except Exception:  # noqa: BLE001 - no links, nothing to record
        fields = []
    written = 0
    for specialty in fields:
        result = emerging_terms(reference, specialty, limit=max(1, limit), today=stamp)
        term = ""
        recent = baseline = 0
        lift = 0.0
        if result["terms"]:
            best = result["terms"][0]
            term, recent, baseline, lift = (str(best["term"]), int(best["recent"]),
                                            int(best["baseline"]), float(best["lift"]))
        reference.conn.execute(
            "INSERT INTO field_trend (specialty, term, recent, baseline, lift, computed_at)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(specialty) DO UPDATE SET term=excluded.term, recent=excluded.recent,"
            " baseline=excluded.baseline, lift=excluded.lift, computed_at=excluded.computed_at",
            (specialty, term, recent, baseline, lift, stamp))
        written += 1
    reference.conn.commit()
    return {"fields": written, "with_term": sum(
        1 for row in reference.conn.execute("SELECT term FROM field_trend WHERE term <> ''")),
        "computed_at": stamp}


def field_trends(reference) -> dict[str, dict[str, Any]]:
    """The materialised trend table, or an empty dict when it has never been built."""
    try:
        rows = reference.conn.execute(
            "SELECT specialty, term, recent, baseline, lift, computed_at FROM field_trend").fetchall()
    except Exception:  # noqa: BLE001 - not built yet is a state, not a crash
        return {}
    return {str(row[0]): {"term": str(row[1] or ""), "recent": int(row[2] or 0),
                          "baseline": int(row[3] or 0), "lift": float(row[4] or 0),
                          "computed_at": str(row[5] or "")} for row in rows}


def emerging_terms_cached(reference, specialty: str, *, recent_days: int = 90,
                          baseline_days: int = 365, limit: int = 8,
                          today: str | None = None) -> dict[str, Any]:
    """emerging_terms with a per-store cache; the query joins two windows over up to 900 papers."""
    try:
        key = (str(reference.path), os.path.getmtime(str(reference.path)), specialty)
    except Exception:  # noqa: BLE001
        return emerging_terms(reference, specialty, recent_days=recent_days,
                              baseline_days=baseline_days, limit=limit, today=today)
    hit = _EMERGING_CACHE.get(key)
    if hit is not None:
        return hit
    value = emerging_terms(reference, specialty, recent_days=recent_days,
                           baseline_days=baseline_days, limit=limit, today=today)
    if len(_EMERGING_CACHE) > 128:
        _EMERGING_CACHE.clear()
    _EMERGING_CACHE[key] = value
    return value


def field_topics_cached(reference, specialty: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """field_topics with a per-store cache.

    The device page shows the vocabulary of up to two fields, and each call is a grouped query over 120
    papers (47 ms measured). Two fields on every dossier would cost 0.1 s on a page that answers in 0.45 s,
    so the result is cached against the register's path, mtime and the specialty.
    """
    try:
        path = str(reference.path)
        key = (path, os.path.getmtime(path), specialty)
    except Exception:  # noqa: BLE001 - no cache key, still answer
        return field_topics(reference, specialty, limit=limit)
    hit = _TOPICS_CACHE.get(key)
    if hit is not None:
        return hit
    value = field_topics(reference, specialty, limit=limit)
    if value:
        # Only successful answers are cached: an empty result may mean the literature lane has not run
        # yet, and caching that would keep the field blank after it does.
        _TOPICS_CACHE.clear()
        _TOPICS_CACHE[key] = value
    return value


def field_topics(reference, specialty: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """What the papers fetched for a field talk about, by term frequency inside that field.

    Restricted to the papers this field's own query brought in, so the answer is about the field and
    not about the corpus. Words that appear in most fields are filtered out: "implant" says nothing
    when every field's papers say it.
    """
    from .papers_index import FUNCTION_WORDS, is_generic, term_field_spread, tokens

    ids = papers_for(reference, specialty)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids[:900])
    try:
        # Distinct papers as well as hits. "in 42 of 120 papers" is a coverage statement a reader can
        # check; "1,032 hits" depends on how often a paper repeats a word, which nobody can interpret.
        rows = reference.conn.execute(
            f"SELECT term, SUM(hits) AS n, COUNT(DISTINCT paper_id) AS papers"
            f" FROM paper_term WHERE paper_id IN ({placeholders})"
            # Ordered by coverage, because the chip labels coverage. Sorting by hits while showing papers
            # made the row read as unsorted: mandibular 51/120 came before abutment 57/120.
            f" GROUP BY term ORDER BY papers DESC, n DESC LIMIT 800",
            tuple(ids[:900])).fetchall()
    except Exception:  # noqa: BLE001 - no term table yet
        return []
    # A word that appears in most fields is not evidence about this one. Measured on Dental: the static
    # list alone left clinical, implant, that, this, with, bone at the top; the spread filter leaves
    # edentulous, abutment, occlusal, mandibular, osteotomy.
    spread = term_field_spread(reference)
    candidates: list[tuple[str, int, int]] = []
    for term, count, papers in rows:
        text = str(term or "")
        # The same word list the paper page uses. It was STRUCTURAL_WORDS here and FUNCTION_WORDS
        # there, so a field's topic chips still led with "which 1,704" while the paper page had been
        # cleaned - one question, two standards.
        if len(text) < MIN_TOPIC_LENGTH or text in FUNCTION_WORDS or is_generic(text, spread):
            continue
        candidates.append((text, int(count or 0), int(papers or 0)))
    # The share is renormalised over what survived. It used to be taken against every term in the field,
    # which was fine while the list was dominated by clinical/implant/that; once those are filtered out the
    # remaining domain words look small and a 0.4% floor emptied the row entirely.
    total = sum(count for _, count, _ in candidates) or 1
    held = len(ids)
    kept: list[dict[str, Any]] = []
    for text, count, papers in candidates[:limit]:
        kept.append({"term": text, "count": count, "papers": papers, "held": held,
                     "share": round(100.0 * count / total, 1)})
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


def recency_by_specialty(reference, *, days: int = 90, today: str | None = None) -> dict[str, dict[str, int]]:
    """How much of each field's held literature is recent, by publication date.

    Every field is capped at the newest 120 papers we could fetch, so the ratio is not "the field's output"
    - it is how densely the field publishes, measured by how much of its 120-item allowance is filled with
    work from the last few months. Measured 2026-11-28: Medical Genetics 109/120 (91%), Pathology 68/120
    (57%), in 5 ms over 2,400 rows.
    """
    from datetime import date, timedelta

    from .watermark import utc_today

    end = str(today or utc_today())[:10]
    try:
        cutoff = (date.fromisoformat(end) - timedelta(days=int(days))).isoformat()
    except ValueError:
        return {}
    out: dict[str, dict[str, int]] = {}
    try:
        rows = reference.conn.execute(
            "SELECT f.specialty, COUNT(*) AS held,"
            " SUM(CASE WHEN COALESCE(m.published_at,'') >= ? THEN 1 ELSE 0 END) AS recent"
            " FROM paper_field f LEFT JOIN paper_meta m ON m.paper_id = f.paper_id"
            " GROUP BY f.specialty", (cutoff,)).fetchall()
    except Exception:  # noqa: BLE001 - no literature is an empty answer, not a failed page
        return {}
    for row in rows:
        held = int(row[1] or 0)
        recent = int(row[2] or 0)
        if held:
            out[str(row[0])] = {"held": held, "recent": recent,
                                "pct": int(round(100.0 * recent / held))}
    return out


def monthly_counts(reference, specialty: str, *, months: int = 12,
                   today: str | None = None) -> list[dict[str, Any]]:
    """Newest-first monthly counts of archived papers in a field, oldest month first in the return.

    Measured 2026-11-28 on the live store: Dental 25/16/15/18 by month, Cardiovascular 30/26/20, so the
    series is dense enough to read. It is also heavily recent - 4,676 of 5,485 papers are dated 2026 -
    because the crawl ran now, and the page says that rather than presenting the shape as the field's
    own publication trend.
    """
    from .watermark import utc_today

    cutoff = str(today or utc_today())[:7]
    try:
        rows = dict(reference.conn.execute(
            "SELECT substr(m.published_at,1,7) AS ym, COUNT(*) FROM paper_field f"
            " JOIN paper_meta m ON m.paper_id = f.paper_id"
            " WHERE f.specialty = ? AND COALESCE(m.published_at,'') <> '' AND m.published_at <= ?"
            "   AND m.published_at >= ?"
            " GROUP BY ym", (specialty, str(today or utc_today()),
                              f"{int(cutoff[:4]) - 1}-{cutoff[5:7]}-01")).fetchall())
    except Exception:  # noqa: BLE001 - no literature yet
        return []

    year, month = int(cutoff[:4]), int(cutoff[5:7])
    series: list[dict[str, Any]] = []
    for _ in range(int(months)):
        key = f"{year:04d}-{month:02d}"
        series.append({"ym": key, "n": int(rows.get(key, 0) or 0)})
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    series.reverse()
    return series


def dates_for(reference, paper_ids: Sequence[str]) -> dict[str, str]:
    """Publication date per paper id, for matches that came from the term index.

    Measured on /topic?id=central_station_telemetry: the table listed five papers with an empty date
    column, because the term index returns identifiers and titles and knows nothing about dates.
    """
    ids = [str(item) for item in paper_ids if str(item or "").strip()]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids[:900])
    try:
        rows = reference.conn.execute(
            f"SELECT paper_id, published_at FROM paper_meta WHERE paper_id IN ({placeholders})",
            tuple(ids[:900])).fetchall()
    except Exception:  # noqa: BLE001 - no meta table yet
        return {}
    return {str(row[0]): str(row[1] or "")[:10] for row in rows}


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


__all__ = ["QUERIES", "by_specialty", "dates_for", "field_coverage", "field_topics",
           "field_topics_cached",
           "monthly_counts", "recency_by_specialty",
           "recent_any", "ensure_table", "field_topics", "next_queries", "papers_for",
           "read_passes", "record_field", "record_pass", "recent_for"]
