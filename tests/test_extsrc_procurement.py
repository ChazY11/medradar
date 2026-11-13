"""Offline tests for the procurement + hiring connectors (DATA-EXPANSION-001).

No network, no credentials, no dated fixtures: every payload below is a small
inline dict written by hand to exercise the *logic* (normalisation, clock
semantics, identity, bounds).  The real responses live in
``research/data_expansion/samples/<source_id>/`` and are not used here, so the
suite stays fast and hermetic.

What is deliberately asserted
-----------------------------
* a procurement **award** never acquires a publication date it does not have
  (USAspending has none) and a tender release never acquires an award date;
* ``source_public_at`` and ``event_at`` come from different fields where the
  source publishes both;
* ``first_observed_at`` equals the fetch clock and is never back-filled;
* job postings keep ``first_published`` separate from ``updated_at``, and an
  epoch-millisecond date is converted exactly once;
* a ``candidate`` company link is never promoted to a confirmed one;
* collection is bounded by ``limit``.

Run:  python -m unittest tests.test_extsrc_procurement -v
"""

from __future__ import annotations

import unittest
from typing import Any

from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources.procurement import common
from medradar.external_sources.procurement import greenhouse
from medradar.external_sources.procurement import lever
from medradar.external_sources.procurement import uk_find_a_tender
from medradar.external_sources.procurement import usaspending

FETCHED_AT = "2026-11-09T04:00:00Z"


# --------------------------------------------------------------------- fakes
class _FakeResult:
    """Minimal stand-in for ``base.HttpResult`` (no network)."""

    def __init__(self, payload: Any, *, status: int = 200) -> None:
        self._payload = payload
        self.status = status
        self.url = "https://example.invalid/"
        self.body = b""
        self.error = "" if status < 400 else f"HTTP {status}"

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    """Records calls and returns canned payloads."""

    def __init__(self, *, post: Any = None, get: Any = None) -> None:
        self._post = post
        self._get = get
        self.calls: list[tuple[str, str, Any]] = []

    def post_json(self, url: str, payload: Any, **_: Any) -> _FakeResult:
        self.calls.append(("POST", url, payload))
        return _FakeResult(self._post)

    def get(self, url: str, **kwargs: Any) -> _FakeResult:
        self.calls.append(("GET", url, kwargs))
        return _FakeResult(self._get)

    def requests_made(self) -> int:
        return len(self.calls)


def _award_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "Award ID": "W91YU013P0422",
        "Recipient Name": "MEDTRONIC INC",
        "Award Amount": 13055.0,
        "Start Date": "2013-04-11",
        "End Date": "2014-04-10",
        "Awarding Agency": "Department of Defense",
        "Awarding Sub Agency": "Department of the Army",
        "Contract Award Type": "PURCHASE ORDER",
        "Description": "STENT DELIVERY SYSTEM",
        "generated_internal_id": "CONT_AWD_W91YU013P0422_9700_-NONE-_-NONE-",
    }
    row.update(overrides)
    return row


def _uk_release(*, tag: list[str], with_contract: bool = True) -> dict[str, Any]:
    release: dict[str, Any] = {
        "ocid": "ocds-h6vhtk-07b710",
        "id": "105976-2026",
        "date": "2026-11-08T20:14:58Z",
        "tag": list(tag),
        "tender": {
            "title": "Surgical consumables",
            "status": "complete",
            "mainProcurementCategory": "goods",
            "classification": {"scheme": "CPV", "id": "33140000", "description": "Medical consumables"},
        },
        "awards": [
            {
                "id": "105976-2026-1",
                "date": None,
                "status": "active",
                "suppliers": [{"name": "Medtronic Limited", "id": "GB-FTS-188248"}],
            }
        ],
    }
    if with_contract:
        release["contracts"] = [
            {
                "id": "105976-2026-1",
                "awardID": "105976-2026-1",
                "status": "active",
                "dateSigned": "2026-10-28T00:00:00Z",
                "value": {"amount": 125460.0, "currency": "GBP"},
            }
        ]
    return release


