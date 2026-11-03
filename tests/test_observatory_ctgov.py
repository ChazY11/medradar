"""Tests for the ClinicalTrials.gov Live Observatory adapter.

Tier note: the first docstring line of every test states its tier. The
``synthetic`` tier runs by default, needs no network, drives the real collection
engine against a throwaway ledger and obviously synthetic payloads
(``NCT00000001`` etc.). The ``real API connectivity`` tier is skipped unless
``MEDRADAR_LIVE_TESTS=1`` and makes exactly one polite request; it asserts that
the documented fields still exist, never on the data's content.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

import pytest

from medradar.http import HttpError
from medradar.observatory.adapter import DONE, run_source
from medradar.observatory.adapters.ctgov import (
    API_URL,
    FIELDS_PARAM,
    SORT,
    SOURCE,
    ClinicalTrialsAdapter,
)
from medradar.observatory.records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_UPDATED,
    RUN_OK,
    RUN_PARTIAL,
)
from tests.fixtures.observatory.helpers import (
    FIXED_NOW,
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
    source_state,
    versions_for,
)

LIVE = pytest.mark.skipif(
    not os.environ.get("MEDRADAR_LIVE_TESTS"),
    reason="real API connectivity tier: set MEDRADAR_LIVE_TESTS=1 to make one polite live request",
)

MEDTRONIC_SPONSOR = "Medtronic Cardiac Rhythm and Heart Failure"
PHILIPS_SPONSOR = "Philips Healthcare"


# ------------------------------------------------------------------ synthetic data
def study(
    nct_id: str,
    *,
    update: str = "2026-11-02",
    first_post: str = "2024-05-01",
    start: str = "2024-06-01",
    status: str = "RECRUITING",
    phases: tuple[str, ...] = ("PHASE3",),
    sponsor: str = MEDTRONIC_SPONSOR,
    title: str = "Synthetic pacemaker trial",
    conditions: tuple[str, ...] = ("Synthetic bradycardia",),
    enrollment: int | None = 120,
    has_results: bool = False,
) -> dict[str, Any]:
    """One synthetic CT.gov v2 study in exactly the shape produced by ``fields=``."""
    design: dict[str, Any] = {"studyType": "INTERVENTIONAL", "phases": list(phases)}
    if enrollment is not None:
        design["enrollmentInfo"] = {"count": enrollment, "type": "ESTIMATED"}
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": title},
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": {"date": start},
                "primaryCompletionDateStruct": {"date": "2028-08"},
                "completionDateStruct": {"date": "2029-02"},
                "studyFirstPostDateStruct": {"date": first_post},
                "lastUpdatePostDateStruct": {"date": update},
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
            "conditionsModule": {"conditions": list(conditions)},
            "designModule": design,
            "armsInterventionsModule": {
                "interventions": [
                    {
                        "type": "DEVICE",
                        "name": "Synthetic pacemaker",
                        "otherNames": ["SYNTH-PM"],
                        "description": "Synthetic device description for tests only.",
                    }
                ]
            },
        },
        "hasResults": has_results,
    }


def page(studies: list[dict[str, Any]], token: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"studies": list(studies)}
    if token:
        payload["nextPageToken"] = token
    return payload


def router(routes: Mapping[tuple[str, str | None], Any]):
    """Route on (``query.spons``, ``pageToken``); a value may be an exception."""

    def route(url: str, params: dict[str, Any]) -> Any:
        assert url == API_URL, f"unexpected URL {url!r}"
        key = (str(params.get("query.spons")), params.get("pageToken"))
        if key not in routes:
            raise AssertionError(f"unexpected ClinicalTrials.gov request: sponsor={key[0]!r} token={key[1]!r}")
        value = routes[key]
        if isinstance(value, BaseException):
            raise value
        return value

    return route


def planned_scope(ledger, *, now: str = FIXED_NOW, companies: list[str] | None = None):
    adapter = ClinicalTrialsAdapter(companies=companies or ["medtronic"])
    ctx = make_ctx(ledger, FakeFetcher(router({})), now=now)
    return adapter, ctx, adapter.plan(ctx)[0]


# --------------------------------------------------------------------- synthetic
def test_ctgov_synthetic_new_then_unchanged_keeps_first_seen_at(tmp_path):
    """Tier: synthetic — first run is NEW; an identical re-run adds no version or change row."""
    ledger = make_ledger(tmp_path)
    canned = page([study("NCT00000001"), study("NCT00000002", update="2026-11-01")])

    run1 = run_source(
        ClinicalTrialsAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", None): canned}))),
    )
    assert run1["status"] == RUN_OK
    assert run1["counters"]["records_new"] == 2
    assert run1["counters"]["records_seen"] == 2

    first = observation(ledger, SOURCE, "NCT00000001")
    first_seen = first["first_seen_at"]
    assert first["current_change_state"] == CHANGE_NEW
    assert first["record_type"] == "trial"
    assert [version["change_state"] for version in versions_for(ledger, SOURCE, "NCT00000001")] == [CHANGE_NEW]

    run2 = run_source(
        ClinicalTrialsAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", None): canned})), now=LATER_NOW),
    )
    assert run2["status"] == RUN_OK
    assert run2["counters"]["records_unchanged"] == 2
    assert run2["counters"]["records_new"] == 0
    assert run2["counters"]["records_updated"] == 0

    again = observation(ledger, SOURCE, "NCT00000001")
    assert again["first_seen_at"] == first_seen
    assert again["last_checked_at"] == LATER_NOW
    assert again["current_change_state"] == CHANGE_NEW
    assert again["version_count"] == 1
    assert len(versions_for(ledger, SOURCE, "NCT00000001")) == 1
    assert [row["change_state"] for row in changes_for(ledger, SOURCE, "NCT00000001")] == [CHANGE_NEW]


def test_ctgov_synthetic_changed_field_is_updated_and_keeps_first_seen_at(tmp_path):
    """Tier: synthetic — a changed trial status becomes UPDATED with both versions retrievable."""
    ledger = make_ledger(tmp_path)
    before = page([study("NCT00000001", status="RECRUITING")])
    run1 = run_source(
        ClinicalTrialsAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", None): before}))),
    )
    assert run1["counters"]["records_new"] == 1
    first_seen = observation(ledger, SOURCE, "NCT00000001")["first_seen_at"]

    after = page([study("NCT00000001", status="ACTIVE_NOT_RECRUITING", update="2026-11-03")])
    run2 = run_source(
        ClinicalTrialsAdapter(companies=["medtronic"]),
        make_ctx(ledger, FakeFetcher(router({("Medtronic", None): after})), now=LATER_NOW),
    )
    assert run2["status"] == RUN_OK
    assert run2["counters"]["records_updated"] == 1
    assert run2["counters"]["records_unchanged"] == 0

    row = observation(ledger, SOURCE, "NCT00000001")
    assert row["first_seen_at"] == first_seen
    assert row["current_change_state"] == CHANGE_UPDATED
    assert row["version_count"] == 2

    versions = versions_for(ledger, SOURCE, "NCT00000001")
    assert [version["version_seq"] for version in versions] == [1, 2]
    assert payload_of(versions[0])["overall_status"] == "RECRUITING"
    assert payload_of(versions[1])["overall_status"] == "ACTIVE_NOT_RECRUITING"

    changes = changes_for(ledger, SOURCE, "NCT00000001")
    assert [row["change_state"] for row in changes] == [CHANGE_NEW, CHANGE_UPDATED]
    assert "overall_status" in json.loads(changes[1]["changed_fields"])


def test_ctgov_synthetic_cursor_paging_checkpoint_and_watermark(tmp_path):
    """Tier: synthetic — two pages are fetched by nextPageToken, the scope is checkpointed DONE and the watermark is committed."""
    ledger = make_ledger(tmp_path)
    routes = {
        ("Medtronic", None): page(
            [study("NCT00000001"), study("NCT00000002", update="2026-11-01")], token="page-2"
        ),
        ("Medtronic", "page-2"): page([study("NCT00000003", update="2026-10-29")]),
    }
    fetcher = FakeFetcher(router(routes))
    result = run_source(ClinicalTrialsAdapter(companies=["medtronic"]), make_ctx(ledger, fetcher))

    assert result["status"] == RUN_OK
    assert result["counters"]["pages"] == 2
    assert result["counters"]["records_new"] == 3
    assert [call[1].get("pageToken") for call in fetcher.calls] == [None, "page-2"]
    for _url, params in fetcher.calls:
        assert params["query.spons"] == "Medtronic"
        assert params["sort"] == SORT
        assert params["fields"] == FIELDS_PARAM
        assert 1 <= int(params["pageSize"]) <= 100

    checkpoints = checkpoints_for(ledger, SOURCE, result["run_id"])
    assert len(checkpoints) == 1
    ((scope_id, cursor),) = checkpoints.items()
    assert cursor == DONE

    watermark = committed_watermark(ledger, SOURCE)
    assert watermark[scope_id]["last_update_post_date"] == "2026-11-02"
    assert watermark[scope_id]["company_key"] == "medtronic"
    assert "NCT00000001" in watermark[scope_id]["known_ids"]
    state = source_state(ledger, SOURCE)
    assert state["status"] == "OK"
    assert state["structure_signature"], "the engine must have stored a structure fingerprint"
    assert observation(ledger, SOURCE, "NCT00000003")["first_seen_at"] == FIXED_NOW


def test_ctgov_synthetic_page_two_failure_is_partial_and_resumable(tmp_path):
    """Tier: synthetic — page-2 failure yields PARTIAL + source_failure, keeps page-1 records, and resume uses the checkpoint."""
    ledger = make_ledger(tmp_path)
    routes: dict[tuple[str, str | None], Any] = {
        ("Medtronic", None): page([study("NCT00000001")], token="MED-2"),
        ("Medtronic", "MED-2"): HttpError(503, API_URL, "synthetic service unavailable"),
        ("Philips", None): page([study("NCT00000009", sponsor=PHILIPS_SPONSOR)]),
    }
    run1 = run_source(
        ClinicalTrialsAdapter(companies=["medtronic", "philips"]),
        make_ctx(ledger, FakeFetcher(router(routes))),
    )
    assert run1["status"] == RUN_PARTIAL
    assert run1["counters"]["pages"] == 2
    assert run1["counters"]["records_new"] == 2
    assert run1["counters"]["records_failed"] >= 1
    assert run1["errors"]

    failures = failures_for(ledger, SOURCE, run1["run_id"])
    assert failures, "a failed page must leave a source_failure row"
    assert failures[0]["kind"] == "HTTP_ERROR"
    assert int(failures[0]["retryable"]) == 1

    # no loss of page-1 records, and the failed re-check is its own recorded state
    assert observation(ledger, SOURCE, "NCT00000001")["observation_status"] == "ACTIVE"
    page_one_states = [row["change_state"] for row in changes_for(ledger, SOURCE, "NCT00000001")]
    assert CHANGE_FETCH_FAILED in page_one_states

    checkpoints = checkpoints_for(ledger, SOURCE, run1["run_id"])
    assert "MED-2" in checkpoints.values()
    assert DONE in checkpoints.values()  # the Philips scope completed

    # the next run resumes from the stored cursor instead of re-reading page 1
    routes[("Medtronic", "MED-2")] = page([study("NCT00000002", update="2026-11-01")])
    fetcher2 = FakeFetcher(router(routes))
    run2 = run_source(
        ClinicalTrialsAdapter(companies=["medtronic", "philips"]),
        make_ctx(ledger, fetcher2, now=LATER_NOW),
    )
    assert run2["resumed"] is True
    assert run2["status"] == RUN_OK
    assert run2["counters"]["records_new"] == 1
    assert len(fetcher2.calls) == 1  # the completed scope and page 1 were not re-read
    assert fetcher2.calls[0][1].get("pageToken") == "MED-2"
    assert observation(ledger, SOURCE, "NCT00000002")["first_seen_at"] == LATER_NOW
    assert len(versions_for(ledger, SOURCE, "NCT00000001")) == 1


def test_ctgov_synthetic_stops_at_incremental_lower_bound(tmp_path):
    """Tier: synthetic — a page entirely behind the watermark window stops paging and says so."""
    ledger = make_ledger(tmp_path)
    _adapter, _ctx, scope = planned_scope(ledger)
    ledger.set_watermark(
        SOURCE,
        {scope.scope_id: {"last_update_post_date": "2026-11-02", "known_ids": ["NCT00000001"]}},
    )
    fetcher = FakeFetcher(
        router({("Medtronic", None): page([study("NCT00000009", update="2026-01-01")], token="page-2")})
    )
    adapter = ClinicalTrialsAdapter(companies=["medtronic"])
    ctx = make_ctx(ledger, fetcher)
    result_page = adapter.fetch_page(ctx, scope, None)

    assert result_page.records == []
    assert result_page.next_cursor is None, "a whole page older than the lower bound ends the scope"
    assert "早于增量下界" in (result_page.note_zh or "")
    assert len(fetcher.calls) == 1, "page 2 must not be requested once the window is exhausted"
    assert result_page.watermark["company_key"] == "medtronic"


def test_ctgov_synthetic_mixed_page_skips_old_but_keeps_paging(tmp_path):
    """Tier: synthetic — the incremental window drops only old records; newer ones are observed and paging continues."""
    ledger = make_ledger(tmp_path)
    _adapter, _ctx, scope = planned_scope(ledger)
    ledger.set_watermark(
        SOURCE,
        {scope.scope_id: {"last_update_post_date": "2026-11-02", "known_ids": ["NCT00000001"]}},
    )
    fetcher = FakeFetcher(
        router(
            {
                ("Medtronic", None): page(
                    [
                        study("NCT00000005", update="2026-11-02"),
                        study("NCT00000006", update="2026-01-01"),
                    ],
                    token="page-2",
                )
            }
        )
    )
    adapter = ClinicalTrialsAdapter(companies=["medtronic"])
    ctx = make_ctx(ledger, fetcher)
    result_page = adapter.fetch_page(ctx, scope, None)

    assert [record.source_record_id for record in result_page.records] == ["NCT00000005"]
    assert result_page.next_cursor == "page-2"
    assert "1 条登记" in (result_page.note_zh or "")
    assert result_page.structure_sample


def test_ctgov_synthetic_time_mapping_is_source_precise(tmp_path):
    """Tier: synthetic — event_at, published_at and source_updated_at are three different source dates."""
    ledger = make_ledger(tmp_path)
    canned = page([study("NCT00000007", start="2024-06-01", first_post="2024-05-20", update="2026-11-02")])
    fetcher = FakeFetcher(router({("Medtronic", None): canned}))
    adapter = ClinicalTrialsAdapter(companies=["medtronic"])
    ctx = make_ctx(ledger, fetcher)
    scope = adapter.plan(ctx)[0]

    (record,) = adapter.fetch_page(ctx, scope, None).records
    assert record.event_at == "2024-06-01"
    assert record.event_at_precision == "date"
    assert record.published_at == "2024-05-20"
    assert record.published_at_precision == "date"
    assert record.source_updated_at == "2026-11-02"
    assert record.source_updated_at_precision == "date"
    assert record.event_at != record.published_at
    assert "T" not in str(record.event_at), "no time of day may be invented"
    assert record.record_type == "trial"
    assert record.url == "https://clinicaltrials.gov/study/NCT00000007"
    assert record.source_record_id == "NCT00000007"

    # payload = source-derived fields only (no derived mapping)
    assert set(record.payload) >= {
        "nct_id",
        "overall_status",
        "phases",
        "enrollment_count",
        "lead_sponsor",
        "conditions",
        "interventions",
        "start_date",
        "study_first_post_date",
        "last_update_post_date",
        "has_results",
    }
    assert not {"entity_id", "track_id", "match_confidence"} & set(record.payload)

    mapped = adapter.map_record(record, ctx)
    assert mapped.entity_id == "medtronic"
    assert mapped.entity_status == "MAPPED"
    assert mapped.entity_method == "ctgov_roster_alias"


def test_ctgov_synthetic_scopes_use_curated_names_only(tmp_path):
    """Tier: synthetic — one scope per verified company and the search term is the curated name, verbatim."""
    ledger = make_ledger(tmp_path)
    adapter = ClinicalTrialsAdapter()
    scopes = adapter.plan(make_ctx(ledger, FakeFetcher(router({}))))
    assert [scope.params["sponsor"] for scope in scopes] == [
        "Medtronic",
        "GE HealthCare",
        "Philips",
        "Dräger",
        "Mindray",
    ]
    assert [scope.params["company_key"] for scope in scopes] == [
        "medtronic",
        "ge_healthcare",
        "philips",
        "draeger",
        "mindray",
    ]
    assert all(scope.params["term_source"] for scope in scopes)

    filtered = ClinicalTrialsAdapter(companies=["philips"]).plan(make_ctx(ledger, FakeFetcher(router({}))))
    assert [scope.params["company_key"] for scope in filtered] == ["philips"]

    with pytest.raises(ValueError):
        ClinicalTrialsAdapter(companies=["not_a_roster_company"]).plan(
            make_ctx(ledger, FakeFetcher(router({})))
        )


# ------------------------------------------------------- real API connectivity
@LIVE
def test_ctgov_live_documented_fields_are_present():
    """Tier: real API connectivity — one polite request; asserts documented structure, never data content."""
    from medradar.http import Fetcher

    fetcher = Fetcher(min_interval=1.0, max_requests=2, timeout=60)
    payload = fetcher.get_json(
        API_URL,
        {
            "query.spons": "Medtronic",
            "pageSize": 1,
            "sort": SORT,
            "fields": FIELDS_PARAM,
        },
    )
    assert fetcher.stats["requests"] == 1, "the connectivity tier must stay at one request"
    assert isinstance(payload, Mapping)
    assert isinstance(payload.get("studies"), list)
    token = payload.get("nextPageToken")
    assert token is None or isinstance(token, str)

    studies = payload["studies"]
    if not studies:  # pragma: no cover - only if the sponsor has no registrations
        pytest.skip("no study returned; structure of studies cannot be asserted")
    study = studies[0]
    assert isinstance(study.get("protocolSection"), Mapping)
    status_module = study["protocolSection"].get("statusModule")
    assert isinstance(status_module, Mapping)
    for key in ("overallStatus", "studyFirstPostDateStruct", "lastUpdatePostDateStruct"):
        assert key in status_module, f"documented CT.gov field {key!r} disappeared"
    identification = study["protocolSection"].get("identificationModule") or {}
    assert identification.get("nctId"), "documented NCTId field is missing"
    design = study["protocolSection"].get("designModule") or {}
    assert "studyType" in design
    assert "hasResults" in study
