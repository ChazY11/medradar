"""SCHOLARLY workstream probe suite.

Declarative ACCESS-only probes for every *GET* endpoint the scholarly
connectors touch. A probe result states ACCESS, never DATA or RESEARCH.

POST-only endpoints (Semantic Scholar batch lookup, NIH RePORTER project
search) cannot be expressed as ``hz.probe.Probe`` because that runner is
GET-only. They are probed by
``CONNECTORS/scholarly/probe_post_endpoints.py``, which writes
``SOURCE_PROBES/scholarly/POST_CALLS.json`` next to the GET probe output and
appends the same ``REQUEST_LOG.jsonl`` format.

Run:
    python -m hz.cli probe --suite scholarly --max-requests 26

IMPORTANT implementation note
-----------------------------
This suite inlines the full query string into ``url`` for every probe and leaves
``params`` unset. That is deliberate and is kept even though the shared client's
cache key was subsequently fixed to ``(url, sorted params)``:

* it makes every probe URL globally unique, so no probe can ever be served
  another probe's response, whatever the client's cache policy becomes;
* it makes the probe record self-describing -- the exact request is visible in
  ``PROBES.json`` without needing to join a separate ``params`` field.

The bug it originally worked around: ``hz.http.BoundedClient.get`` memoised on
``url`` alone, so two probes sharing a base URL but differing only in ``params``
collided and the second silently received the first response. Three probes in the
first draft of this suite were corrupted that way. Every connector in
``CONNECTORS/scholarly/`` was also written to build unique URLs rather than rely
on ``params``; see ``experiments/scholarly/verify_cache_integrity.py`` for the
offline audit that re-checks the saved raw responses against the anchors.
"""

from __future__ import annotations

from .probe import Probe

# A DOI deliberately outside the EXP-H1 anchor sample (numpy, 2020, Nature).
# Using an out-of-sample DOI keeps syntax/access probing from consuming sample
# records.
OUT_OF_SAMPLE_DOI = "10.1038/s41586-020-2649-2"
# A DOI that is well-formed but is not registered.
ABSENT_DOI = "10.9999/horizon-001-does-not-exist-0001"
CONTACT = "medradar-research@proton.me"