def _greenhouse_job(**overrides: Any) -> dict[str, Any]:
    job = {
        "id": 8172487,
        "internal_job_id": 4001,
        "requisition_id": "REQ-17",
        "title": "Senior R&D Engineer, Catheter Design",
        "updated_at": "2026-10-29T10:42:09-04:00",
        "first_published": "2026-09-03T13:30:34-04:00",
        "location": {"name": "Dublin"},
        "absolute_url": "https://example.invalid/jobs/8172487",
        "company_name": "Medtronic",
        "metadata": None,
    }
    job.update(overrides)
    return job


def _lever_posting(**overrides: Any) -> dict[str, Any]:
    posting = {
        "id": "ad208490-4052-4f91-a57e-433f2d1e484b",
        "text": "Customer Success Manager",
        "createdAt": 1788199939703,
        "hostedUrl": "https://example.invalid/lever/1",
        "categories": {
            "department": "Sales",
            "team": "EMEA",
            "location": "Atlanta, Georgia",
            "commitment": "Regular Full Time (Salary)",
        },
    }
    posting.update(overrides)
    return posting


# ------------------------------------------------------------------ helpers
class _IndexMixin:
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = ev_identity.CompanyIndex.from_config()


# ------------------------------------------------------------------ pure fns
class TestCommonHelpers(unittest.TestCase):
    def test_epoch_millis_converts_once(self) -> None:
        iso, quality = common.epoch_millis_to_iso(1788199939703)
        self.assertEqual(iso, "2026-08-31T18:12:19.703000Z")
        self.assertEqual(quality, "exact")
        # a value that is clearly seconds must not be multiplied
        iso_s, _ = common.epoch_millis_to_iso(1788199939)
        self.assertTrue(iso_s.startswith("2026-"))
        # nonsense must not become a date
        self.assertEqual(common.epoch_millis_to_iso("not-a-number"), ("", "unknown"))
        self.assertEqual(common.epoch_millis_to_iso(None), ("", "unknown"))
        self.assertEqual(common.epoch_millis_to_iso(0), ("", "unknown"))
        self.assertEqual(common.epoch_millis_to_iso(True), ("", "unknown"))

    def test_clip_collapses_whitespace(self) -> None:
        self.assertEqual(common.clip("  a \n b  "), "a b")
        self.assertEqual(common.clip(None), "")
        self.assertEqual(len(common.clip("x" * 50, 10)), 10)

    def test_date_quality_downgrades_to_worst(self) -> None:
        self.assertEqual(common.date_quality("2026-11-08T20:14:58Z"), "exact")
        self.assertEqual(common.date_quality("2026-11-08"), "day")
        self.assertEqual(common.date_quality("2026-11"), "coarse")
        self.assertEqual(common.date_quality("2026-11-08", "2026-11"), "coarse")
        self.assertEqual(common.date_quality(None, ""), "unknown")

    def test_dedupe_report_counts_instances_not_rows(self) -> None:
        rows = [
            {"company": "Acme", "title": "Engineer", "location": "Dublin"},
            {"company": "acme ", "title": "engineer", "location": "DUBLIN"},
            {"company": "Acme", "title": "Sales Rep", "location": "Dublin"},
        ]
        report = common.dedupe_report(rows, ("company", "title", "location"))
        self.assertEqual(report["n_items"], 3)
        self.assertEqual(report["n_business_keys"], 2)
        self.assertEqual(report["duplicate_instances"], 1)
        self.assertEqual(report["duplicate_rate"], round(1 / 3, 4))

    def test_dedupe_report_empty(self) -> None:
        report = common.dedupe_report([], ("company",))
        self.assertEqual(report["duplicate_rate"], 0.0)


