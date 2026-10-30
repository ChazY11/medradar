"""EDGAR 8-K catalyst corpus: pure parsing, classification and corpus utilities.

Why a corpus
------------
The 25-filing calibration in ``docs/CALIBRATION.md`` is a pilot: it is enough to
compare a judge against a keyword baseline, not enough to train, evaluate or
show a case library. This module turns SEC EDGAR full-text search hits into a
**reproducible, date-anchored corpus** of 8-K catalyst announcements
(2019-01-01 .. 2026-10-31) that later stages can consume offline:

* case library / examples for the report and dashboard;
* event-study input (``to_events()`` produces rows in the ``events`` table shape,
  with ``event_date = filing date`` so there is no look-ahead);
* a bigger, harder sample for judge evaluation.

Design rules
------------
* **Pure functions.** No network, no SQLite, no global state. The crawler lives in
  ``scripts/build_corpus.py``; everything here is unit-testable offline.
* **The filing date is the observation date.** ``event_date`` is the 8-K
  ``file_date`` (the moment the announcement became public). Text is stored but
  never used to date the event.
* **Text, not HTML.** ``clean_html`` is deterministic and dependency-free so the
  stored 24k prefix is reproducible from the cached raw document.
* **Classification is a documented heuristic**, not a model call: phrase buckets
  from the query + keyword evidence from the text, with an explicit priority
  ladder. It is meant to be reviewed/corrected by the case engine later, so every
  record carries ``classification.reasons``.

Corpus record (one line of ``corpus.jsonl``)
--------------------------------------------
::

    {"accession", "cik", "company", "ticker", "company_key",
     "filed", "form", "document", "url", "buckets", "windows", "items",
     "category", "direction", "classification": {"reasons","confidence","scores"},
     "text", "text_chars", "raw_chars", "fetched_at", "fetch_status",
     "source", "corpus_version"}
"""

from __future__ import annotations

import html as _html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import DATA_DIR
from .util import ensure_dir, read_json, sha1, truncate, utc_now_iso, write_json

CORPUS_VERSION = "edgar-corpus-v1"
SOURCE = "sec_edgar_8k"
KIND = "8k_catalyst"
DEFAULT_CORPUS_DIR = DATA_DIR / "edgar_corpus"
DEFAULT_CORPUS_PATH = DEFAULT_CORPUS_DIR / "corpus.jsonl"
MAX_TEXT_CHARS = 24_000
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
FTS_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"

#: The seven query buckets. The *order* is part of the contract: it decides the
#: tie-break priority when a filing matches several buckets, and it is the order
#: used in every distribution table.
BUCKET_ORDER: tuple[str, ...] = (
    "fda approval",
    "receives fda approval",
    "complete response letter",
    "did not meet",
    "met the primary endpoint",
    "announces positive topline",
    "financial results",
)

#: Bucket -> category prior (what a filing is *probably* about if that query hit).
BUCKET_CATEGORY: dict[str, str] = {
    "fda approval": "approval",
    "receives fda approval": "approval",
    "complete response letter": "crl",
    "did not meet": "trial_result",
    "met the primary endpoint": "trial_result",
    "announces positive topline": "trial_result",
    "financial results": "earnings",
}

CATEGORIES: tuple[str, ...] = ("approval", "crl", "trial_result", "earnings", "other")

#: Tie-break order when two categories have the same evidence score.
CATEGORY_PRIORITY: tuple[str, ...] = ("crl", "trial_result", "approval", "earnings", "other")

#: Healthcare name markers. Deliberately recall-oriented: a missed biotech is a
#: missing case, a few false positives are visible and filterable downstream.
HEALTHCARE_PATTERNS: tuple[str, ...] = (
    "THERAPEUT",
    "PHARMA",
    "BIOTECH",
    "BIOSCIENCE",
    "BIO",
    "MEDICIN",
    "MEDICAL",
    "HEALTH",
    "GENOMIC",
    "GENETIC",
    "ONCOLOG",
    "IMMUN",
    "CELLULAR",
    "LIFESCIENCE",
    "LIFE SCIENCES",
    "CLINICAL",
    "DIAGNOSTIC",
    "VACCIN",
    "SURGICAL",
    "SURGERY",
    "NEURO",
    "CARDIO",
    "OPHTHALM",
    "DERMA",
    "ORTHOPED",
    "HOSPITAL",
    "BIOLOGIC",
)

#: SEC SIC codes whose filers are healthcare even when the legal name is opaque
#: ("Immunome Inc." contains none of the markers above). 2834 pharma, 2836
#: biological, 3826 lab instruments, 384x medical devices, 8011/8050/8060 care,
#: 8731/8734 research services.
HEALTHCARE_SIC_CODES: frozenset[str] = frozenset(
    {"2834", "2835", "2836", "3826", "3841", "3842", "3843", "3844", "3845",
     "3851", "3861", "8011", "8050", "8060", "8731", "8734"}
)

