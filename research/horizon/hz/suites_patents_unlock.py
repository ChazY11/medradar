"""Patent-channel unlock-route probes.

``suites_patents`` establishes which channels answer. This suite establishes, for
each channel that does *not* answer anonymously, the official route by which a
project owner could lawfully obtain access — plus the documentation pages that
state each channel's terms. Recording the correct unlock route is the concrete
deliverable when a source is blocked.
"""

from __future__ import annotations

from .probe import Probe


def probes() -> list[Probe]:
    return [
        # ---- EPO documentation / registration -------------------------
        Probe(
            probe_id="epo_bulk_data_sets_page",
            source_id="epo_publication_server",
            url="https://www.epo.org/en/searching-for-patents/data/bulk-data-sets",
            question="Which bulk data products does the EPO publish, and under what conditions?",
        ),
        Probe(
            probe_id="epo_web_services_page",
            source_id="epo_ops",
            url="https://www.epo.org/en/searching-for-patents/data/web-services",
            question="What is the documented route to EPO web services (OPS)?",
        ),
        Probe(
            probe_id="epo_ops_registration",
            source_id="epo_ops",
            url="https://developers.epo.org/",
            question="Is there a self-service developer/registration portal for OPS?",
            auth_required=True,
        ),
        Probe(
            probe_id="epo_terms_of_use",
            source_id="epo_publication_server",
            url="https://www.epo.org/en/legal/terms-of-use",
            question="What do the EPO terms of use permit for automated retrieval?",
        ),
        # ---- USPTO official access routes -----------------------------
        Probe(
            probe_id="uspto_odp_getting_started",
            source_id="uspto_open_data_portal",
            url="https://data.uspto.gov/apis/getting-started",
            question="What is the documented route to a USPTO ODP API key?",
            auth_required=True,
        ),
        Probe(
            probe_id="uspto_odp_bulk_search_download",
            source_id="uspto_open_data_portal",
            url="https://data.uspto.gov/bulkdata",
            question="Is there still a bulk-search-and-download route, and does it need a key?",
            auth_required=True,
        ),
        Probe(
            probe_id="uspto_terms_website_policies",
            source_id="uspto_open_data_portal",
            url="https://www.uspto.gov/terms-use-uspto-websites",
            question="What do USPTO website terms say about automated access?",
        ),
        # ---- PatentsView current home ---------------------------------
        Probe(
            probe_id="patentsview_home",
            source_id="patentsview",
            url="https://patentsview.org/",
            question="Is PatentsView still operating, and what is its access model now?",
            auth_required=True,
        ),
        Probe(
            probe_id="patentsview_downloads",
            source_id="patentsview",
            url="https://patentsview.org/download/data-download-tables",
            question="Are PatentsView bulk tables still publicly downloadable?",
        ),
        # ---- National offices: correct current URLs -------------------
        Probe(
            probe_id="dpma_open_data_de",
            source_id="dpma_open_data",
            url="https://www.dpma.de/dpma/veroeffentlichungen/opendata/index.html",
            question="Does DPMA publish open patent data, and under what licence?",
        ),
        Probe(
            probe_id="dpma_register_search",
            source_id="dpma_open_data",
            url="https://register.dpma.de/DPMAregister/pat/experte",
            question="Is the DPMA register machine accessible or human-only?",
        ),
        Probe(
            probe_id="cipo_ckan_search",
            source_id="cipo_canada",
            url="https://open.canada.ca/data/api/3/action/package_search",
            params={"q": "patent", "rows": 3},
            question="Does Canada's open-data CKAN API expose patent datasets?",
            expect_marker='"success"',
        ),
        Probe(
            probe_id="ip_australia_ckan_search",
            source_id="ip_australia",
            url="https://data.gov.au/data/api/3/action/package_search",
            params={"q": "patent", "rows": 3},
            question="Does data.gov.au expose IP Australia patent datasets via CKAN?",
            expect_marker='"success"',
        ),
        Probe(
            probe_id="ukipo_data_page",
            source_id="uk_ipo_patents",
            url="https://www.gov.uk/government/organisations/intellectual-property-office/about/statistics",
            question="Where does UK IPO publish its data?",
        ),
        Probe(
            probe_id="wipo_ipstats",
            source_id="wipo_ip_stats",
            url="https://www3.wipo.int/ipstats/",
            question="Does WIPO publish aggregate IP statistics machine-readably?",
        ),
        Probe(
            probe_id="jpo_standard_data",
            source_id="jpo_bulk",
            url="https://www.jpo.go.jp/e/system/laws/rule/guideline/patent/document/index.html",
            question="Is there a documented JPO data route (vs a 403 wall)?",
        ),
        # ---- Open mirrors as a fallback corpus ------------------------
        Probe(
            probe_id="zenodo_patent_records",
            source_id="zenodo",
            url="https://zenodo.org/api/records",
            params={"q": "patents", "size": 3, "sort": "mostrecent"},
            question="Any openly licensed patent-adjacent research datasets?",
            expect_marker='"hits"',
        ),
        Probe(
            probe_id="huggingface_patents_search",
            source_id="huggingface_datasets",
            url="https://huggingface.co/api/datasets",
            params={"search": "patent", "limit": 5, "full": "false"},
            question="Which patent datasets exist on the Hub and under what licence?",
        ),
    ]
