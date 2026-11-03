"""Tests for the Europe PMC Live Observatory adapter.

Tier note: the first docstring line of every test states its tier. The
``synthetic`` tier runs by default, needs no network, drives the real collection
engine against a throwaway ledger and obviously synthetic payloads
(``MED:90000001``, "Synthetic indexed paper"). The ``real API connectivity`` tier
is skipped unless ``MEDRADAR_LIVE_TESTS=1`` and makes exactly one polite request;
it asserts that the documented fields still exist, never on live content.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import pytest

from medradar.http import HttpError
from medradar.observatory.adapter import DONE, run_source
from medradar.observatory.adapters.europepmc import (
    API_URL,
    SORT,
    SOURCE,
    EuropePmcAdapter,
)
from medradar.observatory.records import CHANGE_FETCH_FAILED, CHANGE_NEW, CHANGE_UPDATED, RUN_OK, RUN_PARTIAL
from tests.fixtures.observatory.helpers import (
    LATER_NOW,
    FakeFetcher,
    changes_for,
    checkpoints_for,
    committed_watermark,
    failures_for,
    make_ctx,
    make_ledger,
    observation,
    payload_of,
    versions_for,
)

LIVE = pytest.mark.skipif(
    not os.environ.get("MEDRADAR_LIVE_TESTS"),
    reason="real API connectivity tier: set MEDRADAR_LIVE_TESTS=1 to make one polite live request",
)


# ------------------------------------------------------------------ synthetic data
def result(
    record_id: str | None = "90000001",
    source: str | None = "MED",
    *,
    title: str = "Synthetic indexed paper",
    doi: str | None = "10.0000/synthetic.1",
    first_publication: str | None = "2026-10-31",
    first_index: str | None = "2026-11-01",
    revision: str | None = "2026-11-02",
    creation: str = "2026-10-31",
    journal: str = "Synthetic Journal of Testing",
    authors: str = "Synthetic A, Synthetic B.",
    pub_types: tuple[str, ...] = ("Journal Article",),
    abstract: str = "Synthetic abstract text for tests only.",
) -> dict[str, Any]:
    """One synthetic Europe PMC ``resultType=core`` result."""
    payload: dict[str, Any] = {
        "id": record_id,
        "source": source,
        "pmid": record_id,
        "doi": doi,
        "title": title,
        "authorString": authors,
        "journalTitle": journal,
        "journalIssn": "0000-0000",
        "pubYear": "2026",
        "pubType": pub_types[0] if pub_types else None,
        "pubTypeList": {"pubType": list(pub_types)},
        "firstPublicationDate": first_publication,
        "firstIndexDate": first_index,
        "dateOfCreation": creation,
        "dateOfRevision": revision,
        "language": "eng",
        "publicationStatus": "ppublish",
        "abstractText": abstract,
        "journalInfo": {
            "volume": "12",
            "issue": "3",
            "dateOfPublication": "2026 Oct",
            "printPublicationDate": "2026-10-01",
            "journal": {"title": journal, "issn": "0000-0000"},
        },
    }
    return payload


def page(results: list[dict[str, Any]], next_mark: str | None = None, hit_count: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "6.9",
        "hitCount": hit_count if hit_count is not None else len(results),
        "request": {"queryString": "synthetic", "resultType": "core"},
        "resultList": {"result": list(results)},
    }
    if next_mark:
        payload["nextCursorMark"] = next_mark
    return payload


def router(routes: Mapping[tuple[str | None, str | None], Any], *, terms: tuple[str, ...] = ("Medtronic", "Philips")):
    """Route on (affiliation term in the query, ``cursorMark``); a value may be an exception."""

    def route(url: str, params: dict[str, Any]) -> Any:
        assert url == API_URL, f"unexpected URL {url!r}"
        query = str(params.get("query") or "")
        mark = params.get("cursorMark")
        term = next((candidate for candidate in terms if f'AFF:"{candidate}"' in query), None)
        key = (term, mark)
        if key not in routes:
            raise AssertionError(f"unexpected Europe PMC request: term={term!r} cursorMark={mark!r}")
        value = routes[key]
        if isinstance(value, BaseException):
            raise value
        return value

    return route


# --------------------------------------------------------------------- synthetic
def test_europepmc_synthetic_new_then_unchanged_and_provisional_mapping(tmp_path):
    """Tier: synthetic — first run is NEW with PENDING_REVIEW attribution; an identical re-run changes nothing."""
    ledger = make_ledger(tmp_path)
    canned = page(
        [
            result("90000001"),
            result("90000002", doi="10.0000/synthetic.2", title="Another synthetic indexed paper"),
        ]
    )
    fetcher = FakeFetcher(router({("Medtronic", "*"): canned}))
    run1 = run_source(EuropePmcAdapter(companies=["medtronic"]), make_ctx(ledger, fetcher))
    assert run1["status"] == RUN_OK
    assert run1["counters"]["records_new"] == 2

    # documented request shape (lite/core, cursorMark, FIRST_PDATE window)
    ((_url, params),) = fetcher.calls
    assert params["format"] == "json"
    assert params["resultType"] == "core"
    assert params["sort"] == SORT
    assert int(params["pageSize"]) <= 100
    assert '(AFF:"Medtronic") AND (SRC:MED OR SRC:PPR)' in params["query"]
    assert "FIRST_PDATE:[" in params["query"]

    row = observation(ledger, SOURCE, "MED:90000001")
    first_seen = row["first_seen_at"]
    assert row["record_type"] == "publication"
    assert row["original_url"] == "https://europepmc.org/article/MED/90000001"
    assert row["current_change_state"] == CHANGE_NEW
    # attribution by affiliation query is provisional by construction
    assert row["entity_id"] == "medtronic"
    assert row["entity_status"] == "PENDING_REVIEW"
    assert row["entity_method"] == "europepmc_affiliation_query"

    run2 = run_source(
        EuropePmcAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", "*"): canned})), now=LATER_NOW),
    )
    assert run2["status"] == RUN_OK
    assert run2["counters"]["records_unchanged"] == 2
    assert run2["counters"]["records_new"] == 0
    assert run2["counters"]["records_updated"] == 0

    again = observation(ledger, SOURCE, "MED:90000001")
    assert again["first_seen_at"] == first_seen
    assert again["current_change_state"] == CHANGE_NEW
    assert len(versions_for(ledger, SOURCE, "MED:90000001")) == 1
    assert [entry["change_state"] for entry in changes_for(ledger, SOURCE, "MED:90000001")] == [CHANGE_NEW]


def test_europepmc_synthetic_metadata_revision_is_updated(tmp_path):
    """Tier: synthetic — a metadata revision with the same id becomes UPDATED and keeps first_seen_at."""
    ledger = make_ledger(tmp_path)
    before = page([result("90000001", title="Synthetic indexed paper")])
    run1 = run_source(
        EuropePmcAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", "*"): before}))),
    )
    assert run1["counters"]["records_new"] == 1
    first_seen = observation(ledger, SOURCE, "MED:90000001")["first_seen_at"]

    after = page([result("90000001", title="Synthetic indexed paper (revised metadata)", revision="2026-11-03")])
    run2 = run_source(
        EuropePmcAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", "*"): after})), now=LATER_NOW),
    )
    assert run2["status"] == RUN_OK
    assert run2["counters"]["records_updated"] == 1
    assert run2["counters"]["records_unchanged"] == 0

    row = observation(ledger, SOURCE, "MED:90000001")
    assert row["first_seen_at"] == first_seen
    assert row["current_change_state"] == CHANGE_UPDATED
    assert row["version_count"] == 2

    versions = versions_for(ledger, SOURCE, "MED:90000001")
    assert [version["version_seq"] for version in versions] == [1, 2]
    assert payload_of(versions[0])["title"] == "Synthetic indexed paper"
    assert payload_of(versions[1])["title"] == "Synthetic indexed paper (revised metadata)"
    assert payload_of(versions[1])["published_at_source_field"] == "firstIndexDate"

    changes = changes_for(ledger, SOURCE, "MED:90000001")
    assert [entry["change_state"] for entry in changes] == [CHANGE_NEW, CHANGE_UPDATED]
    assert "title" in json.loads(changes[1]["changed_fields"])


def test_europepmc_synthetic_cursor_paging_checkpoint_and_watermark(tmp_path):
    """Tier: synthetic — nextCursorMark paging, DONE checkpoint and a committed per-scope watermark."""
    ledger = make_ledger(tmp_path)
    routes = {
        ("Medtronic", "*"): page(
            [result("90000001"), result("90000002", first_publication="2026-10-30")],
            next_mark="AoJw1",
            hit_count=3,
        ),
        ("Medtronic", "AoJw1"): page([result("90000003", first_publication="2026-10-29")]),
    }
    fetcher = FakeFetcher(router(routes))
    collected = run_source(EuropePmcAdapter(companies=["medtronic"], page_size=2), make_ctx(ledger, fetcher))

    assert collected["status"] == RUN_OK
    assert collected["counters"]["pages"] == 2
    assert collected["counters"]["records_new"] == 3
    assert [call[1].get("cursorMark") for call in fetcher.calls] == ["*", "AoJw1"]

    checkpoints = checkpoints_for(ledger, SOURCE, collected["run_id"])
    assert len(checkpoints) == 1
    ((scope_id, cursor),) = checkpoints.items()
    assert cursor == DONE
    watermark = committed_watermark(ledger, SOURCE)[scope_id]
    assert watermark["latest_date"] == "2026-11-02"
    assert watermark["pending_upper"] is None
    assert "MED:90000001" in watermark["known_ids"]
    assert '(AFF:"Medtronic")' in watermark["affiliation_query"]


def test_europepmc_synthetic_page_two_failure_is_partial_and_stale_cursor_recovers(tmp_path):
    """Tier: synthetic — page-2 failure is a recorded PARTIAL run; a resumed run uses the checkpoint and recovers from a stale cursor."""
    ledger = make_ledger(tmp_path)
    routes: dict[tuple[str | None, str | None], Any] = {
        ("Medtronic", "*"): page(
            [result("90000001"), result("90000002", first_publication="2026-10-30")],
            next_mark="MED-2",
            hit_count=3,
        ),
        ("Medtronic", "MED-2"): HttpError(503, API_URL, "synthetic service unavailable"),
        ("Philips", "*"): page([result("90000101", title="Synthetic Philips indexed paper")]),
    }
    run1 = run_source(
        EuropePmcAdapter(companies=["medtronic", "philips"], page_size=2),
        make_ctx(ledger, FakeFetcher(router(routes))),
    )
    assert run1["status"] == RUN_PARTIAL
    assert run1["counters"]["pages"] == 2
    assert run1["counters"]["records_new"] == 3
    assert run1["counters"]["records_failed"] >= 1
    assert run1["errors"]

    failures = failures_for(ledger, SOURCE, run1["run_id"])
    assert failures
    assert any(entry["kind"] == "HTTP_ERROR" for entry in failures)

    # no loss of page-1 records; the failed re-check is its own recorded state
    assert observation(ledger, SOURCE, "MED:90000001")["observation_status"] == "ACTIVE"
    page_one_states = [entry["change_state"] for entry in changes_for(ledger, SOURCE, "MED:90000001")]
    assert CHANGE_FETCH_FAILED in page_one_states
    first_seen = observation(ledger, SOURCE, "MED:90000001")["first_seen_at"]

    checkpoints = checkpoints_for(ledger, SOURCE, run1["run_id"])
    assert "MED-2" in checkpoints.values()
    assert DONE in checkpoints.values()

    # The resumed run starts from the stored cursor. That cursor belonged to the
    # previous run's window, so Europe PMC may reject it (400): the adapter must
    # restart the window from page 1, record the event, and lose nothing.
    routes[("Medtronic", "MED-2")] = HttpError(400, API_URL, "synthetic invalid cursorMark")
    routes[("Medtronic", "*")] = page(
        [result("90000001"), result("90000002", first_publication="2026-10-30")],
        next_mark="MED-2b",
        hit_count=3,
    )
    routes[("Medtronic", "MED-2b")] = page([result("90000003", first_publication="2026-10-29")])
    fetcher2 = FakeFetcher(router(routes))
    run2 = run_source(
        EuropePmcAdapter(companies=["medtronic", "philips"], page_size=2),
        make_ctx(ledger, fetcher2, now=LATER_NOW),
    )
    assert run2["resumed"] is True
    assert [call[1].get("cursorMark") for call in fetcher2.calls] == ["MED-2", "*", "MED-2b"]
    assert run2["status"] == RUN_OK
    assert run2["counters"]["records_new"] == 1
    assert run2["counters"]["records_unchanged"] == 2
    assert observation(ledger, SOURCE, "MED:90000001")["first_seen_at"] == first_seen
    assert len(versions_for(ledger, SOURCE, "MED:90000001")) == 1
    assert observation(ledger, SOURCE, "MED:90000003")["first_seen_at"] == LATER_NOW

    # the stale cursor is not swallowed: it is a recorded HTTP event
    cursor_failures = [
        entry for entry in failures_for(ledger, SOURCE, run2["run_id"]) if entry["http_status"] == 400
    ]
    assert cursor_failures, "a rejected checkpoint cursor must leave a source_failure row"


def test_europepmc_synthetic_time_mapping_and_identifiers(tmp_path):
    """Tier: synthetic — event/publish/update times come from three distinct documented fields, no time invented."""
    ledger = make_ledger(tmp_path)
    canned = page(
        [
            result("90000001", first_publication="2026-10-31", first_index="2026-11-01", revision="2026-11-02"),
            result("90000002", first_index=None),
            result(None, None, doi="10.0000/fallback", title="Synthetic DOI-only record"),
            result(None, None, doi=None, title="Synthetic unidentifiable record"),
        ]
    )
    fetcher = FakeFetcher(router({("Medtronic", "*"): canned}))
    adapter = EuropePmcAdapter(companies=["medtronic"])
    ctx = make_ctx(ledger, fetcher)
    scope = adapter.plan(ctx)[0]
    fetched = adapter.fetch_page(ctx, scope, None)

    first = fetched.records[0]
    assert first.source_record_id == "MED:90000001"
    assert first.url == "https://europepmc.org/article/MED/90000001"
    assert first.record_type == "publication"
    assert first.event_at == "2026-10-31" and first.event_at_precision == "date"
    assert first.published_at == "2026-11-01" and first.published_at_precision == "date"
    assert first.published_at != first.event_at, "the publication date must not be reused as availability"
    assert first.source_updated_at == "2026-11-02" and first.source_updated_at_precision == "date"
    assert "T" not in str(first.event_at)
    assert first.payload["published_at_source_field"] == "firstIndexDate"
    assert first.payload["doi"] == "10.0000/synthetic.1"
    assert first.payload["journal"]["title"] == "Synthetic Journal of Testing"
    assert first.payload["pub_types"] == ["Journal Article"]

    # no index date -> published_at stays NULL instead of borrowing the publication date
    second = fetched.records[1]
    assert second.event_at == "2026-10-31"
    assert second.published_at is None
    assert second.published_at_precision == "unknown"
    assert second.payload["published_at_source_field"] is None

    # a DOI-only record keeps a stable, prefixed identifier instead of a fake one
    doi_only = fetched.records[2]
    assert doi_only.source_record_id == "DOI:10.0000/fallback"
    assert doi_only.url == "https://doi.org/10.0000/fallback"

    # a result with neither id nor DOI is skipped loudly, never invented
    assert len(fetched.records) == 3
    assert "缺少稳定标识" in (fetched.note_zh or "")


def test_europepmc_synthetic_page_ceiling_is_not_silent(tmp_path):
    """Tier: synthetic — hitting the page ceiling ends the page cursor but records the pending observation bound."""
    ledger = make_ledger(tmp_path)
    canned = page(
        [result("90000001", first_publication="2026-10-31"), result("90000002", first_publication="2026-10-29")],
        next_mark="next-mark",
        hit_count=57,
    )
    fetcher = FakeFetcher(router({("Medtronic", "*"): canned}))
    adapter = EuropePmcAdapter(companies=["medtronic"], page_size=2, max_pages=1)
    ctx = make_ctx(ledger, fetcher)
    scope = adapter.plan(ctx)[0]
    fetched = adapter.fetch_page(ctx, scope, None)

    assert len(fetcher.calls) == 1
    assert fetched.next_cursor is None
    assert "页数上限" in (fetched.note_zh or "")
    assert "hitCount=57" in (fetched.note_zh or "")
    watermark = fetched.watermark
    assert watermark["pending_upper"] == "2026-10-28", "the window below the oldest read record is still pending"
    assert watermark["latest_date"] == "2026-11-02"


def test_europepmc_synthetic_continuation_window_uses_pending_bound(tmp_path):
    """Tier: synthetic — a truncated run's pending bound is reused by the next run instead of being forgotten."""
    ledger = make_ledger(tmp_path)
    routes = {
        ("Medtronic", "*"): page(
            [result("90000001", first_publication="2026-10-31"), result("90000002", first_publication="2026-10-29")],
            next_mark="next-mark",
            hit_count=57,
        ),
    }
    run1 = run_source(
        EuropePmcAdapter(companies=["medtronic"], page_size=2, max_pages=1),
        make_ctx(ledger, FakeFetcher(router(routes))),
    )
    assert run1["status"] == RUN_OK
    scope_id = next(iter(committed_watermark(ledger, SOURCE)))
    watermark = committed_watermark(ledger, SOURCE)[scope_id]
    assert watermark["pending_upper"] == "2026-10-28"

    seen_queries: list[str] = []

    def continue_router(_url: str, params: dict[str, Any]) -> Any:
        seen_queries.append(str(params.get("query")))
        return page([result("90000003", first_publication="2026-10-20")])

    run2 = run_source(
        EuropePmcAdapter(companies=["medtronic"], page_size=2, max_pages=1),
        make_ctx(ledger, FakeFetcher(continue_router), now=LATER_NOW),
    )
    assert run2["status"] == RUN_OK
    assert len(seen_queries) == 1
    assert "TO 2026-10-28" in seen_queries[0], "the continuation window must end at the recorded pending bound"
    assert '(AFF:"Medtronic")' in seen_queries[0]
    after = committed_watermark(ledger, SOURCE)[scope_id]
    assert after["pending_upper"] is None
    assert after["latest_date"] == "2026-11-02"
    assert observation(ledger, SOURCE, "MED:90000003")["first_seen_at"] == LATER_NOW


