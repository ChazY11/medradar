"""Offline unit tests for the drug approval collector and the trial normaliser.

No network, no fixtures directory walking beyond ``tests/fixtures/drug``:
a ``FakeFetcher`` replays captured openFDA / CT.gov page shapes so the
eligibility rules (NDA/BLA, ORIG+AP, INTERVENTIONAL, event dating) are pinned
down without touching the real APIs.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any

from medradar import clinical, collect_drug
from medradar.db import DB

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "drug"
TODAY = date(2026, 10, 31)


class FakeFetcher:
    """Minimal Fetcher stand-in: returns canned pages keyed by ``skip``."""

    def __init__(self, pages: dict[int, dict[str, Any]], max_requests: int = 500) -> None:
        self.pages = pages
        self.max_requests = max_requests
        self.stats: dict[str, int] = {
            "requests": 0,
            "cache_hits": 0,
            "retries": 0,
            "errors": 0,
        }
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None, **_: Any) -> Any:
        params = params or {}
        self.calls.append({"url": url, **params})
        self.stats["requests"] += 1
        skip = int(params.get("skip") or 0)
        if skip in self.pages:
            return self.pages[skip]
        return {"meta": {"results": {"skip": skip, "limit": 1000, "total": 0}}, "results": []}


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class DrugApprovalRuleTests(unittest.TestCase):
    def test_nda_and_bla_are_accepted_anda_is_not(self) -> None:
        self.assertTrue(collect_drug.is_nda_or_bla("NDA215859"))
        self.assertTrue(collect_drug.is_nda_or_bla("BLA125742"))
        self.assertTrue(collect_drug.is_nda_or_bla(" nda021436 "))  # normalised
        self.assertFalse(collect_drug.is_nda_or_bla("ANDA205504"))
        self.assertFalse(collect_drug.is_nda_or_bla("NDA"))
        self.assertFalse(collect_drug.is_nda_or_bla(""))
        self.assertFalse(collect_drug.is_nda_or_bla(None))

    def test_only_original_approved_submissions(self) -> None:
        self.assertTrue(
            collect_drug.is_original_approval(
                {"submission_type": "ORIG", "submission_status": "AP"}
            )
        )
        self.assertFalse(  # supplement, not the original approval
            collect_drug.is_original_approval(
                {"submission_type": "SUPPL", "submission_status": "AP"}
            )
        )
        self.assertFalse(  # tentative approval
            collect_drug.is_original_approval(
                {"submission_type": "ORIG", "submission_status": "TA"}
            )
        )
        self.assertFalse(collect_drug.is_original_approval({}))

    def test_anda_original_approval_is_rejected_end_to_end(self) -> None:
        record = {
            "application_number": "ANDA205504",
            "sponsor_name": "HETERO LABS LTD V",
            "submissions": [
                {
                    "submission_type": "ORIG",
                    "submission_status": "AP",
                    "submission_status_date": "20240104",
                    "submission_number": "1",
                }
            ],
            "products": [{"brand_name": "ESZOPICLONE"}],
        }
        event = collect_drug.normalize_approval(
            record, record["submissions"][0], as_of=TODAY.isoformat()
        )
        self.assertIsNone(event)


class DrugNormalisationTests(unittest.TestCase):
    def _record(self) -> dict[str, Any]:
        return {
            "application_number": "NDA215859",
            "sponsor_name": "ELI LILLY AND COMPANY",
            "submissions": [
                {
                    "submission_type": "ORIG",
                    "submission_status": "AP",
                    "submission_status_date": "20220513",
                    "submission_number": "1",
                    "submission_class_code": "TYPE 1",
                }
            ],
            "openfda": {"brand_name": ["MOUNJARO"], "generic_name": ["TIRZEPATIDE"]},
            "products": [
                {
                    "brand_name": "MOUNJARO",
                    "active_ingredients": [{"name": "TIRZEPATIDE", "strength": "2.5MG"}],
                }
            ],
        }

    def test_event_shape_and_normalised_payload(self) -> None:
        record = self._record()
        event = collect_drug.normalize_approval(
            record,
            record["submissions"][0],
            company_key="lilly",
            confidence=0.95,
            alias="ELI LILLY",
            as_of=TODAY.isoformat(),
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["kind"], "drug_approval")
        self.assertEqual(event["source"], "openfda_drug_drugsfda")
        self.assertEqual(event["event_date"], "20220513")
        self.assertEqual(event["company_key"], "lilly")
        self.assertEqual(event["applicant_raw"], "ELI LILLY AND COMPANY")
        self.assertEqual(event["title"], "MOUNJARO (TIRZEPATIDE)")
        self.assertIn("ApplNo=215859", event["url"])

        payload = event["payload"]
        self.assertEqual(payload["application_number"], "NDA215859")
        self.assertEqual(payload["sponsor_name"], "ELI LILLY AND COMPANY")
        self.assertEqual(payload["brand_name"], "MOUNJARO")
        self.assertEqual(payload["active_ingredient"], "TIRZEPATIDE")
        self.assertEqual(payload["submission_class_code"], "TYPE 1")
        self.assertEqual(payload["submission_status_date"], "20220513")
        self.assertEqual(payload["raw"], record)

    def test_supplement_and_missing_date_are_dropped(self) -> None:
        record = self._record()
        supplement = dict(record["submissions"][0], submission_type="SUPPL")
        self.assertIsNone(collect_drug.normalize_approval(record, supplement))
        undated = dict(record["submissions"][0], submission_status_date="")
        self.assertIsNone(collect_drug.normalize_approval(record, undated))


class DrugCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DB(Path(self.tmp.name) / "test.sqlite")
        self.addCleanup(self.db.close)

    def _fetcher(self) -> FakeFetcher:
        return FakeFetcher(
            {0: load_fixture("drugsfda_page1.json"), 1000: load_fixture("drugsfda_page2.json")}
        )

    def test_collect_pages_past_filters_and_dedupes(self) -> None:
        fetcher = self._fetcher()
        stats = collect_drug.collect(self.db, fetcher, months=1200, today=TODAY)

        # NDA215859 (Lilly), BLA125742 (Moderna), NDA888888 (unmatched);
        # ANDA excluded, tentative approval excluded, duplicated page row deduped.
        self.assertEqual(stats["events"], 3)
        self.assertEqual(stats["per_kind"], {"drug_approval": 3})
        self.assertEqual(stats["pages"], 2)
        self.assertEqual(stats["documents"], 6)
        self.assertEqual(stats["matched"], 2)
        self.assertAlmostEqual(stats["match_rate"], 2 / 3, places=4)
        self.assertEqual(stats["top_unmatched"], [["TINY UNKNOWN PHARMA LLC", 1]])
        self.assertEqual(stats["requests"], 2)
        self.assertFalse(stats["truncated"])

        rows = self.db.query(
            "SELECT event_id, event_date, company_key, title FROM events"
            " WHERE kind = 'drug_approval' ORDER BY event_date"
        )
        self.assertEqual(
            [row["event_date"] for row in rows],
            ["2022-05-13", "2022-08-23", "2023-06-01"],
        )
        self.assertEqual(rows[0]["company_key"], "lilly")
        self.assertIsNone(rows[2]["company_key"])
        self.assertEqual(len({row["event_id"] for row in rows}), 3)

        # ANDA rows never reach the events table.
        self.assertEqual(
            self.db.query("SELECT * FROM events WHERE title LIKE '%ESZOPICLONE%'"), []
        )

        # The query is the documented openFDA submission-status-date range.
        first = fetcher.calls[0]
        self.assertEqual(first["url"], collect_drug.API_URL)
        self.assertIn("submissions.submission_status_date:[", first["search"])
        self.assertEqual(first["skip"], 0)
        self.assertEqual(fetcher.calls[1]["skip"], 1000)

    def test_collect_is_idempotent(self) -> None:
        collect_drug.collect(self.db, self._fetcher(), months=1200, today=TODAY)
        collect_drug.collect(self.db, self._fetcher(), months=1200, today=TODAY)
        self.assertEqual(self.db.table_count("events"), 3)

    def test_window_excludes_older_approvals(self) -> None:
        stats = collect_drug.collect(self.db, self._fetcher(), months=12, today=TODAY)
        self.assertEqual(stats["events"], 0)
        self.assertEqual(self.db.table_count("events"), 0)
        self.assertEqual(stats["window"], {"start": "2025-10-31", "end": "2026-10-31"})


# ---------------------------------------------------------------- trial (CT.gov)
def _study(
    nct_id: str,
    *,
    posted: str = "2025-05-01",
    study_type: str = "INTERVENTIONAL",
    sponsor: str = "Eli Lilly and Company",
    conditions: list[str] | None = None,
    phases: list[str] | None = None,
    enrollment: int | None = 120,
) -> dict[str, Any]:
    design: dict[str, Any] = {"studyType": study_type}
    if phases is not None:
        design["phases"] = phases
    if enrollment is not None:
        design["enrollmentInfo"] = {"count": enrollment}
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": f"Study {nct_id}"},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "startDateStruct": {"date": "2025-01"},
                "studyFirstPostDateStruct": {"date": posted},
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
            "conditionsModule": {"conditions": conditions or ["Type 2 Diabetes"]},
            "designModule": design,
        }
    }


TINY_COMPANY = {
    "key": "lilly",
    "name_en": "Eli Lilly",
    "name_zh": "礼来",
    "ticker": "LLY",
    "is_major": 1,
    "aliases": ["ELI LILLY"],
}


class TrialNormalisationTests(unittest.TestCase):
    def test_phase_is_uppercase_and_early_phase1_maps_to_phase1(self) -> None:
        self.assertEqual(clinical.normalize_phase(["Phase 3"]), ["PHASE3"])
        self.assertEqual(clinical.normalize_phase(["EARLY_PHASE1", "PHASE2"]), ["PHASE1", "PHASE2"])
        self.assertEqual(clinical.normalize_phase(["weird"]), ["NA"])
        self.assertEqual(clinical.normalize_phase(None), [])
        self.assertEqual(clinical.normalize_phase([]), [])

    def test_payload_contract(self) -> None:
        payload = clinical.normalize_study(_study("NCT00000001", phases=["PHASE3"]))
        assert payload is not None
        self.assertEqual(payload["nct_id"], "NCT00000001")
        self.assertEqual(payload["phase"], ["PHASE3"])
        self.assertEqual(payload["status"], "RECRUITING")
        self.assertEqual(payload["conditions"], ["Type 2 Diabetes"])
        self.assertEqual(payload["enrollment"], 120)
        self.assertEqual(payload["study_type"], "INTERVENTIONAL")
        self.assertEqual(payload["lead_sponsor"], "Eli Lilly and Company")
        self.assertEqual(payload["first_posted"], "2025-05-01")
        self.assertEqual(payload["raw"], _study("NCT00000001", phases=["PHASE3"]))

    def test_missing_first_posted_and_observational_are_rejected(self) -> None:
        broken = _study("NCT00000002")
        del broken["protocolSection"]["statusModule"]["studyFirstPostDateStruct"]
        self.assertIsNone(clinical.normalize_study(broken))
        self.assertIsNone(clinical.normalize_study(_study("NCT00000003", study_type="OBSERVATIONAL")))
        no_id = _study("")
        self.assertIsNone(clinical.normalize_study(no_id))


class TrialCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = DB(Path(self.tmp.name) / "test.sqlite")
        self.addCleanup(self.db.close)

    def test_query_terms_use_parent_name_plus_one_alias(self) -> None:
        lilly = {"name_en": "Eli Lilly", "aliases": ["ELI LILLY", "LILLY"]}
        self.assertEqual(clinical.query_terms(lilly), ["ELI LILLY"])
        jnj = {
            "name_en": "Johnson & Johnson Innovative Medicine",
            "aliases": ["JANSSEN", "JANSSEN BIOTECH"],
        }
        self.assertEqual(clinical.query_terms(jnj), ["JOHNSON JOHNSON", "JANSSEN"])
        merck = {"name_en": "Merck & Co.", "aliases": ["MERCK SHARP DOHME", "MSD"]}
        self.assertEqual(clinical.query_terms(merck), ["MERCK", "MERCK SHARP DOHME"])

    def test_plan_terms_dedupes_across_both_watchlists(self) -> None:
        drug = {"key": "jnj_pharma", "name_en": "Johnson & Johnson Innovative Medicine",
                "aliases": ["JANSSEN"], "is_major": 1}
        device = {"key": "johnson_johnson_medtech", "name_en": "Johnson & Johnson MedTech",
                  "aliases": ["JOHNSON & JOHNSON"], "is_major": 1}
        self.assertEqual(clinical.plan_terms([device, drug]), ["JOHNSON JOHNSON", "JANSSEN"])

    def test_collect_keeps_interventional_in_window_and_flags_unmatched(self) -> None:
        studies = [
            _study("NCT00000001"),
            _study("NCT00000002", study_type="OBSERVATIONAL"),
            _study("NCT00000003", posted="2020-01-01"),
            _study("NCT00000004", sponsor="Unknown Sponsor LLC"),
        ]
        fetcher = FakeFetcher({0: {"studies": studies, "totalCount": 4}})
        stats = clinical.collect_trials(
            self.db,
            fetcher,
            months=24,
            today=TODAY,
            companies=[TINY_COMPANY],
        )
        self.assertEqual(stats["events"], 2)
        self.assertEqual(stats["per_kind"], {"trial": 2})
        self.assertEqual(stats["interventional"], 3)
        self.assertEqual(stats["in_window"], 2)
        self.assertEqual(stats["matched"], 1)
        self.assertAlmostEqual(stats["match_rate"], 0.5)
        self.assertEqual(stats["unmatched"], 1)
        self.assertEqual(stats["track_matched"], 2)
        self.assertEqual(stats["top_unmatched"], [["Unknown Sponsor LLC", 1]])

        rows = self.db.query(
            "SELECT * FROM events WHERE kind = 'trial' ORDER BY company_key IS NOT NULL DESC"
        )
        self.assertEqual(len(rows), 2)
        resolved = [row for row in rows if row["company_key"]]
        unresolved = [row for row in rows if not row["company_key"]]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["event_date"], "2025-05-01")
        self.assertEqual(resolved[0]["track_id"], "t_cardiometabolic")
        # Unmatched sponsors are still stored (SCHEMA §6: company_key NULL) so
        # their therapeutic-area signal is not thrown away.
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["applicant_raw"], "Unknown Sponsor LLC")
        payload = json.loads(resolved[0]["payload"])
        self.assertEqual(payload["nct_id"], "NCT00000001")
        self.assertEqual(payload["phase"], [])  # phases absent in the fixture
        self.assertIn("raw", payload)
        self.assertEqual(fetcher.calls[0]["query.spons"], "ELI LILLY")
        self.assertEqual(fetcher.calls[0]["pageSize"], 100)
        self.assertIn("StudyFirstPostDate", fetcher.calls[0]["sort"])
        self.assertIn("RANGE", fetcher.calls[0]["filter.advanced"])

    def test_collect_is_idempotent(self) -> None:
        studies = [_study("NCT00000001")]
        clinical.collect_trials(
            self.db,
            FakeFetcher({0: {"studies": studies, "totalCount": 1}}),
            months=24,
            today=TODAY,
            companies=[TINY_COMPANY],
        )
        clinical.collect_trials(
            self.db,
            FakeFetcher({0: {"studies": studies, "totalCount": 1}}),
            months=24,
            today=TODAY,
            companies=[TINY_COMPANY],
        )
        self.assertEqual(self.db.table_count("events"), 1)


if __name__ == "__main__":
    unittest.main()
