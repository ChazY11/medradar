"""Device and company identity, from the regulator's own register.

The problem this solves
-----------------------
Entity resolution in this project matches **applicant name strings**, and it therefore only
resolves 35.2% of events to a company. String matching cannot be fixed by a better
threshold: "Medtronic Vascular", "Medtronic Inc", "Covidien LP" and "Tyco Healthcare" are the
same corporate family, "Abbott" and "Abbott Laboratories" split across filings, and a
spelling variant that appears once will never be guessed correctly.

UDI/GUDID hands us the answer. Every device record carries:

* ``labeler_duns_number`` - a stable legal-entity identifier issued by Dun & Bradstreet and
  maintained by the labeler, not derived by us;
* ``company_name`` - the labeler's own name for itself;
* ``premarket_submissions[]`` - the 510(k)/PMA numbers that cleared the device;
* ``catalog_number`` / ``version_or_model_number`` - what a MAUDE report cites when a device
  fails;
* ``product_codes[]`` with the official ``regulation_number`` and ``device_class``.

So ``MAUDE model number -> UDI device -> labeler DUNS -> 510(k)`` is an *exact* path. It
replaces guesswork with a join, which is the only kind of entity resolution that can be
audited.

Why this is not the ledger
--------------------------
5,182,695 UDI records are not 5,182,695 events. Putting them in the append-only ledger would
bury the feed, and a re-sync would look like a change. This module keeps them in a separate
**reference** database (:attr:`medradar.radar.paths.RadarPaths.reference`) that is a
dimension: rebuildable from the source, never cited as evidence of what MedRadar knew.

Budget honesty
--------------
A full openFDA UDI sweep is ~5,182 pages of 1,000. Without an API key openFDA allows 1,000
requests/day, so a full sweep needs either a key (120,000/day) or the GUDID bulk files
(``https://accessgudid.nlm.nih.gov/download``). :meth:`UdiReference.sync` reports the pages
it would need and never pretends a partial sweep is complete: coverage is a measured number,
not an assumption.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ENDPOINT = "https://api.fda.gov/device/udi.json"
#: See medradar.radar.http.OPENFDA_MAX_LIMIT_WITHOUT_KEY: 1000 is now key-gated.
PAGE_SIZE = 999
#: openFDA without a key allows 1,000 requests/day per IP; with a key, 120,000/day.
REQUESTS_PER_DAY_WITHOUT_KEY = 1_000
REQUESTS_PER_DAY_WITH_KEY = 120_000

SCHEMA_VERSION = 3

#: The column order every writer of ``udi_device`` must use. The openFDA sync and the GUDID
#: bulk importer are two different sources for one table; naming the order once is what stops
#: them drifting into a silent column swap that still parses.
DEVICE_COLUMNS: tuple[str, ...] = (
    "device_key", "di", "di_type", "brand_name", "device_description", "company_name",
    "labeler_duns", "catalog_number", "version_or_model", "product_codes",
    "regulation_numbers", "device_classes", "gmdn_code", "gmdn_name", "implantable",
    "is_single_use", "is_kit", "is_rx", "is_pm_exempt", "mri_safety", "publish_date",
    "public_version_date", "record_status", "raw", "first_observed_at",
)


def build_device_row(values: Mapping[str, Any]) -> tuple:
    """Project a mapping onto :data:`DEVICE_COLUMNS`, refusing anything unexpected.

    An unknown key is an error: a typo in a source parser would otherwise write into the wrong
    column and the device would simply stop joining.
    """
    unknown = set(values) - set(DEVICE_COLUMNS)
    if unknown:
        raise KeyError(f"unknown udi_device column(s): {sorted(unknown)}")
    return tuple(values.get(column) for column in DEVICE_COLUMNS)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS udi_device (
    device_key        TEXT PRIMARY KEY,   -- stable: the primary DI, else a hash of the record
    di                TEXT,
    di_type           TEXT,
    brand_name        TEXT,
    device_description TEXT,
    company_name      TEXT,
    labeler_duns      TEXT,
    catalog_number    TEXT,
    version_or_model  TEXT,
    product_codes     TEXT,               -- JSON array of codes
    regulation_numbers TEXT,              -- JSON array
    device_classes    TEXT,               -- JSON array
    gmdn_code         TEXT,
    gmdn_name         TEXT,
    implantable       INTEGER,
    is_single_use     INTEGER,
    is_kit            INTEGER,
    is_rx             INTEGER,
    is_pm_exempt      INTEGER,
    mri_safety        TEXT,
    publish_date      TEXT,
    public_version_date TEXT,
    record_status     TEXT,
    raw               TEXT,               -- the fields we kept, for re-derivation
    first_observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_udi_duns    ON udi_device(labeler_duns);
CREATE INDEX IF NOT EXISTS idx_udi_model   ON udi_device(version_or_model);
CREATE INDEX IF NOT EXISTS idx_udi_catalog ON udi_device(catalog_number);
CREATE INDEX IF NOT EXISTS idx_udi_company ON udi_device(company_name);

CREATE TABLE IF NOT EXISTS udi_premarket (
    submission_number TEXT NOT NULL,
    supplement_number TEXT,
    device_key        TEXT NOT NULL,
    labeler_duns      TEXT,
    PRIMARY KEY (submission_number, supplement_number, device_key)
);
CREATE INDEX IF NOT EXISTS idx_prem_device ON udi_premarket(device_key);
CREATE INDEX IF NOT EXISTS idx_prem_duns   ON udi_premarket(labeler_duns);

CREATE TABLE IF NOT EXISTS udi_company (
    labeler_duns TEXT PRIMARY KEY,
    company_name TEXT,
    device_count INTEGER,
    first_observed_at TEXT
);

CREATE TABLE IF NOT EXISTS reference_sync (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    endpoint      TEXT,
    last_run_at   TEXT,
    last_run_pages INTEGER,
    devices_seen  INTEGER,
    devices_written INTEGER,
    endpoint_version TEXT,
    complete      INTEGER,
    note          TEXT
);

-- Patent ownership resolution. The assignee string a patent states ("MEDTRONIC SOFAMOR
-- DANEK INC") is resolved to a labeler DUNS, because the DUNS is the only legal-entity key
-- that already spans this project's device register. Every resolution records how it was
-- reached, so a wrong one is reviewable rather than invisible.
CREATE TABLE IF NOT EXISTS assignee_alias (
    assignee_norm TEXT PRIMARY KEY,
    assignee_raw  TEXT,
    labeler_duns  TEXT,
    company_name  TEXT,
    method        TEXT NOT NULL,          -- exact | token_subset | manual
    confidence    REAL NOT NULL,
    first_observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alias_duns ON assignee_alias(labeler_duns);

-- Resumable-sweep state. A partial sweep must be able to say where it stopped, otherwise the
-- only honest options are "restart from zero" or "pretend it finished". Both are worse than a
-- cursor.
CREATE TABLE IF NOT EXISTS reference_kv (
    k          TEXT PRIMARY KEY,
    v          TEXT,
    updated_at TEXT NOT NULL
);
"""