#: Text evidence patterns per category. Scanned case-insensitively; a hit in the
#: *lead* window (headline / first paragraph) is worth much more than a hit buried
#: in boilerplate, because press releases keep describing prior catalysts.
TEXT_PATTERNS: dict[str, tuple[str, ...]] = {
    "crl": (
        "complete response letter",
        "complete response (crl)",
        "received a crl",
        "receives a crl",
    ),
    "trial_negative": (
        "did not meet",
        "failed to meet",
        "did not achieve",
        "fails to meet",
        "failed to achieve",
        "missed the primary endpoint",
        "missed its primary endpoint",
        "did not demonstrate",
    ),
    "approval": (
        "fda approval",
        "fda has approved",
        "approved by the fda",
        "approved by fda",
        "receives fda approval",
        "received fda approval",
        "granted approval",
        "approval from the fda",
        "marketing approval",
    ),
    "trial_positive": (
        "met the primary endpoint",
        "met its primary endpoint",
        "met the primary efficacy endpoint",
        "met its primary efficacy endpoint",
        "primary endpoint met",
        "primary efficacy endpoint met",
        "positive topline",
        "positive top-line",
        "positive topline results",
        "achieved the primary endpoint",
        "statistically significant",
    ),
    "earnings": (
        "financial results",
        "quarterly results",
        "full year results",
        "full-year results",
        "reports financial results",
        "earnings call",
        "results for the three months",
        "results for the fiscal year",
    ),
}

#: Lead-window phrases that say "this 8-K is not a catalyst announcement".
#: Financing and presentation releases routinely mention past approvals and
#: trials, which is exactly how a keyword filter produces false catalysts.
OTHER_LEAD_STRONG: tuple[str, ...] = (
    "debt facility",
    "credit facility",
    "term loan",
    "loan agreement",
    "private placement",
    "public offering",
    "securities purchase agreement",
    "underwriting agreement",
    "royalty financing",
    "investment by",
    "license agreement",
    "collaboration agreement",
    "merger agreement",
)
#: Exhibit decks are not announcements at all; they outweigh keyword matches.
OTHER_PRESENTATION: tuple[str, ...] = (
    "corporate presentation",
    "investor presentation",
)
OTHER_LEAD_WEAK: tuple[str, ...] = (
    "provides corporate update",
    "business update",
    "provides a business update",
)

#: Pattern group -> category, and the evidence weight of a hit.
_PATTERN_CATEGORY: dict[str, str] = {
    "crl": "crl",
    "trial_negative": "trial_result",
    "approval": "approval",
    "trial_positive": "trial_result",
    "earnings": "earnings",
}

_LEAD_WEIGHT = 3
_BODY_WEIGHT = 1
_BUCKET_LEAD_WEIGHT = 3
_BUCKET_BODY_WEIGHT = 1
_ITEM_EARNINGS_WEIGHT = 4
_ITEM_DEAL_WEIGHT = 2
_OTHER_STRONG_WEIGHT = 5
_OTHER_PRESENTATION_WEIGHT = 7
_OTHER_WEAK_WEIGHT = 2
LEAD_CHARS = 1_600

#: 8-K item numbers. ``2.02`` is "Results of Operations and Financial Condition" -
#: the authoritative "this is an earnings release" flag, far stronger than any
#: keyword. ``1.01``/``2.01`` usually mean a deal.
ITEM_EARNINGS = "2.02"
ITEM_DEAL = frozenset({"1.01", "2.01"})

__all__ = [
    "CORPUS_VERSION",
    "SOURCE",
    "KIND",
    "DEFAULT_CORPUS_DIR",
    "DEFAULT_CORPUS_PATH",
    "MAX_TEXT_CHARS",
    "ARCHIVES_BASE",
    "FTS_ENDPOINT",
    "BUCKET_ORDER",
    "BUCKET_CATEGORY",
    "CATEGORIES",
    "CATEGORY_PRIORITY",
    "HEALTHCARE_PATTERNS",
    "HEALTHCARE_SIC_CODES",
    "TEXT_PATTERNS",
    "clean_html",
    "truncate_text",
    "is_healthcare_company",
    "parse_display_name",
    "normalize_company_name",
    "parse_fts_hit",
    "merge_candidates",
    "filing_url",
    "classify_detail",
    "classify",
    "build_record",
    "build_manifest",
    "read_jsonl",
    "load_corpus",
    "write_corpus",
    "corpus_sha1",
    "stratified_subset",
    "summarize",
    "to_events",
]


