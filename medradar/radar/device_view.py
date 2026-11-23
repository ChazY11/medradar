"""One device, its whole public life.

Why this module exists
----------------------
Everything below is already in this repository and none of it was readable in one place:

* 5,258,159 UDI records, each with a labeler DUNS and a model number;
* 40,731 510(k) Summary documents with their sections extracted;
* 24,452 MAUDE failure rows keyed by product code and model;
* NIH awards whose organisation DUNS joins the same spine.

An engineer asking "what is this device, what was it cleared on, what does the filing say it
does, and has it failed" currently has to query four stores and join them by hand. This module
is that join, expressed once.

Design rules it keeps
---------------------
**Every gap names its cause.** A missing section is not the same as a section that does not
exist, and a clearance with no document is not the same as one whose document we failed to
read. Each absence carries a reason from a fixed vocabulary, because "empty" without a cause is
the single most misleading thing an intelligence product can show.

**Attribution is labelled.** A model-exact failure count and a brand-family count are different
claims. They are never added together and never presented as one number.

**No network.** This is a local view over local stores. Fetching belongs to the crawler; a view
that silently made requests would be unreproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Why a piece of the picture is absent. A reader can act on these; "no data" they cannot.
GAP_DOCUMENT_NOT_PUBLISHED = "document_not_published_by_fda"
GAP_DOCUMENT_UNREADABLE = "document_present_but_unreadable"
GAP_SECTION_ABSENT = "section_absent_from_document"
GAP_NOT_IN_INDEX = "device_not_in_udi_register"
GAP_NO_FAILURE_INDEX = "product_code_not_swept"
GAP_NO_FAILURE_MATCH = "no_failure_in_swept_window"
GAP_PATENT_CREDENTIAL = "patent_source_needs_credential"
GAP_NO_PATENT_SOURCE = "patent_bulk_tables_absent"
GAP_NO_PATENT_MATCH = "no_patent_for_this_assignee"
GAP_NO_TRIAL_SOURCE = "trials_table_absent"
GAP_NO_TRIAL_MATCH = "no_trial_for_this_sponsor"

_SECTION_ORDER = (
    "indications", "intended_use", "device_description", "submission_identity",
    "applicant_identity", "device_names", "regulatory_info", "measurand", "test_type",
    "substantial_equivalence", "predicate_comparison", "performance_data", "bench_testing",
    "biocompatibility", "sterilization", "animal_testing", "clinical_data",
    "risks_mitigation", "conclusion",
)


@dataclass
class DeviceRef:
    """One registered device that matched the query."""

    device_key: str
    di: str | None
    brand_name: str | None
    version_or_model: str | None
    catalog_number: str | None
    company_name: str | None
    labeler_duns: str | None
    product_codes: list[str]
    gmdn_name: str | None
    publish_date: str | None
    matched_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_key": self.device_key, "di": self.di, "brand_name": self.brand_name,
            "version_or_model": self.version_or_model, "catalog_number": self.catalog_number,
            "company_name": self.company_name, "labeler_duns": self.labeler_duns,
            "product_codes": self.product_codes, "gmdn_name": self.gmdn_name,
            "publish_date": self.publish_date, "matched_by": self.matched_by,
        }


@dataclass
class DocumentSummary:
    """What the stored 510(k) Summary says, or why it says nothing."""

    submission_number: str
    status: str | None = None
    text_source: str | None = None
    text_chars: int = 0
    sections: dict[str, str] = field(default_factory=dict)
    gap: str | None = None

    def to_dict(self, *, section_chars: int = 1200) -> dict[str, Any]:
        return {
            "submission_number": self.submission_number,
            "status": self.status,
            "text_source": self.text_source,
            "text_chars": self.text_chars,
            "sections": {
                key: value[:section_chars] for key, value in self.sections.items()
            },
            "gap": self.gap,
        }


@dataclass
class FailureHistory:
    """Failure counts for one device, with the strength of the claim spelled out."""

    method: str = "none"                     # model_exact | brand_exact | none
    events: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    matched_on: str | None = None
    gap: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "events": self.events, "by_type": self.by_type,
                "matched_on": self.matched_on, "gap": self.gap}


@dataclass
class PatentHistory:
    """What the bulk patent tables say about this device's owner.

    ``available=False`` means the tables were never imported - a different fact from "the
    assignee holds no patents", and the two must not render the same.
    """

    available: bool = False
    organization: str | None = None
    patents: int = 0
    recent: list[dict[str, Any]] = field(default_factory=list)
    method: str = "none"
    gap: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "organization": self.organization,
                "patents": self.patents, "recent": self.recent[:5],
                "method": self.method, "gap": self.gap}


@dataclass
class TrialHistory:
    """Trials run by this device's company: work in progress rather than a claim made after it."""

    available: bool = False
    sponsor: str | None = None
    trials: int = 0
    recent: list[dict[str, Any]] = field(default_factory=list)
    method: str = "none"
    gap: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "sponsor": self.sponsor, "trials": self.trials,
                "recent": self.recent[:5], "method": self.method, "gap": self.gap}


