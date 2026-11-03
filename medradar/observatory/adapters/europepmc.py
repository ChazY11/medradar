"""Europe PMC adapter — observation of publication metadata (not of science).

Why this source, and what it can never prove
--------------------------------------------
Europe PMC is the public *index* of biomedical literature: a keyless, structured
record of "this paper now exists and says this". It is useful evidence about
observable public output, and it is the one channel where the record itself is
routinely revised (titles, author lists, journal metadata), so an ``UPDATED``
observation means "the index changed its metadata", not "the science changed".

Attribution here is **provisional by construction**. A scope is an affiliation
search (``AFF:"<curated company name>"``); the search engine matches the string,
it does not resolve legal entities. ``map_record`` therefore delegates to
``mapping.europepmc_publication``, which always returns ``PENDING_REVIEW`` and a
note that an affiliation hit is not verified corporate attribution. This module
never upgrades it. It also never infers a company from title similarity: a paper
that merely *sounds* like it is about a firm is not attributed to that firm.

What "time" means here
----------------------
Europe PMC does not publish a web-availability timestamp. The fields that exist
in the API (verified live) are:

* ``firstPublicationDate`` — the journal's first publication date.
* ``firstIndexDate`` — the date the record first entered the Europe PMC/PubMed
  index.
* ``dateOfCreation`` / ``dateOfRevision`` — record creation / metadata revision.
* ``electronicPublicationDate``, ``journalInfo.printPublicationDate``.

Mapping used by this adapter, stated explicitly so no field is silently
reinterpreted:

* ``event_at``         = ``firstPublicationDate`` (precision ``date``).
* ``published_at``     = ``firstIndexDate`` (precision ``date``), with
  ``payload["published_at_source_field"] = "firstIndexDate"``. This is the only
  source-stated "when the record became visible in this index" date; it is an
  *index* date, not a guaranteed instant of web availability, and any lag
  computed from it must be labelled as an index-date lag. When absent,
  ``published_at`` stays ``NULL`` — the publication date is never substituted.
* ``source_updated_at`` = ``dateOfRevision`` (or ``dateUpdated``) when present.

No time of day is invented; ``first_seen_at`` belongs to the ledger and is the
collector's real wall clock.

Incremental collection
----------------------
``resultType=core`` is requested by default because ``lite`` exposes neither
``dateOfRevision`` (needed for ``source_updated_at``) nor an abstract; pass
``result_type="lite"`` for the smaller payload and those two become ``NULL``.
Each scope is one affiliation query, sorted newest-first
(``sort=P_PDATE_D desc``) and paged with Europe PMC's own ``cursorMark``
(``nextCursorMark``). The query window is bounded by ``FIRST_PDATE`` so a run is
small; the per-scope watermark stores the newest metadata date seen plus the 25
most recent stable ids.

Truncation is never silent: when the per-run page ceiling is reached the page
cursor is *not* advanced past what was read — instead the watermark records the
date below which observation is still pending (``pending_upper``) and the next
run continues downward from there. The window bounds and that pending bound are
part of the committed watermark, so the limitation is visible in the ledger.

Honest coverage statement
-------------------------
* The affiliation term is the curated roster ``name_en`` or the curated
  ``FEATURED_COMPANIES`` name, used verbatim; no transliteration, acronym or
  subsidiary alias is invented (e.g. ``Dräger`` is searched as curated, so
  ``Draeger`` spellings may be missed — reported, not patched with a guess).
* One company query does not find every paper of that company, and a hit is not
  proof of employment or funding. Counts from this source are therefore
  *observable indexed mentions*, never "the company's research output".
* Because only recently published/revised records are inside the window, a
  revision to an old record outside the window is not re-checked and cannot
  surface as ``UPDATED``; the ledger never claims it did.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from ...config import load_companies
from ...http import HttpError
from ...product.catalog import FEATURED_COMPANIES
from ...util import parse_date
from ..adapter import CollectContext
from ..mapping import europepmc_publication
from ..records import (
    PRECISION_UNKNOWN,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

SOURCE = "europepmc"
LABEL_ZH = "Europe PMC 文献元数据"
COLLECTOR_VERSION = "europepmc/1.0.0"
RECORD_TYPE = "publication"
RECORD_TYPE_LABELS = {"publication": "文献元数据"}
CADENCE_ZH = (
    "默认每 12 小时轮询；Europe PMC 未提供网页可用时间戳，只能按索引日期与修订日期如实记录；"
    "单位署名检索不等于企业归属，也不覆盖全部论文"
)

API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARTICLE_URL = "https://europepmc.org/article/{source}/{record_id}"
DOI_URL = "https://doi.org/{doi}"
#: Newest first publication date first: the incremental window is bounded by
#: ``FIRST_PDATE``, so a full page means the window itself was not exhausted.
SORT = "P_PDATE_D desc"
#: Only peer-reviewed records and preprints, per the design contract.
SOURCE_FILTER = "(SRC:MED OR SRC:PPR)"
AFFILIATION_TEMPLATE = '(AFF:"{term}") AND ' + SOURCE_FILTER

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
#: First run / catch-up window length of ``FIRST_PDATE``.
DEFAULT_INITIAL_DAYS = 30
#: Re-read a small window behind the watermark so revisions are noticed.
DEFAULT_OVERLAP_DAYS = 7
DEFAULT_MAX_CATCHUP_DAYS = 365
#: Per-run page ceiling (request volume stays small); hitting it is reported and
#: recorded in the watermark as a pending lower observation bound.
DEFAULT_MAX_PAGES = 5
KNOWN_ID_LIMIT = 25
ABSTRACT_SNIPPET_CHARS = 480
RESULT_TYPES = ("core", "lite")

_TAG_RE = re.compile(r"<[^>]+>")
_HTTP_CURSOR_ERRORS = frozenset({400, 404})
#: Source-derived date fields, newest-of which becomes the scope watermark.
_DATE_FIELDS = (
    "firstPublicationDate",
    "firstIndexDate",
    "dateOfCreation",
    "dateOfRevision",
    "dateUpdated",
    "electronicPublicationDate",
)


# --------------------------------------------------------------------------- helpers
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _clean_text(value: Any) -> str:
    """Strip source markup and collapse whitespace (display/abstract only)."""
    text = _TAG_RE.sub(" ", str(value or ""))
    return " ".join(text.split())


def _snippet(value: Any, limit: int = ABSTRACT_SNIPPET_CHARS) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_or_none(value: Any) -> date | None:
    text = str(value or "").strip()
    return parse_date(text) if text else None


def _decode_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _pub_types(result: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    pub_type_list = result.get("pubTypeList")
    if isinstance(pub_type_list, Mapping):
        raw = pub_type_list.get("pubType") or []
        if isinstance(raw, (list, tuple)):
            values.extend(str(item).strip() for item in raw)
        elif raw:
            values.append(str(raw).strip())
    single = result.get("pubType")
    if single:
        values.append(str(single).strip())
    ordered: list[str] = []
    for item in values:
        if item and item not in ordered:
            ordered.append(item)
    return ordered


def _journal_block(result: Mapping[str, Any]) -> dict[str, Any]:
    journal_info = result.get("journalInfo")
    journal_info = journal_info if isinstance(journal_info, Mapping) else {}
    journal = journal_info.get("journal")
    journal = journal if isinstance(journal, Mapping) else {}
    return {
        "title": _text(result.get("journalTitle")) or _text(journal.get("title")),
        "issn": _text(result.get("journalIssn")) or _text(journal.get("issn")),
        "volume": _text(journal_info.get("volume")),
        "issue": _text(journal_info.get("issue")),
        "date_of_publication": _text(journal_info.get("dateOfPublication")),
        "print_publication_date": _text(journal_info.get("printPublicationDate")),
    }


# --------------------------------------------------------------------------- adapter
class EuropePmcAdapter:
    """One observation per stable Europe PMC id, one scope per curated company."""

    source_id = SOURCE
    label_zh = LABEL_ZH
    collector_version = COLLECTOR_VERSION
    declared_cadence_zh = CADENCE_ZH
    record_type_labels = RECORD_TYPE_LABELS

    def __init__(
        self,
        *,
        companies: list[str] | None = None,
        all_companies: bool = False,
        max_companies: int | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        initial_days: int = DEFAULT_INITIAL_DAYS,
        overlap_days: int = DEFAULT_OVERLAP_DAYS,
        max_catchup_days: int = DEFAULT_MAX_CATCHUP_DAYS,
        max_pages: int = DEFAULT_MAX_PAGES,
        result_type: str = "core",
        include_abstract: bool = False,
    ) -> None:
        self.company_filter = [str(key).strip() for key in (companies or []) if str(key).strip()]
        self.all_companies = bool(all_companies)
        self.max_companies = max_companies
        self.page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        self.initial_days = max(1, int(initial_days))
        self.overlap_days = max(0, int(overlap_days))
        self.max_catchup_days = max(1, int(max_catchup_days))
        self.max_pages = max(0, int(max_pages))
        normalised = str(result_type or "core").strip().lower()
        if normalised not in RESULT_TYPES:
            raise ValueError(f"result_type must be one of {RESULT_TYPES}, got {result_type!r}")
        self.result_type = normalised
        self.include_abstract = bool(include_abstract)
        self._session_run: str | None = None
        self._watermarks: dict[str, Any] = {}
        self._known: dict[str, list[str]] = {}
        self._latest: dict[str, date] = {}
        self._pages: dict[str, int] = {}
        self._windows: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ planning
    def _reset_session(self, ctx: CollectContext) -> None:
        """Reload per-scope watermarks once per run (never per page)."""
        if self._session_run == ctx.run_id:
            return
        self._session_run = ctx.run_id
        state = ctx.ledger.get_source_state(SOURCE) or {}
        self._watermarks = _decode_json(state.get("watermark"))
        self._known = {}
        self._latest = {}
        self._pages = {}
        self._windows = {}

    def _candidates(self) -> list[dict[str, Any]]:
        """Curated company names used verbatim as the affiliation search term."""
        roster = {str(company["key"]): company for company in load_companies("device").all()}
        chosen: dict[str, dict[str, Any]] = {}
        for featured in FEATURED_COMPANIES:
            key = str(featured["key"])
            base = roster.get(key) or {}
            base_name = str(base.get("name_en") or "").strip()
            featured_name = str(featured.get("name_en") or "").strip()
            term = base_name or featured_name
            if not term:
                continue
            chosen[key] = {
                "key": key,
                "term": term,
                "term_source": (
                    "config/companies_device.json:name_en"
                    if base_name
                    else "medradar/product/catalog.py:FEATURED_COMPANIES.name_en"
                ),
                "in_roster": key in roster,
            }
        if self.all_companies:
            for key, company in roster.items():
                if key in chosen:
                    continue
                term = str(company.get("name_en") or "").strip()
                if not term:
                    continue
                chosen[key] = {
                    "key": key,
                    "term": term,
                    "term_source": "config/companies_device.json:name_en",
                    "in_roster": True,
                }
        if self.company_filter:
            keep = set(self.company_filter)
            unknown = keep - set(chosen)
            if unknown:
                raise ValueError(
                    "unknown company key(s) for Europe PMC coverage: "
                    + ", ".join(sorted(unknown))
                )
            chosen = {key: value for key, value in chosen.items() if key in keep}
        items = list(chosen.values())
        if self.max_companies:
            items = items[: int(self.max_companies)]
        return items

    def plan(self, ctx: CollectContext) -> list[Scope]:
        self._reset_session(ctx)
        scopes: list[Scope] = []
        for candidate in self._candidates():
            term = candidate["term"]
            scopes.append(
                Scope(
                    scope_id=f"aff:{candidate['key']}:{term}",
                    params={
                        "company_key": candidate["key"],
                        "affiliation_term": term,
                        "affiliation_query": AFFILIATION_TEMPLATE.format(term=term),
                        "term_source": candidate["term_source"],
                    },
                )
            )
        return scopes

    # ----------------------------------------------------------------- fetching
    def _watermark(self, scope: Scope) -> dict[str, Any]:
        value = self._watermarks.get(scope.scope_id)
        return value if isinstance(value, dict) else {}

    def _window(self, scope: Scope, now: datetime) -> dict[str, Any]:
        """Bounded ``FIRST_PDATE`` window, plus an honest note about any clamp."""
        today = now.date()
        floor = today - timedelta(days=self.max_catchup_days)
        notes: list[str] = []
        watermark = self._watermark(scope)
        pending = _date_or_none(watermark.get("pending_upper"))
        latest = _date_or_none(watermark.get("latest_date"))
        continuing = pending is not None and pending >= floor
        if pending is not None and not continuing:
            notes.append(
                f"上次待补窗口 {pending.isoformat()} 早于最多回溯 {self.max_catchup_days} 天，已放弃（未观察部分不再追溯）"
            )
        if continuing:
            upper = min(today, pending)  # type: ignore[arg-type]
            lower = max(floor, upper - timedelta(days=self.initial_days))
            notes.append(f"继续补取上次未取尽的窗口（上界 {upper.isoformat()}）")
        else:
            upper = today
            if latest is not None:
                lower = latest - timedelta(days=self.overlap_days)
            else:
                lower = today - timedelta(days=self.initial_days)
                notes.append(
                    f"首次运行（无水位）：只观察最近 {self.initial_days} 天首次发表的文献，不回填更早历史"
                )
        if lower < floor:
            lower = floor
            notes.append(
                f"增量下界早于最多回溯 {self.max_catchup_days} 天，已截断为 {lower.isoformat()}"
            )
        if lower > upper:
            lower = upper
        return {"lower": lower, "upper": upper, "notes": notes, "continuing": continuing}

    def _window_for(self, scope: Scope, now: datetime) -> dict[str, Any]:
        """The query window is fixed for the whole scope *within one run*.

        Recomputing it from the advancing watermark on every page would move the
        ``FIRST_PDATE`` bounds under an open ``cursorMark``, so the window is
        computed once per scope per run and the cursor stays consistent.
        """
        cached = self._windows.get(scope.scope_id)
        if cached is None:
            cached = self._window(scope, now)
            self._windows[scope.scope_id] = cached
        return cached

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        self._reset_session(ctx)
        base_query = str(scope.params.get("affiliation_query") or "").strip()
        if not base_query:
            raise ValueError(f"scope {scope.scope_id!r} has no affiliation query")
        now = _parse_iso(ctx.now) or _utcnow()
        window = self._window_for(scope, now)
        lower: date = window["lower"]
        upper: date = window["upper"]
        notes: list[str] = list(window["notes"])
        query = f"{base_query} AND (FIRST_PDATE:[{lower.isoformat()} TO {upper.isoformat()}])"
        mark = cursor or "*"
        params: dict[str, Any] = {
            "query": query,
            "format": "json",
            "resultType": self.result_type,
            "pageSize": self.page_size,
            "cursorMark": mark,
            "sort": SORT,
        }
        try:
            payload = ctx.get_json(API_URL, params)
        except HttpError as exc:
            # A cursorMark belongs to one query; a checkpointed mark can be
            # rejected after a new day shifts the window. Restart this window
            # from the first page instead of wedging the scope forever.
            if cursor and int(getattr(exc, "status", 0) or 0) in _HTTP_CURSOR_ERRORS:
                notes.append(f"检查点游标失效（{exc}），本次从该窗口第一页重新开始；已观察记录不会丢失")
                ctx.log(f"[{SOURCE}] cursorMark rejected for scope {scope.scope_id}; restarting the window")
                ctx.ledger.record_failure(
                    SOURCE,
                    kind="HTTP_ERROR",
                    message=(
                        f"checkpoint cursorMark rejected; restarted the window of scope "
                        f"{scope.scope_id} from its first page: {exc}"
                    ),
                    run_id=ctx.run_id,
                    url=API_URL,
                    http_status=int(getattr(exc, "status", 0) or 0),
                    retryable=False,
                )
                params["cursorMark"] = "*"
                payload = ctx.get_json(API_URL, params)
            else:
                raise
        if not isinstance(payload, Mapping):
            raise ValueError(f"Europe PMC returned {type(payload).__name__}, expected a JSON object")
        result_list = payload.get("resultList")
        if result_list is not None and not isinstance(result_list, Mapping):
            raise ValueError("Europe PMC field 'resultList' is not an object")
        results = (result_list or {}).get("result") or []
        if not isinstance(results, list):
            raise ValueError("Europe PMC field 'resultList.result' is not a list")

        records: list[RawRecord] = []
        unidentifiable = 0
        page_max: date | None = None
        page_min_publication: date | None = None
        for result in results:
            if not isinstance(result, Mapping):
                raise ValueError("Europe PMC returned a non-object result entry")
            for field in _DATE_FIELDS:
                value = _date_or_none(result.get(field))
                if value is not None and (page_max is None or value > page_max):
                    page_max = value
            published_value = _date_or_none(result.get("firstPublicationDate")) or _date_or_none(
                result.get("firstIndexDate")
            )
            if published_value is not None and (
                page_min_publication is None or published_value < page_min_publication
            ):
                page_min_publication = published_value
            record = self._to_record(result, scope)
            if record is None:
                unidentifiable += 1
                continue
            records.append(record)

        next_mark = str(payload.get("nextCursorMark") or "").strip() or None
        complete = next_mark is None or next_mark == mark or len(results) < self.page_size
        next_cursor: str | None = None
        truncated = False
        if not complete:
            if self.max_pages and self._pages_of(scope) >= self.max_pages:
                truncated = True
                notes.append(
                    f"已达单次运行页数上限 {self.max_pages} 页：窗口 {lower.isoformat()}..{upper.isoformat()} "
                    f"未取尽（hitCount={payload.get('hitCount')}），剩余记录未观察；"
                    "待补下界已写入水位，下一次运行继续向下取（本次不宣称完整）"
                )
                ctx.log(
                    f"[{SOURCE}] scope {scope.scope_id}: page ceiling {self.max_pages} reached; "
                    "the window is NOT fully observed (pending bound recorded)"
                )
            else:
                next_cursor = next_mark
        if unidentifiable:
            notes.append(f"{unidentifiable} 条文献缺少稳定标识（id/DOI），未写入账本（不伪造标识）")

        self._pages[scope.scope_id] = self._pages.get(scope.scope_id, 0) + 1
        watermark = self._build_watermark(
            scope=scope,
            page_max=page_max,
            page_min_publication=page_min_publication,
            records=records,
            truncated=truncated,
            continuing=bool(window["continuing"]),
            lower=lower,
            upper=upper,
        )
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=watermark,
            structure_sample=self._structure_sample(payload, results),
            note_zh="；".join(notes) if notes else None,
        )

    def _pages_of(self, scope: Scope) -> int:
        """Pages fetched for this scope *including* the page being built."""
        return int(self._pages.get(scope.scope_id, 0)) + 1

    def _build_watermark(
        self,
        *,
        scope: Scope,
        page_max: date | None,
        page_min_publication: date | None,
        records: Sequence[RawRecord],
        truncated: bool,
        continuing: bool,
        lower: date,
        upper: date,
    ) -> dict[str, Any]:
        prior = self._watermark(scope)
        prior_latest = _date_or_none(prior.get("latest_date"))
        running = self._latest.get(scope.scope_id)
        candidates = [value for value in (prior_latest, running, page_max) if value is not None]
        high = max(candidates) if candidates else None
        if high is not None:
            self._latest[scope.scope_id] = high
        known = self._known.setdefault(scope.scope_id, [])
        for record in records:
            if record.source_record_id not in known:
                known.append(record.source_record_id)
        pending_upper: str | None = None
        if truncated:
            if page_min_publication is not None:
                pending_upper = (page_min_publication - timedelta(days=1)).isoformat()
            else:
                # Cannot compute where observation stopped: keep whatever was
                # pending before and do not pretend the window was covered.
                pending_upper = _text(prior.get("pending_upper"))
        elif not continuing:
            pending_upper = None
        watermark = {
            "latest_date": high.isoformat() if high else None,
            "known_ids": known[:KNOWN_ID_LIMIT],
            "pending_upper": pending_upper,
            "window_lower": lower.isoformat(),
            "window_upper": upper.isoformat(),
            "company_key": scope.params.get("company_key"),
            "affiliation_term": scope.params.get("affiliation_term"),
            "affiliation_query": scope.params.get("affiliation_query"),
        }
        self._watermarks[scope.scope_id] = watermark
        return watermark

    @staticmethod
    def _structure_sample(payload: Mapping[str, Any], results: Sequence[Any]) -> dict[str, Any]:
        """Fingerprint the *API envelope*, not one publication's optional fields.

        Europe PMC per-result keys legitimately vary by publication type and source
        (a preprint has no journalInfo; a book chapter has different fields), so
        hashing one result's key set produces false structure alarms. The envelope
        plus the small set of fields the parser always needs is what a real
        contract change would move.
        """
        sample = results[0] if results and isinstance(results[0], Mapping) else {}
        result_list = payload.get("resultList")
        result_list = result_list if isinstance(result_list, Mapping) else {}
        request = payload.get("request")
        request = request if isinstance(request, Mapping) else {}
        return {
            "response_has_result_list": "resultList" in payload,
            "result_list_has_result": "result" in result_list,
            "has_request_echo": bool(request),
            "required_result_fields": {
                name: name in sample
                for name in ("id", "source", "title")
            },
        }

    # ------------------------------------------------------------------- mapping
    def _to_record(self, result: Mapping[str, Any], scope: Scope) -> RawRecord | None:
        record_id = str(result.get("id") or "").strip()
        source_prefix = str(result.get("source") or "").strip().upper()
        doi = str(result.get("doi") or "").strip()
        if record_id and source_prefix:
            source_record_id = f"{source_prefix}:{record_id}"
        elif record_id:
            source_record_id = record_id
        elif doi:
            source_record_id = f"DOI:{doi}"
        else:
            return None
        if record_id and source_prefix:
            url = ARTICLE_URL.format(source=source_prefix, record_id=record_id)
        elif doi:
            url = DOI_URL.format(doi=doi)
        else:
            url = None

        first_publication_raw = _text(result.get("firstPublicationDate"))
        first_index_raw = _text(result.get("firstIndexDate"))
        revision_raw = _text(result.get("dateOfRevision")) or _text(result.get("dateUpdated"))
        event_at, event_precision = (
            normalize_moment(first_publication_raw) if first_publication_raw else (None, PRECISION_UNKNOWN)
        )
        published_at, published_precision = (
            normalize_moment(first_index_raw) if first_index_raw else (None, PRECISION_UNKNOWN)
        )
        source_updated_at, source_updated_precision = (
            normalize_moment(revision_raw) if revision_raw else (None, PRECISION_UNKNOWN)
        )

        title_raw = _text(result.get("title"))
        payload: dict[str, Any] = {
            "source_record_id": source_record_id,
            "europepmc_id": record_id or None,
            "source": source_prefix or None,
            "pmid": _text(result.get("pmid")),
            "pmcid": _text(result.get("pmcid")),
            "doi": doi or None,
            "title": title_raw,
            "author_string": _text(result.get("authorString")),
            "journal": _journal_block(result),
            "pub_year": _text(result.get("pubYear")),
            "pub_types": _pub_types(result),
            "language": _text(result.get("language")),
            "publication_status": _text(result.get("publicationStatus")),
            "first_publication_date": first_publication_raw,
            "first_index_date": first_index_raw,
            "date_of_creation": _text(result.get("dateOfCreation")),
            "date_of_revision": _text(result.get("dateOfRevision")),
            "electronic_publication_date": _text(result.get("electronicPublicationDate")),
            # Which field was used, so no reader has to guess.
            "published_at_source_field": "firstIndexDate" if first_index_raw else None,
        }
        if self.include_abstract:
            payload["abstract_snippet"] = _snippet(result.get("abstractText"))

        display_title = _clean_text(title_raw) or source_record_id
        return RawRecord(
            source=SOURCE,
            source_record_id=source_record_id,
            record_type=RECORD_TYPE,
            title=display_title,
            url=url,
            event_at=event_at,
            event_at_precision=event_precision,
            published_at=published_at,
            published_at_precision=published_precision,
            source_updated_at=source_updated_at,
            source_updated_at_precision=source_updated_precision,
            payload=payload,
            company_hint=_text(scope.params.get("affiliation_term")),
            extra={
                "company_key": scope.params.get("company_key"),
                "affiliation_term": scope.params.get("affiliation_term"),
                "affiliation_query": scope.params.get("affiliation_query"),
            },
        )

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        """Provisional affiliation attribution; never promoted to MAPPED here."""
        extra = record.extra or {}
        return europepmc_publication(
            extra.get("company_key"),
            extra.get("affiliation_query"),
        )

    # ------------------------------------------------------------- failure scope
    def scope_known_ids(self, ctx: CollectContext, scope: Scope) -> list[str]:
        """Observation ids already known for this scope (for ``FETCH_FAILED``)."""
        known: list[str] = []
        for item in self._watermark(scope).get("known_ids") or []:
            text = str(item).strip()
            if text and text not in known:
                known.append(text)
        for item in list(self._known.get(scope.scope_id, [])):
            if item and item not in known:
                known.append(item)
        if not known:
            return []
        ids = ctx.ledger.observation_ids_for(SOURCE, known[:KNOWN_ID_LIMIT])
        return list(ids.values())[:KNOWN_ID_LIMIT]


__all__ = [
    "EuropePmcAdapter",
    "API_URL",
    "AFFILIATION_TEMPLATE",
    "SORT",
    "SOURCE",
    "LABEL_ZH",
]
