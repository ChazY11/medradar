"""The FDA document corpus: 510(k) Summaries and PMA statements, as text.

Why this is the moat
--------------------
A 510(k) clearance row in openFDA says: this applicant, this device name, this product code,
this decision date. It does not say what the device does, which predicate it is
substantially equivalent to, which bench tests were run or what the acceptance criteria
were. That information is in the **510(k) Summary PDF**, one per clearance, ~176,466 of
them, and it is:

* public (accessdata.fda.gov serves it anonymously);
* unpriced (no vendor sells it as a corpus);
* unparsed (no market-intelligence platform structures it).

A design engineer's real question - "how did three competitors prove their delivery system
was safe, and with what test methods" - is answerable only from these documents. Market
share estimates are not.

URL derivation, verified rather than assumed
--------------------------------------------
The 510(k) document space follows one rule, confirmed against live filings:

    K<nnnnnn>  ->  https://www.accessdata.fda.gov/cdrh_docs/pdf<nn>/K<nnnnnn>.pdf

where ``<nn>`` is the first two digits of the K number's numeric part. K252901 resolves to
``pdf25/K252901.pdf``; six of six sampled clearances returned a real PDF with a text layer
between 11,869 and 50,914 characters.

Every filing does **not** have one. openFDA's ``statement_or_summary`` field distinguishes
``Summary`` from ``Statement`` and from an empty value, and older filings frequently publish
nothing at all. A missing document is recorded as ``not_published`` - never as an empty
summary, because "FDA published no summary" and "we failed to read the summary" are
different facts and only one of them is our fault.

PMA is deliberately not claimed here
------------------------------------
PMA documents (SSED, approval order, summary) live in a less regular URL space that mixes
``pdf``/``pdf2``/``pdf3`` prefixes with letter suffixes. A guessed URL that happens to
return 200 would be worse than no URL, so :func:`derive_pma_urls` returns the candidates it
can justify and callers must verify the payload is a PDF before recording anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .pdf import PdfText, extract_text

BASE = "https://www.accessdata.fda.gov/cdrh_docs"
#: A real 510(k) Summary is a multi-page document. Anything smaller is an error page that
#: happened to start with %PDF, which some FDA edge responses do.
MIN_PDF_BYTES = 2_048

#: Section headings that actually appear in 510(k) Summaries, in the order a reader expects.
#: Matching is case-insensitive and tolerant of numbering ("1. Indications for Use").
SECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("indications", r"indications?\s+for\s+use"),
    ("device_description", r"device\s+description"),
    ("substantial_equivalence", r"substantial\s+equivalen(?:ce|t)"),
    ("predicate_comparison", r"comparison\s+(?:of|to)\b.*?(?:predicate|cleared|device)"),
    ("performance_data", r"performance\s+(?:data|testing|test)"),
    ("bench_testing", r"(?:bench|non-?clinical|in\s+vitro)\s+(?:testing|tests?|studies)"),
    ("sterilization", r"sterili[sz]ation"),
    ("biocompatibility", r"biocompatibilit"),
    ("animal_testing", r"(?:animal|in\s+vivo)\s+(?:testing|studies)"),
    ("clinical_data", r"clinical\s+(?:data|studies|testing)"),
    ("conclusion", r"conclusions?"),
    ("risks_mitigation", r"risk\s+(?:analysis|mitigation)|mitigation\s+measures"),
    # The pre-2013 format. Filings up to roughly 2012 follow 21 CFR 807.92 as a lettered list -
    # "A. 510(k) Number", "B. Purpose for Submission", "C. Measurand", "D. Type of Test" - rather
    # than the modern "Indications for Use" headings. Measured on K100017 (a 2010 scan): without
    # these the whole document collapses into one unnamed block and every section is lost.
    ("submission_identity", r"(?:510\s*\(?\s*k\s*\)?\s*number|purpose\s+for\s+submission)"),
    ("measurand", r"measurand|analyte"),
    ("test_type", r"type\s+of\s+test"),
    ("applicant_identity", r"applicant|submitter|establishment\s+registration"),
    ("device_names", r"proprietary\s+(?:and|&)\s+established\s+names?|trade\s+or\s+proprietary\s+names?"),
    ("regulatory_info", r"regulatory\s+information|device\s+class(?:ification)?"),
    ("intended_use", r"intended\s+use"),
)

#: A section body shorter than this is form scaffolding, not content. Measured on K252901:
#: the OMB form template repeats the heading "Indications for Use" above its own instruction
#: text ("Please type in the marketing application/submission number"), so the first match is
#: almost never the real section.
SECTION_MIN_CHARS = 40

#: Lines that are form instructions rather than a manufacturer's statement.
_FORM_SCAFFOLDING = re.compile(
    r"(form approved|omb no\.|paperwork reduction|please type in|textbox will be left blank|"
    r"see pra statement|expiration date|according to the paperwork)",
    re.IGNORECASE,
)

_HEADING_RE = re.compile(
    # Optional numbering: "1." or "B." - the pre-2013 lettered format (21 CFR 807.92) numbers its
    # headings A, B, C, and the earlier version of this regex only accepted digits, so a 2010
    # summary produced no sections at all.
    r"^\s*(?:(?:\d{1,2}|[A-Z])[.)]\s*)?(?P<heading>"
    + "|".join(p for _, p in SECTION_PATTERNS)
    + r")\s*(?:\((?:[A-Za-z][A-Za-z .]{0,14})\))?\s*:?[ \t]*(?P<inline>.*)$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class DocumentRecord:
    """One fetched regulatory document and what could be read out of it."""

    kind: str
    identifier: str
    url: str
    status: str                      # "text" | "no_text_layer" | "not_published" | "failed"
    http_status: int | None = None
    bytes: int = 0
    pdf: PdfText | None = None
    sections: dict[str, str] = field(default_factory=dict)
    from_cache: bool = False
    note: str | None = None

    @property
    def text(self) -> str:
        return self.pdf.text if self.pdf else ""

    def summary(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "identifier": self.identifier,
            "url": self.url,
            "status": self.status,
            "http_status": self.http_status,
            "bytes": self.bytes,
            "char_count": len(self.text),
            "sections": sorted(self.sections),
            "pdf": self.pdf.summary() if self.pdf else None,
            "from_cache": self.from_cache,
            "note": self.note,
        }


def derive_510k_pdf_url(k_number: str) -> str | None:
    """The one 510(k) document URL rule, or None when the identifier cannot be used."""
    digits = re.sub(r"\D", "", str(k_number or "").strip().upper().lstrip("K"))
    if len(digits) < 6:
        return None
    return f"{BASE}/pdf{digits[:2]}/K{digits}.pdf"


def derive_pma_urls(pma_number: str, supplement: str | None = None) -> list[str]:
    """Candidate PMA document URLs, in the order they are worth trying.

    Returned as candidates, not as an answer: the caller must confirm the payload is a PDF.
    """
    value = str(pma_number or "").strip().upper()
    if not re.fullmatch(r"P\d{6}", value):
        return []
    stem = value
    if supplement and str(supplement).strip() not in ("", "0"):
        stem = f"{value}S{str(supplement).strip().lstrip('S').zfill(3)}"
    return [
        f"{BASE}/pdf/{stem}B.pdf",
        f"{BASE}/pdf/{stem}A.pdf",
        f"{BASE}/pdf/{stem}.pdf",
    ]


class DocumentStore:
    """A directory of fetched documents plus a JSON sidecar per document.

    The sidecar is the point: a 176k-document sweep must be resumable, and a reader must be
    able to tell a cached "FDA published no summary" from a cached summary without opening
    the PDF.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _paths(self, kind: str, identifier: str) -> tuple[Path, Path]:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", f"{kind}_{identifier}")
        return self.root / f"{safe}.json", self.root / f"{safe}.txt"

    def read(self, kind: str, identifier: str) -> DocumentRecord | None:
        meta_path, text_path = self._paths(kind, identifier)
        if not meta_path.exists():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
        return DocumentRecord(
            kind=str(payload.get("kind") or kind),
            identifier=str(payload.get("identifier") or identifier),
            url=str(payload.get("url") or ""),
            status=str(payload.get("status") or "failed"),
            http_status=payload.get("http_status"),
            bytes=int(payload.get("bytes") or 0),
            pdf=_pdf_from_summary(payload.get("pdf"), text),
            sections=dict(payload.get("sections") or {}),
            from_cache=True,
            note=payload.get("note"),
        )

    def write(self, record: DocumentRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        meta_path, text_path = self._paths(record.kind, record.identifier)
        payload = record.summary()
        payload["sections"] = record.sections
        payload["text_chars"] = len(record.text)
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if record.text:
            text_path.write_text(record.text, encoding="utf-8")

    def coverage(self) -> dict[str, Any]:
        if not self.root.exists():
            return {"documents": 0, "with_text": 0, "without_text": 0, "not_published": 0}
        counts: dict[str, int] = {}
        for meta in self.root.glob("*.json"):
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            status = str(payload.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        return {
            "documents": sum(counts.values()),
            "with_text": counts.get("text", 0),
            "without_text": counts.get("no_text_layer", 0) + counts.get("failed", 0),
            "not_published": counts.get("not_published", 0),
            "by_status": counts,
        }


def fetch_510k_summary(fetcher, k_number: str, *, store: DocumentStore | None = None,
                       refresh: bool = False) -> DocumentRecord:
    """Fetch and parse one 510(k) Summary.

    Never raises for an absent or unreadable document: a sweep of 176k filings must survive
    the ones that were never published, and "not published" is a recorded outcome.
    """
    from .records import utc_now_iso
    from .http import FetchError

    identifier = re.sub(r"\D", "", str(k_number or "")).zfill(6)
    if not identifier:
        return DocumentRecord(kind="510k_summary", identifier=str(k_number), url="",
                             status="not_published", note="no numeric K identifier")
    if store and not refresh:
        cached = store.read("510k_summary", f"K{identifier}")
        if cached is not None:
            return cached
    url = derive_510k_pdf_url(f"K{identifier}") or ""
    record = DocumentRecord(kind="510k_summary", identifier=f"K{identifier}", url=url,
                            status="failed")
    try:
        result = fetcher.get_bytes(url, allow_not_found=True)
    except FetchError as error:
        record.note = f"{type(error).__name__}: {error}"[:400]
        record.status = "failed"
        if store:
            store.write(record)
        return record

    record.http_status = result.status
    record.bytes = result.raw_bytes
    if result.status == 404 or not result.payload:
        record.status = "not_published"
        record.note = "FDA serves no document at the derived URL"
        if store:
            store.write(record)
        return record
    if result.raw_bytes < MIN_PDF_BYTES or not result.payload.startswith(b"%PDF"):
        record.status = "failed"
        record.note = (f"payload was not a plausible PDF ({result.raw_bytes} bytes, "
                       f"content-type {result.content_type})")
        if store:
            store.write(record)
        return record

    parsed = extract_text(result.payload)
    record.pdf = parsed
    if parsed.has_text_layer:
        record.status = "text"
        record.sections = split_sections(parsed.text)
    else:
        record.status = "no_text_layer"
        record.note = f"pdf reason={parsed.reason}; needs OCR"
    if store:
        store.write(record)
    return record


def split_sections(text: str) -> dict[str, str]:
    """Split a 510(k) Summary into the sections a reader actually looks for.

    A heading can appear more than once - the OMB form template repeats several of them above
    its own instructions - so the *longest* body for each key wins rather than the first one.
    A body made of form scaffolding is discarded.

    Returns only the sections that were found. An absent section is absent - it is not an
    empty string, because "this summary states no clinical data" and "our splitter missed the
    clinical section" must not look the same to a downstream reader.
    """
    if not text:
        return {}
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return {}
    candidates: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        key = _key_for(match.group("heading"))
        if key is None:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        inline = (match.group("inline") or "").strip()
        body = text[start:end].strip()
        if inline:
            # "B. Purpose for Submission: New device" - the value sits on the heading line in the
            # lettered format. Dropping it would lose the shortest, most specific sections.
            body = (inline + "\n" + body).strip()
        # The length floor exists to reject a bare heading echoed by the OMB template. A line
        # that carried a value inline is a deliberate "field: answer" statement, so it is kept
        # even when the answer is short - "A. 510(k)Number: K100017" is seven characters and is
        # exactly the fact a reader wants.
        if len(body) < SECTION_MIN_CHARS and not inline:
            continue
        # A body that opens with form instructions is the template echoing its own heading,
        # however long it is. Reporting it as "Indications for Use" would put the OMB
        # paperwork notice in front of an engineer as if a manufacturer had written it.
        if _FORM_SCAFFOLDING.search(body[:400]):
            continue
        candidates.setdefault(key, []).append(body[:20_000])
    return {key: max(bodies, key=len) for key, bodies in candidates.items()}


def _key_for(heading_text: str) -> str | None:
    for key, pattern in SECTION_PATTERNS:
        if re.search(pattern, heading_text, re.IGNORECASE):
            return key
    return None


def _pdf_from_summary(summary: Mapping[str, Any] | None, text: str) -> PdfText:
    payload = dict(summary or {})
    return PdfText(
        text=text,
        has_text_layer=bool(payload.get("has_text_layer")),
        reason=payload.get("reason"),
        streams_found=int(payload.get("streams_found") or 0),
        streams_decoded=int(payload.get("streams_decoded") or 0),
        bytes_seen=int(payload.get("bytes_seen") or 0),
    )


__all__ = [
    "DocumentRecord",
    "DocumentStore",
    "MIN_PDF_BYTES",
    "SECTION_PATTERNS",
    "derive_510k_pdf_url",
    "derive_pma_urls",
    "fetch_510k_summary",
    "split_sections",
]
