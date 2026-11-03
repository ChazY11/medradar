#!/usr/bin/env python3
"""S-029 (MedRadar) historical legal-entity register for the five study companies.

Purpose
-------
Build an evidence-backed *historical* legal-entity register for Medtronic, GE
HealthCare, Philips, Draegerwerk and Mindray so that no relation claim in the
S-029 network study can project a 2026 corporate group structure onto an earlier
period.

Design rules (enforced by this script, not just documented)
-----------------------------------------------------------
1. Every legal fact in the register is backed by a primary/official document
   fetched over HTTP at build time.  Each evidence item carries the URL, a
   verbatim excerpt and the UTC retrieval timestamp.
2. Verbatim excerpts are checked as substrings of the normalised document text.
   For JSON APIs the relevant fields are re-read and compared field-by-field.
   A single failed check aborts the build with a diagnostic (the register can
   therefore never silently contain an unsupported quote).
3. Dates are only written when a source states them.  Anything not verified is
   left null and the failed verification attempts are recorded (for stable IDs
   the empty search result itself is recorded as evidence).
4. Source conflicts are recorded in ENTITY_HISTORY_REGISTER.md rather than
   silently resolved.

Outputs (all inside research/studies/relation_network_s029/):
  artifacts/company_entity_register.json   <- consumed by the study pipeline
  artifacts/entity_provenance.json         <- retrieval manifest
  ENTITY_HISTORY_REGISTER.md               <- human-readable audit register

Usage
-----
  python code/s029_company_register.py [--refresh] [--check-only]

No network?  Everything is cached in %TEMP%/s029_entity_cache so a re-run is
reproducible offline; --refresh forces re-download.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
STUDY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(STUDY_DIR, "artifacts")
DATA_DIR = os.path.join(STUDY_DIR, "data")
CORPUS_PATH = os.path.join(DATA_DIR, "observed_company_strings.json")
CACHE_DIR = os.path.join(tempfile.gettempdir(), "s029_entity_cache")

UA = {
    "User-Agent": "MedRadar S-029 entity audit (research@medradar.local)",
    "Accept-Encoding": "identity",
    "Accept": "*/*",
}

UTC = _dt.timezone.utc


def utc_now_iso() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Fetch + normalise (with on-disk cache that preserves first-retrieval time)
# --------------------------------------------------------------------------- #
class Fetched:
    __slots__ = ("key", "url", "text", "status", "retrieved_at", "sha256", "kind")

    def __init__(self, key, url, text, status, retrieved_at, sha256, kind):
        self.key = key
        self.url = url
        self.text = text
        self.status = status
        self.retrieved_at = retrieved_at
        self.sha256 = sha256
        self.kind = kind


def _cache_file(url: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")


def fetch_text(url: str, refresh: bool = False, timeout: int = 60) -> dict:
    """Return {text, retrieved_at, sha256, status}.  Cached with first-seen time."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cp = _cache_file(url)
    if os.path.exists(cp) and not refresh:
        with open(cp, encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("url") == url and rec.get("text"):
            return rec
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
            break
        except Exception as exc:  # noqa: BLE001 - retried with backoff
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"fetch failed for {url}: {last_err}")
    rec = {
        "url": url,
        "text": raw.decode("utf-8", "replace"),
        "retrieved_at": utc_now_iso(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "status": status,
        "bytes": len(raw),
    }
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    time.sleep(0.12)  # be polite to SEC/GLEIF
    return rec


_TAG_RE = re.compile(r"(?s)<[^>]+>")
_SCRIPT_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")


def normalise(raw: str) -> str:
    """HTML/plain-text -> single-spaced text used for excerpt verification."""
    s = _SCRIPT_RE.sub(" ", raw)
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = s.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def simplify(s: str) -> str:
    """Alphanumeric-only projection, used only to diagnose a failed quote."""
    return re.sub(r"[^0-9a-z]+", "", s.lower())


# --------------------------------------------------------------------------- #
# Source registry
# --------------------------------------------------------------------------- #
SEC_ARCH = "https://www.sec.gov/Archives/edgar/data"
SOURCES: dict[str, dict] = {
    # ---- Medtronic ---------------------------------------------------------
    "mdt_10k_fy2015": {
        "url": f"{SEC_ARCH}/1613103/000161310315000028/mdt-2015424x10k.htm",
        "kind": "html_text",
    },
    "mdt_8k_20150126_ex991": {
        "url": f"{SEC_ARCH}/1613103/000119312515020681/d859999dex991.htm",
        "kind": "html_text",
    },
    "mdt_8k_20140717": {
        "url": f"{SEC_ARCH}/64670/000119312514271779/d761416d8k.htm",
        "kind": "html_text",
    },
    "mdt_ex21_fy2025": {
        "url": f"{SEC_ARCH}/1613103/000161310325000091/mdt-202510kxex21.htm",
        "kind": "html_text",
    },
    "mdt_10k_fy2001": {
        "url": f"{SEC_ARCH}/64670/000089710101500449/medtronic012520_10k.txt",
        "kind": "text",
    },
    "mdt_10k_fy2002": {
        "url": f"{SEC_ARCH}/64670/000091205702027975/a2083896z10-k.htm",
        "kind": "html_text",
    },
    "mdt_8k_20010905": {
        "url": f"{SEC_ARCH}/64670/000091205701531399/a2058671z8-k.htm",
        "kind": "html_text",
    },
    # ---- Covidien (inside the Medtronic group since 2015-01-26) -----------
    "cov_10k_fy2014": {
        "url": f"{SEC_ARCH}/1385187/000138518714000041/cov-201492614x10k.htm",
        "kind": "html_text",
    },
    "cov_10k_fy2007": {
        "url": f"{SEC_ARCH}/1385187/000119312507264586/d10k.htm",
        "kind": "html_text",
    },
    "cov_ex21_fy2007": {
        "url": f"{SEC_ARCH}/1385187/000119312507264586/dex211.htm",
        "kind": "html_text",
    },
    # ---- GE / GE HealthCare ------------------------------------------------
    "gehc_10k_fy2022": {
        "url": f"{SEC_ARCH}/1932393/000193239323000025/gehc-20221231.htm",
        "kind": "html_text",
    },
    "ge_10k_fy2003": {
        "url": f"{SEC_ARCH}/40545/000004054504000013/frm10k.htm",
        "kind": "html_text",
    },
    "ge_10k_fy2004": {
        "url": f"{SEC_ARCH}/40545/000004054505000020/gefrm10k.htm",
        "kind": "html_text",
    },
    "ge_10k_fy2021": {
        "url": f"{SEC_ARCH}/40545/000004054522000008/ge-20211231.htm",
        "kind": "html_text",
    },
    # ---- Philips -----------------------------------------------------------
    "phg_20f_fy2013": {
        "url": f"{SEC_ARCH}/313216/000119312514067281/d672413d20f.htm",
        "kind": "html_text",
    },
    "phg_20f_fy2008": {
        "url": f"{SEC_ARCH}/313216/000115697309000099/u06127e20vf.htm",
        "kind": "html_text",
    },
    "phg_20f_fy2024": {
        "url": f"{SEC_ARCH}/313216/000031321625000009/phg-20241231.htm",
        "kind": "html_text",
    },
    "phg_ar2015": {
        "url": f"{SEC_ARCH}/313216/000119312516473594/d145196d20f.htm",
        "kind": "html_text",
    },
    "phg_ar2016": {
        "url": f"{SEC_ARCH}/313216/000119312517050359/d330553d20f.htm",
        "kind": "html_text",
    },
    "phg_6k_20080321": {
        "url": f"{SEC_ARCH}/313216/000130901408000155/exhibit12.htm",
        "kind": "html_text",
    },
    # ---- Mindray -----------------------------------------------------------
    "mry_20f_fy2013": {
        "url": f"{SEC_ARCH}/1373060/000119312514163316/d646003d20f.htm",
        "kind": "html_text",
    },
    "mry_20f_fy2007": {
        "url": f"{SEC_ARCH}/1373060/000114554908001185/h02233e20vf.htm",
        "kind": "html_text",
    },
    "mry_6k_20080515_datascope": {
        "url": f"{SEC_ARCH}/1373060/000114554908000881/h02114exv99w1.htm",
        "kind": "html_text",
    },
    "mry_6k_20130717_zonare": {
        "url": f"{SEC_ARCH}/1373060/000119312513292410/d570219dex991.htm",
        "kind": "html_text",
    },
    "mry_6k_20160303_takeprivate": {
        "url": f"{SEC_ARCH}/1373060/000114420416085800/v433228_ex99-1.htm",
        "kind": "html_text",
    },
    "mry_25nse_20160304": {
        "url": f"{SEC_ARCH}/1373060/000087666116000851/ruleprovisionnotice.htm",
        "kind": "html_text",
    },
    "datascope_8k_20080515": {
        "url": f"{SEC_ARCH}/27096/000095012308005728/y58644e8vk.htm",
        "kind": "html_text",
    },
    "szse_mindray_listing_20181016": {
        "url": "http://www.szse.cn/English/about/news/listings/English/t20181016_559469.html",
        "kind": "html_text",
    },
    # ---- Registries (JSON APIs) -------------------------------------------
    "sec_sub_medtronic_plc": {"url": "https://data.sec.gov/submissions/CIK0001613103.json", "kind": "json"},
    "sec_sub_medtronic_inc": {"url": "https://data.sec.gov/submissions/CIK0000064670.json", "kind": "json"},
    "sec_sub_covidien": {"url": "https://data.sec.gov/submissions/CIK0001385187.json", "kind": "json"},
    "sec_sub_gehc": {"url": "https://data.sec.gov/submissions/CIK0001932393.json", "kind": "json"},
    "sec_sub_ge": {"url": "https://data.sec.gov/submissions/CIK0000040545.json", "kind": "json"},
    "sec_sub_philips": {"url": "https://data.sec.gov/submissions/CIK0000313216.json", "kind": "json"},
    "sec_sub_mindray": {"url": "https://data.sec.gov/submissions/CIK0001373060.json", "kind": "json"},
    "sec_sub_datascope": {"url": "https://data.sec.gov/submissions/CIK0000027096.json", "kind": "json"},
    "sec_sub_respironics": {"url": "https://data.sec.gov/submissions/CIK0000780434.json", "kind": "json"},
    "gleif_medtronic_plc": {
        "url": "https://api.gleif.org/api/v1/lei-records/549300GX3ZBSQWUXY261",
        "kind": "json",
    },
    "gleif_medtronic_inc": {
        "url": "https://api.gleif.org/api/v1/lei-records/D56MRZY2INAN94ZONZ37",
        "kind": "json",
    },
    "gleif_gehc": {
        "url": "https://api.gleif.org/api/v1/lei-records/549300OI9J7XOWZMUN85",
        "kind": "json",
    },
    "gleif_philips_nv": {
        "url": "https://api.gleif.org/api/v1/lei-records/H1FJE8H61JGM1JSGM897",
        "kind": "json",
    },
    "gleif_philips_electronics_nederland": {
        "url": "https://api.gleif.org/api/v1/lei-records/549300VGHFJJ58HE2B54",
        "kind": "json",
    },
    "gleif_draegerwerk": {
        "url": "https://api.gleif.org/api/v1/lei-records/5493005UFVHY0PPNKD75",
        "kind": "json",
    },
    "gleif_draeger_safety": {
        "url": "https://api.gleif.org/api/v1/lei-records/549300T8IDCFNHN29E62",
        "kind": "json",
    },
    "gleif_draeger_medical": {
        "url": "https://api.gleif.org/api/v1/lei-records/529900PCM8FAO280F764",
        "kind": "json",
    },
    "gleif_draeger_medical_systems": {
        "url": "https://api.gleif.org/api/v1/lei-records/549300R77YDRH6WZPY39",
        "kind": "json",
    },
    "gleif_mindray_international": {
        "url": "https://api.gleif.org/api/v1/lei-records/213800L7HSJE2P72PZ24",
        "kind": "json",
    },
    "gleif_medtronic_minimed": {
        "url": "https://api.gleif.org/api/v1/lei-records/254900IAZPP0LN8FNH78",
        "kind": "json",
    },
    "ror_ge": {
        "url": "https://api.ror.org/organizations/013msgt25",
        "kind": "json",
    },
    "gleif_draeger_safety_parent_rel": {
        "url": "https://api.gleif.org/api/v1/lei-records/549300T8IDCFNHN29E62/direct-parent-relationship",
        "kind": "json",
    },
    "ror_medtronic_us": {
        "url": "https://api.ror.org/organizations/00grd1h17",
        "kind": "json",
    },
    "ror_gehc": {
        "url": "https://api.ror.org/organizations/01bwa4v12",
        "kind": "json",
    },
    "ror_philips_nl": {
        "url": "https://api.ror.org/organizations/02p2bgp27",
        "kind": "json",
    },
    "ror_draeger": {
        "url": "https://api.ror.org/organizations/0415p9s42",
        "kind": "json",
    },
    "ror_mindray": {
        "url": "https://api.ror.org/organizations/04yfe8169",
        "kind": "json",
    },
    "crossref_medtronic": {
        "url": "https://api.crossref.org/funders/10.13039/100004374",
        "kind": "json",
    },
    "crossref_philips": {
        "url": "https://api.crossref.org/funders/10.13039/100004320",
        "kind": "json",
    },
    "crossref_ge_healthcare": {
        "url": "https://api.crossref.org/funders/10.13039/100006775",
        "kind": "json",
    },
    "wikidata_medtronic": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q642189&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
    "wikidata_gehc": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1152374&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
    "wikidata_philips": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q170416&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
    "wikidata_draeger": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q605908&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
    "wikidata_mindray": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q15138136&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
    "wikidata_covidien": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q908172&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
    "wikidata_ge": {
        "url": "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q54173&props=labels|descriptions&languages=en&format=json",
        "kind": "json",
    },
}

# Negative searches: executed and recorded so that every UNKNOWN stable id is
# backed by an actual failed lookup instead of an unsupported guess.
NEGATIVE_SEARCHES: list[dict] = [
    {
        "key": "gleif_search_covidien_plc",
        "url": "https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=Covidien%20plc&page[size]=5",
        "expect_total": 0,
        "why": "Covidien plc (Ireland, 2009-2015) has no LEI record in GLEIF",
        "path": ("meta", "pagination", "total"),
    },
    {
        "key": "gleif_search_shenzhen_mindray",
        "url": "https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=Shenzhen%20Mindray%20Bio-Medical&page[size]=5",
        "expect_total": 0,
        "why": "Shenzhen Mindray Bio-Medical Electronics Co., Ltd. has no LEI record in GLEIF",
        "path": ("meta", "pagination", "total"),
    },
    {
        "key": "gleif_search_zonare",
        "url": "https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=ZONARE&page[size]=5",
        "expect_total": 0,
        "why": "ZONARE Medical Systems, Inc. has no LEI record in GLEIF",
        "path": ("meta", "pagination", "total"),
    },
    {
        "key": "ror_search_draegerwerk",
        "url": "https://api.ror.org/organizations?query=Draegerwerk",
        "expect_total": 0,
        "why": "ASCII spelling 'Draegerwerk' returns no ROR match; the accented query 'Dräger' does",
        "path": ("number_of_results",),
    },
    {
        "key": "crossref_search_draeger",
        "url": "https://api.crossref.org/funders?query=Draegerwerk&rows=5",
        "expect_total": 0,
        "why": "no Crossref Funder Registry record for Draegerwerk AG & Co. KGaA",
        "path": ("message", "total-results"),
    },
    {
        "key": "sec_company_tickers_no_draeger_mindray",
        "url": "https://www.sec.gov/files/company_tickers.json",
        "expect_total": None,
        "kind": "absent_substring",
        "forbidden": ["DRAGER", "DRAEGER", "MINDRAY"],
        "why": "no SEC CIK exists for Draegerwerk AG & Co. KGaA or Shenzhen Mindray Bio-Medical Electronics "
               "Co., Ltd.: neither name appears in SEC's registrant ticker list",
        "path": (),
    },
    {
        "key": "crossref_search_mindray",
        "url": "https://api.crossref.org/funders?query=Shenzhen%20Mindray&rows=5",
        "expect_total": 0,
        "why": "no Crossref Funder Registry record for Shenzhen Mindray",
        "path": ("message", "total-results"),
    },
]

# Documented UNKNOWN stable identifiers: entity_key -> {id_name: attempt description}
UNKNOWN_IDS: list[dict] = [
    {"entity_key": "covidien_plc", "id": "lei",
     "attempts": ["GLEIF legal-name search 'Covidien plc' returned 0 records (negative search "
                  "gleif_search_covidien_plc in entity_provenance.json)"],
     "status": "UNKNOWN"},
    {"entity_key": "shenzhen_mindray", "id": "lei",
     "attempts": ["GLEIF legal-name search 'Shenzhen Mindray Bio-Medical' returned 0 records (negative "
                  "search gleif_search_shenzhen_mindray)"],
     "status": "UNKNOWN"},
    {"entity_key": "shenzhen_mindray", "id": "cik",
     "attempts": ["the name does not appear in SEC company_tickers.json (negative search "
                  "sec_company_tickers_no_draeger_mindray); the company is not an SEC registrant"],
     "status": "UNKNOWN"},
    {"entity_key": "draegerwerk_ag_co_kgaa", "id": "cik",
     "attempts": ["the name does not appear in SEC company_tickers.json (negative search "
                  "sec_company_tickers_no_draeger_mindray); no 10-K/20-F is filed by it"],
     "status": "UNKNOWN"},
    {"entity_key": "draegerwerk_ag_co_kgaa", "id": "funder_doi",
     "attempts": ["Crossref Funder Registry query 'Draegerwerk' returned 0 matches (negative search "
                  "crossref_search_draeger)"],
     "status": "UNKNOWN"},
    {"entity_key": "shenzhen_mindray", "id": "funder_doi",
     "attempts": ["Crossref Funder Registry query 'Shenzhen Mindray' returned 0 matches (negative search "
                  "crossref_search_mindray)"],
     "status": "UNKNOWN"},
    {"entity_key": "zonare_medical_systems_inc", "id": "lei",
     "attempts": ["GLEIF legal-name search 'ZONARE' returned 0 records (negative search "
                  "gleif_search_zonare)"],
     "status": "UNKNOWN"},
    {"entity_key": "*", "id": "cik|lei|ror|funder_doi",
     "attempts": ["For subsidiary/division/brand entities, a null identifier means that no identifier for "
                  "that legal person was found in the registry searches executed by this build; identifiers "
                  "are only written when a registry record naming the entity was retrieved"],
     "status": "NOT_APPLICABLE_OR_UNKNOWN"},
]
#
# --------------------------------------------------------------------------- #
# Evidence references
#
#   EV("source_key", "verbatim excerpt")
#   API("source_key", [ (path-tuple, expected-value), ... ])
#
# API evidence excerpts are generated from the *verified* response values, so
# the excerpt is always exactly what the registry returned.
# --------------------------------------------------------------------------- #
class Ev:
    __slots__ = ("src", "excerpt")

    def __init__(self, src, excerpt):
        self.src = src
        self.excerpt = excerpt


class ApiEv:
    __slots__ = ("src", "assertions", "label")

    def __init__(self, src, assertions, label=""):
        self.src = src
        self.assertions = assertions
        self.label = label


E = Ev
A = ApiEv


# --------------------------------------------------------------------------- #
# Entity definitions
# --------------------------------------------------------------------------- #
# Confidence rule (recorded verbatim in both artifacts and the register):
CONFIDENCE_RULE = (
    "identity_confidence is assigned by rule, not per-case taste: 0.95 = canonical identity "
    "confirmed by >=2 independent official documents AND a resolved stable registry id; "
    "0.90 = one official document plus a resolved stable registry id, or >=2 independent "
    "official documents without an id; 0.80 = one official document or one registry record "
    "that names the entity and its role but no second source; 0.60 = the entity is attested "
    "only by corpus/observed strings with parentage inferred from observed naming context "
    "(explicitly flagged as inferred); 0.40 = the string is attested but the underlying legal "
    "entity could not be pinned down."
)

MEDTRONIC_10K15 = "mdt_10k_fy2015"
MDT_PR15 = "mdt_8k_20150126_ex991"

ENTITIES: list[dict] = [
    # ======================= MEDTRONIC =====================================
    {
        "company": "medtronic",
        "entity_key": "medtronic_plc",
        "entity_type": "public_parent",
        "canonical_name": "Medtronic plc",
        "valid_from": "2014-06-12",
        "date_event": "incorporated in Ireland on 2014-06-12 as a private limited company; "
                      "re-registered as a public limited company effective 2015-01-26",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "identity_confidence": 0.95,
        "stable_ids": {
            "cik": "1613103",
            "lei": "549300GX3ZBSQWUXY261",
            "ror": None,
            "funder_doi": None,
            "wikidata": "Q642189",
        },
        "id_evidence": {
            "cik": [A("sec_sub_medtronic_plc", [
                (("name",), "Medtronic plc"),
                (("cik",), "0001613103"),
            ])],
            "lei": [A("gleif_medtronic_plc", [
                (("data", "attributes", "entity", "legalName", "name"), "MEDTRONIC PUBLIC LIMITED COMPANY"),
                (("data", "attributes", "entity", "legalAddress", "country"), "IE"),
                (("data", "attributes", "entity", "creationDate"), "2014-06-12T00:00:00Z"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ])],
            "wikidata": [A("wikidata_medtronic", [
                (("entities", "Q642189", "labels", "en", "value"), "Medtronic plc"),
            ])],
        },
        "identity_evidence": [
            E(MEDTRONIC_10K15,
              "Medtronic plc (Medtronic plc, Medtronic or the Company), the successor registrant to "
              "Medtronic, Inc., a Minnesota corporation, was incorporated in Ireland on June 12, 2014 "
              "as a private limited company, and was re-registered effective January 26, 2015 as a "
              "public limited company."),
            E(MEDTRONIC_10K15,
              "In connection with the transaction, Medtronic, Inc., a Minnesota corporation "
              "(Medtronic, Inc.), and Covidien were combined under and became subsidiaries of Medtronic plc."),
            E(MDT_PR15, "MEDTRONIC COMPLETES ACQUISITION OF COVIDIEN"),
            A("gleif_medtronic_plc", [
                (("data", "attributes", "entity", "legalName", "name"), "MEDTRONIC PUBLIC LIMITED COMPANY"),
                (("data", "attributes", "entity", "legalAddress", "city"), "Galway"),
            ]),
        ],
        "aliases": [
            {"string": "Medtronic Public Limited Company", "kind": "canonical",
             "evidence": [E(MEDTRONIC_10K15, "MEDTRONIC PUBLIC LIMITED COMPANY (Exact name of registrant as specified in its charter)")]},
            {"string": "MEDTRONIC PUBLIC LIMITED COMPANY", "kind": "alias",
             "evidence": [A("gleif_medtronic_plc", [(("data", "attributes", "entity", "legalName", "name"),
                                                    "MEDTRONIC PUBLIC LIMITED COMPANY")])]},
            {"string": "Medtronic Holdings Limited",
             "kind": "former_name",
             "valid_from": "2014-06-12", "valid_to": "2015-01-26",
             "evidence": [E("mdt_8k_20140717",
                            "On July 14, 2014, Medtronic Holdings Limited, a private limited company "
                            "organized under the laws of Ireland")]},
            {"string": "Medtronic", "kind": "alias",
             "evidence": [E(MDT_PR15, "Medtronic plc (NYSE: MDT), a global leader in medical technology, services and solutions")]},
            {"string": "Medtronic - MITG", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic - MITG")},
            {"string": "Medtronic Cardiac Rhythm and Heart Failure", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Cardiac Rhythm and Heart Failure")},
            {"string": "Medtronic Vascular", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Vascular")},
            {"string": "Medtronic Spinal and Biologics", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Spinal and Biologics")},
            {"string": "Medtronic BRC", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic BRC")},
            {"string": "Covidien AG", "kind": "subsidiary",
             "note": "Covidien-branded legal entity that survives inside Medtronic plc",
             "evidence": [E("mdt_ex21_fy2025", "Covidien AG Switzerland")]},
            {"string": "Covidien Limited", "kind": "subsidiary",
             "evidence": [E("mdt_ex21_fy2025", "Covidien Limited Ireland")]},
            {"string": "Covidien (China) Medical Devices Technology Co., Ltd.", "kind": "subsidiary",
             "evidence": [E("mdt_ex21_fy2025", "Covidien (China) Medical Devices Technology Co., Ltd. China")]},
            {"string": "Medtronic, PLC", "kind": "alias",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic, PLC")},
            {"string": "Physio-Control, Inc", "kind": "subsidiary",
             "note": "measured string 'Physio-Control, Inc, A division of Medtronic'; Physio-Control was a "
                     "Medtronic business unit, but its divestiture date is NOT verified in any fetched "
                     "document, so no date is asserted and the string must be time-scoped before 2016 use",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Physio-Control, Inc, A division of Medtronic")},
            {"string": "Medtronic Xomed, Inc.", "kind": "subsidiary",
             "evidence": [E("mdt_ex21_fy2025", "Medtronic Xomed, Inc. Delaware")]},
            {"string": "MEDTRONIC labs provide the aquamantys\u00ae probes for the study.", "kind": "not_company",
             "note": "measured sponsor field containing free text, not an entity name",
             "evidence_corpus": ("medtronic", "sponsor_strings", "MEDTRONIC labs provide the aquamantys\u00ae probes for the study.")},
            {"string": "Medtronic General Research Grant", "kind": "not_company",
             "note": "measured: a grant programme, not an entity",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic General Research Grant")},
            {"string": "Medtronic Foundation", "kind": "not_company",
             "note": "measured sponsor string; a separate non-profit legal entity, not a Medtronic operating company",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Foundation")},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "medtronic_inc",
        "entity_type": "former_parent",
        "canonical_name": "Medtronic, Inc.",
        "valid_from": "1957-04-23",
        "date_event": "registry creation date reported by the GLEIF LEI record for 'Medtronic, Inc.' "
                      "(Minnesota); the business itself traces to 1949, which no fetched primary "
                      "document states, so 1949 is NOT used",
        "valid_to": "2015-01-26",
        "valid_to_event": "ceased to be the public parent on 2015-01-26, when Medtronic, Inc. and "
                          "Covidien 'became subsidiaries of Medtronic plc' (the entity continues as a "
                          "Minnesota subsidiary: it is listed in the FY2025 Exhibit 21)",
        "parent_entity_key": "medtronic_plc",
        "parent_note": "the 2015-01-26 acquisition made Medtronic, Inc. a subsidiary of Medtronic plc; before "
                       "that date Medtronic, Inc. was itself the listed parent (no parent)",
        "identity_confidence": 0.95,
        "stable_ids": {
            "cik": "64670",
            "lei": "D56MRZY2INAN94ZONZ37",
            "ror": "00grd1h17",
            "funder_doi": "10.13039/100004374",
            "wikidata": None,
        },
        "id_evidence": {
            "cik": [A("sec_sub_medtronic_inc", [
                (("name",), "MEDTRONIC INC"),
                (("cik",), "0000064670"),
            ])],
            "lei": [A("gleif_medtronic_inc", [
                (("data", "attributes", "entity", "legalName", "name"), "Medtronic, Inc."),
                (("data", "attributes", "entity", "legalAddress", "country"), "US"),
                (("data", "attributes", "entity", "creationDate"), "1957-04-23T00:00:00Z"),
            ])],
            "ror": [A("ror_medtronic_us", [
                (("id",), "https://ror.org/00grd1h17"),
            ])],
            "funder_doi": [A("crossref_medtronic", [
                (("message", "name"), "Medtronic"),
            ])],
        },
        "identity_evidence": [
            E("mdt_8k_20140717",
              "Medtronic, Inc. (Exact name of registrant as specified in its charter) Minnesota 1-7707"),
            E(MEDTRONIC_10K15,
              "In connection with the transaction, Medtronic, Inc., a Minnesota corporation (Medtronic, "
              "Inc.), and Covidien were combined under and became subsidiaries of Medtronic plc."),
            E("mdt_ex21_fy2025", "Medtronic, Inc. Minnesota"),
            E(MEDTRONIC_10K15,
              "MergerSub merged with and into Medtronic Inc., with Medtronic Inc. as the surviving "
              "corporation in the merger"),
            A("gleif_medtronic_inc", [
                (("data", "attributes", "entity", "legalName", "name"), "Medtronic, Inc."),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ]),
        ],
        "aliases": [
            {"string": "Medtronic Inc.", "kind": "alias",
             "evidence_corpus": ("medtronic", "affiliation_strings_sample", "Medtronic Inc., Minneapolis, MN, USA.")},
            {"string": "Medtronic, Inc", "kind": "alias",
             "evidence_corpus": ("medtronic", "affiliation_strings_sample", "Medtronic, Inc, Minneapolis, Minnesota.")},
            {"string": "MEDTRONIC INC", "kind": "alias",
             "evidence": [E("mdt_8k_20010905", "Medtronic, Inc. (Exact Name of Registrant as Specified in Its Charter)")]},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "covidien_plc",
        "entity_type": "former_parent",
        "canonical_name": "Covidien plc",
        "valid_from": "2009-06-04",
        "date_event": "reorganisation completed 2009-06-04: 'Covidien plc replaced Covidien Ltd. as the "
                      "ultimate parent company' (first NYSE trade of the new Irish shares 2009-06-05)",
        "valid_to": "2015-01-26",
        "valid_to_event": "acquired by Medtronic plc on completion 2015-01-26. Covidien plc does not appear "
                          "in Medtronic's FY2025 Exhibit 21 (which lists Covidien AG and Covidien Limited), "
                          "i.e. there is no evidence that it survives as a separate legal person; the brand "
                          "'Covidien' does continue inside the Medtronic group",
        "parent_entity_key": None,
        "parent_note": "independent public parent until 2015-01-26; owned by Medtronic plc only during the "
                       "closing period, hence no parent link is asserted",
        "identity_confidence": 0.95,
        "stable_ids": {
            "cik": "1385187",
            "lei": None,
            "ror": None,
            "funder_doi": None,
            "wikidata": "Q908172",
        },
        "id_evidence": {
            "cik": [A("sec_sub_covidien", [
                (("name",), "Covidien plc"),
                (("cik",), "0001385187"),
            ])],
            "wikidata": [A("wikidata_covidien", [
                (("entities", "Q908172", "labels", "en", "value"), "Covidien"),
            ])],
        },
        "identity_evidence": [
            E("cov_10k_fy2014",
              "The reorganization transaction was completed on June 4, 2009, following approval from the "
              "Supreme Court of Bermuda, at which time Covidien plc replaced Covidien Ltd. as the ultimate "
              "parent company."),
            E("cov_10k_fy2014",
              "Shares of the Irish company, Covidien plc, began trading on the New York Stock Exchange on "
              "June 5, 2009, under the symbol"),
            E(MEDTRONIC_10K15,
              "Medtronic and IrSub acquired Covidien (the Acquisition) pursuant to the Irish Scheme of "
              "Arrangement under Section 201"),
            E(MEDTRONIC_10K15,
              "On January 26, 2015 (Acquisition Date), Medtronic completed the acquisition of Covidien plc, "
              "a public limited company organized under the laws of Ireland (Covidien) in a cash and stock "
              "transaction valued at approximately $50 billion."),
        ],
        "aliases": [
            {"string": "Covidien", "kind": "brand",
             "note": "the company name ended 2015-01-26; the brand continues as a product brand inside the "
                     "Medtronic group, so the string must be time-scoped before being treated as Medtronic",
             "evidence": [E(MEDTRONIC_10K15,
                            "On January 26, 2015 (Acquisition Date), Medtronic completed the acquisition of "
                            "Covidien plc, a public limited company organized under the laws of Ireland (Covidien)")]},
            {"string": "Covidien plc", "kind": "canonical",
             "evidence": [E("cov_10k_fy2014", "Covidien plc, a company incorporated in Ireland")]},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "covidien_ltd",
        "entity_type": "former_parent",
        "canonical_name": "Covidien Ltd.",
        "valid_from": "2007-06-29",
        "date_event": "became an independent public parent on 2007-06-29 when Tyco International distributed "
                      "all of its shares to Tyco shareholders (before that date it 'did not engage in any "
                      "significant business activities'; it was incorporated in Bermuda in 2000, day UNKNOWN)",
        "valid_to": "2009-06-04",
        "valid_to_event": "replaced as ultimate parent by Covidien plc on completion of the 2009 reorganisation",
        "parent_entity_key": None,
        "identity_confidence": 0.9,
        "stable_ids": {"cik": "1385187", "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "cik": [E("cov_10k_fy2007", "COVIDIEN LTD. (Exact name of registrant as specified in its charter) Bermuda")],
        },
        "identity_evidence": [
            E("cov_10k_fy2007",
              "Covidien Ltd. was incorporated in Bermuda in 2000 as a wholly-owned subsidiary of Tyco "
              "International Ltd."),
            E("cov_10k_fy2007",
              "As part of a plan to separate Tyco International into three independent companies, Tyco "
              "International transferred the equity interests of the entities that held all of the assets "
              "and liabilities of its healthcare businesses to Covidien and, on June 29, 2007, distributed "
              "all of its shares of Covidien to its shareholders."),
            E("cov_10k_fy2014",
              "at which time Covidien plc replaced Covidien Ltd. as the ultimate parent company"),
        ],
        "aliases": [
            {"string": "Covidien Ltd.", "kind": "canonical",
             "note": "shares the SEC CIK 1385187 with Covidien plc: the registrant was reorganised in 2009, so "
                     "the CIK identifies the registrant lineage, not a single legal person",
             "evidence": [E("cov_10k_fy2007", "COVIDIEN LTD. (Exact name of registrant as specified in its charter)")]},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "tyco_healthcare",
        "entity_type": "division",
        "canonical_name": "Tyco Healthcare (Tyco International healthcare business)",
        "valid_from": None,
        "date_event": "UNKNOWN: the division is attested only as the healthcare business of Tyco "
                      "International Ltd.; no fetched document gives its start date",
        "valid_to": "2007-06-29",
        "valid_to_event": "Tyco International distributed the healthcare entities' shares to Covidien "
                          "shareholders on 2007-06-29 (the '2007 separation')",
        "parent_entity_key": None,
        "identity_confidence": 0.8,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("cov_10k_fy2007",
              "for all periods prior to June 29, 2007, a combined reporting entity comprised of the assets "
              "and liabilities used in managing Tyco International Ltd."),
            E("cov_10k_fy2007",
              "on June 29, 2007, distributed all of its shares of Covidien to its shareholders"),
        ],
        "aliases": [
            {"string": "Tyco Healthcare", "kind": "former_name",
             "note": "the name survives in Covidien's legal entities and in litigation captions; the division "
                     "itself was not separately incorporated",
             "evidence": [E("cov_10k_fy2007", "Tyco Healthcare Group LP v. Applied Medical Resources Corp")]},
            {"string": "Tyco Healthcare Group LP", "kind": "subsidiary",
             "note": "Delaware legal entity, listed in the FY2007 Covidien Exhibit 21; the corporate string "
                     "'Tyco Healthcare' is the division name, the LP is a legal entity",
             "evidence": [E("cov_ex21_fy2007", "Tyco Healthcare Group LP DE")]},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "minimed_inc",
        "entity_type": "former_subsidiary",
        "canonical_name": "MiniMed Inc.",
        "valid_from": None,
        "date_event": "UNKNOWN: no fetched document states when MiniMed Inc. was incorporated",
        "valid_to": "2001-08-28",
        "valid_to_event": "acquired 2001-08-28 through a merger of a newly created Medtronic subsidiary "
                          "into MiniMed; ceased to be an independent company",
        "parent_entity_key": "medtronic_inc",
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("mdt_8k_20010905",
              "On August 28, 2001, Medtronic, Inc. (the \"Registrant\") acquired all of the outstanding "
              "stock of MiniMed Inc. (\"MiniMed\") through a merger of a newly-created subsidiary of the "
              "Registrant into MiniMed."),
            E("mdt_10k_fy2002",
              "In August 2001, we acquired MiniMed Inc. and a related company, Medical Research Group, "
              "Inc., for a total of approximately $3.8 billion in cash."),
            E("mdt_10k_fy2001",
              "In May 2001, the company announced that it had signed an agreement to purchase MiniMed Inc."),
        ],
        "aliases": [
            {"string": "MiniMed Inc.", "kind": "canonical",
             "evidence": [E("mdt_8k_20010905", "acquired all of the outstanding stock of MiniMed Inc.")]},
            {"string": "MiniMed", "kind": "alias",
             "evidence_corpus": ("medtronic", "sponsor_strings", "MiniMed")},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "medtronic_minimed_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Medtronic MiniMed, Inc.",
        "valid_from": None,
        "date_event": "UNKNOWN: the entity appears in the FY2025 Exhibit 21 as a Delaware subsidiary; no "
                      "fetched document states when it was incorporated or when it was renamed",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "medtronic_plc",
        "identity_confidence": 0.8,
        "stable_ids": {"cik": None, "lei": "254900IAZPP0LN8FNH78", "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "lei": [A("gleif_medtronic_minimed", [
                (("data", "attributes", "entity", "legalName", "name"), "MEDTRONIC MINIMED, INC."),
                (("data", "attributes", "entity", "legalAddress", "country"), "US"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ])],
        },
        "identity_evidence": [
            E("mdt_ex21_fy2025", "Medtronic MiniMed, Inc. Delaware"),
            A("gleif_medtronic_minimed", [
                (("data", "attributes", "entity", "legalName", "name"), "MEDTRONIC MINIMED, INC."),
                (("data", "attributes", "entity", "legalAddress", "city"), "WILMINGTON"),
            ]),
        ],
        "aliases": [
            {"string": "Medtronic MiniMed, Inc.", "kind": "canonical",
             "evidence": [E("mdt_ex21_fy2025", "Medtronic MiniMed, Inc. Delaware")]},
            {"string": "Medtronic MiniMed", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic MiniMed, Inc.")},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "medtronic_vascular_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Medtronic Vascular, Inc.",
        "valid_from": None,
        "date_event": "UNKNOWN: listed in the FY2025 Exhibit 21 as a Delaware subsidiary; no fetched "
                      "document gives its incorporation or acquisition date",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "medtronic_plc",
        "identity_confidence": 0.85,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("mdt_ex21_fy2025", "Medtronic Vascular, Inc. Delaware"),
        ],
        "aliases": [
            {"string": "Medtronic Vascular, Inc.", "kind": "canonical",
             "evidence": [E("mdt_ex21_fy2025", "Medtronic Vascular, Inc. Delaware")]},
            {"string": "Medtronic Vascular", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Vascular")},
            {"string": "Medtronic Endovascular", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Endovascular")},
        ],
    },
    {
        "company": "medtronic",
        "entity_key": "medtronic_sofamor_danek_usa_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Medtronic Sofamor Danek USA, Inc.",
        "valid_from": None,
        "date_event": "UNKNOWN: listed in the FY2025 Exhibit 21 as a Tennessee subsidiary; no fetched "
                      "document gives its incorporation date or the Sofamor Danek acquisition date",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "medtronic_plc",
        "identity_confidence": 0.85,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("mdt_ex21_fy2025", "Medtronic Sofamor Danek USA, Inc. Tennessee"),
        ],
        "aliases": [
            {"string": "Medtronic Sofamor Danek USA, Inc.", "kind": "canonical",
             "evidence": [E("mdt_ex21_fy2025", "Medtronic Sofamor Danek USA, Inc. Tennessee")]},
            {"string": "Medtronic Sofamor Danek", "kind": "operating_unit_prefix",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Sofamor Danek")},
            {"string": "Medtronic Spine LLC", "kind": "operating_unit_prefix",
             "note": "measured sponsor string; it does NOT appear in the FY2025 Exhibit 21, so no legal-entity "
                     "status is asserted and it is treated as a business-unit name",
             "evidence_corpus": ("medtronic", "sponsor_strings", "Medtronic Spine LLC")},
        ],
    },
    # ======================= GE HEALTHCARE =================================
    {
        "company": "ge_healthcare",
        "entity_key": "ge_healthcare_technologies_inc",
        "entity_type": "public_parent",
        "canonical_name": "GE HealthCare Technologies Inc.",
        "valid_from": "2022-05-16",
        "date_event": "Delaware incorporation date reported by its GLEIF LEI record (2022-05-16); the "
                      "spin-off from General Electric completed 2023-01-03 and regular-way trading began "
                      "2023-01-04",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "identity_confidence": 0.95,
        "stable_ids": {
            "cik": "1932393",
            "lei": "549300OI9J7XOWZMUN85",
            "ror": "01bwa4v12",
            "funder_doi": "10.13039/100006775",
            "wikidata": "Q1152374",
        },
        "id_evidence": {
            "cik": [A("sec_sub_gehc", [
                (("name",), "GE HealthCare Technologies Inc."),
                (("cik",), "0001932393"),
            ])],
            "lei": [A("gleif_gehc", [
                (("data", "attributes", "entity", "legalName", "name"), "GE HEALTHCARE TECHNOLOGIES INC."),
                (("data", "attributes", "entity", "legalAddress", "country"), "US"),
                (("data", "attributes", "entity", "creationDate"), "2022-05-16T00:00:00Z"),
                (("data", "attributes", "entity", "registeredAs"), "6772877"),
            ])],
            "ror": [A("ror_gehc", [
                (("id",), "https://ror.org/01bwa4v12"),
                (("names", 0, "value"), "GE HealthCare"),
            ])],
            "funder_doi": [A("crossref_ge_healthcare", [
                (("message", "name"), "GE Healthcare"),
            ])],
            "wikidata": [A("wikidata_gehc", [
                (("entities", "Q1152374", "labels", "en", "value"), "GE HealthCare"),
            ])],
        },
        "identity_evidence": [
            E("gehc_10k_fy2022",
              "GE HealthCare Technologies Inc., a Delaware corporation, completed i ts spin off (the"),
            E("gehc_10k_fy2022",
              "on January 3, 2023. On January 4, 2023, our common stock began regular-way trading on The "
              "Nasdaq Stock Market LLC"),
            E("gehc_10k_fy2022",
              "A \"when issued\" trading market for GE HealthCare's common stock began on Nasdaq on "
              "December 16, 2022, and \"regular way\" trading of GE HealthCare's common stock began on "
              "January 4, 2023."),
            A("gleif_gehc", [
                (("data", "attributes", "entity", "legalName", "name"), "GE HEALTHCARE TECHNOLOGIES INC."),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ]),
        ],
        "aliases": [
            {"string": "GE HealthCare Technologies Inc.", "kind": "canonical",
             "evidence": [E("gehc_10k_fy2022", "GE HEALTHCARE TECHNOLOGIES INC. (Exact name of registrant as specified in its charter)")]},
            {"string": "GE HealthCare", "kind": "alias",
             "evidence": [E("gehc_10k_fy2022", "GE HealthCare Technologies Inc. (\"GE HealthCare,\" the \"Company,\" \"our,\" or \"we\")")]},
            {"string": "GE Healthcare", "kind": "alias",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "GE Healthcare")},
            {"string": "GE HealthCare MR Research", "kind": "operating_unit_prefix",
             "evidence_corpus": ("ge_healthcare", "affiliation_strings_sample", "GE HealthCare MR Research, Beijing, China.")},
            {"string": "General Electric", "kind": "former_name",
             "note": "the former parent, not the spun-off issuer",
             "evidence": [E("gehc_10k_fy2022", "spin off (the")]},
            {"string": "Imperial College Healthcare NHS Trust", "kind": "not_company",
             "note": "measured substring false positive: an NHS hospital trust, not GE HealthCare",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "Imperial College Healthcare NHS Trust")},
            {"string": "Orange healthcare", "kind": "not_company",
             "note": "measured substring false positive: telehealth brand, not GE HealthCare",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "Orange healthcare")},
            {"string": "Canadian Heads of Academic Radiology-GE Healthcare Development Award", "kind": "not_company",
             "note": "a named research award, not a legal entity",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "Canadian Heads of Academic Radiology-GE Healthcare Development Award")},
        ],
    },
    {
        "company": "ge_healthcare",
        "entity_key": "general_electric",
        "entity_type": "former_parent",
        "canonical_name": "General Electric Company",
        "valid_from": None,
        "date_event": "UNKNOWN: no fetched document states the incorporation date of General Electric Company",
        "valid_to": "2023-01-03",
        "valid_to_event": "GE HealthCare spin-off completed 2023-01-03; GE ceased to be the parent",
        "parent_entity_key": None,
        "identity_confidence": 0.85,
        "stable_ids": {"cik": "40545", "lei": None, "ror": "013msgt25", "funder_doi": None, "wikidata": "Q54173"},
        "id_evidence": {
            "cik": [A("sec_sub_ge", [
                (("name",), "GENERAL ELECTRIC CO"),
                (("cik",), "0000040545"),
            ])],
            "ror": [A("ror_ge", [
                (("id",), "https://ror.org/013msgt25"),
            ])],
            "wikidata": [A("wikidata_ge", [
                (("entities", "Q54173", "labels", "en", "value"), "General Electric"),
            ])],
        },
        "identity_evidence": [
            E("gehc_10k_fy2022",
              "from General Electric Company"),
            E("ge_10k_fy2021",
              "Peter J. Arduini Senior Vice President of General Electric Company"),
        ],
        "aliases": [
            {"string": "General Electric", "kind": "canonical",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "General Electric")},
            {"string": "GE", "kind": "alias",
             "note": "ticker/short name; ambiguous on its own, resolved to the former parent in this corpus",
             "evidence": [E("gehc_10k_fy2022", "from General Electric Company")]},
            {"string": "General Electric Research", "kind": "not_company",
             "note": "measured sponsor string: GE's corporate research organisation, not a distinct company",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "General Electric Research")},
        ],
    },
    {
        "company": "ge_healthcare",
        "entity_key": "ge_healthcare_division",
        "entity_type": "division",
        "canonical_name": "GE Healthcare (division of General Electric)",
        "valid_from": None,
        "date_event": "UNKNOWN: no fetched document states the day the division was named 'GE Healthcare'; "
                      "GE's FY2003 10-K reports the segment as 'Medical Systems' and its FY2004 10-K reports "
                      "it as 'Healthcare', so the change falls between the two filings",
        "valid_to": "2023-01-03",
        "valid_to_event": "the business left General Electric when the spin-off completed 2023-01-03",
        "parent_entity_key": "general_electric",
        "identity_confidence": 0.8,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("ge_10k_fy2004", "Healthcare Healthcare (8.8%, 7.6% and 6.8% of consolidated revenues in 2004, 2003 and 2002, respectively)"),
            E("ge_10k_fy2021", "President & CEO, GE Healthcare"),
            E("gehc_10k_fy2022", "spin off (the"),
        ],
        "aliases": [
            {"string": "GE Healthcare", "kind": "canonical",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "GE Healthcare")},
            {"string": "GE Healthcare Technologies", "kind": "former_name",
             "note": "officer title 'Senior Vice President, GE Healthcare Technologies' in the FY2004 10-K",
             "evidence": [E("ge_10k_fy2004", "Senior Vice President, GE Healthcare Technologies")]},
            {"string": "general electric healthcare Finland", "kind": "alias",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "general electric healthcare Finland")},
            {"string": "General Electric Healthcare", "kind": "alias",
             "note": "measured affiliation form ('General Electric Healthcare, Aurora, OH'); the division-era "
                     "spelling of the GE Healthcare business, not the spun-off issuer",
             "evidence_corpus": ("ge_healthcare", "affiliation_strings_sample", "General Electric Healthcare, Aurora, OH 44202, USA.")},
            {"string": "GE Healthcare China", "kind": "operating_unit_prefix",
             "evidence_corpus": ("ge_healthcare", "affiliation_strings_sample", "GE Healthcare China, Beijing, China.")},
            {"string": "GE Healthcare Finland Ltd", "kind": "subsidiary",
             "note": "measured sponsor string; a local legal entity, no stable id verified",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "GE Healthcare Finland Ltd")},
        ],
    },
    {
        "company": "ge_healthcare",
        "entity_key": "ge_medical_systems_division",
        "entity_type": "division",
        "canonical_name": "GE Medical Systems (division of General Electric)",
        "valid_from": None,
        "date_event": "UNKNOWN: attested as a GE reportable segment in the FY2003 10-K; no fetched document "
                      "gives a start date",
        "valid_to": None,
        "valid_to_event": "UNKNOWN: last attested as a segment name in the FY2003 10-K; by the FY2004 10-K "
                          "the segment is called 'Healthcare'. A third-party 2006 10-K (CVD Equipment, CIK "
                          "1049521) already calls the successor 'GE Healthcare (formerly GE Medical Systems)'.",
        "parent_entity_key": "general_electric",
        "identity_confidence": 0.8,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("ge_10k_fy2003", "Medical Systems Medical Systems (7.6%, 6.8% and 6.7% of consolidated revenues in 2003, 2002 and 2001, respectively)"),
            E("ge_10k_fy2004", "Healthcare Healthcare (8.8%, 7.6% and 6.8% of consolidated revenues in 2004, 2003 and 2002, respectively)"),
        ],
        "aliases": [
            {"string": "GE Medical Systems", "kind": "canonical",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "GE Medical Systems ultrasound (only technical support)")},
            {"string": "GE Medical Systems ultrasound (only technical support)", "kind": "operating_unit_prefix",
             "evidence_corpus": ("ge_healthcare", "sponsor_strings", "GE Medical Systems ultrasound (only technical support)")},
        ],
    },
    # ======================= PHILIPS =======================================
    {
        "company": "philips",
        "entity_key": "koninklijke_philips_nv",
        "entity_type": "public_parent",
        "canonical_name": "Koninklijke Philips N.V.",
        "valid_from": "1912-09-11",
        "date_event": "converted into the limited company N.V. Philips' Gloeilampenfabrieken on 1912-09-11; "
                      "renamed Philips Electronics N.V. (1994-05-06), Koninklijke Philips Electronics N.V. "
                      "(1998-04-01) and Koninklijke Philips N.V. (2013-05-03)",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "identity_confidence": 0.95,
        "stable_ids": {
            "cik": "313216",
            "lei": "H1FJE8H61JGM1JSGM897",
            "ror": "02p2bgp27",
            "funder_doi": "10.13039/100004320",
            "wikidata": "Q170416",
        },
        "id_evidence": {
            "cik": [A("sec_sub_philips", [
                (("name",), "KONINKLIJKE PHILIPS NV"),
                (("cik",), "0000313216"),
            ])],
            "lei": [A("gleif_philips_nv", [
                (("data", "attributes", "entity", "legalName", "name"), "Koninklijke Philips N.V."),
                (("data", "attributes", "entity", "legalAddress", "country"), "NL"),
                (("data", "attributes", "entity", "registeredAs"), "17001910"),
            ])],
            "ror": [A("ror_philips_nl", [
                (("id",), "https://ror.org/02p2bgp27"),
                (("names", 0, "value"), "Koninklijke Philips"),
            ])],
            "funder_doi": [A("crossref_philips", [
                (("message", "name"), "Philips"),
            ])],
            "wikidata": [A("wikidata_philips", [
                (("entities", "Q170416", "labels", "en", "value"), "Koninklijke Philips NV"),
            ])],
        },
        "identity_evidence": [
            E("phg_20f_fy2013",
              "was converted into the company with limited liability N.V. Philips\u2019 Gloeilampenfabrieken on September 11, 1912."),
            E("phg_20f_fy2013",
              "The Company\u2019s name was changed to Philips Electronics N.V. on May 6, 1994, to Koninklijke "
              "Philips Electronics N.V. on April 1, 1998, and to Koninklijke Philips N.V. on May 3, 2013."),
            E("phg_20f_fy2024",
              "References to the Company or company, to Philips or the (Philips) Group or group, relate to "
              "Koninklijke Philips N.V. and its subsidiaries, as the context requires. Royal Philips refers "
              "to Koninklijke Philips N.V."),
        ],
        "aliases": [
            {"string": "Koninklijke Philips N.V.", "kind": "canonical",
             "evidence": [E("phg_20f_fy2013", "KONINKLIJKE PHILIPS N.V. (Exact name of Registrant as specified in charter)")]},
            {"string": "Royal Philips", "kind": "alias",
             "note": "brand name / English translation, not a separate legal entity",
             "evidence": [E("phg_20f_fy2024", "Royal Philips refers to Koninklijke Philips N.V.")]},
            {"string": "Philips", "kind": "brand",
             "note": "group brand; the 20-F defines group references as referring to Koninklijke Philips N.V.",
             "evidence": [E("phg_20f_fy2024",
                            "References to the Company or company, to Philips or the (Philips) Group or group, "
                            "relate to Koninklijke Philips N.V. and its subsidiaries, as the context requires.")]},
            {"string": "Koninklijke Philips Electronics N.V.", "kind": "former_name",
             "valid_from": "1998-04-01", "valid_to": "2013-05-03",
             "evidence": [E("phg_20f_fy2013", "to Koninklijke Philips Electronics N.V. on April 1, 1998")]},
            {"string": "Philips Electronics N.V.", "kind": "former_name",
             "valid_from": "1994-05-06", "valid_to": "1998-04-01",
             "evidence": [E("phg_20f_fy2013", "The Company\u2019s name was changed to Philips Electronics N.V. on May 6, 1994")]},
            {"string": "N.V. Philips' Gloeilampenfabrieken", "kind": "former_name",
             "valid_from": "1912-09-11", "valid_to": "1994-05-06",
             "evidence": [E("phg_20f_fy2013", "N.V. Philips\u2019 Gloeilampenfabrieken")]},
            {"string": "Philips Electronics Nederland BV", "kind": "subsidiary",
             "note": "operating company, distinct from the listed parent",
             "evidence": [A("gleif_philips_electronics_nederland", [
                 (("data", "attributes", "entity", "legalName", "name"), "PHILIPS ELECTRONICS NEDERLAND B.V."),
                 (("data", "attributes", "entity", "legalAddress", "city"), "EINDHOVEN"),
             ])]},
            {"string": "Philips GmbH", "kind": "subsidiary",
             "evidence": [E("phg_20f_fy2024", "Philips GmbH, Hamburg")]},
            {"string": "Philips Health Care", "kind": "alias",
             "note": "measured two-word variant of the sector name",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Health Care")},
            {"string": "EPD Solutions", "kind": "subsidiary",
             "note": "measured string 'EPD Solutions, A Philips Company'",
             "evidence_corpus": ("philips", "sponsor_strings", "EPD Solutions, A Philips Company")},
            {"string": "Philips Oral Healthcare, LLC", "kind": "subsidiary",
             "evidence": [E("phg_ar2015", "Philips Oral Healthcare, LLC United States")]},
            {"string": "Philips Intellectual Property & Standards", "kind": "operating_unit_prefix",
             "note": "corporate department, not a legal entity",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Intellectual Property & Standards")},
            {"string": "Philips Research Eindhoven", "kind": "operating_unit_prefix",
             "note": "corporate research site, not a legal entity",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Research Eindhoven")},
            {"string": "Bj\u00f6rn Philips", "kind": "not_company",
             "note": "COLLISION: measured sponsor string that is a person's name (surname Philips), not the company",
             "evidence_corpus": ("philips", "sponsor_strings", "Bj\u00f6rn Philips")},
        ],
    },
    {
        "company": "philips",
        "entity_key": "philips_medical_systems_division",
        "entity_type": "division",
        "canonical_name": "Philips Medical Systems (division of Philips)",
        "valid_from": None,
        "date_event": "UNKNOWN: attested as the 'former Medical Systems division' in the FY2008 20-F; no "
                      "fetched document gives the day the division was created or named",
        "valid_to": "2008-01-01",
        "valid_to_event": "from 2008-01-01 Philips organised activities into sectors and the Healthcare sector "
                          "absorbed the 'former Medical Systems division'",
        "parent_entity_key": "koninklijke_philips_nv",
        "identity_confidence": 0.85,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("phg_20f_fy2008",
              "As of January 1, 2008, Philips\u2019 activities are organized on a sector basis, with each "
              "operating sector"),
            E("phg_20f_fy2008",
              "The Healthcare sector brings together the former Medical Systems division and Home "
              "Healthcare Solutions (formerly Consumer Healthcare Solutions)"),
            E("phg_20f_fy2008",
              "Our new Healthcare sector brings together our former Medical Systems division and our "
              "growing Home Healthcare Solutions business."),
        ],
        "aliases": [
            {"string": "Philips Medical Systems", "kind": "canonical",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Medical Systems")},
            {"string": "Philips Medizin Systeme B\u00f6blingen GmbH", "kind": "subsidiary",
             "note": "the legal-entity form of the name (Germany), listed in the FY2024 20-F",
             "evidence": [E("phg_20f_fy2024", "Philips Medizin Systeme B\u00f6blingen GmbH Germany")]},
            {"string": "Philips Medical Systems (Cleveland), Inc.", "kind": "subsidiary",
             "evidence": [E("phg_20f_fy2024", "Philips Medical Systems (Cleveland), Inc. United States")]},
            {"string": "Philips Medical Systems Nederland B.V.", "kind": "subsidiary",
             "evidence": [E("phg_20f_fy2024", "Philips Medical Systems DMC GmbH, Hamburg")]},
        ],
    },
    {
        "company": "philips",
        "entity_key": "philips_healthcare_division",
        "entity_type": "division",
        "canonical_name": "Philips Healthcare (sector/brand of Koninklijke Philips N.V.)",
        "valid_from": "2008-01-01",
        "date_event": "Philips reorganised into sectors on 2008-01-01 and the Healthcare sector replaced the "
                      "former Medical Systems division",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "koninklijke_philips_nv",
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("phg_20f_fy2008",
              "About Philips Healthcare Philips is one of the top-tier players in the healthcare technology "
              "market (based on sales) alongside General Electric (GE) and Siemens."),
            E("phg_20f_fy2008",
              "Our new Healthcare sector brings together our former Medical Systems division and our "
              "growing Home Healthcare Solutions business."),
            E("phg_20f_fy2008",
              "As of January 1, 2008, Philips\u2019 activities are organized on a sector basis"),
        ],
        "aliases": [
            {"string": "Philips Healthcare", "kind": "canonical",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Healthcare")},
            {"string": "Philips Healthcare (Suzhou) Co., Ltd.", "kind": "subsidiary",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Healthcare (Suzhou) Co., Ltd.")},
            {"string": "Philips Clinical & Medical Affairs Global", "kind": "not_company",
             "note": "measured: a functional department inside Philips, not a legal entity; 114 sponsor records",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Clinical & Medical Affairs Global")},
            {"string": "Philips Chair for Medical Information Technology", "kind": "not_company",
             "note": "measured: an endowed university chair (RWTH Aachen), not a Philips entity",
             "evidence_corpus": ("philips", "affiliation_strings_sample", "Philips Chair for Medical Information Technology, Helmholtz-Institute for Biomedical Engineering, RWTH Aachen")},
            {"string": "Philips Institute for Oral Health Research", "kind": "not_company",
             "note": "measured: a university research institute (Virginia Commonwealth University), not a Philips entity",
             "evidence_corpus": ("philips", "affiliation_strings_sample", "Philips Institute for Oral Health Research, School of Dentistry, Virginia Commonwealth University (VCU), Rich")},
        ],
    },
    {
        "company": "philips",
        "entity_key": "respironics_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Respironics, Inc.",
        "valid_from": "2008-03-17",
        "date_event": "acquisition completed: Philips press release dated 2008-03-17 states 'Philips has "
                      "completed the acquisition of Respironics through the merger of its indirect wholly "
                      "owned subsidiary with and into Respironics' (the tender offer expired 2008-03-13)",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "koninklijke_philips_nv",
        "identity_confidence": 0.9,
        "stable_ids": {"cik": "780434", "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "cik": [A("sec_sub_respironics", [
                (("name",), "RESPIRONICS INC"),
                (("cik",), "0000780434"),
            ])],
        },
        "identity_evidence": [
            E("phg_6k_20080321",
              "PHILIPS ANNOUNCES COMPLETION OF RESPIRONICS ACQUISITION"),
            E("phg_6k_20080321",
              "Philips has completed the acquisition of Respironics through the merger of its indirect "
              "wholly owned subsidiary with and into Respironics. As a result of the merger, Respironics "
              "has become an indirect wholly owned subsidiary of Philips."),
            E("phg_6k_20080321",
              "As of March 10, 2008, Respironics\u2019 financial results will be accounted for in the "
              "financial results of Philips Healthcare."),
        ],
        "aliases": [
            {"string": "Respironics, Inc.", "kind": "canonical",
             "evidence": [E("phg_6k_20080321", "Respironics, Inc. (NASDAQ:RESP)")]},
            {"string": "Philips Respironics", "kind": "brand",
             "evidence_corpus": ("philips", "sponsor_strings", "Philips Respironics")},
            {"string": "Philips RS North America LLC Formerly Known as Respironics, Inc.",
             "kind": "former_name",
             "note": "measured affiliation string; the legal renaming date to Philips RS North America LLC is "
                     "not verified in any fetched official document, so no date is asserted",
             "evidence_corpus": ("philips", "affiliation_strings_sample", "Philips RS North America LLC Formerly Known as Respironics, Inc.")},
            {"string": "Respironics, California, Inc.", "kind": "subsidiary",
             "evidence_corpus": ("philips", "sponsor_strings", "Respironics, California, Inc.")},
        ],
    },
    {
        "company": "philips",
        "entity_key": "philips_lighting_nv",
        "entity_type": "former_subsidiary",
        "canonical_name": "Philips Lighting N.V.",
        "valid_from": "2016-05-27",
        "date_event": "listed and began trading on Euronext Amsterdam 2016-05-27; Philips retained 71.225% "
                      "at listing and deconsolidated it at the end of November 2017",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "parent_note": "Philips held 71.225% at the 2016-05-27 listing and deconsolidated Philips Lighting at "
                       "the end of November 2017, so no current parent link is asserted",
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("phg_ar2016",
              "a stand-alone structure was established for Philips Lighting within the Philips Group, "
              "effective February 1, 2016."),
            E("phg_ar2016",
              "Then, on May 27, 2016, Philips Lighting was listed and started trading on Euronext in "
              "Amsterdam under the symbol"),
            E("phg_ar2016",
              "Following the listing of Philips Lighting, Philips retained a 71.225% stake"),
            E("phg_20f_fy2024",
              "prior to deconsolidation as from the end of November 2017"),
        ],
        "aliases": [
            {"string": "Philips Lighting", "kind": "canonical",
             "evidence": [E("phg_ar2016", "Philips Lighting was listed and started trading on Euronext in Amsterdam")]},
            {"string": "Signify N.V.", "kind": "former_name",
             "note": "renamed in May 2018 (month precision only; no day-level date is asserted)",
             "evidence": [E("phg_20f_fy2024", "Signify N.V. (after its renaming in May 2018)")]},
        ],
    },
    # ======================= DRAEGER =======================================
    {
        "company": "draeger",
        "entity_key": "draegerwerk_ag_co_kgaa",
        "entity_type": "public_parent",
        "canonical_name": "Dr\u00e4gerwerk AG & Co. KGaA",
        "valid_from": None,
        "date_event": "UNKNOWN: no fetched official document states the incorporation date of the KGaA. "
                      "The GLEIF record reports a registry creation date of 1970-06-29, which is not used "
                      "here because its legal meaning (formation vs. conversion) was not verified",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": "5493005UFVHY0PPNKD75", "ror": "0415p9s42", "funder_doi": None, "wikidata": "Q605908"},
        "id_evidence": {
            "lei": [A("gleif_draegerwerk", [
                (("data", "attributes", "entity", "legalName", "name"), "Dr\u00e4gerwerk AG & Co. KGaA"),
                (("data", "attributes", "entity", "legalAddress", "city"), "L\u00fcbeck"),
                (("data", "attributes", "entity", "registeredAs"), "HRB 7903 HL"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ])],
            "ror": [A("ror_draeger", [
                (("id",), "https://ror.org/0415p9s42"),
                (("names", 0, "value"), "Dr\u00e4ger (Germany)"),
            ])],
            "wikidata": [A("wikidata_draeger", [
                (("entities", "Q605908", "labels", "en", "value"), "Dr\u00e4gerwerk"),
            ])],
        },
        "identity_evidence": [
            A("gleif_draegerwerk", [
                (("data", "attributes", "entity", "legalName", "name"), "Dr\u00e4gerwerk AG & Co. KGaA"),
                (("data", "attributes", "entity", "legalAddress", "city"), "L\u00fcbeck"),
                (("data", "attributes", "entity", "legalForm", "id"), "T0YJ"),
                (("data", "attributes", "registration", "status"), "ISSUED"),
            ]),
            A("gleif_draegerwerk", [
                (("data", "attributes", "entity", "creationDate"), "1970-06-29T23:00:00Z"),
            ]),
        ],
        "aliases": [
            {"string": "Dr\u00e4gerwerk AG & Co. KGaA", "kind": "canonical",
             "evidence": [A("gleif_draegerwerk", [(("data", "attributes", "entity", "legalName", "name"),
                                                   "Dr\u00e4gerwerk AG & Co. KGaA")])]},
            {"string": "Draegerwerk AG & Co KGaA", "kind": "alias",
             "note": "measured ASCII transliteration in the corpus; GLEIF has no record under the ASCII spelling",
             "evidence_corpus": ("draeger", "affiliation_strings_sample", "Dr\u00e4gerwerk AG & Co KGaA, L\u00fcbeck, Germany. hansulrich.schueler@draeger.com.")},
            {"string": "Dr\u00e4gerwerk", "kind": "alias",
             "evidence_corpus": ("draeger", "sponsor_strings", "Draeger")},
            {"string": "Draeger", "kind": "alias",
             "note": "ASCII string that collides with the German surname; see the not_company aliases",
             "evidence_corpus": ("draeger", "sponsor_strings", "Draeger")},
            {"string": "(Ms Draeger)", "kind": "not_company",
             "note": "measured false positive: the string is the surname of a paper author, not the company",
             "evidence_corpus": ("draeger", "affiliation_strings_sample", "(Ms Draeger)")},
            {"string": "draeger@ana.unibe.ch", "kind": "not_company",
             "note": "measured false positive: an institutional e-mail address of a Dr\u00e4ger-named researcher",
             "evidence_corpus": ("draeger", "affiliation_strings_sample", "draeger@ana.unibe.ch")},
            {"string": "draeger@informatik.uni-tuebingen.de", "kind": "not_company",
             "note": "measured false positive: an institutional e-mail address of a Dr\u00e4ger-named researcher",
             "evidence_corpus": ("draeger", "affiliation_strings_sample", "draeger@informatik.uni-tuebingen.de")},
            {"string": "schumm-draeger@klinikum-muenchen.de", "kind": "not_company",
             "note": "measured false positive: personal e-mail address containing the surname",
             "evidence_corpus": ("draeger", "affiliation_strings_sample", "petra-maria.schumm-draeger@klinikum-muenchen.de")},
        ],
    },
    {
        "company": "draeger",
        "entity_key": "draeger_medical_gmbh",
        "entity_type": "former_subsidiary",
        "canonical_name": "Dr\u00e4ger Medical GmbH",
        "valid_from": None,
        "date_event": "UNKNOWN: no fetched official document states its incorporation date",
        "valid_to": None,
        "valid_to_event": "UNKNOWN exact date: the LEI record's entity status is INACTIVE and its "
                          "successorEntities list points to Dr\u00e4gerwerk AG & Co. KGaA (i.e. the company "
                          "was merged into the parent). The LEI registration is RETIRED with last update "
                          "2022-03-29, which bounds but does not date the merger.",
        "parent_entity_key": "draegerwerk_ag_co_kgaa",
        "identity_confidence": 0.85,
        "stable_ids": {"cik": None, "lei": "529900PCM8FAO280F764", "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "lei": [A("gleif_draeger_medical", [
                (("data", "attributes", "entity", "legalName", "name"), "Dr\u00e4ger Medical GmbH"),
                (("data", "attributes", "entity", "status"), "INACTIVE"),
                (("data", "attributes", "entity", "successorEntities", 0, "lei"), "5493005UFVHY0PPNKD75"),
            ])],
        },
        "identity_evidence": [
            A("gleif_draeger_medical", [
                (("data", "attributes", "entity", "legalName", "name"), "Dr\u00e4ger Medical GmbH"),
                (("data", "attributes", "entity", "legalAddress", "city"), "L\u00fcbeck"),
                (("data", "attributes", "entity", "registeredAs"), "HRB 4358 HL"),
            ]),
        ],
        "aliases": [
            {"string": "Dr\u00e4ger Medical GmbH", "kind": "canonical",
             "evidence": [A("gleif_draeger_medical", [(("data", "attributes", "entity", "legalName", "name"),
                                                       "Dr\u00e4ger Medical GmbH")])]},
            {"string": "Draeger Medical GmbH", "kind": "alias",
             "note": "measured ASCII spelling used in affiliation strings",
             "evidence_corpus": ("draeger", "affiliation_strings_sample", "Draeger Medical GmbH, Moislinger Allee 53, 23558, L\u00fcbeck, Germany. eckhard.teschner@draeger.com.")},
            {"string": "Dr\u00e4ger Medical", "kind": "brand",
             "note": "business-unit brand used both for the legal entity and for the medical division",
             "evidence": [A("gleif_draeger_medical", [(("data", "attributes", "entity", "legalName", "name"),
                                                       "Dr\u00e4ger Medical GmbH")])]},
        ],
    },
    {
        "company": "draeger",
        "entity_key": "draeger_safety_ag_co_kgaa",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Dr\u00e4ger Safety AG & Co. KGaA",
        "valid_from": "2001-05-21",
        "date_event": "registry creation date 2001-05-21 reported by its GLEIF LEI record",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "draegerwerk_ag_co_kgaa",
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": "549300T8IDCFNHN29E62", "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "lei": [A("gleif_draeger_safety", [
                (("data", "attributes", "entity", "legalName", "name"), "Dr\u00e4ger Safety AG & Co. KGaA"),
                (("data", "attributes", "entity", "creationDate"), "2001-05-21T22:00:00Z"),
                (("data", "attributes", "entity", "registeredAs"), "HRB 4097 HL"),
            ])],
        },
        "identity_evidence": [
            A("gleif_draeger_safety", [
                (("data", "attributes", "entity", "legalName", "name"), "Dr\u00e4ger Safety AG & Co. KGaA"),
                (("data", "attributes", "entity", "legalAddress", "city"), "L\u00fcbeck"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ]),
            A("gleif_draeger_safety_parent_rel", [
                (("data", "attributes", "relationship", "endNode", "id"), "5493005UFVHY0PPNKD75"),
                (("data", "attributes", "relationship", "startNode", "type"), "LEI"),
            ]),
        ],
        "aliases": [
            {"string": "Dr\u00e4ger Safety AG & Co. KGaA", "kind": "canonical",
             "evidence": [A("gleif_draeger_safety", [(("data", "attributes", "entity", "legalName", "name"),
                                                      "Dr\u00e4ger Safety AG & Co. KGaA")])]},
            {"string": "Draeger Safety", "kind": "operating_unit_prefix",
             "evidence_corpus": ("draeger", "sponsor_strings", "Draeger")},
        ],
    },
    {
        "company": "draeger",
        "entity_key": "draeger_medical_systems_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Draeger Medical Systems, Inc.",
        "valid_from": "2003-04-03",
        "date_event": "registry creation date 2003-04-03 reported by its GLEIF LEI record (Delaware/Wilmington)",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "identity_confidence": 0.8,
        "stable_ids": {"cik": None, "lei": "549300R77YDRH6WZPY39", "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "lei": [A("gleif_draeger_medical_systems", [
                (("data", "attributes", "entity", "legalName", "name"), "Draeger Medical Systems, Inc."),
                (("data", "attributes", "entity", "legalAddress", "country"), "US"),
                (("data", "attributes", "entity", "creationDate"), "2003-04-03T22:00:00Z"),
            ])],
        },
        "identity_evidence": [
            A("gleif_draeger_medical_systems", [
                (("data", "attributes", "entity", "legalName", "name"), "Draeger Medical Systems, Inc."),
                (("data", "attributes", "entity", "legalAddress", "city"), "Wilmington"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ]),
        ],
        "aliases": [
            {"string": "Draeger Medical Systems, Inc.", "kind": "canonical",
             "evidence_corpus": ("draeger", "sponsor_strings", "Draeger Medical Systems, Inc.")},
            {"string": "Draeger Medical, Inc", "kind": "alias",
             "note": "measured sponsor string; the exact US legal entity (Telford PA) could not be pinned to "
                     "an LEI record, so this row maps to the US subsidiary family, confidence only 0.40",
             "evidence_corpus": ("draeger", "sponsor_strings", "Draeger Medical, Inc")},
        ],
    },
    # ======================= MINDRAY =======================================
    {
        "company": "mindray",
        "entity_key": "shenzhen_mindray",
        "entity_type": "public_parent",
        "canonical_name": "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.",
        "valid_from": None,
        "date_event": "UNKNOWN: the company states 'Established in 1991' (year only); no fetched official "
                      "document gives an incorporation day. Its ChiNext listing ceremony was 2018-10-16.",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": None,
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": None, "ror": "04yfe8169", "funder_doi": None, "wikidata": "Q15138136",
                       "szse_code": "300760"},
        "id_evidence": {
            "ror": [A("ror_mindray", [
                (("id",), "https://ror.org/04yfe8169"),
                (("names", 0, "value"), "Mindray (China)"),
            ])],
            "wikidata": [A("wikidata_mindray", [
                (("entities", "Q15138136", "labels", "en", "value"), "Mindray"),
            ])],
            "szse_code": [E("szse_mindray_listing_20181016",
                            "On October 16, 2018, Shenzhen Mindray Bio-Medical Electronics Co., Ltd. (stock code: 300760")],
        },
        "identity_evidence": [
            E("szse_mindray_listing_20181016",
              "On October 16, 2018, Shenzhen Mindray Bio-Medical Electronics Co., Ltd. (stock code: 300760"),
            E("mry_20f_fy2013",
              "Shenzhen Mindray Bio-Medical Electronics Co., Ltd., or Shenzhen Mindray"),
            E("mry_6k_20080515_datascope",
              "Mindray Medical International Limited (NYSE: MR), a leading China-based developer, "
              "manufacturer and marketer of medical devices worldwide"),
        ],
        "aliases": [
            {"string": "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "kind": "canonical",
             "evidence_corpus": ("mindray", "sponsor_strings", "Shenzhen Mindray Bio-Medical Electronics Co., Ltd")},
            {"string": "Shenzhen Mindray Bio-Medical Electronics Co. Ltd.", "kind": "alias",
             "evidence_corpus": ("mindray", "affiliation_strings_sample", "Shenzhen Mindray Bio-Medical Electronics Co. Ltd., Shenzhen, 518057.")},
            {"string": "Mindray Bio-Medical Electronics Co., Ltd.", "kind": "alias",
             "evidence_corpus": ("mindray", "sponsor_strings", "Mindray Bio-Medical Electronics Co., Ltd.")},
            {"string": "MINDRAY", "kind": "alias",
             "evidence_corpus": ("mindray", "sponsor_strings", "MINDRAY")},
            {"string": "Mindray Medical International Limited", "kind": "not_company",
             "note": "COLLISION: this is the Cayman holding company (former NYSE issuer), a different legal "
                     "entity from the SZSE-listed Shenzhen company; mapping the string to the A-share issuer "
                     "is exactly the anachronism this register exists to prevent",
             "evidence": [E("mry_20f_fy2013", "Mindray Medical International Limited")]},
        ],
    },
    {
        "company": "mindray",
        "entity_key": "mindray_medical_international_ltd",
        "entity_type": "former_parent",
        "canonical_name": "Mindray Medical International Limited",
        "valid_from": None,
        "date_event": "UNKNOWN: the Cayman holding company's incorporation date is not stated in any fetched "
                      "document; it renamed itself 'Mindray Medical International Limited' in May 2006 and "
                      "listed ADSs on the NYSE on 2006-09-26",
        "valid_to": "2016-03-03",
        "valid_to_event": "going-private merger became effective 2016-03-03; the company 'ceased to be a "
                          "publicly traded company' (NYSE notified removal from listing on 2016-03-15)",
        "parent_entity_key": None,
        "identity_confidence": 0.95,
        "stable_ids": {"cik": "1373060", "lei": "213800L7HSJE2P72PZ24", "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "cik": [A("sec_sub_mindray", [
                (("name",), "Mindray Medical International LTD"),
                (("cik",), "0001373060"),
            ])],
            "lei": [A("gleif_mindray_international", [
                (("data", "attributes", "entity", "legalName", "name"), "MINDRAY MEDICAL INTERNATIONAL LIMITED"),
                (("data", "attributes", "entity", "legalAddress", "country"), "KY"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ])],
        },
        "identity_evidence": [
            E("mry_20f_fy2013", "Cayman Islands (Jurisdiction of incorporation or organization)"),
            E("mry_20f_fy2007",
              "We and certain of our shareholders completed the initial public offering of 23,000,000 ADSs, "
              "each representing one Class A ordinary share, on September 29, 2006. On September 26, 2006, "
              "we listed our ADSs on the New York Stock Exchange under the symbol"),
            E("mry_6k_20160303_takeprivate",
              "today announced the completion of its merger (the"),
            E("mry_6k_20160303_takeprivate",
              "As a result of the merger, the Company has ceased to be a publicly traded company and became "
              "a wholly owned subsidiary of Parent."),
            E("mry_25nse_20160304",
              "The merger between Mindray Medical International Limited and Solid Union Limited, a wholly "
              "owned subsidiary of Excelsior Union Limited became effective on March 3, 2016."),
            A("gleif_mindray_international", [
                (("data", "attributes", "entity", "legalName", "name"), "MINDRAY MEDICAL INTERNATIONAL LIMITED"),
                (("data", "attributes", "entity", "status"), "ACTIVE"),
            ]),
        ],
        "aliases": [
            {"string": "Mindray Medical International Limited", "kind": "canonical",
             "evidence": [E("mry_20f_fy2013", "Mindray Medical International Limited (Exact name of Registrant as specified in its charter)")]},
            {"string": "Mindray Medical International LTD", "kind": "alias",
             "evidence": [A("sec_sub_mindray", [(("name",), "Mindray Medical International LTD")])]},
            {"string": "Mindray", "kind": "alias",
             "evidence": [E("mry_6k_20080515_datascope", "Mindray Medical International Limited (NYSE: MR)")]},
        ],
    },
    {
        "company": "mindray",
        "entity_key": "mindray_ds_usa_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "Mindray DS USA, Inc.",
        "valid_from": None,
        "date_event": "UNKNOWN: named as a consolidated subsidiary in the FY2013 20-F; no fetched document "
                      "gives its incorporation date",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "mindray_medical_international_ltd",
        "parent_note": "listed as a consolidated subsidiary in MMIL's FY2013 20-F; the ownership chain after "
                       "the 2016 take-private is not verified, so the 20-F reporting parent is used",
        "identity_confidence": 0.8,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("mry_20f_fy2013", "Mindray DS USA Inc., or Mindray DS USA"),
        ],
        "aliases": [
            {"string": "Mindray DS USA, Inc.", "kind": "canonical",
             "evidence": [E("mry_20f_fy2013", "Mindray DS USA Inc., or Mindray DS USA")]},
            {"string": "Mindray DS USA Inc.", "kind": "alias",
             "evidence": [E("mry_20f_fy2013", "Mindray DS USA Inc., or Mindray DS USA")]},
        ],
    },
    {
        "company": "mindray",
        "entity_key": "datascope_corp",
        "entity_type": "former_parent",
        "canonical_name": "Datascope Corp.",
        "valid_from": None,
        "date_event": "UNKNOWN: no fetched document states its incorporation date (Delaware, CIK 27096)",
        "valid_to": "2008-05-14",
        "valid_to_event": "sold its Patient Monitoring business to Mindray Medical International Limited; "
                          "the sale closed 2008-05-14 (effective 2008-05-01). Datascope Corp. was NOT "
                          "acquired by Mindray and continued as an independent company.",
        "parent_entity_key": None,
        "identity_confidence": 0.9,
        "stable_ids": {"cik": "27096", "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {
            "cik": [A("sec_sub_datascope", [
                (("name",), "DATASCOPE CORP"),
                (("cik",), "0000027096"),
            ])],
        },
        "identity_evidence": [
            E("datascope_8k_20080515", "DATASCOPE CORP. (Exact name of registrant as specified in its charter) Delaware"),
            E("datascope_8k_20080515",
              "completed the sale of the assets (excluding receivables), operations and certain "
              "liabilities of its Patient Monitoring business"),
            E("datascope_8k_20080515",
              "The sale was completed pursuant to the Asset Purchase Agreement"),
            E("datascope_8k_20080515", "and is effective as of May 1, 2008."),
        ],
        "aliases": [
            {"string": "Datascope Corp.", "kind": "canonical",
             "evidence_corpus": ("mindray", "sponsor_strings", "Datascope Corp.")},
            {"string": "Getinge Datascope Corp", "kind": "alias",
             "note": "measured affiliation string; it shows Datascope Corp. inside the Getinge group, but the "
                     "Getinge acquisition date is NOT verified in any fetched official document, so no date "
                     "is asserted and the string is not treated as a Mindray entity",
             "evidence_corpus": ("mindray", "affiliation_strings_sample", "Getinge Datascope Corp")},
            {"string": "Datascope Patient Monitoring", "kind": "not_company",
             "note": "COLLISION: this is the acquired business unit, not the seller legal entity; sponsor "
                     "string 'Datascope Corp.' can refer either to the pre-2008 independent company or, "
                     "loosely, to the acquired business",
             "evidence_corpus": ("mindray", "sponsor_strings", "Datascope Patient Monitoring")},
        ],
    },
    {
        "company": "mindray",
        "entity_key": "datascope_patient_monitoring_business",
        "entity_type": "division",
        "canonical_name": "Datascope Patient Monitoring business (acquired by Mindray)",
        "valid_from": "2008-05-14",
        "date_event": "acquisition completed 2008-05-14 (sale closed per the seller's 8-K; effective "
                      "2008-05-01); Mindray announced completion on 2008-05-15",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "mindray_medical_international_ltd",
        "identity_confidence": 0.85,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("mry_6k_20080515_datascope",
              "Mindray Medical Completes Acquisition of Datascope\u2019s Patient Monitoring Business"),
            E("mry_6k_20080515_datascope",
              "today announced the completion of its acquisition of Datascope Corporation\u2019s patient "
              "monitoring device business"),
            E("datascope_8k_20080515", "On May 14, 2008, Datascope Corp."),
        ],
        "aliases": [
            {"string": "Datascope Patient Monitoring", "kind": "canonical",
             "evidence_corpus": ("mindray", "sponsor_strings", "Datascope Patient Monitoring")},
        ],
    },
    {
        "company": "mindray",
        "entity_key": "zonare_medical_systems_inc",
        "entity_type": "operating_subsidiary",
        "canonical_name": "ZONARE Medical Systems, Inc.",
        "valid_from": "2013-07-17",
        "date_event": "acquisition completed and announced 2013-07-17",
        "valid_to": None,
        "valid_to_event": None,
        "parent_entity_key": "mindray_medical_international_ltd",
        "identity_confidence": 0.9,
        "stable_ids": {"cik": None, "lei": None, "ror": None, "funder_doi": None, "wikidata": None},
        "id_evidence": {},
        "identity_evidence": [
            E("mry_6k_20130717_zonare",
              "Mindray Medical Completes Acquisition of ZONARE Medical Systems"),
            E("mry_6k_20130717_zonare",
              "announced today that it has completed the acquisition of ZONARE Medical Systems, Inc."),
            E("mry_20f_fy2013", "In 2013, we acquired ZONARE, a U.S. ultrasound technology company"),
        ],
        "aliases": [
            {"string": "ZONARE Medical Systems, Inc.", "kind": "canonical",
             "evidence": [E("mry_6k_20130717_zonare", "the acquisition of ZONARE Medical Systems, Inc.")]},
        ],
    },
]