@dataclass
class DeviceTimeline:
    query: str
    refs: list[DeviceRef] = field(default_factory=list)
    clearances: dict[str, DocumentSummary] = field(default_factory=dict)
    failures: dict[str, FailureHistory] = field(default_factory=dict)
    patents: dict[str, PatentHistory] = field(default_factory=dict)
    trials: dict[str, TrialHistory] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "devices": [ref.to_dict() for ref in self.refs],
            "clearances": {key: value.to_dict() for key, value in self.clearances.items()},
            "failures": {key: value.to_dict() for key, value in self.failures.items()},
            "patents": {key: value.to_dict() for key, value in self.patents.items()},
            "trials": {key: value.to_dict() for key, value in self.trials.items()},
            "gaps": self.gaps,
        }


# ------------------------------------------------------------------ resolution
def resolve(reference, query: str, *, limit: int = 25) -> list[DeviceRef]:
    """Find devices by K number, DI, DUNS, model/catalog number, or company name.

    The match order is deliberate: an exact identifier first, then a model number, then a name.
    A name search that returns 4,000 devices is not an answer, so it is capped and the caller is
    told how many there were.
    """
    text = (query or "").strip()
    if not text:
        return []
    upper = text.upper()
    refs: list[DeviceRef] = []

    def add(rows: Iterable[Mapping[str, Any]], matched_by: str) -> None:
        for row in rows:
            refs.append(_to_ref(row, matched_by))

    if upper.startswith("K") and upper[1:].isdigit():
        add(_rows_for_submission(reference, upper), "submission_number")
    elif upper.isdigit():
        if len(upper) >= 12:
            add(_query(reference, "SELECT * FROM udi_device WHERE di = ? LIMIT ?",
                       (text, limit)), "di")
        if not refs and len(upper) <= 10:
            add(_query(reference, "SELECT * FROM udi_device WHERE labeler_duns = ? LIMIT ?",
                       (text, limit)), "labeler_duns")
    if not refs:
        add(_query(reference,
                   "SELECT * FROM udi_device WHERE version_or_model = ? COLLATE NOCASE LIMIT ?",
                   (text, limit)), "version_or_model")
        add(_query(reference,
                   "SELECT * FROM udi_device WHERE catalog_number = ? COLLATE NOCASE LIMIT ?",
                   (text, limit)), "catalog_number")
    if not refs:
        add(_query(reference,
                   "SELECT * FROM udi_device WHERE brand_name LIKE ? LIMIT ?",
                   (f"%{text}%", limit)), "brand_name")
        add(_query(reference,
                   "SELECT * FROM udi_device WHERE company_name LIKE ? LIMIT ?",
                   (f"%{text}%", limit)), "company_name")

    seen: set[str] = set()
    unique: list[DeviceRef] = []
    for ref in refs:
        if ref.device_key in seen:
            continue
        seen.add(ref.device_key)
        unique.append(ref)
    return unique[:limit]


def _query(reference, sql: str, args: Sequence[Any]) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in reference.conn.execute(sql, args)]
    except Exception:  # noqa: BLE001 - a slim store may lack an optional column
        return []


def _rows_for_submission(reference, k_number: str) -> list[dict[str, Any]]:
    return _query(
        reference,
        """
        SELECT d.* FROM udi_premarket p JOIN udi_device d ON d.device_key = p.device_key
        WHERE p.submission_number = ? LIMIT 100
        """,
        (k_number,),
    )


def _to_ref(row: Mapping[str, Any], matched_by: str) -> DeviceRef:
    codes = row.get("product_codes")
    if isinstance(codes, str):
        try:
            codes = json.loads(codes)
        except ValueError:
            codes = []
    return DeviceRef(
        device_key=str(row.get("device_key") or ""),
        di=row.get("di"), brand_name=row.get("brand_name"),
        version_or_model=row.get("version_or_model"),
        catalog_number=row.get("catalog_number"),
        company_name=row.get("company_name"), labeler_duns=row.get("labeler_duns"),
        product_codes=[str(code) for code in (codes or [])],
        gmdn_name=row.get("gmdn_name"), publish_date=row.get("publish_date"),
        matched_by=matched_by,
    )


