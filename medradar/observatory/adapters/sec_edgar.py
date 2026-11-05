"""SEC EDGAR adapter — continuous observation of authoritative US disclosures.

Why EDGAR is the first source
-----------------------------
EDGAR is the only medical-technology channel in this project that publishes a
*real availability timestamp*: ``acceptanceDateTime`` is the instant the filing
became publicly retrievable. That makes the honest latency question —
"how long after the source published this did MedRadar first see it?" — actually
measurable, instead of guessed.

Verified, not assumed, issuer coverage
--------------------------------------
The five firms this project tracks do **not** all file with the SEC:

* Medtronic plc (MDT), GE HealthCare (GEHC) and Koninklijke Philips (PHG, 20-F
  filer) are SEC registrants — CIK resolved from the official
  ``company_tickers.json`` and re-verified against each issuer's own submissions
  document (the CIK's ticker list must contain the ticker we asked for).
* Dräger (XETRA: DRW3) has no SEC registrant entry; an EDGAR company search
  matches only an unrelated individual named Draeger (Form 4 owner).
* Mindray (SZSE: 300760) has *historical* ADR-era filings that stop in 2016
  (15-12B / 25-NSE delisting notifications) and no current registrant.

Those facts are stored per company in ``source_state.entity_coverage`` together
with the evidence that was checked, so "0 filings" can never be misread as
"0 activity" (see ``truthful_zero``).

What this adapter observes
--------------------------
The issuer's official submissions document (``data.sec.gov/submissions``) is a
rolling list of that issuer's most recent filings. Each filing becomes one
observation keyed by accession number (stable, globally unique). Filings are
immutable at the SEC: a correction arrives as a *new accession* (8-K/A), not as
a mutation. The adapter therefore reports ``UPDATED`` only if SEC itself revises
metadata for an already-observed accession — the hash comparison would catch it,
and we do not claim revisions that did not happen.

Deliberately out of scope here: rendering the filing body, LLM interpretation,
strategic inference. A filing is public evidence, not a strategy signal.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ...product.catalog import FEATURED_COMPANIES
from ...util import norm_text, parse_date, token_similarity
from ..adapter import CollectContext
from ..mapping import sec_filing
from ..records import (
    PRECISION_DATE,
    PRECISION_DATETIME,
    PRECISION_UNKNOWN,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

SOURCE = "sec_edgar"
LABEL_ZH = "SEC EDGAR 公开披露"
COLLECTOR_VERSION = "sec-edgar/1.0.0"
CADENCE_ZH = "默认每 6 小时轮询；SEC 受理后通常数分钟即可检索"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_SEARCH_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={query}"
    "&type=&dateb=&owner=include&count=40&output=atom"
)
FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{accession}-index.htm"
)

FORMS: dict[str, str] = {
    "8-K": "8-K 重大事件披露",
    "8-K/A": "8-K 修订披露",
    "6-K": "6-K 外国发行人报告",
    "10-Q": "10-Q 季度报告",
    "10-K": "10-K 年度报告",
    "20-F": "20-F 外国发行人年报",
}

RECORD_TYPE_LABELS = {
    "sec_8k": "8-K 重大事件披露",
    "sec_8ka": "8-K 修订披露",
    "sec_6k": "6-K 外国发行人报告",
    "sec_10q": "10-Q 季度报告",
    "sec_10k": "10-K 年度报告",
    "sec_20f": "20-F 外国发行人年报",
    "sec_other": "其他 SEC 披露",
}

COVERAGE_COVERED = "COVERED"
COVERAGE_NOT_REGISTRANT = "NOT_REGISTRANT"
COVERAGE_NOT_CURRENT = "NOT_CURRENT_REGISTRANT"
COVERAGE_UNVERIFIED = "UNVERIFIED"

DEFAULT_SINCE_DAYS = 30
DEFAULT_PAGE_SIZE = 50
DEFAULT_OVERLAP_HOURS = 6


def _record_type(form: str) -> str:
    mapping = {"8-K": "sec_8k", "8-K/A": "sec_8ka", "6-K": "sec_6k", "10-Q": "sec_10q",
               "10-K": "sec_10k", "20-F": "sec_20f"}
    return mapping.get(form, "sec_other")


def _tz_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class SecEdgarAdapter:
    """One observation per SEC accession, per verified issuer CIK."""

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
        since_days: int = DEFAULT_SINCE_DAYS,
        page_size: int = DEFAULT_PAGE_SIZE,
        overlap_hours: int = DEFAULT_OVERLAP_HOURS,
        max_companies: int | None = None,
    ) -> None:
        self.company_filter = [str(key).strip() for key in (companies or []) if str(key).strip()]
        self.all_companies = bool(all_companies)
        self.since_days = max(1, int(since_days))
        self.page_size = max(1, min(int(page_size), 200))
        self.overlap_hours = max(0, int(overlap_hours))
        self.max_companies = max_companies
        self._session_run: str | None = None
        self._ticker_rows: list[dict[str, Any]] | None = None
        self._ticker_map: dict[str, dict[str, Any]] = {}
        self._docs: dict[str, dict[str, Any]] = {}
        self._coverage: dict[str, dict[str, Any]] = {}
        self._watermarks: dict[str, Any] = {}
        self._searches: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ planning
    def _reset_session(self, ctx: CollectContext) -> None:
        if self._session_run != ctx.run_id:
            self._session_run = ctx.run_id
            self._docs = {}
            self._ticker_rows = None
            self._ticker_map = {}
            state = ctx.ledger.get_source_state(SOURCE) or {}
            self._watermarks = _decode_json(state.get("watermark")) if state else {}

    def _candidates(self) -> list[dict[str, Any]]:
        """Featured firms first, then optionally the whole device roster."""
        from ...config import load_companies

        roster = {company["key"]: company for company in load_companies("device").all()}
        chosen: dict[str, dict[str, Any]] = {}
        for featured in FEATURED_COMPANIES:
            key = featured["key"]
            base = dict(roster.get(key) or {})
            base.update(
                {
                    "key": key,
                    "name_en": featured.get("name_en") or base.get("name_en"),
                    "ticker": featured.get("ticker") or base.get("ticker"),
                    "exchange": featured.get("exchange"),
                    "in_roster": key in roster,
                }
            )
            chosen[key] = base
        if self.all_companies:
            for key, company in roster.items():
                chosen.setdefault(
                    key,
                    {
                        "key": key,
                        "name_en": company.get("name_en"),
                        "ticker": company.get("ticker"),
                        "exchange": None,
                        "in_roster": True,
                    },
                )
        if self.company_filter:
            keep = set(self.company_filter)
            unknown = keep - set(chosen)
            if unknown:
                raise ValueError(f"unknown company key(s) for SEC coverage: {', '.join(sorted(unknown))}")
            chosen = {key: value for key, value in chosen.items() if key in keep}
        items = list(chosen.values())
        if self.max_companies:
            items = items[: self.max_companies]
        return items

    def _load_ticker_map(self, ctx: CollectContext) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if self._ticker_rows is not None:
            return self._ticker_rows, self._ticker_map
        payload = ctx.get_json(TICKERS_URL)
        rows: list[dict[str, Any]] = []
        index: dict[str, dict[str, Any]] = {}
        if isinstance(payload, Mapping):
            for value in payload.values():
                if not isinstance(value, Mapping):
                    continue
                ticker = str(value.get("ticker") or "").upper()
                if not ticker or value.get("cik_str") is None:
                    continue
                row = {
                    "ticker": ticker,
                    "cik": f"{int(value['cik_str']):010d}",
                    "title": str(value.get("title") or ""),
                }
                rows.append(row)
                index.setdefault(ticker, row)
        if not rows:
            raise ValueError("SEC company_tickers.json returned no usable rows")
        self._ticker_rows = rows
        self._ticker_map = index
        return rows, index

    def _search_company(self, ctx: CollectContext, query: str) -> dict[str, Any]:
        """EDGAR company search, used only to *verify absence* of a registrant.

        The Atom feed exposes a ``<company-info>`` block when EDGAR matched an
        actual filer; a no-match feed contains only a generic title. Treating
        those two cases the same is exactly how a "0 filings" claim turns into a
        false statement, so they are separated here.
        """
        import urllib.parse

        attempts = [query]
        ascii_query = _ascii_transliterate(query)
        if ascii_query and ascii_query != query:
            attempts.append(ascii_query)
        last: dict[str, Any] = {"ok": False, "error": "no attempt", "entries": []}
        for attempt in attempts:
            url = COMPANY_SEARCH_URL.format(query=urllib.parse.quote(attempt, safe=""))
            try:
                text = ctx.fetcher.get_text(url, refresh=not ctx.offline)
            except Exception as exc:  # noqa: BLE001 - coverage check is best effort but recorded
                last = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "entries": []}
                continue
            matched = "<company-info>" in text
            conformed = [item.strip() for item in re.findall(r"<conformed-name>(.*?)</conformed-name>", text, flags=re.S)]
            ciks = [item.strip() for item in re.findall(r"<cik>(\d+)</cik>", text, flags=re.S)]
            dates = [item.strip() for item in re.findall(r"<filing-date>(.*?)</filing-date>", text, flags=re.S)]
            titles = [
                item.strip()
                for item in re.findall(r"<title>(.*?)</title>", text, flags=re.S)
                if item.strip() and item.strip() != "Company Search Feed"
            ]
            result = {
                "ok": True,
                "matched_feed": matched,
                "conformed_names": conformed,
                "ciks": ciks,
                "entries": titles[:40],
                "filing_dates": dates,
                "url": url,
                "query_used": attempt,
            }
            if matched:
                return result
            last = result
        return last

    def _resolve_coverage(self, ctx: CollectContext, candidate: Mapping[str, Any]) -> dict[str, Any]:
        key = str(candidate.get("key"))
        name = str(candidate.get("name_en") or key)
        ticker = str(candidate.get("ticker") or "").upper()
        _, index = self._load_ticker_map(ctx)
        hit = index.get(ticker) if ticker else None
        if hit and not _title_matches(name, hit["title"]):
            return {
                "entity_id": key,
                "name": name,
                "ticker": ticker,
                "status": COVERAGE_UNVERIFIED,
                "identifier": f"CIK {hit['cik']}",
                "cik": None,
                "evidence_zh": (
                    f"ticker {ticker} 在 SEC 官方列表对应 CIK {hit['cik']}"
                    f"（{hit['title']}），与名册名称 {name!r} 不一致；未确认前不据该 CIK 断言企业披露"
                ),
                "search_sample": [],
                "latest_historical_filing": None,
                "truthful_zero_zh": "状态为未核验：既不能断言有披露，也不能断言没有披露",
            }
        if hit:
            return {
                "entity_id": key,
                "name": name,
                "ticker": ticker,
                "status": COVERAGE_COVERED,
                "identifier": f"CIK {hit['cik']}",
                "cik": hit["cik"],
                "evidence_zh": (
                    f"SEC 官方 company_tickers.json 中 {ticker} → CIK {hit['cik']}"
                    f"（{hit['title']}），并在该 CIK 的官方 submissions 文件中复核了 ticker 列表"
                ),
                "truthful_zero_zh": None,
            }
        search = self._search_company(ctx, name)
        recent_cutoff = _now_minus_days(ctx, 24 * 30)
        dated = []
        for value in search.get("filing_dates", []):
            parsed = parse_date(value)
            if parsed:
                dated.append(parsed)
        has_recent = any(day >= recent_cutoff.date() for day in dated)
        conformed = ", ".join(search.get("conformed_names") or []) or "（未返回主体名）"
        ciks = ", ".join(search.get("ciks") or []) or "（未返回 CIK）"
        sample = "；".join((search.get("entries") or [])[:3])
        if not search.get("ok"):
            status = COVERAGE_UNVERIFIED
            evidence = f"无法完成 SEC 公司检索核验（{search.get('error')}）；不得据此判断无披露"
        elif not search.get("matched_feed"):
            status = COVERAGE_NOT_REGISTRANT
            evidence = (
                f"SEC 官方 ticker 列表中没有 {ticker or name}；EDGAR 公司检索（{search.get('query_used')!r}）"
                "没有匹配到任何申报主体。该企业不是 SEC 发行人，因此不存在 8-K 类披露。"
            )
        elif has_recent:
            status = COVERAGE_UNVERIFIED
            evidence = (
                f"EDGAR 公司检索匹配到申报主体 {conformed}（CIK {ciks}），且存在近期申报；"
                f"但官方 ticker 列表中没有 {ticker}；主体归属需人工确认，暂不宣称覆盖。样例：{sample}"
            )
        else:
            status = COVERAGE_NOT_CURRENT
            evidence = (
                f"EDGAR 公司检索匹配到的申报主体为 {conformed}（CIK {ciks}），"
                f"最近申报日期 {max(dated).isoformat() if dated else '未知'}，且官方 ticker 列表中没有 {ticker}；"
                f"该企业目前没有持续的 SEC 披露，历史记录不在本轮实时观察范围内。样例：{sample}"
            )
        return {
            "entity_id": key,
            "name": name,
            "ticker": ticker or None,
            "status": status,
            "identifier": None,
            "cik": None,
            "evidence_zh": evidence,
            "search_sample": search.get("entries", [])[:5],
            "latest_historical_filing": max(dated).isoformat() if dated else None,
            "truthful_zero_zh": (
                "此状态表示 SEC 渠道没有该企业的当前披露，不代表该企业没有产品、销售或研发活动；"
                "其他数据源（ClinicalTrials.gov / Europe PMC）独立观察"
            ),
        }

    def plan(self, ctx: CollectContext) -> list[Scope]:
        self._reset_session(ctx)
        candidates = self._candidates()
        self._coverage = {}
        scopes: list[Scope] = []
        for candidate in candidates:
            coverage = self._resolve_coverage(ctx, candidate)
            self._coverage[coverage["entity_id"]] = coverage
            if coverage["status"] == COVERAGE_COVERED and coverage.get("cik"):
                scopes.append(
                    Scope(
                        scope_id=f"cik:{coverage['cik']}",
                        params={
                            "cik": coverage["cik"],
                            "ticker": coverage["ticker"],
                            "company_key": coverage["entity_id"],
                            "name": coverage["name"],
                        },
                    )
                )
        ctx.ledger.set_entity_coverage(SOURCE, list(self._coverage.values()))
        return scopes

    # ----------------------------------------------------------------- fetching
    def _watermark_for(self, scope: Scope) -> dict[str, Any]:
        value = self._watermarks.get(scope.scope_id)
        return value if isinstance(value, dict) else {}

    def _doc_for(self, ctx: CollectContext, scope: Scope) -> dict[str, Any]:
        cik = str(scope.params["cik"])
        cached = self._docs.get(cik)
        if cached is not None:
            return cached
        payload = ctx.get_json(SUBMISSIONS_URL.format(cik=cik))
        if not isinstance(payload, Mapping):
            raise ValueError(f"SEC submissions for CIK {cik} is not a JSON object")
        tickers = [str(item).upper() for item in (payload.get("tickers") or [])]
        expected = str(scope.params.get("ticker") or "").upper()
        if expected and tickers and expected not in tickers:
            raise ValueError(
                f"CIK {cik} tickers {tickers} do not include expected {expected}; refusing to attribute"
            )
        self._docs[cik] = dict(payload)
        return self._docs[cik]

    def _recent_filings(self, doc: Mapping[str, Any]) -> list[dict[str, Any]]:
        filings = doc.get("filings") or {}
        recent = filings.get("recent") or {}
        columns = {key: value for key, value in recent.items() if isinstance(value, list)}
        if not columns:
            return []
        length = min(len(value) for value in columns.values())
        return [{key: value[i] for key, value in columns.items()} for i in range(length)]

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        doc = self._doc_for(ctx, scope)
        filings = self._recent_filings(doc)
        watermark = self._watermark_for(scope)
        now = _parse_iso(ctx.now) or datetime.now(timezone.utc)
        lower: datetime
        if watermark.get("acceptance"):
            base = _tz_utc(watermark["acceptance"])
            lower = (base - timedelta(hours=self.overlap_hours)) if base else now - timedelta(days=self.since_days)
        else:
            lower = now - timedelta(days=self.since_days)

        selected: list[dict[str, Any]] = []
        max_acceptance: datetime | None = None
        for filing in filings:
            form = str(filing.get("form") or "")
            accepted = _tz_utc(filing.get("acceptanceDateTime"))
            if form not in FORMS or accepted is None:
                continue
            if accepted < lower:
                continue
            selected.append(filing)
            if max_acceptance is None or accepted > max_acceptance:
                max_acceptance = accepted
        selected.sort(key=lambda row: (_tz_utc(row.get("acceptanceDateTime")) or now, row.get("accessionNumber") or ""), reverse=True)

        offset = int(cursor) if cursor and str(cursor).isdigit() else 0
        window = selected[offset : offset + self.page_size]
        next_cursor = (
            str(offset + self.page_size) if offset + self.page_size < len(selected) else None
        )
        records = [
            self._to_record(filing, scope) for filing in window
        ]
        known_ids = [str(row.get("accessionNumber")) for row in selected[:25] if row.get("accessionNumber")]
        # The watermark may only advance once the whole scope has been processed;
        # advancing it mid-scope would skip the pages that were not read yet. It is
        # also scoped to *observed* filings: the newest insider Form 4 must not push
        # the cursor past an 8-K we never looked at.
        new_watermark = None
        if next_cursor is None:
            new_watermark = {
                "acceptance": (max_acceptance or _tz_utc(watermark.get("acceptance"))).isoformat()
                if (max_acceptance or watermark.get("acceptance"))
                else None,
                "known_ids": known_ids,
                "ticker": scope.params.get("ticker"),
            }
        structure_sample = {
            "document_keys": sorted(str(key) for key in doc.keys()),
            "filings_keys": sorted(str(key) for key in (doc.get("filings") or {}).keys()),
            "recent_keys": sorted(
                str(key) for key in ((doc.get("filings") or {}).get("recent") or {}).keys()
            ),
            "sample_filing_keys": sorted(str(key) for key in (window[0].keys() if window else [])),
        }
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=new_watermark,
            structure_sample=structure_sample,
        )

    def _to_record(self, filing: Mapping[str, Any], scope: Scope) -> RawRecord:
        accession = str(filing.get("accessionNumber") or "").strip()
        form = str(filing.get("form") or "").strip()
        cik = str(scope.params["cik"])
        cik_int = str(int(cik)) if cik.isdigit() else cik
        accession_nodash = accession.replace("-", "")
        primary_document = str(filing.get("primaryDocument") or "")
        url = (
            FILING_INDEX_URL.format(cik_int=cik_int, accession_nodash=accession_nodash, accession=accession)
            if accession
            else None
        )
        filing_date = str(filing.get("filingDate") or "")
        acceptance = filing.get("acceptanceDateTime")
        accepted_value, accepted_precision = (
            normalize_moment(acceptance) if acceptance else (None, PRECISION_UNKNOWN)
        )
        items = str(filing.get("items") or "").strip()
        issuer = str(scope.params.get("name") or "")
        type_key = _record_type(form)
        title_bits = [form or "SEC 披露"]
        if items:
            title_bits.append(f"Item {items}")
        title_bits.append(f"{issuer}，{filing_date} 提交")
        payload = {
            "accession_number": accession,
            "form": form,
            "filing_date": filing_date or None,
            "report_date": filing.get("reportDate") or None,
            "acceptance_datetime": str(acceptance) if acceptance else None,
            "items": items or None,
            "primary_document": primary_document or None,
            "primary_doc_description": filing.get("primaryDocDescription") or None,
            "file_number": filing.get("fileNumber") or None,
            "film_number": filing.get("filmNumber") or None,
            "act": filing.get("act") or None,
            "size": filing.get("size") or None,
            "is_xbrl": bool(filing.get("isXBRL")) if filing.get("isXBRL") is not None else None,
            "is_inline_xbrl": bool(filing.get("isInlineXBRL"))
            if filing.get("isInlineXBRL") is not None
            else None,
            "cik": cik,
        }
        return RawRecord(
            source=SOURCE,
            source_record_id=accession,
            record_type=type_key,
            title="｜".join(title_bits),
            url=url,
            event_at=filing_date or None,
            event_at_precision=PRECISION_DATE if filing_date else PRECISION_UNKNOWN,
            published_at=accepted_value,
            published_at_precision=accepted_precision,
            source_updated_at=None,
            source_updated_at_precision=PRECISION_UNKNOWN,
            payload=payload,
            company_hint=issuer,
            extra={"cik": cik, "ticker": scope.params.get("ticker"),
                   "company_key": scope.params.get("company_key")},
        )

    # -------------------------------------------------------------- attribution
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        extra = record.extra or {}
        return sec_filing(
            extra.get("company_key"),
            record.company_hint,
            extra.get("cik"),
        )

    # ------------------------------------------------------------- failure scope
    def scope_known_ids(self, ctx: CollectContext, scope: Scope) -> list[str]:
        """Record ids we already observed for this scope (for FETCH_FAILED marks)."""
        watermark = self._watermark_for(scope)
        known = [str(item) for item in (watermark.get("known_ids") or []) if item]
        if not known:
            return []
        ids = ctx.ledger.observation_ids_for(SOURCE, known)
        return list(ids.values())[:25]


_TRANSLIT = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "ê": "e",
    "á": "a", "à": "a", "å": "a", "ø": "o", "æ": "ae", "ç": "c", "ñ": "n",
    "ô": "o", "î": "i", "í": "i", "ó": "o", "ú": "u", "å": "a",
}


def _ascii_transliterate(text: str) -> str:
    """ASCII fallback for names like Dräger, so an EDGAR search URL is legal."""
    out: list[str] = []
    for character in text:
        low = character.lower()
        if low in _TRANSLIT:
            replacement = _TRANSLIT[low]
            out.append(replacement.capitalize() if character.isupper() else replacement)
        else:
            out.append(character)
    return "".join(out).encode("ascii", "ignore").decode("ascii")


def _title_matches(name: str, title: str) -> bool:
    if not name or not title:
        return False
    left = norm_text(name).replace(" ", "")
    right = norm_text(title).replace(" ", "")
    if left and left in right:
        return True
    return token_similarity(name, title) >= 0.5


def _now_minus_days(ctx: CollectContext, days: int) -> datetime:
    base = _parse_iso(ctx.now) or datetime.now(timezone.utc)
    return base - timedelta(days=days)


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _decode_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    except (TypeError, ValueError):
        return {}


__all__ = [
    "SecEdgarAdapter",
    "COVERAGE_COVERED",
    "COVERAGE_NOT_CURRENT",
    "COVERAGE_NOT_REGISTRANT",
    "COVERAGE_UNVERIFIED",
]