def test_europepmc_synthetic_scopes_are_affiliation_queries(tmp_path):
    """Tier: synthetic — one scope per verified company, with the curated name inside an AFF query."""
    ledger = make_ledger(tmp_path)
    adapter = EuropePmcAdapter()
    scopes = adapter.plan(make_ctx(ledger, FakeFetcher(router({}, terms=()))))
    assert [scope.params["company_key"] for scope in scopes] == [
        "medtronic",
        "ge_healthcare",
        "philips",
        "draeger",
        "mindray",
    ]
    assert [scope.params["affiliation_term"] for scope in scopes] == [
        "Medtronic",
        "GE HealthCare",
        "Philips",
        "Dräger",
        "Mindray",
    ]
    for scope in scopes:
        query = scope.params["affiliation_query"]
        assert query.startswith('(AFF:"')
        assert "(SRC:MED OR SRC:PPR)" in query
        assert scope.params["term_source"]

    filtered = EuropePmcAdapter(companies=["philips"]).plan(
        make_ctx(ledger, FakeFetcher(router({}, terms=())))
    )
    assert [scope.params["company_key"] for scope in filtered] == ["philips"]

    with pytest.raises(ValueError):
        EuropePmcAdapter(companies=["not_a_roster_company"]).plan(
            make_ctx(ledger, FakeFetcher(router({}, terms=())))
        )


