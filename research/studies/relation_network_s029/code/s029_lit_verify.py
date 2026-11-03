#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s029_lit_verify.py -- verified reference corpus for S-029 (MedRadar).

WHY THIS SCRIPT EXISTS
----------------------
S-028 (the predecessor study) ended with a public correction
(``LITERATURE_CORRECTION_NOTE.md``, S-028-CORRECTION-1) after a paper that
*does* exist was reported as non-existent, and after six remembered DOIs
turned out to be wrong.  The lesson enforced here is mechanical:

    A reference enters the review only if a machine fetched a live metadata
    record for it, and the review quotes only the fields that record contained.

No DOI, title, author or year in ``LITERATURE_REVIEW.md`` is written from
memory.  The candidate list below is *only a search intent*: each candidate is
resolved against Crossref, and the authoritative record is then re-fetched
by DOI and stored verbatim.  If resolution fails, the candidate is recorded as
unresolved and is NOT citable.

WHAT IT DOES
------------
1. Resolve: Crossref ``query.bibliographic`` search -> best title match
   (>=0.50 Jaccard OR >=0.80 SequenceMatcher) with an author/year sanity check.
2. Verify: ``GET https://api.crossref.org/works/{doi}`` and store exactly what
   came back (title, authors, year, venue, type, publisher, ISSN).
3. Cross-check: Europe PMC ``DOI:"..."`` lookup (biomedical coverage) and one
   batched OpenAlex ``filter=doi:a|b|c`` call (<=25 DOIs per call, 2 calls max)
   which also supplies abstracts via ``abstract_inverted_index``.
4. Coverage queries: a fixed set of Crossref searches whose *misses* are what
   the review's "we did not find X" statements are allowed to rest on.  The
   queries are stored, so the negative claim is search-scoped, never absolute.
5. Write artifacts/literature_refs.json, artifacts/lit_abstracts.json and
   artifacts/lit_diagnostics.json.

RATE LIMITS (self-imposed, from the S-029 brief)
------------------------------------------------
Crossref: polite pool (``mailto=medradar.research@proton.me``), 0.30 s between
calls.  Europe PMC: <=2 req/s -> 0.60 s between calls.  OpenAlex: shared
unauthenticated budget, hard cap 25 requests and <=25 DOIs per batch request;
this script uses 2.

RE-RUNNABILITY
--------------
``python s029_lit_verify.py`` re-fetches everything and rewrites all three
artifacts.  Only ``*_utc`` timestamps (and, if upstream records changed, the
metadata itself) can differ between runs; the reference set, the DOIs and the
stored field values are a deterministic function of the upstream records.
``--offline-check`` validates the written JSON without network access:
required fields, hash format, one record per DOI, no unresolved entry in the
citable list, counts consistent.

CLI
---
    python s029_lit_verify.py                     # full resolve + verify
    python s029_lit_verify.py --only R01,R29      # debug a subset
    python s029_lit_verify.py --discover "query"  # print Crossref top hits
    python s029_lit_verify.py --offline-check     # validate artifacts
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import difflib
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

MAILTO = "medradar.research@proton.me"
UA = f"s029-lit-verify/1.0 (MedRadar; mailto:{MAILTO})"

CROSSREF = "https://api.crossref.org"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
OPENALEX = "https://api.openalex.org"

DELAY_CROSSREF = 0.30
DELAY_EPMC = 0.60
DELAY_OPENALEX = 1.00

OPENALEX_MAX_REQUESTS = 25          # brief: hard cap for this study
OPENALEX_BATCH = 25                 # brief: <=25 DOIs per filter request

STUDY_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY_DIR / "artifacts"

REF_JACCARD = 0.50
REF_RATIO = 0.80

# --------------------------------------------------------------------------
# candidate list
# --------------------------------------------------------------------------
# ``query`` is the search intent, NOT a bibliographic assertion.  The record
# that is finally stored is whatever the resolver returns, after the match
# gate below accepts it as the intended work.  ``author`` and ``year`` are
# sanity checks only.
#
# category keys:
#   science_of_science, knowledge_diffusion, university_industry,
#   collaboration_networks, temporal_networks, translational_lag,
#   clinical_networks, technology_transfer, entity_resolution,
#   temporal_kg_provenance, measurement_error, medical_device
# --------------------------------------------------------------------------

