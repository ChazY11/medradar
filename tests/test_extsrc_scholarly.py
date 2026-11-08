"""Offline tests for the scholarly (papers) and trials/grants connector packages.

No network: every connector is exercised on small built-in dicts that mirror the
real response shapes captured by the live probes (the probe artifacts live under
``research/data_expansion/samples/`` and are *not* read here).

The cross-source de-duplication suite is the important part: one paper present in
OpenAlex, Crossref, Europe PMC and PubMed must count as **one** independent
piece of evidence, and that rule is asserted directly.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from medradar.external_sources import schema
from medradar.external_sources.scholarly import (
    _common,
    crossref,
    dedupe,
    europepmc,
    linking,
    openalex,
    pubmed_eutils,
)
from medradar.external_sources.trials import clinicaltrials_gov, nih_reporter

FIXED = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

OPENALEX_WORK = {
    "id": "https://openalex.org/W2060583550",
    "ids": {
        "doi": "https://doi.org/10.1109/TNSRE.2012.2183617",
        "pmid": "https://pubmed.ncbi.nlm.nih.gov/22275720",
    },
    "title": "Design and validation of a fully implantable neuromodulation device",
    "publication_date": "2012-01-31",
    "created_date": "2016-06-24T00:00:00",
    "updated_date": "2024-01-01T00:00:00",
    "type": "article",
    "publication_year": 2012,
    "open_access": {"is_oa": False},
    "cited_by_count": 42,
    "authorships": [
        {
            "institutions": [{"display_name": "Medtronic (United States)"}],
            "raw_affiliation_strings": ["Medtronic Neuromodulation, Minneapolis, MN, USA"],
        }
    ],
    "institutions": [{"display_name": "Medtronic (United States)"}],
    "funders": [],
    "awards": [],
    "primary_location": {"source": {"display_name": "IEEE Trans Neural Syst Rehabil Eng"}},
}

EUROPE_PMC_RECORD = {
    "id": "22275720",
    "source": "MED",
    "pmid": "22275720",
    "pmcid": "PMC9999999",
    "doi": "10.1109/tnsre.2012.2183617",
    "title": "Design and validation of a fully implantable neuromodulation device",
    "pubYear": "2012",
    "firstPublicationDate": "2012-01-31",
    "electronicPublicationDate": "2012-02-02",
    "firstIndexDate": "2012-02-09",
    "dateOfCreation": "2012-02-09",
    "journalInfo": {
        "journal": {"title": "IEEE Trans Neural Syst Rehabil Eng"},
        "dateOfPublication": "2012 Mar",
    },
    "authorList": {
        "author": [
            {
                "fullName": "Stanslaski S",
                "affiliation": "Medtronic Neuromodulation, Minneapolis, MN, USA",
            }
        ]
    },
    "grantsList": {"grant": [{"agency": "Medtronic", "grantId": "R01DK064567"}]},
    "dbCrossReferenceList": {"dbCrossReference": [{"id": "NCT01234567"}]},
}

CROSSREF_WORK = {
    "DOI": "10.1109/TNSRE.2012.2183617",
    "title": ["Design and validation of a fully implantable neuromodulation device"],
    "type": "journal-article",
    "container-title": ["IEEE Trans Neural Syst Rehabil Eng"],
    "publisher": "IEEE",
    "published-online": {"date-parts": [[2012, 1, 31]]},
    "published-print": {"date-parts": [[2012, 3]]},
    "issued": {"date-parts": [[2012, 3]]},
    "created": {"date-time": "2012-02-10T00:00:00Z"},
    "deposited": {"date-time": "2019-01-01T00:00:00Z"},
    "indexed": {"date-time": "2024-01-01T00:00:00Z"},
    "URL": "https://doi.org/10.1109/TNSRE.2012.2183617",
    "funder": [{"name": "Medtronic", "award": ["R01DK064567"]}],
    "author": [{"affiliation": [{"name": "Medtronic Neuromodulation"}]}],
    "relation": {"has-clinical-trial": [{"id": "NCT01234567"}]},
}

PUBMED_ITEM = {
    "uid": "22275720",
    "docsum": {
        "uid": "22275720",
        "title": "Design and validation of a fully implantable neuromodulation device.",
        "pubdate": "2012 Mar",
        "epubdate": "2012 Jan 31",
        "source": "IEEE Trans Neural Syst Rehabil Eng",
        "fulljournalname": "IEEE transactions on neural systems and rehabilitation engineering",
        "sortpubdate": "2012/03/01 00:00",
        "volume": "20",
        "issue": "1",
        "pages": "1-10",
        "authors": [{"name": "Stanslaski S"}],
        "articleids": [
            {"idtype": "pubmed", "value": "22275720"},
            {"idtype": "doi", "value": "10.1109/TNSRE.2012.2183617"},
            {"idtype": "pmc", "value": "PMC9999999"},
        ],
    },
}

CTGOV_STUDY = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT01693120",
            "briefTitle": "Evaluation of the Phased Radio Frequency Ablation System",
            "officialTitle": "Evaluation of Multielectrode Phased RF Technology",
            "acronym": "VICTORY-AF",
            "orgStudyIdInfo": {"id": "VICTORY AF"},
            "organization": {"fullName": "Medtronic Cardiac Ablation Solutions"},
        },
        "statusModule": {
            "overallStatus": "TERMINATED",
            "studyFirstPostDateStruct": {"date": "2012-09-26", "type": "ESTIMATED"},
            "startDateStruct": {"date": "2013-11"},
            "lastUpdatePostDateStruct": {"date": "2025-02-13", "type": "ACTUAL"},
            "primaryCompletionDateStruct": {"date": "2017-02-07", "type": "ACTUAL"},
        },
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Medtronic Cardiac Ablation Solutions", "class": "INDUSTRY"},
            "collaborators": [{"name": "Philips Healthcare", "class": "INDUSTRY"}],
        },
        "designModule": {"studyType": "INTERVENTIONAL", "phases": ["NA"], "enrollmentInfo": {"count": 100}},
        "conditionsModule": {"conditions": ["Persistent Atrial Fibrillation"]},
        "armsInterventionsModule": {"interventions": [{"type": "DEVICE", "name": "Phased RF System"}]},
        "contactsLocationsModule": {"locations": [{"country": "United States"}]},
    }
}

NIH_PROJECT = {
    "project_num": "5R01DK064567-02",
    "core_project_num": "R01DK064567",
    "project_title": "Long term glucose sensing and physiologic insulin delivery",
    "fiscal_year": 2003,
    "award_amount": 674720,
    "project_start_date": "2002-09-30T00:00:00",
    "award_notice_date": "2003-08-04T00:00:00",
    "organization": {
        "org_name": "MEDTRONIC MINIMED",
        "org_city": "NORTHRIDGE",
        "org_country": "UNITED STATES",
        "org_state": "CA",
    },
    "agency_ic_admin": {"code": "DK", "abbreviation": "NIDDK"},
    "principal_investigators": [{"full_name": "Doe J"}],
}


def _publication(**overrides):
    payload = {"source_id": "test", "kind": "publication"}
    payload.update(overrides)
    return payload


class DateSemanticsTests(unittest.TestCase):
    def test_full_date_is_day_quality(self):
        self.assertEqual(_common.coerce_date("2021-03-04"), ("2021-03-04", "day"))

    def test_month_year_is_coarse_first_of_month(self):
        self.assertEqual(_common.coerce_date("2021-03"), ("2021-03-01", "coarse"))
        self.assertEqual(_common.coerce_date("2020 Dec"), ("2020-12-01", "coarse"))
        self.assertEqual(_common.coerce_date("2026 Nov-Dec"), ("2026-11-01", "coarse"))
        self.assertEqual(_common.coerce_date("2019"), ("2019-01-01", "coarse"))

    def test_unknown_is_never_guessed(self):
        self.assertEqual(_common.coerce_date(""), ("", "unknown"))
        self.assertEqual(_common.coerce_date(None), ("", "unknown"))
        self.assertEqual(_common.coerce_date("not a date"), ("", "unknown"))

    def test_ctis_dd_mm_yyyy(self):
        self.assertEqual(_common.date10("04/10/2023"), "2023-10-04")

    def test_machine_timestamp_keeps_day_quality(self):
        self.assertEqual(_common.coerce_date("2022-06-24 17:23:18"), ("2022-06-24", "day"))


class TimeSemanticsTests(unittest.TestCase):
    def test_openalex_created_date_is_not_the_public_clock(self):
        record = openalex.to_evidence(OPENALEX_WORK, fetched_at=FIXED)
        self.assertEqual(record["time"]["source_public_at"], "2012-01-31")
        self.assertEqual(record["time"]["event_at"], "2012-01-31")
        clock_fields = [item["field"] for item in record["normalized"]["metadata_clock_fields"]]
        self.assertIn("created_date", clock_fields)
        self.assertNotEqual(record["time"]["source_public_at"], "2016-06-24")

    def test_crossref_prefers_published_online_over_print_and_registration(self):
        record = crossref.to_evidence(CROSSREF_WORK, fetched_at=FIXED)
        self.assertEqual(record["time"]["source_public_at"], "2012-01-31")
        self.assertEqual(record["time"]["event_at"], "2012-03-01")
        self.assertEqual(record["time"]["source_public_at_quality"], "day")
        clock_fields = [item["field"] for item in record["normalized"]["metadata_clock_fields"]]
        self.assertIn("created", clock_fields)
        self.assertIn("deposited", clock_fields)
        self.assertNotIn("2012-02-10", record["time"]["source_public_at"])

    def test_europepmc_uses_first_publication_not_first_index(self):
        record = europepmc.to_evidence(EUROPE_PMC_RECORD, fetched_at=FIXED)
        self.assertEqual(record["time"]["source_public_at"], "2012-01-31")
        self.assertEqual(record["time"]["event_at"], "2012-03-01")
        self.assertEqual(record["time"]["source_public_at_quality"], "day")
        self.assertEqual(record["time"]["event_at"], "2012-03-01")
        self.assertNotEqual(record["time"]["source_public_at"], "2012-02-09")

    def test_pubmed_prefers_epubdate_and_marks_coarse_pubdate(self):
        record = pubmed_eutils.to_evidence(PUBMED_ITEM, fetched_at=FIXED)
        self.assertEqual(record["time"]["source_public_at"], "2012-01-31")
        self.assertEqual(record["time"]["event_at"], "2012-03-01")
        self.assertEqual(record["time"]["event_at"] == record["time"]["source_public_at"], False)

    def test_ctgov_public_clock_is_study_first_post_date_not_start_date(self):
        record = clinicaltrials_gov.to_evidence(CTGOV_STUDY, fetched_at=FIXED)
        self.assertEqual(record["time"]["source_public_at"], "2012-09-26")
        self.assertEqual(record["time"]["event_at"], "2013-11-01")
        self.assertEqual(record["time"]["event_at"] != record["time"]["source_public_at"], True)

    def test_nih_event_and_public_clock_are_distinct(self):
        record = nih_reporter.to_evidence(NIH_PROJECT, fetched_at=FIXED)
        self.assertEqual(record["time"]["event_at"], "2002-09-30")
        self.assertEqual(record["time"]["source_public_at"], "2003-08-04")

    def test_nih_missing_notice_date_stays_unknown(self):
        item = dict(NIH_PROJECT)
        item["award_notice_date"] = None
        record = nih_reporter.to_evidence(item, fetched_at=FIXED)
        self.assertEqual(record["time"]["source_public_at"], "")
        self.assertEqual(record["time"]["source_public_at_quality"], "unknown")

    def test_first_observed_equals_fetch_clock(self):
        record = openalex.to_evidence(OPENALEX_WORK, fetched_at=FIXED)
        self.assertEqual(record["time"]["first_observed_at"], record["time"]["fetched_at"])


class EvidenceContractTests(unittest.TestCase):
    def test_every_connector_produces_valid_evidence(self):
        records = [
            openalex.to_evidence(OPENALEX_WORK, fetched_at=FIXED),
            europepmc.to_evidence(EUROPE_PMC_RECORD, fetched_at=FIXED),
            crossref.to_evidence(CROSSREF_WORK, fetched_at=FIXED),
            pubmed_eutils.to_evidence(PUBMED_ITEM, fetched_at=FIXED),
            clinicaltrials_gov.to_evidence(CTGOV_STUDY, fetched_at=FIXED),
            nih_reporter.to_evidence(NIH_PROJECT, fetched_at=FIXED),
        ]
        for record in records:
            self.assertEqual(schema.validate_evidence(record), [], record["source_id"])
            self.assertTrue(record["canonical_key"])
            self.assertEqual(record["content_hash"], record["provenance"]["normalized_content_hash"])

    def test_evidence_id_is_stable_and_idempotent(self):
        first = openalex.to_evidence(OPENALEX_WORK, fetched_at=FIXED)["evidence_id"]
        second = openalex.to_evidence(OPENALEX_WORK, fetched_at=FIXED)["evidence_id"]
        self.assertEqual(first, second)

    def test_connector_metadata_constants(self):
        for module, kind in (
            (openalex, "publication"),
            (europepmc, "publication"),
            (crossref, "publication"),
            (pubmed_eutils, "publication"),
            (clinicaltrials_gov, "clinical_trial"),
            (nih_reporter, "grant"),
        ):
            self.assertEqual(module.KIND, kind)
            self.assertIn(module.LICENCE_STATUS, schema.LICENCE_STATUSES)
            self.assertTrue(callable(module.collect))
            self.assertTrue(callable(module.to_evidence))


class CrossSourceDedupeTests(unittest.TestCase):
    """The hard requirement: the same paper is one piece of evidence."""

    def setUp(self):
        self.records = [
            openalex.to_evidence(OPENALEX_WORK, fetched_at=FIXED),
            europepmc.to_evidence(EUROPE_PMC_RECORD, fetched_at=FIXED),
            crossref.to_evidence(CROSSREF_WORK, fetched_at=FIXED),
            pubmed_eutils.to_evidence(PUBMED_ITEM, fetched_at=FIXED),
        ]

    def test_same_paper_in_four_sources_is_one_work(self):
        report = dedupe.dedupe_report(self.records)
        self.assertEqual(report["records_collected"], 4)
        self.assertEqual(report["unique_works"], 1)
        self.assertEqual(report["duplicate_records"], 3)
        self.assertAlmostEqual(report["duplicate_ratio"], 0.75, places=4)
        self.assertEqual(report["counts_as_independent_evidence"], 1)

    def test_unique_publications_returns_one_representative(self):
        unique = dedupe.unique_publications(self.records)
        self.assertEqual(len(unique), 1)
        representative = unique[0]
        self.assertEqual(representative["source_id"], "europepmc")  # preferred clock
        self.assertEqual(representative["dedupe"]["records"], 4)
        self.assertEqual(
            representative["dedupe"]["sources"],
            ["crossref", "europepmc", "openalex", "pubmed_eutils"],
        )

    def test_duplicate_pairs_are_explicit(self):
        pairs = dedupe.duplicate_pairs(self.records)
        self.assertEqual(len(pairs), 3)
        for pair in pairs:
            self.assertTrue(pair["shared_identifiers"])
            self.assertEqual(pair["kept_evidence_id"], dedupe.unique_publications(self.records)[0]["evidence_id"])

    def test_identifier_union_bridges_doi_only_and_pmid_only_records(self):
        doi_only = _publication(evidence_id="ev-a", source_id="crossref", identifiers=[{"scheme": "doi", "value": "10.1000/x"}])
        pmid_only = _publication(evidence_id="ev-b", source_id="pubmed_eutils", identifiers=[{"scheme": "pmid", "value": "555"}])
        bridge = _publication(
            evidence_id="ev-c",
            source_id="europepmc",
            identifiers=[{"scheme": "doi", "value": "10.1000/X"}, {"scheme": "pmid", "value": "555"}],
        )
        report = dedupe.dedupe_report([doi_only, pmid_only, bridge])
        self.assertEqual(report["unique_works"], 1)
        self.assertEqual(report["duplicate_records"], 2)

    def test_different_papers_are_not_merged(self):
        left = _publication(evidence_id="ev-a", source_id="openalex", identifiers=[{"scheme": "doi", "value": "10.1000/a"}])
        right = _publication(evidence_id="ev-b", source_id="openalex", identifiers=[{"scheme": "doi", "value": "10.1000/b"}])
        self.assertEqual(dedupe.dedupe_report([left, right])["unique_works"], 2)

    def test_non_publication_identifiers_do_not_deduplicate_papers(self):
        left = _publication(
            evidence_id="ev-a",
            source_id="openalex",
            identifiers=[{"scheme": "doi", "value": "10.1000/a"}, {"scheme": "nct", "value": "NCT01234567"}],
        )
        right = _publication(
            evidence_id="ev-b",
            source_id="crossref",
            identifiers=[{"scheme": "doi", "value": "10.1000/b"}, {"scheme": "nct", "value": "NCT01234567"}],
        )
        self.assertEqual(dedupe.dedupe_report([left, right])["unique_works"], 2)

    def test_record_without_identifier_is_a_singleton_and_flagged(self):
        no_id = _publication(evidence_id="ev-x", source_id="semantic_scholar", identifiers=[])
        report = dedupe.dedupe_report([no_id, *self.records])
        self.assertEqual(report["unique_works"], 2)
        self.assertEqual(report["records_without_publication_identifier"], 1)

    def test_doi_normalisation_ignores_prefix_and_case(self):
        one = _publication(evidence_id="ev-a", source_id="openalex", identifiers=[{"scheme": "doi", "value": "https://doi.org/10.1000/ABC"}])
        two = _publication(evidence_id="ev-b", source_id="crossref", identifiers=[{"scheme": "doi", "value": "DOI:10.1000/abc"}])
        self.assertEqual(dedupe.dedupe_report([one, two])["unique_works"], 1)

    def test_pmcid_forms_are_the_same_identifier(self):
        one = _publication(evidence_id="ev-a", source_id="europepmc", identifiers=[{"scheme": "pmcid", "value": "PMC123"}])
        two = _publication(evidence_id="ev-b", source_id="pubmed_eutils", identifiers=[{"scheme": "pmcid", "value": "123"}])
        self.assertEqual(dedupe.dedupe_report([one, two])["unique_works"], 1)

    def test_cluster_shared_identifiers_reported(self):
        clusters = dedupe.cluster_publications(self.records)
        self.assertEqual(len(clusters), 1)
        shared = {f"{scheme}:{value}" for scheme, value in clusters[0].shared}
        self.assertIn("doi:10.1109/tnsre.2012.2183617", shared)


class CompanySignalTierTests(unittest.TestCase):
    def test_funder_and_author_affiliation_are_separate_tiers(self):
        record = openalex.to_evidence(
            {**OPENALEX_WORK, "funders": [{"display_name": "Medtronic"}]}, fetched_at=FIXED
        )
        tiers = sorted({ref["evidence"]["signal"] for ref in record["entity_refs"]})
        self.assertEqual(tiers, ["author_affiliation", "funder"])
        for ref in record["entity_refs"]:
            self.assertIn(ref["method"], {"exact_alias", "multi_field", "candidate"})

    def test_text_mention_is_always_candidate(self):
        refs = _common.company_refs(["A study of Medtronic devices"], tier="text_mention")
        self.assertTrue(refs)
        for ref in refs:
            self.assertEqual(ref["method"], "candidate")
            self.assertLess(ref["confidence"], 0.9)

    def test_negative_guard_demotes_to_candidate(self):
        refs = _common.company_refs(["Philips Lighting"], tier="funder")
        self.assertTrue(refs)
        self.assertEqual(refs[0]["method"], "candidate")

    def test_sponsor_and_collaborator_tiers_kept_apart(self):
        record = clinicaltrials_gov.to_evidence(CTGOV_STUDY, fetched_at=FIXED)
        signals = {ref["evidence"]["signal"] for ref in record["entity_refs"]}
        self.assertIn("lead_sponsor", signals)
        self.assertIn("collaborator", signals)

    def test_grantee_attribution_from_organization_field(self):
        record = nih_reporter.to_evidence(NIH_PROJECT, fetched_at=FIXED)
        self.assertTrue(
            any(ref["evidence"]["signal"] == "grantee" for ref in record["entity_refs"])
        )


class LinkingTests(unittest.TestCase):
    def test_grant_number_normalisation(self):
        self.assertEqual(linking.normalize_grant_number("5R01DK064567-02"), "R01DK064567")
        self.assertEqual(linking.normalize_grant_number("R01 DK064567"), "R01DK064567")
        self.assertEqual(linking.normalize_grant_number("R01DK064567-05A1"), "R01DK064567")
        self.assertEqual(linking.normalize_grant_number(""), "")
        self.assertEqual(linking.normalize_grant_number(None), "")

    def test_publication_trial_links_use_structured_nct_only(self):
        record = europepmc.to_evidence(EUROPE_PMC_RECORD, fetched_at=FIXED)
        links = linking.publication_trial_links([record])
        self.assertEqual([link["value"] for link in links], ["NCT01234567"])
        self.assertTrue(links[0]["deterministic"])

    def test_title_mention_is_not_a_trial_link(self):
        record = openalex.to_evidence(
            {**OPENALEX_WORK, "title": "Results of NCT01234567 in a device study"}, fetched_at=FIXED
        )
        self.assertEqual(linking.publication_trial_links([record]), [])

    def test_publication_grant_links_and_resolution_against_grant_records(self):
        paper = crossref.to_evidence(CROSSREF_WORK, fetched_at=FIXED)
        grant = nih_reporter.to_evidence(NIH_PROJECT, fetched_at=FIXED)
        links = linking.publication_grant_links([paper])
        self.assertEqual(len(links), 1)
        resolved = linking.resolve_grant_links(links, [grant])
        self.assertEqual(len(resolved["resolved"]), 1)
        self.assertEqual(resolved["resolved"][0]["target_evidence_id"], grant["evidence_id"])

    def test_unmatched_award_numbers_are_reported(self):
        paper = crossref.to_evidence(
            {**CROSSREF_WORK, "funder": [{"name": "Medtronic", "award": ["ZZ999"]}]},
            fetched_at=FIXED,
        )
        resolved = linking.resolve_grant_links(linking.publication_grant_links([paper]), [])
        self.assertEqual(resolved["resolved"], [])
        self.assertEqual(resolved["unmatched_award_numbers"], ["ZZ999"])


class _FakeResult:
    def __init__(self, payload, url="https://fake.test", status=200):
        import json

        self._payload = payload
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.url = url
        self.elapsed_ms = 1
        self.attempts = 1
        self.error = ""

    @property
    def ok(self):
        return 200 <= self.status < 300 and not self.error

    def json(self):
        return self._payload


class _FakeClient:
    """Network-free stand-in for ``base.HttpClient``."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []

    def get(self, url, *, params=None, headers=None, accept="application/json"):
        self.calls.append({"method": "GET", "url": url, "params": dict(params or {})})
        payload = self._payloads.pop(0) if self._payloads else {}
        return _FakeResult(payload, url=url)

    def post_json(self, url, payload, *, params=None, headers=None, accept="application/json"):
        self.calls.append({"method": "POST", "url": url, "payload": payload})
        result = self._payloads.pop(0) if self._payloads else {}
        return _FakeResult(result, url=url)