def test_europepmc_synthetic_record_type_labels_are_declared():
    """Tier: synthetic — the adapter declares the publication record type and its Chinese label."""
    adapter = EuropePmcAdapter()
    assert adapter.source_id == "europepmc"
    assert adapter.record_type_labels == {"publication": "文献元数据"}
    assert adapter.declared_cadence_zh


# ------------------------------------------------------- real API connectivity
@LIVE
def test_europepmc_live_documented_fields_are_present():
    """Tier: real API connectivity — one polite request; asserts documented structure, never data content."""
    from medradar.http import Fetcher

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=30)
    query = (
        f'(AFF:"Medtronic") AND (SRC:MED OR SRC:PPR) '
        f"AND (FIRST_PDATE:[{start.isoformat()} TO {today.isoformat()}])"
    )
    fetcher = Fetcher(min_interval=1.0, max_requests=2, timeout=60)
    payload = fetcher.get_json(
        API_URL,
        {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": 1,
            "cursorMark": "*",
            "sort": SORT,
        },
    )
    assert fetcher.stats["requests"] == 1, "the connectivity tier must stay at one request"
    assert isinstance(payload, Mapping)
    assert isinstance(payload.get("hitCount"), int)
    assert isinstance(payload.get("resultList"), Mapping)
    results = payload["resultList"].get("result")
    assert isinstance(results, list)
    mark = payload.get("nextCursorMark")
    assert mark is None or isinstance(mark, str)
    request_echo = payload.get("request") or {}
    assert request_echo.get("resultType") == "core"

    if not results:  # pragma: no cover - only when the window has no hits
        pytest.skip("no result in the window; result structure cannot be asserted")
    first = results[0]
    for key in ("id", "source", "title", "firstPublicationDate"):
        assert key in first, f"documented Europe PMC field {key!r} disappeared"
    assert first["id"] and first["source"]
    assert isinstance(first["firstPublicationDate"], str)
    if "dateOfRevision" in first:
        assert isinstance(first["dateOfRevision"], str)
    if isinstance(first.get("journalInfo"), Mapping):
        assert isinstance(first.get("pubTypeList"), Mapping)