# ------------------------------------------------------------------ html => text
_SCRIPT_RE = re.compile(r"<\s*(script|style|noscript)\b[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_BLOCK_RE = re.compile(
    r"<\s*/?\s*(?:br|p|div|tr|li|h[1-6]|table|section|article|ul|ol|td|th)\b[^>]*>", re.I
)
_TAG_RE = re.compile(r"<[^>]*>")
_INLINE_WS_RE = re.compile(r"[ \t\u00a0\f\v\r]+")
_EXTRA_NL_RE = re.compile(r"\n{2,}")


def clean_html(raw: str) -> str:
    """Convert an EDGAR HTML document into deterministic plain text.

    Steps (all standard library, order matters):

    1. drop comments and ``script`` / ``style`` / ``noscript`` blocks - their
       contents are not filing prose and would poison keyword evidence;
    2. turn block-level tags (``</p>``, ``<br>``, ``</tr>`` ...) into newlines so
       paragraphs stay separated;
    3. strip all remaining tags;
    4. unescape HTML entities **twice** - EDGAR filings are frequently
       double-encoded (``&#38;nbsp;``), and a single pass leaves ``&nbsp;`` text;
    5. collapse runs of spaces/tabs, trim each line, collapse 3+ blank lines.

    No text is truncated here: callers decide the storage limit
    (:data:`MAX_TEXT_CHARS`) so the cleaning function stays reusable.
    """
    text = str(raw or "")
    if not text:
        return ""
    text = _COMMENT_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    text = _html.unescape(text)
    text = text.replace("\x00", " ").replace("\xa0", " ")
    text = _INLINE_WS_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _EXTRA_NL_RE.sub("\n", text)
    return text.strip()


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Cap stored text at ``limit`` characters (default 24k, matching the judge prompt).

    Uses :func:`medradar.util.truncate` so the ellipsis convention is the same as
    everywhere else in the repo; ``24k`` is the prompt budget in
    ``medradar.llm.MAX_INPUT_CHARS``.
    """
    return truncate(text, limit)


# --------------------------------------------------------------------- company
def normalize_company_name(name: Any) -> str:
    """Collapse whitespace and strip SEC display-name decoration."""
    return re.sub(r"\s+", " ", str(name or "")).strip()


def parse_display_name(display: Any) -> dict[str, Any]:
    """Parse EDGAR's ``"Immunome Inc.  (IMNM)  (CIK 0001472012)"`` display string.

    Returns ``{"name", "ticker", "cik"}``. Robust to missing pieces: EDGAR omits
    the ticker for non-listed filers and sometimes ships bare names.
    """
    text = normalize_company_name(display)
    cik_match = re.search(r"\(\s*CIK\s+(\d+)\s*\)", text, re.I)
    cik = int(cik_match.group(1)) if cik_match else None
    name = text
    if cik_match:
        name = text[: cik_match.start()].strip()
    ticker = ""
    ticker_match = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", name)
    if ticker_match:
        ticker = ticker_match.group(1)
        name = (name[: ticker_match.start()] + " " + name[ticker_match.end():]).strip()
    name = re.sub(r"\s{2,}", " ", name).strip().rstrip(",").strip()
    if not name:
        name = text
    return {"name": name, "ticker": ticker, "cik": cik}


def is_healthcare_company(name: Any, sic_codes: Iterable[Any] = ()) -> bool:
    """True when a filer looks like a healthcare company.

    Name markers are the primary signal (as specified by the research task);
    SEC SIC codes are accepted as a second, cleaner signal because plenty of
    biotechs have names with no marker at all ("Immunome"). This is recall-first
    on purpose: a missing catalyst is invisible, a wrong one can be reviewed.
    """
    upper = normalize_company_name(name).upper()
    if any(pattern in upper for pattern in HEALTHCARE_PATTERNS):
        return True
    for code in sic_codes or ():
        digits = re.sub(r"\D", "", str(code))
        if digits[:4] in HEALTHCARE_SIC_CODES:
            return True
    return False


# ------------------------------------------------------------------- FTS hits
def filing_url(cik: Any, accession: str, document: str) -> str:
    """Direct EDGAR Archives URL for one document (no index.json round-trip).

    CIK leading zeros are stripped (EDGAR serves ``/data/1472012/...``, not the
    10-digit padded form) and the accession loses its dashes, matching the
    canonical Archives layout.
    """
    cik_text = re.sub(r"\D", "", str(cik or "")).lstrip("0") or "0"
    accession_text = str(accession or "").replace("-", "").strip()
    return f"{ARCHIVES_BASE}/{cik_text}/{accession_text}/{document}"


def parse_fts_hit(
    hit: Mapping[str, Any], bucket: str, window: str | None = None
) -> dict[str, Any] | None:
    """Normalise one ``hits.hits[]`` element into a candidate dict (or ``None``).

    ``None`` means "not usable": missing ``_id``/document, unparsable accession,
    or a filer that fails the healthcare filter. No exception is raised - a
    malformed hit must not kill a 200-query crawl.
    """
    if not isinstance(hit, Mapping):
        return None
    source = hit.get("_source") or {}
    if not isinstance(source, Mapping):
        return None
    raw_id = str(hit.get("_id") or "")
    accession, _, document = raw_id.partition(":")
    accession = accession.strip()
    document = document.strip()
    if not accession or not document:
        return None
    if not re.match(r"^\d{10}-\d{2}-\d{6}$", accession):
        return None
    form = str(source.get("form") or "")
    if form and not form.upper().startswith("8-K"):
        return None
    displays = [str(item) for item in (source.get("display_names") or []) if item]
    parsed = parse_display_name(displays[0] if displays else "")
    ciks = [re.sub(r"\D", "", str(item)) for item in (source.get("ciks") or [])]
    ciks = [cik for cik in ciks if cik]
    cik = int(ciks[0]) if ciks else (parsed["cik"] or 0)
    sics = tuple(re.sub(r"\D", "", str(item)) for item in (source.get("sics") or []))
    if not is_healthcare_company(parsed["name"], sics):
        return None
    filed = str(source.get("file_date") or "")
    return {
        "accession": accession,
        "cik": cik,
        "company": parsed["name"],
        "ticker": parsed["ticker"],
        "filed": filed,
        "form": form or "8-K",
        "document": document,
        "file_type": str(source.get("file_type") or ""),
        "sequence": int(source.get("sequence") or 0),
        "items": [str(item) for item in (source.get("items") or [])],
        "sics": list(sics),
        "url": filing_url(cik, accession, document),
        "buckets": [bucket],
        "windows": [window] if window else [],
    }


def merge_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """De-duplicate candidates by accession and union their bucket evidence.

    EDGAR FTS returns one hit **per matching document** inside a filing, so the
    same 8-K can appear once per exhibit. We keep one document per accession:

    * prefer the document matched by the highest-priority bucket (``BUCKET_ORDER``
      order), because that is the document that actually contains the catalyst
      wording;
    * a primary ``8-K`` document is preferred only as a tie-break - the body of
      the announcement usually lives in the EX-99.1 press release, not in the
      cover-page 8-K;
    * identifiers (cik/company/ticker/filed) come from the first hit and are not
      overwritten by later duplicates.

    Output is sorted by ``(filed, accession)`` so the corpus file is stable across
    crawls.
    """
    by_accession: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        accession = str(candidate.get("accession") or "")
        if not accession:
            continue
        buckets = list(candidate.get("buckets") or [])
        rank = min(
            (BUCKET_ORDER.index(b) for b in buckets if b in BUCKET_ORDER),
            default=len(BUCKET_ORDER),
        )
        current = by_accession.get(accession)
        if current is None:
            merged = dict(candidate)
            merged["buckets"] = [b for b in BUCKET_ORDER if b in buckets] or buckets
            merged["windows"] = list(dict.fromkeys(candidate.get("windows") or []))
            by_accession[accession] = merged
            continue
        # rank of the document we already hold, captured *before* the buckets merge
        previous_rank = min(
            (BUCKET_ORDER.index(b) for b in current.get("buckets") or [] if b in BUCKET_ORDER),
            default=len(BUCKET_ORDER),
        )
        for bucket in buckets:
            if bucket not in current["buckets"]:
                current["buckets"].append(bucket)
        current["buckets"] = [b for b in BUCKET_ORDER if b in current["buckets"]]
        for window in candidate.get("windows") or []:
            if window not in current["windows"]:
                current["windows"].append(window)
        # a higher-priority bucket hit (smaller rank) replaces the chosen document
        if rank < previous_rank:
            for key in ("document", "file_type", "sequence", "url"):
                current[key] = candidate.get(key, current.get(key))
    return sorted(
        by_accession.values(),
        key=lambda item: (str(item.get("filed") or ""), str(item.get("accession") or "")),
    )


# ------------------------------------------------------------------ classifier
def _score_categories(
    text: str, buckets: Sequence[str], items: Sequence[str]
) -> tuple[dict[str, float], list[str]]:
    """Evidence scores per category (see :func:`classify_detail` for the model)."""
    lower = (text or "").lower()
    lead = lower[:LEAD_CHARS]
    scores: dict[str, float] = {category: 0.0 for category in CATEGORIES}
    reasons: list[str] = []
    for bucket in buckets:
        category = BUCKET_CATEGORY.get(bucket)
        if not category:
            continue
        if bucket in lead:
            scores[category] += _BUCKET_LEAD_WEIGHT
            reasons.append(f"lead-bucket:{bucket}")
        else:
            scores[category] += _BUCKET_BODY_WEIGHT
            reasons.append(f"bucket:{bucket}")
    for pattern_group, patterns in TEXT_PATTERNS.items():
        category = _PATTERN_CATEGORY[pattern_group]
        if any(pattern in lead for pattern in patterns):
            matched = next(pattern for pattern in patterns if pattern in lead)
            scores[category] += _LEAD_WEIGHT
            reasons.append(f"lead:{matched}")
            continue
        matched = next((pattern for pattern in patterns if pattern in lower), None)
        if matched is not None:
            scores[category] += _BODY_WEIGHT
            reasons.append(f"text:{matched}")
    item_set = {str(item).strip() for item in (items or [])}
    if ITEM_EARNINGS in item_set:
        scores["earnings"] += _ITEM_EARNINGS_WEIGHT
        reasons.append(f"item:{ITEM_EARNINGS}")
    if item_set & ITEM_DEAL:
        scores["other"] += _ITEM_DEAL_WEIGHT
        reasons.append("item:deal")
    strong_other = next((pattern for pattern in OTHER_LEAD_STRONG if pattern in lead), None)
    if strong_other:
        scores["other"] += _OTHER_STRONG_WEIGHT
        reasons.append(f"context:{strong_other}")
    presentation = next((pattern for pattern in OTHER_PRESENTATION if pattern in lead), None)
    if presentation:
        scores["other"] += _OTHER_PRESENTATION_WEIGHT
        reasons.append(f"presentation:{presentation}")
    weak_other = next((pattern for pattern in OTHER_LEAD_WEAK if pattern in lead), None)
    if weak_other:
        scores["other"] += _OTHER_WEAK_WEIGHT
        reasons.append(f"context:{weak_other}")
    return scores, reasons


def _confidence(score: float) -> float:
    if score >= 6:
        return 1.0
    if score >= 4:
        return 0.8
    if score >= 2:
        return 0.6
    if score >= 1:
        return 0.4
    return 0.0


def classify_detail(
    text: str,
    buckets: Sequence[str] = (),
    items: Sequence[str] = (),
) -> dict[str, Any]:
    """Heuristic category + direction for one filing, with its evidence.

    Evidence model (deterministic, no model calls)::

        score[category] = 3 if a query-bucket phrase appears in the lead (first 1.6k
                           chars) else 1 if it appears anywhere
                        + 3 if a category keyword appears in the lead, else 1 in body
                        + 4 if the 8-K carries Item 2.02 (results of operations)
                        + 5 for a lead-window financing/licensing marker -> "other"
                        + 7 for a corporate/investor presentation marker -> "other"
                        + 2 for a softer "business update" marker -> "other"

    Why the lead window dominates: an 8-K press release keeps describing *past*
    catalysts ("following the FDA approval of X in March..."), so whole-text
    keyword matching turns an earnings release into an "approval". The headline is
    where the event is stated, so lead evidence outranks body evidence. Item 2.02
    is authoritative metadata from EDGAR itself and outranks any keyword.

    The highest score wins; ties fall back to :data:`CATEGORY_PRIORITY`
    (``crl`` > ``trial_result`` > ``approval`` > ``earnings`` > ``other``). A
    filing whose best evidence is only a body-level bucket mention is kept
    (score 1, low confidence) rather than silently dropped - the case engine is
    supposed to review it.

    Direction: ``approval`` +1, ``crl`` -1, ``trial_result`` -1 for a miss / +1
    for a hit / 0 when no polarity is detectable, ``earnings`` and ``other`` 0.

    Returns ``{"category", "direction", "confidence", "scores", "reasons"}``.
    ``confidence`` is a coarse evidence-strength label (not a probability).
    """
    scores, reasons = _score_categories(text, list(buckets), list(items))
    lower = (text or "").lower()
    best_score = max(scores.values())
    if best_score <= 0:
        return {
            "category": "other",
            "direction": 0,
            "confidence": 0.0,
            "scores": scores,
            "reasons": reasons,
        }
    ranking = sorted(
        scores,
        key=lambda category: (-scores[category], CATEGORY_PRIORITY.index(category)),
    )
    category = ranking[0]
    negative = any(pattern in lower for pattern in TEXT_PATTERNS["trial_negative"])
    positive = any(pattern in lower for pattern in TEXT_PATTERNS["trial_positive"])
    if category == "trial_result":
        direction = -1 if negative else (1 if positive else 0)
    elif category == "approval":
        direction = 1
    elif category == "crl":
        direction = -1
    else:
        direction = 0
    return {
        "category": category,
        "direction": direction,
        "confidence": _confidence(best_score),
        "scores": {key: round(value, 2) for key, value in scores.items()},
        "reasons": reasons,
    }


def classify(
    text: str, buckets: Sequence[str] = (), items: Sequence[str] = ()
) -> str:
    """Convenience wrapper returning only the category (see :func:`classify_detail`)."""
    return str(classify_detail(text, buckets, items)["category"])


# --------------------------------------------------------------------- records
def build_record(
    candidate: Mapping[str, Any],
    text: str,
    *,
    fetched_at: str | None = None,
    raw_chars: int | None = None,
    fetch_status: str = "ok",
    company_key: str = "",
    items: Sequence[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Join a search candidate with its fetched text into one corpus record.

    ``text`` is expected to be **already cleaned** (plain text); it is capped at
    :data:`MAX_TEXT_CHARS` here so no caller can accidentally store a whole HTML
    page. ``category``/``direction`` come from :func:`classify_detail` using the
    query buckets and the 8-K item numbers as evidence (``items`` defaults to the
    candidate's ``items`` field captured from EDGAR FTS).
    """
    plain = str(text or "")
    stored = truncate_text(plain, MAX_TEXT_CHARS)
    item_list = [str(item) for item in (items if items is not None else candidate.get("items") or [])]
    detail = classify_detail(plain, list(candidate.get("buckets") or []), item_list)
    buckets = list(candidate.get("buckets") or [])
    record: dict[str, Any] = {
        "accession": str(candidate.get("accession") or ""),
        "cik": int(candidate.get("cik") or 0),
        "company": normalize_company_name(candidate.get("company")),
        "ticker": str(candidate.get("ticker") or ""),
        "company_key": str(company_key or ""),
        "filed": str(candidate.get("filed") or ""),
        "form": str(candidate.get("form") or "8-K"),
        "document": str(candidate.get("document") or ""),
        "url": str(candidate.get("url") or ""),
        "buckets": [b for b in BUCKET_ORDER if b in buckets] or buckets,
        "windows": list(candidate.get("windows") or []),
        "items": item_list,
        "category": detail["category"],
        "direction": int(detail["direction"]),
        "classification": {
            "reasons": detail["reasons"],
            "confidence": detail["confidence"],
            "scores": detail["scores"],
        },
        "text": stored,
        "text_chars": len(stored),
        "raw_chars": int(raw_chars if raw_chars is not None else len(plain)),
        "fetched_at": str(fetched_at or ""),
        "fetch_status": str(fetch_status),
        "source": SOURCE,
        "corpus_version": CORPUS_VERSION,
    }
    if extra:
        record.update(dict(extra))
    return record