CANDIDATES = [
    # ---------------- science of science (4) ----------------
    dict(id="R01", cat="science_of_science", author="Fortunato", year=2018,
         query="Science of science", doi_hint="10.1126/science.aao0185",
         role="canonical review of the field; what counts as a "
              "science-of-science measurement"),
    dict(id="R02", cat="science_of_science", author="Clauset", year=2017,
         query="Data-driven predictions in the science of science",
         role="prediction-vs-explanation framing; the observable record is a "
              "biased sample of science"),
    dict(id="R03", cat="science_of_science", author="Hicks", year=2015,
         query="Bibliometrics: the Leiden Manifesto for research metrics",
         doi_hint="10.1038/520429a",
         role="explicit limits on what bibliometric indicators may be used to "
              "claim"),
    dict(id="R04", cat="science_of_science", author="Martín", year=2021,
         query="Google Scholar, Microsoft Academic, Scopus, Dimensions, Web of "
               "Science, and OpenCitations COCI: a multidisciplinary "
               "comparison of coverage via citations",
         doi_hint="10.1007/s11192-020-03690-4",
         role="measured disagreement between bibliographic infrastructures; "
              "the size of the measurement-error problem"),

    # ---------------- knowledge diffusion / spillover (5) ----------------
    dict(id="R05", cat="knowledge_diffusion", author="Jaffe", year=1993,
         query="Geographic localization of knowledge spillovers as evidenced "
               "by patent citations", doi_hint="10.2307/2118401",
         role="the founding proxy: citations treated as spillover; origin of "
              "the matching-control design"),
    dict(id="R06", cat="knowledge_diffusion", author="Keller", year=2004,
         query="International technology diffusion",
         doi_hint="10.1257/0022051042177685",
         role="review concluding diffusion is neither automatic nor "
              "universal"),
    dict(id="R07", cat="knowledge_diffusion", author="Azoulay", year=2010,
         query="Superstar extinction", doi_hint="10.1162/qjec.2010.125.2.549",
         role="co-author death design: a rare causal estimate of knowledge "
              "flow through collaboration ties"),
    dict(id="R08", cat="knowledge_diffusion", author="Narin", year=1997,
         query="The increasing linkage between U.S. technology and public "
               "science",
         role="non-patent references as the science-technology linkage "
              "indicator"),
    dict(id="R09", cat="knowledge_diffusion", author="Wijk", year=2008,
         query="Inter- and intra-organizational knowledge transfer: a "
               "meta-analytic review and assessment of its antecedents and "
               "consequences",
         role="what the knowledge-transfer literature actually measures and "
              "how often it measures it with proxies"),

    # ---------------- university-industry (4) ----------------
    dict(id="R10", cat="university_industry", author="Perkmann", year=2013,
         query="Academic engagement and commercialisation: a review of the "
               "literature on university-industry relations",
         doi_hint="10.1016/j.respol.2012.09.007",
         role="separates engagement channels from commercialisation; relation "
              "taxonomy"),
    dict(id="R11", cat="university_industry", author="Cohen", year=2002,
         query="Links and impacts: the influence of public research on "
               "industrial R&D", doi_hint="10.1287/mnsc.48.1.1.14273",
         role="survey evidence that public research matters through channels "
              "that leave no bibliographic trace"),
    dict(id="R12", cat="university_industry", author="Bekkers", year=2008,
         query="Analysing knowledge transfer channels between universities "
               "and industry: to what degree do sectors also matter?",
         role="enumerates transfer channels; channel choice is "
              "sector-dependent"),
    dict(id="R13", cat="university_industry", author="Mansfield", year=1991,
         query="Academic research and industrial innovation",
         role="firm survey of the lag from academic research to industrial "
              "innovation; a human-truth lag estimate"),

    # ---------------- collaboration networks (5) ----------------
    dict(id="R14", cat="collaboration_networks", author="Katz", year=1997,
         query="What is research collaboration?",
         role="definitional critique: co-authorship measures one narrow form "
              "of collaboration"),
    dict(id="R15", cat="collaboration_networks", author="Laudel", year=2002,
         query="What do we measure by co-authorship?",
         role="interview-based evidence that co-authorship and collaboration "
              "diverge in both directions; a human-truth benchmark"),
    dict(id="R16", cat="collaboration_networks", author="Newman", year=2001,
         query="Scientific collaboration networks. I. Network construction "
               "and fundamental results",
         role="how a co-authorship network is built (nodes, edges, time "
              "window) and what its statistics mean"),
    dict(id="R17", cat="collaboration_networks", author="Newman", year=2004,
         query="Coauthorship networks and patterns of scientific "
               "collaboration",
         role="co-authorship as a network object; the template most "
              "'collaboration network' studies copy"),
    dict(id="R18", cat="collaboration_networks", author="Powell", year=1996,
         query="Interorganizational collaboration and the locus of "
               "innovation: networks of learning in biotechnology",
         role="firm-firm alliance network as a knowledge channel; the "
              "organisational-network template"),

    # ---------------- temporal networks (1) ----------------
    dict(id="R19", cat="temporal_networks", author="Holme", year=2012,
         query="Temporal networks", doi_hint="10.1016/j.physrep.2012.03.001",
         role="formal treatment of time-resolved networks; why aggregating "
              "over time destroys information"),

    # ---------------- translational lag (3) ----------------
    dict(id="R20", cat="translational_lag", author="Morris", year=2011,
         query="The answer is 17 years, what is the question: understanding "
               "time lags in translational research",
         role="canonical translational-lag review; source of the '17 years' "
              "figure that S-029 must not re-cite blindly"),
    dict(id="R21", cat="translational_lag", author="Contopoulos",
         year=2008,
         query="Life cycle of translational research for medical "
               "interventions",
         role="hand-traced discovery-to-guideline trajectories; the closest "
              "human-truth design for a translational relation"),
    dict(id="R22", cat="translational_lag", author="Macleod", year=2014,
         query="Biomedical research: increasing value, reducing waste",
         doi_hint="10.1016/S0140-6736(13)62329-6",
         role="where the research pipeline loses value; supports treating "
              "non-arrival as a measurable outcome"),

    # ---------------- clinical research networks / registries (4) --------
    dict(id="R23", cat="clinical_networks", author="Zarin", year=2011,
         query="The ClinicalTrials.gov results database: update and key "
               "issues",
         role="the registry as a data source; completeness and definitional "
              "problems of a public trial record"),
    dict(id="R24", cat="clinical_networks", author="Ross", year=2009,
         query="Trial publication after registration in ClinicalTrials.gov: a "
               "cross-sectional analysis",
         role="registry-to-publication link measured record by record; the "
              "template for a 'registered but never published' relation"),
    dict(id="R25", cat="clinical_networks", author="Jones", year=2015,
         query="Non-publication of large randomized clinical trials: cross "
               "sectional analysis",
         role="quantifies non-publication; absence of a publication is not "
              "absence of a study"),
    dict(id="R26", cat="clinical_networks", author="Zarin", year=2016,
         query="Trial reporting in ClinicalTrials.gov: the final rule",
         role="the reporting regime and its timeline; registry fields changed "
              "meaning over time"),

    # ---------------- technology transfer (3) ----------------
    dict(id="R27", cat="technology_transfer", author="Mowery", year=2001,
         query="The growth of patenting and licensing by U.S. universities: an "
               "assessment of the effects of the Bayh-Dole Act of 1980",
         role="university patenting/licensing trends; transfer is inferred "
              "from administrative records"),
    dict(id="R28", cat="technology_transfer", author="Thursby", year=2002,
         query="Who is selling the ivory tower? Sources of growth in "
               "university licensing", doi_hint="10.1287/mnsc.48.1.90.14271",
         role="licensing survey; measures the transfer event rather than a "
              "bibliographic proxy"),
    dict(id="R29", cat="technology_transfer", author="Salter", year=2001,
         query="The economic benefits of publicly funded basic research: a "
               "critical review",
         role="critical review of the evidence behind 'public research "
              "benefits industry' claims"),

    # ---------------- entity resolution / name disambiguation (5) --------
    dict(id="R30", cat="entity_resolution", author="Ferreira", year=2012,
         query="A brief survey of automatic methods for author name "
               "disambiguation",
         role="the disambiguation problem statement: same name -> different "
              "people, one person -> many name strings"),
    dict(id="R31", cat="entity_resolution", author="Smalheiser", year=2009,
         query="Author name disambiguation",
         via="openalex", doi_hint="10.1002/aris.2009.1440430113",
         role="review of disambiguation evidence and error sources"),
    dict(id="R32", cat="entity_resolution", author="Tekles", year=2020,
         query="Author name disambiguation of bibliometric data: a comparison "
               "of several unsupervised approaches",
         role="benchmarked against a manual gold standard; reported accuracy "
              "depends on the truth set"),
    dict(id="R33", cat="entity_resolution", author="Getoor", year=2012,
         query="Entity resolution: theory, practice and open challenges",
         doi_hint="10.14778/2367502.2367564",
         role="general ER framing (blocking, matching, clustering) that "
              "institution-level resolution inherits"),
    dict(id="R34", cat="entity_resolution", author="Peroni", year=2015,
         query="Setting our bibliographic references free: towards open "
               "citation data",
         role="open citation infrastructure; provenance of a link is an "
              "explicit object, not an afterthought"),

    # ---------------- temporal knowledge graphs / provenance (4) ---------
    dict(id="R35", cat="temporal_kg_provenance", author="Gottschalk",
         year=2018,
         query="EventKG: a multilingual event-centric temporal knowledge graph",
         role="event-centric temporal KG with explicit temporal scopes; the "
              "closest construction precedent for dated relations"),
    dict(id="R36", cat="temporal_kg_provenance", author="Cheney", year=2009,
         query="Provenance in databases: why, how, and where",
         doi_hint="10.1561/1900000006",
         role="formal provenance semantics: why/how/where"),
    dict(id="R37", cat="temporal_kg_provenance", author="Herschel", year=2017,
         query="A survey on provenance: what for? what form? what from?",
         role="provenance dimensions across workflows; separates source, "
              "process and use provenance"),
    dict(id="R38", cat="temporal_kg_provenance", author="Wilkinson",
         year=2016,
         query="The FAIR Guiding Principles for scientific data management and "
               "stewardship", doi_hint="10.1038/sdata.2016.18",
         role="findability/accessibility/interoperability/reuse as the "
              "minimum standard for a reusable evidence base"),

    # ---------------- measurement error / infrastructure quality (3) -----
    dict(id="R39", cat="measurement_error", author="Wang", year=2012,
         query="Measurement error in network data: a re-classification",
         role="taxonomy of how network data are wrong (node, edge, timing)"),
    dict(id="R40", cat="measurement_error", author="Priem", year=2022,
         query="OpenAlex: a fully-open index of scholarly works, authors, "
               "venues, institutions, and concepts",
         via="openalex", doi_hint="10.48550/arXiv.2205.01833",
         role="coverage claims of the open index, in the index's own words"),
    dict(id="R41", cat="measurement_error", author="Buneman", year=2001,
         query="Why and where: a characterization of data provenance",
         doi_hint="10.1007/3-540-44503-x_20",
         role="why-provenance vs where-provenance; source attribution vs "
              "derivation"),

    # ---------------- medical device / FDA pathway (4) ------------------
    dict(id="R42", cat="medical_device", author="Zuckerman", year=2011,
         query="Medical device recalls and the FDA approval process",
         role="closest empirical device work: recall outcomes by approval "
              "pathway"),
    dict(id="R43", cat="medical_device", author="Ardaugh", year=2013,
         query="The 510(k) ancestry of a metal-on-metal hip implant",
         role="traces a device's predicate lineage; a rare hand-built "
              "regulatory-ancestry graph"),
    dict(id="R44", cat="medical_device", author="Kramer", year=2012,
         query="Regulation of medical devices in the United States and "
               "European Union", doi_hint="10.1056/NEJMhle1113918",
         role="the device pathway taxonomy (510(k)/PMA/De Novo) that event "
              "typing depends on"),
    dict(id="R45", cat="medical_device", author="Dhruva", year=2009,
         query="Strength of study evidence examined by the FDA in premarket "
               "approval of cardiovascular devices",
         doi_hint="10.1001/jama.2009.1899",
         role="what evidence supports a high-risk device approval; the "
              "measurement ceiling on any 'clinical study' relation"),

]