class TestUsaspendingPure(unittest.TestCase):
    def test_payload_is_post_body_with_filters(self) -> None:
        payload = usaspending.build_search_payload(keywords=["stent"], limit=5, page=2)
        self.assertEqual(payload["filters"]["keywords"], ["stent"])
        self.assertEqual(payload["filters"]["award_type_codes"], ["A", "B", "C", "D"])
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["page"], 2)
        self.assertIn("Description", payload["fields"])

    def test_payload_recipient_search(self) -> None:
        payload = usaspending.build_search_payload(recipient="Medtronic")
        self.assertEqual(payload["filters"]["recipient_search_text"], ["Medtronic"])
        self.assertNotIn("keywords", payload["filters"])

    def test_record_id_prefers_generated_internal_id(self) -> None:
        self.assertEqual(
            usaspending.award_record_id(_award_row()),
            "CONT_AWD_W91YU013P0422_9700_-NONE-_-NONE-",
        )
        self.assertEqual(
            usaspending.award_record_id(_award_row(**{"generated_internal_id": ""})),
            "W91YU013P0422",
        )


class TestUkPure(unittest.TestCase):
    def test_release_kind_separates_stages(self) -> None:
        self.assertEqual(uk_find_a_tender.release_kind({"tag": ["tender"]}), "procurement_notice")
        self.assertEqual(
            uk_find_a_tender.release_kind({"tag": ["tender", "tenderAmendment"]}),
            "procurement_notice",
        )
        self.assertEqual(
            uk_find_a_tender.release_kind({"tag": ["award", "contract"]}), "procurement_award"
        )
        self.assertEqual(uk_find_a_tender.release_kind({"tag": ["contract"]}), "procurement_award")
        # unknown/no tag must not default to "award": that would over-claim
        self.assertEqual(uk_find_a_tender.release_kind({"tag": []}), "procurement_notice")
        self.assertEqual(uk_find_a_tender.release_kind({}), "procurement_notice")
        self.assertEqual(uk_find_a_tender.release_kind({"tag": "award"}), "procurement_award")

    def test_release_record_id_shape(self) -> None:
        self.assertEqual(
            uk_find_a_tender.release_record_id({"ocid": "ocds-x", "id": "42"}), "ocds-x#42"
        )


class TestHiringPure(unittest.TestCase):
    def test_greenhouse_role_heuristic_is_labelled(self) -> None:
        self.assertEqual(greenhouse.classify_role_heuristic("Senior R&D Engineer"), "rnd")
        self.assertEqual(greenhouse.classify_role_heuristic("Territory Sales Manager"), "sales")
        self.assertEqual(greenhouse.classify_role_heuristic("Manufacturing Technician"), "production")
        self.assertEqual(greenhouse.classify_role_heuristic("Office Manager"), "unknown")
        self.assertEqual(greenhouse.classify_role_heuristic(None), "unknown")

    def test_lever_department_role_uses_real_field(self) -> None:
        self.assertEqual(lever.department_role("Sales"), "sales")
        self.assertEqual(lever.department_role("Engineering"), "rnd")
        self.assertEqual(lever.department_role("Manufacturing"), "production")
        self.assertEqual(lever.department_role(None), "unknown")
        self.assertEqual(lever.department_role(""), "unknown")

    def test_lever_department_coverage_is_measured(self) -> None:
        records = [
            {"normalized": {"department_available": True, "department_role": "sales"}},
            {"normalized": {"department_available": False, "department_role": "unknown"}},
        ]
        coverage = lever.department_coverage(records)
        self.assertEqual(coverage["n_postings"], 2)
        self.assertEqual(coverage["n_with_department"], 1)
        self.assertEqual(coverage["coverage_rate"], 0.5)
        self.assertEqual(coverage["role_counts_over_covered_postings"], {"sales": 1})