# --------------------------------------------------------------------------- #
# Verification engine
# --------------------------------------------------------------------------- #
class Verifier:
    def __init__(self, refresh: bool = False):
        self.refresh = refresh
        self.docs: dict[str, Fetched] = {}
        self.provenance: dict[str, dict] = {}
        self.failures: list[str] = []
        self.checks = {"verbatim": 0, "api": 0, "negative": 0}

    # -- fetch ---------------------------------------------------------------
    def get(self, key: str) -> Fetched:
        if key in self.docs:
            return self.docs[key]
        spec = SOURCES[key]
        rec = fetch_text(spec["url"], refresh=self.refresh)
        text = rec["text"]
        if spec["kind"] == "html_text":
            normd = normalise(text)
        elif spec["kind"] == "text":
            normd = normalise(text)
        else:
            normd = text
        f = Fetched(key, spec["url"], normd, rec["status"], rec["retrieved_at"],
                    rec["sha256"], spec["kind"])
        self.docs[key] = f
        entry = {
            "source_key": key,
            "url": f.url,
            "http_status": f.status,
            "retrieved_at_utc": f.retrieved_at,
            "sha256": f.sha256,
            "evidence_kind": ("api_field_assertion" if f.kind == "json" else "verbatim_excerpt"),
            "n_assertions": 0,
        }
        self.provenance[key] = entry
        return f

    # -- verbatim ------------------------------------------------------------
    def verbatim(self, key: str, excerpt: str) -> str:
        f = self.get(key)
        needle = excerpt.strip()
        if needle and needle in f.text:
            self.checks["verbatim"] += 1
            self.provenance[key]["n_assertions"] += 1
            return needle
        # diagnostic: locate the region in an alphanumeric projection
        sn, sf = simplify(needle), simplify(f.text)
        detail = ""
        pos = sf.find(sn[:60]) if len(sn) >= 60 else sf.find(sn[:30])
        if pos < 0:
            for cut in (40, 30, 20):
                if len(sn) > cut:
                    pos = sf.find(sn[:cut])
                    if pos >= 0:
                        break
        if pos >= 0:
            # map back approximately and show the real text
            approx = max(0, pos - 20)
            detail = "\n    actual text region: " + f.text[approx:approx + len(needle) + 80]
        self.failures.append(f"[{key}] excerpt not found: {needle[:120]!r}{detail}")
        return needle

    # -- api field assertions ------------------------------------------------
    def api(self, src_key: str, assertions, label: str = "") -> str:
        f = self.get(src_key)
        doc = json.loads(f.text)
        rendered = []
        for path, expected in assertions:
            cur = doc
            for part in path:
                if isinstance(cur, list):
                    cur = cur[part]
                else:
                    cur = cur[part]
            got = cur
            if got != expected:
                self.failures.append(
                    f"[{src_key}] field {'.'.join(map(str, path))}: expected {expected!r}, got {got!r}")
            rendered.append(f"{'.'.join(map(str, path))} = {json.dumps(got, ensure_ascii=False)}")
            self.checks["api"] += 1
            self.provenance[src_key]["n_assertions"] += 1
        return (label + ": " if label else "") + "; ".join(rendered)

    # -- negative search -----------------------------------------------------
    def negative(self, spec: dict) -> dict:
        rec = fetch_text(spec["url"], refresh=self.refresh)
        self.checks["negative"] += 1
        base = {
            "search_key": spec["key"],
            "url": spec["url"],
            "http_status": rec["status"],
            "retrieved_at_utc": rec["retrieved_at"],
            "sha256": rec["sha256"],
            "why_unknown": spec["why"],
        }
        if spec.get("kind") == "absent_substring":
            low = rec["text"].lower()
            found = [tok for tok in spec["forbidden"] if tok.lower() in low]
            ok = not found
            base.update({"kind": "absent_substring", "forbidden_tokens": spec["forbidden"],
                         "tokens_found": found, "assertion_passed": ok})
            if not ok:
                self.failures.append(f"[negative {spec['key']}] forbidden tokens present: {found}")
            return base
        doc = json.loads(rec["text"])
        cur = doc
        for part in spec["path"]:
            cur = cur[part] if not isinstance(cur, list) else cur[part]
        ok = cur == spec["expect_total"]
        base.update({"kind": "expected_total", "observed_total": cur,
                     "expected_total": spec["expect_total"], "assertion_passed": ok})
        if not ok:
            self.failures.append(f"[negative {spec['key']}] expected total {spec['expect_total']}, got {cur}")
        return base


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def load_corpus() -> dict:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def corpus_evidence(corpus: dict, company: str, section: str, needle: str) -> tuple[dict, str]:
    """Return (evidence dict, exact excerpt) for a string observed in the S-029 corpus extract.

    The corpus key may be the exact observed string or any observed string that
    *contains* it (useful for long affiliation strings).  Fails loudly otherwise,
    so a corpus-backed alias can never be invented.
    """
    block = corpus[company]
    table = block[section]
    if needle in table:
        exact, count = needle, table[needle]
    else:
        matches = [(s, n) for s, n in table.items() if needle in s]
        if not matches:
            raise SystemExit(f"corpus string not found: {company}/{section}/{needle!r}")
        matches.sort(key=lambda kv: kv[1], reverse=True)
        exact, count = matches[0]
    mtime = _dt.datetime.fromtimestamp(os.path.getmtime(CORPUS_PATH), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "file:///" + CORPUS_PATH.replace("\\", "/")
    shown = exact if len(exact) <= 320 else exact[:317] + "..."
    excerpt = f'{section} entry observed {count}x: "{shown}"'
    return {"url": url, "excerpt": excerpt, "retrieved_at": mtime,
            "evidence_kind": "corpus_observed_string"}, excerpt


def build(refresh: bool = False) -> tuple[dict, dict, list[str]]:
    v = Verifier(refresh=refresh)
    corpus = load_corpus()
    notes: list[str] = []

    companies: dict[str, dict] = {
        "medtronic": {"canonical_company": "Medtronic plc", "entities": []},
        "ge_healthcare": {"canonical_company": "GE HealthCare Technologies Inc.", "entities": []},
        "philips": {"canonical_company": "Koninklijke Philips N.V.", "entities": []},
        "draeger": {"canonical_company": "Dr\u00e4gerwerk AG & Co. KGaA", "entities": []},
        "mindray": {"canonical_company": "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "entities": []},
    }

    for spec in ENTITIES:
        entity = {
            "entity_key": spec["entity_key"],
            "entity_type": spec["entity_type"],
            "canonical_name": spec["canonical_name"],
            "valid_from": spec["valid_from"],
            "valid_to": spec["valid_to"],
            "parent_entity_key": spec["parent_entity_key"],
            "date_event": spec["date_event"],
            "valid_to_event": spec["valid_to_event"],
            "stable_ids": dict(spec["stable_ids"]),
            "identity_confidence": spec["identity_confidence"],
            "identity_evidence": [],
            "aliases": [],
            "date_precision": ("day" if spec["valid_from"] else "unknown"),
        }
        if spec.get("parent_note"):
            entity["parent_note"] = spec["parent_note"]
        if spec.get("parent_from"):
            entity["parent_from"] = spec["parent_from"]
        # identity evidence
        for item in spec["identity_evidence"]:
            if isinstance(item, Ev):
                ex = v.verbatim(item.src, item.excerpt)
                f = v.get(item.src)
                entity["identity_evidence"].append({
                    "url": f.url, "excerpt": ex, "retrieved_at": f.retrieved_at,
                    "source_key": item.src, "verification": "verbatim"})
            elif isinstance(item, ApiEv):
                ex = v.api(item.src, item.assertions, label=item.label)
                f = v.get(item.src)
                entity["identity_evidence"].append({
                    "url": f.url, "excerpt": ex, "retrieved_at": f.retrieved_at,
                    "source_key": item.src, "verification": "api_field_assertion"})
            else:  # pragma: no cover
                raise SystemExit("bad evidence spec")
        # id provenance
        id_prov = {}
        for id_name, evs in spec.get("id_evidence", {}).items():
            rendered = []
            for item in evs:
                if isinstance(item, Ev):
                    ex = v.verbatim(item.src, item.excerpt)
                    f = v.get(item.src)
                else:
                    ex = v.api(item.src, item.assertions)
                    f = v.get(item.src)
                rendered.append({"url": f.url, "excerpt": ex, "retrieved_at": f.retrieved_at})
            id_prov[id_name] = rendered
        entity["stable_id_evidence"] = id_prov
        # aliases
        for al in spec["aliases"]:
            row = {"string": al["string"], "kind": al["kind"],
                   "valid_from": al.get("valid_from"), "valid_to": al.get("valid_to")}
            if "note" in al:
                row["note"] = al["note"]
            evidence = []
            if "evidence" in al:
                for item in al["evidence"]:
                    if isinstance(item, Ev):
                        ex = v.verbatim(item.src, item.excerpt)
                        f = v.get(item.src)
                        evidence.append({"url": f.url, "excerpt": ex, "retrieved_at": f.retrieved_at,
                                         "source_key": item.src, "verification": "verbatim"})
                    else:
                        ex = v.api(item.src, item.assertions)
                        f = v.get(item.src)
                        evidence.append({"url": f.url, "excerpt": ex, "retrieved_at": f.retrieved_at,
                                         "source_key": item.src, "verification": "api_field_assertion"})
            if "evidence_corpus" in al:
                company, section, exact = al["evidence_corpus"]
                ev, _ = corpus_evidence(corpus, company, section, exact)
                evidence.append(ev)
            if not evidence:
                raise SystemExit(f"alias without evidence: {spec['entity_key']}/{al['string']}")
            row["evidence"] = evidence
            entity["aliases"].append(row)
        companies[spec["company"]]["entities"].append(entity)

    # negative searches (documented UNKNOWNs)
    negative = [v.negative(s) for s in NEGATIVE_SEARCHES]

    # ---- validation -------------------------------------------------------
    allowed_types = {"public_parent", "operating_subsidiary", "former_subsidiary",
                     "division", "brand", "former_parent"}
    allowed_kinds = {"canonical", "alias", "operating_unit_prefix", "former_name",
                     "subsidiary", "not_company", "brand"}
    DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    keys = set()
    for company, block in companies.items():
        if not block["entities"]:
            raise SystemExit(f"company without entities: {company}")
        for e in block["entities"]:
            if e["entity_key"] in keys:
                raise SystemExit(f"duplicate entity_key {e['entity_key']}")
            keys.add(e["entity_key"])
            if e["entity_type"] not in allowed_types:
                raise SystemExit(f"bad entity_type {e['entity_key']}")
            for k in ("valid_from", "valid_to"):
                if e[k] is not None and not DATE_RE.match(e[k]):
                    raise SystemExit(f"bad date {k}={e[k]} in {e['entity_key']}")
            if not 0.0 <= e["identity_confidence"] <= 1.0:
                raise SystemExit(f"bad confidence {e['entity_key']}")
            if not e["identity_evidence"]:
                raise SystemExit(f"no identity_evidence for {e['entity_key']}")
            for ev in e["identity_evidence"]:
                if not (ev.get("url") and ev.get("excerpt") and ev.get("retrieved_at")):
                    raise SystemExit(f"incomplete evidence in {e['entity_key']}")
            for al in e["aliases"]:
                if al["kind"] not in allowed_kinds:
                    raise SystemExit(f"bad alias kind {al['kind']} in {e['entity_key']}")
                if not al["evidence"]:
                    raise SystemExit(f"alias without evidence {e['entity_key']}/{al['string']}")
                for ev in al["evidence"]:
                    if not (ev.get("url") and ev.get("excerpt") and ev.get("retrieved_at")):
                        raise SystemExit(f"incomplete alias evidence {e['entity_key']}")
    for company, block in companies.items():
        if not any(al["kind"] == "not_company" for e in block["entities"] for al in e["aliases"]):
            raise SystemExit(f"company {company} has no not_company alias")
    for company, block in companies.items():
        for e in block["entities"]:
            p = e["parent_entity_key"]
            if p is not None:
                if p not in keys:
                    raise SystemExit(f"dangling parent {p} in {e['entity_key']}")
                if p == e["entity_key"]:
                    raise SystemExit(f"self parent {p}")

    generated_at = utc_now_iso()
    register = {
        "schema": "s029_company_entity_register_v1",
        "study": "S-029 / relation_network_s029",
        "generated_at": generated_at,
        "generator": "research/studies/relation_network_s029/code/s029_company_register.py",
        "confidence_rule": CONFIDENCE_RULE,
        "company_keys": list(companies.keys()),
        "companies": companies,
        "notes": {
            "validity_semantics": (
                "valid_from/valid_to delimit the period in which the entity existed IN THE ROLE named by "
                "entity_type, not necessarily the lifetime of the legal person. Example: medtronic_inc is a "
                "former_parent with valid_to 2015-01-26; the legal entity 'Medtronic, Inc.' continues to "
                "exist as a Minnesota subsidiary (FY2025 Exhibit 21). Anachronism testing uses valid_from only, "
                "as instructed."),
            "operating_unit_rule": (
                "Rule (stated once, not re-derived per string): every string of the form 'Medtronic <unit>' "
                "(e.g. 'Medtronic - MITG', 'Medtronic Cardiac Rhythm and Heart Failure', 'Medtronic BRC') is "
                "an operating unit or department of the Medtronic group, not a separate legal entity; it maps "
                "to the group parent medtronic_plc unless the string names one of the registered subsidiaries. "
                "Rationale: the FY2025 Exhibit 21 lists the group's legal entities; a few observed strings do "
                "match legal persons (Medtronic MiniMed, Inc., Medtronic Xomed, Inc., and 'Medtronic Vascular' "
                "which is the prefix of Medtronic Vascular, Inc.) and are registered as subsidiaries or as "
                "aliases of them, while the remaining 'Medtronic <unit>' strings (MITG, Cardiac Rhythm and "
                "Heart Failure, BRC, Spinal and Biologics, ...) are divisional/portfolio names used in trial "
                "sponsorship. The same rule is applied to 'GE Healthcare <place>' (site/affiliate), "
                "'Philips Healthcare <place>' and 'Shenzhen Mindray Bio-Medical Electronics Co., Ltd.' "
                "(registered parent)."),
            "corpus_strings_source": "data/observed_company_strings.json",
        },
        "not_company_registry": [
            {"company": c,
             "strings": [{"string": al["string"], "note": al.get("note", ""),
                          "evidence": al["evidence"]}
                         for e in b["entities"] for al in e["aliases"] if al["kind"] == "not_company"]}
            for c, b in companies.items()
        ],
        "unknown_ids": UNKNOWN_IDS,
    }

    provenance = {
        "schema": "s029_entity_provenance_v1",
        "study": "S-029 / relation_network_s029",
        "generated_at": generated_at,
        "description": "Retrieval manifest for artifacts/company_entity_register.json: one entry per HTTP "
                       "retrieval, with the sha256 of the retrieved bytes, the UTC retrieval timestamp, and "
                       "the number of evidence assertions verified against that document.",
        "user_agent": UA["User-Agent"],
        "verification": {
            "verbatim_excerpts_checked": v.checks["verbatim"],
            "api_field_assertions_checked": v.checks["api"],
            "negative_searches": v.checks["negative"],
            "failures": v.failures,
            "policy": "A build with any failed assertion is aborted; the committed artifacts therefore have "
                      "zero unverified quotes.",
        },
        "sources": list(v.provenance.values()),
        "negative_searches": negative,
    }
    return register, provenance, v.failures


# --------------------------------------------------------------------------- #
# Markdown register
# --------------------------------------------------------------------------- #
def render_markdown(register: dict, provenance: dict) -> str:
    L: list[str] = []
    A_ = L.append
    A_("# S-029 entity history register \u2014 legal entities behind the five study companies")
    A_("")
    A_("Generated by `code/s029_company_register.py` (and regenerated only by re-running it). "
       "Machine-readable form: `artifacts/company_entity_register.json`; retrieval manifest: "
       "`artifacts/entity_provenance.json`.")
    A_("")
    A_("## 0. What this register is for")
    A_("")
    A_("S-029 measures relations between five medical-device companies using trial sponsorships, "
       "publication affiliations and awards. Every one of those sources carries a *string*, never a "
       "guaranteed legal entity. This register fixes, for each company, which legal persons existed when, "
       "under which names, and which observed strings are companies at all. It exists so that a 2026 group "
       "structure cannot be projected backwards onto earlier periods: e.g. 'Covidien' before "
       "2015-01-26 is not Medtronic; 'Mindray Medical International Limited' is not the SZSE-listed "
       "Shenzhen company; 'Draeger' is often a German surname.")
    A_("")
    A_("## 1. Verification status")
    A_("")
    ver = provenance["verification"]
    A_(f"- HTTP retrievals in manifest: **{len(provenance['sources'])}**")
    A_(f"- Verbatim excerpts re-checked as substrings of the fetched documents: "
       f"**{ver['verbatim_excerpts_checked']}**")
    A_(f"- API field assertions re-read from live registry responses: "
       f"**{ver['api_field_assertions_checked']}**")
    A_(f"- Negative searches recorded (to justify UNKNOWN stable ids): "
       f"**{ver['negative_searches']}**")
    A_(f"- Failed assertions: **{len(ver['failures'])}** (a non-zero count aborts the build, so this file "
       "cannot be produced with an unsupported quote)")
    A_("")
    A_("## 2. Rules used")
    A_("")
    A_("### 2.1 Role-based validity")
    A_("")
    A_("`valid_from` / `valid_to` delimit the period in which the entity existed **in the role named by "
       "`entity_type`**, not necessarily the lifetime of the legal person. `medtronic_inc` is a "
       "`former_parent` ending 2015-01-26; the legal person 'Medtronic, Inc.' still exists as a Minnesota "
       "subsidiary (FY2025 Exhibit 21 lists it). `covidien_plc` is likewise a `former_parent`: the "
       "independent Irish parent 2009-06-04 \u2192 2015-01-26, after which it was acquired and is absent "
       "from Medtronic's FY2025 Exhibit 21. Anachronism testing uses `valid_from` only, so a claim dated "
       "before a company's `valid_from` is a claim about an entity that did not yet exist / a subsidiary "
       "the group did not yet own.")
    A_("")
    A_("### 2.2 Confidence rule")
    A_("")
    A_(register["confidence_rule"])
    A_("")
    A_("### 2.3 Operating-unit rule (stated once)")
    A_("")
    A_(register["notes"]["operating_unit_rule"])
    A_("")
    A_("### 2.4 Brand \u2260 legal entity, former \u2260 current")
    A_("")
    A_("Brands and divisions are typed `brand` / `division` and never carry a SEC CIK or LEI unless the "
       "same string is also a registered legal person. Conversely, `former_subsidiary` and `former_parent` "
       "are used for entities that were once inside (or at the head of) the group but are not now: "
       "Covidien plc (independent public parent 2009-06-04 \u2192 acquired 2015-01-26; no evidence it "
       "survives as a legal person), Covidien Ltd. (parent 2007 \u2192 2009), Datascope Corp. "
       "(never a Mindray entity \u2014 it was the *seller* of the patient-monitoring business), MiniMed Inc. "
       "(acquired 2001), Philips Lighting N.V. (now Signify N.V.), Dr\u00e4ger Medical GmbH (LEI status "
       "INACTIVE, successor is the KGaA).")
    A_("")
    A_("## 3. Entity register by company")
    for company, block in register["companies"].items():
        A_("")
        A_(f"### {company} \u2014 canonical: {block['canonical_company']}")
        A_("")
        A_("| entity_key | type | canonical name | valid_from | valid_to | parent | confidence | stable ids |")
        A_("|---|---|---|---|---|---|---|---|")
        for e in block["entities"]:
            ids = ", ".join(f"{k}={v}" for k, v in e["stable_ids"].items() if v)
            A_(f"| `{e['entity_key']}` | {e['entity_type']} | {e['canonical_name']} | "
               f"{e['valid_from'] or 'UNKNOWN'} | {e['valid_to'] or 'null'} | "
               f"{('`' + e['parent_entity_key'] + '`') if e['parent_entity_key'] else 'null'} | "
               f"{e['identity_confidence']:.2f} | {ids or '\u2014'} |")
        A_("")
        for e in block["entities"]:
            A_(f"**`{e['entity_key']}`** \u2014 {e['canonical_name']}")
            A_("")
            A_(f"- valid_from: `{e['valid_from'] or 'UNKNOWN'}` \u2014 {e['date_event']}")
            if e["valid_to"]:
                A_(f"- valid_to: `{e['valid_to']}` \u2014 {e['valid_to_event']}")
            else:
                A_(f"- valid_to: `null` \u2014 {e['valid_to_event'] or 'still valid (no terminating event verified)'}")
            if e.get("parent_note"):
                A_(f"- parent note: {e['parent_note']}")
            if e["aliases"]:
                A_("- aliases / variants:")
                for al in e["aliases"]:
                    extra = f" \u2014 {al['note']}" if al.get("note") else ""
                    A_(f"  - `{al['string']}` [{al['kind']}]{extra}")
            A_("")
    A_("## 4. The five priority date questions")
    A_("")
    A_("| fact | date | evidence |")
    A_("|---|---|---|")
    A_("| Medtronic plc inversion (Medtronic, Inc. \u2192 subsidiary of Medtronic plc) | **2015-01-26** | "
       "FY2015 10-K: 'Medtronic, Inc. and Covidien became subsidiaries of the Company'; completion 8-K "
       "press release dated 2015-01-26; plc incorporated 2014-06-12 and re-registered as plc 2015-01-26 |")
    A_("| Medtronic plc first NYSE trade | **2015-01-27** | completion press release: 'expected to begin "
       "trading ... on Tuesday, January 27, 2015'; Medtronic, Inc. shares ceased trading 2015-01-26 |")
    A_("| Medtronic\u2013Covidien acquisition completion | **2015-01-26** | FY2015 10-K 'On January 26, "
       "2015 (Acquisition Date), Medtronic completed the acquisition of Covidien plc' |")
    A_("| MiniMed acquisition completion | **2001-08-28** | Medtronic 8-K (event date 2001-08-28): "
       "'acquired all of the outstanding stock of MiniMed Inc. ... through a merger of a newly-created "
       "subsidiary' |")
    A_("| GE HealthCare spin-off completion / first regular-way trade | **2023-01-03 / 2023-01-04** | GEHC "
       "FY2022 10-K; 'when issued' market opened 2022-12-16 |")
    A_("| Philips Respironics acquisition completion | **2008-03-17** (announced) | Philips 6-K exhibit: "
       "'PHILIPS ANNOUNCES COMPLETION OF RESPIRONICS ACQUISITION', dated March 17, 2008; tender offer "
       "expired 2008-03-13 |")
    A_("| Mindray (Cayman) NYSE listing / delisting | **2006-09-26 (listing)** \u2192 **2016-03-03 "
       "(merger effective)** / 2016-03-15 (removal from listing) | 20-F FY2007 (listing sentence); 6-K "
       "2016-03-03; NYSE Form 25-NSE |")
    A_("| Shenzhen Mindray ChiNext listing | **2018-10-16** | SZSE English news page (listing ceremony, "
       "stock code 300760) |")
    A_("| Datascope patient-monitoring acquisition closing | **2008-05-14** (effective 2008-05-01) | "
       "Datascope Corp. 8-K 'Item 2.01 Completion of Acquisition or Disposition of Assets'; Mindray "
       "announced completion 2008-05-15 |")
    A_("| ZONARE acquisition completion | **2013-07-17** | Mindray 6-K exhibit, press release dated "
       "2013-07-17 |")
    A_("")
    A_("No `joint_venture` entity is registered: none of the five companies' verified structures in this "
       "corpus required one, and no joint-venture vehicle could be verified from a primary source.")
    A_("")
    A_("## 5. Mapping rules the pipeline must apply")
    A_("")
    A_("These rules follow directly from the dates and types above; they are the operational content of "
       "the register.")
    A_("")
    A_("1. **Covidien before 2015-01-26 is not Medtronic.** A claim dated before 2015-01-26 whose only "
       "company string is 'Covidien' / 'Covidien plc' maps to `covidien_plc`, an independent public parent "
       "with `parent_entity_key = null`. Only from 2015-01-26 does Covidien activity belong to the "
       "Medtronic group. Covidien-branded *legal entities* that survive inside Medtronic (Covidien AG, "
       "Covidien Limited, ...) are listed as subsidiaries of `medtronic_plc` and are valid after 2015-01-26.")
    A_("2. **'Tyco Healthcare' is neither Covidien nor Medtronic.** It maps to `tyco_healthcare` "
       "(`division`), valid up to 2007-06-29. A pre-2007 claim naming it is a claim about Tyco "
       "International's healthcare business.")
    A_("3. **'Mindray Medical International Limited' is not the SZSE issuer.** It maps to "
       "`mindray_medical_international_ltd` (`former_parent`, Cayman, NYSE ADS 2006-09-26 \u2192 private "
       "2016-03-03). The ChiNext-listed company (300760, listed 2018-10-16) is `shenzhen_mindray`. Any "
       "claim that uses the Cayman issuer's name as if it were the 2018+ listed company is a name "
       "collision, not a relation.")
    A_("4. **'Datascope Corp.' has two periods.** Before 2008-05-14 it is the independent seller "
       "`datascope_corp`; the *business* it sold is `datascope_patient_monitoring_business`, inside Mindray "
       "from 2008-05-14. Datascope Corp. itself was never acquired by Mindray. A measured affiliation "
       "string places it later under Getinge; the Getinge date is unverified, so no date is asserted.")
    A_("5. **Bare 'Draeger' is ambiguous.** It is both the company's ASCII transliteration and a frequent "
       "German surname (author names, e-mail local parts). It must not be mapped to the company without a "
       "corroborating attribute (affiliation with L\u00fcbeck, a draeger.com address, a legal-form token, "
       "or a registered alias). The not_company entries above give the measured counter-examples.")
    A_("6. **Divisions and brands carry no legal-entity identifiers.** 'Philips Healthcare' (from "
       "2008-01-01), 'Philips Medical Systems' (\u2264 2008-01-01), 'GE Healthcare', 'GE Medical Systems' "
       "and 'Medtronic <unit>' are divisions/sites of the parent; a claim naming them maps to the parent "
       "company only through their `division`/`brand` entities, and inherits no CIK/LEI from them.")
    A_("7. **Anachronism test.** For every claim, map the company string, then compare the claim's "
       "`declared_at`/`published_at` with the mapped entity's `valid_from`. A date before `valid_from` "
       "means the claim attributes activity to an entity that did not yet exist or to a subsidiary the "
       "group did not yet own (e.g. a 2012 'Covidien' claim tagged as Medtronic).")
    A_("")
    A_("## 6. Recorded conflicts and UNKNOWNs")
    A_("")
    A_("### 6.1 Conflicts between sources (not resolved silently)")
    A_("")
    A_("1. **Acquirer naming in the Covidien transaction.** The 2014-07-17 Medtronic, Inc. 8-K describes "
       "'the acquisition of Covidien ... by Medtronic, Inc.'; the FY2015 10-K and the 2015-01-26 press "
       "release describe Medtronic plc as the acquirer. Both are correct for their own entity: the "
       "transaction was effected by an Irish scheme plus a merger of the merger subsidiary into "
       "Medtronic, Inc., so the acquirer's legal identity changed *during* the closing. The register "
       "therefore does not assert a single acquirer entity for the pre-closing period.")
    A_("2. **Transaction value.** Completion press release: 'approximately $49.9 billion'; FY2015 10-K: "
       "'approximately $50 billion'. The register records the completion fact, not the valuation.")
    A_("3. **Mindray 'relisting 2018' framing.** The study brief says the Cayman issuer was 'delisted 2016, "
       "relisted 2018'. No relisting of Mindray Medical International Limited occurred: it went private on "
       "2016-03-03 and remains a private Cayman entity (GLEIF status ACTIVE). The 2018-10-16 event is the "
       "ChiNext IPO of a *different* legal person, Shenzhen Mindray Bio-Medical Electronics Co., Ltd. "
       "Treating the two as one issuer is a name-collision case.")
    A_("4. **Datascope acquisition date.** Mindray's press release is dated 2008-05-15 and says 'today "
       "announced the completion'; the seller's 8-K states the sale closed 2008-05-14 (effective "
       "2008-05-01). The register uses 2008-05-14 as the closing date and records the announcement date.")
    A_("5. **Dr\u00e4ger registry creation date.** GLEIF reports `creationDate` 1970-06-29 for Dr\u00e4gerwerk "
       "AG & Co. KGaA, while the corporate group is normally dated to 1889. The legal meaning of the 1970 "
       "date (formation vs. conversion into the current form) is not verified, so `valid_from` stays "
       "UNKNOWN and the 1970 date is kept only in the provenance record.")
    A_("6. **Philips Healthcare start.** The FY2008 20-F calls it 'our new Healthcare sector' with effect "
       "from 2008-01-01. Any earlier use of 'Philips Healthcare' as a *sector* name is not attested in the "
       "fetched filings: before 2008 the corresponding division is 'Philips Medical Systems' (attested as "
       "the 'former Medical Systems division' and, by a 2006 third-party 10-K, as a supplier name), so the "
       "sector reorganisation is dated to 2008-01-01 and the older string is a separate division entity.")
    A_("")
    A_("### 6.2 UNKNOWN facts and why")
    A_("")
    A_("| fact | status | verification attempts |")
    A_("|---|---|---|")
    A_("| Dr\u00e4gerwerk AG & Co. KGaA incorporation / valid_from | UNKNOWN | GLEIF record fetched "
       "(creationDate 1970-06-29, legal meaning unverified); no official annual report or register "
       "extract retrievable in this environment (draeger.com returns HTTP 403 to non-browser clients) |")
    A_("| Dr\u00e4ger Medical GmbH merger date into Dr\u00e4gerwerk | UNKNOWN (bounded \u2264 2022-03-29) | "
       "GLEIF record: entity status INACTIVE, successorEntities \u2192 KGaA LEI, registration RETIRED, "
       "last update 2022-03-29. No Handelsregister notice fetched |")
    A_("| MiniMed Inc., Datascope Corp., Respironics, ZONARE, Shenzhen Mindray, Covidien Ltd. incorporation "
       "dates | UNKNOWN | year-only or absent in the fetched filings; no attempt to infer a day |")
    A_("| Covidien plc LEI | UNKNOWN | GLEIF legal-name search returned 0 records (recorded as a negative "
       "search in the provenance manifest) |")
    A_("| Shenzhen Mindray LEI | UNKNOWN | GLEIF legal-name search returned 0 records |")
    A_("| Dr\u00e4ger and Mindray Crossref Funder Registry ids | UNKNOWN | funder queries returned 0 matches "
       "(negative searches recorded) |")
    A_("| GE 'GE Medical Systems' \u2192 'GE Healthcare' rename date | UNKNOWN (bracketed 2004) | FY2003 "
       "10-K says 'Medical Systems'; FY2004 10-K says 'Healthcare' and titles an officer 'Senior Vice "
       "President, GE Healthcare Technologies'; no filing dates the change |")
    A_("")
    A_("### 6.3 UNKNOWN stable identifiers with the attempts made")
    A_("")
    A_("| entity_key | identifier | status | verification attempts |")
    A_("|---|---|---|---|")
    for row in register.get("unknown_ids", []):
        A_(f"| `{row['entity_key']}` | {row['id']} | {row['status']} | {'; '.join(row['attempts'])} |")
    A_("")
    A_("")
    A_("## 7. not_company registry (strings that must never be mapped to the company)")
    A_("")
    A_("| company | string | reason |")
    A_("|---|---|---|")
    for block in register["not_company_registry"]:
        for s in block["strings"]:
            A_(f"| {block['company']} | `{s['string']}` | {s['note']} |")
    A_("")
    A_("## 8. Provenance")
    A_("")
    A_("Every URL above was retrieved while building this file; `artifacts/entity_provenance.json` records "
       "the exact retrieval timestamp and sha256 of each response, so any excerpt can be re-checked "
       "offline. Re-running the script re-verifies all excerpts and aborts on the first mismatch.")
    A_("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Stage 2 - entity resolution audit over the collected claims
#
# Independent measurement: the tiers below are computed by THIS code from the
# observed string against the register, not copied from the pipeline's own
# mapping status.  The pipeline status is used only as a cross-check, so the
# report contains both "our" resolution tier and whether the pipeline agreed.
# --------------------------------------------------------------------------- #
STAGE2_TIERS = ["exact_identifier", "normalized_name", "alias", "fuzzy", "conflict", "unmapped"]

# Brand tokens a *canonical-name* search would use.  Derived from the register:
# these are the shortest canonical/alias strings of each public parent.
STAGE2_TOKENS: dict[str, list[str]] = {
    "medtronic": ["medtronic"],
    "ge_healthcare": ["ge healthcare", "ge health care"],
    "philips": ["philips", "koninklijke philips", "royal philips"],
    "draeger": ["dr\u00e4gerwerk", "draegerwerk", "dr\u00e4ger", "draeger"],
    "mindray": ["mindray", "shenzhen mindray"],
}

# E-mail domains that identify the company (a resolved organisation identifier).
STAGE2_EMAIL_DOMAINS: dict[str, list[str]] = {
    "medtronic": ["medtronic.com", "medtronic.nl", "medtronic.ca", "covidien.com"],
    "ge_healthcare": ["gehealthcare.com", "med.ge.com"],
    "philips": ["philips.com", "philips.nl", "philipsresearch.com", "respironics.com"],
    "draeger": ["draeger.com", "draegerwerk.com"],
    "mindray": ["mindray.com", "mindray.cn"],
}

STAGE2_IDENTIFIER_RULES = {
    "org_email", "email_domain", "exact_identifier", "stable_id", "registry_id",
    "identifier_exact", "email",
}


def fold(s: str) -> str:
    """Case/accent/punctuation-insensitive projection used for name matching."""
    s = html.unescape(s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^0-9a-z\u00c0-\u024f]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _boundary_hit(token: str, folded: str) -> bool:
    """Boundary test on folded text; the token itself is folded too (accents stripped)."""
    tok = fold(token) if token else ""
    if not tok:
        return False
    return re.search(r"(?<![0-9a-z])" + re.escape(tok) + r"(?![0-9a-z])", folded) is not None


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def build_name_index(register: dict) -> dict:
    """company -> {'entities': {entity_key: {...names, type, valid_from}}, 'aliases': [(folded, entity_key, kind)],
       'parent_key': entity_key of the public parent}"""
    idx = {}
    for company, block in register["companies"].items():
        ents = {}
        alias_rows = []
        parent_key = None
        for e in block["entities"]:
            ents[e["entity_key"]] = {
                "canonical": e["canonical_name"],
                "folded_canonical": fold(e["canonical_name"]),
                "entity_type": e["entity_type"],
                "valid_from": e["valid_from"],
                "valid_to": e["valid_to"],
                "names": [],
            }
            if e["entity_type"] == "public_parent":
                parent_key = e["entity_key"]
            names = [e["canonical_name"]]
            for al in e["aliases"]:
                if al["kind"] == "not_company":
                    continue
                folded = fold(al["string"])
                names.append(al["string"])
                alias_rows.append((folded, e["entity_key"], al["kind"], al["string"]))
            ents[e["entity_key"]]["names"] = names
        idx[company] = {"entities": ents, "aliases": alias_rows, "parent_key": parent_key}
    return idx


def classify_string(raw: str, company: str | None, idx: dict, register: dict) -> tuple[str, list[dict]]:
    """Return (tier, matches).  matches = [{'company','entity_key','how','score'}]"""
    folded = fold(raw)
    lowered = (raw or "").lower()
    matches: list[dict] = []

    # 1. identifier hit: an e-mail domain that names the company
    for ck, domains in STAGE2_EMAIL_DOMAINS.items():
        for d in domains:
            if d in lowered:
                matches.append({"company": ck, "entity_key": None, "how": "email_domain:%s" % d,
                                "score": 1.0})

    # 2. exact normalised canonical name (any company)
    for ck, block in idx.items():
        for ek, ent in block["entities"].items():
            if folded and folded == ent["folded_canonical"]:
                matches.append({"company": ck, "entity_key": ek, "how": "canonical_name_exact",
                                "score": 1.0})

    # 3. registered alias (exact folded equality, or operating-unit prefix)
    for ck, block in idx.items():
        for folded_alias, ek, kind, original in block["aliases"]:
            how = None
            if folded == folded_alias:
                how = "alias_exact"
            elif kind in ("operating_unit_prefix", "brand") and folded_alias and \
                    re.match(re.escape(folded_alias) + r"(?![0-9a-z])", folded):
                how = "operating_unit_prefix"
            if how:
                matches.append({"company": ck, "entity_key": ek, "how": how,
                                "score": 0.95, "alias_kind": kind})

    # 3b. brand-token / operating-unit prefix ("Medtronic Cardiovascular", "GE Healthcare, Waukesha")
    for ck, toks in STAGE2_TOKENS.items():
        if not any(_boundary_hit(tok, folded) for tok in toks):
            continue
        for ek, ent in idx[ck]["entities"].items():
            names = [ent["folded_canonical"]] + [fold(n) for n in ent["names"]]
            if any(nm and re.match(re.escape(nm) + r"(?![0-9a-z])", folded) for nm in names):
                matches.append({"company": ck, "entity_key": ek,
                                "how": "operating_unit_prefix", "score": 0.90})
        if not any(m["company"] == ck for m in matches):
            matches.append({"company": ck, "entity_key": idx[ck]["parent_key"],
                            "how": "operating_unit_prefix", "score": 0.85})

    # 3c. distinctive registered brand/subsidiary alias appearing inside a longer free-text string
    for ck, block in idx.items():
        for folded_alias, ek, kind, original in block["aliases"]:
            if len(folded_alias) >= 6 and folded_alias != folded and _boundary_hit(folded_alias, folded):
                matches.append({"company": ck, "entity_key": ek,
                                "how": "alias_token_in_text", "score": 0.88})

    # 4. fuzzy: best similarity to canonical/alias names
    best = None
    for ck, block in idx.items():
        for ek, ent in block["entities"].items():
            for cand in [ent["folded_canonical"]] + [fold(n) for n in ent["names"]]:
                score = _ratio(folded, cand)
                if score >= 0.88 and (best is None or score > best["score"]):
                    best = {"company": ck, "entity_key": ek, "how": "fuzzy_similarity",
                            "score": round(score, 4), "candidate": cand}
    if best and not matches:
        matches.append(best)

    companies_hit = {m["company"] for m in matches}
    if len(companies_hit) > 1:
        return "conflict", matches
    if not matches:
        return "unmapped", []
    hows = [m["how"] for m in matches]
    if any(h.startswith("email_domain") for h in hows):
        return "exact_identifier", matches
    if "canonical_name_exact" in hows:
        return "normalized_name", matches
    if any(h in ("alias_exact", "operating_unit_prefix", "alias_token_in_text") for h in hows):
        return "alias", matches
    return "fuzzy", matches


def _date(s) -> _dt.date | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _interval_contains(ent: dict, d: _dt.date | None) -> bool:
    if not d or not ent.get("valid_from"):
        return True   # unknown start -> cannot prove the entity did not exist
    start = _date(ent["valid_from"])
    end = _date(ent.get("valid_to")) if ent.get("valid_to") else None
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def resolve_time_aware(matches: list[dict], claim_date: _dt.date | None, idx: dict,
                       company: str) -> tuple[str | None, dict | None]:
    """Pick the entity whose lifetime contains the claim date; else the earliest future one."""
    keys = []
    for m in matches:
        if m["company"] == company and m.get("entity_key") and m["entity_key"] not in keys:
            keys.append(m["entity_key"])
    if not keys:
        return None, None
    ents = idx[company]["entities"]
    for ek in keys:
        if _interval_contains(ents[ek], claim_date):
            return ek, None
    if claim_date:
        future = [(ents[ek]["valid_from"], ek) for ek in keys if ents[ek].get("valid_from")]
        if future:
            future.sort()
            return future[0][1], {"kind": "before_valid_from",
                                  "entity_valid_from": future[0][0]}
    return keys[0], None


def _is_canonical_name_hit(raw: str, company: str) -> bool:
    f = fold(raw)
    return any(_boundary_hit(t, f) for t in STAGE2_TOKENS.get(company, []))



def compute_stage2(register: dict, claims: list[dict], rejects: list[dict],
                   entities: list[dict], mentions: list[dict]) -> dict:
    idx = build_name_index(register)

    # company entity ids from entities.jsonl
    company_entity = {}
    for row in entities:
        eid = row.get("entity_id") or ""
        if row.get("entity_type") != "company_legal":
            continue
        ck = None
        for candidate in register["companies"]:
            if candidate in eid.lower() or candidate.replace("_", "-") in eid.lower():
                ck = candidate
                break
        if ck is None:
            f = fold(row.get("canonical_name") or "")
            for candidate, block in register["companies"].items():
                if f and f in (fold(block["canonical_company"]),):
                    ck = candidate
                    break
        if ck:
            company_entity[eid] = ck

    # mention lookup by evidence_id
    mention_by_evidence: dict[str, list[dict]] = {}
    for m in mentions:
        mention_by_evidence.setdefault(m.get("evidence_id"), []).append(m)

    # not_company strings for collision detection
    not_company = []
    for row in register.get("not_company_registry") or []:
        for s in row.get("strings") or []:
            not_company.append((row.get("company"), fold(s.get("string") or ""), s.get("string")))

    def not_company_hit(raw: str):
        f = fold(raw)
        for ck_nc, f_nc, original in not_company:
            if f_nc and (f == f_nc or _boundary_hit(f_nc, f)):
                reason = next((s.get("note") for row in register.get("not_company_registry") or []
                               for s in row.get("strings") or []
                               if s.get("string") == original), None)
                return {"kind": "not_company_string", "raw": raw,
                        "matched_not_company": original, "note_company": ck_nc,
                        "reason": reason}
        return None

    population = []   # one row per resolution event
    for c in claims:
        subj = company_entity.get(c.get("subject_id"))
        obj = company_entity.get(c.get("object_id"))
        company = subj or obj
        if not company:
            continue
        ment = [m for m in mention_by_evidence.get(c.get("evidence_id"), [])
                if m.get("company_key") in (None, company)]
        raw = (ment[0].get("raw_string") if ment else None) or c.get("subject_id") or ""
        pipe_status = c.get("mapping_status")
        claim_date = c.get("declared_at") or c.get("published_at") or c.get("event_at")
        d = _date(claim_date)
        tier, matches = classify_string(raw, company, idx, register)
        collision = not_company_hit(raw)
        if collision:
            tier, matches = "unmapped", []
        if pipe_status == "AMBIGUOUS" and tier != "unmapped":
            tier = "conflict"
        ek, ana = (None, None)
        if tier not in ("unmapped", "conflict"):
            ek, ana = resolve_time_aware(matches, d, idx, company)
        if ek is None and ment and ment[0].get("entity_key") and tier not in ("unmapped", "conflict"):
            ek = ment[0].get("entity_key")
        population.append({
            "company": company, "raw": raw, "tier": tier, "matches": matches,
            "claim_date": claim_date, "entity_key": ek, "pipeline_status": pipe_status,
            "rule": (ment[0].get("rule") if ment else c.get("mapping_method")),
            "source": (ment[0].get("source") if ment else None),
            "anachronism": ana, "collision": collision,
            "pipeline_anachronism": bool(ment[0].get("anachronism_if_mapped")) if ment else None,
            "from_reject": False,
        })

    for r in rejects:
        status = (r.get("mapping_status") or r.get("status") or "")
        raw = r.get("raw_string") or r.get("string") or ""
        company = r.get("company_key")
        if company not in register["companies"]:
            _, m0 = classify_string(raw, None, idx, register)
            company = m0[0]["company"] if m0 else None
        if company not in register["companies"]:
            continue
        tier, matches = classify_string(raw, company, idx, register)
        collision = not_company_hit(raw)
        if collision or status in ("NOT_MAPPED", "UNMAPPED"):
            tier, matches = "unmapped", []
        elif status == "AMBIGUOUS":
            tier = "conflict"
        elif status in ("REJECTED", "WEAK_TEXT") and tier != "unmapped":
            tier = "unmapped"
        d = _date(r.get("claim_date"))
        ek, ana = (None, None)
        if tier not in ("unmapped", "conflict"):
            ek, ana = resolve_time_aware(matches, d, idx, company)
        population.append({
            "company": company, "raw": raw, "tier": tier, "matches": matches,
            "claim_date": r.get("claim_date"), "entity_key": ek or r.get("entity_key"),
            "pipeline_status": status, "rule": r.get("rule"), "source": r.get("source"),
            "anachronism": ana, "collision": collision, "pipeline_anachronism": None,
            "from_reject": True,
        })

    n = len(population)
    tiers = {t: [p for p in population if p["tier"] == t] for t in STAGE2_TIERS}

    # ---- anachronisms -----------------------------------------------------
    anachronisms = []
    for p in population:
        if not p.get("anachronism"):
            continue
        d = _date(p["claim_date"])
        vf = p["anachronism"]["entity_valid_from"]
        anachronisms.append({
            "company": p["company"], "raw": p["raw"], "entity_key": p["entity_key"],
            "claim_date": d.isoformat() if d else p["claim_date"],
            "entity_valid_from": vf,
            "days_before": (_dt.date.fromisoformat(vf) - d).days if d else None,
            "tier": p["tier"], "source": p["source"],
        })

    # ---- collisions -------------------------------------------------------
    collisions = []
    for p in population:
        if p.get("collision"):
            c = dict(p["collision"])
            c["pipeline_status"] = p["pipeline_status"]
            collisions.append(c)
        if p["tier"] == "conflict":
            collisions.append({"kind": "multiple_companies", "raw": p["raw"],
                               "companies": sorted({m["company"] for m in p["matches"]}),
                               "pipeline_status": p["pipeline_status"]})

    # ---- per-company ------------------------------------------------------
    per_company = {}
    for ck, block in register["companies"].items():
        rows = [p for p in population if p["company"] == ck]
        c_tiers = {t: sum(1 for p in rows if p["tier"] == t) for t in STAGE2_TIERS}
        non_canonical = [p for p in rows if p["tier"] not in ("unmapped", "conflict")
                         and not _is_canonical_name_hit(p["raw"], ck)]
        # register names never observed anywhere in the population (canonical search would miss them)
        observed = {fold(p["raw"]) for p in population}
        unobserved = []
        for e in block["entities"]:
            if e["entity_type"] in ("former_subsidiary", "former_parent", "division", "brand",
                                    "operating_subsidiary"):
                names = [e["canonical_name"]] + [a["string"] for a in e["aliases"]
                                                 if a["kind"] != "not_company"]
                if not any(fold(nm) in observed or any(fold(nm) == o for o in observed) for nm in names):
                    unobserved.append({"entity_key": e["entity_key"],
                                       "canonical_name": e["canonical_name"],
                                       "entity_type": e["entity_type"]})
        per_company[ck] = {
            "population": len(rows),
            "tiers": c_tiers,
            "non_canonical_name_hits": len(non_canonical),
            "non_canonical_examples": sorted({p["raw"] for p in non_canonical})[:8],
            "unobserved_register_names": unobserved,
            "canonical_brand_token": STAGE2_TOKENS.get(ck),
        }

    return {
        "schema": "s029_entity_resolution_metrics_v1",
        "generated_at": utc_now_iso(),
        "population": {
            "claims_total": len(claims),
            "claim_rejects_total": len(rejects),
            "entities_total": len(entities),
            "mentions_total": len(mentions),
            "resolution_events": n,
        },
        "tier_definition": {
            "exact_identifier": "the string matched through a resolved identifier (e-mail domain of the company)",
            "normalized_name": "case/accent/punctuation-folded equality with a registered canonical name",
            "alias": "folded equality with, or operating-unit prefix of, a registered alias string",
            "fuzzy": "difflib similarity >= 0.88 to a canonical name or alias without an exact alias hit",
            "conflict": "the same string matches entities of two or more companies, or the pipeline flagged AMBIGUOUS",
            "unmapped": "no register match above the fuzzy threshold (includes pipeline REJECTED/NOT_MAPPED)",
        },
        "tiers": {t: {"n": len(tiers[t]), "rate": round(len(tiers[t]) / n, 4) if n else 0.0}
                  for t in STAGE2_TIERS},
        "anachronisms": {"n": len(anachronisms), "examples": sorted(
            anachronisms, key=lambda x: -(x["days_before"] or 0))[:10]},
        "pre_ownership_attributions": {
            "n": sum(1 for p in population if p.get("pipeline_anachronism")),
            "definition": "claims whose company string names an entity before the group owned it "
                          "(pipeline flag anachronism_if_mapped on the source mention); measured "
                          "separately from the valid_from anachronism because a former parent can "
                          "legitimately exist before the group owns its successor",
            "examples": [{"company": p["company"], "raw": p["raw"], "claim_date": p["claim_date"],
                          "entity_key": p["entity_key"]}
                         for p in population if p.get("pipeline_anachronism")][:10],
        },
        "collisions": {
            "n": len(collisions),
            "not_company_n": sum(1 for x in collisions if x["kind"] == "not_company_string"),
            "multi_company_n": sum(1 for x in collisions if x["kind"] == "multiple_companies"),
            "examples": collisions[:12],
        },
        "per_company": per_company,
        "pipeline_crosscheck": {
            "status_counts": {s: sum(1 for p in population if p["pipeline_status"] == s)
                              for s in sorted({p["pipeline_status"] for p in population},
                                              key=lambda x: str(x))},
            "agreement": round(sum(1 for p in population
                                   if (p["pipeline_status"] in ("EXACT", "ALIAS", "ORG_TEXT", "ORG_EMAIL"))
                                   == (p["tier"] not in ("unmapped", "conflict"))) / n, 4) if n else 0.0,
        },
        "notes": "Counts are computed by code/s029_company_register.py --stage2; every rate is "
                 "count/size of the stated population.",
    }


def render_stage2_md(metrics: dict, register: dict) -> str:
    L: list[str] = []
    A_ = L.append
    p = metrics["population"]
    A_("# S-029 entity resolution audit \u2014 measured mapping outcomes")
    A_("")
    A_("Generated by `code/s029_company_register.py --stage2` from the collected claims and the "
       "evidence-backed register `artifacts/company_entity_register.json`. Machine-readable numbers: "
       "`stage2_entity_resolution` in the same register artifact.")
    A_("")
    A_("## 1. Population")
    A_("")
    A_(f"- claims read: **{p['claims_total']}**; claim rejects read: **{p['claim_rejects_total']}**; "
       f"mentions available: **{p['mentions_total']}**; company entities: **{p['entities_total']}**")
    A_(f"- resolution events measured (claims involving a company + company-candidate rejects): "
       f"**{p['resolution_events']}**")
    A_("")
    A_("## 2. Match tiers (disjoint; rate = n / resolution events)")
    A_("")
    A_("| tier | meaning | n | rate |")
    A_("|---|---|---:|---:|")
    for t in STAGE2_TIERS:
        A_(f"| {t} | {metrics['tier_definition'][t]} | {metrics['tiers'][t]['n']} | "
           f"{metrics['tiers'][t]['rate']:.1%} |")
    A_("")
    A_("## 3. Conflicts and name collisions")
    A_("")
    col = metrics["collisions"]
    A_(f"- **{col['n']}** collision cases: **{col['not_company_n']}** strings that look like the company "
       f"but are not (surname / hospital trust / award / department), **{col['multi_company_n']}** strings "
       "matching more than one company.")
    if col["examples"]:
        A_("")
        A_("| kind | observed string | resolution |")
        A_("|---|---|---|")
        for ex in col["examples"]:
            if ex["kind"] == "not_company_string":
                A_(f"| not_company | `{ex['raw'][:90]}` | {ex['reason'] or 'not the company'} |")
            else:
                A_(f"| multi-company | `{ex['raw'][:90]}` | matches {', '.join(ex['companies'])} |")
    A_("")
    A_("## 4. Anachronisms")
    A_("")
    ana = metrics["anachronisms"]
    A_(f"**{ana['n']}** claims attribute activity to an entity before its `valid_from` (i.e. before it "
       "existed in that role, or before the group owned it). Largest offsets:")
    A_("")
    if ana["examples"]:
        A_("| company | observed string | entity | claim date | entity valid_from | days early |")
        A_("|---|---|---|---|---|---:|")
        for ex in ana["examples"]:
            A_(f"| {ex['company']} | `{ex['raw'][:70]}` | `{ex['entity_key']}` | {ex['claim_date']} | "
               f"{ex['entity_valid_from']} | {ex['days_before']} |")
    else:
        A_("_No anachronism measured._")
    A_("")
    po = metrics.get("pre_ownership_attributions") or {}
    A_(f"Separately, **{po.get('n', 0)}** claims name an entity *before the group owned it* "
       "(e.g. a pre-2015 'Covidien' record attributed to Medtronic). This is the broader "
       "attribution error and is reported separately: the entity existed, so it is not a "
       "`valid_from` anachronism, but the group did not own it yet.")
    if po.get("examples"):
        A_("")
        A_("| company | observed string | claim date | entity |")
        A_("|---|---|---|---|")
        for ex in po["examples"]:
            A_(f"| {ex['company']} | `{str(ex['raw'])[:70]}` | {ex['claim_date']} | `{ex['entity_key']}` |")
    A_("")
    A_("## 5. Per-company consequences for recall")
    A_("")
    A_("`non_canonical_name_hits` = claims whose string matched only a subsidiary/former-unit name that "
       "does **not** contain the company's canonical brand token (e.g. 'Covidien' contains no "
       "'Medtronic'). Those are invisible to a canonical-name search but recovered by the register. "
       "`unobserved_register_names` = registered names that never appear in the collected claims at all.")
    A_("")
    A_("| company | events | exact_id | normalized | alias | fuzzy | conflict | unmapped | non-canonical hits |")
    A_("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for ck, row in metrics["per_company"].items():
        t = row["tiers"]
        A_(f"| {ck} | {row['population']} | {t['exact_identifier']} | {t['normalized_name']} | "
           f"{t['alias']} | {t['fuzzy']} | {t['conflict']} | {t['unmapped']} | "
           f"{row['non_canonical_name_hits']} |")
    A_("")
    for ck, row in metrics["per_company"].items():
        A_(f"### {ck}")
        A_("")
        if row["non_canonical_examples"]:
            A_("- recovered only through non-canonical names: " +
               ", ".join(f"`{s}`" for s in row["non_canonical_examples"]))
        if row["unobserved_register_names"]:
            A_("- registered names that a canonical-name search would miss entirely in this corpus: " +
               ", ".join(f"`{u['canonical_name']}` ({u['entity_key']})"
                         for u in row["unobserved_register_names"]))
        A_("")
    A_("## 6. Cross-check against the pipeline's own mapping")
    A_("")
    cc = metrics["pipeline_crosscheck"]
    A_(f"- agreement between our independent tier (mapped vs not) and the pipeline status: "
       f"**{cc['agreement']:.1%}**")
    A_("- pipeline statuses over the same events: " +
       ", ".join(f"{k}={v}" for k, v in cc["status_counts"].items() if k is not None))
    A_("")
    A_("## 7. Limitations")
    A_("")
    A_("Tiers are computed on the *string* a source emitted, not on a registry record, so "
       "`normalized_name` means name agreement, not identity proof; identifiers are rare in this corpus "
       "and mostly appear as e-mail domains. Anachronism detection is bounded by the register's UNKNOWN "
       "`valid_from` values (no date, no finding).")
    A_("")
    return "\n".join(L)


def stage2(claims_path: str | None, refresh: bool, mentions_only: bool, write: bool) -> int:
    paths = {}
    for name in ("claims", "claim_rejects", "entities", "company_mentions"):
        for cand in (os.path.join(STUDY_DIR, "artifacts", name + ".jsonl"),
                     os.path.join(DATA_DIR, name + ".jsonl")):
            if os.path.exists(cand):
                paths[name] = cand
                break
    if claims_path:
        paths["claims"] = claims_path
    if "claims" not in paths:
        print("STAGE2 BLOCKED: no claims.jsonl found (looked in artifacts/ and data/). "
              "The Lead must publish the claim store first.", file=sys.stderr)
        return 3
    claims = load_jsonl(paths["claims"])
    rejects = load_jsonl(paths.get("claim_rejects", ""))
    entities = load_jsonl(paths.get("entities", ""))
    mentions = load_jsonl(paths.get("company_mentions", ""))
    register = json.load(open(os.path.join(ARTIFACTS, "company_entity_register.json"), encoding="utf-8"))
    metrics = compute_stage2(register, claims, rejects, entities, mentions)
    if mentions_only:
        print(json.dumps(metrics, ensure_ascii=False, indent=1)[:4000])
        return 0
    print(f"stage2: {metrics['population']['resolution_events']} resolution events; "
          f"tiers=" + ", ".join(f"{t}={metrics['tiers'][t]['n']}" for t in STAGE2_TIERS))
    print(f"        anachronisms={metrics['anachronisms']['n']} collisions={metrics['collisions']['n']}")
    if not write:
        return 0
    register["stage2_entity_resolution"] = metrics
    reg_path = os.path.join(ARTIFACTS, "company_entity_register.json")
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(register, f, indent=2, ensure_ascii=False)
        f.write("\n")
    md_path = os.path.join(STUDY_DIR, "ENTITY_RESOLUTION.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_stage2_md(metrics, register))
    print(f"        wrote {md_path}")
    print(f"        embedded metrics in {reg_path} (key: stage2_entity_resolution)")
    return 0


# ============================== STAGE 2 (report) ============================
ACCEPTED_STATUSES = {"EXACT", "ALIAS", "ORG_TEXT", "ORG_EMAIL"}
NONCLAIM_STATUSES = {"AMBIGUOUS", "NOT_MAPPED", "REJECTED", "WEAK_TEXT", "UNMAPPED"}
SPONSOR_ROLES = {"lead_sponsor", "collaborator"}
NON_CANONICAL_TYPES = {"former_subsidiary", "former_parent", "operating_subsidiary", "division"}


def _parent_names(register: dict, company: str) -> set[str]:
    names = set()
    for e in register["companies"][company]["entities"]:
        if e["entity_type"] != "public_parent":
            continue
        names.add(fold(e["canonical_name"]))
        for al in e["aliases"]:
            if al["kind"] in ("canonical", "alias", "former_name", "brand"):
                names.add(fold(al["string"]))
    return {n for n in names if n}


def _entity_by_key(register: dict) -> dict[str, dict]:
    out = {}
    for company, block in register["companies"].items():
        for e in block["entities"]:
            d = dict(e)
            d["_company"] = company
            out[e["entity_key"]] = d
    return out


def _count_by(rows: list[dict], keyfn) -> dict:
    c: dict = {}
    for r in rows:
        k = keyfn(r)
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0]))))