def probes() -> list[Probe]:
    return [
        # ---------------------------------------------------------- OpenAlex
        Probe(
            probe_id="openalex_works_search",
            source_id="openalex",
            url=(
                "https://api.openalex.org/works?filter="
                "raw_affiliation_strings.search:mindray,"
                "from_publication_date:2023-01-01,to_publication_date:2023-01-31,"
                "has_doi:true"
                "&per-page=2&select=id,doi,ids,display_name,publication_date,"
                "created_date,updated_date"
                f"&mailto={CONTACT}"
            ),
            question=(
                "Does the OpenAlex works endpoint accept a compound filter "
                "(affiliation search + publication window + has_doi) and a bounded "
                "per-page, returning JSON without a key?"
            ),
            expect_marker='"results"',
            note=(
                "Filter names verified live: raw_affiliation_strings.search, "
                "title_and_abstract.search, from_publication_date, "
                "to_publication_date, has_doi. Window here is 2023-01, "
                "deliberately disjoint from the EXP-H1 2020-2022 sample window. "
                "Query string is inlined because the client caches on url only."
            ),
        ),
        Probe(
            probe_id="openalex_select_contract",
            source_id="openalex",
            url=(
                "https://api.openalex.org/works?filter=has_doi:true&per-page=1"
                f"&select=grants&mailto={CONTACT}"
            ),
            question=(
                "Is the set of fields that can be projected with `select` closed and "
                "self-describing, so that a missing field is a documented 400 rather "
                "than a silent null?"
            ),
            expect_status=(400,),
            expect_marker="not a valid select field",
            note=(
                "Documents that `grants` is NOT selectable on works; `awards` and "
                "`funders` are. Used to justify the select list in EXP_H1."
            ),
        ),
        # ------------------------------------------------------------ Crossref
        Probe(
            probe_id="crossref_works_doi",
            source_id="crossref",
            url=f"https://api.crossref.org/works/{OUT_OF_SAMPLE_DOI}",
            question=(
                "Does the Crossref REST API return full work metadata for a DOI "
                "without a key, including created/issued/published-print/"
                "published-online timestamps and funder award metadata?"
            ),
            headers={"User-Agent": f"MedRadar-HORIZON-001/1.0 (mailto:{CONTACT})"},
            expect_marker='"message"',
            note="Anonymous access; Crossref asks for a contact in the User-Agent.",
        ),
        Probe(
            probe_id="crossref_absent_doi",
            source_id="crossref",
            url=f"https://api.crossref.org/works/{ABSENT_DOI}",
            question="Does a non-registered DOI yield a clean 404 (ABSENT) rather than a 200 with empty metadata?",
            expect_status=(404,),
            headers={"User-Agent": f"MedRadar-HORIZON-001/1.0 (mailto:{CONTACT})"},
            expect_marker="Resource not found",
            note="Defines what 'source does not hold this work' looks like.",
        ),
        # ---------------------------------------------------------- Europe PMC
        Probe(
            probe_id="europepmc_search_core",
            source_id="europepmc",
            url=(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                f'?query=DOI:"{OUT_OF_SAMPLE_DOI}"&format=json&resultType=core&pageSize=1'
            ),
            question=(
                "Does Europe PMC search return resultType=core with pmid, pmcid, doi, "
                "firstPublicationDate, electronicPublicationDate and grantsList?"
            ),
            expect_marker='"firstPublicationDate"',
            note="No key required. Core result type carries the grant and date fields.",
        ),
        Probe(
            probe_id="europepmc_grant_field",
            source_id="europepmc",
            url=(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                '?query=GRANT_ID:"R01 HL123456"&format=json&resultType=lite&pageSize=1'
            ),
            question="Does Europe PMC expose a queryable GRANT_ID field usable for grant<->work linkage?",
            expect_marker='"hitCount"',
            note="Syntactically accepted; a zero hitCount is a real answer, not a failure.",
        ),
        Probe(
            probe_id="europepmc_nct_fulltext",
            source_id="europepmc",
            url=(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                '?query=%22NCT04494867%22&format=json&resultType=lite&pageSize=2'
            ),
            question=(
                "Can a trial registry identifier be found as a literal string in "
                "Europe PMC's indexed text, enabling paper->trial linkage?"
            ),
            expect_marker='"hitCount"',
            note=(
                "NCT04494867 is an arbitrary registry id used only to test the "
                "string-search capability; it is not part of the EXP-H1 sample."
            ),
        ),
        # ------------------------------------------------------ PubMed E-utilities
        Probe(
            probe_id="pubmed_eutils_esearch",
            source_id="pubmed_eutils",
            url=(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                f'?db=pubmed&term="{OUT_OF_SAMPLE_DOI}"[doi]&retmode=json&retmax=2'
            ),
            question="Does esearch resolve a DOI to a PMID list via the [doi] field tag without a key?",
            expect_marker='"idlist"',
            note="NCBI E-utilities, anonymous tier. No api_key sent.",
        ),
        Probe(
            probe_id="pubmed_eutils_efetch",
            source_id="pubmed_eutils",
            url=(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                "?db=pubmed&id=32939066&retmode=xml"
            ),
            question="Does efetch return the ArticleIdList with doi/pubmed/pmc IdTypes for a known PMID?",
            expect_marker="ArticleIdList",
            note="PMID 32939066 is the out-of-sample Nature/numpy article.",
        ),
        # ------------------------------------------------------ Semantic Scholar
        Probe(
            probe_id="semanticscholar_paper_get",
            source_id="semantic_scholar",
            url=(
                "https://api.semanticscholar.org/graph/v1/paper/"
                f"DOI:{OUT_OF_SAMPLE_DOI}"
                "?fields=title,externalIds,publicationDate,venue,publicationTypes,journal"
            ),
            question=(
                "Does the Semantic Scholar Graph API resolve a DOI to externalIds "
                "(PubMed, PubMedCentral, ArXiv, MAG) without a key?"
            ),
            expect_marker='"externalIds"',
            note=(
                "The experiment uses the POST /paper/batch form; this GET probe "
                "establishes that the identifier surface is the same. Batch POST is "
                "probed in POST_CALLS.json."
            ),
        ),
        # -------------------------------------------------------------- OpenAIRE
        Probe(
            probe_id="openaire_researchproducts_pid",
            source_id="openaire",
            url=(
                "https://api.openaire.eu/graph/v1/researchProducts"
                f"?pid={OUT_OF_SAMPLE_DOI}&pageSize=1"
            ),
            question=(
                "Does the OpenAIRE Graph resolve a DOI passed as a *bare* `pid` value, "
                "and return pids/instances/originalIds?"
            ),
            expect_marker='"numFound"',
            note=(
                "Verified negative: `pid=doi:10.xxxx` and `pid=doi|10.xxxx` both "
                "return numFound=0. Only the bare DOI form resolves."
            ),
        ),
        Probe(
            probe_id="openaire_projects_search",
            source_id="openaire",
            url=(
                "https://api.openaire.eu/graph/v1/projects"
                "?keywords=medical%20device&pageSize=1"
            ),
            question="Is the OpenAIRE project/grant endpoint open and does it expose grant codes?",
            expect_marker='"numFound"',
            note="Checked as an alternative EU grant route to CORDIS.",
        ),
        # --------------------------------------------------- ClinicalTrials.gov
        Probe(
            probe_id="ctgov_studies_search",
            source_id="clinicaltrials_gov",
            url=(
                "https://clinicaltrials.gov/api/v2/studies"
                "?query.spons=Medtronic&pageSize=2"
            ),
            question=(
                "Does the CT.gov API v2 study search work keyless, and does it accept "
                "query.spons plus pageSize?"
            ),
            expect_marker='"protocolSection"',
            note=(
                "Verified: the `fields` projection parameter rejects leaf names such "
                "as ReferenceDOI with HTTP 400, so the connectors request whole study "
                "objects instead of fragile field projections."
            ),
        ),
        Probe(
            probe_id="ctgov_study_detail",
            source_id="clinicaltrials_gov",
            url="https://clinicaltrials.gov/api/v2/studies/NCT00631709",
            question=(
                "Does the single-study endpoint return statusModule posting dates and a "
                "referencesModule (when the study has one)?"
            ),
            expect_marker='"statusModule"',
            note="NCT00631709 is a Medtronic-sponsored pacemaker study used as an access example.",
        ),
        Probe(
            probe_id="ctgov_fields_projection_rejected",
            source_id="clinicaltrials_gov",
            url=(
                "https://clinicaltrials.gov/api/v2/studies"
                "?query.term=medical%20device&pageSize=1&fields=NCTId,ReferenceDOI"
            ),
            question="Is the `fields` projection contract closed, i.e. does an invalid leaf name fail closed?",
            expect_status=(400,),
            expect_marker="invalid field name",
            note="Evidence for why connectors do not rely on `fields` projections.",
        ),
        # ---------------------------------------------------------- NIH RePORTER
        Probe(
            probe_id="nih_reporter_get_405",
            source_id="nih_reporter",
            url="https://api.reporter.nih.gov/v2/projects/search",
            question=(
                "Does a GET on the NIH RePORTER v2 search endpoint fail with 405, "
                "confirming POST is mandatory?"
            ),
            expect_status=(405,),
            note=(
                "Expected failure, recorded as evidence. The working POST is probed in "
                "POST_CALLS.json via requests.post."
            ),
        ),
        # --------------------------------------------------------------- CORDIS
        Probe(
            probe_id="cordis_search_results",
            source_id="eu_cordis",
            url=(
                "https://cordis.europa.eu/api/search/results"
                "?q=contenttype%3D%27project%27%20AND%20medical%20device&num=2"
            ),
            question=(
                "Does CORDIS expose an undocumented-but-open JSON search endpoint that "
                "returns project records with RCN / grant agreement ids?"
            ),
            expect_marker='"payload"',
            note=(
                "No published API contract found. /api/, /api/v1/projects, "
                "/api/v1/search, /api/search all return the 404 SPA shell. "
                "/api/search/results returns JSON. Undocumented => licence posture "
                "open_no_explicit_licence."
            ),
        ),
        Probe(
            probe_id="cordis_search_published_contract_absent",
            source_id="eu_cordis",
            url="https://cordis.europa.eu/api/v1/projects?format=json&p=1&num=1",
            question="Is there a documented CORDIS project API at the /api/v1 path?",
            expect_status=(404,),
            expect_marker="CORDIS",
            note="404 SPA shell returned; documents that the /v1 route is not a JSON API.",
        ),
        Probe(
            probe_id="cordis_no_publication_index",
            source_id="eu_cordis",
            url="https://cordis.europa.eu/api/search/results?q=contenttype%3D%27publication%27&num=1",
            question=(
                "Does CORDIS carry a publication index, which would be required to link "
                "an EU grant to a scholarly work?"
            ),
            expect_status=(500,),
            expect_marker="index_not_found_exception",
            note=(
                "The answer is a hard negative: Elasticsearch reports "
                "`no such index [publication]`. CORDIS has project/result/article "
                "indices but no publication index, so grant->publication linkage "
                "cannot be built from CORDIS alone."
            ),
        ),
        # -------------------------------------------------------------- EU CTIS
        Probe(
            probe_id="ctis_search_blocked",
            source_id="eu_ctis",
            url=(
                "https://euclinicaltrials.eu/ctis-public-api/search"
                "?pagination.page=1&pagination.size=2"
            ),
            question="Is the EU CTIS public search API usable without an EMA-issued credential?",
            expect_status=(403,),
            expect_marker="Missing Authentication Token",
            note=(
                "AWS API Gateway 'Missing Authentication Token' body. Also returned "
                "with a dummy X-API-KEY header, so the gate is not a simple shared key. "
                "Unlock route: EMA CTIS public-API access request."
            ),
        ),
        Probe(
            probe_id="ctis_retrieve_empty",
            source_id="eu_ctis",
            url="https://euclinicaltrials.eu/ctis-public-api/retrieve/2024-511234-12-00",
            question="Does the CTIS retrieve path return trial data for a plausible CT number?",
            expect_marker=None,
            note=(
                "Returns a 2-byte `{}` body with HTTP 200 - a success status carrying no "
                "record. This is the exact shape a naive connector would mistake for a "
                "positive result."
            ),
        ),
        Probe(
            probe_id="ctis_api_docs_is_spa_shell",
            source_id="eu_ctis",
            url="https://euclinicaltrials.eu/ctis-public-api/api-docs",
            question=(
                "Is a machine-readable API description published at the advertised "
                "api-docs path?"
            ),
            expect_marker="<html",
            note=(
                "Returns the 66 KB single-page-application HTML shell, not an OpenAPI "
                "document. So the CTIS contract is not discoverable from the site."
            ),
        ),
    ]