# Fixed coverage queries.  Their purpose is the *negative* claim in the
# review: "we did not find X in the verified corpus of N works located with
# these queries".  They are run on every full run and stored with their hits.
COVERAGE_QUERIES = [
    ("knowledge transfer direction from co-authorship",
     "co-authorship direction of knowledge flow inference"),
    ("bench to bedside lag measurement",
     "translational research lag measurement publication to practice"),
    ("clinical trial network co-participation knowledge",
     "clinical trial site network co-participation industry"),
    ("medical device regulatory pathway evidence",
     "medical device premarket approval clinical evidence outcomes"),
    ("temporal provenance knowledge graph construction",
     "temporal knowledge graph construction provenance evidence"),
    ("affiliation-based attribution error",
     "author affiliation disambiguation attribution error bibliometrics"),
]

# --------------------------------------------------------------------------
# http plumbing
# --------------------------------------------------------------------------


class _Calls:
    """Counters and a timestamped log of every outbound HTTP call."""

    def __init__(self):
        self.count = {"crossref": 0, "europepmc": 0, "openalex": 0}
        self.log = []

    def bump(self, source):
        self.count[source] += 1

    def record(self, source, url, status, nbytes, note=""):
        self.log.append({
            "source": source,
            "url": url,
            "http_status": status,
            "bytes": nbytes,
            "utc": utc_now(),
            "note": note,
        })


CALLS = _Calls()
_LAST = {"crossref": 0.0, "europepmc": 0.0, "openalex": 0.0}
_DELAY = {"crossref": DELAY_CROSSREF, "europepmc": DELAY_EPMC,
          "openalex": DELAY_OPENALEX}


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _throttle(source: str) -> None:
    dt = time.monotonic() - _LAST[source]
    if dt < _DELAY[source]:
        time.sleep(_DELAY[source] - dt)


def http_get(url: str, source: str, timeout: int = 45, retries: int = 2):
    """GET url, return dict(status, body_bytes, text, url, content_type, error).

    Never raises: a failed fetch is data (it goes into the diagnostics file).
    """
    _throttle(source)
    result = {"status": None, "body": b"", "text": "", "url": url,
              "content_type": "", "error": None}
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                result.update(status=resp.status, body=body,
                              text=body.decode("utf-8", "replace"),
                              url=resp.geturl(),
                              content_type=resp.headers.get("content-type", ""))
                CALLS.bump(source)
                CALLS.record(source, url, resp.status, len(body))
                _LAST[source] = time.monotonic()
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read() or b""
            result.update(status=exc.code, body=body,
                          text=body.decode("utf-8", "replace"),
                          url=url, error=f"HTTP {exc.code}")
            CALLS.bump(source)
            CALLS.record(source, url, exc.code, len(body), note="http error")
            _LAST[source] = time.monotonic()
            if exc.code == 429:          # back off politely, then retry
                time.sleep(3.0 + 2.0 * attempt)
                continue
            if exc.code in (400, 401, 403, 404):
                return result
        except Exception as exc:  # noqa: BLE001 - network is untrusted
            result.update(error=f"{type(exc).__name__}: {exc}")
        time.sleep(1.0 + attempt)
    CALLS.record(source, url, None, 0, note="exhausted retries")
    return result


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def json_load(text: str):
    try:
        return json.loads(text), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# title matching
# --------------------------------------------------------------------------


def norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(s.split())


def title_jaccard(a: str, b: str) -> float:
    A, B = set(norm_title(a).split()), set(norm_title(b).split())
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def title_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def title_score(expected: str, got: str) -> float:
    return max(title_jaccard(expected, got), title_ratio(expected, got))


def family_names(nodes) -> list:
    out = []
    for n in nodes or []:
        if isinstance(n, dict):
            fam = n.get("family") or n.get("name") or ""
            if not fam and n.get("literal"):
                fam = n["literal"]
        else:
            fam = str(n)
        if fam:
            out.append(fam)
    return out


# --------------------------------------------------------------------------
# source adapters
# --------------------------------------------------------------------------


def crossref_search(query: str, rows: int = 5, author: str = ""):
    params = {
        "query.bibliographic": query,
        "rows": str(rows),
        "select": "DOI,title,author,issued,container-title,type,score",
        "mailto": MAILTO,
    }
    if author:
        params["query.author"] = author
    url = f"{CROSSREF}/works?" + urllib.parse.urlencode(params)
    r = http_get(url, "crossref")
    payload, err = json_load(r["text"])
    items = []
    if payload:
        for it in (payload.get("message", {}) or {}).get("items", []) or []:
            items.append({
                "doi": (it.get("DOI") or "").lower(),
                "title": (it.get("title") or [""])[0],
                "authors": family_names(it.get("author")),
                "year": _crossref_year(it),
                "venue": (it.get("container-title") or [""])[0],
                "type": it.get("type"),
                "score": it.get("score"),
            })
    return {"url": url, "status": r["status"], "error": err or r["error"],
            "items": items, "sha256": sha256_hex(r["body"])}