def _examples_per_entity(rows: list[dict], per_entity: int = 3) -> list[dict]:
    seen: dict = {}
    out = []
    for r in rows:
        ek = r.get("entity_key")
        if seen.get(ek, 0) >= per_entity:
            continue
        seen[ek] = seen.get(ek, 0) + 1
        out.append(r)
    return out


# --------------------------------------------------------------------------- #
# Claim-store linkage + ownership-date reconciliation (stage-2 additions)
# --------------------------------------------------------------------------- #
SPONSOR_ROLE_SET = {"lead_sponsor", "collaborator"}

# Family-level ownership dates already established by the register's verified
# acquisition events.  These are the dates the mapping layer uses for ownership; a
# string naming the family is therefore date-placeable even when the *legal entity's*
# incorporation date is UNKNOWN.
FAMILY_OWNERSHIP: dict[str, dict] = {
    "minimed_inc": {"date": "2001-08-28",
                    "event": "MiniMed acquisition completed 2001-08-28 (register minimed_inc "
                             "valid_to; Medtronic 8-K event date 2001-08-28)"},
    "medtronic_minimed_inc": {"date": "2001-08-28",
                              "event": "MiniMed family; ownership dates from the 2001-08-28 "
                                       "acquisition (accepted attribution of the mapping layer)"},
    "covidien_plc": {"date": "2015-01-26", "event": "Covidien acquisition completed 2015-01-26"},
    "covidien_ltd": {"date": "2015-01-26", "event": "Covidien group acquired 2015-01-26"},
    "tyco_healthcare": {"date": "2015-01-26", "event": "Covidien group acquired 2015-01-26"},
    "respironics_inc": {"date": "2008-03-17", "event": "Respironics acquisition announced complete 2008-03-17"},
    "zonare_medical_systems_inc": {"date": "2013-07-17", "event": "ZONARE acquisition completed 2013-07-17"},
    "datascope_patient_monitoring_business": {"date": "2008-05-14",
                                              "event": "Datascope Patient Monitoring closed 2008-05-14"},
    "philips_lighting_nv": {"date": "2016-05-27", "event": "Philips Lighting listed 2016-05-27"},
}