# ------------------------------------------------------------------ evidence
class TestUsaspendingEvidence(_IndexMixin, unittest.TestCase):
    def test_evidence_is_valid_and_has_no_publication_date(self) -> None:
        record = usaspending.to_evidence(_award_row(), fetched_at=FETCHED_AT, company_index=self.index)
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "procurement_award")
        # the source publishes no publication clock: it must stay empty, not be
        # borrowed from Start Date
        self.assertEqual(record["time"]["source_public_at"], "")
        self.assertEqual(record["time"]["source_public_at_quality"], "unknown")
        self.assertEqual(record["time"]["event_at"], "2013-04-11")
        self.assertNotEqual(record["time"]["event_at"], record["time"]["source_public_at"])
        self.assertEqual(record["time"]["first_observed_at"], FETCHED_AT)
        self.assertEqual(record["time"]["fetched_at"], FETCHED_AT)

    def test_amount_semantics_are_stated(self) -> None:
        record = usaspending.to_evidence(_award_row(), fetched_at=FETCHED_AT, company_index=self.index)
        self.assertEqual(record["normalized"]["award_amount_usd"], 13055.0)
        self.assertIn("not supplier revenue", record["normalized"]["amount_semantics"])
        self.assertIn("no UDI", record["normalized"]["product_link"])

    def test_missing_amount_is_null_not_zero(self) -> None:
        record = usaspending.to_evidence(
            _award_row(**{"Award Amount": None}), fetched_at=FETCHED_AT, company_index=self.index
        )
        self.assertIsNone(record["normalized"]["award_amount_usd"])
        self.assertEqual(ev_schema.validate_evidence(record), [])

    def test_confirmed_supplier_link(self) -> None:
        record = usaspending.to_evidence(_award_row(), fetched_at=FETCHED_AT, company_index=self.index)
        ref = record["entity_refs"][0]
        self.assertEqual(ref["resolved_key"], "medtronic")
        self.assertEqual(ref["method"], "exact_alias")
        self.assertGreaterEqual(ref["confidence"], 0.9)

    def test_unrelated_recipient_is_not_linked(self) -> None:
        record = usaspending.to_evidence(
            _award_row(**{"Recipient Name": "CHANGE HEALTHCARE TECHNOLOGIES, LLC"}),
            fetched_at=FETCHED_AT,
            company_index=self.index,
        )
        ref = record["entity_refs"][0]
        self.assertIsNone(ref["resolved_key"])
        self.assertEqual(ref["method"], "none")

    def test_signature_date_helper_keeps_both_dates(self) -> None:
        detail = {
            "date_signed": "2024-02-01",
            "period_of_performance": {"start_date": "2024-03-01"},
        }
        diff = usaspending.signature_date_mismatch(detail)
        self.assertEqual(diff["date_signed"], "2024-02-01")
        self.assertEqual(diff["period_of_performance_start"], "2024-03-01")
        self.assertEqual(diff["days_between_signature_and_performance_start"], 29)


class TestUkEvidence(_IndexMixin, unittest.TestCase):
    def test_award_release_has_publication_and_event_dates_from_different_fields(self) -> None:
        record = uk_find_a_tender.to_evidence(
            _uk_release(tag=["award", "contract"]), fetched_at=FETCHED_AT, company_index=self.index
        )
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "procurement_award")
        self.assertEqual(record["time"]["source_public_at"], "2026-11-08")
        self.assertEqual(record["time"]["event_at"], "2026-10-28")
        self.assertNotEqual(record["time"]["event_at"], record["time"]["source_public_at"])
        self.assertEqual(record["normalized"]["contract_value"], 125460.0)
        self.assertEqual(record["normalized"]["contract_value_currency"], "GBP")
        self.assertEqual(record["normalized"]["suppliers"][0]["name"], "Medtronic Limited")

    def test_tender_release_has_no_event_date(self) -> None:
        record = uk_find_a_tender.to_evidence(
            _uk_release(tag=["tender"], with_contract=False),
            fetched_at=FETCHED_AT,
            company_index=self.index,
        )
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "procurement_notice")
        self.assertEqual(record["time"]["source_public_at"], "2026-11-08")
        self.assertEqual(record["time"]["event_at"], "")
        self.assertEqual(record["normalized"]["contract_value"], None)

    def test_supplier_resolution_uses_ocds_identifier_evidence(self) -> None:
        record = uk_find_a_tender.to_evidence(
            _uk_release(tag=["award", "contract"]), fetched_at=FETCHED_AT, company_index=self.index
        )
        ref = record["entity_refs"][0]
        self.assertEqual(ref["resolved_key"], "medtronic")
        self.assertIn(ref["method"], {"exact_alias", "multi_field"})

    def test_split_by_stage_never_merges(self) -> None:
        tender = uk_find_a_tender.to_evidence(
            _uk_release(tag=["tender"], with_contract=False), fetched_at=FETCHED_AT, company_index=self.index
        )
        award = uk_find_a_tender.to_evidence(
            _uk_release(tag=["award", "contract"]), fetched_at=FETCHED_AT, company_index=self.index
        )
        self.assertEqual(
            uk_find_a_tender.split_by_stage([tender, award]),
            {"procurement_notice": 1, "procurement_award": 1},
        )


