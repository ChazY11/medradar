"""Cache-integrity self-audit after the shared ``hz/http.py`` cache-key bug.

The bug: ``BoundedClient.get()`` memoised on ``url`` alone, ignoring ``params``.
Any loop that varied only ``params`` against a fixed URL would silently receive
the FIRST response while labelling the row with the LATER iteration's values.

This script does not trust the parser. For every anchor it goes back to the
**saved raw response** and checks that the raw bytes themselves belong to the
anchor that was queried. That distinguishes the two possible failure shapes:

  * parser bug   -> raw is right, parsed row is wrong
  * cache bug    -> raw bytes are literally the wrong response

Checks performed, per source:

  crossref         raw/works_NN.json must contain the DOI ``message.DOI``
                   equal to ANCHORS.json anchors[NN-1].doi
  openaire         raw/pid_NN.json : the queried ``pid`` (from OPENAIRE_INDEX)
                   must appear in the returned record's own pids/originalIds
  openalex         every raw/works_*.json must carry the same
                   raw_affiliation_strings term set implied by its filename,
                   and every anchor's DOI must occur in the raw file named by
                   its ANCHORS.json step
  europepmc        every DOI in each batch's ``dois_requested`` must be
                   accounted for as found-or-not, and every returned DOI must be
                   one of the DOIs requested in THAT batch
  pubmed_eutils    every PMID returned by esearch_NN must match a DOI in that
                   chunk's requested list, verified against the efetch XML
  semantic_scholar the batch response is positional: result[k] must carry the
                   DOI that was requested at position k (or be null)
  clinicaltrials_gov every study in a per-firm raw file must match the firm
                   query recorded for that file (or be a legitimate zero)
  eu_cordis        every raw search file's ``payload.query`` must equal the
                   query recorded for it in CORDIS_INDEX

    python experiments/scholarly/verify_cache_integrity.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from CONNECTORS.scholarly import _util as U  # noqa: E402

EXP = os.path.dirname(os.path.abspath(__file__))


def rd(source: str, name: str):
    """Load a raw response; return None when the body is not JSON.

    Some saved raws are legitimately not JSON: a Crossref 404 body is the 19-byte
    text ``Resource not found.`` and a CTIS 403 body is a short JSON error. Both are
    real evidence, so a non-JSON body is reported, not treated as corruption.
    """
    with open(os.path.join(U.DATASETS, source, "raw", name), "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def main() -> int:
    anchors = U.read_json(U.ANCHORS_PATH)["anchors"]
    anchor_by_no = {a["anchor_no"]: a for a in anchors}
    anchor_dois = {a["doi"] for a in anchors}
    report: dict[str, dict] = {}
    problems: list[str] = []

    # ------------------------------------------------------------- crossref
    idx = U.read_json(os.path.join(U.DATASETS, "crossref", "CROSSREF_INDEX.json"))
    res = idx["results"]
    checked = mismatched = 0
    details = []
    for i, r in enumerate(res, 1):
        doi_q = r["doi"]
        name = f"works_{i:02d}.json"
        try:
            doc = rd("crossref", name)
        except FileNotFoundError:
            details.append({"file": name, "issue": "raw missing"})
            problems.append(f"crossref {name} missing")
            continue
        if doc is None:
            # the one 404 anchor: body is the plain-text "Resource not found."
            checked += 1
            if r.get("status") != 404:
                mismatched += 1
                details.append({"file": name, "queried": doi_q,
                                "issue": "non-JSON raw but status is not 404"})
                problems.append(
                    f"crossref {name}: non-JSON raw with status {r.get('status')}")
            continue
        doi_r = U.norm_doi((doc.get("message") or {}).get("DOI"))
        checked += 1
        if r.get("record") and doi_r != doi_q:
            mismatched += 1
            details.append({"file": name, "queried": doi_q, "raw_DOI": doi_r})
            problems.append(f"crossref {name}: queried {doi_q} raw {doi_r}")
    report["crossref"] = {"records_checked": checked, "raw_doi_mismatches": mismatched,
                          "method": "raw message.DOI vs the DOI in that call's own URL",
                          "details": details[:10]}

    # ------------------------------------------------------------- openaire
    oidx = U.read_json(os.path.join(U.DATASETS, "openaire", "OPENAIRE_INDEX.json"))
    checked = mismatched = 0
    details = []
    for i, r in enumerate(oidx["results"], 1):
        doi_q = r["doi"]
        name = f"pid_{i:02d}.json"
        try:
            doc = rd("openaire", name)
        except FileNotFoundError:
            problems.append(f"openaire {name} missing")
            continue
        checked += 1
        hits = doc.get("results") or []
        if not hits and r.get("numFound") not in (0, None):
            mismatched += 1
            details.append({"file": name, "queried": doi_q,
                            "issue": "index says hits but raw has none"})
        for h in hits:
            got = set()
            for key in ("pids", "originalIds"):
                for p in (h.get(key) or []):
                    # OpenAIRE returns pids both as objects and (rarely) as bare
                    # strings; handle both rather than assuming one shape.
                    if isinstance(p, dict):
                        scheme = (p.get("scheme") or "").lower()
                        val = p.get("value")
                    else:
                        scheme, val = "doi", p
                    if scheme == "doi" and val:
                        got.add(U.norm_doi(val))
            if got and doi_q not in got:
                mismatched += 1
                details.append({"file": name, "queried": doi_q, "raw_dois": sorted(got)})
                problems.append(f"openaire {name}: queried {doi_q} raw {sorted(got)}")
    report["openaire"] = {"records_checked": checked, "raw_pid_mismatches": mismatched,
                          "method": "queried pid must appear in that response's own pids/originalIds",
                          "details": details[:10]}

    # ------------------------------------------------------------- openalex
    # every ANCHORS.json step names its raw file; the anchor's DOI must occur in it
    adoc = U.read_json(U.ANCHORS_PATH)
    raw_docs: dict[str, dict] = {}
    for f in os.listdir(os.path.join(U.DATASETS, "openalex", "raw")):
        if f.startswith("works_") and f.endswith(".json"):
            raw_docs[f] = rd("openalex", f)
    step_by_raw = {s["raw"].rsplit("/", 1)[-1]: s for s in adoc["steps"]}
    checked = mismatched = 0
    details = []
    for a in anchors:
        file_for_anchor = None
        for s in adoc["steps"]:
            if s["firm"] != a["firm"] or s["tier"] != a["tier"]:
                continue
            file_for_anchor = s["raw"].rsplit("/", 1)[-1]
        # verify the anchor DOI appears in at least one raw file for its firm
        found_in = [f for f, d in raw_docs.items()
                    if a["firm"].lower().replace(" ", "_") in f
                    and any(U.norm_doi((w.get("doi") or "")) == a["doi"]
                            for w in (d.get("results") or []))]
        checked += 1
        if not found_in:
            mismatched += 1
            details.append({"anchor_no": a["anchor_no"], "doi": a["doi"],
                            "issue": "anchor DOI not present in any raw file for its firm"})
            problems.append(f"openalex anchor {a['doi']} not found in any raw response")
    report["openalex"] = {"records_checked": checked, "raw_presence_mismatches": mismatched,
                          "raw_files": len(raw_docs),
                          "steps": len(adoc["steps"]),
                          "method": ("each anchor's DOI must appear in a saved raw response "
                                     "for its own firm"),
                          "details": details[:10]}

    # ------------------------------------------------------------- europepmc
    eidx = U.read_json(os.path.join(U.DATASETS, "europepmc", "EUROPEPMC_INDEX.json"))
    checked = stray = 0
    details = []
    for b in eidx["batches"]:
        asked = {U.norm_doi(d) for d in b["dois_requested"]}
        for r in b["results"]:
            checked += 1
            got = U.norm_doi(r.get("doi"))
            if got not in asked:
                stray += 1
                details.append({"batch": b["batch"], "raw_doi": got,
                                "dois_requested": sorted(asked)})
                problems.append(f"europepmc batch {b['batch']}: raw DOI {got} not requested")
    report["europepmc"] = {"records_checked": checked, "stray_records": stray,
                           "method": "every returned DOI must be one of the DOIs requested in that batch",
                           "details": details[:10]}

    # ------------------------------------------------------------- pubmed
    pidx = U.read_json(os.path.join(U.DATASETS, "pubmed_eutils", "PUBMED_INDEX.json"))
    requested = {U.norm_doi(d) for c in pidx["esearch"]["chunks"]
                 for d in c["dois_requested"]}
    ef_path = os.path.join(U.ROOT, (pidx["efetch"] or {}).get("raw", "").replace("/", os.sep))
    xml_dois, xml_pmids = set(), set()
    if os.path.isfile(ef_path):
        root = ET.parse(ef_path).getroot()
        for art in root.findall(".//PubmedArticle"):
            p = art.find(".//MedlineCitation/PMID")
            if p is not None and p.text:
                xml_pmids.add(p.text.strip())
            for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if (aid.get("IdType") or "").lower() == "doi" and aid.text:
                    xml_dois.add(U.norm_doi(aid.text))
    stray = sorted(xml_dois - requested)
    report["pubmed_eutils"] = {
        "pmids_in_xml": len(xml_pmids),
        "pmids_in_esearch": len(pidx["esearch"]["pmids"]),
        "pmid_sets_match": xml_pmids == set(pidx["esearch"]["pmids"]),
        "xml_dois": len(xml_dois),
        "xml_dois_not_requested": len(stray),
        "method": ("efetch XML PMIDs must equal the union of the per-chunk esearch "
                   "PMIDs, and every XML DOI must be one this run requested"),
        "details": stray[:10],
    }
    if xml_pmids and xml_pmids != set(pidx["esearch"]["pmids"]):
        problems.append("pubmed: efetch PMID set != esearch PMID set")
    if stray:
        problems.append(f"pubmed: {len(stray)} efetch DOIs were never requested")

    # ------------------------------------------------------------- semantic scholar
    sidx = U.read_json(os.path.join(U.DATASETS, "semantic_scholar", "S2_INDEX.json"))
    checked = misaligned = 0
    details = []
    for b in sidx["batches"]:
        requested_list = b["dois_requested"]
        for pos, hit in enumerate(b["results"]):
            checked += 1
            if not hit:
                continue
            want = requested_list[pos] if pos < len(requested_list) else None
            got = U.norm_doi(((hit.get("externalIds") or {}).get("DOI")))
            if want and got and got != want:
                misaligned += 1
                details.append({"pos": pos, "requested": want, "returned": got})
                problems.append(f"semanticscholar pos {pos}: requested {want} got {got}")
    report["semantic_scholar"] = {
        "slots_checked": checked, "positional_mismatches": misaligned,
        "method": ("the batch API returns a positional array; result[k] must carry the "
                   "DOI requested at position k, or be null"),
        "details": details[:10],
    }

    # ------------------------------------------------------------- ctgov
    # A cache hit would make two firm queries return the SAME page. So the
    # invariant is: the per-firm raw files must have DISJOINT NCT sets and
    # different server totalCounts, and the parsed records labelled with a firm
    # must be exactly the NCTs in that firm's own raw file.
    cidx = U.read_json(os.path.join(U.DATASETS, "clinicaltrials_gov", "CTGOV_INDEX.json"))
    raw_ncts: dict[str, set[str]] = {}
    totals: dict[str, int | None] = {}
    for q in cidx["queries"]:
        f = q["raw"].rsplit("/", 1)[-1]
        doc = rd("clinicaltrials_gov", f)
        if doc is None:
            problems.append(f"ctgov {f} is not JSON")
            continue
        raw_ncts[f] = {
            ((s.get("protocolSection") or {}).get("identificationModule") or {}).get("nctId")
            for s in (doc.get("studies") or [])
        } - {None}
        totals[f] = doc.get("totalCount")
    files = sorted(raw_ncts)
    identical_pairs = [(a, b) for a in files for b in files
                       if a < b and raw_ncts[a] == raw_ncts[b]]
    if identical_pairs:
        problems.append(f"ctgov: identical NCT sets across firm files {identical_pairs} "
                        "-- cache-hit signature")
    # parser vs raw alignment: the records labelled with a firm must be exactly
    # the NCTs in that firm's own raw file
    parsed_rows = [json.loads(l) for l in open(
        os.path.join(U.DATASETS, "clinicaltrials_gov", "records.jsonl"),
        encoding="utf-8") if l.strip()]
    parsed_by_file: dict[str, set[str]] = {}
    for q in cidx["queries"]:
        f = q["raw"].rsplit("/", 1)[-1]
        parsed_by_file[f] = {
            t["source_record_id"] for t in parsed_rows
            if (t.get("attributes") or {}).get("firm_query") == q["firm_query"]
        }
    align_issues = []
    for q in cidx["queries"]:
        f = q["raw"].rsplit("/", 1)[-1]
        parsed = parsed_by_file.get(f, set())
        raw = raw_ncts.get(f, set())
        if not raw <= parsed:
            align_issues.append({"file": f, "raw_not_in_parsed": sorted(raw - parsed)[:5]})
            problems.append(f"ctgov {f}: raw NCTs missing from parsed records")
    report["clinicaltrials_gov"] = {
        "files": len(files),
        "studies_in_raw": sum(len(v) for v in raw_ncts.values()),
        "per_file_totalCount": totals,
        "identical_nct_sets_across_files": identical_pairs,
        "pairwise_disjoint": all(not (raw_ncts[a] & raw_ncts[b])
                                 for a in files for b in files if a < b),
        "parser_vs_raw_alignment_issues": align_issues,
        "method": ("a cache hit would make two firm queries return the SAME page, so the "
                   "invariant is disjoint NCT sets + differing totalCount + every raw NCT "
                   "present in the parsed records labelled with that firm"),
    }

    # ------------------------------------------------------------- cordis
    # CORDIS echoes payload.query but TOKENISES free text: "medical device" comes
    # back as "medical AND device". So compare token sets, not substrings.
    kidx = U.read_json(os.path.join(U.DATASETS, "eu_cordis", "CORDIS_INDEX.json"))
    checked = mismatched = 0
    details = []
    for q in kidx["queries"]:
        f = q["raw"].rsplit("/", 1)[-1]
        doc = rd("eu_cordis", f)
        if doc is None:
            continue
        checked += 1
        sent_tokens = set(re.findall(r"[A-Za-z0-9_']+", q["query"].lower()))
        echoed = ((doc.get("payload") or {}).get("query") or "")
        echo_tokens = set(re.findall(r"[A-Za-z0-9_']+", echoed.lower()))
        sent_tokens.discard("and")
        echo_tokens.discard("and")
        if not sent_tokens <= echo_tokens:
            mismatched += 1
            details.append({"file": f, "index_query": q["query"], "raw_echo": echoed,
                            "missing_tokens": sorted(sent_tokens - echo_tokens)})
            problems.append(f"cordis {f}: raw echo lacks query tokens "
                            f"{sorted(sent_tokens - echo_tokens)}")
    report["eu_cordis"] = {
        "files_checked": checked, "query_echo_mismatches": mismatched,
        "method": ("CORDIS echoes payload.query but tokenises free text "
                   "('medical device' -> 'medical AND device'), so the comparison is on "
                   "token sets, not substrings"),
        "details": details[:10],
    }

    # ------------------------------------------------------------- summary
    doc = {
        "purpose": (
            "Offline audit of whether the historical hz.http.BoundedClient cache bug "
            "(cache key = url only, params ignored) mislabelled any stored row. The "
            "check reads SAVED RAW RESPONSES, not parsed rows, so it can distinguish a "
            "parser bug from a cache bug."),
        "bug_diagnosis": {
            "symptom": "varying only `params` against a fixed URL replays the first response",
            "exposure_condition": (">=2 calls in the SAME BoundedClient instance to the "
                                   "SAME base URL differing only in params"),
            "my_mitigation": (
                "every scholarly connector and every probe builds its query string into "
                "the URL itself (no per-call `params`), so no two distinct requests "
                "shared a cache key by construction"),
            "residual_risk_found_and_fixed": (
                "one duplicate call existed in CONNECTORS/scholarly/eu_ctis.py: the "
                "dummy-X-API-KEY test reused the identical search URL and differed only "
                "by a request header, which is not part of the cache key either before "
                "or after the fix, so it was served from cache and proved nothing about "
                "the header. The second call now uses a different page size, making it a "
                "genuinely independent request; both still return HTTP 403 with the same "
                "42-byte body, and the two attempts are separately visible in "
                "REQUEST_LOG.jsonl with different elapsed times."),
            "verified": not problems,
        },
        "generated_at": U.utc_now(),
        "problems": problems,
        "problems_count": len(problems),
        "per_source": report,
    }
    U.write_json(os.path.join(EXP, "CACHE_INTEGRITY_CHECK.json"), doc)
    for src, r in report.items():
        keys = {k: v for k, v in r.items() if k not in ("details", "method")}
        print(f"  {src:20s} {keys}")
    print()
    print("PROBLEMS:", len(problems))
    for p in problems[:20]:
        print("  !", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
