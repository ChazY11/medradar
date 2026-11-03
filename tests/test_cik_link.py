"""Tests for B-029 / b101 CIK-based deterministic 8-K linking.

The point of the linking rule is what it refuses as much as what it accepts:
a curated CIK mapping to two company keys must be refused, a near-name string
must never link, and the whole run must be byte-identical across repeats.  The
real store currently yields zero *new* links, so the end-to-end fixture below
also proves the code does link when a curated CIK actually resolves - the zero
is a property of the data, not of the resolver.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "b101_cik_link" / "link_cik.py"
SEED = 20261103


def load_module():
    spec = importlib.util.spec_from_file_location("b101_link_cik", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_event(
    event_id: str,
    cik,
    company_key: str = "",
    applicant: str = "",
    accession: str = "",
    payload_ok: bool = True,
) -> dict:
    payload = {"cik": cik, "accession": accession or f"acc-{event_id}"}
    return {
        "event_id": event_id,
        "company_key": company_key,
        "applicant_raw": applicant,
        "title": f"{applicant or event_id} · event",
        "payload": payload if payload_ok else None,
        "payload_ok": payload_ok,
        "cik": None if payload_ok is False else cik,
        "accession": payload["accession"],
    }


def json_dump(payload) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


class ModuleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="b101-"))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    # -------------------------------------------------------------- fixtures
    def make_store(self, path: Path, events: list[dict], companies: list[tuple[str, str]] = ()) -> Path:
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE events (event_id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT, "
                "event_date TEXT, company_key TEXT, applicant_raw TEXT, title TEXT, payload TEXT)"
            )
            connection.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, cik TEXT)")
            for event in events:
                connection.execute(
                    "INSERT INTO events(event_id, source, kind, company_key, applicant_raw, title, payload) "
                    "VALUES (?, 'sec_edgar_corpus', '8k_catalyst', ?, ?, ?, ?)",
                    (
                        event["event_id"],
                        event["company_key"] or None,
                        event["applicant_raw"],
                        event["title"],
                        json.dumps(event["payload"]) if event["payload"] is not None else None,
                    ),
                )
            connection.executemany("INSERT INTO companies(key, cik) VALUES (?, ?)", list(companies))
            connection.commit()
        finally:
            connection.close()
        return path

    def make_research(
        self,
        path: Path,
        identifiers: list[tuple[str, str, str, str]],
        companies: list[tuple[str, str]] = (),
    ) -> Path:
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE company_identifiers (company_key TEXT NOT NULL, scheme TEXT NOT NULL, "
                "identifier TEXT NOT NULL, source TEXT NOT NULL, valid_from TEXT, valid_to TEXT, "
                "available_at TEXT NOT NULL, confidence REAL NOT NULL, evidence TEXT, "
                "PRIMARY KEY (company_key, scheme, identifier, source))"
            )
            connection.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, cik TEXT)")
            for company_key, scheme, identifier, source in identifiers:
                connection.execute(
                    "INSERT INTO company_identifiers(company_key, scheme, identifier, source, available_at, "
                    "confidence) VALUES (?, ?, ?, ?, '2026-11-01T00:00:00Z', 1.0)",
                    (company_key, scheme, identifier, source),
                )
            connection.executemany("INSERT INTO companies(key, cik) VALUES (?, ?)", list(companies))
            connection.commit()
        finally:
            connection.close()
        return path

    def make_registry(self, path: Path, curated: dict[int, str], ambiguous: dict[int, list[str]] = None) -> Path:
        companies = {
            self.module.cik10(cik): {
                "cik_int": cik,
                "company_key": company_key,
                "ticker": "",
                "evidence": ["company_identifiers:test"],
            }
            for cik, company_key in curated.items()
        }
        ambiguous = ambiguous or {}
        document = {
            "schema": self.module.REGISTRY_SCHEMA,
            "built_by": "test",
            "rule": "test fixture",
            "provenance": {},
            "companies": companies,
            "ambiguous": {
                self.module.cik10(cik): {"cik_int": cik, "companies": sorted(names)}
                for cik, names in ambiguous.items()
            },
        }
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


# --------------------------------------------------------------------- CIK form
class CikNormalisationTests(ModuleTestCase):
    def test_integer_stays_integer(self) -> None:
        self.assertEqual(self.module.normalise_cik(1613103), 1613103)
        self.assertEqual(self.module.normalise_cik(1), 1)

    def test_ten_digit_zero_padded_string(self) -> None:
        self.assertEqual(self.module.normalise_cik("0001613103"), 1613103)

    def test_leading_zeros_and_whitespace(self) -> None:
        self.assertEqual(self.module.normalise_cik("0000001800"), 1800)
        self.assertEqual(self.module.normalise_cik("  1800  "), 1800)
        self.assertEqual(self.module.normalise_cik(1800), 1800)

    def test_integral_float_from_json(self) -> None:
        self.assertEqual(self.module.normalise_cik(1586049.0), 1586049)

    def test_rejects_non_cik_values(self) -> None:
        for value in (None, "", "   ", "0", "0000000000", 0, -5, "12a", "1,800", True, False, 1800.5):
            with self.subTest(value=value):
                self.assertIsNone(self.module.normalise_cik(value))

    def test_cik10_roundtrip(self) -> None:
        self.assertEqual(self.module.cik10(1800), "0000001800")
        self.assertEqual(self.module.normalise_cik(self.module.cik10(1613103)), 1613103)


# --------------------------------------------------------------------- registry
class RegistryBuildTests(ModuleTestCase):
    def test_identifier_and_ticker_evidence_merge(self) -> None:
        registry = self.module.build_curated_registry(
            identifier_rows=[("abbott", "0000001800", "sec_company_tickers")],
            candidate_rows=[{"cik": 1800, "ticker": "ABT"}],
            company_tickers={"ABT": {"abbott"}},
        )
        self.assertEqual(list(registry["companies"]), ["0000001800"])
        entry = registry["companies"]["0000001800"]
        self.assertEqual(entry["company_key"], "abbott")
        self.assertEqual(entry["cik_int"], 1800)
        self.assertIn("company_identifiers:sec_company_tickers", entry["evidence"])
        self.assertIn("sec_ticker:ABT", entry["evidence"])
        self.assertEqual(registry["ambiguous"], {})

    def test_shared_ticker_is_ambiguous_and_never_curated(self) -> None:
        registry = self.module.build_curated_registry(
            identifier_rows=[],
            candidate_rows=[{"cik": 200406, "ticker": "JNJ"}],
            company_tickers={"JNJ": {"jnj_pharma", "johnson_johnson_medtech"}},
        )
        self.assertEqual(registry["companies"], {})
        self.assertIn("0000200406", registry["ambiguous"])
        self.assertEqual(registry["ambiguous"]["0000200406"]["companies"], ["jnj_pharma", "johnson_johnson_medtech"])

    def test_identifier_and_ticker_disagreement_is_ambiguous(self) -> None:
        registry = self.module.build_curated_registry(
            identifier_rows=[("abbott", "0000001800", "sec_company_tickers")],
            candidate_rows=[{"cik": 1800, "ticker": "MDT"}],
            company_tickers={"MDT": {"medtronic"}},
        )
        self.assertEqual(registry["companies"], {})
        self.assertEqual(registry["ambiguous"]["0000001800"]["companies"], ["abbott", "medtronic"])

    def test_blank_tickers_are_ignored(self) -> None:
        registry = self.module.build_curated_registry(
            identifier_rows=[],
            candidate_rows=[{"cik": 1800, "ticker": ""}, {"cik": 1801, "ticker": "   "}],
            company_tickers={"ABT": {"abbott"}},
        )
        self.assertEqual(registry, {"companies": {}, "ambiguous": {}})

    def test_same_company_from_identifier_and_ticker_is_unambiguous(self) -> None:
        registry = self.module.build_curated_registry(
            identifier_rows=[("medtronic", "0001613103", "sec_company_tickers")],
            candidate_rows=[{"cik": 1613103, "ticker": "MDT"}],
            company_tickers={"MDT": {"medtronic"}},
        )
        self.assertIn("0001613103", registry["companies"])
        self.assertNotIn("0001613103", registry["ambiguous"])

    def test_registry_document_is_deterministic(self) -> None:
        def build() -> str:
            registry = self.module.build_curated_registry(
                identifier_rows=[("abbott", "0000001800", "sec_company_tickers")],
                candidate_rows=[{"cik": 1800, "ticker": "ABT"}, {"cik": 1800, "ticker": "ABT"}],
                company_tickers={"ABT": {"abbott"}},
            )
            return json_dump(self.module.registry_document(registry, {"source": "test"}))

        self.assertEqual(build(), build())

    def test_validate_rejects_two_ciks_for_one_company(self) -> None:
        document = {
            "companies": {
                "0000001800": {"cik_int": 1800, "company_key": "abbott"},
                "0000001801": {"cik_int": 1801, "company_key": "abbott"},
            },
            "ambiguous": {},
        }
        with self.assertRaises(self.module.InputError):
            self.module.validate_registry_document(document)

    def test_validate_rejects_curated_and_ambiguous_overlap(self) -> None:
        document = {
            "companies": {"0000001800": {"cik_int": 1800, "company_key": "abbott"}},
            "ambiguous": {"0000001800": {"cik_int": 1800, "companies": ["abbott", "x"]}},
        }
        with self.assertRaises(self.module.InputError):
            self.module.validate_registry_document(document)


# ---------------------------------------------------------------- resolve rule
class ResolveRuleTests(ModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.curated = {
            1800: {"company_key": "abbott", "cik": 1800, "ticker": "ABT", "evidence": ["company_identifiers:test"]},
            1613103: {"company_key": "medtronic", "cik": 1613103, "ticker": "MDT", "evidence": ["sec_ticker:MDT"]},
        }
        self.ambiguous = {200406: {"cik": 200406, "companies": ["jnj_pharma", "johnson_johnson_medtech"]}}

    def test_exact_cik_links_without_any_name_evidence(self) -> None:
        events = [make_event("e1", "0000001800", applicant="COMPLETELY UNRELATED STRING", accession="a1")]
        result = self.module.resolve_events(events, self.curated, self.ambiguous)
        self.assertEqual(len(result["new_links"]), 1)
        record = result["new_links"][0]
        self.assertEqual(record["event_id"], "e1")
        self.assertEqual(record["company_key"], "abbott")
        self.assertEqual(record["cik"], 1800)
        self.assertEqual(record["cik_10"], "0000001800")
        self.assertEqual(record["accession"], "a1")
        self.assertEqual(record["confidence"], 1.0)
        self.assertEqual(record["link_status"], "new")
        self.assertIn("exact CIK match", record["evidence"])
        self.assertIn("no name/similarity evidence used", record["evidence"])

    def test_near_name_string_never_links_without_curated_cik(self) -> None:
        events = [
            make_event("e1", 999999, applicant="MEDTRONIC INC"),
            make_event("e2", 999998, applicant="ABBOTT LABORATORIES"),
            make_event("e3", 999997, applicant="MEDTRONIC"),
        ]
        result = self.module.resolve_events(events, self.curated, self.ambiguous)
        self.assertEqual(result["new_links"], [])
        self.assertEqual(result["funnel"]["linked_now"], 0)
        self.assertEqual(result["unresolved_reasons"]["cik_not_in_curated_registry"], 3)
        self.assertEqual(result["unlinked_distinct_uncurated_ciks"], 3)

    def test_ambiguous_cik_is_refused_and_counted(self) -> None:
        events = [make_event("e1", 200406, applicant="JOHNSON & JOHNSON")]
        result = self.module.resolve_events(events, self.curated, self.ambiguous)
        self.assertEqual(result["new_links"], [])
        self.assertEqual(result["unresolved_reasons"]["cik_ambiguous"], 1)
        self.assertEqual(result["funnel"]["events_cik_ambiguous"], 1)

    def test_payloadless_and_missing_cik_events_are_counted(self) -> None:
        events = [
            {"event_id": "e1", "company_key": "", "applicant_raw": "", "title": "",
             "payload": None, "payload_ok": False, "cik": None, "accession": ""},
            {"event_id": "e2", "company_key": "", "applicant_raw": "", "title": "",
             "payload": {"accession": "a"}, "payload_ok": True, "cik": None, "accession": "a"},
        ]
        result = self.module.resolve_events(events, self.curated, self.ambiguous)
        self.assertEqual(result["unresolved_reasons"]["payload_unparseable"], 1)
        self.assertEqual(result["unresolved_reasons"]["no_cik"], 1)
        self.assertEqual(result["funnel"]["unlinked_with_payload_cik"], 0)

    def test_existing_links_are_audited(self) -> None:
        events = [
            make_event("e1", 1800, company_key="abbott"),
            make_event("e2", 1613103, company_key="abbott"),  # contradiction
            make_event("e3", 777777, company_key="medtronic"),  # unverifiable
            make_event("e4", 200406, company_key="jnj_pharma"),  # ambiguous
        ]
        result = self.module.resolve_events(events, self.curated, self.ambiguous)
        self.assertEqual(len(result["corroborated"]), 1)
        self.assertEqual(result["corroborated"][0]["link_status"], "existing_corroborated")
        self.assertEqual(len(result["mismatches"]), 1)
        self.assertEqual(result["mismatches"][0]["registry_company_key"], "medtronic")
        self.assertEqual(result["funnel"]["already_linked_events"], 4)
        self.assertEqual(result["funnel"]["linked_now"], 0)

    def test_funnel_arithmetic_closes(self) -> None:
        events = [
            make_event("e1", 1800),
            make_event("e2", 1800),
            make_event("e3", 200406),
            make_event("e4", 555555),
            make_event("e5", 1800, company_key="abbott"),
            make_event("e6", 555555, company_key="philips"),
        ]
        result = self.module.resolve_events(events, self.curated, self.ambiguous)
        funnel = result["funnel"]
        self.assertEqual(funnel["sec_8k_events"], 6)
        self.assertEqual(funnel["events_with_payload_cik"], 6)
        self.assertEqual(funnel["unlinked_events"], 4)
        self.assertEqual(funnel["linked_now"], 2)
        self.assertEqual(funnel["events_cik_ambiguous"], 1)
        self.assertEqual(funnel["events_cik_equals_exactly_one_curated_cik"], 3)
        self.assertEqual(
            funnel["events_cik_equals_exactly_one_curated_cik"]
            + funnel["events_cik_ambiguous"]
            + funnel["events_cik_not_in_curated_registry"],
            funnel["sec_8k_events"],
        )


# ------------------------------------------------------------------ determinism
class DeterminismTests(ModuleTestCase):
    def test_resolution_is_order_independent(self) -> None:
        curated = {1800: {"company_key": "abbott", "cik": 1800, "ticker": "", "evidence": []}}
        events = [make_event(f"e{index}", 1800 if index % 2 else 999000 + index) for index in range(20)]
        forwards = self.module.resolve_events(events, curated, {})
        backwards = self.module.resolve_events(list(reversed(events)), curated, {})
        self.assertEqual(json_dump(forwards), json_dump(backwards))

    def test_precision_sample_is_deterministic(self) -> None:
        curated = {1000 + index: {"company_key": f"co{index}", "cik": 1000 + index, "ticker": "", "evidence": []}
                   for index in range(100)}
        records = [
            {"event_id": f"e{index:03d}", "company_key": f"co{index % 100}", "cik": 1000 + index % 100}
            for index in range(100)
        ]
        first = self.module.precision_check(records, curated, {}, seed=SEED, sample_size=60)
        second = self.module.precision_check(records, curated, {}, seed=SEED, sample_size=60)
        self.assertEqual(json_dump(first), json_dump(second))
        self.assertEqual(first["checks"]["sampled"], 60)
        self.assertEqual(first["verdict"], "PASS")

    def test_sample_never_exceeds_pool(self) -> None:
        curated = {1000: {"company_key": "co", "cik": 1000, "ticker": "", "evidence": []}}
        records = [{"event_id": "e1", "company_key": "co", "cik": 1000}]
        result = self.module.precision_check(records, curated, {}, seed=SEED, sample_size=60)
        self.assertEqual(result["checks"]["sampled"], 1)
        self.assertEqual(result["verdict"], "PASS")


# --------------------------------------------------------------- precision check
class PrecisionCheckTests(ModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.curated = {
            1000 + index: {"company_key": f"co{index}", "cik": 1000 + index, "ticker": "", "evidence": []}
            for index in range(10)
        }

    def test_wrong_company_key_fails(self) -> None:
        records = [{"event_id": "e1", "company_key": "wrong", "cik": 1000}]
        result = self.module.precision_check(records, self.curated, {}, seed=SEED, sample_size=50)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["failures"][0]["reason"], "company_key_mismatch")

    def test_uncurated_cik_fails(self) -> None:
        records = [{"event_id": "e1", "company_key": "co0", "cik": 424242}]
        result = self.module.precision_check(records, self.curated, {}, seed=SEED, sample_size=50)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["failures"][0]["reason"], "cik_not_in_curated_registry")

    def test_independent_identifier_cross_check(self) -> None:
        records = [{"event_id": "e1", "company_key": "co0", "cik": 1000}]
        agreeing = self.module.precision_check(
            records, self.curated, {}, seed=SEED, sample_size=50, independent={1000: {"co0"}}
        )
        disagreeing = self.module.precision_check(
            records, self.curated, {}, seed=SEED, sample_size=50, independent={1000: {"co1"}}
        )
        self.assertEqual(agreeing["checks"]["independent_identifier_agrees"], 1)
        self.assertEqual(disagreeing["verdict"], "FAIL")
        self.assertEqual(disagreeing["failures"][0]["reason"], "independent_identifier_disagrees")

    def test_name_overlap_is_reported_but_not_required(self) -> None:
        records = [
            {"event_id": "e1", "company_key": "co0", "cik": 1000},
            {"event_id": "e2", "company_key": "co1", "cik": 1001},
        ]
        result = self.module.precision_check(
            records,
            self.curated,
            {},
            seed=SEED,
            sample_size=50,
            applicant_by_event={"e1": "CO0 THERAPEUTICS", "e2": "UNRELATED NAME"},
        )
        self.assertEqual(result["checks"]["name_token_overlap_descriptive"], 1)
        self.assertEqual(result["verdict"], "PASS")


# -------------------------------------------------------------------- end-to-end
class EndToEndTests(ModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = self.make_store(
            self.tmp / "store.sqlite",
            events=[
                make_event("e1", "0000001800", applicant="UNRELATED NAME"),  # resolvable, unlinked
                make_event("e2", 999999, applicant="MEDTRONIC INC"),        # near name, not resolvable
                make_event("e3", 1800, company_key="abbott"),               # existing corroborated
                make_event("e4", 200406, applicant="JNJ"),                  # ambiguous cik
            ],
            companies=[("abbott", ""), ("medtronic", "")],
        )
        self.research = self.make_research(
            self.tmp / "research.sqlite",
            identifiers=[("abbott", "SEC_CIK", "0000001800", "sec_company_tickers")],
            companies=[("abbott", "")],
        )
        self.registry = self.make_registry(
            self.tmp / "registry.json",
            curated={1800: "abbott"},
            ambiguous={200406: ["jnj_pharma", "johnson_johnson_medtech"]},
        )
        self.report = self.tmp / "link_report.json"
        self.links = self.tmp / "events_linked.jsonl"

    def run_linker(self, report: Path | None = None, links: Path | None = None) -> int:
        return self.module.main([
            "--store", str(self.store),
            "--research", str(self.research),
            "--registry", str(self.registry),
            "--report", str(report or self.report),
            "--links", str(links or self.links),
            "--seed", str(SEED),
            "--sample-size", "60",
        ])

    def test_links_a_resolvable_event_at_confidence_one(self) -> None:
        self.assertEqual(self.run_linker(), 0)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["funnel"]["sec_8k_events"], 4)
        self.assertEqual(report["funnel"]["unlinked_events"], 3)
        self.assertEqual(report["funnel"]["unlinked_with_payload_cik"], 3)
        self.assertEqual(report["funnel"]["linked_now"], 1)
        self.assertEqual(report["funnel"]["events_cik_ambiguous"], 1)
        self.assertEqual(report["unresolved_reasons"]["cik_not_in_curated_registry"], 1)
        lines = [json.loads(line) for line in self.links.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 2)  # one new link + one existing corroboration
        by_event = {line["event_id"]: line for line in lines}
        self.assertEqual(by_event["e1"]["company_key"], "abbott")
        self.assertEqual(by_event["e1"]["confidence"], 1.0)
        self.assertEqual(by_event["e1"]["link_status"], "new")
        self.assertIn("exact CIK match", by_event["e1"]["evidence"])
        self.assertEqual(by_event["e3"]["link_status"], "existing_corroborated")
        self.assertNotIn("e2", by_event)  # near name must not link

    def test_run_is_byte_identical_twice(self) -> None:
        first_report = self.tmp / "report-1.json"
        first_links = self.tmp / "links-1.jsonl"
        second_report = self.tmp / "report-2.json"
        second_links = self.tmp / "links-2.jsonl"
        self.assertEqual(self.run_linker(first_report, first_links), 0)
        self.assertEqual(self.run_linker(second_report, second_links), 0)
        self.assertEqual(first_report.read_bytes(), second_report.read_bytes())
        self.assertEqual(first_links.read_bytes(), second_links.read_bytes())

    def test_report_records_data_quality_and_registry(self) -> None:
        self.assertEqual(self.run_linker(), 0)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["data_quality"]["store"]["companies_with_nonempty_cik"], 0)
        self.assertEqual(report["data_quality"]["research"]["company_identifier_schemes"], {"SEC_CIK": 1})
        self.assertEqual(report["registry"]["curated_ciks"], 1)
        self.assertEqual(report["registry"]["ambiguous_ciks"], 1)
        self.assertEqual(report["precision_check"]["verdict"], "PASS")
        self.assertEqual(report["existing_links_audit"]["cik_corroborated"], 1)
        self.assertEqual(report["existing_links_audit"]["cik_contradicted"], 0)

    def test_store_is_never_modified(self) -> None:
        before = hashlib.sha256(self.store.read_bytes()).hexdigest()
        self.assertEqual(self.run_linker(), 0)
        self.assertEqual(hashlib.sha256(self.store.read_bytes()).hexdigest(), before)

    def test_missing_store_exits_two(self) -> None:
        self.assertEqual(
            self.module.main([
                "--store", str(self.tmp / "absent.sqlite"),
                "--research", str(self.research),
                "--registry", str(self.registry),
                "--report", str(self.tmp / "r.json"),
                "--links", str(self.tmp / "l.jsonl"),
            ]),
            2,
        )

    def test_rebuild_registry_mode_writes_curated_registry(self) -> None:
        candidates = self.tmp / "candidates.jsonl"
        candidates.write_text(
            json.dumps({"cik": 1800, "ticker": "ABT"}) + "\n" + json.dumps({"cik": 200406, "ticker": "JNJ"}) + "\n",
            encoding="utf-8",
        )
        config = self.tmp / "companies.json"
        config.write_text(
            json.dumps(
                {"companies": [
                    {"key": "abbott", "ticker": "ABT"},
                    {"key": "jnj_pharma", "ticker": "JNJ"},
                    {"key": "johnson_johnson_medtech", "ticker": "JNJ"},
                ]}
            ),
            encoding="utf-8",
        )
        target = self.tmp / "rebuilt.json"
        exit_code = self.module.main([
            "--store", str(self.store),
            "--research", str(self.research),
            "--registry", str(target),
            "--report", str(self.tmp / "r.json"),
            "--links", str(self.tmp / "l.jsonl"),
            "--rebuild-registry",
            "--candidates", str(candidates),
            "--configs", str(config),
        ])
        self.assertEqual(exit_code, 0)
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], self.module.REGISTRY_SCHEMA)
        self.assertIn("0000001800", document["companies"])
        self.assertIn("0000200406", document["ambiguous"])
        self.assertEqual(document["companies"]["0000001800"]["company_key"], "abbott")


if __name__ == "__main__":
    unittest.main()