# ------------------------------------------------------------------ documents
def _sidecar(corpus_root: str | Path | None, k_number: str) -> dict[str, Any] | None:
    if not corpus_root:
        return None
    path = Path(corpus_root) / f"510k_summary_{k_number}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summarise_document(corpus_root: str | Path | None, k_number: str) -> DocumentSummary:
    """The sections for one clearance, or the reason there are none."""
    payload = _sidecar(corpus_root, k_number)
    if payload is None:
        return DocumentSummary(k_number, gap=GAP_DOCUMENT_NOT_PUBLISHED)
    status = str(payload.get("status") or "")
    if status == "not_published":
        return DocumentSummary(k_number, status=status, gap=GAP_DOCUMENT_NOT_PUBLISHED)
    if status != "text":
        return DocumentSummary(k_number, status=status,
                               gap=GAP_DOCUMENT_UNREADABLE)
    sections = {str(key): str(value) for key, value in (payload.get("sections") or {}).items()}
    if not sections:
        return DocumentSummary(
            k_number, status=status, text_source=payload.get("text_source"),
            text_chars=int(payload.get("text_chars") or 0), gap=GAP_SECTION_ABSENT,
        )
    return DocumentSummary(
        k_number, status=status, text_source=payload.get("text_source"),
        text_chars=int(payload.get("text_chars") or 0), sections=sections,
    )


# ------------------------------------------------------------------- failures
def failure_history(reference, ref: DeviceRef) -> FailureHistory:
    """Model-exact first, then the brand family, and say which one answered."""
    from .failure_index import failures_for_brand, failures_for_model

    for candidate in (ref.version_or_model, ref.catalog_number):
        if not candidate:
            continue
        result = failures_for_model(reference, candidate, product_codes=ref.product_codes or None)
        if result["events"]:
            return FailureHistory(method="model_exact", events=result["events"],
                                  by_type=result["by_type"], matched_on=str(candidate))
    if not ref.product_codes:
        return FailureHistory(gap=GAP_NO_FAILURE_INDEX)
    brand = failures_for_brand(reference, ref.brand_name or "",
                               product_codes=ref.product_codes or None)
    if brand["events"]:
        return FailureHistory(method="brand_exact", events=brand["events"],
                              by_type=brand["by_type"], matched_on=ref.brand_name)
    return FailureHistory(gap=GAP_NO_FAILURE_MATCH)


# ---------------------------------------------------------------------- patents
def patent_history(reference, ref: DeviceRef, *, limit: int = 5) -> PatentHistory:
    """Patents held by this device's company, from the bulk tables if they were imported.

    The company name is tried first, then the brand, because a large group files under the
    subsidiary that makes the device and the disambiguated assignee is usually that subsidiary.
    """
    from .patents_bulk import patents_for_assignee, tables_present

    if not tables_present(reference):
        return PatentHistory(available=False, gap=GAP_NO_PATENT_SOURCE)
    for candidate in (ref.company_name, ref.brand_name):
        if not candidate:
            continue
        result = patents_for_assignee(reference, candidate, limit=limit)
        if result["patents"]:
            return PatentHistory(available=True, organization=str(candidate),
                                 patents=int(result["patents"]), recent=result["recent"],
                                 method=str(result["method"]))
    return PatentHistory(available=True, gap=GAP_NO_PATENT_MATCH)


# ---------------------------------------------------------------------- trials
def trial_history(reference, ref: DeviceRef, *, limit: int = 5) -> TrialHistory:
    """Clinical trials run by this device's company.

    Attached by the sponsor query that fetched the rows, not by string similarity: registry
    sponsors are subsidiaries ("Medtronic - MITG") and a fuzzy join would have produced
    confident nonsense. The full legal name is tried first; if it yields nothing, the group token
    is tried and the answer is labelled as group-level, because it is a weaker claim.
    """
    from .trials import tables_present, trials_for_sponsor

    if not tables_present(reference):
        return TrialHistory(available=False, gap=GAP_NO_TRIAL_SOURCE)
    candidates: list[tuple[str, str]] = []
    for candidate in (ref.company_name, ref.brand_name):
        if candidate:
            candidates.append((str(candidate), "sponsor_query"))
    if ref.company_name:
        first = str(ref.company_name).replace(",", " ").split()
        if first and len(first[0]) >= 5:
            candidates.append((first[0], "sponsor_group"))
    for candidate, method in candidates:
        result = trials_for_sponsor(reference, candidate, limit=limit)
        if result["trials"]:
            return TrialHistory(available=True, sponsor=candidate,
                                trials=int(result["trials"]), recent=result["recent"],
                                method=method)
    return TrialHistory(available=True, gap=GAP_NO_TRIAL_MATCH)


