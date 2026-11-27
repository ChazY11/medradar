"""Materialise ``registry/sources/*.json`` from a single audited fact table.

Keeping the facts in one reviewed file and generating the per-source JSON avoids
the usual failure mode where the register and the code drift apart. Every string
in here is traceable to a probe in ``SOURCE_PROBES/`` or to a licence page whose
text is quoted.

    python tools/build_registry.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from hz.registry import SourceEntry, write_entry  # noqa: E402

VERIFIED = "2026-11-10"

FACTS: list[dict] = [
    # =====================================================================
    # PATENTS — the two channels that actually work
    # =====================================================================
    dict(
        source_id="epo_publication_server",
        name="EPO European Publication Server (sitemap + INID front pages)",
        operator="European Patent Office",
        domain="data.epo.org",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "SOURCE_PROBES/patents: sitemap index 200/360906 B; weekly gzip sitemap "
            "200/238148 B; document.html 200/124905 B; document.pdf 200/524450 B. "
            "Live collection of 228 records over 241 requests / 30.7 MB."
        ),
        machine_interface="gzip XML sitemap index -> weekly sitemap -> HTML/PDF document",
        auth_required=False,
        rate_policy="no published limit; EPO asks indexers to register; we self-limit to ~1.5 req/s and a fixed budget",
        licence_status="open_no_explicit_licence",
        licence_url="https://www.epo.org/en/legal",
        licence_note=(
            "Official public patent publications. The EPO terms of use apply; no explicit "
            "reuse licence is stated for the publication servers. We therefore keep derived "
            "bibliographic records plus bounded hashed samples rather than a mirror, and "
            "record this as open_no_explicit_licence rather than claiming CC-style rights."
        ),
        robots_url="https://data.epo.org/robots.txt",
        robots_summary=(
            "Advertises /publication-server/sitemap.xml and /gpi/sitemap.xml; disallows "
            "/pise-server/, /qual_lod/ and /linked-data/{id,doc,data,def,representation}/. "
            "Asks crawler operators to e-mail patentinformation@epo.org to register for "
            "deep redirects when building indexes. This connector samples and does not index."
        ),
        bulk_available=True,
        historical_depth="EP publications from 1978-12-20 to present (weekly since 1978-12-20)",
        first_verified_at=VERIFIED,
        what_is_new=(
            "The only keyless channel found that yields applicant-of-record, inventor, IPC, "
            "CPC, filing date, publication date, priority and abstract for real EP patents. "
            "This is the first working patent acquisition asset for MedRadar."
        ),
        id_schemes=["epo_publication_number", "epo_application_number", "pct_application_number"],
        entity_types=["patent_publication"],
        blockers=[],
        unlock_route=(
            "None needed for bounded research use. For index-scale harvesting, register with "
            "patentinformation@epo.org as the robots.txt asks."
        ),
        probe_suite="patents",
        notes="INID 43 = application publication date, INID 45 = grant publication date. The connector selects by kind; using 43 for a B grant would misdate it by years.",
    ),
    dict(
        source_id="cipo_canada",
        name="CIPO Patent bulk data (PT_Main / PT_Interested_Party / PT_IPC / PT_Priority)",
        operator="Canadian Intellectual Property Office (ISED)",
        domain="opic-cipo.ca",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "open.canada.ca CKAN package fe1dfbb9-0fc3-42ca-b2a9-6ca4c05dbac9 resolves 152 "
            "resources; 8 range files downloaded and SHA-256 recorded in "
            "DATASETS/patents/cipo_canada/raw/PROVENANCE.json."
        ),
        machine_interface="CKAN catalogue -> zipped CSV range files (8 tables, 2 splits each)",
        auth_required=False,
        rate_policy="CKAN API returned 429 once; connector backs off 4x with sleeps",
        licence_status="open_licence",
        licence_url="https://open.canada.ca/en/open-government-licence-canada",
        licence_note=(
            "Open Government Licence - Canada. Quoted: 'grants you a worldwide, royalty-free, "
            "perpetual, non-exclusive licence to use the Information, including for commercial "
            "purposes'. Attribution required: 'Contains information licensed under the Open "
            "Government Licence - Canada'."
        ),
        robots_url="https://opic-cipo.ca/robots.txt",
        robots_summary="not retrieving documents by crawler; bulk archives fetched from catalogue-listed URLs",
        bulk_available=True,
        historical_depth="patent documents 1869 -> 2022-02-28 (dataset statement)",
        first_verified_at=VERIFIED,
        what_is_new=(
            "Second jurisdiction AND an explicit open licence. Uniquely carries an ownership "
            "timeline (Owner Enable Date / Ownership End date) per party, which is exactly "
            "what historical subsidiary-vs-parent attribution needs."
        ),
        id_schemes=["cipo_patent_number", "pct_application_number", "pct_publication_number"],
        entity_types=["patent_publication"],
        blockers=[
            "Snapshot only: bibliographic extract ends 2022-02-28, so no record-level history.",
            "No publication / open-to-inspection date field; only Filing Date and Grant Date.",
            "opic-cipo.ca serves an incomplete TLS chain (omits intermediate).",
        ],
        unlock_route=(
            "TLS: intermediate obtained from the leaf's AIA caIssuers URL and added to a bundle "
            "(hz.tls.complete_chain); verification is still enforced. Freshness: CIPO states "
            "the dataset is refreshed quarterly through IP Horizons, so a newer extract can be "
            "picked up from the same catalogue record when published."
        ),
        probe_suite="patents_unlock",
        notes="Do NOT apply the 18-month laid-open rule as a date. Pending applications get source_public_at = NULL + MISSING_PUBLICATION_DATE.",
    ),
    # =====================================================================
    # PATENTS — blocked, with the lawful unlock route recorded
    # =====================================================================
    dict(
        source_id="epo_ops",
        name="EPO Open Patent Services (OPS)",
        operator="European Patent Office",
        domain="ops.epo.org",
        access_state="REQUIRES_REGISTRATION",
        access_evidence="SOURCE_PROBES/patents: 403 / 208 B on both /rest-services/ and a biblio path, anonymously",
        machine_interface="REST + OAuth2 (client id / secret)",
        auth_required=True,
        registration_url="https://developers.epo.org/",
        rate_policy="tiered free quota per registered app",
        licence_status="terms_restricted",
        licence_url="https://www.epo.org/en/legal",
        licence_note="Free but contract-gated: needs a registered OPS account and an OAuth consumer key.",
        bulk_available=True,
        historical_depth="full EP/DOCDB bibliographic coverage",
        first_verified_at=VERIFIED,
        what_is_new="Would add applicant/inventor search and citation data that the sitemap channel cannot query.",
        id_schemes=["epo_publication_number", "docdb_family_id"],
        entity_types=["patent_publication"],
        blockers=["403 anonymous; OAuth consumer key required", "https://developers.epo.org/ returns a 403 WAF challenge to clients"],
        unlock_route=(
            "Project owner registers once at https://developers.epo.org/ (free), creates an "
            "OPS consumer key, and exports it as an environment variable. HORIZON does not "
            "register accounts on the owner's behalf."
        ),
        probe_suite="patents",
    ),
    dict(
        source_id="uspto_open_data_portal",
        name="USPTO Open Data Portal (ODP) API and bulk files",
        operator="United States Patent and Trademark Office",
        domain="api.uspto.gov / data.uspto.gov",
        access_state="REQUIRES_REGISTRATION",
        access_evidence=(
            "SOURCE_PROBES/patents: api.uspto.gov/api/v1/datasets/products/search -> 401 / 26 B; "
            "bulk file path -> 403 / 42 B"
        ),
        machine_interface="REST JSON, API key required; bulk products also keyed",
        auth_required=True,
        registration_url="https://data.uspto.gov/apis/getting-started",
        rate_policy="per-key rate limits published in ODP docs",
        licence_status="public_domain",
        licence_url="https://www.uspto.gov/terms-use-uspto-websites",
        licence_note=(
            "US Government work; USPTO terms quoted: 'Bulk data products may be separately "
            "obtained from the USPTO, either for free ...' and 'USPTO's online databases are "
            "not designed or intended to be a source for bulk downloads ... generating unusually "
            "high numbers of database accesses ... may be denied access'."
        ),
        bulk_available=True,
        historical_depth="US patents from 1790; bulk XML by week",
        first_verified_at=VERIFIED,
        what_is_new="The authoritative US patent corpus, including assignee and citation tables.",
        id_schemes=["uspto_patent_number", "uspto_application_number"],
        entity_types=["patent_publication"],
        blockers=["every api.uspto.gov path returns 401/403 without a key", "legacy keyless hosts are gone or WAF-challenged"],
        unlock_route=(
            "Project owner creates a free USPTO ODP account and API key at "
            "https://data.uspto.gov/apis/getting-started; bulk products are then downloadable "
            "per dataset. This matches USPTO's own stated route for bulk use."
        ),
        probe_suite="patents_unlock",
    ),
    dict(
        source_id="patentsview",
        name="PatentsView (USPTO)",
        operator="USPTO (formerly a joint USPTO/American Institutes for Research project)",
        domain="patentsview.org / search.patentsview.org",
        access_state="BLOCKED_TECHNICAL",
        access_evidence=(
            "SOURCE_PROBES/patents: legacy api.patentsview.org answered 200 with 20666 B that is "
            "the ODP single-page-app shell (expected marker 'patents' absent); "
            "search.patentsview.org does not resolve in DNS; "
            "s3://data.patentsview.org/download/... returns 403"
        ),
        machine_interface="retired search API; bulk S3 no longer public",
        auth_required=True,
        registration_url="https://patentsview.org/",
        licence_status="unknown",
        bulk_available=False,
        historical_depth="n/a (retired)",
        first_verified_at=VERIFIED,
        what_is_new="Nothing now: this is a documentation of a retired channel so the next round does not chase it again.",
        id_schemes=[],
        entity_types=["patent_publication"],
        blockers=[
            "legacy API host now serves the USPTO ODP shell instead of JSON",
            "search.patentsview.org: DNS resolution failure from this host",
            "bulk S3 objects return 403",
        ],
        unlock_route=(
            "Use USPTO ODP instead (same underlying data). PatentsView-era bulk tables were "
            "absorbed into ODP, which needs a free API key."
        ),
        probe_suite="patents",
    ),
    dict(
        source_id="espacenet",
        name="Espacenet publication-details service",
        operator="European Patent Office",
        domain="worldwide.espacenet.com",
        access_state="BLOCKED_TECHNICAL",
        access_evidence="SOURCE_PROBES/patents: 403 / 5878 B WAF challenge page (awswaf/captcha signature)",
        machine_interface="web UI only for clients",
        auth_required=True,
        licence_status="terms_restricted",
        licence_url="https://www.epo.org/en/legal",
        bulk_available=False,
        historical_depth="worldwide",
        first_verified_at=VERIFIED,
        what_is_new="Would add worldwide DOCDB search; unreachable without a browser and is explicitly a WAF-protected UI.",
        id_schemes=["docdb_publication_number"],
        entity_types=["patent_publication"],
        blockers=["AWS WAF challenge on direct requests — treated as an anti-automation control and not circumvented"],
        unlock_route="Use EPO OPS with a registered key instead of the web UI.",
        probe_suite="patents",
    ),
    dict(
        source_id="wipo_patentscope",
        name="WIPO PATENTSCOPE",
        operator="World Intellectual Property Organization",
        domain="patentscope.wipo.int",
        access_state="MANUAL_ONLY",
        access_evidence=(
            "SOURCE_PROBES/patents: search UI 200 / 52215 B; bulk-download endpoint 404 / 8020 B"
        ),
        machine_interface="JSF web application; no anonymous bulk endpoint found",
        auth_required=True,
        licence_status="terms_restricted",
        licence_url="https://www.wipo.int/terms-of-use/",
        bulk_available=False,
        historical_depth="PCT and many national collections",
        first_verified_at=VERIFIED,
        what_is_new="PCT international applications would add a filing-stage view not present in EP publication data.",
        id_schemes=["pct_application_number", "pct_publication_number"],
        entity_types=["patent_publication"],
        blockers=["no anonymous machine interface", "stateful JSF session — scraping would be fragile and is not attempted"],
        unlock_route="WIPO offers PATENTSCOPE data to registered users/offices; request route is via WIPO customer support.",
        probe_suite="patents",
    ),
    dict(
        source_id="lens_org",
        name="Lens.org patent API",
        operator="Cambia / Lens.org",
        domain="api.lens.org",
        access_state="REQUIRES_REGISTRATION",
        access_evidence="SOURCE_PROBES/patents: 401 / 114 B",
        machine_interface="REST with bearer token",
        auth_required=True,
        registration_url="https://www.lens.org/lens/user/subscriptions",
        licence_status="terms_restricted",
        bulk_available=False,
        historical_depth="large worldwide corpus",
        first_verified_at=VERIFIED,
        what_is_new="Cross-office citation and family data; a good supplementary source once a token exists.",
        id_schemes=["lens_id"],
        entity_types=["patent_publication"],
        blockers=["401 anonymous"],
        unlock_route="Free research account at lens.org; API token issued to the account.",
        probe_suite="patents",
    ),
    dict(
        source_id="google_patents",
        name="Google Patents",
        operator="Google",
        domain="patents.google.com",
        access_state="MANUAL_ONLY",
        access_evidence="SOURCE_PROBES/patents: record page 200 / 371596 B (read-only single record)",
        machine_interface="no public bulk API outside BigQuery; site is not offered for bulk retrieval",
        auth_required=True,
        licence_status="terms_restricted",
        licence_url="https://policies.google.com/terms",
        bulk_available=True,
        historical_depth="worldwide",
        first_verified_at=VERIFIED,
        what_is_new="The BigQuery public dataset would be excellent, but it requires a Google Cloud project with billing enabled — a registration plus payment barrier.",
        id_schemes=["google_patents_id"],
        entity_types=["patent_publication"],
        blockers=["bulk access requires Google Cloud billing account", "site scraping is contrary to the terms for bulk use — not attempted"],
        unlock_route="Enable the Google Patents public dataset in BigQuery under a project owner's own GCP account.",
        probe_suite="patents",
    ),
    dict(
        source_id="epo_linked_open_data",
        name="Linked open EP data (LOD)",
        operator="European Patent Office",
        domain="data.epo.org/linked-data",
        access_state="BLOCKED_TECHNICAL",
        access_evidence="SOURCE_PROBES/patents: API root 500 / 114 B; landing page 200 / 2793 B",
        machine_interface="RDF/SPARQL-style API behind a SPA",
        auth_required=True,
        licence_status="unknown",
        bulk_available=False,
        historical_depth="EP bibliographic + classification",
        first_verified_at=VERIFIED,
        what_is_new="Classification and citation triples in RDF; would be useful if the endpoint is restored.",
        id_schemes=["epo_publication_number"],
        entity_types=["patent_publication"],
        blockers=["API root returns 500", "robots.txt disallows the document/data/id paths, so not crawled even if up"],
        unlock_route="Re-probe later; if it returns, consume only via the documented API root, not the disallowed paths.",
        probe_suite="patents",
    ),
    dict(
        source_id="epo_global_patent_index",
        name="EPO Global Patent Index (GPI) sitemap",
        operator="European Patent Office",
        domain="data.epo.org/gpi",
        access_state="BLOCKED_TECHNICAL",
        access_evidence="SOURCE_PROBES/patents: sitemap advertised in robots.txt returns 404 / 0 B",
        machine_interface="none currently advertised",
        auth_required=False,
        licence_status="unknown",
        bulk_available=False,
        historical_depth="n/a",
        first_verified_at=VERIFIED,
        what_is_new="Nothing yet: robots.txt advertises a sitemap that does not resolve. Documented so it is not chased blindly.",
        id_schemes=[],
        entity_types=["patent_publication"],
        blockers=["robots.txt advertises https://data.epo.org/gpi/sitemap.xml but it 404s"],
        unlock_route="Ask EPO patent information for GPI access; not attempted.",
        probe_suite="patents",
    ),
    dict(
        source_id="uspto_bulkdata",
        name="bulkdata.uspto.gov (legacy bulk host)",
        operator="USPTO",
        domain="bulkdata.uspto.gov",
        access_state="BLOCKED_TECHNICAL",
        access_evidence="SOURCE_PROBES/patents: DNS resolution failure (getaddrinfo failed)",
        machine_interface="retired host",
        auth_required=False,
        licence_status="public_domain",
        bulk_available=False,
        historical_depth="retired",
        first_verified_at=VERIFIED,
        what_is_new="Confirms the legacy keyless bulk host is gone; bulk now lives behind ODP.",
        id_schemes=[],
        entity_types=["patent_publication"],
        blockers=["host no longer resolves"],
        unlock_route="Use data.uspto.gov with an ODP API key.",
        probe_suite="patents",
    ),
    dict(
        source_id="jpo_bulk",
        name="JPO patent data (Japan)",
        operator="Japan Patent Office",
        domain="www.jpo.go.jp",
        access_state="BLOCKED_TECHNICAL",
        access_evidence="SOURCE_PROBES/patents_unlock: 403 / 9939 B on two distinct JPO pages",
        machine_interface="not reachable from this host",
        auth_required=True,
        licence_status="unknown",
        bulk_available=True,
        historical_depth="JP patents; JPO does publish bulk data under application",
        first_verified_at=VERIFIED,
        what_is_new="A third patent jurisdiction, blocked at the network edge rather than by policy.",
        id_schemes=["jp_application_number"],
        entity_types=["patent_publication"],
        blockers=["403 on every JPO page reached from this host (likely geo/UA filtering)"],
        unlock_route="JPO bulk data is requested through the JPO's published application procedure; also reachable via EPO OPS worldwide data with a key.",
        probe_suite="patents_unlock",
    ),
    dict(
        source_id="dpma_open_data",
        name="DPMA (Germany) open data / DPMAregister",
        operator="Deutsches Patent- und Markenamt",
        domain="dpma.de / register.dpma.de",
        access_state="MANUAL_ONLY",
        access_evidence=(
            "SOURCE_PROBES/patents_unlock: register search page 200 / 160771 B; the open-data "
            "landing path used returned 404, so the correct data URL still has to be found"
        ),
        machine_interface="human search interface reachable; machine interface not established",
        auth_required=False,
        licence_status="unknown",
        licence_url="https://www.dpma.de/english/service/opendata/index.html",
        bulk_available=True,
        historical_depth="DE patents",
        first_verified_at=VERIFIED,
        what_is_new="A fourth jurisdiction, but not yet turned into an asset: the register UI is reachable while the documented open-data path was not at the URL tried.",
        id_schemes=["de_application_number"],
        entity_types=["patent_publication"],
        blockers=["open-data landing URL tried returned 404", "no machine interface confirmed"],
        unlock_route="Confirm the current DPMA open-data URL from the DPMA site index, then probe; DPMA publishes free bulk datasets under its own terms.",
        probe_suite="patents_unlock",
    ),
    dict(
        source_id="ip_australia",
        name="IP Australia patent datasets on data.gov.au",
        operator="IP Australia",
        domain="data.gov.au",
        access_state="OPEN_DOCUMENTED",
        access_evidence="SOURCE_PROBES/patents_unlock: CKAN package_search 200 / 18778 B with '\"success\"' present; 147 patent-related packages",
        machine_interface="CKAN API",
        auth_required=False,
        licence_status="open_licence",
        licence_url="https://data.gov.au/data/dataset?q=patents",
        licence_note="Datasets carry CC BY 2.5/3.0 Australia or 'Other (Open)' licences; check per dataset before reuse.",
        bulk_available=True,
        historical_depth="mostly aggregate/statistical datasets plus an authority file, not full patent texts",
        first_verified_at=VERIFIED,
        what_is_new="Mostly statistics rather than bibliographic records, so the marginal research value is low for MedRadar. Recorded as available but not worth an asset this round.",
        id_schemes=[],
        entity_types=["patent_publication"],
        blockers=["no full bibliographic patent corpus found in the catalogue sample"],
        unlock_route="n/a — catalogue is open; only useful for aggregate statistics",
        probe_suite="patents_unlock",
    ),
]


def main() -> int:
    n = 0
    for f in FACTS:
        entry = SourceEntry(**f)
        path = write_entry(ROOT, entry)
        n += 1
        print(f"wrote {os.path.relpath(path, ROOT)}")
    print(f"{n} source entries written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