def _crossref_year(it: dict):
    for key in ("issued", "published-print", "published-online", "created"):
        parts = (it.get(key) or {}).get("date-parts") or [[]]
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def crossref_verify(doi: str):
    """Fetch the authoritative Crossref record for a DOI."""
    raw_url = f"{CROSSREF}/works/{doi}"
    attempts = [raw_url, f"{CROSSREF}/works/{urllib.parse.quote(doi, safe='')}"]
    last = None
    for i, url in enumerate(attempts):
        q = url + ("?mailto=" + MAILTO if "?" not in url else "&mailto=" + MAILTO)
        r = http_get(q, "crossref")
        payload, err = json_load(r["text"])
        if r["status"] == 200 and payload and payload.get("message"):
            return _crossref_entry(payload["message"], q, r, err)
        last = _crossref_entry(None, q, r, err or f"HTTP {r['status']}")
        if r["status"] not in (404, 400):
            break
    return last


def _crossref_entry(msg, url, r, err):
    if not msg:
        return {"api": "crossref", "url": url, "http_status": r["status"],
                "retrieved_utc": utc_now(), "payload_sha256": sha256_hex(r["body"]),
                "payload_bytes": len(r["body"]), "ok": False,
                "error": err or "no message"}
    authors = []
    for a in msg.get("author") or []:
        authors.append({
            "family": a.get("family"),
            "given": a.get("given"),
            "literal": a.get("literal"),
            "sequence": a.get("sequence"),
            "orcid": a.get("ORCID"),
            "affiliation": [x.get("name") for x in (a.get("affiliation") or [])
                            if x.get("name")],
        })
    year = _crossref_year(msg)
    return {
        "api": "crossref",
        "url": url,
        "http_status": r["status"],
        "retrieved_utc": utc_now(),
        "payload_sha256": sha256_hex(r["body"]),
        "payload_bytes": len(r["body"]),
        "payload_snippet": r["body"][:300].decode("utf-8", "replace"),
        "ok": True,
        "error": None,
        "doi": (msg.get("DOI") or "").lower(),
        "title": (msg.get("title") or [""])[0],
        "subtitle": (msg.get("subtitle") or [""])[0] if msg.get("subtitle") else "",
        "authors": authors,
        "year": year,
        "issued": (msg.get("issued") or {}).get("date-parts"),
        "published_online": (msg.get("published-online") or {}).get("date-parts"),
        "published_print": (msg.get("published-print") or {}).get("date-parts"),
        "venue": (msg.get("container-title") or [""])[0],
        "publisher": msg.get("publisher"),
        "type": msg.get("type"),
        "issn": msg.get("ISSN") or [],
        "isbn": msg.get("ISBN") or [],
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "page": msg.get("page"),
        "record_created": (msg.get("created") or {}).get("date-time"),
        "record_deposited": (msg.get("deposited") or {}).get("date-time"),
        "abstract_present": bool(msg.get("abstract")),
        "abstract": msg.get("abstract"),
        "resource_url": (msg.get("resource") or {}).get("primary", {}).get("URL"),
        "reference_count": msg.get("reference-count"),
        "is_referenced_by_count": msg.get("is-referenced-by-count"),
    }


def epmc_lookup_doi(doi: str):
    q = f'DOI:"{doi}"'
    url = (f"{EPMC}/search?" + urllib.parse.urlencode(
        {"query": q, "format": "json", "resultType": "core", "pageSize": "3"}))
    r = http_get(url, "europepmc")
    payload, err = json_load(r["text"])
    hits = []
    if payload:
        hits = ((payload.get("resultList") or {}).get("result") or [])
    entry = {
        "api": "europepmc",
        "url": url,
        "http_status": r["status"],
        "retrieved_utc": utc_now(),
        "payload_sha256": sha256_hex(r["body"]),
        "payload_bytes": len(r["body"]),
        "ok": bool(hits),
        "error": err or r["error"],
        "hit_count": len(hits),
    }
    if hits:
        h = hits[0]
        entry.update({
            "doi": (h.get("doi") or "").lower(),
            "title": h.get("title") or "",
            "authors": h.get("authorString") or "",
            "year": h.get("pubYear"),
            "venue": h.get("journalTitle") or h.get("bookOrReportDetails") or "",
            "pmid": h.get("pmid"),
            "pmcid": h.get("pmcid"),
            "first_publication_date": h.get("firstPublicationDate"),
            "first_index_date": h.get("firstIndexDate"),
            "abstract": h.get("abstractText"),
        })
    return entry


def openalex_batch(dois: list):
    """One OpenAlex request for <=25 DOIs. Returns dict doi -> record."""
    clean = [d for d in dois if d][:OPENALEX_BATCH]
    if not clean:
        return {"url": None, "records": {}, "ok": False, "error": "empty batch"}
    filt = "doi:" + "|".join(clean)
    params = {
        "filter": filt,
        "per-page": str(len(clean) * 2),
        "select": ("id,doi,title,publication_year,authorships,primary_location,"
                   "abstract_inverted_index,type,biblio,cited_by_count"),
        "mailto": MAILTO,
    }
    url = f"{OPENALEX}/works?" + urllib.parse.urlencode(params)
    r = http_get(url, "openalex")
    payload, err = json_load(r["text"])
    records = {}
    if payload:
        for w in payload.get("results", []) or []:
            doi = (w.get("doi") or "").lower()
            doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
            records[doi] = w
    return {
        "url": url,
        "ok": bool(payload),
        "error": err or r["error"],
        "http_status": r["status"],
        "retrieved_utc": utc_now(),
        "payload_sha256": sha256_hex(r["body"]),
        "payload_bytes": len(r["body"]),
        "records": records,
    }


def openalex_abstract(inv_idx) -> str:
    if not inv_idx:
        return ""
    pos = {}
    for word, positions in inv_idx.items():
        for p in positions:
            pos[p] = word
    return " ".join(pos[k] for k in sorted(pos))


def openalex_entry(rec: dict, url: str, sha: str, status, utc: str) -> dict:
    if not rec:
        return {"api": "openalex", "url": url, "http_status": status,
                "retrieved_utc": utc, "payload_sha256": sha, "ok": False,
                "error": "doi not returned by OpenAlex"}
    auth = []
    for a in rec.get("authorships") or []:
        auth.append({
            "name": a.get("author", {}).get("display_name"),
            "position": a.get("author_position"),
            "institutions": [i.get("display_name") for i in
                             (a.get("institutions") or [])],
        })
    return {
        "api": "openalex",
        "url": url,
        "http_status": status,
        "retrieved_utc": utc,
        "payload_sha256": sha,
        "ok": True,
        "openalex_id": rec.get("id"),
        "doi": (rec.get("doi") or "").lower(),
        "title": rec.get("title"),
        "authors": auth,
        "year": rec.get("publication_year"),
        "venue": ((rec.get("primary_location") or {}).get("source") or {})
                 .get("display_name"),
        "type": rec.get("type"),
        "cited_by_count": rec.get("cited_by_count"),
        "abstract": openalex_abstract(rec.get("abstract_inverted_index")),
    }


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------