class CollectPaginationTests(unittest.TestCase):
    def test_openalex_collect_is_bounded_and_valid(self):
        client = _FakeClient(
            [
                {"results": [OPENALEX_WORK], "meta": {"next_cursor": "next"}},
                {
                    "results": [{**OPENALEX_WORK, "id": "https://openalex.org/W2"}],
                    "meta": {"next_cursor": "next2"},
                },
            ]
        )
        records = openalex.collect(client, limit=10, query="stent", per_page=1, max_pages=2)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(schema.validate_evidence(records[0]), [])

    def test_openalex_max_pages_one_makes_one_request(self):
        client = _FakeClient([{"results": [OPENALEX_WORK], "meta": {"next_cursor": "next"}}])
        records = openalex.collect(client, limit=10, per_page=1, max_pages=1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(records), 1)

    def test_europepmc_collect_paginates_with_cursormark(self):
        payload = {
            "resultList": {"result": [EUROPE_PMC_RECORD]},
            "nextCursorMark": "AoE=",
        }
        client = _FakeClient([payload, {"resultList": {"result": []}, "nextCursorMark": "AoE="}])
        records = europepmc.collect(client, limit=5, query="stent", page_size=1, max_pages=2)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(client.calls), 2)

    def test_ctgov_collect_uses_study_first_post_date(self):
        client = _FakeClient([{"studies": [CTGOV_STUDY], "totalCount": 1}])
        records = clinicaltrials_gov.collect(client, limit=5, sponsor="Medtronic")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "clinical_trial")
        self.assertEqual(records[0]["time"]["source_public_at"], "2012-09-26")

    def test_nih_reporter_collect_posts_and_validates(self):
        client = _FakeClient([{"results": [NIH_PROJECT], "meta": {"total": 1}}])
        records = nih_reporter.collect(client, limit=5, criteria={"fiscal_years": [2003]})
        self.assertEqual(client.calls[0]["method"], "POST")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "grant")
        self.assertEqual(schema.validate_evidence(records[0]), [])


if __name__ == "__main__":
    unittest.main()