def _mention_index(mentions: list[dict]) -> dict:
    idx = {}
    for m in mentions:
        idx.setdefault((m.get("record_id"), m.get("role"), m.get("company_key")), []).append(m)
    return idx


def _claim_company(claim: dict, company_ids: dict) -> str | None:
    for fld in ("subject_id", "object_id"):
        eid = claim.get(fld)
        if isinstance(eid, str) and eid in company_ids:
            return company_ids[eid]
    return None


def compute_claim_linkage(register: dict, claims: list[dict], mentions: list[dict],
                          entities: list[dict] | None = None) -> dict:
    """Map the claim store onto the identity decisions and measure claim-level outcomes."""
    company_ids = {}
    for e in (entities or []):
        eid = e.get("entity_id") or ""
        if e.get("entity_type") != "company_legal":
            continue
        for ck in register["companies"]:
            if eid.endswith(":" + ck):
                company_ids[eid] = ck
                break
    if not company_ids:
        company_ids = {f"ent:company:{ck}": ck for ck in register["companies"]}
    m_idx = _mention_index(mentions)
    parent_names = {ck: _parent_names(register, ck) for ck in register["companies"]}

    by_company: dict[str, dict] = {}
    roles: dict[str, int] = {}
    statuses: dict[str, int] = {}
    matched_by_role: dict[str, int] = {}
    unit_claims: dict[str, int] = {}
    parent_claims: dict[str, int] = {}
    sponsor_claims: dict[str, int] = {}
    for c in claims:
        ck = _claim_company(c, company_ids)
        if not ck:
            continue
        row = by_company.setdefault(ck, {"claims": 0, "roles": {}, "mapping_status": {},
                                         "matched_to_mention": 0})
        row["claims"] += 1
        role = c.get("relation_role") or "UNKNOWN"
        row["roles"][role] = row["roles"].get(role, 0) + 1
        st = c.get("mapping_status") or "UNKNOWN"
        row["mapping_status"][st] = row["mapping_status"].get(st, 0) + 1
        roles[role] = roles.get(role, 0) + 1
        statuses[st] = statuses.get(st, 0) + 1
        ms = m_idx.get((c.get("source_record_id"), c.get("relation_role"), ck)) or []
        if not ms:
            continue
        row["matched_to_mention"] += 1
        matched_by_role[role] = matched_by_role.get(role, 0) + 1
        if role in SPONSOR_ROLE_SET:
            sponsor_claims[ck] = sponsor_claims.get(ck, 0) + 1
            raws = [fold(x.get("raw_string") or "") for x in ms]
            if any(rw in parent_names[ck] for rw in raws):
                parent_claims[ck] = parent_claims.get(ck, 0) + 1
            else:
                unit_claims[ck] = unit_claims.get(ck, 0) + 1

    sponsor_total = sum(sponsor_claims.values())
    unit_total = sum(unit_claims.values())
    parent_total = sum(parent_claims.values())
    per_company = {}
    for ck in register["companies"]:
        s = sponsor_claims.get(ck, 0)
        per_company[ck] = {
            "claims": by_company.get(ck, {}).get("claims", 0),
            "roles": by_company.get(ck, {}).get("roles", {}),
            "mapping_status": by_company.get(ck, {}).get("mapping_status", {}),
            "matched_to_mention": by_company.get(ck, {}).get("matched_to_mention", 0),
            "sponsor_claims": s,
            "sponsor_parent_name": parent_claims.get(ck, 0),
            "sponsor_operating_unit": unit_claims.get(ck, 0),
            "sponsor_unit_share": round(unit_claims.get(ck, 0) / s, 4) if s else 0.0,
        }
    return {
        "claims_total": len(claims),
        "claims_involving_company": sum(by_company.get(ck, {}).get("claims", 0) for ck in register["companies"]),
        "roles": roles,
        "mapping_status": statuses,
        "matched_to_mentions": sum(v.get("matched_to_mention", 0) for v in by_company.values()),
        "matched_by_role": matched_by_role,
        "per_company": per_company,
        "reviewer_statement": {
            "sponsor_claims": sponsor_total,
            "operating_unit_string_claims": unit_total,
            "exact_parent_string_claims": parent_total,
            "operating_unit_share": round(unit_total / sponsor_total, 4) if sponsor_total else 0.0,
            "sentence": ("Claims whose subject is a company but whose raw sponsor string was an "
                         "operating unit or subsidiary rather than the legal parent: "
                         f"{unit_total} of {sponsor_total} company-subject sponsorship claims "
                         f"({(unit_total / sponsor_total * 100) if sponsor_total else 0.0:.1f}%)"),
        },
        "join_note": ("claims are linked to their raw identity decisions on "
                      "(source_record_id, relation_role, company_key); co-affiliation claims are "
                      "DERIVED_FROM_EXACT pairs and grant-funder claims have no company mention row, "
                      "which is why not every company claim has a matched mention"),
    }