# ----------------------------------------------------------------------- I/O
def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL file, skipping blank/malformed lines (resume-friendly)."""
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def load_corpus(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load ``data/edgar_corpus/corpus.jsonl`` (or an explicit path).

    Returns ``[]`` when the corpus has not been built yet - callers should treat
    "no corpus" as a data-status condition, not an error (same honesty rule as
    ``cn_gap``: absence is not zero).
    """
    return read_jsonl(Path(path) if path else DEFAULT_CORPUS_PATH)


def corpus_sha1(records: Sequence[Mapping[str, Any]]) -> str:
    """Deterministic digest of the corpus content (timestamps excluded).

    The digest hashes the canonical JSON of each record **without**
    ``fetched_at`` (wall clock) so re-running the pipeline over the same inputs
    produces the same fingerprint - the reproducibility claim the manifest makes.
    """
    canonical_lines = []
    for record in sorted(records, key=lambda item: str(item.get("accession") or "")):
        payload = {key: value for key, value in record.items() if key != "fetched_at"}
        canonical_lines.append(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    return sha1("\n".join(canonical_lines))


def stratified_subset(
    items: Sequence[Mapping[str, Any]],
    limit: int,
    *,
    key: str = "filed",
) -> list[Mapping[str, Any]]:
    """Deterministic year-stratified subset, used to cap a crawl without bias.

    Fetching the first N candidates would bias the corpus toward the earliest
    years (candidates are sorted by filing date). This allocates ``limit`` slots
    across years proportionally (largest-remainder, at least one per year until
    the budget runs out) and picks **evenly spaced** members inside each year, so
    a capped run still spans 2019-2026.

    Returns ``limit`` items (or all of them when ``limit <= 0`` / ``limit`` is
    larger than the input) sorted by ``(key, accession)`` - deterministic for the
    same input regardless of input order.
    """
    rows = [row for row in items if isinstance(row, Mapping)]
    if limit <= 0 or len(rows) <= limit:
        return list(rows)
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        year = str(row.get(key) or "")[:4] or "unknown"
        groups.setdefault(year, []).append(row)
    for group in groups.values():
        group.sort(key=lambda row: (str(row.get(key) or ""), str(row.get("accession") or "")))
    years = sorted(groups)
    if limit < len(years):
        years = years[:limit]
        quota = {year: 1 for year in years}
    else:
        total = len(rows)
        exact = {year: limit * len(groups[year]) / total for year in years}
        quota = {
            year: min(len(groups[year]), max(1, int(exact[year]))) for year in years
        }
        while sum(quota.values()) > limit:
            reducible = [year for year in years if quota[year] > 1]
            if not reducible:
                break
            year = max(reducible, key=lambda value: (quota[value], -exact[value]))
            quota[year] -= 1
        while sum(quota.values()) < limit:
            expandable = [year for year in years if quota[year] < len(groups[year])]
            if not expandable:
                break
            year = max(expandable, key=lambda value: exact[value] - quota[value])
            quota[year] += 1
    picked: list[Mapping[str, Any]] = []
    for year in years:
        group = groups[year]
        wanted = quota.get(year, 0)
        if wanted >= len(group):
            picked.extend(group)
            continue
        step = len(group) / wanted
        for index in range(wanted):
            picked.append(group[min(len(group) - 1, int(index * step))])
    return sorted(
        picked, key=lambda row: (str(row.get(key) or ""), str(row.get("accession") or ""))
    )


def write_corpus(
    records: Sequence[Mapping[str, Any]], out_dir: str | Path | None = None
) -> dict[str, Any]:
    """Write ``corpus.jsonl`` (stable order) and return paths/counts metadata.

    Records are sorted by ``(filed, accession)`` so a diff between two crawls is
    readable. The JSON is written with ``ensure_ascii=False`` - Chinese notes in
    payloads stay readable, and every record is one physical line.
    """
    target_dir = ensure_dir(Path(out_dir) if out_dir else DEFAULT_CORPUS_DIR)
    ordered = sorted(
        records, key=lambda item: (str(item.get("filed") or ""), str(item.get("accession") or ""))
    )
    path = target_dir / "corpus.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return {
        "path": str(path),
        "n": len(ordered),
        "sha1": corpus_sha1(ordered),
        "text_chars_total": sum(int(record.get("text_chars") or 0) for record in ordered),
    }


