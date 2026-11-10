"""CIPO (Canadian Intellectual Property Office) patent dataset connector.

Why this source
---------------
CIPO publishes its **entire** patent database as CSV under the
*Open Government Licence – Canada* — a real, explicit reuse licence, which is a
strictly better licence posture than the EPO publication server's terms. Coverage
is 1869 → 2022-02-28. Tables are joinable on ``Patent Number``:

* ``PT_Main``              bibliographic summary (titles EN/FR, filing, grant, status)
* ``PT_Interested_Party``  applicants / owners / inventors **with ``Owner Enable
                           Date`` and ``Ownership End date``** — an ownership
                           timeline, which is exactly what historical subsidiary
                           vs current parent attribution needs
* ``PT_IPC_Classification`` full IPC codes with subclass code
* ``PT_Priority_Claim``    priority claims with country and date
* ``PT_PCT``-ish columns live inside PT_Main (PCT application/publication number/date)

Temporal semantics — the important limitation
---------------------------------------------
``PT_Main`` has **Filing Date** and **Grant Date** but **no publication /
open-to-public-inspection date**. Canadian applications are laid open 18 months
after filing, but that rule is not a recorded field, so this connector does NOT
invent it:

* granted patent   -> ``source_public_at`` = Grant Date (recorded)
* pending application -> ``source_public_at`` = None, flagged
  ``MISSING_PUBLICATION_DATE``; the 18-month rule is recorded only as a note in
  ``attributes["public_availability_note"]``, never as a value.

The whole dataset is a **snapshot** whose last bibliographic extract is
2022-02-28, so every record is flagged ``SNAPSHOT_ONLY``: we cannot observe how
a record looked before that date.

Access
------
No key, no registration. The bulk files are advertised by an open-data catalogue
record (``open.canada.ca`` CKAN id ``fe1dfbb9-0fc3-42ca-b2a9-6ca4c05dbac9``) and
served from ``opic-cipo.ca``. That host omits its TLS intermediate certificate,
so this connector completes the chain from the leaf's AIA pointer
(``hz.tls.complete_chain``) and still verifies against the platform trust store.
Verification is never disabled.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from typing import Iterable, Iterator

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.schema import Identifier, build_record  # noqa: E402
from hz.timeq import classify_record, now_utc  # noqa: E402

SOURCE_ID = "cipo_canada"
KIND = "patent_publication"
LICENCE_STATUS = "open_licence"
LICENCE_NAME = "Open Government Licence - Canada"
LICENCE_URL = "https://open.canada.ca/en/open-government-licence-canada"
CKAN_PACKAGE_ID = "fe1dfbb9-0fc3-42ca-b2a9-6ca4c05dbac9"
CKAN_API = "https://open.canada.ca/data/api/3/action/package_show"
BULK_HOST = "opic-cipo.ca"
COVERAGE_NOTE = "patent documents 1869 -> 2022-02-28 (CIPO dataset statement)"

# IPC subclasses treated as medical technology (same policy as the EPO connector)
MEDTECH_IPC = {
    "A61B", "A61M", "A61H", "A61N", "A61G", "A61F", "A61J", "A61L", "A61C",
    "A61D", "G16H", "H05G",
}
_DEVICE_SUBCLASSES = MEDTECH_IPC


@dataclass
class PartyRow:
    patent_number: str
    party_name: str
    party_type: str = ""
    enable_date: str | None = None
    end_date: str | None = None
    country: str | None = None


@dataclass
class MainRow:
    patent_number: str
    filing_date: str | None = None
    grant_date: str | None = None
    status_code: str | None = None
    app_type_code: str | None = None
    title_en: str | None = None
    title_fr: str | None = None
    extract_date: str | None = None
    pub_country: str | None = None
    doc_kind: str | None = None
    exam_request_date: str | None = None
    filing_country: str | None = None
    filing_lang: str | None = None
    pct_app: str | None = None
    pct_pub: str | None = None
    pct_pub_date: str | None = None
    parent_app: str | None = None
    pub_kind: str | None = None


def _iso(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if re.match(r"^\d{8}$", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _norm_num(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"[^0-9A-Za-z]", "", str(v))
    return s or None


def _clean(s) -> str | None:
    if s is None:
        return None
    t = str(s).replace("\ufeff", "").strip()
    if not t or t.upper() in ("NULL", "N/A", "NA"):
        return None
    return t


# CIPO publishes these CSVs **pipe-delimited** with a bilingual header of the
# form "Patent Number - Numéro du brevet". Getting either of those wrong makes
# every row unreadable, so the delimiter is sniffed rather than assumed.
_DELIMS = ("|", "\t", ";", ",")


def sniff_delimiter(path: str) -> str:
    with open_csv(path) as fh:
        header = fh.readline()
    best, best_n = "|", -1
    for d in _DELIMS:
        n = header.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def english_header(h: str) -> str:
    """'Patent Number - Numéro du brevet' -> 'Patent Number'"""
    return (h or "").split(" - ")[0].strip()


def sniff_encoding(path: str) -> str:
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head.startswith(b"PK"):
        # zip: look at the first member
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not names:
                return "utf-8-sig"
            with z.open(names[0]) as fh2:
                probe = fh2.read(65536)
    else:
        with open(path, "rb") as fh:
            probe = fh.read(65536)
    try:
        probe.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "latin-1"


def open_csv(path: str):
    """Return a text file object for a .csv or a .csv inside a .zip."""
    enc = sniff_encoding(path)
    if path.lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"{path}: no csv member")
        return io.TextIOWrapper(z.open(names[0]), encoding=enc, errors="replace", newline="")
    return open(path, "r", encoding=enc, errors="replace", newline="")


def iter_csv_dicts(path: str) -> Iterator[dict]:
    delim = sniff_delimiter(path)
    with open_csv(path) as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        for row in reader:
            yield {english_header(k): v for k, v in row.items() if k is not None}


def parse_party(row: dict) -> PartyRow:
    return PartyRow(
        patent_number=_norm_num(row.get("Patent Number")) or "",
        party_name=_clean(row.get("Party Name")) or "",
        party_type=_clean(row.get("Interested Party Type")) or "",
        enable_date=_iso(row.get("Owner Enable Date")),
        end_date=_iso(row.get("Ownership End date")),
        country=_clean(row.get("Party Country Code")),
    )


def parse_main(row: dict) -> MainRow:
    return MainRow(
        patent_number=_norm_num(row.get("Patent Number")) or "",
        filing_date=_iso(row.get("Filling Date")),
        grant_date=_iso(row.get("Grant Date")),
        status_code=_clean(row.get("Application Status Code")),
        app_type_code=_clean(row.get("Application Type Code")),
        title_en=_clean(row.get("Application/Patent Title English")),
        title_fr=_clean(row.get("Application/Patent Title French")),
        extract_date=_iso(row.get("Bibliographic File Extract Date")),
        pub_country=_clean(row.get("Country of Publication Code")),
        doc_kind=_clean(row.get("Document Kind Type")),
        exam_request_date=_iso(row.get("Examination Request Date")),
        filing_country=_clean(row.get("Filling Country Code")),
        filing_lang=_clean(row.get("Language of Filing Code")),
        pct_app=_clean(row.get("PCT Application Number")),
        pct_pub=_clean(row.get("PCT Publication Number")),
        pct_pub_date=_iso(row.get("PCT Publication Date")),
        parent_app=_clean(row.get("Parent Application Number")),
        pub_kind=_clean(row.get("Publication Kind Type")),
    )


def ipc_subclasses(rows: Iterable[dict]) -> list[str]:
    out: list[str] = []
    for r in rows:
        sc = _clean(r.get("IPC Subclass Code")) or ""
        sc = sc[:4].upper()
        if re.match(r"^[A-H]\d\d[A-Z]$", sc) and sc not in out:
            out.append(sc)
    return out


def ipc_full(rows: Iterable[dict]) -> list[str]:
    out: list[str] = []
    for r in rows:
        sec = _clean(r.get("IPC Section Code")) or ""
        cls = _clean(r.get("IPC Class Code")) or ""
        sub = _clean(r.get("IPC Subclass Code")) or ""
        grp = _clean(r.get("IPC Main Group Code")) or ""
        subgrp = _clean(r.get("IPC Subgroup Code")) or ""
        sub_full = sub if len(sub) == 4 else (sec + cls + sub)
        if not sub_full or not grp:
            continue
        g = str(int(grp)) if grp.isdigit() else grp
        tok = f"{sub_full} {g}/{subgrp}"
        if tok not in out:
            out.append(tok)
    return out


def to_record(
    main: MainRow,
    parties: list[PartyRow],
    ipc_subs: list[str],
    ipc_codes: list[str],
    priorities: list[dict],
    fetched_at: str | None = None,
) -> dict:
    fetched_at = fetched_at or now_utc()
    flags = ["SNAPSHOT_ONLY"]

    applicants = [p.party_name for p in parties if "appl" in (p.party_type or "").lower()]
    owners = [p.party_name for p in parties if "owner" in (p.party_type or "").lower()]
    inventors = [p.party_name for p in parties if "invent" in (p.party_type or "").lower()]
    if not applicants and not owners:
        applicants = [p.party_name for p in parties if p.party_name]

    # observability clock: only a recorded grant date counts
    if main.grant_date:
        public_at = main.grant_date
        public_basis = "PT_Main Grant Date"
    else:
        public_at = None
        public_basis = ("no recorded publication/open-to-inspection date; "
                        "CIPO dataset ends 2022-02-28")
        flags.append("MISSING_PUBLICATION_DATE")

    event_at = main.filing_date
    if not event_at:
        flags.append("MISSING_FILING_DATE")
    if not (applicants or owners):
        flags.append("MISSING_MANUFACTURER")
    if not (main.title_en or main.title_fr):
        flags.append("MISSING_TITLE")
    if not ipc_subs:
        flags.append("MISSING_CLASSIFICATION")
    if not priorities:
        flags.append("MISSING_PRIORITY_DATE")

    tech = [s for s in ipc_subs if s in _DEVICE_SUBCLASSES]
    if not tech:
        flags.append("NOT_MEDTECH_ON_FRONT_PAGE")

    doc_id = f"CA{main.patent_number}"
    identifiers = [
        Identifier(
            scheme="cipo_patent_number",
            value=main.patent_number,
            issuing_authority="CIPO",
            scope="CA",
            is_primary=True,
        )
    ]
    if main.pct_app:
        identifiers.append(
            Identifier(scheme="pct_application_number", value=main.pct_app, issuing_authority="WIPO")
        )
    if main.pct_pub:
        identifiers.append(
            Identifier(scheme="pct_publication_number", value=main.pct_pub, issuing_authority="WIPO")
        )

    attrs = {
        "patent_number": main.patent_number,
        "grant_date": main.grant_date,
        "filing_date": main.filing_date,
        "public_availability_basis": public_basis,
        "status_code": main.status_code,
        "application_type_code": main.app_type_code,
        "document_kind": main.doc_kind,
        "publication_kind": main.pub_kind,
        "country_of_publication": main.pub_country,
        "filing_country": main.filing_country,
        "filing_language": main.filing_lang,
        "examination_request_date": main.exam_request_date,
        "bibliographic_extract_date": main.extract_date,
        "pct_application_number": main.pct_app,
        "pct_publication_number": main.pct_pub,
        "pct_publication_date": main.pct_pub_date,
        "parent_application_number": main.parent_app,
        "title_en": main.title_en,
        "title_fr": main.title_fr,
        "applicants": applicants,
        "owners": owners,
        "inventors": inventors,
        "party_ownership_timeline": [
            {
                "party": p.party_name,
                "type": p.party_type,
                "enable_date": p.enable_date,
                "end_date": p.end_date,
                "country": p.country,
            }
            for p in parties
        ],
        "ipc": ipc_codes or ipc_subs,
        "ipc_subclasses": ipc_subs,
        "medtech_ipc_subclasses": tech,
        "priority_claims": priorities,
        "priority_date": min([p["date"] for p in priorities if p.get("date")]) if any(
            p.get("date") for p in priorities
        ) else None,
        "dataset_coverage": COVERAGE_NOTE,
        "clock": classify_record(event_at, public_at),
        "parsed_from": "cipo_open_data_csv",
    }

    relations = []
    for p in priorities:
        if p.get("number"):
            relations.append(
                {
                    "type": "priority_claim",
                    "to_scheme": "priority_application_number",
                    "to_value": f"{p.get('country','?')}{p['number']}",
                    "to_date": p.get("date"),
                    "basis": "PT_Priority_Claim table",
                    "status": "CONFIRMED",
                }
            )

    return build_record(
        source_id=SOURCE_ID,
        source_record_id=doc_id,
        entity_type="patent_publication",
        original_name=main.title_en or main.title_fr or f"(no title) {doc_id}",
        identifiers=identifiers,
        manufacturer=(applicants or owners or [None])[0],
        attributes=attrs,
        event_at=event_at,
        source_public_at=public_at,
        first_observed_at=fetched_at,
        fetched_at=fetched_at,
        source_url=(
            "https://ised-isde.canada.ca/site/canadian-intellectual-property-office/en/"
            "canadian-patents-database"
        ),
        licence_status=LICENCE_STATUS,
        licence_note=f"{LICENCE_NAME} ({LICENCE_URL}) via open.canada.ca package {CKAN_PACKAGE_ID}",
        identity_status="UNKNOWN",
        evidence_status="CANDIDATE",
        quality_flags=sorted(set(flags)),
        relations=relations,
    ).to_dict()