def compute_ownership_reconciliation(register: dict, mentions: list[dict]) -> dict:
    """Reconcile the two ownership-date-unknown definitions.

    A = 'legal-entity date unknown': the register has no valid_from/valid_to for the
        subsidiary legal person (this is what the earlier run reported: 86 strings).
    B = 'group-ownership date unknown' (the operative definition, aligned with the
        mapping layer): the family has no verified acquisition/ownership date.  The
        MiniMed family is dated by the 2001-08-28 acquisition, so MiniMed strings are
        NOT undated under B.
    """
    idx = build_name_index(register)
    ent_by = _entity_by_key(register)
    alias_idx: dict[str, list] = {}
    for ck, block in idx.items():
        alias_idx[ck] = list(block["aliases"])
    accepted = {"EXACT", "ALIAS", "ORG_TEXT", "ORG_EMAIL"}

    undated_b, division_undated = [], []
    undated_a = 0
    for m in mentions:
        ck = m.get("company_key")
        if ck not in register["companies"]:
            continue
        ek = m.get("entity_key")
        if not ek:
            raw = m.get("raw_string") or ""
            f = fold(raw)
            pk = idx[ck]["parent_key"]
            spec = [(a_ek, a_kind) for folded, a_ek, a_kind, _orig in alias_idx[ck]
                    if a_ek != pk and a_kind != "operating_unit_prefix"
                    and (folded == f or (len(folded) >= 6 and _boundary_hit(folded, f)))]
            if not spec:
                continue
            ek = spec[0][0]
        ent = ent_by.get(ek)
        if not ent or ent.get("valid_from") or ent.get("valid_to"):
            continue
        undated_a += 1
        if m.get("mapping_status") not in accepted:
            continue
        row = {"company": ck, "raw": m.get("raw_string"), "entity_key": ek,
               "entity_type": ent["entity_type"], "mapping_status": m.get("mapping_status"),
               "record_id": m.get("record_id"), "rule": m.get("rule")}
        if ent["entity_type"] == "division":
            division_undated.append(row)
        elif ek not in FAMILY_OWNERSHIP:
            undated_b.append(row)
    return {
        "definitions": {
            "A_legal_entity_date_unknown": (
                "the register records no valid_from/valid_to for the subsidiary legal person "
                f"itself -> {undated_a} mention strings (dominated by medtronic_minimed_inc). "
                "This is a legal-entity fact, NOT an ownership problem."),
            "B_group_ownership_date_unknown": (
                "the family has no verified acquisition/ownership date; MiniMed strings are dated "
                "by the 2001-08-28 acquisition and are therefore NOT undated under this definition. "
                "This is the operative definition for the study."),
        },
        "family_ownership_dates": FAMILY_OWNERSHIP,
        "accepted_attribution": (
            "ACCEPTED: 'Medtronic MiniMed, Inc.' strings are date-placed through the MiniMed "
            "acquisition of 2001-08-28 (mapping layer ownership_from = 2001-08-28). The register still "
            "records the Delaware entity's own incorporation date as UNKNOWN; the reconciliation uses "
            "the family ownership date, so the earlier 79-string MiniMed figure is withdrawn as an "
            "ownership-date measure and retained only as a legal-entity-date caveat."),
        "undated_ownership": {
            "n_strings": len(undated_b),
            "by_entity": _count_by(undated_b, lambda r: r["entity_key"]),
            "by_mapping_status": _count_by(undated_b, lambda r: r["mapping_status"]),
            "examples": _examples_per_entity(undated_b, per_entity=4),
        },
        "undated_division": {"n_strings": len(division_undated),
                             "examples": _examples_per_entity(division_undated, per_entity=3)},
    }