def build_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    search: Mapping[str, Any] | None = None,
    fetch: Mapping[str, Any] | None = None,
    window: Mapping[str, str] | None = None,
    buckets: Sequence[str] = BUCKET_ORDER,
    user_agent: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble ``manifest.json``: where the data came from and what is in it.

    Pure function (no I/O) so the same manifest can be regenerated from the
    corpus files and re-verified in tests. Every number the report quotes about
    the corpus must be findable here.
    """
    summary = summarize(records)
    manifest: dict[str, Any] = {
        "schema": "edgar-corpus-manifest-v1",
        "corpus_version": CORPUS_VERSION,
        "generated_at": utc_now_iso(),
        "source": {
            "name": "SEC EDGAR full-text search",
            "fts_endpoint": FTS_ENDPOINT,
            "archives_base": ARCHIVES_BASE,
            "forms": "8-K",
            "user_agent": user_agent or "(not recorded)",
            "max_text_chars": MAX_TEXT_CHARS,
        },
        "window": dict(window or {}),
        "buckets": list(buckets),
        "search": dict(search or {}),
        "fetch": dict(fetch or {}),
        "corpus": {
            "n": summary["n"],
            "sha1": corpus_sha1(records),
            "by_category": summary["by_category"],
            "by_year": summary["by_year"],
            "by_bucket": summary["by_bucket"],
            "date_range": summary["date_range"],
            "avg_text_chars": summary["avg_text_chars"],
            "with_text": summary["with_text"],
            "companies": summary["companies"],
            "tickers": summary["tickers"],
        },
        "notes_zh": [
            "原始 HTML 不入库：只保留清洗后的前 24000 字符纯文本与 EDGAR 直链，可回原文复核。",
            "event_date = 8-K 的 file_date（公开可获知日），无前视偏差。",
            "只收录 healthcare 公司（名称关键词或 SEC SIC 2834/2836/384x 等），按 accession 去重。",
            "分类为短语桶+文本关键词的启发式，可被 case 引擎复核；不是模型判定。",
            "样本按 EDGAR FTS 每窗每桶前 100 条相关性排序，非全量普查。",
        ],
    }
    if extra:
        manifest.update(dict(extra))
    return manifest


# ------------------------------------------------------------------- summaries
def _year_of(filed: Any) -> str:
    text = str(filed or "")
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else "unknown"


def summarize(
    records: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Distributions used by the report/manifest (n, categories, years, buckets...).

    Never raises on malformed records: unknown dates fall into ``"unknown"`` and
    missing text contributes 0 characters. ``failure_rate`` is copied from the
    manifest's ``fetch`` block when supplied because failures are counted at
    crawl time, not in the corpus itself.
    """
    rows = [record for record in records if isinstance(record, Mapping)]
    n = len(rows)
    by_category = Counter(str(record.get("category") or "other") for record in rows)
    by_year = Counter(_year_of(record.get("filed")) for record in rows)
    by_bucket: Counter[str] = Counter()
    for record in rows:
        for bucket in record.get("buckets") or []:
            by_bucket[str(bucket)] += 1
    tickers = {str(record.get("ticker") or "") for record in rows} - {""}
    companies = {str(record.get("company") or "") for record in rows} - {""}
    dates = sorted(
        str(record.get("filed") or "") for record in rows if str(record.get("filed") or "")
    )
    text_chars = [int(record.get("text_chars") or 0) for record in rows]
    with_text = sum(1 for value in text_chars if value > 0)
    payload: dict[str, Any] = {
        "n": n,
        "unique_accessions": len({str(record.get("accession") or "") for record in rows} - {""}),
        "by_category": {category: by_category.get(category, 0) for category in CATEGORIES},
        "by_year": {year: by_year[year] for year in sorted(by_year)},
        "by_bucket": {bucket: by_bucket.get(bucket, 0) for bucket in BUCKET_ORDER},
        "item_202_filings": sum(
            1 for record in rows if ITEM_EARNINGS in {str(item) for item in (record.get("items") or [])}
        ),
        "companies": len(companies),
        "tickers": len(tickers),
        "date_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
        "with_text": with_text,
        "missing_text": n - with_text,
        "avg_text_chars": (sum(text_chars) / n) if n else 0.0,
        "text_chars_total": sum(text_chars),
        "by_direction": {
            str(direction): sum(1 for record in rows if int(record.get("direction") or 0) == direction)
            for direction in (-1, 0, 1)
        },
        "companies_top": Counter(
            str(record.get("company") or "") for record in rows if record.get("company")
        ).most_common(10),
    }
    if manifest:
        fetch = manifest.get("fetch") or {}
        payload["failure_rate"] = fetch.get("failure_rate")
        payload["fetch_failures"] = fetch.get("failed")
    return payload


