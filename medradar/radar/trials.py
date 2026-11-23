"""Clinical trials as the R&D signal, from a source that needs no credential.

Why this lane exists
--------------------
The patent lane is blocked on a USPTO key that its own UI will not issue, and every legacy USPTO
API now redirects to the portal that will not issue it. Chasing that further would have been
polite stubbornness. Meanwhile the question the platform actually has to answer - *what is this
company building next* - has a free, documented, keyless answer:

    GET https://clinicaltrials.gov/api/v2/studies?query.spons=Medtronic&countTotal=true

Measured: 200 from the production host, ``totalCount`` 1,677 for Medtronic, and each record
carries the sponsor, the device names being studied, the phase, the dates and the enrolment.

A patent is a claim made after the fact. A trial is work in progress. For an engineer deciding
what to benchmark against, the trial is the more useful document.

Joining
-------
The join key is the **query itself**. We ask ClinicalTrials.gov for one company by name and store
``query_key`` beside every row, so a trial is attached to a company because that company was
searched for - not because two strings looked similar afterwards. Sponsor strings in the registry
are subsidiaries ("Medtronic - MITG"), so fuzzy matching would have produced confident nonsense.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_PAGE_SIZE = 100
#: Five pages is 500 studies for one company. Medtronic's newest 500 trials describe its current
#: programme; the remaining 1,177 are history that a device view will never surface.
DEFAULT_MAX_PAGES = 5

TRIAL_TABLE = """
CREATE TABLE IF NOT EXISTS trial (
    query_key       TEXT NOT NULL,
    nct_id          TEXT NOT NULL,
    lead_sponsor    TEXT,
    title           TEXT,
    status          TEXT,
    phase           TEXT,
    study_type      TEXT,
    start_date      TEXT,
    completion_date TEXT,
    enrollment      INTEGER,
    interventions   TEXT,
    countries       TEXT,
    PRIMARY KEY (query_key, nct_id)
);
CREATE INDEX IF NOT EXISTS idx_trial_key ON trial(query_key);
CREATE INDEX IF NOT EXISTS idx_trial_start ON trial(start_date);
"""


@dataclass
class TrialStats:
    sponsors: int = 0
    requests: int = 0
    studies_seen: int = 0
    rows_written: int = 0
    total_reported: int = 0
    per_sponsor: dict[str, int] = field(default_factory=dict)
    reported_per_sponsor: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {"sponsors": self.sponsors, "requests": self.requests,
                "studies_seen": self.studies_seen, "rows_written": self.rows_written,
                "total_reported": self.total_reported, "per_sponsor": self.per_sponsor,
                "reported_per_sponsor": self.reported_per_sponsor,
                "errors": self.errors}


def _query_key(name: str) -> str:
    """Share the assignee resolver's notion of identity so the lanes agree on names."""
    from .patents import normalise_assignee

    return normalise_assignee(name)


def ensure_tables(reference) -> None:
    reference.conn.executescript(TRIAL_TABLE)
    reference.conn.commit()