@dataclass
class UdiSyncResult:
    """What one sync actually did. Every field is measured, none is inferred."""

    pages: int = 0
    rows_seen: int = 0
    devices_written: int = 0
    submissions_written: int = 0
    companies_written: int = 0
    skipped: int = 0
    endpoint_version: str | None = None
    complete: bool = False
    stop_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "rows_seen": self.rows_seen,
            "devices_written": self.devices_written,
            "submissions_written": self.submissions_written,
            "companies_written": self.companies_written,
            "skipped": self.skipped,
            "endpoint_version": self.endpoint_version,
            "complete": self.complete,
            "stop_reason": self.stop_reason,
            "notes": self.notes,
        }


class UdiReference:
    """The UDI/GUDID reference store. Rebuildable; never evidence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ storage
    def _schema_version_on_disk(self) -> int | None:
        """Read the on-disk schema version without taking a write lock.

        Needed because creating the schema is a write, and on a shared host the database may be
        held by another process for a long sweep. Measured: the pipeline re-opened this store on
        every restart, each open ran ``executescript`` plus ``PRAGMA user_version`` as a write
        transaction, and against a 1.6 GB store with a concurrent reader it failed with
        ``database is locked`` 62 times in a row.
        """
        if not self.path.exists():
            return None
        try:
            probe = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error:
            return None
        try:
            return int(probe.execute("PRAGMA user_version").fetchone()[0])
        except sqlite3.Error:
            return None
        finally:
            probe.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            current = self._schema_version_on_disk()
            # timeout=30 instead of the 5 s default: a 1.6 GB store under a concurrent writer can
            # take longer than five seconds to hand over the lock, and failing immediately turns a
            # slow moment into a crash loop.
            self._conn = sqlite3.connect(str(self.path), timeout=30.0)
            self._conn.row_factory = sqlite3.Row
            if current != SCHEMA_VERSION:
                self._conn.executescript(_SCHEMA)
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "UdiReference":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --------------------------------------------------------------------- sync
    def sync(
        self,
        fetcher,
        *,
        product_codes: Sequence[str] | None = None,
        page_size: int = PAGE_SIZE,
        max_pages: int | None = None,
        api_key: str | None = None,
        progress=None,
    ) -> UdiSyncResult:
        """Page openFDA UDI into the reference store.

        ``max_pages`` is not a hidden safety net, it is the budget: a caller that cannot
        spend 5,182 requests must say so, and ``result.complete`` will be False. A partial
        sweep is reported as partial, because a coverage number that cannot admit its own
        gaps is worse than no number.
        """
        from .records import utc_now_iso

        result = UdiSyncResult()
        search = None
        if product_codes:
            search = " OR ".join(f'product_codes.code:"{code}"' for code in product_codes)
        from .http import OPENFDA_MAX_LIMIT_WITHOUT_KEY, with_openfda_key

        page_size = min(int(page_size), OPENFDA_MAX_LIMIT_WITHOUT_KEY)
        skip = 0
        total = None
        while True:
            if max_pages is not None and result.pages >= max_pages:
                result.stop_reason = f"page budget {max_pages} reached"
                break
            params: dict[str, Any] = {"limit": page_size, "skip": skip}
            if search:
                params["search"] = search
            params = with_openfda_key(params)
            if api_key:
                params["api_key"] = api_key
            data = fetcher.get_json(ENDPOINT, params=params, allow_not_found=True)
            if data is None:
                result.stop_reason = "endpoint returned no payload"
                break
            meta = data.get("meta") or {}
            version = str(meta.get("last_updated") or "").strip() or None
            if version:
                result.endpoint_version = version
            if total is None:
                total = int(((meta.get("results") or {}).get("total") or 0))
            rows = [row for row in (data.get("results") or []) if isinstance(row, dict)]
            if not rows:
                result.complete = True
                break
            written, submissions, companies, skipped = self._write_rows(rows)
            result.rows_seen += len(rows)
            result.devices_written += written
            result.submissions_written += submissions
            result.companies_written += companies
            result.skipped += skipped
            result.pages += 1
            skip += len(rows)
            if progress:
                progress(result, total)
            if len(rows) < page_size or (total and skip >= total):
                result.complete = True
                break

        result.notes.append(
            f"endpoint version {result.endpoint_version or 'unknown'}; "
            f"{result.pages} pages for {result.rows_seen} of {total or 'unknown'} rows"
        )
        if not result.complete:
            needed = _pages_needed(total, page_size)
            budget = REQUESTS_PER_DAY_WITH_KEY if api_key else REQUESTS_PER_DAY_WITHOUT_KEY
            result.notes.append(
                f"a complete sweep needs about {needed} pages; this run had a budget of "
                f"{budget} requests/day ({'keyed' if api_key else 'unkeyed'}). "
                "Use an openFDA API key or the GUDID bulk download for the full register."
            )
        self._record_sync(result)
        return result

    def _write_rows(self, rows: Iterable[Mapping[str, Any]]) -> tuple[int, int, int, int]:
        parsed: list[dict[str, Any]] = []
        skipped = 0
        for row in rows:
            item = _parse_udi(row)
            if item is None:
                skipped += 1
                continue
            parsed.append(item)
        devices, submissions, companies = self.write_parsed(parsed)
        return devices, submissions, companies, skipped

    def write_parsed(self, parsed: Iterable[Mapping[str, Any]]) -> tuple[int, int, int]:
        """Write devices that are already normalised to the store's own shape.

        Both writers land here: the openFDA JSON sync (:func:`_parse_udi`) and the GUDID bulk
        importer (:mod:`medradar.radar.gudid`). One upsert path means the two routes cannot
        disagree about what a device row is, which is the only way a DUNS spine stays usable.
        """
        from .records import utc_now_iso

        now = utc_now_iso()
        devices = 0
        submissions = 0
        companies: dict[str, str] = {}
        cursor = self.conn.cursor()
        for item in parsed:
            cursor.execute(
                """
                INSERT INTO udi_device (
                    device_key, di, di_type, brand_name, device_description, company_name,
                    labeler_duns, catalog_number, version_or_model, product_codes,
                    regulation_numbers, device_classes, gmdn_code, gmdn_name, implantable,
                    is_single_use, is_kit, is_rx, is_pm_exempt, mri_safety, publish_date,
                    public_version_date, record_status, raw, first_observed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(device_key) DO UPDATE SET
                    company_name=excluded.company_name,
                    labeler_duns=excluded.labeler_duns,
                    catalog_number=excluded.catalog_number,
                    version_or_model=excluded.version_or_model,
                    product_codes=excluded.product_codes,
                    regulation_numbers=excluded.regulation_numbers,
                    device_classes=excluded.device_classes,
                    publish_date=excluded.publish_date,
                    record_status=excluded.record_status,
                    raw=excluded.raw
                """,
                item["row"],
            )
            devices += 1
            for submission in item.get("submissions") or ():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO udi_premarket
                        (submission_number, supplement_number, device_key, labeler_duns)
                    VALUES (?,?,?,?)
                    """,
                    (submission["number"], submission["supplement"],
                     item["device_key"], item.get("duns")),
                )
                submissions += 1
            duns = item.get("duns")
            if duns:
                companies[str(duns)] = str(item.get("company_name") or "")
        for duns, name in companies.items():
            cursor.execute(
                """
                INSERT INTO udi_company (labeler_duns, company_name, device_count,
                                         first_observed_at)
                VALUES (?, ?, 0, ?)
                ON CONFLICT(labeler_duns) DO UPDATE SET
                    company_name = COALESCE(NULLIF(excluded.company_name, ''),
                                            udi_company.company_name)
                """,
                (duns, name, now),
            )
        self.conn.commit()
        self._refresh_company_counts()
        return devices, submissions, len(companies)

    def _refresh_company_counts(self) -> None:
        self.conn.execute(
            """
            UPDATE udi_company SET device_count = (
                SELECT COUNT(*) FROM udi_device d WHERE d.labeler_duns = udi_company.labeler_duns
            )
            """
        )
        self.conn.commit()

    def _record_sync(self, result: UdiSyncResult) -> None:
        from .records import utc_now_iso

        self.conn.execute(
            """
            INSERT INTO reference_sync (id, endpoint, last_run_at, last_run_pages,
                devices_seen, devices_written, endpoint_version, complete, note)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_run_at=excluded.last_run_at,
                last_run_pages=excluded.last_run_pages,
                devices_seen=excluded.devices_seen,
                devices_written=excluded.devices_written,
                endpoint_version=excluded.endpoint_version,
                complete=excluded.complete,
                note=excluded.note
            """,
            (ENDPOINT, utc_now_iso(), result.pages, result.rows_seen,
             result.devices_written, result.endpoint_version, int(result.complete),
             " | ".join(result.notes)[:2000]),
        )
        self.conn.commit()

    # ------------------------------------------------------------------- lookup
    def company_by_duns(self, duns: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM udi_company WHERE labeler_duns = ?", (str(duns).strip(),)
        ).fetchone()
        return dict(row) if row else None

    def devices_for_duns(self, duns: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT device_key, brand_name, catalog_number, version_or_model, product_codes "
            "FROM udi_device WHERE labeler_duns = ? LIMIT ?",
            (str(duns).strip(), int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def devices_for_model(self, model: str, limit: int = 50) -> list[dict[str, Any]]:
        """Resolve a MAUDE ``model_number``/``catalog_number`` to UDI devices.

        This is the join that makes a failure report engineering-usable: the report names a
        model, and the register says which company and which clearance it belongs to.
        """
        value = str(model or "").strip()
        if not value:
            return []
        rows = self.conn.execute(
            "SELECT device_key, brand_name, company_name, labeler_duns, product_codes "
            "FROM udi_device WHERE version_or_model = ? OR catalog_number = ? LIMIT ?",
            (value, value, int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def submissions_for_device(self, device_key: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT submission_number, supplement_number FROM udi_premarket WHERE device_key = ?",
            (device_key,),
        ).fetchall()
        return [dict(row) for row in rows]

    def submissions_for_model(self, model: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT p.submission_number
            FROM udi_premarket p
            JOIN udi_device d ON d.device_key = p.device_key
            WHERE d.version_or_model = ? OR d.catalog_number = ?
            ORDER BY p.submission_number
            """,
            (str(model).strip(), str(model).strip()),
        ).fetchall()
        return [str(row["submission_number"]) for row in rows]

    def write_udi_rows(self, rows: Iterable[Mapping[str, Any]]
                       ) -> tuple[int, int, int, int]:
        """Write raw openFDA UDI records (``{"device": ..., "premarket": [...]}``)."""
        return self._write_rows(rows)

    def devices_for_submission(self, submission_number: str) -> list[dict[str, Any]]:
        """Every registered device that points at a 510(k)/PMA submission number.

        This is the bridge the whole exercise exists for: a clearance number on one side, a
        labeler DUNS and a model number on the other. A 510(k) document can therefore be joined
        to the devices it cleared without matching a single company name.
        """
        rows = self.conn.execute(
            """
            SELECT d.device_key, d.di, d.brand_name, d.company_name, d.labeler_duns,
                   d.version_or_model, d.catalog_number, d.product_codes, d.gmdn_name,
                   p.submission_number, p.supplement_number
            FROM udi_premarket p
            JOIN udi_device d ON d.device_key = p.device_key
            WHERE p.submission_number = ?
            ORDER BY d.company_name
            """,
            (str(submission_number).strip().upper(),),
        ).fetchall()
        return [dict(row) for row in rows]

    # ---------------------------------------------------------------------- state
    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT v FROM reference_kv WHERE k = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return row[0]

    def kv_set(self, key: str, value: Any) -> None:
        from .records import utc_now_iso

        self.conn.execute(
            """
            INSERT INTO reference_kv (k, v, updated_at) VALUES (?,?,?)
            ON CONFLICT(k) DO UPDATE SET v = excluded.v, updated_at = excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), utc_now_iso()),
        )
        self.conn.commit()

    # ----------------------------------------------------------------- coverage
    def company_names(self, *, limit: int | None = None) -> list[tuple[str, str]]:
        """Every ``(company_name, labeler_duns)`` pair, largest labeler first.

        This is the candidate set a patent assignee string is matched against, which is why it
        is ordered by device count: a name that labels 300,000 devices should be matched before
        one that labels three.
        """
        sql = ("SELECT company_name, labeler_duns FROM udi_company "
               "WHERE company_name IS NOT NULL AND company_name <> '' "
               "AND labeler_duns IS NOT NULL ORDER BY device_count DESC")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [(str(row[0]), str(row[1])) for row in self.conn.execute(sql)]

    def record_assignee_resolution(self, *, assignee_raw: str, assignee_norm: str,
                                   labeler_duns: str, company_name: str | None,
                                   method: str, confidence: float) -> None:
        from .records import utc_now_iso

        self.conn.execute(
            """
            INSERT INTO assignee_alias (assignee_norm, assignee_raw, labeler_duns,
                company_name, method, confidence, first_observed_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(assignee_norm) DO UPDATE SET
                labeler_duns = excluded.labeler_duns,
                company_name = excluded.company_name,
                method = excluded.method,
                confidence = excluded.confidence
            """,
            (assignee_norm, assignee_raw, labeler_duns, company_name, method,
             float(confidence), utc_now_iso()),
        )
        self.conn.commit()

    def resolve_assignee(self, assignee_norm: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM assignee_alias WHERE assignee_norm = ?", (assignee_norm,)
        ).fetchone()
        return dict(row) if row else None

    def assignee_coverage(self) -> dict[str, Any]:
        def scalar(sql: str) -> int:
            row = self.conn.execute(sql).fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        return {
            "resolved_assignees": scalar("SELECT COUNT(*) FROM assignee_alias"),
            "by_method": {
                str(row[0]): int(row[1])
                for row in self.conn.execute(
                    "SELECT method, COUNT(*) FROM assignee_alias GROUP BY method")
            },
            "distinct_duns": scalar(
                "SELECT COUNT(DISTINCT labeler_duns) FROM assignee_alias"),
        }

    def coverage(self) -> dict[str, Any]:
        """Measured coverage. Every number here is a COUNT, not an estimate."""
        def scalar(sql: str, *args: Any) -> int:
            row = self.conn.execute(sql, args).fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        sync_row = self.conn.execute("SELECT * FROM reference_sync WHERE id = 1").fetchone()
        return {
            "devices": scalar("SELECT COUNT(*) FROM udi_device"),
            "devices_with_duns": scalar(
                "SELECT COUNT(*) FROM udi_device WHERE labeler_duns IS NOT NULL "
                "AND labeler_duns <> ''"
            ),
            "devices_with_model": scalar(
                "SELECT COUNT(*) FROM udi_device WHERE version_or_model IS NOT NULL "
                "AND version_or_model <> ''"
            ),
            "companies": scalar("SELECT COUNT(*) FROM udi_company"),
            "premarket_links": scalar("SELECT COUNT(*) FROM udi_premarket"),
            "distinct_submissions": scalar(
                "SELECT COUNT(DISTINCT submission_number) FROM udi_premarket"
            ),
            "last_sync": dict(sync_row) if sync_row else None,
        }


# ------------------------------------------------------------------- parsing
def _parse_udi(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Flatten one openFDA UDI record. Returns None when it cannot carry identity."""
    from .records import utc_now_iso

    identifiers = raw.get("identifiers") or []
    primary = None
    for entry in identifiers:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("type") or "").strip().lower() == "primary":
            primary = entry
            break
    if primary is None and identifiers and isinstance(identifiers[0], Mapping):
        primary = identifiers[0]
    di = str((primary or {}).get("id") or "").strip()
    di_type = str((primary or {}).get("issuing_agency") or "").strip() or None

    company = " ".join(str(raw.get("company_name") or "").split())
    duns = str(raw.get("labeler_duns_number") or "").strip() or None
    catalog = str(raw.get("catalog_number") or "").strip() or None
    model = str(raw.get("version_or_model_number") or "").strip() or None
    brand = " ".join(str(raw.get("brand_name") or "").split())
    description = " ".join(str(raw.get("device_description") or "").split())

    if not di and not (catalog or model):
        return None
    device_key = f"di:{di}" if di else f"cm:{company}|{catalog or model}"

    codes: list[str] = []
    regulations: list[str] = []
    classes: list[str] = []
    for code in raw.get("product_codes") or []:
        if not isinstance(code, Mapping):
            continue
        value = str(code.get("code") or "").strip()
        if value:
            codes.append(value)
        openfda = code.get("openfda") or {}
        if isinstance(openfda, Mapping):
            regulation = str(openfda.get("regulation_number") or "").strip()
            if regulation:
                regulations.append(regulation)
            device_class = str(openfda.get("device_class") or "").strip()
            if device_class:
                classes.append(device_class)

    gmdn = {}
    for term in raw.get("gmdn_terms") or []:
        if isinstance(term, Mapping):
            gmdn = term
            break

    submissions = []
    for entry in raw.get("premarket_submissions") or []:
        if not isinstance(entry, Mapping):
            continue
        number = str(entry.get("submission_number") or "").strip()
        if number:
            submissions.append({
                "number": number,
                "supplement": str(entry.get("supplement_number") or "").strip() or None,
            })

    sterilisation = raw.get("sterilization") or {}
    kept = {
        "di": di, "di_type": di_type, "brand_name": brand,
        "device_description": description, "company_name": company,
        "labeler_duns": duns, "catalog_number": catalog, "version_or_model": model,
        "product_codes": codes, "regulation_numbers": regulations,
        "device_classes": classes, "gmdn_code": gmdn.get("code"),
        "gmdn_name": gmdn.get("name"), "implantable": gmdn.get("implantable"),
        "is_single_use": raw.get("is_single_use"), "is_kit": raw.get("is_kit"),
        "is_rx": raw.get("is_rx"), "is_pm_exempt": raw.get("is_pm_exempt"),
        "mri_safety": raw.get("mri_safety"),
        "publish_date": raw.get("publish_date"),
        "public_version_date": raw.get("public_version_date"),
        "record_status": raw.get("record_status"),
        "sterilization": sterilisation if isinstance(sterilisation, Mapping) else {},
        "premarket_submissions": submissions,
    }

    row = (
        device_key, di, di_type, brand or None, description or None, company or None,
        duns, catalog, model,
        json.dumps(codes, ensure_ascii=False),
        json.dumps(regulations, ensure_ascii=False),
        json.dumps(classes, ensure_ascii=False),
        _text(gmdn.get("code")), _text(gmdn.get("name")),
        _bool_int(gmdn.get("implantable")),
        _bool_int(raw.get("is_single_use")), _bool_int(raw.get("is_kit")),
        _bool_int(raw.get("is_rx")), _bool_int(raw.get("is_pm_exempt")),
        _text(raw.get("mri_safety")),
        _text(raw.get("publish_date")), _text(raw.get("public_version_date")),
        _text(raw.get("record_status")),
        json.dumps(kept, ensure_ascii=False, sort_keys=True), utc_now_iso(),
    )
    return {"device_key": device_key, "duns": duns, "company_name": company,
            "submissions": submissions, "row": row}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "y", "yes"):
        return 1
    if text in ("false", "0", "n", "no"):
        return 0
    return None


def _pages_needed(total: int | None, page_size: int) -> int:
    if not total:
        return 0
    return -(-int(total) // max(1, int(page_size)))


def open_reference(paths=None) -> UdiReference:
    """Open the reference store at the configured radar location."""
    from .paths import radar_paths

    resolved = paths or radar_paths()
    return UdiReference(resolved.reference)


__all__ = [
    "ENDPOINT",
    "REQUESTS_PER_DAY_WITHOUT_KEY",
    "REQUESTS_PER_DAY_WITH_KEY",
    "UdiReference",
    "UdiSyncResult",
    "open_reference",
]
