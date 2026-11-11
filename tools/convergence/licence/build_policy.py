#!/usr/bin/env python
"""Build the machine-readable data-licence gate policy.

Reads the HORIZON source registry (`research/horizon/registry/sources/*.json`) and
the export MANIFEST, applies the audited decision table below, and emits
`config/convergence/licence_policy.json`.

The decision table is deliberately explicit and small: every source that differs
from its status-class default is listed in SOURCE_OVERRIDES with the reasoning and
the evidence URL, so a reviewer can see exactly which judgement calls were made and
change one line to flip a source into or out of quarantine.

Usage
    python tools/convergence/licence/build_policy.py \
        --repo . \
        --out config/convergence/licence_policy.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import sys

POLICY_SCHEMA = "medradar.licence_policy.v1"
POLICY_VERSION = "1.0.0"

# The audit date of this policy.  Every source records its own checked_at, which is
# either the date this session re-read the primary source (LIVE_VERIFIED) or the
# date HORIZON's acquisition probes recorded the page (registry evidence).
AUDIT_DATE = "2026-11-11"

# --------------------------------------------------------------------------- #
# Status-class defaults.  The three rights are tracked separately:
#   may_query          - may the pipeline make automated requests to the endpoint
#   may_ingest         - may the pipeline persist what it fetched
#   may_analyse_locally- may derived analysis be performed over ingested material
#   may_redistribute   - may the materialised/derived records be committed to this
#                        public repository
# --------------------------------------------------------------------------- #
CLASS_DEFAULTS = {
    "public_domain": {
        "may_query": True, "may_ingest": True, "may_analyse_locally": True,
        "may_redistribute": True, "redistribution_condition": None,
        "attribution_required": False,
    },
    "open_licence": {
        "may_query": True, "may_ingest": True, "may_analyse_locally": True,
        "may_redistribute": True, "redistribution_condition": "attribution",
        "attribution_required": True,
    },
    # No licence is asserted by the publisher.  Redistribution is NOT established;
    # we publish attributed, caveated records as a conservative compromise and keep
    # the class one edit away from full quarantine.
    "open_no_explicit_licence": {
        "may_query": True, "may_ingest": True, "may_analyse_locally": True,
        "may_redistribute": True,
        "redistribution_condition": "attribution_and_caveat",
        "attribution_required": True,
    },
    "terms_restricted": {
        "may_query": False, "may_ingest": False, "may_analyse_locally": False,
        "may_redistribute": False, "redistribution_condition": None,
        "attribution_required": False,
    },
    "requires_licence": {
        "may_query": False, "may_ingest": False, "may_analyse_locally": False,
        "may_redistribute": False, "redistribution_condition": None,
        "attribution_required": False,
    },
    "unknown": {
        "may_query": False, "may_ingest": False, "may_analyse_locally": False,
        "may_redistribute": False, "redistribution_condition": None,
        "attribution_required": False,
    },
}

CLASS_RATIONALE = {
    "public_domain": "US federal government work or an explicit public-domain/CC0 "
                     "dedication: no reuse restriction is asserted.",
    "open_licence": "A named open licence (OGL, CC-BY, CC0) grants redistribution "
                    "provided attribution is given.",
    "open_no_explicit_licence": "Published openly with no reuse licence asserted. "
                                "Query and local analysis are safe; redistribution "
                                "is unverified. Records may be published only with "
                                "attribution and an explicit rights caveat.",
    "terms_restricted": "Publisher terms prohibit or condition automated retrieval "
                        "and/or redistribution. Requires written permission.",
    "requires_licence": "Access is contractual (subscription/EULA). No open right "
                        "to query, store or redistribute.",
    "unknown": "No licence text could be read, or the host is technically "
               "unreachable. Silence is not permission.",
}

# --------------------------------------------------------------------------- #
# Per-source overrides.  Anything not listed inherits its status-class defaults.
# Keys: status (to correct the registry), rights, attribution_text, notes,
# evidence_url, checked_at, verification.
# --------------------------------------------------------------------------- #
OGL_CA_TEXT = ("Contains information licensed under the Open Government Licence "
               "- Canada.")

SOURCE_OVERRIDES = {
    # ------------------------------------------------------------------ #
    # The one restricted source that is actually materialised.
    # ------------------------------------------------------------------ #
    "un_comtrade": {
        "may_query": True,          # the public API is published for programmatic use
        "may_ingest": True,         # bounded preview sample only
        "may_analyse_locally": True,
        "may_redistribute": False,  # Usage Agreement §5 requires written permission
        "redistribution_condition": "written_permission_required",
        "attribution_required": True,
        "attribution_text": "United Nations Comtrade Database, United Nations "
                            "Statistics Division (used under the public preview "
                            "API; redistribution not permitted).",
        "notes": (
            "Usage Agreement §5 forbids 'any copying, automated browsing or "
            "downloading, redistribution, publication, or commercial exploitation' "
            "without prior written permission from the Director, UNSD. The public "
            "preview API is nevertheless documented for programmatic use ('call it "
            "from your program', no key, <=500 rows), so the two instruments "
            "conflict. Audited position: query + bounded local analysis defensible "
            "under the API invitation; redistribution NOT defensible. Either obtain "
            "written permission or drop the source. Quarantine is enforced by the "
            "export gate."
        ),
        "evidence_url": "https://comtradeplus.un.org/en/license-agreement",
        "evidence_url_secondary": "https://comtradeplus.un.org/en/api-docs",
        "checked_at": AUDIT_DATE,
        "verification": "live_verified",
        "ingest_conditions": "public preview endpoint only; one reference period "
                             "per request; <=1 request/second; no bulk endpoint; no "
                             "keyed /data/v1 path.",
    },
    # ------------------------------------------------------------------ #
    # Open Government Licence - Canada: attribution, and no personal data.
    # ------------------------------------------------------------------ #
    "canada_mdall": {
        "attribution_text": OGL_CA_TEXT,
        "notes": "Open Government Licence - Canada v2.0 grants a worldwide, "
                 "royalty-free, perpetual, non-exclusive licence including "
                 "commercial use, subject to attribution. The licence expressly "
                 "excludes Personal Information; MDALL licence records are "
                 "company/licence data, not personal data.",
        "evidence_url": "https://open.canada.ca/en/open-government-licence-canada",
        "checked_at": AUDIT_DATE,
        "verification": "live_verified",
    },
    "cipo_canada": {
        "attribution_text": OGL_CA_TEXT,
        "notes": "Open Government Licence - Canada v2.0. Patent bibliographic "
                 "records only; the licence's exclusion of Personal Information "
                 "does not bite on the inventor-name fields retained here, which "
                 "are published bibliographic data.",
        "evidence_url": "https://open.canada.ca/en/open-government-licence-canada",
        "checked_at": AUDIT_DATE,
        "verification": "live_verified",
    },
    # ------------------------------------------------------------------ #
    # public_domain sources whose "public domain" basis is US federal
    # authorship rather than a positive licence sentence.
    # ------------------------------------------------------------------ #
    "accessgudid": {
        "notes": "US federal dataset (FDA GUDID via NLM). Public-domain basis is US "
                 "federal authorship; no explicit licence sentence is published on "
                 "the release pages. GMDN term names embedded in GUDID remain "
                 "third-party content: do not extract GMDN term definitions as a "
                 "standalone glossary.",
    },
    "openfda_device_510k": {
        "notes": "openFDA licence page dedicates content to the public domain under "
                 "CC0 1.0 unless otherwise noted. GMDN(R) is carved out as "
                 "third-party content; openFDA device endpoints do not carry GMDN "
                 "fields, so the carve-out does not bite on these records.",
        "evidence_url": "https://open.fda.gov/license/",
    },
    "openfda_device_classification": {
        "notes": "As openfda_device_510k; CC0 1.0 dedication with the GMDN carve-out "
                 "not applying to these fields.",
        "evidence_url": "https://open.fda.gov/license/",
    },
    "openfda_device_pma": {
        "notes": "As openfda_device_510k; CC0 1.0 dedication with the GMDN carve-out "
                 "not applying to these fields.",
        "evidence_url": "https://open.fda.gov/license/",
    },
    "openfda_device_registrationlisting": {
        "notes": "As openfda_device_510k; CC0 1.0 dedication with the GMDN carve-out "
                 "not applying to these fields.",
        "evidence_url": "https://open.fda.gov/license/",
    },
    "openfda_bulk_download": {
        "notes": "Catalogue-only, never materialised. Same CC0 1.0 terms as the "
                 "device endpoints.",
        "evidence_url": "https://open.fda.gov/license/",
    },
    "clinicaltrials_gov": {
        "notes": "ClinicalTrials.gov terms state the data is available for public "
                 "use and is not subject to copyright restrictions in the United "
                 "States. Sponsor/collaborator organisations are named; no patient "
                 "data is present.",
        "evidence_url": "https://clinicaltrials.gov/about-site/terms-conditions",
    },
    "nih_reporter": {
        "notes": "US federal government data; RePORTER FAQ answers 'Is the data "
                 "copyrighted?' with no.",
        "evidence_url": "https://reporter.nih.gov/faq",
    },
    # ------------------------------------------------------------------ #
    # open_no_explicit_licence: the 8 materialised sources.  Rights are
    # unverified; redistribution is permitted here only under
    # attribution_and_caveat, and flipping may_redistribute to false
    # quarantines the source with no other change.
    # ------------------------------------------------------------------ #
    "eurostat_comext": {
        "notes": "Eurostat copyright notice: reuse for commercial or non-commercial "
                 "purposes is authorised provided the source is acknowledged "
                 "(Commission Decision 2011/833/EU). Attribution: 'Source: Eurostat'.",
        "attribution_text": "Source: Eurostat (Comext), European Commission.",
        "evidence_url": "https://ec.europa.eu/eurostat/help/copyright-notice",
        "verification": "archived_page_in_repo",
    },
    "uk_hmrc_trade": {
        "notes": "uktradeinfo.com footer: content available under the Open "
                 "Government Licence v3.0 except where otherwise stated.",
        "attribution_text": "Contains public sector information licensed under the "
                            "Open Government Licence v3.0 (UK Trade Info, HMRC).",
        "evidence_url": "https://www.uktradeinfo.com/",
        "verification": "archived_page_in_repo",
    },
    "uk_find_a_tender": {
        "notes": "OCDS release packages declare their own licence field: "
                 "OGL v3.0. NOTE: the vendored raw packages additionally contain "
                 "named individual contact emails of public-sector staff (see the "
                 "PII finding in the review). The derived export records do not.",
        "attribution_text": "Contains public sector information licensed under the "
                            "Open Government Licence v3.0 (Find a Tender Service).",
        "evidence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    },
    "eu_ted": {
        "notes": "TED API documentation addresses 'reusers of TED Data' and permits "
                 "retrieval 'for analysis or reuse', but no formal reuse licence "
                 "sentence was located. Treated as open_no_explicit_licence.",
        "attribution_text": "Source: TED (Tenders Electronic Daily), European Union.",
        "evidence_url": "https://docs.ted.europa.eu/api/latest/index.html",
        "verification": "archived_page_in_repo",
    },
    "eu_cordis": {
        "notes": "Commission legal notice permits reuse of Commission documents with "
                 "attribution, but the /api/search/results endpoint is undocumented "
                 "and carries no machine-interface licence.",
        "attribution_text": "Source: EU CORDIS, European Commission.",
        "evidence_url": "https://commission.europa.eu/legal-notice_en",
    },
    "crossref": {
        "notes": "Crossref makes metadata openly available for reuse and asks only "
                 "for a polite contact; no blanket content licence is attached. "
                 "Per-record license[] is preserved because that is where the rights "
                 "actually are.",
        "attribution_text": "Metadata from Crossref; per-record licence terms are "
                            "preserved in the records.",
        "evidence_url": "https://www.crossref.org/operations-and-sustainability/accessibility/",
    },
    "openalex": {
        "status_correction": "open_licence",
        "notes": "OpenAlex releases its data under CC0 1.0.",
        "attribution_text": "Data from OpenAlex (CC0 1.0).",
        "evidence_url": "https://openalex.org/licenses",
    },
    "openaire": {
        "status_correction": "open_licence",
        "notes": "OpenAIRE Graph is published as open data under CC-BY 4.0; "
                 "per-record bestAccessRight and licence are preserved.",
        "attribution_text": "Metadata from OpenAIRE Graph (CC-BY 4.0).",
        "evidence_url": "https://graph.openaire.eu/docs/",
    },
    "europepmc": {
        "status_correction": "open_licence",
        "notes": "Europe PMC content available for reuse with attribution; per-record "
                 "licence preserved because article rights differ from metadata "
                 "rights.",
        "attribution_text": "Metadata from Europe PMC (EMBL-EBI); per-record licence "
                            "preserved.",
        "evidence_url": "https://europepmc.org/help",
    },
    "pubmed_eutils": {
        "notes": "NLM makes PubMed citation data available for public use; no blanket "
                 "content licence is attached and abstract copyright stays with the "
                 "publisher. Redistribute citation metadata, not abstracts.",
        "attribution_text": "Citation metadata from PubMed (NLM).",
        "evidence_url": "https://www.ncbi.nlm.nih.gov/books/NBK25497/",
    },
    "semantic_scholar": {
        "notes": "Graph API is free for research use; API terms restrict bulk "
                 "redistribution and require attribution. Record-level licence "
                 "fields are preserved.",
        "attribution_text": "Data from Semantic Scholar (Allen Institute for AI).",
        "evidence_url": "https://www.semanticscholar.org/product/api/license",
    },
    "epo_publication_server": {
        "notes": "Official public patent publications under EPO terms of use; no "
                 "explicit reuse licence is stated. Only derived bibliographic "
                 "records plus bounded hashed samples are retained, not a mirror.",
        "attribution_text": "Patent data from the European Patent Office.",
        "evidence_url": "https://www.epo.org/en/legal",
    },
    "brazil_anvisa": {
        "notes": "ANVISA 'dados abertos' portal: no login, no key, and no licence "
                 "statement on the directory index. Recorded as open with no "
                 "explicit licence rather than inventing a CC-BY grant.",
        "attribution_text": "Source: ANVISA (Brazil) open data.",
        "evidence_url": "https://www.gov.br/anvisa/pt-br/acessoainformacao/dadosabertos",
    },
    "usaspending": {
        "notes": "No reuse-licence sentence found on the pages fetched (the /about "
                 "page is a JS shell). The underlying records are the awarding "
                 "agencies' own public contract data. Keep the caveat.",
        "attribution_text": "Source: USAspending.gov (US federal award data).",
        "evidence_url": "https://www.usaspending.gov/about",
        "verification": "archived_page_in_repo",
    },
    "sam_gov": {
        "notes": "Registry-only. GSA documents the account+API-key requirement but "
                 "publishes no reuse licence. Not materialised, so no payload to "
                 "redistribute.",
        "evidence_url": "https://open.gsa.gov/api/sam-entity-extracts-api/",
    },
    "us_census_trade": {
        "notes": "Registry-only. No explicit reuse-licence sentence located; key "
                 "required. Not materialised.",
        "evidence_url": "https://www.census.gov/foreign-trade/index.html",
    },
    # ------------------------------------------------------------------ #
    # terms_restricted / requires_licence, all registry-only.  No payload,
    # and no right to fetch one without permission.
    # ------------------------------------------------------------------ #
    "importgenius": {
        "status_correction": "terms_restricted",
        "notes": "Terms of use forbid sale, transfer, sublicence, reproduction, "
                 "derivative works and distribution of any Content, and state 'No "
                 "other use is permitted without our prior written consent.'",
        "evidence_url": "https://www.importgenius.com/utilities/legal/terms-of-use",
        "verification": "archived_page_in_repo",
    },
    "importyeti": {
        "notes": "robots.txt disallows exactly the endpoints that serve the shipment "
                 "data; no published reuse licence. Access was not attempted.",
        "evidence_url": "https://www.importyeti.com/policies",
        "verification": "archived_page_in_repo",
    },
    "descartes_datamyne": {
        "notes": "Contractual only: SaaS subscription terms + EULA. No open data or "
                 "open API licence.",
        "evidence_url": "https://www.descartes.com/legal-compliance",
        "verification": "archived_page_in_repo",
    },
    "panjiva": {
        "notes": "Commercial subscription platform/feed. The terms page returned HTTP "
                 "403 to an automated client, so the exact clause is NOT quoted: the "
                 "status is inferred from product structure and is explicitly "
                 "unverified rather than permissive.",
        "evidence_url": "https://www.spglobal.com/en/terms-of-use",
        "verification": "archived_page_in_repo",
    },
    "epo_ops": {
        "notes": "Free but contract-gated: registered OPS account + OAuth consumer "
                 "key. No payload without accepting the OPS fair-use terms.",
        "evidence_url": "https://www.epo.org/en/legal",
    },
    "espacenet": {
        "notes": "WAF challenge on direct requests; treated as an anti-automation "
                 "control and not circumvented.",
        "evidence_url": "https://www.epo.org/en/legal",
    },
    "google_patents": {
        "notes": "Bulk access requires a billing account; scraping for bulk use is "
                 "contrary to the terms and was not attempted.",
        "evidence_url": "https://policies.google.com/terms",
    },
    "wipo_patentscope": {
        "notes": "No anonymous machine interface; stateful JSF session. Scraping not "
                 "attempted.",
        "evidence_url": "https://www.wipo.int/terms-of-use/",
    },
    "eudamed": {
        "notes": "Public API paths return HTTP 429 with an explicit anti-scraping "
                 "instruction pointing machine users at the official data API, which "
                 "requires EU Login + subscription key.",
        "evidence_url": "https://developer.datalake.sante.service.ec.europa.eu/api-details",
    },
    "lens_org": {
        "notes": "API returns 401 anonymous; access is by registration and licence.",
        "verification": "probe_only",
    },
    "usitc_dataweb": {
        "notes": "Registry-only, and no licence text was recoverable: SPA shell only. "
                 "Unknown is recorded rather than guessed.",
        "verification": "archived_page_in_repo",
    },
    "australia_tga_artg": {
        "notes": "Unreachable host; TGA normally publishes under CC-BY 3.0 AU but that "
                 "could not be read from the source, so unknown.",
    },
    "china_nmpa_udi": {
        "notes": "Only manual/HTML access; no licence statement readable. Unknown.",
    },
    "japan_pmda": {
        "notes": "No machine-readable endpoint; no licence statement read. Unknown.",
    },
    "dpma_open_data": {
        "notes": "Open-data landing URL 404s; no confirmed interface. Unknown.",
    },
    "epo_global_patent_index": {
        "notes": "robots.txt advertises a sitemap that 404s. Unknown.",
    },
    "epo_linked_open_data": {
        "notes": "API root returns 500 and robots.txt disallows the data paths. "
                 "Unknown.",
    },
    "eu_ctis": {
        "notes": "403 before any content; the site serves an SPA shell instead of a "
                 "contract. Unknown (and a 2-byte '{}' 200 response is a trap for a "
                 "naive connector).",
    },
    "jpo_bulk": {"notes": "403 on every page reached; likely geo/UA filtering. Unknown."},
    "patentsview": {
        "notes": "Legacy host serves a SPA shell; DNS failure on the new host; bulk S3 "
                 "403. Unknown.",
    },
    "uspto_bulkdata": {
        "status_correction": "public_domain",
        "notes": "US Government work; host no longer resolves. Not materialised.",
    },
    "uspto_open_data_portal": {
        "notes": "US Government work; USPTO terms warn that the online databases are "
                 "not intended as a bulk-download source. Not materialised.",
        "evidence_url": "https://www.uspto.gov/terms-use-uspto-websites",
    },
    "ip_australia": {
        "notes": "Datasets carry CC BY 2.5/3.0 AU or 'Other (Open)'; check per dataset "
                 "before reuse. Not materialised.",
        "evidence_url": "https://data.gov.au/data/dataset?q=patents",
    },
    "uk_mhra_device": {
        "notes": "GOV.UK content is OGL v3.0, but no public per-device UK registration "
                 "register exists as open data, so nothing to ingest.",
        "evidence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    },
}

# Paths that must never reappear in the repository (the 30 excluded from the
# selective import).  Kept explicit so the gate can assert their absence directly
# even when a MANIFEST no longer declares them.
QUARANTINE_PATHS = [
    "research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl",
    "research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl.sha256",
    "research/horizon/experiments/industry/evidence/un_comtrade.jsonl",
    "research/horizon/DATASETS/industry/un_comtrade/summary.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2015.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2016.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2017.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2018.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2019.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2020.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2021.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2022.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2023.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/annual_2024.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/api_root.html",
    "research/horizon/DATASETS/industry/un_comtrade/raw/comtradeplus_home.html",
    "research/horizon/DATASETS/industry/un_comtrade/raw/hs.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/reporters.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202501.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202502.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202503.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202504.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202505.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202506.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202507.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202508.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202509.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202510.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202511.json",
    "research/horizon/DATASETS/industry/un_comtrade/raw/monthly_202512.json",
]

# Files that are allowed to remain because they are licence *evidence* (no trade
# values) rather than payload.
LICENCE_EVIDENCE_ALLOWLIST = [
    "research/horizon/DATASETS/industry/un_comtrade/raw/comtrade_license.html",
    "research/horizon/DATASETS/industry/un_comtrade/raw/terms_of_use.html",
    "research/horizon/DATASETS/industry/un_comtrade/PROVENANCE.json",
    "research/horizon/registry/sources/un_comtrade.json",
]

# Retained files that still carry *derived* UN Comtrade figures.  These are not
# payload files, so the file-presence gate cannot see them; they are listed here so
# the owner has an explicit decision to make.
DERIVED_VALUE_REFERENCES = [
    {
        "path": "research/horizon/reports/INDUSTRY_DATA_REPORT.md",
        "source_id": "un_comtrade",
        "lines": [82, 83, 84, 85, 86, 87, 88, 127],
        "what": "HS-9018 China imports 2015/2019/2021/2023/2024 in USD bn (5 cells) "
                "and the exact Germany-2023 cell US$13,359,445,208.52.",
        "severity": "medium",
    },
    {
        "path": "research/horizon/experiments/industry/EXP_H4_INDUSTRY.json",
        "source_id": "un_comtrade",
        "json_pointers": ["/cross_checks/de_9018_imports_2023/comtrade_usd"],
        "what": "The same Germany-2023 cell (13359445208.517) as a machine-readable "
                "figure.",
        "severity": "medium",
    },
]


def load_registry(repo: str) -> dict:
    pattern = os.path.join(repo, "research", "horizon", "registry", "sources", "*.json")
    out = {}
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        out[data["source_id"]] = data
    if not out:
        raise SystemExit(f"no registry sources found under {pattern}")
    return out


def load_manifest(repo: str) -> dict:
    path = os.path.join(repo, "research", "horizon", "exports",
                        "horizon-2026-11-10", "MANIFEST.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="repository root")
    ap.add_argument("--out", default=os.path.join("config", "convergence",
                                                  "licence_policy.json"))
    args = ap.parse_args(argv)

    registry = load_registry(args.repo)
    manifest = load_manifest(args.repo)
    declared = {f["source_id"]: f for f in manifest["files"]}
    licence_summary = manifest.get("licence_summary", {})

    sources = {}
    for sid in sorted(registry):
        reg = registry[sid]
        override = dict(SOURCE_OVERRIDES.get(sid, {}))
        status = override.pop("status_correction", None) or reg.get("licence_status")
        if status not in CLASS_DEFAULTS:
            raise SystemExit(f"{sid}: unknown licence_status {status!r}")
        entry = dict(CLASS_DEFAULTS[status])
        entry.update({
            "source_id": sid,
            "name": reg.get("name"),
            "operator": reg.get("operator"),
            "licence_status": status,
            "licence_status_as_claimed_by_horizon": reg.get("licence_status"),
            "status_rationale": CLASS_RATIONALE[status],
            "materialised": sid in declared,
            "auth_required": reg.get("auth_required"),
            "access_state": reg.get("access_state"),
            "evidence_url": reg.get("licence_url") or override.get("evidence_url"),
            "checked_at": override.pop("checked_at", AUDIT_DATE),
            "verification": override.pop("verification", "registry_recorded_not_reverified"),
            "notes": "",
            "attribution_text": None,
        })
        # Registry notes are the baseline; overrides replace them where they are
        # more precise.
        base_note = (reg.get("licence_note") or "").strip()
        entry["notes"] = base_note if base_note else CLASS_RATIONALE[status]

        evidence_url = override.pop("evidence_url", None)
        if evidence_url:
            entry["evidence_url"] = evidence_url
        for key in ("may_query", "may_ingest", "may_analyse_locally",
                    "may_redistribute", "redistribution_condition",
                    "attribution_required", "attribution_text", "notes",
                    "ingest_conditions", "evidence_url_secondary"):
            if key in override:
                entry[key] = override.pop(key)
        if override:
            raise SystemExit(f"{sid}: unhandled override keys {sorted(override)}")

        entry["may_redistribute_export_records"] = bool(entry["may_redistribute"])
        sources[sid] = entry

    # Sanity: every declared export source must be covered by the policy.
    missing = sorted(set(declared) - set(sources))
    if missing:
        raise SystemExit(f"declared sources missing from policy: {missing}")

    counts = {}
    for e in sources.values():
        counts[e["licence_status"]] = counts.get(e["licence_status"], 0) + 1
    redis = {"allowed": 0, "unknown_conditioned": 0, "forbidden": 0}
    for e in sources.values():
        if not e["may_redistribute"]:
            redis["forbidden"] += 1
        elif e["redistribution_condition"] in (None, "attribution"):
            redis["allowed"] += 1
        else:
            redis["unknown_conditioned"] += 1

    policy = {
        "schema": POLICY_SCHEMA,
        "policy_version": POLICY_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audit_date": AUDIT_DATE,
        "description": (
            "Authoritative data-licence gate for the MedRadar public repository. "
            "Consumed by the integration pipeline and CI. A source with "
            "may_redistribute=false must NOT have its payload committed: the export "
            "gate (tools/convergence/licence/licence_gate.py) enforces this."
        ),
        "rights_model": {
            "may_query": "Automated requests to the published endpoint are permitted.",
            "may_ingest": "Fetched material may be persisted locally.",
            "may_analyse_locally": "Derived analysis over ingested material is permitted.",
            "may_redistribute": "Materialised/derived records may be committed to this "
                                "public repository.",
            "redistribution_condition": "null | 'attribution' | "
                                        "'attribution_and_caveat' | "
                                        "'written_permission_required'",
        },
        "status_definitions": CLASS_RATIONALE,
        "counts": {
            "sources_total": len(sources),
            "by_licence_status": dict(sorted(counts.items())),
            "redistribution": redis,
            "materialised": sum(1 for e in sources.values() if e["materialised"]),
        },
        "quarantine": {
            "source_ids": sorted(s for s, e in sources.items()
                                 if not e["may_redistribute"]),
            "paths": QUARANTINE_PATHS,
            "licence_evidence_allowlist": LICENCE_EVIDENCE_ALLOWLIST,
            "derived_value_references": DERIVED_VALUE_REFERENCES,
        },
        "gate_contract": {
            "manifest": "research/horizon/exports/<export_id>/MANIFEST.json",
            "declared_files": "files[].path is relative to the export directory",
            "allow": "declared file whose source has may_redistribute=true and is present",
            "quarantine": "declared file whose source has may_redistribute=false and is absent",
            "violation": "declared file whose source has may_redistribute=false but is present",
            "missing_expected": "declared file whose source has may_redistribute=true but is absent",
            "unknown_source": "declared file whose source_id is not in this policy",
        },
        "sources": sources,
    }

    out_path = os.path.join(args.repo, args.out) if not os.path.isabs(args.out) else args.out
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(policy, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {out_path}")
    print(f"  sources: {len(sources)}  materialised: {policy['counts']['materialised']}")
    print(f"  by status: {policy['counts']['by_licence_status']}")
    print(f"  redistribution: {redis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