# ---------------------------------------------------------------------- build
def build(reference, query: str, *, corpus_root: str | Path | None = None,
          limit: int = 25, failures: bool = True, patents: bool = True,
          trials: bool = True) -> DeviceTimeline:
    timeline = DeviceTimeline(query=query)
    timeline.refs = resolve(reference, query, limit=limit)
    if not timeline.refs:
        timeline.gaps.append(GAP_NOT_IN_INDEX)
        return timeline

    submissions: set[str] = set()
    for ref in timeline.refs:
        for row in _query(
            reference,
            "SELECT submission_number FROM udi_premarket WHERE device_key = ?",
            (ref.device_key,),
        ):
            number = str(row.get("submission_number") or "").strip().upper()
            if number:
                submissions.add(number)

    for number in sorted(submissions):
        timeline.clearances[number] = summarise_document(corpus_root, number)

    if failures:
        for ref in timeline.refs:
            timeline.failures[ref.device_key] = failure_history(reference, ref)

    if patents:
        for ref in timeline.refs:
            timeline.patents[ref.device_key] = patent_history(reference, ref)

    if trials:
        for ref in timeline.refs:
            timeline.trials[ref.device_key] = trial_history(reference, ref)

    if not submissions:
        timeline.gaps.append("no_clearance_linked_to_this_device")
    if not any(summary.sections for summary in timeline.clearances.values()):
        timeline.gaps.append("no_readable_summary_for_any_clearance")
    # The patent and trial gaps are reported from the data, not asserted: a deployment with the
    # tables imported has answers, and one without them says which source is missing.
    if patents and timeline.patents:
        for state in sorted({h.gap for h in timeline.patents.values() if h.gap}):
            timeline.gaps.append(str(state))
    if trials and timeline.trials:
        for state in sorted({h.gap for h in timeline.trials.values() if h.gap}):
            timeline.gaps.append(str(state))
    return timeline