def _resolve_openalex(cand: dict):
    """Verify a work directly against OpenAlex (used where Crossref has no
    record, e.g. an arXiv DOI).  The same author + title gates apply."""
    doi = cand["doi_hint"]
    url = (f"{OPENALEX}/works/doi:{urllib.parse.quote(doi, safe='/:')}"
           "?select=id,doi,title,publication_year,authorships,"
           "primary_location,abstract_inverted_index,type,biblio,"
           f"cited_by_count&mailto={MAILTO}")
    r = http_get(url, "openalex")
    payload, err = json_load(r["text"])
    diag = {"candidate_query": cand["query"], "stage": "openalex_doi",
            "doi_hint": doi,
            "search": {"url": url, "http_status": r["status"],
                       "sha256": sha256_hex(r["body"]), "items": []}}
    if not payload or not payload.get("id"):
        return None, diag, (f"OpenAlex lookup failed: "
                            f"{err or r.get('error') or r['status']}")
    title = payload.get("title") or ""
    ts = title_score(cand["query"], title)
    ratio = title_ratio(cand["query"], title)
    auth = [{"name": (a.get("author") or {}).get("display_name"),
             "orcid": (a.get("author") or {}).get("orcid"),
             "institutions": [i.get("display_name")
                              for i in (a.get("institutions") or [])]}
            for a in payload.get("authorships") or []]
    fams = " ".join((a.get("name") or "") for a in auth).lower()
    venue = (((payload.get("primary_location") or {}).get("source") or {})
             .get("display_name"))
    diag["title_score"] = round(ts, 4)
    diag["best_hit"] = {
        "doi": (payload.get("doi") or "").replace("https://doi.org/", ""),
        "title": title, "authors": [a.get("name") for a in auth],
        "year": payload.get("publication_year"), "venue": venue}
    if ts < REF_JACCARD and ratio < REF_RATIO:
        return None, diag, f"title gate failed (title score {ts:.3f})"
    if cand.get("author") and cand["author"].lower() not in fams:
        return None, diag, "author hint absent from OpenAlex record"
    clean_doi = ((payload.get("doi") or "").replace("https://doi.org/", "")
                 .lower())
    ver = {
        "api": "openalex", "url": url, "http_status": r["status"],
        "retrieved_utc": utc_now(), "payload_sha256": sha256_hex(r["body"]),
        "payload_bytes": len(r["body"]),
        "payload_snippet": r["body"][:300].decode("utf-8", "replace"),
        "ok": True, "error": None,
        "doi": clean_doi or doi.lower(), "title": title, "authors": auth,
        "year": payload.get("publication_year"), "venue": venue,
        "type": payload.get("type"), "publisher": None,
        "record_created": None, "record_deposited": None,
        "abstract_present": bool(payload.get("abstract_inverted_index")),
        "abstract": openalex_abstract(payload.get("abstract_inverted_index")),
        "resource_url": None, "openalex_id": payload.get("id"),
        "cited_by_count": payload.get("cited_by_count"),
        "reference_count": None, "is_referenced_by_count": None,
        "volume": (payload.get("biblio") or {}).get("volume"),
        "issue": (payload.get("biblio") or {}).get("issue"),
        "page": (payload.get("biblio") or {}).get("first_page"),
    }
    diag["openalex_verification"] = ver
    hit = {"doi": ver["doi"], "title": title,
           "authors": [a.get("name") for a in auth],
           "year": payload.get("publication_year"), "venue": venue,
           "type": payload.get("type")}
    return hit, diag, None


def resolve_candidate(cand: dict):
    """Return (hit, diagnostics, failure_reason).

    Resolution order:
      1. ``via="openalex"``: verify the DOI directly against OpenAlex (only
         for works Crossref does not index).
      2. ``doi_hint`` (a remembered identifier, used ONLY as a lookup hint):
         fetch it and accept only if the returned title still matches the
         search intent. A wrong hint therefore cannot smuggle in a different
         paper -- the title (and author) gate rejects it.
      3. Crossref ``query.bibliographic`` (+ ``query.author`` if given).
    """
    if cand.get("via") == "openalex":
        return _resolve_openalex(cand)
    if cand.get("doi_hint"):
        ver = crossref_verify(cand["doi_hint"])
        if ver.get("ok"):
            ts = title_score(cand["query"], ver.get("title") or "")
            ratio = title_ratio(cand["query"], ver.get("title") or "")
            fams = " ".join(f.get("family") or f.get("literal") or ""
                            for f in (ver.get("authors") or [])).lower()
            hint_author_ok = (not cand.get("author") or
                              cand["author"].lower() in fams)
            nq = norm_title(cand["query"])
            nt = norm_title(ver.get("title") or "")
            prefix_ok = bool(nt) and (nq.startswith(nt) or nt.startswith(nq))
            yh, yr = cand.get("year"), ver.get("year")
            year_ok = (yh is None or yr is None or abs(int(yr) - int(yh)) <= 3)
            sim_ok = ts >= REF_JACCARD or ratio >= REF_RATIO
            # A verified DOI whose deposited title is a truncated form of the
            # intended title (e.g. VLDB deposits "Entity resolution" for
            # "Entity Resolution: Theory, Practice & Open Challenges") is
            # accepted only when authors AND year also agree.
            if hint_author_ok and (sim_ok or (prefix_ok and year_ok)):
                diag = {"candidate_query": cand["query"],
                        "stage": "doi_hint_verified",
                        "doi_hint": cand["doi_hint"],
                        "search": {"url": ver["url"],
                                   "http_status": ver["http_status"],
                                   "sha256": ver["payload_sha256"],
                                   "items": []},
                        "best_hit": {"doi": ver["doi"], "title": ver["title"],
                                     "authors": [f.get("family") for f in
                                                 (ver.get("authors") or [])],
                                     "year": ver.get("year"),
                                     "venue": ver.get("venue")},
                        "title_score": round(ts, 4),
                        "title_gate": "similarity" if sim_ok else "prefix",
                        "author_match": bool(cand.get("author")) and
                                        cand["author"].lower() in fams,
                        "year_match": True,
                        "doi_hint_record": ver}
                return diag["best_hit"], diag, None
            diag = {"candidate_query": cand["query"],
                    "stage": "doi_hint_rejected",
                    "doi_hint": cand["doi_hint"],
                    "title_score": round(ts, 4),
                    "doi_hint_title": ver.get("title"),
                    "search": {"url": ver["url"],
                               "http_status": ver["http_status"],
                               "sha256": ver["payload_sha256"], "items": []}}
            # fall through to a normal search
            search = crossref_search(cand["query"], rows=5,
                                     author=cand.get("query_author", ""))
            diag["search"] = {"url": search["url"],
                              "http_status": search["status"],
                              "sha256": search["sha256"],
                              "items": search["items"]}
            return _pick_from_items(cand, search, diag)
    search = crossref_search(cand["query"], rows=5,
                             author=cand.get("query_author", ""))
    diag = {"candidate_query": cand["query"], "stage": "crossref_search",
            "search": {"url": search["url"],
                       "http_status": search["status"],
                       "sha256": search["sha256"],
                       "items": search["items"]}}
    return _pick_from_items(cand, search, diag)


