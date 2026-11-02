"""Offline tests for the deterministic applicant-entity universe (``universe_v1``).

Everything here runs on synthetic fixtures: no test touches ``data/``.  The
real build is exercised separately against the read-only research database, but
the *rules* (normalisation table, entity identity, coverage accounting,
selection rule, byte-for-byte determinism) are pinned here.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from medradar.intelligence import universe as U

SOURCE_510K = "openfda_device_510k_bulk"
SOURCE_PMA = "openfda_device_pma_bulk"


def event(
    applicant,
    kind="510k",
    date="2020-01-15",
    track="cardiac_rhythm",
    source=SOURCE_510K,
    company_key=None,
    supplement_number=None,
):
    return {
        "applicant_raw": applicant,
        "kind": kind,
        "event_date": date,
        "track_id": track,
        "source": source,
        "company_key": company_key,
        "supplement_number": supplement_number,
    }


def synthetic_events():
    """Small fixture containing every focus company plus suffix variants."""
    return [
        event("Medtronic, Inc.", date="2017-03-01"),
        event("MEDTRONIC", date="2019-07-04", track="neurostimulation",
              company_key="medtronic"),
        event("Shenzhen Mindray Bio-Medical Electronics Co., Ltd.",
              date="2018-05-02", track="patient_monitoring"),
        event("Shenzhen Mindray Bio-Meidcal Electronics Co., Ltd.",
              date="2021-01-10", track="patient_monitoring"),
        event("Draeger Medical Systems, Inc.", date="2016-11-20", track="respiratory"),
        event("Drägerwerk AG & Co. KGaA", date="2020-09-01", track="respiratory"),
        event("Draegerwerk AG & CO Kgaa", date="2022-02-02", track="respiratory"),
        event("Philips Medical Systems Nederland B.V.", date="2018-08-08",
              track="imaging_us"),
        event("Philips Ultrasound, LLC", date="2023-03-03", track="imaging_us"),
        event("GE Healthcare", date="2019-11-11", track="imaging_mr_ct"),
        event("GE Medical Systems, LLC", date="2020-12-12", track="imaging_mr_ct"),
        event("Acme Medical Inc", date="2016-11-01", track=None),
        event("Acme Surgical Inc", date="2024-04-04", track=None),
        event("PMA ORIGINAL CORP", kind="pma", date="2019-01-01",
              source=SOURCE_PMA, track="structural_heart"),
        event("PMA SUPPLEMENT CORP", kind="pma", date="2019-01-02",
              source=SOURCE_PMA, supplement_number="S001"),
    ]


CURATED = [
    {"key": "medtronic", "name_en": "Medtronic", "aliases": ["MEDTRONIC"]},
    {"key": "philips", "name_en": "Philips", "aliases": ["PHILIPS"]},
    {"key": "acme", "name_en": "Acme Medical", "aliases": ["ACME MEDICAL"]},
]


class NormalisationTableTests(unittest.TestCase):
    def test_every_declared_suffix_token_is_stripped(self):
        self.assertGreater(len(U.CORPORATE_SUFFIX_TOKENS), 30)
        for suffix in U.CORPORATE_SUFFIX_TOKENS:
            with self.subTest(suffix=suffix):
                self.assertEqual(
                    U.normalise_applicant(f"Acme Medical {suffix}"), "ACME MEDICAL"
                )

    def test_representative_legal_forms(self):
        table = {
            "Medtronic, Inc.": "MEDTRONIC",
            "Acme Medical Incorporated": "ACME MEDICAL",
            "Intuitive Surgical Operations, LLC": "INTUITIVE SURGICAL OPERATIONS",
            "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.":
                "SHENZHEN MINDRAY BIO MEDICAL ELECTRONICS",
            "Acme Limited": "ACME",
            "Boston Scientific Corp": "BOSTON SCIENTIFIC",
            "Boston Scientific Corporation": "BOSTON SCIENTIFIC",
            "Acme Medical Co.": "ACME MEDICAL",
            "Acme Medical Company": "ACME MEDICAL",
            "Philips Medizin Systeme Böblingen GmbH":
                "PHILIPS MEDIZIN SYSTEME BOBLINGEN",
            "Drägerwerk AG & Co. KGaA": "DRAGERWERK",
            "Draegerwerk AG & CO KGAA": "DRAEGERWERK",
            "Biomérieux SA": "BIOMERIEUX",
            "Medos International Sàrl": "MEDOS INTERNATIONAL",
            "Philips Medical Systems Nederland B.V.":
                "PHILIPS MEDICAL SYSTEMS NEDERLAND",
            "Ambu A/S": "AMBU",
            "Acme Medical Pty Ltd": "ACME MEDICAL",
            "Acme Medical, L.P.": "ACME MEDICAL",
            "Acme Medical LLP": "ACME MEDICAL",
            "Acme Medical KG": "ACME MEDICAL",
            "Acme Medical K.K.": "ACME MEDICAL",
            "Eko.Ai Pte Ltd.": "EKO AI",
            "Acme Medical Sdn. Bhd.": "ACME MEDICAL",
            "De Götzen S.R.L.": "DE GOTZEN",
            "Talladium España, SL": "TALLADIUM ESPANA",
            "Dürr Dental SE": "DURR DENTAL",
            "Acme Medical S.A.S.": "ACME MEDICAL",
            "Acme Medical S.p.A.": "ACME MEDICAL",
            "Acme Medical N.V.": "ACME MEDICAL",
            "Acme Medical PLC": "ACME MEDICAL",
        }
        for raw, expected in table.items():
            with self.subTest(raw=raw):
                self.assertEqual(U.normalise_applicant(raw), expected)

    def test_punctuation_diacritics_and_whitespace(self):
        table = {
            "Q'Apel Medical, Inc.": "Q APEL MEDICAL",
            "Cepheid®": "CEPHEID",
            "The Spectranetics Corp.": "SPECTRANETICS",
            "Karl Storz Endoscopy-America, Inc.": "KARL STORZ ENDOSCOPY AMERICA",
            "Wilson-Cook Medical, Inc.": "WILSON COOK MEDICAL",
            "  Acme   Medical\tInc. ": "ACME MEDICAL",
            "Shenzhen\xa0Mlay\xa0Intelligent\xa0Technology\xa0Co.,\xa0, Ltd.":
                "SHENZHEN MLAY INTELLIGENT TECHNOLOGY",
            "Bausch + Lomb, Inc.": "BAUSCH LOMB",
        }
        for raw, expected in table.items():
            with self.subTest(raw=raw):
                self.assertEqual(U.normalise_applicant(raw), expected)

    def test_descriptive_clauses_are_removed(self):
        table = {
            "Medtronic Vascular,Inc(Formerly D.B.A Ev3 Inc.,Covidien, LLC)":
                "MEDTRONIC VASCULAR",
            "Philips Image Guided Therapy Corporation (Formerly Intact)":
                "PHILIPS IMAGE GUIDED THERAPY",
            "Airway Technologies D/B/A Airway Management": "AIRWAY TECHNOLOGIES",
            "Creganna Medical Also Doing Business AS Ceganna Tactx Medica":
                "CREGANNA MEDICAL",
            "Acme Medical Inc. FKA Acme Devices": "ACME MEDICAL",
            "X, Inc. DBA Y Medical": "X",
        }
        for raw, expected in table.items():
            with self.subTest(raw=raw):
                self.assertEqual(U.normalise_applicant(raw), expected)

    def test_only_trailing_suffix_tokens_are_stripped(self):
        self.assertEqual(U.normalise_applicant("Acme Inc. Medical Inc."), "ACME INC MEDICAL")
        self.assertEqual(U.normalise_applicant("Ltd. Acme"), "LTD ACME")
        self.assertEqual(U.normalise_applicant("Acme Medical Inc Inc."), "ACME MEDICAL")

    def test_deterministic_and_idempotent(self):
        raws = [
            "Medtronic, Inc.",
            "Drägerwerk AG & Co. KGaA",
            "SHENZHEN MINDRAY BIO-MEIDCAL ELECTRONICS CO., LTD.",
            "Philips Medical Systems Nederland B.V.",
            "Acme Medical Company (Formerly Acme Devices, Inc.)",
        ]
        for raw in raws:
            once = U.normalise_applicant(raw)
            self.assertEqual(once, U.normalise_applicant(raw))
            self.assertEqual(once, U.normalise_applicant(once))

    def test_blank_and_unstrippable_inputs(self):
        self.assertEqual(U.normalise_applicant(""), "")
        self.assertEqual(U.normalise_applicant(None), "")
        self.assertEqual(U.normalise_applicant("   \t "), "")
        # A name made only of a suffix keeps the punctuation-normalised form
        # rather than becoming empty (documented step 8).
        self.assertEqual(U.normalise_applicant("Ltd."), "LTD")


class EntityKeyTests(unittest.TestCase):
    def test_stable_slug_plus_hash(self):
        key = U.entity_key(U.normalise_applicant("Medtronic, Inc."))
        self.assertEqual(key, "medtronic-4bdceace")
        self.assertEqual(key, U.entity_key("MEDTRONIC"))
        self.assertTrue(key.endswith("-4bdceace"))

    def test_distinct_entities_get_distinct_keys(self):
        keys = {
            U.entity_key(U.normalise_applicant(raw))
            for raw in (
                "Acme Medical Inc",
                "Acme Surgical Inc",
                "Acme Medicals Inc",
                "Acme Medical Group",
            )
        }
        self.assertEqual(len(keys), 4)

    def test_ascii_safe_slug(self):
        key = U.entity_key(U.normalise_applicant("北京医疗科技有限公司"))
        self.assertRegex(key, r"^entity-[0-9a-f]{8}$")


class NoFalseMergeTests(unittest.TestCase):
    def test_substantive_name_differences_stay_distinct(self):
        pairs = [
            ("ACME MEDICAL INC", "ACME SURGICAL INC"),
            ("ACME MEDICAL", "ACME MEDICALS"),
            ("ACME MEDICAL", "ACME MEDICAL GROUP"),
            ("MINDRAY", "MINDRAYX"),
            ("PHILIPS ULTRASOUND", "PHILIPS ULTRASOUND SYSTEMS"),
        ]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertNotEqual(
                    U.normalise_applicant(left), U.normalise_applicant(right)
                )

    def test_suffix_only_variants_merge_under_documented_rule(self):
        # Documented consequence of suffix stripping: same stem + different
        # legal form is *one* entity, and the record keeps both raw strings.
        records = U.build_universe(
            [
                event("Acme Medical, Inc."),
                event("ACME MEDICAL LLC"),
                event("Acme Medical GmbH"),
            ],
            min_events=1,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]["members"]), 3)
        self.assertEqual(records[0]["n_events"], 3)

    def test_token_containment_resolution_is_not_substring_matching(self):
        names = ["MINDRAY", "MINDRAYX", "ACME MEDICAL"]
        self.assertEqual(U.resolve_normalised(names, ["MINDRAY"]), ["MINDRAY"])
        self.assertEqual(U.resolve_normalised(["MINDRAYX"], ["MINDRAY"]), [])
        self.assertEqual(
            U.resolve_normalised(["SHENZHEN MINDRAY BIO MEDICAL ELECTRONICS"], ["MINDRAY"]),
            ["SHENZHEN MINDRAY BIO MEDICAL ELECTRONICS"],
        )
        self.assertEqual(U.resolve_normalised(names, ["ACME MEDICAL GROUP"]), [])

    def test_resolution_never_rewrites_entity_identity(self):
        records = U.build_universe(synthetic_events(), min_events=1)
        before = json.dumps(records, sort_keys=True, ensure_ascii=False)
        U.resolve_entities(records, ["MINDRAY"])
        after = json.dumps(records, sort_keys=True, ensure_ascii=False)
        self.assertEqual(before, after)


class BuildUniverseTests(unittest.TestCase):
    def test_member_raw_strings_are_aggregated(self):
        records = U.build_universe(
            [
                event("Medtronic, Inc.", date="2017-01-01", track="cardiac_rhythm"),
                event("MEDTRONIC", date="2018-01-01", track="neurostimulation"),
                event("Medtronic, Inc.", date="2020-01-01", track="cardiac_rhythm"),
            ],
            min_events=1,
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["normalised_name"], "MEDTRONIC")
        self.assertEqual(record["members"], ["MEDTRONIC", "Medtronic, Inc."])
        self.assertEqual(record["display_name"], "Medtronic, Inc.")
        self.assertEqual(record["n_events"], 3)
        self.assertEqual(record["n_510k"], 3)
        self.assertEqual(record["first_date"], "2017-01-01")
        self.assertEqual(record["last_date"], "2020-01-01")
        self.assertEqual(record["active_years"], 3)
        self.assertEqual(record["tracks"], {"cardiac_rhythm": 2, "neurostimulation": 1})
        self.assertIn("510k", record["evidence"])

    def test_material_event_definition(self):
        records = U.build_universe(
            [
                event("PMA CORP", kind="pma", source=SOURCE_PMA),
                event("PMA CORP", kind="pma", source=SOURCE_PMA, supplement_number="S001"),
                event("PMA CORP", kind="pma", source=SOURCE_PMA, supplement_number="S002"),
                event("PMA CORP", kind="510k"),
            ],
            min_events=1,
        )
        record = records[0]
        self.assertEqual(record["n_events"], 4)
        self.assertEqual(record["n_pma"], 3)
        self.assertEqual(record["n_510k"], 1)
        self.assertEqual(record["n_material"], 2)  # 510(k) + the original PMA

    def test_min_events_and_pinned_entities(self):
        events = [event("ONE EVENT DEVICES"), event("TWO EVENT DEVICES"),
                  event("TWO EVENT DEVICES")]
        self.assertEqual(len(U.build_universe(events, min_events=2)), 1)
        pinned = {U.normalise_applicant("ONE EVENT DEVICES")}
        records = U.build_universe(events, min_events=2, pinned_normalised=pinned)
        self.assertEqual({r["normalised_name"] for r in records},
                         {"ONE EVENT DEVICES", "TWO EVENT DEVICES"})

    def test_output_is_sorted_and_input_order_independent(self):
        events = synthetic_events()
        shuffled = list(events)
        random.Random(7).shuffle(shuffled)
        one = U.build_universe(events, min_events=2)
        two = U.build_universe(shuffled, min_events=2)
        self.assertEqual(
            json.dumps(one, sort_keys=True, ensure_ascii=False),
            json.dumps(two, sort_keys=True, ensure_ascii=False),
        )
        keys = [(-record["n_events"], record["entity_key"]) for record in one]
        self.assertEqual(keys, sorted(keys))

    def test_empty_input(self):
        self.assertEqual(U.build_universe([], min_events=2), [])
        self.assertEqual(U.build_universe(iter([]), min_events=1), [])

    def test_blank_applicant_goes_to_unknown_bucket(self):
        records = U.build_universe(
            [event(""), event(None), event("REAL CORP")], min_events=1
        )
        by_name = {record["normalised_name"]: record for record in records}
        self.assertIn(U.UNKNOWN_APPLICANT, by_name)
        self.assertEqual(by_name[U.UNKNOWN_APPLICANT]["n_events"], 2)

    def test_other_kinds_count_but_are_not_material(self):
        records = U.build_universe(
            [event("ODD CORP", kind="recall"), event("ODD CORP", kind="510k")],
            min_events=1,
        )
        self.assertEqual(records[0]["n_events"], 2)
        self.assertEqual(records[0]["n_material"], 1)


class SelectCohortTests(unittest.TestCase):
    @staticmethod
    def _entity(key, n_material, n_events, active_years):
        return {
            "entity_key": key,
            "n_material": n_material,
            "n_events": n_events,
            "active_years": active_years,
        }

    def test_rank_and_eligibility(self):
        entities = [
            self._entity("a-1", 10, 50, 5),
            self._entity("b-2", 10, 60, 5),
            self._entity("c-3", 9, 100, 5),
            self._entity("d-4", 2, 100, 5),   # below material floor
            self._entity("e-5", 30, 30, 1),   # below history floor
        ]
        self.assertEqual(
            U.select_cohort(entities, max_entities=10, min_material_events=3,
                            min_active_years=2),
            ["b-2", "a-1", "c-3"],
        )

    def test_input_order_independent_and_capped(self):
        entities = [
            self._entity(f"e-{index}", 100 - index, 100 + index, 3)
            for index in range(10)
        ]
        cohort = U.select_cohort(entities, max_entities=4)
        self.assertEqual(len(cohort), 4)
        self.assertEqual(cohort, U.select_cohort(list(reversed(entities)), max_entities=4))
        self.assertEqual(cohort[0], "e-0")

    def test_required_keys_are_pinned_only_when_eligible(self):
        entities = [
            self._entity("big-1", 100, 100, 5),
            self._entity("mid-2", 5, 5, 5),
            self._entity("small-3", 1, 20, 5),  # ineligible despite history
        ]
        cohort = U.select_cohort(
            entities, max_entities=2, required_keys=["small-3", "mid-2"]
        )
        self.assertNotIn("small-3", cohort)
        self.assertIn("mid-2", cohort)

    def test_negative_cap_rejected(self):
        with self.assertRaises(ValueError):
            U.select_cohort([], max_entities=-1)


class BuildDocumentTests(unittest.TestCase):
    def _document(self, events=None, curated=None, **kwargs):
        return U.build_document(
            synthetic_events() if events is None else events,
            curated_companies=CURATED if curated is None else curated,
            **kwargs,
        )

    def test_focus_companies_are_all_resolvable(self):
        document = self._document()
        focus = document["focus_companies"]
        self.assertEqual(
            sorted(focus),
            ["draeger", "ge_healthcare", "medtronic", "mindray", "philips"],
        )
        expected_events = {
            "medtronic": 2,
            "ge_healthcare": 2,
            "philips": 2,
            "draeger": 3,
            "mindray": 2,
        }
        for key, n_events in expected_events.items():
            with self.subTest(focus=key):
                self.assertEqual(focus[key]["n_events"], n_events)
                self.assertGreaterEqual(focus[key]["n_entities"], 1)
        self.assertEqual(focus["mindray"]["n_entities"], 2)  # two spellings keep separate
        self.assertEqual(focus["draeger"]["n_entities"], 3)
        self.assertEqual(focus["mindray"]["roster_status"], "absent_from_curated_roster")
        self.assertEqual(focus["draeger"]["roster_status"], "absent_from_curated_roster")
        self.assertEqual(focus["medtronic"]["roster_status"], "in_curated_roster")

    def test_curated_coverage_resolves_roster_and_reports_gap(self):
        document = self._document()
        curated = document["curated_coverage"]
        self.assertEqual(curated["companies_total"], 3)
        self.assertEqual(curated["companies_resolved"], 3)
        self.assertEqual(curated["by_company"]["acme"]["n_events"], 1)
        # Acme Medical Inc / Acme Surgical Inc are one-event entities pinned by
        # the curated alias even though min_events = 2.
        pinned = {record["normalised_name"] for record in document["entities"]}
        self.assertIn("ACME MEDICAL", pinned)

    def test_coverage_accounting_adds_up(self):
        document = self._document()
        counts = document["counts"]
        entities_events = sum(record["n_events"] for record in document["entities"])
        self.assertEqual(entities_events, counts["events_detailed"])
        self.assertEqual(
            counts["events_detailed"] + counts["events_remainder"],
            counts["events_total"],
        )
        self.assertEqual(counts["events_total"], len(synthetic_events()))
        self.assertEqual(counts["events_accounted_pct"], 100.0)
        self.assertEqual(
            counts["entities_detailed"] + counts["entities_remainder"],
            counts["entities_total"],
        )
        self.assertEqual(document["remainder"]["n_entities"],
                         document["remainder"]["n_events"])
        for record in document["entities"]:
            self.assertEqual(record["n_510k"] + record["n_pma"], record["n_events"])
            self.assertLessEqual(record["n_material"], record["n_events"])

    def test_no_timestamps_and_byte_identical_serialisation(self):
        first = self._document()
        second = self._document()
        blob_one = json.dumps(first, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"))
        blob_two = json.dumps(second, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"))
        self.assertEqual(blob_one, blob_two)
        self.assertNotIn("generated_at", first)
        self.assertEqual(first["schema_version"], U.SCHEMA_VERSION)
        self.assertEqual(first["counts"]["events_accounted_pct"], 100.0)

    def test_entity_records_are_sorted_and_json_safe(self):
        document = self._document()
        records = document["entities"]
        ranks = [(-record["n_events"], record["entity_key"]) for record in records]
        self.assertEqual(ranks, sorted(ranks))
        keys = [record["entity_key"] for record in records]
        self.assertEqual(len(keys), len(set(keys)))
        for record in records:
            self.assertEqual(record["members"], sorted(record["members"]))
            self.assertEqual(list(record["tracks"]), sorted(record["tracks"]))
            self.assertTrue(record["normalised_name"])
            self.assertTrue(record["display_name"])
        json.loads(json.dumps(document, ensure_ascii=False))

    def test_cohort_includes_one_entity_per_focus_company(self):
        document = self._document()
        cohort = document["cohort"]
        required = cohort["required_focus_entity_keys"]
        self.assertEqual(len(required), 5)
        self.assertEqual(len(set(required)), 5)
        names = {record["entity_key"]: record for record in document["entities"]}
        for key in required:
            self.assertIn(key, names)
        self.assertEqual(cohort["entity_keys"], U.select_cohort(
            document["entities"], required_keys=required,
        ))
        for key in cohort["entity_keys"]:
            self.assertGreaterEqual(
                names[key]["n_material"], U.DEFAULT_MIN_MATERIAL_EVENTS
            )
            self.assertGreaterEqual(
                names[key]["active_years"], U.DEFAULT_MIN_ACTIVE_YEARS
            )
        # Pinned required entities that are eligible are placed before the rest.
        eligible_required = [key for key in required if key in cohort["entity_keys"]]
        self.assertEqual(cohort["entity_keys"][:len(eligible_required)], eligible_required)

    def test_empty_document(self):
        document = U.build_document([], curated_companies=[])
        self.assertEqual(document["counts"]["events_total"], 0)
        self.assertEqual(document["counts"]["events_accounted_pct"], 0.0)
        self.assertEqual(document["entities"], [])
        self.assertEqual(document["curated_coverage"]["companies_total"], 0)

    def test_module_uses_stdlib_only(self):
        source = Path(U.__file__).read_text(encoding="utf-8")
        for forbidden in ("import numpy", "import pandas", "rapidfuzz", "pycountry",
                          "difflib", "Levenshtein"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class DatabaseRoundTripTests(unittest.TestCase):
    """Exercise the real read-only DB path on a tiny synthetic SQLite database."""

    @staticmethod
    def _make_db(path: Path) -> None:
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE events (event_id TEXT PRIMARY KEY, applicant_raw TEXT, "
            "kind TEXT, event_date TEXT, track_id TEXT, source TEXT, "
            "company_key TEXT, payload TEXT)"
        )
        rows = [
            ("e1", "Medtronic, Inc.", "510k", "2017-03-01", "cardiac_rhythm",
             SOURCE_510K, "medtronic", "{}"),
            ("e2", "MEDTRONIC", "510k", "2019-07-04", "neurostimulation",
             SOURCE_510K, None, "{}"),
            ("e3", "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "510k",
             "2018-05-02", "patient_monitoring", SOURCE_510K, None, "{}"),
            ("e4", "Draeger Medical Systems, Inc.", "510k", "2016-11-20",
             "respiratory", SOURCE_510K, None, "{}"),
            ("e5", "PHILIPS MEDICAL SYSTEMS, INC.", "pma", "2019-01-01",
             "imaging_us", SOURCE_PMA, None, '{"supplement_number": "S010"}'),
            ("e6", "ACME MEDICAL INC", "510k", "2020-02-02", None,
             SOURCE_510K, None, "{}"),
        ]
        connection.executemany(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", rows
        )
        connection.commit()
        connection.close()

    @staticmethod
    def _make_config(path: Path) -> None:
        path.write_text(
            json.dumps({"companies": CURATED}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_write_universe_is_deterministic_and_never_writes_the_database(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            directory = Path(raw_dir)
            db = directory / "events.sqlite"
            self._make_db(db)
            config = directory / "companies_device.json"
            self._make_config(config)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            first = directory / "universe_a.json"
            second = directory / "universe_b.json"

            document = U.write_universe(db, first, config_path=config)
            U.write_universe(db, second, config_path=config)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
            self.assertFalse((directory / "events.sqlite-journal").exists())
            self.assertFalse((directory / "events.sqlite-wal").exists())

            loaded = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(loaded, document)
            self.assertEqual(loaded["source"]["db_sha256"], before)
            self.assertEqual(loaded["counts"]["events_total"], 6)
            self.assertEqual(loaded["counts"]["events_accounted_pct"], 100.0)
            self.assertTrue(first.read_bytes().endswith(b"\n"))
            # MEDTRONIC appears twice -> detailed; one-event curated/focus
            # applicants are pinned by the alias view.
            self.assertEqual(loaded["focus_companies"]["mindray"]["n_events"], 1)
            self.assertEqual(loaded["focus_companies"]["draeger"]["n_events"], 1)
            self.assertEqual(loaded["focus_companies"]["philips"]["n_events"], 1)
            # The supplement-only PMA entity is not material.
            pma_entity = next(
                record for record in loaded["entities"]
                if record["normalised_name"] == "PHILIPS MEDICAL SYSTEMS"
            )
            self.assertEqual(pma_entity["n_material"], 0)
            self.assertEqual(pma_entity["n_pma"], 1)

    def test_missing_database_raises(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            with self.assertRaises(FileNotFoundError):
                U.write_universe(
                    Path(raw_dir) / "nope.sqlite",
                    Path(raw_dir) / "out.json",
                    config_path=Path(raw_dir) / "missing_config.json",
                )


if __name__ == "__main__":
    unittest.main()