# --------------------------------------------------------------------- render
def render(timeline: DeviceTimeline, *, section_chars: int = 900,
           max_devices: int = 5) -> str:
    """Human-readable view. Every absence is printed with its reason, never left blank."""
    lines: list[str] = [f"query: {timeline.query}", ""]
    if not timeline.refs:
        lines.append(f"  没有任何设备匹配（{GAP_NOT_IN_INDEX}）")
        return "\n".join(lines)

    lines.append(f"设备 {len(timeline.refs)} 台（按 {timeline.refs[0].matched_by} 匹配）")
    for ref in timeline.refs[:max_devices]:
        header = " · ".join(filter(None, [ref.company_name, ref.brand_name,
                                          ref.version_or_model]))
        lines.append(f"  - {header}")
        detail = [f"DI {ref.di}" if ref.di else None,
                  f"DUNS {ref.labeler_duns}" if ref.labeler_duns else None,
                  f"目录号 {ref.catalog_number}" if ref.catalog_number else None,
                  f"产品码 {','.join(ref.product_codes)}" if ref.product_codes else None]
        if any(detail):
            lines.append("      " + " · ".join(d for d in detail if d))
    if len(timeline.refs) > max_devices:
        lines.append(f"  …另有 {len(timeline.refs) - max_devices} 台")

    lines.append("")
    lines.append("批文与文件")
    if not timeline.clearances:
        lines.append("  （无关联批文）")
    for number, summary in sorted(timeline.clearances.items()):
        if summary.sections:
            source = "OCR 文本" if summary.text_source == "ocr" else "出版方文字层"
            lines.append(f"  {number}  {summary.text_chars:,} 字符（{source}）")
            if summary.text_source == "ocr":
                # Measured on K100175: OCR renders "Grade I" as "Grade |" and "S1" as "$1".
                # Presenting that as the manufacturer's own words without a caveat would be the
                # quiet kind of inaccuracy this project exists to avoid.
                lines.append("      注意：OCR 结果有字符级错误（如 I→|、S1→$1），"
                             "引用前需对照原件")
            for key in _SECTION_ORDER:
                body = summary.sections.get(key)
                if not body:
                    continue
                snippet = " ".join(body.split())[:section_chars]
                lines.append(f"    [{key}] {snippet}")
        else:
            lines.append(f"  {number}  — {summary.gap}")

    lines.append("")
    lines.append("现场失效")
    # A K-number query can resolve to dozens of devices that share one submission. Printing
    # "no failure" once per device buries the one line a reader needs, so the misses are
    # collapsed into a single statement that still names the reason.
    hits = {key: history for key, history in timeline.failures.items() if history.events}
    if hits:
        for key, history in hits.items():
            label = "型号精确" if history.method == "model_exact" else "品牌族（较弱）"
            parts = ", ".join(f"{name} {count:,}"
                              for name, count in sorted(history.by_type.items(),
                                                        key=lambda kv: -kv[1]))
            lines.append(f"  {key}  {label} · 匹配 {history.matched_on} · "
                         f"共 {history.events:,} 条")
            lines.append(f"      {parts}")
        missed = len(timeline.failures) - len(hits)
        if missed:
            lines.append(f"  另 {missed} 台未匹配到失效记录")
    elif timeline.failures:
        reasons = sorted({h.gap for h in timeline.failures.values() if h.gap})
        lines.append(f"  {len(timeline.failures)} 台均未匹配到失效记录"
                     f"（原因：{', '.join(reasons) or 'unknown'}）")

    lines.append("")
    lines.append("专利")
    if not timeline.patents:
        lines.append("  （未查询）")
    else:
        hits = {key: history for key, history in timeline.patents.items()
                if history.available and history.patents}
        if hits:
            for key, history in hits.items():
                lines.append(f"  {key}  受让人「{history.organization}」· 共 {history.patents:,} 件")
                for item in history.recent[:3]:
                    date = item.get("patent_date") or "日期未知"
                    lines.append(f"      {date}  {item.get('patent_id')}  "
                                 f"{(item.get('title') or '')[:70]}")
            missed = len(timeline.patents) - len(hits)
            if missed:
                lines.append(f"  另 {missed} 台未匹配到受让人")
        elif any(history.available for history in timeline.patents.values()):
            lines.append(f"  未匹配到受让人（{GAP_NO_PATENT_MATCH}）")
        else:
            lines.append(f"  专利表未导入（{GAP_NO_PATENT_SOURCE}）")

    lines.append("")
    lines.append("临床试验（在研，不是事后声明）")
    if not timeline.trials:
        lines.append("  （未查询）")
    else:
        trial_hits = {key: history for key, history in timeline.trials.items()
                      if history.available and history.trials}
        if trial_hits:
            for key, history in trial_hits.items():
                level = "集团级" if history.method == "sponsor_group" else "精确"
                lines.append(f"  {key}  申办方「{history.sponsor}」"
                             f"（{level}）· 共 {history.trials:,} 项")
                for item in history.recent[:3]:
                    date = item.get("start_date") or "起始未知"
                    enroll = item.get("enrollment")
                    enroll_text = f"入组 {enroll}" if enroll else "入组未知"
                    lines.append(f"      {date}  {item.get('nct_id')}  "
                                 f"[{item.get('status') or '?'}] "
                                 f"{(item.get('title') or '')[:60]}")
                    extra = " · ".join(filter(None, [
                        (item.get("interventions") or "")[:60] or None, enroll_text]))
                    if extra:
                        lines.append(f"          {extra}")
        elif any(history.available for history in timeline.trials.values()):
            lines.append(f"  未匹配到申办方（{GAP_NO_TRIAL_MATCH}）")
        else:
            lines.append(f"  试验表未导入（{GAP_NO_TRIAL_SOURCE}）")

    if timeline.gaps:
        lines.append("")
        lines.append("缺口（原因明确，不是「没有」）")
        for gap in dict.fromkeys(timeline.gaps):
            lines.append(f"  · {gap}")
    return "\n".join(lines)


__all__ = [
    "DeviceRef",
    "DeviceTimeline",
    "DocumentSummary",
    "FailureHistory",
    "GAP_DOCUMENT_NOT_PUBLISHED",
    "GAP_DOCUMENT_UNREADABLE",
    "GAP_NO_FAILURE_INDEX",
    "GAP_NO_FAILURE_MATCH",
    "GAP_NO_PATENT_MATCH",
    "GAP_NO_PATENT_SOURCE",
    "GAP_NO_TRIAL_MATCH",
    "GAP_NO_TRIAL_SOURCE",
    "GAP_NOT_IN_INDEX",
    "GAP_PATENT_CREDENTIAL",
    "GAP_SECTION_ABSENT",
    "PatentHistory",
    "TrialHistory",
    "build",
    "failure_history",
    "patent_history",
    "render",
    "resolve",
    "summarise_document",
    "trial_history",
]