def _pick_from_items(cand: dict, search: dict, diag: dict):
    """Choose the best Crossref hit and apply the match gate.

    The author hint, when the candidate supplies one, is a HARD gate: a title
    that is similar but written by different people is a different work.  This
    is what rejects, e.g., a Lancet comment whose title is a near-substring of
    the intended article.
    """
    ranked = []
    for it in search.get("items") or []:
        if not it.get("doi"):
            continue
        ts = title_score(cand["query"], it.get("title") or "")
        fams = [f.lower() for f in it.get("authors") or []]
        amatch = bool(cand.get("author")) and any(
            cand["author"].lower() in f for f in fams)
        ymatch = (cand.get("year") is not None and it.get("year") is not None
                  and abs(int(it["year"]) - int(cand["year"])) <= 3)
        key = ts + 0.10 * amatch + 0.05 * ymatch
        ranked.append((key, ts, it, amatch, ymatch))
    if not ranked:
        return None, diag, "no crossref hits"
    ranked.sort(key=lambda x: x[0], reverse=True)
    diag["top_hits_considered"] = [r[2] for r in ranked[:5]]
    rejected = []
    for _, ts, it, amatch, ymatch in ranked:
        if cand.get("author") and not amatch:
            rejected.append({"doi": it["doi"], "title": it.get("title"),
                             "why": "author hint absent from retrieved record"})
            continue
        gate = (ts >= REF_JACCARD or
                title_ratio(cand["query"], it["title"]) >= REF_RATIO)
        if not gate:
            rejected.append({"doi": it["doi"], "title": it.get("title"),
                             "why": f"title score {ts:.3f} below gate"})
            continue
        diag["best_hit"] = it
        diag["title_score"] = round(ts, 4)
        diag["author_match"] = amatch
        diag["year_match"] = ymatch
        diag["rejected_hits"] = rejected
        return it, diag, None
    diag["best_hit"] = ranked[0][2]
    diag["rejected_hits"] = rejected
    return None, diag, "no hit passed the author + title gate"


def build_reference(cand: dict, hit: dict, diag: dict) -> dict:
    ver = (diag.get("doi_hint_record")
           or diag.get("openalex_verification")
           or crossref_verify(hit["doi"]))
    entry = {
        "id": cand["id"],
        "category": cand["cat"],
        "role_in_s029": cand.get("role", ""),
        "doi": hit["doi"].lower(),
        "resolver": {
            "stage": diag.get("stage", "crossref_query_bibliographic"),
            "candidate_query": cand["query"],
            "candidate_author_hint": cand.get("author"),
            "candidate_year_hint": cand.get("year"),
            "query_url": diag["search"]["url"],
            "query_sha256": diag["search"]["sha256"],
            "title_score_vs_query": diag.get("title_score"),
            "author_hint_matched": diag.get("author_match"),
            "year_hint_matched": diag.get("year_match"),
            "top_hits_considered": diag["search"]["items"][:5],
        },
        "verification": ver,
        "title_exact": ver.get("title") if ver.get("ok") else None,
        "title_display": clean_title(ver.get("title")) if ver.get("ok") else None,
        "authors_exact": ver.get("authors") if ver.get("ok") else None,
        "year_exact": ver.get("year") if ver.get("ok") else None,
        "venue_exact": ver.get("venue") if ver.get("ok") else None,
        "type_exact": ver.get("type") if ver.get("ok") else None,
        "publisher_exact": ver.get("publisher") if ver.get("ok") else None,
        "metadata_notes": (
            "Deposited title is a truncated form of the intended title; "
            "acceptance required author and year agreement "
            "(resolver.title_gate=prefix)."
            if diag.get("title_gate") == "prefix" else None),
        "cross_checks": [],
        "abstract": None,
        "claim_scope": "metadata",
        "status": "verified" if ver.get("ok") else "verify_failed",
    }
    return entry


def is_non_journal(entry) -> bool:
    return (entry.get("type_exact") or "") in ("book", "book-chapter",
                                               "monograph", "report")


# --------------------------------------------------------------------------
# numeric sentences from abstracts (review may quote numbers ONLY from here)
# --------------------------------------------------------------------------

_STOP = set("""a an and are as at be been being by can could did do does for
from had has have how in into is it its may more most no not of on or our over
such than that the their them then there these they this to up was we were what
when where which who why will with within would you your all any both each few
many one only other per same some too under than via""".split())


def _abstract_relevance(entry: dict) -> dict:
    """Cheap sanity check: does the stored abstract use the title's content
    words?  A low overlap is not proof of contamination, but it is a reason
    not to quote that abstract in the review."""
    title = norm_title(entry.get("title_display") or "")
    body = norm_title((entry.get("abstract") or {}).get("text") or "")
    terms = {w for w in title.split() if len(w) > 2 and w not in _STOP}
    if not terms:
        return {"title_terms": 0, "matched": 0, "overlap": None,
                "flag": "no_title_terms"}
    matched = sum(1 for w in terms if w in set(body.split()))
    return {"title_terms": len(terms), "matched": matched,
            "overlap": round(matched / len(terms), 3),
            "flag": "low" if matched / len(terms) < 0.34 else "ok"}


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def numeric_sentences(text: str, limit: int = 4) -> list:
    if not text:
        return []
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    out = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip()
        if len(s) < 40:
            continue
        if re.search(r"\d", s):
            out.append(s)
        if len(out) >= limit:
            break
    return out