def tables_present(reference) -> bool:
    """True only when the table exists **and holds rows**.

    An empty table left behind by a summary call must not read as "this sponsor runs no trials";
    it means the import never ran, which is a different and more useful statement.
    """
    try:
        row = reference.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trial'").fetchone()
        if row is None:
            return False
        return reference.conn.execute("SELECT 1 FROM trial LIMIT 1").fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _dig(record: dict[str, Any], *path: str) -> Any:
    current: Any = record
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _flatten(record: dict[str, Any], query_key: str) -> tuple[Any, ...] | None:
    protocol = record.get("protocolSection") or {}
    nct_id = _dig(protocol, "identificationModule", "nctId")
    if not nct_id:
        return None
    phases = _dig(protocol, "designModule", "phases") or []
    interventions = [
        str(item.get("name")).strip()
        for item in (_dig(protocol, "armsInterventionsModule", "interventions") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    countries = []
    for location in (_dig(protocol, "contactsLocationsModule", "locations") or []):
        if isinstance(location, dict) and location.get("country"):
            name = str(location["country"])
            if name not in countries:
                countries.append(name)
    enrolment = _dig(protocol, "designModule", "enrollmentInfo", "count")
    return (
        query_key,
        str(nct_id),
        _dig(protocol, "sponsorCollaboratorsModule", "leadSponsor", "name"),
        _dig(protocol, "identificationModule", "briefTitle"),
        _dig(protocol, "statusModule", "overallStatus"),
        ",".join(str(phase) for phase in phases) or None,
        _dig(protocol, "designModule", "studyType"),
        _dig(protocol, "statusModule", "startDateStruct", "date"),
        _dig(protocol, "statusModule", "completionDateStruct", "date"),
        int(enrolment) if isinstance(enrolment, (int, float)) else None,
        " | ".join(interventions[:8]) or None,
        ", ".join(countries[:8]) or None,
    )


def import_trials(reference, sponsors: Iterable[str], *, fetcher=None,
                  page_size: int = DEFAULT_PAGE_SIZE,
                  max_pages: int = DEFAULT_MAX_PAGES,
                  progress: Callable[[TrialStats], None] | None = None) -> TrialStats:
    """Fetch trials for each sponsor name and store them keyed by that query."""
    from .http import HostPolicy, PoliteFetcher

    ensure_tables(reference)
    client = fetcher or PoliteFetcher(
        user_agent="MedRadar/0.1 (+https://github.com/ChazY11/medradar; research)",
        policies={"clinicaltrials.gov": HostPolicy(requests_per_second=2.0)},
        max_requests=200_000,
    )
    stats = TrialStats()
    for sponsor in sponsors:
        name = str(sponsor or "").strip()
        if not name:
            continue
        key = _query_key(name)
        if not key:
            continue
        stats.sponsors += 1
        written_before = stats.rows_written
        token: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"query.spons": name, "pageSize": page_size}
            if token:
                params["pageToken"] = token
            else:
                params["countTotal"] = "true"
            try:
                data = client.get_json(ENDPOINT, params=params)
            except Exception as error:  # noqa: BLE001 - one bad sponsor must not stop the batch
                stats.errors[name] = f"{type(error).__name__}: {error}"
                break
            stats.requests += 1
            if not data:
                break
            if not token and data.get("totalCount"):
                # Counted once per sponsor, on its first page: the registry's own total, which is
                # larger than what we store when max_pages caps the walk.
                reported = int(data["totalCount"])
                stats.total_reported += reported
                stats.reported_per_sponsor[name] = reported
            studies = data.get("studies") or []
            if not studies:
                break
            stats.studies_seen += len(studies)
            rows = [row for row in (_flatten(study, key) for study in studies) if row]
            if rows:
                reference.conn.executemany(
                    "INSERT OR REPLACE INTO trial (query_key, nct_id, lead_sponsor, title, "
                    "status, phase, study_type, start_date, completion_date, enrollment, "
                    "interventions, countries) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                reference.conn.commit()
                stats.rows_written += len(rows)
            token = data.get("nextPageToken")
            if not token:
                break
        stats.per_sponsor[name] = stats.rows_written - written_before
        if progress:
            progress(stats)
    reference.conn.commit()
    return stats


# ------------------------------------------------------------------------ queries
def trials_for_sponsor(reference, name: str, *, limit: int = 5) -> dict[str, Any]:
    """Trials attached to this sponsor query, newest start date first."""
    ensure_tables(reference)
    key = _query_key(name)
    if not key:
        return {"sponsor": name, "trials": 0, "recent": [], "method": "none"}
    total = reference.conn.execute(
        "SELECT COUNT(*) FROM trial WHERE query_key = ?", (key,)).fetchone()[0]
    recent = [
        {"nct_id": row[0], "title": row[1], "status": row[2], "phase": row[3],
         "start_date": row[4], "enrollment": row[5], "interventions": row[6]}
        for row in reference.conn.execute(
            "SELECT nct_id, title, status, phase, start_date, enrollment, interventions "
            "FROM trial WHERE query_key = ? "
            "ORDER BY COALESCE(start_date, '') DESC LIMIT ?", (key, limit))
    ]
    return {"sponsor": name, "trials": int(total), "recent": recent,
            "method": "sponsor_query"}


def trials_summary(reference) -> dict[str, Any]:
    ensure_tables(reference)

    def scalar(sql: str) -> int:
        row = reference.conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def text_scalar(sql: str) -> str:
        row = reference.conn.execute(sql).fetchone()
        return str(row[0]) if row and row[0] is not None else ""

    return {
        "trials": scalar("SELECT COUNT(*) FROM trial"),
        "sponsors": scalar("SELECT COUNT(DISTINCT query_key) FROM trial"),
        "with_device_interventions": scalar(
            "SELECT COUNT(*) FROM trial WHERE interventions IS NOT NULL"),
        "date_range": [
            text_scalar("SELECT COALESCE(MIN(start_date), '') FROM trial"),
            text_scalar("SELECT COALESCE(MAX(start_date), '') FROM trial"),
        ],
    }


__all__ = [
    "DEFAULT_MAX_PAGES",
    "DEFAULT_PAGE_SIZE",
    "ENDPOINT",
    "TRIAL_TABLE",
    "TrialStats",
    "ensure_tables",
    "import_trials",
    "tables_present",
    "trials_for_sponsor",
    "trials_summary",
]