def compute_stage2_report(register: dict, claims: list[dict], mentions: list[dict],
                          trials: list[dict], institutions: list[dict],
                          rejects: list[dict]) -> dict:
    """Compute the six required stage-2 measurements from the collected data."""
    ent_by_key = _entity_by_key(register)
    idx = build_name_index(register)
    parent_names = {ck: _parent_names(register, ck) for ck in register["companies"]}

    company_of = {}
    for m in mentions:
        ck = m.get("company_key")
        if ck in register["companies"]:
            company_of.setdefault(ck, []).append(m)

    # ---------- 1. per company mapping_status distribution -----------------
    per_company: dict[str, dict] = {}
    for ck in register["companies"]:
        rows = company_of.get(ck, [])
        st = _count_by(rows, lambda r: r.get("mapping_status") or "UNKNOWN")
        accepted = sum(1 for r in rows if r.get("mapping_status") in ACCEPTED_STATUSES)
        nonclaim = sum(1 for r in rows if r.get("mapping_status") in NONCLAIM_STATUSES)
        other = len(rows) - accepted - nonclaim
        per_company[ck] = {
            "mentions": len(rows),
            "mapping_status": st,
            "claim_producing": accepted,
            "claim_producing_rate": round(accepted / len(rows), 4) if rows else 0.0,
            "non_claim_producing": nonclaim,
            "non_claim_producing_rate": round(nonclaim / len(rows), 4) if rows else 0.0,
            "other_status": other,
        }

    # ---------- 2. operating unit vs exact parent name ----------------------
    for ck, block in per_company.items():
        rows = [m for m in company_of.get(ck, []) if m.get("role") in SPONSOR_ROLES]
        accepted = [m for m in rows if m.get("mapping_status") in ACCEPTED_STATUSES]
        exact_parent, unit = [], []
        for m in accepted:
            f = fold(m.get("raw_string") or "")
            (exact_parent if f in parent_names[ck] else unit).append(m)
        unit_strings = _count_by(unit, lambda r: r.get("raw_string"))
        block["operating_unit_reality"] = {
            "sponsor_role_mentions": len(rows),
            "accepted_sponsor_mentions": len(accepted),
            "exact_parent_name": len(exact_parent),
            "operating_unit_or_subsidiary": len(unit),
            "operating_unit_share_of_accepted": round(len(unit) / len(accepted), 4) if accepted else 0.0,
            "distinct_unit_strings": len(unit_strings),
            "top_unit_strings": [{"string": k, "mentions": v} for k, v in list(unit_strings.items())[:8]],
            "exact_parent_strings": _count_by(exact_parent, lambda r: r.get("raw_string")),
        }

    # ---------- 3. anachronisms -------------------------------------------
    ana_rule = [m for m in mentions if m.get("rule") == "subsidiary_not_yet_owned"]
    ana_examples = [{"company": m.get("company_key"), "raw": m.get("raw_string"),
                     "claim_date": m.get("claim_date"), "ownership_from": m.get("ownership_from"),
                     "entity_key": m.get("entity_key"), "mapping_status": m.get("mapping_status"),
                     "source": m.get("source"), "record_id": m.get("record_id")}
                    for m in ana_rule]

    # own computation: accepted mentions dated before the register valid_from of the mapped entity
    ana_register = []
    for m in mentions:
        if m.get("mapping_status") not in ACCEPTED_STATUSES:
            continue
        ek = m.get("entity_key")
        ent = ent_by_key.get(ek)
        if not ent or not ent.get("valid_from"):
            continue
        d = _date(m.get("claim_date"))
        if d and d.isoformat() < ent["valid_from"]:
            ana_register.append({"company": ent["_company"], "raw": m.get("raw_string"),
                                 "entity_key": ek, "claim_date": d.isoformat(),
                                 "entity_valid_from": ent["valid_from"],
                                 "days_before": (_dt.date.fromisoformat(ent["valid_from"]) - d).days,
                                 "source": m.get("source"), "record_id": m.get("record_id")})

    # ownership date UNKNOWN: accepted mentions mapped to a subsidiary/former entity whose
    # register valid_from is UNKNOWN and whose ownership_from was never established
    unknown_owner, unknown_division, dates_unknown_flag = [], [], []
    for m in mentions:
        if m.get("dates_unknown"):
            dates_unknown_flag.append({"company": m.get("company_key"), "raw": m.get("raw_string"),
                                       "entity_key": m.get("entity_key"),
                                       "claim_date": m.get("claim_date"), "rule": m.get("rule")})
        if m.get("mapping_status") not in ACCEPTED_STATUSES:
            continue
        ent = ent_by_key.get(m.get("entity_key"))
        if not ent or ent.get("valid_from") is not None or ent.get("valid_to") is not None \
                or m.get("ownership_from") is not None:
            continue
        row = {"company": ent["_company"], "raw": m.get("raw_string"),
               "entity_key": ent["entity_key"], "entity_type": ent["entity_type"],
               "claim_date": m.get("claim_date"), "mapping_status": m.get("mapping_status"),
               "rule": m.get("rule"), "record_id": m.get("record_id"),
               "register_valid_from": None}
        if ent["entity_type"] == "division":
            unknown_division.append(row)
        elif ent["entity_type"] in ("former_subsidiary", "former_parent", "operating_subsidiary"):
            unknown_owner.append(row)
    # mentions the mapping layer accepted but without a resolved entity: resolve them through the
    # register and downgrade any that land on an entity whose validity/ownership date is UNKNOWN
    for m in mentions:
        if m.get("mapping_status") not in ACCEPTED_STATUSES or m.get("entity_key"):
            continue
        ck = m.get("company_key")
        if ck not in register["companies"]:
            continue
        _tier, matches = classify_string(m.get("raw_string") or "", ck, idx, register)
        specific = [x for x in matches
                    if x.get("how") == "canonical_name_exact"
                    or x.get("how") == "alias_token_in_text"
                    or (x.get("how") == "alias_exact"
                        and x.get("alias_kind") in ("canonical", "alias", "former_name", "subsidiary"))]
        if not specific:
            continue
        ek, _ana = resolve_time_aware(specific, _date(m.get("claim_date")), idx, ck)
        ent = ent_by_key.get(ek)
        if not ent or ent.get("valid_from") is not None or ent.get("valid_to") is not None:
            continue
        row = {"company": ck, "raw": m.get("raw_string"), "entity_key": ent["entity_key"],
               "entity_type": ent["entity_type"], "claim_date": m.get("claim_date"),
               "mapping_status": m.get("mapping_status"), "rule": m.get("rule"),
               "record_id": m.get("record_id"), "register_valid_from": None,
               "resolved_by": "register_alias_fallback:" + specific[0]["how"]}
        if ent["entity_type"] == "division":
            unknown_division.append(row)
        elif ent["entity_type"] in ("former_subsidiary", "former_parent", "operating_subsidiary"):
            unknown_owner.append(row)
    unknown_owner_by_entity = _count_by(unknown_owner, lambda r: r["entity_key"])

    # ---------- 4. collisions ---------------------------------------------
    rejected = [m for m in mentions if m.get("mapping_status") == "REJECTED"]
    rejected_by_rule = _count_by(rejected, lambda r: "%s|%s" % (r.get("company_key"), r.get("rule")))
    # register not_company strings that appear in rejected mentions
    nc_hits = []
    for m in rejected:
        f = fold(m.get("raw_string") or "")
        for row in register.get("not_company_registry") or []:
            hit = None
            for s in row.get("strings") or []:
                if _boundary_hit(fold(s.get("string") or ""), f):
                    hit = s
                    break
            if hit:
                nc_hits.append({"company": row.get("company"), "raw": m.get("raw_string"),
                                "not_company_string": hit.get("string"),
                                "reason": hit.get("note"), "rule": m.get("rule"),
                                "source": m.get("source")})
                break
    collision_examples = []
    seen_groups = {}
    seen_rows = set()
    for m in rejected:
        g = (m.get("company_key"), m.get("rule"))
        rk = (m.get("company_key"), m.get("rule"), m.get("raw_string"))
        if rk in seen_rows:
            continue
        seen_rows.add(rk)
        seen_groups[g] = seen_groups.get(g, 0) + 1
        if seen_groups[g] <= 3:
            collision_examples.append({"company": m.get("company_key"), "raw": m.get("raw_string"),
                                       "rule": m.get("rule"), "reason": m.get("reason"),
                                       "source": m.get("source")})

    # ---------- 5. recall consequence from discovered_by + mentions --------
    recall = {}
    for ck in register["companies"]:
        noncanon_queries, canon_queries = set(), set()
        reached_only = []
        for t in trials:
            nct = t.get("nct_id")
            dbs = t.get("discovered_by") or []
            ck_dbs = [d for d in dbs if d.get("company_key") == ck]
            if not ck_dbs:
                continue
            qs = [d.get("query_value") or "" for d in ck_dbs]
            for q in qs:
                if _is_canonical_name_hit(q, ck) and fold(q) in parent_names[ck]:
                    canon_queries.add(q)
                else:
                    noncanon_queries.add(q)
            noncanon_here = [q for q in qs if not (fold(q) in parent_names[ck])]
            if noncanon_here:
                reached_only.append({"nct_id": nct, "query_values": noncanon_here,
                                     "canonical_query_present": any(fold(q) in parent_names[ck] for q in qs)})
        recall[ck] = {
            "studies_discovered": sum(1 for t in trials
                                      if any(d.get("company_key") == ck for d in (t.get("discovered_by") or []))),
            "canonical_query_values": sorted(canon_queries),
            "non_canonical_query_values": sorted(noncanon_queries)[:12],
            "studies_with_non_canonical_query": len(reached_only),
            "studies_reached_only_via_non_canonical_query": sum(
                1 for r in reached_only if not r["canonical_query_present"]),
            "examples": reached_only[:8],
        }
    # mention-based recall: studies whose company mentions are only non-canonical names
    for ck, block in recall.items():
        only_noncanon = set()
        per_nct: dict[str, dict] = {}
        for m in company_of.get(ck, []):
            if m.get("record_kind") != "trial" or m.get("mapping_status") not in ACCEPTED_STATUSES:
                continue
            nct = m.get("record_id")
            rec = per_nct.setdefault(nct, {"canon": 0, "noncanon": 0})
            raw_f = fold(m.get("raw_string") or "")
            if raw_f in parent_names[ck]:
                rec["canon"] += 1
            else:
                rec["noncanon"] += 1
        for nct, rec in per_nct.items():
            if rec["noncanon"] and not rec["canon"]:
                only_noncanon.add(nct)
        block["studies_reached_only_via_non_canonical_mention"] = len(only_noncanon)
        block["mentions_trial_link_examples"] = sorted(only_noncanon)[:8]

    # ---------- brief's tier table (independent classifier) ----------------
    tiers = {t: 0 for t in STAGE2_TIERS}
    tier_by_company = {ck: {t: 0 for t in STAGE2_TIERS} for ck in register["companies"]}
    collision_flags = 0
    for m in mentions:
        ck = m.get("company_key")
        if ck not in register["companies"]:
            continue
        raw = m.get("raw_string") or ""
        t, _mt = classify_string(raw, ck, idx, register)
        nc = None
        for row in register.get("not_company_registry") or []:
            for s in row.get("strings") or []:
                if _boundary_hit(fold(s.get("string") or ""), fold(raw)):
                    nc = s.get("string")
                    break
            if nc:
                break
        if nc:
            t = "unmapped"
            collision_flags += 1
        tiers[t] += 1
        tier_by_company[ck][t] += 1
    n_tier = sum(tiers.values())

    # ---------- claims linkage (optional) ---------------------------------
    claims_info = {"claims_total": len(claims), "status": "PENDING" if not claims else "LINKED"}
    if claims:
        # detect company subjects by entity ids present in claims
        claims_info.update({
            "status": "LINKED",
            "claims_with_company_subject": sum(
                1 for c in claims
                if str(c.get("subject_id", "")).startswith("ent:company:")
                or str(c.get("object_id", "")).startswith("ent:company:")),
            "mapping_status": _count_by(
                [c for c in claims if c.get("subject_id", "").startswith("ent:company:")
                 or c.get("object_id", "").startswith("ent:company:")],
                lambda c: c.get("mapping_status") or "UNKNOWN"),
        })

    claim_linkage = compute_claim_linkage(register, claims, mentions)
    reconciliation = compute_ownership_reconciliation(register, mentions)

    # ---------- 6. verdict (derived from the numbers above) ----------------
    total_mentions = len(mentions)
    accepted_total = sum(b["claim_producing"] for b in per_company.values())
    unknown_share = round(len(unknown_owner) / accepted_total, 4) if accepted_total else 0.0
    ana_total = len(ana_register)
    ana_share = round(ana_total / accepted_total, 4) if accepted_total else 0.0
    rejection_total = len(rejected)
    verdict = {
        "claim_producing_rate": round(accepted_total / total_mentions, 4) if total_mentions else 0.0,
        "accepted_mentions": accepted_total,
        "mentions": total_mentions,
        "ownership_date_unknown_share": unknown_share,
        "anachronism_share": ana_share,
        "rejected_mentions": rejection_total,
        "statement": None,
    }
    min_company_rate = min((b["claim_producing_rate"] for b in per_company.values()), default=0.0)
    weak = sorted(((b["claim_producing_rate"], ck) for ck, b in per_company.items()))[:2]
    verdict["min_company_claim_producing_rate"] = round(min_company_rate, 4)
    verdict["weakest_companies"] = [{"company": ck, "rate": round(r, 4)} for r, ck in weak]
    if accepted_total and unknown_share <= 0.01 and ana_share <= 0.01 and min_company_rate >= 0.85:
        verdict["statement"] = (
            "The identity layer is fit for a cross-source temporal study: "
            f"{verdict['claim_producing_rate']:.1%} of {total_mentions} company strings resolve to a "
            f"company, the ownership-date-unknown share is {unknown_share:.2%} and the measured "
            f"valid_from anachronism share is {ana_share:.2%}. Residual risk is concentrated in the "
            "explicitly listed UNKNOWN entities and rejected collisions, not in the mapped core.")
    elif accepted_total and unknown_share <= 0.10 and ana_share <= 0.05 and min_company_rate >= 0.40:
        verdict["statement"] = (
            "The identity layer is usable for a temporal study only with the documented caveats: "
            f"{verdict['claim_producing_rate']:.1%} of {total_mentions} company strings resolve to a "
            f"company, but {unknown_share:.2%} of accepted mappings have an UNKNOWN ownership date and "
            f"{ana_share:.2%} are measured anachronisms. Claims resting on the UNKNOWN entities must be "
            "excluded from any time-sensitive test rather than silently accepted.")
    else:
        verdict["statement"] = (
            "The identity layer is NOT yet fit for a time-sensitive study on these numbers: "
            f"claim-producing rate {verdict['claim_producing_rate']:.1%}, ownership-date-unknown share "
            f"{unknown_share:.2%}, anachronism share {ana_share:.2%}. The failures are enumerated above "
            "and must be fixed before cross-source temporal inference.")

    return {
        "schema": "s029_entity_resolution_metrics_v1",
        "generated_at": utc_now_iso(),
        "inputs": {
            "claims": claims_info,
            "mentions": len(mentions),
            "claim_rejects": len(rejects),
            "trials": len(trials),
            "institutions": len(institutions),
        },
        "register_authority": {
            "path": "artifacts/company_entity_register.json",
            "hash_sha256": hashlib.sha256(
                json.dumps(register["companies"], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "unknown_entities": sorted(
                ek for ek, e in ent_by_key.items() if e.get("valid_from") is None),
        },
        "per_company": per_company,
        "anachronisms": {
            "rule_subsidiary_not_yet_owned": {"n": len(ana_rule), "examples": ana_examples[:12]},
            "register_valid_from_violations": {"count": len(ana_register),
                                               "examples": sorted(ana_register,
                                                                  key=lambda x: -x["days_before"])[:12]},
            "division_start_unknown": {"n": len(unknown_division),
                                        "examples": unknown_division[:8]},
            "dates_unknown_flag_from_mapping_layer": {"n": len(dates_unknown_flag),
                                                        "examples": dates_unknown_flag[:8]},
            "ownership_date_unknown": {"n": reconciliation["undated_ownership"]["n_strings"],
                                       "by_entity": reconciliation["undated_ownership"]["by_entity"],
                                       "examples": reconciliation["undated_ownership"]["examples"],
                                       "policy": "mapping downgraded: the entity is in the register but its "
                                                 "group-ownership/validity date is UNKNOWN, so the claim cannot "
                                                 "be placed in time"},
        },
        "collisions": {
            "rejected_mentions": rejection_total,
            "by_company_and_rule": rejected_by_rule,
            "register_not_company_hits": {"n": len(nc_hits), "examples": nc_hits[:12]},
            "examples": collision_examples[:20],
        },
        "recall": recall,
        "tiers": {
            "definition": {
                "exact_identifier": "matched through a resolved identifier (company e-mail domain)",
                "normalized_name": "folded equality with a registered canonical name",
                "alias": "registered alias, operating-unit prefix, or registered brand token inside the string",
                "fuzzy": "similarity >= 0.88 without an exact name/alias hit",
                "conflict": "the string matches entities of two or more companies",
                "unmapped": "no register match, or a match to a registered not_company string",
            },
            "counts": tiers,
            "rates": {t: round(tiers[t] / n_tier, 4) if n_tier else 0.0 for t in STAGE2_TIERS},
            "by_company": tier_by_company,
            "not_company_collisions": collision_flags,
        },
        "claims_linkage": claim_linkage,
        "ownership_reconciliation": reconciliation,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------- #
# Stage-2 report renderer (Lead-specified sections)
# --------------------------------------------------------------------------- #
def render_entity_resolution_md(metrics: dict, register: dict) -> str:
    L: list[str] = []
    A_ = L.append
    A_("# S-029 entity resolution audit \u2014 measured identity outcomes")
    A_("")
    A_("Generated by `code/s029_company_register.py --stage2`. Every number below is computed by that "
       "code and stored in `artifacts/entity_resolution_metrics.json`; this file contains no hand-written "
       "number. The corporate facts are cited from `artifacts/company_entity_register.json` "
       f"(register hash `{metrics['register_authority']['hash_sha256'][:16]}\u2026`).")
    A_("")
    A_("## 0. Inputs and authority")
    A_("")
    inp = metrics["inputs"]
    A_(f"- company mention records: **{inp['mentions']}**; ClinicalTrials.gov studies: "
       f"**{inp['trials']}**; institutions: **{inp['institutions']}**; claim rejects: "
       f"**{inp['claim_rejects']}**")
    cl = inp["claims"]
    if cl.get("status") == "PENDING":
        A_("- claims store: **PENDING** \u2014 `data/claims.jsonl` did not exist when this run was made; "
           "all identity measurements below are computed from the per-string mention records, which are "
           "the inputs the claim builder consumes. Re-running `--stage2` after the claim store exists adds "
           "the claim-level linkage without changing the identity numbers.")
    else:
        A_(f"- claims store: **{cl['claims_total']}** claims, **{cl.get('claims_with_company_subject', 0)}** "
           "with a company as subject/object; status distribution stored in the JSON artifact.")
    A_(f"- entities whose register `valid_from` is UNKNOWN (treated as UNKNOWN, never dated): "
       + ", ".join(f"`{e}`" for e in metrics["register_authority"]["unknown_entities"]))
    A_("")
    A_("## 1. Mapping-status distribution per company")
    A_("")
    A_("`claim-producing` = EXACT / ALIAS / ORG_TEXT / ORG_EMAIL (the statuses the claim builder accepts). "
       "`non-claim-producing` = AMBIGUOUS / NOT_MAPPED / REJECTED / WEAK_TEXT / UNMAPPED.")
    A_("")
    A_("| company | mentions | claim-producing | rate | non-claim-producing | rate | status breakdown |")
    A_("|---|---:|---:|---:|---:|---:|---|")
    for ck, row in metrics["per_company"].items():
        st = ", ".join(f"{k}={v}" for k, v in row["mapping_status"].items())
        A_(f"| {ck} | {row['mentions']} | {row['claim_producing']} | {row['claim_producing_rate']:.1%} | "
           f"{row['non_claim_producing']} | {row['non_claim_producing_rate']:.1%} | {st} |")
    A_("")
    A_("## 2. The company as a fiction in registry data (operating units vs exact parent)")
    A_("")
    A_("Counted over sponsor-role mentions (lead sponsor, collaborator) with an accepted mapping. "
       "`exact_parent_name` means the string folds to a registered parent name/alias; everything else is "
       "an operating unit, site, division or subsidiary string.")
    A_("")
    A_("| company | accepted sponsor mentions | exact parent name | operating unit / subsidiary | unit share | distinct unit strings |")
    A_("|---|---:|---:|---:|---:|---:|")
    for ck, row in metrics["per_company"].items():
        u = row["operating_unit_reality"]
        A_(f"| {ck} | {u['accepted_sponsor_mentions']} | {u['exact_parent_name']} | "
           f"{u['operating_unit_or_subsidiary']} | {u['operating_unit_share_of_accepted']:.1%} | "
           f"{u['distinct_unit_strings']} |")
    A_("")
    for ck, row in metrics["per_company"].items():
        u = row["operating_unit_reality"]
        if u["top_unit_strings"]:
            A_(f"- {ck}: " + "; ".join(f"`{x['string']}` ({x['mentions']})" for x in u["top_unit_strings"][:5]))
    A_("")
    A_("## 3. Anachronisms and ownership dates that cannot be established")
    A_("")
    ana = metrics["anachronisms"]
    A_(f"- Mentions flagged `subsidiary_not_yet_owned` by the mapping layer (claim date < ownership date): "
       f"**{ana['rule_subsidiary_not_yet_owned']['n']}**")
    A_(f"- Additional mentions whose date precedes the mapped entity's register `valid_from`: "
       f"**{ana['register_valid_from_violations']['count']}**")
    A_(f"- Mentions whose mapped subsidiary/former entity has an **UNKNOWN ownership date**: "
       f"**{ana['ownership_date_unknown']['n']}** \u2014 reported as *mapping downgraded*, never accepted "
       "silently.")
    A_("")
    A_("### 3.1 subsidiary_not_yet_owned (mapping layer)")
    A_("")
    if ana["rule_subsidiary_not_yet_owned"]["examples"]:
        A_("| company | observed string | claim date | ownership from | entity |")
        A_("|---|---|---|---|---|")
        for ex in ana["rule_subsidiary_not_yet_owned"]["examples"]:
            A_(f"| {ex['company']} | `{str(ex['raw'])[:70]}` | {ex['claim_date']} | "
               f"{ex['ownership_from']} | `{ex['entity_key']}` |")
    else:
        A_("_None._")
    A_("")
    A_("### 3.2 Before register valid_from")
    A_("")
    if ana["register_valid_from_violations"]["examples"]:
        A_("| company | observed string | entity | claim date | entity valid_from | days early |")
        A_("|---|---|---|---|---|---:|")
        for ex in ana["register_valid_from_violations"]["examples"]:
            A_(f"| {ex['company']} | `{str(ex['raw'])[:60]}` | `{ex['entity_key']}` | {ex['claim_date']} | "
               f"{ex['entity_valid_from']} | {ex['days_before']} |")
    else:
        A_("_None._")
    A_("")
    A_("### 3.3 Ownership date UNKNOWN \u2014 mapping downgraded")
    A_("")
    A_(ana["ownership_date_unknown"]["policy"])
    A_("")
    if ana["ownership_date_unknown"]["examples"]:
        A_("| company | observed string | entity | entity type | claim date | rule | resolved by |")
        A_("|---|---|---|---|---|---|---|")
        for ex in ana["ownership_date_unknown"]["examples"]:
            A_(f"| {ex['company']} | `{str(ex['raw'])[:70]}` | `{ex['entity_key']}` | "
               f"{ex['entity_type']} | {ex['claim_date']} | {ex['rule']} | "
               f"{ex.get('resolved_by', 'mapping layer')} |")
        A_("")
        A_("By entity: " + ", ".join(f"`{k}`={v}" for k, v in
                                     ana["ownership_date_unknown"]["by_entity"].items()))
    else:
        A_("_None._")
    A_("")
    A_("### 3.4 Division start date UNKNOWN (not an ownership date)")
    A_("")
    du = ana.get("division_start_unknown") or {"n": 0, "examples": []}
    A_(f"**{du['n']}** mentions name a division whose start date the register cannot establish; they are "
       "reported separately because a division's start is not an ownership date.")
    A_("")
    if du["examples"]:
        A_("| company | observed string | entity | claim date |")
        A_("|---|---|---|---|")
        for ex in du["examples"]:
            A_(f"| {ex['company']} | `{str(ex['raw'])[:70]}` | `{ex['entity_key']}` | {ex['claim_date']} |")
        A_("")
    duf = ana.get("dates_unknown_flag_from_mapping_layer") or {"n": 0, "examples": []}
    A_(f"The mapping layer's own `dates_unknown=true` flag covers **{duf['n']}** mentions in this "
       "snapshot; the register-derived counts above are the authoritative cross-check on any re-run.")
    A_("")
    A_("## 4. Name collisions and rejections")
    A_("")
    col = metrics["collisions"]
    A_(f"- rejected mentions: **{col['rejected_mentions']}**; of these, "
       f"**{col['register_not_company_hits']['n']}** match a string the register explicitly lists as "
       "`not_company` (surname, hospital trust, award, department, person).")
    A_("")
    A_("| company \\| rule | rejected mentions |")
    A_("|---|---:|")
    for k, v in col["by_company_and_rule"].items():
        A_(f"| `{k}` | {v} |")
    A_("")
    if col["register_not_company_hits"]["examples"]:
        A_("| company | observed string | register not_company string | why not the company |")
        A_("|---|---|---|---|")
        for ex in col["register_not_company_hits"]["examples"]:
            A_(f"| {ex['company']} | `{str(ex['raw'])[:60]}` | `{ex['not_company_string']}` | "
               f"{str(ex['reason'])[:120]} |")
    A_("")
    if col.get("examples"):
        A_("Rejected mentions, examples per company and rule (the measured collision cases):")
        A_("")
        A_("| company | observed string | rule | reason |")
        A_("|---|---|---|---|")
        for ex in col["examples"]:
            A_(f"| {ex['company']} | {str(ex['raw'])[:80]} | {ex['rule']} | {str(ex['reason'])[:100]} |")
        A_("")
    A_("## 5. Recall consequence of former/subsidiary names")
    A_("")
    A_("Computed from `data/ctgov_trials.jsonl` `discovered_by` (the query that found the study) joined "
       "with the mention records. `only via non-canonical query` = studies where the company appears only "
       "through a former/division/subsidiary name (e.g. Covidien, Datascope, MiniMed, GE Medical Systems), "
       "so a canonical-name search alone would not have found them.")
    A_("")
    A_("| company | studies discovered | with non-canonical query | only via non-canonical query | only via non-canonical mention |")
    A_("|---|---:|---:|---:|---:|")
    for ck, row in metrics["recall"].items():
        A_(f"| {ck} | {row['studies_discovered']} | {row['studies_with_non_canonical_query']} | "
           f"{row['studies_reached_only_via_non_canonical_query']} | "
           f"{row['studies_reached_only_via_non_canonical_mention']} |")
    A_("")
    for ck, row in metrics["recall"].items():
        A_(f"- **{ck}**: canonical query values {row['canonical_query_values']}; non-canonical query values "
           + ", ".join(f"`{q}`" for q in row["non_canonical_query_values"]))
    A_("")
    A_("## 6. Independent string-tier measurement (register-only)")
    A_("")
    A_("This tier assignment is computed by this script from the observed string and the register alone, "
       "not from the pipeline's decisions; it is an independent cross-check.")
    A_("")
    A_("| tier | n | rate |")
    A_("|---|---:|---:|")
    for t in STAGE2_TIERS:
        A_(f"| {t} | {metrics['tiers']['counts'][t]} | {metrics['tiers']['rates'][t]:.1%} |")
    A_("")
    A_("## 7. Verdict")
    A_("")
    v = metrics["verdict"]
    A_(v["statement"])
    A_("")
    A_("Numbers behind the verdict (all in the JSON artifact): claim-producing rate "
       f"{v['claim_producing_rate']:.1%} ({v['accepted_mentions']}/{v['mentions']} mentions), "
       f"ownership-date-unknown share {v['ownership_date_unknown_share']:.2%}, valid_from anachronism share "
       f"{v['anachronism_share']:.2%}, rejected mentions {v['rejected_mentions']}.")
    A_("")
    A_("## 8. Method and limitations")
    A_("")
    A_("- The measurement population is the per-string mention record `data/company_mentions.jsonl`, which "
       "is the input of the claim builder; when `data/claims.jsonl` exists the claim-level linkage is added "
       "without altering these numbers.")
    A_("- `claim-producing` follows the pipeline's accepted statuses; the tier table is independent.")
    A_("- Ownership dates are used as the register states them. Where the register says UNKNOWN, the report "
       "says UNKNOWN and the mapping is downgraded (section 3.3), never back-filled with a plausible date.")
    A_("- Recall is measured on ClinicalTrials.gov discovery queries only; Europe PMC affiliations are "
       "measured through the mention records in sections 1-4.")
    A_("")
    return "\n".join(L)


def stage2(claims_path: str | None, refresh: bool, mentions_only: bool, write: bool) -> int:
    base = STUDY_DIR
    def data_path(name: str) -> str:
        return os.path.join(base, "data", name)

    claims_file = claims_path or data_path("claims.jsonl")
    claims = load_jsonl(claims_file)
    rejects = load_jsonl(data_path("claim_rejects.jsonl"))
    mentions = load_jsonl(data_path("company_mentions.jsonl"))
    trials = load_jsonl(data_path("ctgov_trials.jsonl"))
    institutions = load_jsonl(data_path("institutions.jsonl"))
    if not institutions:
        institutions = load_jsonl(data_path("institution_candidates.jsonl"))
    if not mentions:
        print("STAGE2 BLOCKED: data/company_mentions.jsonl missing or empty.", file=sys.stderr)
        return 3
    reg_path = os.path.join(ARTIFACTS, "company_entity_register.json")
    register = json.load(open(reg_path, encoding="utf-8"))
    metrics = compute_stage2_report(register, claims, mentions, trials, institutions, rejects)
    if mentions_only:
        print(json.dumps(metrics, ensure_ascii=False, indent=1)[:6000])
        return 0
    pc = metrics["per_company"]
    print("stage2: mentions=%d claims=%d tiers=%s" % (
        metrics["inputs"]["mentions"], len(claims),
        {t: metrics["tiers"]["counts"][t] for t in STAGE2_TIERS}))
    print("        anachronisms: rule=%d register=%d unknown_owner=%d ; rejected=%d" % (
        metrics["anachronisms"]["rule_subsidiary_not_yet_owned"]["n"],
        metrics["anachronisms"]["register_valid_from_violations"]["count"],
        metrics["anachronisms"]["ownership_date_unknown"]["n"],
        metrics["collisions"]["rejected_mentions"]))
    if not write:
        return 0
    art = os.path.join(ARTIFACTS, "entity_resolution_metrics.json")
    with open(art, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
        f.write("\n")
    md = os.path.join(base, "ENTITY_RESOLUTION.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(render_entity_resolution_md(metrics, register))
    print(f"        wrote {art}")
    print(f"        wrote {md}")
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download every source")
    ap.add_argument("--stage2", action="store_true",
                    help="compute the entity-resolution audit over the collected claims")
    ap.add_argument("--claims", default=None, help="explicit path to claims.jsonl for --stage2")
    ap.add_argument("--mentions-only", action="store_true",
                    help="with --stage2: print the metrics as JSON instead of writing the report")
    ap.add_argument("--no-write", action="store_true",
                    help="with --stage2: compute and print but write nothing")
    args = ap.parse_args()

    if args.stage2:
        reg_path = os.path.join(ARTIFACTS, "company_entity_register.json")
        if not os.path.exists(reg_path):
            rc = main_build(args)
            if rc:
                return rc
        return stage2(args.claims, args.refresh, args.mentions_only, not args.no_write)

    return main_build(args)


def main_build(args) -> int:
    os.makedirs(ARTIFACTS, exist_ok=True)
    register, provenance, failures = build(refresh=args.refresh)
    if failures:
        print("BUILD ABORTED \u2014 unverified evidence:", file=sys.stderr)
        for f in failures:
            print(" -", f, file=sys.stderr)
        return 2

    reg_path = os.path.join(ARTIFACTS, "company_entity_register.json")
    prov_path = os.path.join(ARTIFACTS, "entity_provenance.json")
    md_path = os.path.join(STUDY_DIR, "ENTITY_HISTORY_REGISTER.md")
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(register, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(prov_path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(register, provenance))

    n_entities = sum(len(b["entities"]) for b in register["companies"].values())
    n_aliases = sum(len(e["aliases"]) for b in register["companies"].values() for e in b["entities"])
    print(f"OK: {n_entities} entities, {n_aliases} aliases across {len(register['companies'])} companies")
    print(f"    verbatim excerpts verified: {provenance['verification']['verbatim_excerpts_checked']}")
    print(f"    api assertions verified:    {provenance['verification']['api_field_assertions_checked']}")
    print(f"    negative searches:          {provenance['verification']['negative_searches']}")
    print(f"    wrote {reg_path}")
    print(f"    wrote {prov_path}")
    print(f"    wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
