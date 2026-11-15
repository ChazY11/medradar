"""Scoped collection with explicit pagination, partitioning and coverage evidence.

The product's scope is the reviewed organization roster. For every organization and
official endpoint we make the same query the legacy collector made, then record:

* the exact search expression (without credentials);
* the official reported total for that query;
* pages, partitions and every pagination skip used;
* how many records were returned;
* whether the query was complete.

If an openFDA query can return more than the 25,000-record skip window, it is split by
the source's own date field. A failure in any partition aborts the collection; a partial
sweep is never allowed to become a candidate snapshot.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Sequence

from .model import SOURCES, SourceSpec
from .normalize import (
    build_classifications,
    content_hash,
    normalise_record,
)
from .openfda import FetchResult, OpenFDAError, OpenFDAClient

PAGE_LIMIT = 1000
MAX_SKIP = 25000
MAX_RECORDS_PER_QUERY = MAX_SKIP + PAGE_LIMIT
MAX_PARTITION_DEPTH = 2


class CollectionError(RuntimeError):
    def __init__(self, message: str, *, audit: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.audit = audit or {}


@dataclass
class SourceCollection:
    source_id: str
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    audits: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    response_bytes: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AllCollection:
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    classifications: list[dict[str, Any]] = field(default_factory=list)
    source_audits: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    classification_audit: dict[str, Any] = field(default_factory=dict)
    requests: int = 0
    response_bytes: int = 0
    requests_by_source: dict[str, int] = field(default_factory=dict)
    bytes_by_source: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _quote(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def scope_expression(field: str, tokens: Sequence[str]) -> str:
    return field + ":(" + " OR ".join(_quote(token) for token in tokens) + ")"


def date_expression(field: str, start: str, end: str) -> str:
    return field + ":[" + start + " TO " + end + "]"


def _params(search: str | None, skip: int, limit: int = PAGE_LIMIT, sort: str | None = None) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    if search:
        params.append(("search", search))
    if sort:
        params.append(("sort", sort))
    params.append(("limit", str(limit)))
    params.append(("skip", str(skip)))
    return params


class Collector:
    def __init__(
        self,
        client: OpenFDAClient,
        *,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.progress = progress or (lambda _message: None)
        self._request_count = 0
        self._response_bytes = 0

    def _fetch(self, source: SourceSpec, params: list[tuple[str, str]], context: str) -> FetchResult:
        result = self.client.fetch_page(source.endpoint, params, source_id=source.source_id, context=context)
        self._request_count += 1
        self._response_bytes += result.bytes
        return result

    def _total(self, result: FetchResult) -> int:
        meta = result.data.get("meta") or {}
        results = meta.get("results") or {}
        try:
            return int(results.get("total") or 0)
        except (TypeError, ValueError):
            return 0

    def _date_bounds(self, source: SourceSpec, search: str) -> tuple[str, str] | None:
        if not source.date_field:
            return None
        try:
            first = self._fetch(
                source,
                _params(search, 0, 1, sort=source.date_field + ":asc"),
                "date lower bound " + source.source_id,
            )
            last = self._fetch(
                source,
                _params(search, 0, 1, sort=source.date_field + ":desc"),
                "date upper bound " + source.source_id,
            )
        except OpenFDAError:
            return None
        first_results = first.data.get("results") or []
        last_results = last.data.get("results") or []
        if not first_results or not last_results:
            return None
        start = str((first_results[0] or {}).get(source.date_field) or "")[:10]
        end = str((last_results[0] or {}).get(source.date_field) or "")[:10]
        if not start or not end:
            return None
        try:
            date.fromisoformat(start)
            date.fromisoformat(end)
        except ValueError:
            return None
        return start, end

    @staticmethod
    def _month_windows(start: str, end: str) -> list[tuple[str, str]]:
        first = date.fromisoformat(start[:10])
        last = date.fromisoformat(end[:10])
        windows: list[tuple[str, str]] = []
        cursor = date(first.year, first.month, 1)
        while cursor <= last:
            if cursor.month == 12:
                next_month = date(cursor.year + 1, 1, 1)
            else:
                next_month = date(cursor.year, cursor.month + 1, 1)
            window_start = max(first, cursor)
            window_end = min(last, date.fromordinal(next_month.toordinal() - 1))
            if window_start <= window_end:
                windows.append((window_start.isoformat(), window_end.isoformat()))
            cursor = next_month
        return windows

    @staticmethod
    def _year_windows(start: str, end: str) -> list[tuple[str, str]]:
        first = date.fromisoformat(start[:10])
        last = date.fromisoformat(end[:10])
        windows: list[tuple[str, str]] = []
        for year in range(first.year, last.year + 1):
            window_start = max(first, date(year, 1, 1))
            window_end = min(last, date(year, 12, 31))
            if window_start <= window_end:
                windows.append((window_start.isoformat(), window_end.isoformat()))
        return windows

    def _fetch_pages(
        self,
        source: SourceSpec,
        search: str,
        audit: dict[str, Any],
        *,
        context: str,
        depth: int = 0,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Fetch one query window. Returns (normalised records, raw count, reported total)."""
        if depth > MAX_PARTITION_DEPTH:
            raise CollectionError("pagination window still too large after " + str(MAX_PARTITION_DEPTH) + " partitions", audit=audit)
        first = self._fetch(source, _params(search, 0), context + " page 1")
        total = self._total(first)
        if first.empty or total == 0:
            audit["partitions"].append({"search": search, "skip": 0, "total": 0, "pages": 0, "depth": depth})
            return [], 0, 0
        if total > MAX_RECORDS_PER_QUERY and source.date_field and depth < MAX_PARTITION_DEPTH:
            bounds = self._date_bounds(source, search)
            if bounds is None:
                raise CollectionError(
                    "query returns " + str(total) + " records, above the openFDA skip window, and no date bounds were available",
                    audit=audit,
                )
            windows = self._year_windows(*bounds) if depth == 0 else self._month_windows(*bounds)
            records: list[dict[str, Any]] = []
            raw_count = 0
            window_total = 0
            for window_start, window_end in windows:
                window_search = "(" + search + ") AND " + date_expression(source.date_field, window_start, window_end)
                part_records, part_raw, part_total = self._fetch_pages(
                    source, window_search, audit, context=context + " " + window_start + ".." + window_end, depth=depth + 1
                )
                records.extend(part_records)
                raw_count += part_raw
                window_total += part_total
            return records, raw_count, window_total

        records: list[dict[str, Any]] = []
        raw_count = 0
        pages = 0
        skip = 0
        while True:
            if pages == 0:
                result = first
            else:
                result = self._fetch(source, _params(search, skip), context + " page " + str(pages + 1))
            page_total = self._total(result)
            if page_total != total:
                raise CollectionError(
                    "official total changed during a paginated query ("
                    + str(total)
                    + " -> "
                    + str(page_total)
                    + "); refusing a partial sweep",
                    audit=audit,
                )
            rows = result.data.get("results") or []
            pages += 1
            raw_count += len(rows)
            for record in rows:
                if not isinstance(record, dict):
                    continue
                normalised = normalise_record(source.source_id, record)
                normalised["content_hash"] = content_hash(normalised)
                records.append(normalised)
            audit["urls"].append(result.url)
            if raw_count >= total:
                break
            if not rows:
                raise CollectionError(
                    "official total says " + str(total) + " records but the API returned an empty page at skip " + str(skip),
                    audit=audit,
                )
            if skip + PAGE_LIMIT > MAX_SKIP:
                raise CollectionError(
                    "query reached the openFDA skip ceiling before the reported total",
                    audit=audit,
                )
            skip += PAGE_LIMIT
        audit["partitions"].append({
            "search": search,
            "skip": skip,
            "total": total,
            "pages": pages,
            "depth": depth,
        })
        return records, raw_count, total

    def _collect_query(self, source: SourceSpec, org_key: str, tokens: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        search = scope_expression(source.scope_field or "applicant", tokens)
        audit: dict[str, Any] = {
            "source_id": source.source_id,
            "org_key": org_key,
            "field": source.scope_field,
            "query": search,
            "tokens": list(tokens),
            "pages": 0,
            "reported_total": 0,
            "records": 0,
            "unique_records": 0,
            "duplicates": 0,
            "complete": False,
            "partitions": [],
            "urls": [],
            "errors": [],
        }
        try:
            records, raw_count, reported_total = self._fetch_pages(
                source, search, audit, context=source.source_id + "/" + org_key
            )
        except CollectionError as error:
            audit["errors"].append({"type": "collection", "message": str(error)})
            raise
        except OpenFDAError as error:
            audit["errors"].append({"type": "http", "message": str(error), "status": error.status})
            raise CollectionError(str(error), audit=audit) from error
        unique: dict[str, dict[str, Any]] = {}
        duplicates = 0
        for event in records:
            existing = unique.get(event["event_id"])
            if existing is not None:
                duplicates += 1
                if existing["content_hash"] != event["content_hash"]:
                    raise CollectionError(
                        "the official endpoint returned two different payloads for " + event["event_id"]
                        + " within one query",
                        audit=audit,
                    )
                continue
            unique[event["event_id"]] = event
        audit.update({
            "pages": sum(int(part["pages"]) for part in audit["partitions"]),
            "reported_total": reported_total,
            "records": raw_count,
            "unique_records": len(unique),
            "duplicates": duplicates,
            "complete": raw_count >= reported_total and not audit["errors"],
        })
        audit["urls"] = audit["urls"][:3]
        return list(unique.values()), audit

    def collect_source(self, source_id: str, organizations: Sequence[dict[str, Any]]) -> SourceCollection:
        source = SOURCES[source_id]
        if source.is_support_source or source.scope_field is None:
            raise ValueError(source_id + " is not a scoped product source")
        start_requests = self._request_count
        start_bytes = self._response_bytes
        result = SourceCollection(source_id=source_id)
        for index, org in enumerate(organizations, 1):
            org_key = str(org.get("key") or "")
            tokens = [str(token) for token in (org.get("search_tokens") or []) if str(token).strip()]
            if not tokens:
                result.audits.append({
                    "source_id": source_id,
                    "org_key": org_key,
                    "query": "",
                    "tokens": [],
                    "pages": 0,
                    "reported_total": 0,
                    "records": 0,
                    "unique_records": 0,
                    "duplicates": 0,
                    "complete": True,
                    "partitions": [],
                    "urls": [],
                    "errors": [{"type": "scope", "message": "no search tokens configured"}],
                })
                continue
            self.progress("  [" + str(index) + "/" + str(len(organizations)) + "] " + org_key + " / " + source_id)
            try:
                records, audit = self._collect_query(source, org_key, tokens)
            except CollectionError as error:
                error.audit["complete"] = False
                result.audits.append(error.audit)
                result.errors.append({"source_id": source_id, "org_key": org_key, "message": str(error)})
                raise
            for event in records:
                existing = result.events.get(event["event_id"])
                if existing is None:
                    event["collection_scopes"] = [org_key]
                    result.events[event["event_id"]] = event
                else:
                    if existing["content_hash"] != event["content_hash"]:
                        raise CollectionError(
                            "the official endpoint returned inconsistent payloads for "
                            + event["event_id"]
                            + " across organization scopes"
                        )
                    scopes = set(existing.get("collection_scopes") or [])
                    scopes.add(org_key)
                    existing["collection_scopes"] = sorted(scopes)
            result.audits.append(audit)
            self.progress("      " + str(audit["unique_records"]) + " records / " + str(audit["pages"]) + " pages")
        result.requests = self._request_count - start_requests
        result.response_bytes = self._response_bytes - start_bytes
        return result

    def collect_classifications(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        source = SOURCES["openfda_classification"]
        start_requests = self._request_count
        start_bytes = self._response_bytes
        audit: dict[str, Any] = {
            "source_id": source.source_id,
            "pages": 0,
            "reported_total": 0,
            "records": 0,
            "complete": False,
            "partitions": [],
            "urls": [],
            "errors": [],
        }
        raw: list[dict[str, Any]] = []
        first = self._fetch(source, _params(None, 0), "classification page 1")
        total = self._total(first)
        pages = 0
        skip = 0
        while True:
            result = first if pages == 0 else self._fetch(source, _params(None, skip), "classification page " + str(pages + 1))
            if self._total(result) != total:
                raise CollectionError("classification total changed during pagination", audit=audit)
            rows = result.data.get("results") or []
            pages += 1
            raw.extend(row for row in rows if isinstance(row, dict))
            audit["urls"].append(result.url)
            if len(raw) >= total:
                break
            if not rows:
                raise CollectionError("classification query returned an empty page before its reported total", audit=audit)
            if skip + PAGE_LIMIT > MAX_SKIP:
                raise CollectionError("classification query reached the skip ceiling", audit=audit)
            skip += PAGE_LIMIT
        audit["pages"] = pages
        audit["reported_total"] = total
        audit["records"] = len(raw)
        audit["complete"] = len(raw) >= total
        meta = first.data.get("meta") or {}
        audit["official_last_updated"] = meta.get("last_updated")
        audit["official_total"] = total
        audit["urls"] = audit["urls"][:3]
        audit["requests"] = self._request_count - start_requests
        audit["response_bytes"] = self._response_bytes - start_bytes
        return build_classifications(raw), audit

    def collect_all(self, source_ids: Sequence[str], organizations: Sequence[dict[str, Any]]) -> AllCollection:
        all_result = AllCollection()
        for source_id in source_ids:
            source = SOURCES[source_id]
            if source.is_support_source:
                continue
            collection = self.collect_source(source_id, organizations)
            all_result.source_audits[source_id] = collection.audits
            all_result.requests += collection.requests
            all_result.response_bytes += collection.response_bytes
            all_result.requests_by_source[source_id] = collection.requests
            all_result.bytes_by_source[source_id] = collection.response_bytes
            all_result.errors.extend(collection.errors)
            for event_id, event in collection.events.items():
                if event_id in all_result.events:
                    raise CollectionError("duplicate event id across sources: " + event_id)
                all_result.events[event_id] = event
        return all_result

    # ------------------------------------------------------------------ exact recheck
    def recheck_official_id(self, source_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        source = SOURCES[source_id]
        raw = event.get("raw") or {}
        official_id = str(event.get("official_id") or "")
        if source_id == "openfda_510k":
            search = 'k_number:' + _quote(official_id)
        elif source_id == "openfda_pma":
            pma_number = str(raw.get("pma_number") or official_id.split(":")[0])
            supplement = str(raw.get("supplement_number") or "").strip()
            search = 'pma_number:' + _quote(pma_number)
            if supplement and supplement not in ("0", "-", "S000"):
                search += " AND supplement_number:" + _quote(supplement)
        elif source_id == "openfda_recall":
            search = 'product_res_number:' + _quote(official_id)
            if not raw.get("product_res_number"):
                search = 'cfres_id:' + _quote(official_id)
        else:
            return None
        result = self._fetch(source, _params(search, 0, 10), "recheck " + official_id)
        for record in result.data.get("results") or []:
            if not isinstance(record, dict):
                continue
            normalised = normalise_record(source_id, record)
            if normalised["official_id"] == official_id:
                normalised["content_hash"] = content_hash(normalised)
                return normalised
        return None

    def recheck_missing(
        self, source_id: str, missing: Sequence[dict[str, Any]], cap: int
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        found: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, Any]] = []
        if len(missing) > cap:
            return found, [{
                "type": "recheck_cap",
                "message": str(len(missing)) + " missing records exceed the recheck cap of " + str(cap),
            }]
        for event in missing:
            try:
                rechecked = self.recheck_official_id(source_id, event)
            except OpenFDAError as error:
                errors.append({"event_id": event.get("event_id"), "error": str(error), "status": error.status})
                continue
            if rechecked is not None:
                found[rechecked["event_id"]] = rechecked
        return found, errors