# --------------------------------------------------------------------- events
def to_events(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Map corpus records to ``events``-table rows (Lead owns the DB write).

    Contract (``docs/SCHEMA.md`` §6): ``event_date`` is the 8-K filing date - the
    earliest public date - and ``event_id`` is the same deterministic hash formula
    as :func:`medradar.db.make_event_id`::

        sha1("|".join([source, kind, *parts]))[:32]

    No DB access here: the integration can upsert the returned dicts with
    ``db.upsert_events`` and stay idempotent, because the id only depends on the
    accession.

    ``title``/``summary`` are short Chinese-labelled strings for the report; the
    full English text stays in the corpus record, not in the events row.
    """
    events: list[dict[str, Any]] = []
    for record in records:
        accession = str(record.get("accession") or "")
        if not accession:
            continue
        filed = str(record.get("filed") or "")
        if not filed:
            continue
        category = str(record.get("category") or "other")
        company = str(record.get("company") or "")
        direction = int(record.get("direction") or 0)
        label = {
            "approval": "获批",
            "crl": "CRL/受挫",
            "trial_result": "试验读出",
            "earnings": "财报",
            "other": "其他",
        }.get(category, "其他")
        events.append(
            {
                "event_id": sha1("|".join([SOURCE, KIND, accession]))[:32],
                "source": SOURCE,
                "kind": KIND,
                "event_date": filed,
                "as_of": str(record.get("fetched_at") or "")[:10],
                "company_key": record.get("company_key") or None,
                "applicant_raw": company,
                "track_id": None,
                "product_code": None,
                "title": f"{company}: {label}（8-K {filed}）",
                "summary": f"category={category} direction={direction} "
                f"buckets={','.join(record.get('buckets') or [])}",
                "url": str(record.get("url") or ""),
                "ticker": str(record.get("ticker") or ""),
                "payload": {
                    "accession": accession,
                    "cik": record.get("cik"),
                    "form": record.get("form"),
                    "document": record.get("document"),
                    "buckets": list(record.get("buckets") or []),
                    "items": list(record.get("items") or []),
                    "category": category,
                    "direction": direction,
                    "classification": record.get("classification"),
                    "text_chars": record.get("text_chars"),
                    "corpus_version": CORPUS_VERSION,
                },
            }
        )
    return events