class TestGreenhouseEvidence(_IndexMixin, unittest.TestCase):
    def test_publication_clock_is_first_published_not_updated_at(self) -> None:
        record = greenhouse.to_evidence(
            _greenhouse_job(), fetched_at=FETCHED_AT, company_index=self.index, board_token="stripe"
        )
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "job_posting")
        self.assertEqual(record["time"]["source_public_at"], "2026-09-03")
        self.assertEqual(record["normalized"]["updated_at"], "2026-10-29T10:42:09-04:00")
        self.assertEqual(record["normalized"]["first_published"], "2026-09-03T13:30:34-04:00")
        self.assertNotEqual(record["time"]["source_public_at"], record["normalized"]["updated_at"])
        self.assertEqual(record["time"]["first_observed_at"], FETCHED_AT)
        self.assertEqual(record["time"]["event_at"], "")

    def test_no_department_claim_is_made(self) -> None:
        record = greenhouse.to_evidence(
            _greenhouse_job(), fetched_at=FETCHED_AT, company_index=self.index, board_token="stripe"
        )
        self.assertFalse(record["normalized"]["department_available"])
        self.assertEqual(record["normalized"]["department"], "")
        self.assertIn("not a source field", record["normalized"]["role_heuristic_caveat"])

    def test_identical_fetch_is_idempotent(self) -> None:
        first = greenhouse.to_evidence(
            _greenhouse_job(), fetched_at=FETCHED_AT, company_index=self.index, board_token="stripe"
        )
        second = greenhouse.to_evidence(
            _greenhouse_job(), fetched_at=FETCHED_AT, company_index=self.index, board_token="stripe"
        )
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertEqual(first["content_hash"], second["content_hash"])


class TestLeverEvidence(_IndexMixin, unittest.TestCase):
    def test_epoch_millis_becomes_publication_clock(self) -> None:
        record = lever.to_evidence(
            _lever_posting(), fetched_at=FETCHED_AT, company_index=self.index, company_token="leverdemo"
        )
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["time"]["source_public_at"], "2026-08-31")
        self.assertEqual(record["normalized"]["created_at_iso"], "2026-08-31T18:12:19.703000Z")
        self.assertEqual(record["normalized"]["created_at_raw_epoch_ms"], 1788199939703)

    def test_department_split_comes_from_a_real_field(self) -> None:
        record = lever.to_evidence(
            _lever_posting(), fetched_at=FETCHED_AT, company_index=self.index, company_token="leverdemo"
        )
        self.assertTrue(record["normalized"]["department_available"])
        self.assertEqual(record["normalized"]["department_role"], "sales")

    def test_missing_created_at_is_unknown_not_1970(self) -> None:
        record = lever.to_evidence(
            _lever_posting(**{"createdAt": None}),
            fetched_at=FETCHED_AT,
            company_index=self.index,
            company_token="leverdemo",
        )
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["time"]["source_public_at"], "")
        self.assertEqual(record["time"]["source_public_at_quality"], "unknown")