def plain_abstract(raw: str) -> str:
    if not raw:
        return ""
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = (txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&#x2019;", "\u2019"))
    return re.sub(r"\s+", " ", txt).strip()


def clean_title(raw: str) -> str:
    """Display form of a deposited title: HTML tags removed, entities decoded,
    whitespace collapsed. ``title_exact`` remains the verbatim record."""
    if not raw:
        return ""
    txt = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\s+", " ", txt).strip()


# --------------------------------------------------------------------------
# full run
# --------------------------------------------------------------------------


def run_full(only=None) -> int:
    started = utc_now()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cands = CANDIDATES
    if only:
        keep = {x.strip().upper() for x in only.split(",") if x.strip()}
        cands = [c for c in CANDIDATES if c["id"] in keep]

    refs, unresolved, diag_out = [], [], []
    for cand in cands:
        print(f"[{cand['id']:>3}] resolving {cand['query'][:70]}...", flush=True)
        hit, diag, reason = resolve_candidate(cand)
        diag["id"] = cand["id"]
        if hit is None:
            diag["outcome"] = "unresolved"
            diag["reason"] = reason
            diag_out.append(diag)
            unresolved.append({
                "id": cand["id"], "category": cand["cat"],
                "candidate_query": cand["query"], "reason": reason,
                "best_hit": diag.get("best_hit"),
                "note": "NOT citable; kept only as a recorded search failure",
            })
            print(f"        -> UNRESOLVED: {reason}", flush=True)
            continue
        entry = build_reference(cand, hit, diag)
        diag["outcome"] = entry["status"]
        diag_out.append(diag)
        if entry["status"] != "verified":
            unresolved.append({
                "id": cand["id"], "category": cand["cat"],
                "candidate_query": cand["query"],
                "reason": f"verification fetch failed: {entry['verification'].get('error')}",
                "best_hit": diag.get("best_hit"),
                "note": "NOT citable",
            })
            print("        -> VERIFY FAILED", flush=True)
            continue
        print(f"        -> {entry['doi']}  {entry['title_exact'][:60]}",
              flush=True)
        refs.append(entry)

    # ---- Europe PMC cross-checks (biomedical coverage; miss is recorded) ----
    print("[..] Europe PMC cross-checks", flush=True)
    for entry in refs:
        cc = epmc_lookup_doi(entry["doi"])
        if cc.get("ok"):
            entry["cross_checks"].append(cc)
            if not entry.get("pmid") and cc.get("pmid"):
                entry["pmid"] = cc["pmid"]
            if not entry.get("abstract") and cc.get("abstract"):
                entry["abstract"] = {
                    "source": "europepmc",
                    "url": cc["url"],
                    "retrieved_utc": cc["retrieved_utc"],
                    "sha256": cc["payload_sha256"],
                    "text": plain_abstract(cc["abstract"]),
                }
        else:
            entry["cross_checks"].append({
                "api": "europepmc", "url": cc["url"],
                "http_status": cc["http_status"],
                "retrieved_utc": cc["retrieved_utc"],
                "payload_sha256": cc["payload_sha256"],
                "ok": False,
                "error": cc.get("error") or "not indexed in Europe PMC",
                "hit_count": 0,
            })

    # ---- OpenAlex: batched cross-check + abstracts (<=2 requests) ----
    print("[..] OpenAlex batch cross-check", flush=True)
    dois = [e["doi"] for e in refs if e["doi"]]
    batches, cur = [], []
    for d in dois:
        cur.append(d)
        if len(cur) >= OPENALEX_BATCH:
            batches.append(cur)
            cur = []
    if cur:
        batches.append(cur)
    if len(batches) > 3:
        batches = batches[:3]
        print("[!] OpenAlex request cap reached; remaining refs not cross-checked",
              flush=True)
    oa_records, oa_meta = {}, []
    for batch in batches:
        res = openalex_batch(batch)
        oa_meta.append({
            "url": res["url"], "http_status": res.get("http_status"),
            "retrieved_utc": res.get("retrieved_utc"),
            "payload_sha256": res.get("payload_sha256"),
            "payload_bytes": res.get("payload_bytes"),
            "requested_dois": len(batch),
            "returned_dois": len(res.get("records") or {}),
            "ok": res.get("ok"), "error": res.get("error"),
        })
        for k, v in (res.get("records") or {}).items():
            oa_records[k] = (v, res)
    for entry in refs:
        d = entry["doi"]
        if d in oa_records:
            rec, res = oa_records[d]
            oa = openalex_entry(rec, res["url"], res["payload_sha256"],
                                res.get("http_status"), res.get("retrieved_utc"))
            entry["cross_checks"].append(oa)
            if not entry.get("abstract") and oa.get("abstract"):
                entry["abstract"] = {
                    "source": "openalex",
                    "url": res["url"],
                    "retrieved_utc": res.get("retrieved_utc"),
                    "sha256": res.get("payload_sha256"),
                    "text": plain_abstract(oa["abstract"]),
                }
        else:
            entry["cross_checks"].append({
                "api": "openalex", "url": None, "ok": False,
                "error": "DOI not returned in the batched OpenAlex request",
            })

    # ---- resolve claim scope, add numeric sentences ----
    for entry in refs:
        if entry.get("abstract") and entry["abstract"].get("text"):
            entry["claim_scope"] = "abstract"
            entry["numeric_sentences"] = numeric_sentences(
                entry["abstract"]["text"])
        else:
            entry["claim_scope"] = "metadata"
            entry["numeric_sentences"] = []

    # ---- flag abstracts that may not describe the work they are attached to ----
    for entry in refs:
        if entry.get("abstract") and entry["abstract"].get("text"):
            entry["abstract_relevance"] = _abstract_relevance(entry)

    # ---- coverage queries ----
    print("[..] coverage queries", flush=True)
    coverage = []
    for label, q in COVERAGE_QUERIES:
        res = crossref_search(q, rows=10)
        coverage.append({
            "label": label,
            "query": q,
            "url": res["url"],
            "http_status": res["status"],
            "retrieved_utc": utc_now(),
            "payload_sha256": res["sha256"],
            "hit_count": len(res["items"]),
            "hits": [{"doi": h["doi"], "title": h["title"],
                      "year": h["year"], "venue": h["venue"]}
                     for h in res["items"]],
        })
        print(f"        {label}: {len(res['items'])} hits", flush=True)

    # ---- assemble ----
    refs.sort(key=lambda e: e["id"])
    by_cat = {}
    for e in refs:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    with_abstract = sum(1 for e in refs if e["claim_scope"] == "abstract")
    with_pmid = sum(1 for e in refs if e.get("pmid"))
    cross_ok = sum(1 for e in refs
                   if any(c.get("ok") for c in e["cross_checks"]))
    payload = {
        "schema": "s029.literature_refs/1",
        "study": "S-029 -- Observable, time-resolved relations in medical "
                 "technology (MedRadar)",
        "generated_utc": utc_now(),
        "run_started_utc": started,
        "generator": {
            "path": "research/studies/relation_network_s029/code/"
                    "s029_lit_verify.py",
            "sha256": sha256_hex(Path(__file__).read_bytes()),
            "python": sys.version.split()[0],
        },
        "verification_policy": {
            "rule": "A reference is citable only if a live metadata record was "
                    "fetched by this script and stored below. No citation is "
                    "written from memory.",
            "resolver": "Crossref query.bibliographic -> best title match, "
                        "gated on title similarity (Jaccard>=0.50 or "
                        "SequenceMatcher>=0.80) plus an author-or-year check.",
            "record_of_truth": "GET https://api.crossref.org/works/{doi} -- "
                               "title/authors/year/venue are copied verbatim.",
            "cross_checks": "Europe PMC DOI lookup (biomedical coverage only) "
                            "and one batched OpenAlex filter=doi call. A miss "
                            "is recorded as a miss, not smoothed over.",
            "payload_hash": "sha256 of the raw HTTP response body bytes of the "
                            "fetch recorded in 'url'.",
            "claim_scope": "abstract = an abstract was retrieved and stored; "
                           "metadata = title/record fields only. Numbers in "
                           "LITERATURE_REVIEW.md may only be quoted from a "
                           "stored abstract sentence or computed here.",
            "negative_claims": "Statements of the form 'we did not find X' are "
                               "scoped to this corpus and to the recorded "
                               "coverage queries. Absence from a keyword "
                               "search is not evidence of non-existence "
                               "(S-028-CORRECTION-1).",
        },
        "rate_limits": {
            "crossref": f"polite pool mailto={MAILTO}; {DELAY_CROSSREF}s "
                        "between calls",
            "europepmc": f"{DELAY_EPMC}s between calls (~1.7 req/s)",
            "openalex": f"hard cap {OPENALEX_MAX_REQUESTS} requests; "
                        f"<= {OPENALEX_BATCH} DOIs per batched filter request; "
                        f"this run used {CALLS.count['openalex']}",
        },
        "counts": {
            "candidates_considered": len(cands),
            "references_verified": len(refs),
            "unresolved_candidates": len(unresolved),
            "with_abstract": with_abstract,
            "metadata_only": len(refs) - with_abstract,
            "with_pmid": with_pmid,
            "with_any_cross_check": cross_ok,
            "by_category": dict(sorted(by_cat.items())),
            "verification_sources": dict(sorted(
                collections.Counter(
                    e["verification"].get("api") for e in refs).items())),
            "resolver_stages": dict(sorted(
                collections.Counter(
                    e["resolver"]["stage"] for e in refs).items())),
            "abstract_sources": dict(sorted(
                collections.Counter(
                    e["abstract"]["source"] for e in refs
                    if e.get("abstract")).items())),
            "abstract_relevance_flags": dict(sorted(
                collections.Counter(
                    (e.get("abstract_relevance") or {}).get("flag")
                    for e in refs if e.get("abstract_relevance")).items())),
            "cross_check_hits": {
                "europepmc": sum(1 for e in refs if any(
                    c.get("api") == "europepmc" and c.get("ok")
                    for c in e["cross_checks"])),
                "openalex": sum(1 for e in refs if any(
                    c.get("api") == "openalex" and c.get("ok")
                    for c in e["cross_checks"])),
            },
            "coverage_queries": len(coverage),
            "openalex_batch_requests": len(oa_meta),
            "api_calls": dict(CALLS.count),
        },
        "search_queries_run": [
            {"id": c["id"], "query": c["query"], "kind": "resolution"}
            for c in cands
        ] + [
            {"label": c["label"], "query": c["query"], "kind": "coverage"}
            for c in coverage
        ],
        "references": refs,
        "unresolved_candidates": unresolved,
        "coverage_queries": coverage,
        "openalex_requests": oa_meta,
        "api_call_log": CALLS.log,
    }
    refs_path = ARTIFACTS / "literature_refs.json"
    refs_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")

    abstracts = {
        "schema": "s029.lit_abstracts/1",
        "generated_utc": utc_now(),
        "note": "Abstract text as returned by the API, for writing the review "
                "without re-reading sources from memory. Only 'abstract' "
                "scope references may be quoted numerically.",
        "abstracts": [
            {
                "id": e["id"], "doi": e["doi"],
                "title_exact": e["title_exact"],
                "source": e["abstract"]["source"],
                "url": e["abstract"]["url"],
                "retrieved_utc": e["abstract"]["retrieved_utc"],
                "sha256": e["abstract"]["sha256"],
                "text": e["abstract"]["text"],
                "numeric_sentences": e["numeric_sentences"],
            }
            for e in refs if e.get("abstract")
        ],
    }
    (ARTIFACTS / "lit_abstracts.json").write_text(
        json.dumps(abstracts, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    diagnostics = {
        "schema": "s029.lit_diagnostics/1",
        "generated_utc": utc_now(),
        "purpose": "Why each candidate did or did not resolve; the audit trail "
                   "behind the reference list.",
        "resolution": diag_out,
        "unresolved": unresolved,
        "api_call_log": CALLS.log,
    }
    (ARTIFACTS / "lit_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print("\n== done ==")
    print(json.dumps(payload["counts"], indent=2))
    print(f"wrote {refs_path}")
    return 0


# --------------------------------------------------------------------------
# offline check
# --------------------------------------------------------------------------

REQUIRED_REF_FIELDS = ["id", "category", "doi", "title_exact", "authors_exact",
                       "year_exact", "verification"]
REQUIRED_VER_FIELDS = ["url", "retrieved_utc", "payload_sha256",
                       "payload_snippet", "http_status"]


def run_offline_check() -> int:
    path = ARTIFACTS / "literature_refs.json"
    if not path.exists():
        print(f"FAIL missing {path}")
        return 1
    doc = json.loads(path.read_text(encoding="utf-8"))
    refs = doc["references"]
    problems = []
    seen_ids, seen_dois = set(), set()
    for e in refs:
        for f in REQUIRED_REF_FIELDS:
            if not e.get(f):
                problems.append(f"{e.get('id')}: missing {f}")
        ver = e.get("verification") or {}
        for f in REQUIRED_VER_FIELDS:
            if not ver.get(f):
                problems.append(f"{e.get('id')}: verification missing {f}")
        sha = ver.get("payload_sha256") or ""
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            problems.append(f"{e.get('id')}: payload_sha256 not 64 hex chars")
        ts = ver.get("retrieved_utc") or ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts):
            problems.append(f"{e.get('id')}: retrieved_utc not ISO-8601 Z")
        if ver.get("http_status") != 200:
            problems.append(f"{e.get('id')}: verifying fetch was not HTTP 200")
        if e["id"] in seen_ids:
            problems.append(f"{e['id']}: duplicate id")
        seen_ids.add(e["id"])
        if not e.get("venue_exact") and (e.get("type_exact") in
                                         ("journal-article", "proceedings-article",
                                          "book-chapter")):
            problems.append(f"{e['id']}: journal-like record has no venue")
        if e["doi"] in seen_dois:
            problems.append(f"{e['id']}: duplicate DOI {e['doi']}")
        seen_dois.add(e["doi"])
        if not e.get("authors_exact"):
            problems.append(f"{e['id']}: empty author list")
    for u in doc.get("unresolved_candidates", []):
        if u.get("id") in seen_ids:
            problems.append(f"{u['id']}: unresolved but also citable")
    n = doc["counts"]["references_verified"]
    if n != len(refs):
        problems.append(f"counts.references_verified={n} != {len(refs)} refs")
    if not (30 <= len(refs) <= 45):
        problems.append(f"corpus size {len(refs)} outside the 30-45 target")
    with_abs = sum(1 for e in refs if e.get("claim_scope") == "abstract")
    if with_abs != doc["counts"]["with_abstract"]:
        problems.append("with_abstract count mismatch")
    if len(doc.get("coverage_queries") or []) < 3:
        problems.append("coverage queries missing (negative claims unscopeable)")
    if problems:
        print(f"FAIL {len(problems)} problem(s) in {path}")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK {path}: {len(refs)} references, {with_abs} with abstract, "
          f"{len(doc['coverage_queries'])} coverage queries, hashes valid, "
          f"no duplicates, no unresolved/id collision.")
    return 0


# --------------------------------------------------------------------------
# discovery helper
# --------------------------------------------------------------------------


def run_discover(query: str, rows: int = 8) -> int:
    res = crossref_search(query, rows=rows)
    print(json.dumps({"query": query, "url": res["url"],
                      "status": res["status"], "sha256": res["sha256"],
                      "hits": res["items"]}, indent=2, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default=None,
                    help="comma-separated reference ids, for debugging")
    ap.add_argument("--discover", default=None,
                    help="run one Crossref bibliographic query and print hits")
    ap.add_argument("--rows", type=int, default=8)
    ap.add_argument("--offline-check", action="store_true",
                    help="validate the written JSON without network access")
    args = ap.parse_args()
    if args.offline_check:
        return run_offline_check()
    if args.discover:
        return run_discover(args.discover, args.rows)
    return run_full(args.only)


if __name__ == "__main__":
    raise SystemExit(main())

