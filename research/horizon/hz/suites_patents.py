"""Patent-access probe suite.

Every candidate channel for legal, free, machine-readable patent data is
probed here so that the resulting ``PROBES.json`` is the evidence behind
``PATENT_ACCESS_REPORT.md``. A probe that fails is a deliverable, not a bug.
"""

from __future__ import annotations

from .probe import Probe


def probes() -> list[Probe]:
    return [
        # ---------------------------------------------------------------
        # 1. EPO European Publication Server  (the channel that works)
        # ---------------------------------------------------------------
        Probe(
            probe_id="epo_pubsrv_sitemap_index",
            source_id="epo_publication_server",
            url="https://data.epo.org/publication-server/sitemap.xml",
            question=(
                "Does the EPO advertise a public sitemap index of EP publications, "
                "as referenced in its own robots.txt?"
            ),
            expect_marker="sitemapindex",
            note="robots.txt at https://data.epo.org/robots.txt lists this sitemap",
        ),
        Probe(
            probe_id="epo_pubsrv_weekly_sitemap",
            source_id="epo_publication_server",
            url="https://data.epo.org/publication-server/sitemap.2025-01-08.xml.gz",
            question="Is a weekly sitemap gzip fetchable without any credential?",
            note="binary gzip; validated separately by the connector",
        ),
        Probe(
            probe_id="epo_pubsrv_document_html",
            source_id="epo_publication_server",
            url=(
                "https://data.epo.org/publication-server/rest/v1.2/publication-dates/"
                "2025-01-08/patents/EP4488863NWA1/document.html"
            ),
            question="Does a publication HTML carry the INID-coded front page "
            "(applicant, inventor, IPC, filing date, publication date)?",
            expect_marker="(71)",
            note="(71) is the INID code for applicant",
        ),
        Probe(
            probe_id="epo_pubsrv_document_pdf",
            source_id="epo_publication_server",
            url=(
                "https://data.epo.org/publication-server/rest/v1.2/publication-dates/"
                "2025-01-08/patents/EP4488863NWA1/document.pdf"
            ),
            question="Is the PDF also public and keyless?",
        ),
        Probe(
            probe_id="epo_pubsrv_robots",
            source_id="epo_publication_server",
            url="https://data.epo.org/robots.txt",
            question="What does the operator say about crawler access?",
        ),
        # ---------------------------------------------------------------
        # 2. EPO OPS (historical assumption: free with key)
        # ---------------------------------------------------------------
        Probe(
            probe_id="epo_ops_biblio_anonymous",
            source_id="epo_ops",
            url="https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/EP1000000/biblio",
            question="Does EPO OPS answer anonymously, or is OAuth required?",
            auth_required=True,
        ),
        Probe(
            probe_id="epo_ops_root",
            source_id="epo_ops",
            url="https://ops.epo.org/3.2/rest-services/",
            question="Is the OPS service endpoint itself reachable?",
            auth_required=True,
        ),
        # ---------------------------------------------------------------
        # 3. EPO Linked Open Data (RDF) — robots.txt disallows crawler paths
        # ---------------------------------------------------------------
        Probe(
            probe_id="epo_lod_api_root",
            source_id="epo_linked_open_data",
            url="https://data.epo.org/linked-data/api",
            question="Does the Linked Open EP Data API answer?",
            note=(
                "robots.txt Disallow entries cover /linked-data/{id,doc,data,def,representation}/; "
                "probed at the documented API root only, and not crawled"
            ),
            auth_required=True,
        ),
        Probe(
            probe_id="epo_lod_page",
            source_id="epo_linked_open_data",
            url="https://data.epo.org/linked-data/",
            question="Is the LOD landing page live (i.e. service still offered)?",
        ),
        # ---------------------------------------------------------------
        # 4. EPO Global Patent Index sitemap promised by robots.txt
        # ---------------------------------------------------------------
        Probe(
            probe_id="epo_gpi_sitemap",
            source_id="epo_global_patent_index",
            url="https://data.epo.org/gpi/sitemap.xml",
            question="Does the GPI sitemap advertised in robots.txt resolve?",
        ),
        # ---------------------------------------------------------------
        # 5. USPTO — everything migrated behind the Open Data Portal
        # ---------------------------------------------------------------
        Probe(
            probe_id="uspto_odp_dataset_search",
            source_id="uspto_open_data_portal",
            url="https://api.uspto.gov/api/v1/datasets/products/search",
            params={"q": "patent", "limit": 1},
            question="Does the USPTO Open Data Portal API answer without an API key?",
            auth_required=True,
        ),
        Probe(
            probe_id="uspto_odp_bulk_download",
            source_id="uspto_open_data_portal",
            url="https://api.uspto.gov/api/v1/datasets/products/files/PTGRXML",
            question="Are USPTO bulk patent files downloadable keylessly?",
            auth_required=True,
        ),
        Probe(
            probe_id="uspto_bulkdata_host",
            source_id="uspto_bulkdata",
            url="https://bulkdata.uspto.gov/",
            question="Does the legacy bulk-data host still serve files?",
        ),
        Probe(
            probe_id="uspto_legacy_patentsview_api",
            source_id="patentsview",
            url="https://api.patentsview.org/patents/query",
            params={"q": '{"_gte":{"patent_date":"2020-01-01"}}'},
            question=(
                "Is the legacy PatentsView API still alive, or does it now return the "
                "Open Data Portal shell?"
            ),
            expect_marker='"patents"',
        ),
        Probe(
            probe_id="patentsview_search_api",
            source_id="patentsview",
            url="https://search.patentsview.org/api/v1/patent/",
            question="Does the current PatentsView search API answer without a key?",
            auth_required=True,
        ),
        Probe(
            probe_id="patentsview_bulk_s3",
            source_id="patentsview",
            url="https://s3.amazonaws.com/data.patentsview.org/download/g_brf.tsv.zip",
            question="Are PatentsView bulk extracts still on public S3 without auth?",
            auth_required=True,
        ),
        Probe(
            probe_id="uspto_ped_api",
            source_id="uspto_peds",
            url="https://ped.uspto.gov/api/queries",
            question="Does the Patent Examination Data System API still exist?",
        ),
        Probe(
            probe_id="uspto_assignment_api",
            source_id="uspto_assignment",
            url="https://assignment-api.uspto.gov/patent/lookup",
            params={"query": "medtronic", "fields": "patAssigneeName"},
            question="Does the patent assignment API answer keylessly?",
        ),
        # ---------------------------------------------------------------
        # 6. Espacenet / PATENTSCOPE / Lens / Google
        # ---------------------------------------------------------------
        Probe(
            probe_id="espacenet_biblio",
            source_id="espacenet",
            url=(
                "https://worldwide.espacenet.com/data/publicationDetails/biblio"
                "?CC=EP&NR=1000000A1"
            ),
            question="Is Espacenet's publication-details service machine accessible?",
            auth_required=True,
        ),
        Probe(
            probe_id="wipo_patentscope_bulk",
            source_id="wipo_patentscope",
            url="https://patentscope.wipo.int/search/en/bulkDownload.jsf",
            question="Does PATENTSCOPE offer a public bulk-download endpoint?",
            auth_required=True,
        ),
        Probe(
            probe_id="wipo_patentscope_search",
            source_id="wipo_patentscope",
            url="https://patentscope.wipo.int/search/en/search.jsf",
            question="Is the PATENTSCOPE search UI reachable (human interface only)?",
        ),
        Probe(
            probe_id="lens_org_api",
            source_id="lens_org",
            url="https://api.lens.org/patent/search",
            question="Does the Lens API answer without a token?",
            auth_required=True,
        ),
        Probe(
            probe_id="google_patents_page",
            source_id="google_patents",
            url="https://patents.google.com/patent/EP4488863A1/en",
            question="Is a Google Patents record page reachable (read-only, no bulk)?",
            note="Google Patents has no public bulk API outside BigQuery; see report",
        ),
        # ---------------------------------------------------------------
        # 7. National offices that publish genuinely open patent data
        # ---------------------------------------------------------------
        Probe(
            probe_id="dpma_open_data_page",
            source_id="dpma_open_data",
            url="https://www.dpma.de/english/services/open_data/index.html",
            question="Does DPMA (DE) publish open patent data?",
        ),
        Probe(
            probe_id="ukipo_bulk_patents",
            source_id="uk_ipo_patents",
            url="https://www.gov.uk/government/collections/intellectual-property-statistics-and-research",
            question="Does UK IPO publish reusable patent datasets?",
        ),
        Probe(
            probe_id="cipo_open_data",
            source_id="cipo_canada",
            url="https://open.canada.ca/data/en/dataset?q=patent",
            question="Does Canada publish patent datasets on its open-data portal?",
        ),
        Probe(
            probe_id="ip_australia_open_data",
            source_id="ip_australia",
            url="https://data.gov.au/data/dataset?q=patents",
            question="Does IP Australia publish patent datasets on data.gov.au?",
        ),
        Probe(
            probe_id="jpo_bulk_data",
            source_id="jpo_bulk",
            url="https://www.jpo.go.jp/e/system/help/bulkdata/index.html",
            question="Does JPO offer free bulk patent data, and under what conditions?",
        ),
        # ---------------------------------------------------------------
        # 8. Open mirrors / research datasets
        # ---------------------------------------------------------------
        Probe(
            probe_id="zenodo_patent_datasets",
            source_id="zenodo",
            url="https://zenodo.org/api/records",
            params={"q": "patent dataset", "size": 3, "type": "dataset"},
            question="Are there openly licensed patent datasets deposited on Zenodo?",
            expect_marker='"hits"',
        ),
        Probe(
            probe_id="huggingface_patents",
            source_id="huggingface_datasets",
            url="https://huggingface.co/api/datasets",
            params={"search": "patent", "limit": 3},
            question="Are patent datasets published with open licences on the Hub?",
        ),
    ]
