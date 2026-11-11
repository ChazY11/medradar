"""Write the ten scholarly ``registry/sources/<source_id>.json`` entries.

Every value here is traceable to saved evidence:

* ``access_evidence`` -> the probe id in ``SOURCE_PROBES/scholarly/PROBES.json``
  (or ``POST_CALLS.json`` for the two POST endpoints) plus the observed HTTP code;
* ``licence_note``    -> the exact URL and sentence relied on;
* ``what_is_new``     -> the measured increment, not an advertisement;
* ``blockers``        -> the precise HTTP signature, from the probe output.

    python CONNECTORS/scholarly/write_registry.py
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hz.registry import SourceEntry, write_entry  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

from CONNECTORS.scholarly import _util as U  # noqa: E402

SUITE = "scholarly"

ENTRIES: list[dict] = [
    dict(
        source_id="openalex",
        name="OpenAlex",
        operator="OurResearch (non-profit)",
        domain="api.openalex.org",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe openalex_works_search: HTTP 200 with a compound filter "
            "(raw_affiliation_strings.search + publication window + has_doi) and a "
            "field projection; probe openalex_select_contract: HTTP 400 with the "
            "closed list of selectable field names. 12 anchor-selection requests, "
            "0 failures."),
        machine_interface="REST JSON, cursor paging, `select` field projection",
        auth_required=False,
        rate_policy=(
            "Documented: add `mailto` to join the polite pool. Observed in "
            "meta.notice: without an API key the request costs ~$0.001 against a "
            "$0.10/day shared budget per IP, so this workstream stayed at 12 "
            "requests and never paged deeply."),
        licence_status="open_licence",
        licence_url="https://openalex.org/licenses",
        licence_note=(
            "OpenAlex states its data is released under CC0 1.0 Universal "
            "(https://openalex.org/licenses, 'All data ... is licensed under CC0 1.0'). "
            "Quoted from the licence page surfaced by the API's own meta.notice."),
        robots_url="https://api.openalex.org/robots.txt",
        robots_summary="Not applicable: only the JSON API is touched, never HTML pages.",
        bulk_available=True,
        historical_depth=(
            "Works from the 1800s to present. `created_date` gives per-work index "
            "history; the publication date itself is a mutable current value."),
        first_verified_at=now_utc(),
        what_is_new=(
            "Definitional for the sample (60/60 anchors) and the only source here that "
            "exposes a per-work index-creation timestamp. Contributes the anchor "
            "universe, not de-duplication value."),
        id_schemes=["openalex_id", "doi", "pmid", "pmcid", "mag"],
        entity_types=["publication"],
        notes=(
            "Anonymous daily budget is a real ceiling: the API's meta.notice states "
            "requests share a $0.10/day budget per IP without a key, and that mailto "
            "does not raise it. A free key exists (POST https://api.openalex.org/"
            "api-keys with an email, then the emailed link must be clicked) but the "
            "click-through is a human step and was not attempted."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="crossref",
        name="Crossref REST API",
        operator="Crossref",
        domain="api.crossref.org",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe crossref_works_doi: HTTP 200 with created/issued/published-print/"
            "published-online timestamps, author list, funder awards and per-record "
            "licence array; probe crossref_absent_doi: HTTP 404 with a 19-byte "
            "'Resource not found.' body. 60 anchor lookups: 59 found, 1 absent, 0 "
            "errors."),
        machine_interface="REST JSON, /works/{doi} and /works?filter=",
        auth_required=False,
        rate_policy="Polite pool via a contact User-Agent; no published hard limit.",
        licence_status="open_no_explicit_licence",
        licence_url="https://www.crossref.org/operations-and-sustainability/accessibility/",
        licence_note=(
            "Crossref makes metadata openly available for reuse and asks only for a "
            "polite contact, but attaches no single blanket content licence to the "
            "metadata; the per-record `license[]` array is preserved because that is "
            "where the rights actually are. Recorded as open_no_explicit_licence "
            "rather than assumed open."),
        robots_url="https://api.crossref.org/robots.txt",
        robots_summary="Not applicable: API only.",
        bulk_available=True,
        historical_depth=(
            "Full back file. `created` is the DOI registration timestamp, so it is a "
            "genuine historical record; `deposited`/`indexed` are mutable."),
        first_verified_at=now_utc(),
        what_is_new=(
            "The only source here where the creation timestamp is a registry event "
            "(DOI registration) rather than an index event. Holds 59/60 anchors and "
            "contributes 13 of 60 anchors with funder-award metadata, which is one of "
            "the two usable grant-declaration surfaces."),
        id_schemes=["doi"],
        entity_types=["publication"],
        notes=(
            "Crossref exposes NO pmid/pmcid. Any workflow that needs the DOI<->PMID "
            "edge must get it from PubMed, Europe PMC or Semantic Scholar."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="europepmc",
        name="Europe PMC REST",
        operator="EMBL-EBI / Europe PMC",
        domain="www.ebi.ac.uk/europepmc",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe europepmc_search_core: HTTP 200, resultType=core returns "
            "firstPublicationDate, electronicPublicationDate, grantsList, pmid, pmcid; "
            "probe europepmc_grant_field: GRANT_ID is an accepted query field; probe "
            "europepmc_nct_fulltext: NCT04494867 found as a literal string, so trial "
            "identifiers are searchable. 4 batched DOI queries covering 60 DOIs -> 37 "
            "hits."),
        machine_interface="REST JSON, query-language search, resultType=lite|core",
        auth_required=False,
        rate_policy="No key; the search endpoint is used at ~1.5 req/s in batches of 15 DOIs.",
        licence_status="open_licence",
        licence_url="https://europepmc.org/help",
        licence_note=(
            "Europe PMC describes itself as an ELIXIR Core Data Resource with content "
            "available for reuse with attribution, and the REST service is free and "
            "unrestricted (https://europepmc.org/help, terms of use). Per-record "
            "`license` is preserved. Recorded as open_licence at the metadata level."),
        robots_url="https://europepmc.org/robots.txt",
        robots_summary="Not applicable: REST API only.",
        bulk_available=True,
        historical_depth=(
            "firstIndexDate and dateOfCreation give real indexing history in addition "
            "to firstPublicationDate."),
        first_verified_at=now_utc(),
        what_is_new=(
            "The best single source for identifier convergence (doi+pmid+pmcid on the "
            "same record) and the richest grant surface: 13 of 37 records carry a "
            "grantsList, which is where 30 of the 108 declared grant rows come from."),
        id_schemes=["doi", "pmid", "pmcid"],
        entity_types=["publication"],
        notes=(
            "Coverage of an OpenAlex-defined device-technology sample is 37/60: Europe "
            "PMC is biomedical, so it misses physics/engineering venues. That is scope, "
            "not failure."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="pubmed_eutils",
        name="PubMed E-utilities",
        operator="US National Library of Medicine",
        domain="eutils.ncbi.nlm.nih.gov",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe pubmed_eutils_esearch: HTTP 200, DOI resolves via the [doi] field "
            "tag; probe pubmed_eutils_efetch: HTTP 200 with ArticleIdList carrying "
            "doi/pubmed/pmc/mid IdTypes. 3 chunked esearch calls over 60 DOIs resolved "
            "37 distinct PMIDs; one efetch returned all 37."),
        machine_interface="REST (esearch/efetch), JSON + XML",
        auth_required=False,
        rate_policy=(
            "NCBI policy: <=3 requests/second without an API key. Used at 1 req/s with "
            "tool= and email= set. A key raises the limit but is not required."),
        licence_status="open_no_explicit_licence",
        licence_url="https://www.ncbi.nlm.nih.gov/books/NBK25497/",
        licence_note=(
            "NLM makes PubMed citation data available for public use and the "
            "E-utilities usage policy grants keyless access at <=3 req/s "
            "(https://www.ncbi.nlm.nih.gov/books/NBK25497/). No blanket content "
            "licence is attached to the citation metadata and abstract copyright "
            "stays with the publisher, so this is open_no_explicit_licence."),
        robots_url="https://www.ncbi.nlm.nih.gov/robots.txt",
        robots_summary="Not applicable: E-utilities only, no HTML scraping.",
        bulk_available=True,
        historical_depth=(
            "No record-creation or index timestamp is exposed, so PubMed can only "
            "ever supply a current-snapshot date."),
        first_verified_at=now_utc(),
        what_is_new=(
            "Provides the authoritative PMID<->DOI edge and the GrantList (7 of 37 "
            "records). Its PMID set matches OpenAlex's pmid field exactly (37 vs 37), "
            "which is a clean independent cross-check of the identifier links."),
        id_schemes=["pmid", "doi", "pmcid", "pubmed_mid"],
        entity_types=["publication"],
        blockers=[
            "DOIs must be double-quoted before the [doi] tag: an unquoted 60-DOI OR "
            "query silently returned 10 of 37 hits because PubMed's parser splits on "
            "the embedded '/' and '('.",
        ],
        notes=(
            "PubMed is not a superset of Europe PMC and vice versa, but on this sample "
            "the two agree on 37 PMIDs exactly and disagree on publication date for "
            "only 3 of 37 pairs."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="semantic_scholar",
        name="Semantic Scholar Graph API",
        operator="Allen Institute for AI",
        domain="api.semanticscholar.org",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe semanticscholar_paper_get: HTTP 200 with externalIds incl. PubMed, "
            "PubMedCentral, ArXiv, MAG; POST probe semanticscholar_batch_post in "
            "POST_CALLS.json: HTTP 200 after one HTTP 429 on the anonymous tier. 60 "
            "DOIs in one batch call -> 56 resolved."),
        machine_interface="REST JSON; GET /paper/{id} and POST /paper/batch",
        auth_required=False,
        rate_policy=(
            "Anonymous tier is shared and does throttle: HTTP 429 observed twice, "
            "recovered by bounded exponential backoff. A key exists on request."),
        licence_status="open_no_explicit_licence",
        licence_url="https://www.semanticscholar.org/product/api/license",
        licence_note=(
            "The Graph API is free for research use, and the Open Research Corpus is "
            "ODC-BY, but the API terms restrict bulk redistribution and require "
            "attribution. Recorded as open_no_explicit_licence because API-level terms "
            "rather than a content licence govern reuse of these responses."),
        robots_url="https://www.semanticscholar.org/robots.txt",
        robots_summary="Not applicable: Graph API only.",
        bulk_available=True,
        historical_depth=(
            "publicationDate only; no creation or update timestamp is exposed, so every "
            "record is SNAPSHOT_ONLY."),
        first_verified_at=now_utc(),
        what_is_new=(
            "The only source here exposing an ArXiv identifier, and it carries PubMed "
            "and PubMedCentral ids too, so it is a second independent path to the "
            "PMID<->DOI edge: 56/60 anchors, 1 of which OpenAlex and Crossref could not "
            "reach by PMID."),
        id_schemes=["doi", "pmid", "pmcid", "arxiv", "mag", "s2_corpus_id"],
        entity_types=["publication"],
        blockers=[
            "The batch endpoint ignores the field projection unless `fields` is passed "
            "as a query parameter; without it the response is HTTP 200 with only "
            "{paperId,title} - a silent partial response.",
        ],
        notes=(
            "Four of 60 DOIs returned null from the batch call (not in S2). Those are "
            "recorded as ABSENT, not as errors."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="openaire",
        name="OpenAIRE Graph API",
        operator="OpenAIRE (EU)",
        domain="api.openaire.eu",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe openaire_researchproducts_pid: HTTP 200 with numFound/pids/instances "
            "when the DOI is passed as a BARE `pid` value; probe openaire_projects_search: "
            "HTTP 200 with grant codes on the project side. 60 per-DOI pid lookups -> 59 "
            "records."),
        machine_interface="REST JSON, Graph API v1 (researchProducts, projects)",
        auth_required=False,
        rate_policy="No key; used at 1.5 req/s.",
        licence_status="open_licence",
        licence_url="https://graph.openaire.eu/docs/",
        licence_note=(
            "OpenAIRE publishes the Graph as open data under CC-BY 4.0 and the Graph "
            "API is free to query (https://graph.openaire.eu/docs/). Per-record "
            "bestAccessRight and instances[].license are preserved because the "
            "publication rights differ from the metadata rights."),
        robots_url="https://api.openaire.eu/robots.txt",
        robots_summary="Not applicable: Graph API only.",
        bulk_available=True,
        historical_depth=(
            "publicationDate plus lastUpdateTimeStamp; no creation timestamp, so "
            "records are SNAPSHOT_ONLY."),
        first_verified_at=now_utc(),
        what_is_new=(
            "It is the only source here that de-duplicates works across repositories, "
            "and the only one that surfaced multiple DOIs for a single work (9 of 59 "
            "records). That is directly relevant to de-duplication, and it is also a "
            "trap: a naive 'first DOI' reader mis-assigns those records."),
        id_schemes=["doi", "pmid", "pmcid", "handle"],
        entity_types=["publication"],
        blockers=[
            "`pid=doi:<doi>` and `pid=doi|<doi>` both return numFound=0; only the bare "
            "DOI resolves. Verified by matrix in method-development and recorded in the "
            "probe note.",
        ],
        notes=(
            "A pid query can return a record whose `pids` hold no DOI but whose "
            "`originalIds` do. The queried DOI is therefore recorded as primary and all "
            "others are listed, rather than silently taking the first DOI in the array."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="clinicaltrials_gov",
        name="ClinicalTrials.gov API v2",
        operator="US National Library of Medicine",
        domain="clinicaltrials.gov",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe ctgov_studies_search: HTTP 200 with query.spons, pageSize and "
            "protocolSection payloads; probe ctgov_study_detail: HTTP 200 with "
            "statusModule posting dates; probe ctgov_fields_projection_rejected: HTTP "
            "400 'invalid field name' for an unlisted leaf. 5 sponsor queries -> 164 "
            "study records."),
        machine_interface="REST JSON v2, query.* + filter.* parameters",
        auth_required=False,
        rate_policy="Keyless. pageSize used at 50 throughout.",
        licence_status="public_domain",
        licence_url="https://clinicaltrials.gov/about-site/terms-conditions",
        licence_note=(
            "ClinicalTrials.gov states the data is available for public use and is not "
            "subject to copyright restrictions in the United States "
            "(https://clinicaltrials.gov/about-site/terms-conditions). Recorded as "
            "public_domain."),
        robots_url="https://clinicaltrials.gov/robots.txt",
        robots_summary="Not applicable: API v2 only.",
        bulk_available=True,
        historical_depth=(
            "Exposes study first SUBMIT date, first POST date, last update submit and "
            "post dates separately, so the registry's own publication queue is "
            "measurable rather than assumed."),
        first_verified_at=now_utc(),
        what_is_new=(
            "The only trial-registry source that answered. Supplies referencesModule "
            "citations (185 references, 179 with a PMID, 66 labelled RESULT or DERIVED) "
            "and the four separate status dates. It is what makes a machine-checkable "
            "trial<->paper relation possible at all."),
        id_schemes=["nct", "secondary:org_study_id"],
        entity_types=["clinical_trial"],
        blockers=[
            "The `fields` projection is closed: HTTP 400 'Parameter `fields` contains "
            "invalid field name: ReferenceDOI'. Whole study objects are requested "
            "instead.",
            "A sponsor query's `totalCount` is the server's count for the whole query "
            "(e.g. 1675 for Medtronic) and is NOT the number collected; only one page "
            "of 50 was taken per firm, and that truncation is recorded on every record.",
        ],
        notes=(
            "Reference `type` is submitter-asserted and is observably wrong for some "
            "records: a venous-ulcer device trial labels epidemiology papers as RESULT. "
            "Only 35 of 66 RESULT/DERIVED references are corroborated by the paper's own "
            "abstract naming the trial's NCT number."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="nih_reporter",
        name="NIH RePORTER v2",
        operator="US National Institutes of Health",
        domain="api.reporter.nih.gov",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "probe nih_reporter_get_405: GET returns HTTP 405 with a zero-byte body "
            "(POST is mandatory). POST probe nih_reporter_search_post in "
            "POST_CALLS.json: HTTP 200 with a meta block. 6 POSTs total: 1 discovery + 4 "
            "bounded pages + 1 probe."),
        machine_interface="REST JSON, POST /v2/projects/search only",
        auth_required=False,
        rate_policy="No key documented; used sequentially with small limits (<=50/page, <=6 pages).",
        licence_status="public_domain",
        licence_url="https://reporter.nih.gov/faq",
        licence_note=(
            "RePORTER's FAQ answers 'Is the data copyrighted?' with no: it is US "
            "federal government data, public domain in the United States "
            "(https://reporter.nih.gov/faq). Recorded as public_domain."),
        robots_url="https://reporter.nih.gov/robots.txt",
        robots_summary="Not applicable: API only.",
        bulk_available=True,
        historical_depth=(
            "Award notice date and project start/end dates are separate fields, so the "
            "award's own event date and its public-visible date are distinguishable."),
        first_verified_at=now_utc(),
        what_is_new=(
            "The only open grant registry in the source set that resolves a declared "
            "grant number to a specific project and echoes core_project_num back. Nine "
            "declared NIH cores all resolved; 64 project records captured with full "
            "paging (170/170 rows for the queried cores)."),
        id_schemes=["nih_core_project_num", "nih_project_num", "nih_appl_id"],
        entity_types=["grant"],
        blockers=[
            "GET is not supported (HTTP 405, empty body). Any connector that only does "
            "GET will report this source as broken.",
        ],
        notes=(
            "criteria.project_nums accepts BARE core numbers such as R01EB026995 and "
            "returns core_project_num in every row, which is what makes the grant<->work "
            "link machine-verified. A looser core-number regex also accepted the Japan "
            "AMED id 'JP22fk0210090'; the tightened six-digit serial rule rejects it and "
            "the rejected candidate is logged in REPORTER_INDEX.json."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="eu_cordis",
        name="CORDIS (EU research projects)",
        operator="European Commission",
        domain="cordis.europa.eu",
        access_state="OPEN",
        access_evidence=(
            "probe cordis_search_results: HTTP 200 JSON at /api/search/results with "
            "payload.total and payload.results[] including rcn, reference (grant "
            "agreement id), acronym and programme; probe "
            "cordis_search_published_contract_absent: HTTP 404 SPA HTML at "
            "/api/v1/projects; probe cordis_no_publication_index: HTTP 500 "
            "index_not_found_exception. 4 domain queries -> 60 project records."),
        machine_interface=(
            "Undocumented JSON search endpoint /api/search/results?q=&num=; no published "
            "API contract, no OpenAPI document"),
        auth_required=False,
        rate_policy="Undocumented. Used at 1 req/s with num<=25.",
        licence_status="open_no_explicit_licence",
        licence_url="https://commission.europa.eu/legal-notice_en",
        licence_note=(
            "The Commission legal notice permits reuse of Commission documents with "
            "attribution, but /api/search/results is UNDOCUMENTED: no API contract and "
            "no stated machine-interface licence. Recorded as "
            "open_no_explicit_licence, not open_licence."),
        robots_url="https://cordis.europa.eu/robots.txt",
        robots_summary="Only the JSON API path is touched, never the HTML site.",
        bulk_available=False,
        historical_depth=(
            "Dates arrive as human strings with unfilled template tokens such as "
            "'1 {{month_08}} 2014', so no ISO date can be read off them."),
        first_verified_at=now_utc(),
        what_is_new=(
            "Supplies EU project identity (RCN + grant agreement id) and confirmed 1 of "
            "2 declared EU grant numbers for a publication. It does NOT supply "
            "publications, so the reverse direction is impossible."),
        id_schemes=["cordis_rcn", "cordis_grant_agreement_id"],
        entity_types=["grant"],
        blockers=[
            "No publication index: contenttype='publication' -> HTTP 500 "
            "'[es/search] failed: [index_not_found_exception] no such index [publication]'. "
            "EU grant -> publication linkage therefore cannot be built from CORDIS.",
            "The query parser rejects numeric-only tokens: q=685648 -> HTTP 500 "
            "'Error processing the request :Unknown filter type'; "
            "q=contenttype='project' AND 685648 -> HTTP 500 'Query is not valid'. The "
            "quoted form q=\"685648\" works (HTTP 200) and is what the connector uses.",
            "Field queries such as title:'medical device' -> HTTP 500 'Query is not "
            "valid', and an rcn: filter -> HTTP 500. The query language is effectively "
            "free text plus contenttype.",
        ],
        unlock_route=(
            "Use the quoted numeric form for grant-agreement lookup. For a supported "
            "contract, the Commission's open-data route is the CORDIS datasets published "
            "through the EU Open Data Portal (data.europa.eu); that is a bulk download, "
            "not this API, and was not used here."),
        notes=(
            "Because the endpoint is undocumented, every response is saved verbatim so "
            "the behaviour can be re-checked even if the route changes without notice."),
        probe_suite=SUITE,
    ),
    dict(
        source_id="eu_ctis",
        name="EU Clinical Trials Information System (CTIS) public API",
        operator="European Medicines Agency",
        domain="euclinicaltrials.eu",
        access_state="REQUIRES_REGISTRATION",
        access_evidence=(
            "probe ctis_search_blocked: /ctis-public-api/search -> HTTP 403 with the "
            "42-byte body {\"message\":\"Missing Authentication Token\"}; the same 403 "
            "with a dummy X-API-KEY header; probe ctis_retrieve_empty: "
            "/retrieve/<CT number> -> HTTP 200 with a 2-byte {} body; probe "
            "ctis_api_docs_is_spa_shell: /api-docs -> HTTP 200 with the 66 KB "
            "single-page-application HTML shell, not an OpenAPI document."),
        machine_interface=(
            "Advertised as a public REST API, but the search route sits behind an AWS "
            "API Gateway authorizer and no contract is published"),
        auth_required=True,
        registration_url="https://euclinicaltrials.eu/contact/",
        rate_policy="Unknown: no request ever reached the application layer.",
        licence_status="unknown",
        licence_url=None,
        licence_note=(
            "No reuse licence could be established: the API returned 403 before serving "
            "any content and the site serves the application shell instead of a "
            "contract. Recorded as unknown rather than assumed permissive."),
        robots_url="https://euclinicaltrials.eu/robots.txt",
        robots_summary="Only API paths are touched; the SPA HTML shell was read to prove it is a shell.",
        bulk_available=False,
        historical_depth="Unknown: no record was ever served.",
        first_verified_at=now_utc(),
        what_is_new=(
            "Nothing yet: zero rows. This is a recorded negative, and deliberately not "
            "replaced with a guess or with ClinicalTrials.gov data presented as EU data."),
        id_schemes=[],
        entity_types=["clinical_trial"],
        blockers=[
            "HTTP 403 AWS API Gateway 'Missing Authentication Token' on /search, with and "
            "without a dummy X-API-KEY, so it is not a shared static key.",
            "HTTP 200 with a 2-byte {} body on /retrieve/<ct-number>: a success status "
            "carrying no record. This is exactly the shape a naive connector would log "
            "as 'found'.",
            "No OpenAPI document at /api-docs (the SPA shell is returned).",
        ],
        unlock_route=(
            "Request CTIS public-API credentials from EMA through the CTIS contact "
            "route (https://euclinicaltrials.eu/contact/). There is no anonymous tier. "
            "Substitute while waiting: ClinicalTrials.gov API v2 (already used) for "
            "non-EU trials, and the CTIS public web pages for manual checks, which are "
            "not automatable under this project's rules."),
        notes=(
            "eu_ctis is in this workstream's source list, so the deliverable is the "
            "precise blocker rather than a stub connector that emits invented rows."),
        probe_suite=SUITE,
    ),
]


def main() -> int:
    written = []
    for spec in ENTRIES:
        entry = SourceEntry(**spec)
        path = write_entry(_ROOT, entry)
        written.append(path)
        print("  wrote", U.rel(path), "|", entry.access_state, "|", entry.licence_status)
    print(f"{len(written)} registry entries written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