# ------------------------------------------------------------------- bounds
class TestBoundedCollect(unittest.TestCase):
    def test_usaspending_collect_honours_limit_and_page_bound(self) -> None:
        rows = [_award_row(**{"generated_internal_id": f"ID-{i}"}) for i in range(5)]
        client = _FakeClient(post={"results": rows})
        records = usaspending.collect(client, limit=3, page_size=5, fetched_at=FETCHED_AT)
        self.assertEqual(len(records), 3)
        self.assertEqual(client.requests_made(), 1)

    def test_usaspending_collect_stops_on_failed_request(self) -> None:
        client = _FakeClient()
        client.post_json = lambda url, payload, **kw: _FakeResult(None, status=500)  # type: ignore[method-assign]
        records = usaspending.collect(client, limit=5, fetched_at=FETCHED_AT)
        self.assertEqual(records, [])

    def test_uk_collect_sends_stage_filter_and_bounds_pages(self) -> None:
        releases = [_uk_release(tag=["tender"], with_contract=False)]
        client = _FakeClient(get={"releases": releases})
        records = uk_find_a_tender.collect(
            client, limit=1, stages="tender", page_size=1, max_pages=2, fetched_at=FETCHED_AT
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "procurement_notice")
        # limit=1 must stop after one request even though max_pages allows two
        self.assertEqual(client.requests_made(), 1)
        _, _, kwargs = client.calls[0]
        self.assertEqual(kwargs["params"]["stages"], "tender")

    def test_greenhouse_collect_bounds_records(self) -> None:
        jobs = [_greenhouse_job(**{"id": i}) for i in range(4)]
        client = _FakeClient(get={"jobs": jobs})
        records = greenhouse.collect(client, token="stripe", limit=2, fetched_at=FETCHED_AT)
        self.assertEqual(len(records), 2)
        self.assertEqual(client.requests_made(), 1)
        self.assertEqual(records[0]["source_id"], "greenhouse")

    def test_lever_collect_returns_empty_on_404(self) -> None:
        # a 404 board is a negative result, not an exception: the firm is simply
        # not on Lever
        client = _FakeClient()
        client.get = lambda url, **kw: _FakeResult(None, status=404)  # type: ignore[method-assign]
        records = lever.collect(client, company="medtronic", limit=5, fetched_at=FETCHED_AT)
        self.assertEqual(records, [])

    def test_collect_rejects_non_positive_limit(self) -> None:
        client = _FakeClient(post={"results": []})
        with self.assertRaises(ValueError):
            usaspending.collect(client, limit=0)
        client2 = _FakeClient(get={"jobs": []})
        with self.assertRaises(ValueError):
            greenhouse.collect(client2, token="stripe", limit=0)


class TestModuleContract(unittest.TestCase):
    def test_connector_constants_exist(self) -> None:
        for module in (usaspending, uk_find_a_tender, greenhouse, lever):
            self.assertTrue(getattr(module, "SOURCE_ID", ""))
            self.assertIn(getattr(module, "KIND"), ev_schema.EVIDENCE_KINDS)
            self.assertIn(getattr(module, "LICENCE_STATUS"), ev_schema.LICENCE_STATUSES)
            self.assertTrue(callable(getattr(module, "collect")))
            self.assertTrue(callable(getattr(module, "to_evidence")))

    def test_procurement_kinds_are_distinct_strings(self) -> None:
        self.assertEqual(uk_find_a_tender.TENDER_KIND, "procurement_notice")
        self.assertEqual(uk_find_a_tender.AWARD_KIND, "procurement_award")
        self.assertNotEqual(uk_find_a_tender.TENDER_KIND, uk_find_a_tender.AWARD_KIND)

    def test_candidate_links_are_never_promoted(self) -> None:
        """A guard-hit alias must stay a candidate with confidence < 0.9."""
        index = ev_identity.CompanyIndex.from_config()
        resolution = index.resolve("PHILIPS LIGHTING NORTH AMERICA CORP")
        self.assertEqual(resolution["method"], "candidate")
        self.assertLess(resolution["confidence"], 0.9)
        record = usaspending.to_evidence(
            _award_row(**{"Recipient Name": "PHILIPS LIGHTING NORTH AMERICA CORP"}),
            fetched_at=FETCHED_AT,
            company_index=index,
        )
        self.assertEqual(ev_schema.validate_evidence(record), [])
        self.assertEqual(record["entity_refs"][0]["method"], "candidate")


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
