"""Import the ODP bulk patent tables, which need no API key.

Why this exists beside the API client
-------------------------------------
``api.uspto.gov`` rejects every credential except an ``X-API-KEY``: measured, it answers
``401 {"message":"Unauthorized"}`` both to an anonymous request **and to the OAuth bearer token
that a signed-in ODP session holds** in ``okta-token-storage``. So the API lane is genuinely
key-gated, and the key is issued only after ID.me identity proofing.

The bulk lane is different. PatentsView's tables moved to ODP bulk files
(``/bulkdata/datasets/pvgpatdis``), and those are full historical dumps rather than paginated
queries:

* ``g_patent.tsv`` — one row per granted patent, with title and date;
* ``g_assignee_disambiguated.tsv`` — one row per patent/assignee pair, with the assignee
  organisation already disambiguated.

Joining the two answers "which patents belong to this company" for the whole corpus at once,
without a request limit, which is what the L4 layer actually wants.

Honesty rules
-------------
The upstream column set is not documented in one place and has changed between releases, so the
reader is **header-driven**: it resolves each column by name from a list of accepted aliases and
raises :class:`BulkSchemaError` naming the headers it actually saw when one is missing. Guessing
a column position would silently attach the wrong assignee to the wrong patent, which is worse
than failing.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

#: Accepted header names per logical field, in preference order. Upstream has used both
#: ``patent_id``/``id`` and ``disambig_assignee_organization``/``organization``.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "patent_id": ("patent_id", "id"),
    "title": ("patent_title", "title"),
    "date": ("patent_date", "date"),
    "patent_type": ("patent_type", "type"),
    "assignee_id": ("assignee_id",),
    "organization": ("disambig_assignee_organization", "organization",
                     "assignee_organization"),
    "assignee_type": ("assignee_type",),
}

REQUIRED: dict[str, tuple[str, ...]] = {
    "patents": ("patent_id",),
    "assignees": ("patent_id", "assignee_id"),
}

PATENTS_TABLE = """
CREATE TABLE IF NOT EXISTS bulk_patent (
    patent_id   TEXT PRIMARY KEY,
    title       TEXT,
    patent_date TEXT,
    patent_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_bulk_patent_date ON bulk_patent(patent_date);
"""

ASSIGNEES_TABLE = """
CREATE TABLE IF NOT EXISTS bulk_patent_assignee (
    patent_id        TEXT NOT NULL,
    assignee_id      TEXT NOT NULL,
    organization     TEXT,
    organization_norm TEXT,
    assignee_type    TEXT,
    PRIMARY KEY (patent_id, assignee_id)
);
CREATE INDEX IF NOT EXISTS idx_bulk_assignee_org ON bulk_patent_assignee(organization);
CREATE INDEX IF NOT EXISTS idx_bulk_assignee_norm ON bulk_patent_assignee(organization_norm);
CREATE INDEX IF NOT EXISTS idx_bulk_assignee_patent ON bulk_patent_assignee(patent_id);
"""

#: A slim store built before this column existed has the old shape; ALTER is cheaper than a
#: rebuild and keeps an already-imported archive usable.
ASSIGNEES_MIGRATIONS = (
    "ALTER TABLE bulk_patent_assignee ADD COLUMN organization_norm TEXT",
)


class BulkSchemaError(ValueError):
    """The archive did not carry a column we cannot do without."""

    def __init__(self, missing: Sequence[str], headers: Sequence[str], source: str) -> None:
        self.missing = list(missing)
        self.headers = list(headers)
        super().__init__(
            f"{source}: missing required column(s) {self.missing}; "
            f"the archive's headers are {self.headers[:25]}"
        )


@dataclass
class ImportStats:
    rows_read: int = 0
    rows_written: int = 0
    rows_skipped: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {"rows_read": self.rows_read, "rows_written": self.rows_written,
                "rows_skipped": self.rows_skipped,
                "skipped_reasons": self.skipped_reasons}


def _tsv_stream(path: Path) -> tuple[io.TextIOBase, str]:
    """Open a plain .tsv or the single .tsv inside a .zip, as UTF-8 text."""
    if path.suffix.lower() == ".zip":
        archive = zipfile.ZipFile(path)
        members = [name for name in archive.namelist() if name.lower().endswith(".tsv")]
        if not members:
            archive.close()
            raise BulkSchemaError([], archive.namelist(), str(path))
        member = sorted(members)[0]
        return io.TextIOWrapper(archive.open(member), encoding="utf-8", errors="replace"), member
    return path.open("r", encoding="utf-8", errors="replace", newline=""), str(path)


def _resolve_columns(headers: Sequence[str], wanted: Mapping[str, tuple[str, ...]],
                     required: Sequence[str], source: str) -> dict[str, str]:
    lowered = {header.strip().lower(): header for header in headers}
    mapping: dict[str, str] = {}
    for field_name, aliases in wanted.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field_name] = lowered[alias]
                break
    missing = [name for name in required if name not in mapping]
    if missing:
        raise BulkSchemaError(missing, headers, source)
    return mapping


def _iter_rows(path: Path) -> Iterator[tuple[dict[str, str], list[str], str]]:
    stream, member = _tsv_stream(path)
    try:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            headers = next(reader)
        except StopIteration:
            return
        yield {"__headers__": headers}, headers, member  # type: ignore[misc]
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            yield dict(zip(headers, row)), headers, member  # type: ignore[misc]
    finally:
        stream.close()


def ensure_tables(reference) -> None:
    """Create both tables and apply the additive migration, tolerating an already-migrated file."""
    reference.conn.executescript(PATENTS_TABLE)
    reference.conn.executescript(ASSIGNEES_TABLE)
    for statement in ASSIGNEES_MIGRATIONS:
        try:
            reference.conn.execute(statement)
        except Exception:  # noqa: BLE001 - duplicate column means it is already there
            pass
    reference.conn.commit()


def tables_present(reference) -> bool:
    """True only when the tables exist **and hold rows**.

    Measured failure this prevents: running ``--summary`` on a fresh store created the empty
    tables, and ``device_view`` then reported ``no_patent_for_this_assignee`` - "this company
    holds no patents" - when the truth was "the bulk files were never imported". Those are
    different facts and the second one is the honest one.
    """
    try:
        names = {row[0] for row in reference.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('bulk_patent','bulk_patent_assignee')").fetchall()}
        if len(names) != 2:
            return False
        return reference.conn.execute(
            "SELECT 1 FROM bulk_patent_assignee LIMIT 1").fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def import_tables(reference, patents_path: str | Path | None = None,
                  assignees_path: str | Path | None = None, *,
                  progress: Any = None) -> dict[str, Any]:
    """Load whichever of the two tables were supplied, into ``reference``."""
    ensure_tables(reference)
    result: dict[str, Any] = {}

    if patents_path is not None:
        path = Path(patents_path)
        mapping = None
        stats = ImportStats()
        batch: list[tuple[Any, ...]] = []
        for row, headers, member in _rows_with_header(path, "patents"):
            if mapping is None:
                mapping = _resolve_columns(headers, COLUMN_ALIASES, REQUIRED["patents"], member)
            stats.rows_read += 1
            patent_id = (row.get(mapping["patent_id"]) or "").strip()
            if not patent_id:
                stats.rows_skipped += 1
                stats.skipped_reasons["no_patent_id"] = (
                    stats.skipped_reasons.get("no_patent_id", 0) + 1)
                continue
            batch.append((
                patent_id,
                (row.get(mapping.get("title", ""), "") or "").strip() or None,
                (row.get(mapping.get("date", ""), "") or "").strip() or None,
                (row.get(mapping.get("patent_type", ""), "") or "").strip() or None,
            ))
            if len(batch) >= 5000:
                _flush_patents(reference, batch, stats)
                batch.clear()
        _flush_patents(reference, batch, stats)
        reference.conn.commit()
        result["patents"] = stats.summary()
        if progress:
            progress("patents", stats)

    if assignees_path is not None:
        path = Path(assignees_path)
        mapping = None
        stats = ImportStats()
        batch = []
        for row, headers, member in _rows_with_header(path, "assignees"):
            if mapping is None:
                mapping = _resolve_columns(headers, COLUMN_ALIASES,
                                           REQUIRED["assignees"], member)
            stats.rows_read += 1
            patent_id = (row.get(mapping["patent_id"]) or "").strip()
            assignee_id = (row.get(mapping["assignee_id"]) or "").strip()
            if not patent_id or not assignee_id:
                stats.rows_skipped += 1
                stats.skipped_reasons["no_ids"] = stats.skipped_reasons.get("no_ids", 0) + 1
                continue
            batch.append((
                patent_id, assignee_id,
                (row.get(mapping.get("organization", ""), "") or "").strip() or None,
                _norm(row.get(mapping.get("organization", ""), "")),
                (row.get(mapping.get("assignee_type", ""), "") or "").strip() or None,
            ))
            if len(batch) >= 5000:
                _flush_assignees(reference, batch, stats)
                batch.clear()
        _flush_assignees(reference, batch, stats)
        reference.conn.commit()
        result["assignees"] = stats.summary()
        if progress:
            progress("assignees", stats)

    return result


def _rows_with_header(path: Path, table: str):
    """Yield data rows, raising a named error when the required columns are absent."""
    stream, member = _tsv_stream(path)
    try:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            headers = next(reader)
        except StopIteration:
            return
        _resolve_columns(headers, COLUMN_ALIASES, REQUIRED[table], member)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            yield dict(zip(headers, row)), headers, member
    finally:
        stream.close()


def _flush_patents(reference, batch: Sequence[tuple[Any, ...]], stats: ImportStats) -> None:
    reference.conn.executemany(
        "INSERT OR REPLACE INTO bulk_patent (patent_id, title, patent_date, patent_type) "
        "VALUES (?,?,?,?)", batch)
    stats.rows_written += len(batch)


def _flush_assignees(reference, batch: Sequence[tuple[Any, ...]], stats: ImportStats) -> None:
    reference.conn.executemany(
        "INSERT OR REPLACE INTO bulk_patent_assignee "
        "(patent_id, assignee_id, organization, organization_norm, assignee_type) "
        "VALUES (?,?,?,?,?)", batch)
    stats.rows_written += len(batch)


def _norm(raw: Any) -> str | None:
    """Same normalisation the assignee resolver uses, so the two lanes agree on identity."""
    from .patents import normalise_assignee

    text = normalise_assignee(str(raw or ""))
    return text or None


# ------------------------------------------------------------------------ queries
def patents_for_assignee(reference, name: str, *, limit: int = 10) -> dict[str, Any]:
    """Patents held by one organisation, matched on the normalised disambiguated name."""
    ensure_tables(reference)
    key = _norm(name)
    if not key:
        return {"organization": name, "patents": 0, "recent": [], "method": "none"}
    total = reference.conn.execute(
        "SELECT COUNT(DISTINCT patent_id) FROM bulk_patent_assignee "
        "WHERE organization_norm = ?", (key,)).fetchone()[0]
    recent = [
        {"patent_id": row[0], "title": row[1], "patent_date": row[2]}
        for row in reference.conn.execute(
            "SELECT p.patent_id, p.title, p.patent_date "
            "FROM bulk_patent_assignee a JOIN bulk_patent p ON p.patent_id = a.patent_id "
            "WHERE a.organization_norm = ? "
            "ORDER BY p.patent_date DESC LIMIT ?", (key, limit))
    ]
    return {"organization": name, "patents": int(total), "recent": recent,
            "method": "disambiguated_assignee"}


def organisation_patents(reference, organization: str, *, limit: int = 10) -> dict[str, Any]:
    """Backwards-compatible alias kept for callers that used the substring form."""
    result = patents_for_assignee(reference, organization, limit=limit)
    if result["patents"]:
        return result
    ensure_tables(reference)
    like = f"%{organization.strip()}%"
    total = reference.conn.execute(
        "SELECT COUNT(DISTINCT patent_id) FROM bulk_patent_assignee "
        "WHERE organization LIKE ?", (like,)).fetchone()[0]
    return {"organization": organization, "patents": int(total), "recent": [],
            "method": "substring_fallback" if total else "none"}


def bulk_summary(reference) -> dict[str, Any]:
    ensure_tables(reference)

    def scalar(sql: str) -> int:
        row = reference.conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def text_scalar(sql: str) -> str:
        row = reference.conn.execute(sql).fetchone()
        return str(row[0]) if row and row[0] is not None else ""

    return {
        "patents": scalar("SELECT COUNT(*) FROM bulk_patent"),
        "assignee_rows": scalar("SELECT COUNT(*) FROM bulk_patent_assignee"),
        "organisations": scalar(
            "SELECT COUNT(DISTINCT organization) FROM bulk_patent_assignee "
            "WHERE organization IS NOT NULL"),
        "date_range": [
            text_scalar("SELECT COALESCE(MIN(patent_date), '') FROM bulk_patent"),
            text_scalar("SELECT COALESCE(MAX(patent_date), '') FROM bulk_patent"),
        ],
    }


__all__ = [
    "BulkSchemaError",
    "COLUMN_ALIASES",
    "ImportStats",
    "bulk_summary",
    "ensure_tables",
    "import_tables",
    "organisation_patents",
    "patents_for_assignee",
    "tables_present",
]
